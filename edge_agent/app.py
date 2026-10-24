import socket
import hmac
import time
from datetime import UTC, datetime

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from edge_agent.config import settings
from edge_agent.detection_process import detection_manager
from edge_agent.networking import NetworkCommandError, connect_wifi, network_status, scan_wifi
from edge_agent.schemas import (
    DetectionStartRequest,
    DetectionStatusResponse,
    PairingCompleteRequest,
    PairingCompleteResponse,
    PairingInfo,
    WifiConnectRequest,
)
from edge_agent.state import edge_state
from edge_agent.streaming import mjpeg_frames, snapshot_jpeg
from edge_agent.camera_source import camera_manager, camera_status
from edge_agent.overlay_store import write_latest_overlay
from edge_agent.frame_store import read_frame

app = FastAPI(title="ERGoSIGHT Edge Agent", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def device_auth(request: Request, call_next):
    public = request.url.path in {"/health", "/pairing/info"} or request.method == "OPTIONS"
    state = edge_state.read()
    token = state.get("device_token")
    if not public and (request.url.path != "/pairing/complete" or token):
        supplied = request.headers.get("authorization", "").removeprefix("Bearer ")
        if not token or not hmac.compare_digest(supplied, token):
            return Response("Pair this device again from its owning account", status_code=403,
                            headers={"X-Device-Id": edge_state.device_id()})
    response = await call_next(request)
    response.headers["X-Device-Id"] = edge_state.device_id()
    return response


@app.on_event("shutdown")
def shutdown_camera() -> None:
    detection_manager.stop()
    camera_manager.stop()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/pairing/info", response_model=PairingInfo)
def pairing_info() -> PairingInfo:
    state = edge_state.read()
    return PairingInfo(
        cam_id=state.get("cam_id", settings.edge_cam_id),
        hostname=socket.gethostname(),
        status="running" if detection_manager.status().running else "idle",
        paired=bool(state.get("paired")),
        device_id=edge_state.device_id(),
    )


def require_paired() -> None:
    if not edge_state.read().get("paired"):
        raise HTTPException(status_code=403, detail="Edge node is not paired")


@app.get("/network/status")
def get_network_status() -> dict:
    require_paired()
    try:
        return network_status()
    except NetworkCommandError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/network/wifi")
def get_wifi_networks() -> dict[str, list[dict]]:
    require_paired()
    try:
        return {"networks": scan_wifi()}
    except NetworkCommandError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/network/wifi/connect", status_code=202)
def connect_to_wifi(payload: WifiConnectRequest, background_tasks: BackgroundTasks) -> dict[str, str]:
    require_paired()
    background_tasks.add_task(connect_wifi, payload.ssid, payload.password)
    return {"status": "connecting", "ssid": payload.ssid}


@app.post("/pairing/complete", response_model=PairingCompleteResponse)
async def complete_pairing(payload: PairingCompleteRequest) -> PairingCompleteResponse:
    backend_url = payload.backend_url.rstrip("/")
    request_payload = {
        "pairing_code": payload.pairing_code,
        "cam_id": settings.edge_cam_id,
        "device_id": edge_state.device_id(),
        "hostname": socket.gethostname(),
        "device_type": "raspberry_pi_5_hailo8",
        "metadata": {
            "agent_version": "0.2.0",
            "edge_base_url": payload.edge_base_url,
            "paired_at": datetime.now(UTC).isoformat(),
        },
    }

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            f"{backend_url}/api/v1/device-pairings/complete",
            json=request_payload,
        )

    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)

    edge_state.write(
        {
            "paired": True,
            "cam_id": settings.edge_cam_id,
            "backend_url": backend_url,
            "device_token": response.json()["device_token"],
            "paired_at": datetime.now(UTC).isoformat(),
        }
    )
    return PairingCompleteResponse(status="paired", cam_id=settings.edge_cam_id, backend_url=backend_url)


@app.post("/detection/start", response_model=DetectionStatusResponse)
def start_detection(payload: DetectionStartRequest) -> DetectionStatusResponse:
    require_paired()
    state = edge_state.read()

    backend_url = payload.backend_url or state.get("backend_url") or settings.edge_backend_url
    current = detection_manager.status()
    if not current.running and not camera_status()["camera_available"]:
        raise HTTPException(503, "Camera is unavailable. Connect the USB camera and try again.")
    camera_manager.pause_for_detection()
    try:
        status = detection_manager.start(payload.session_id, backend_url, payload.run_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    deadline = time.monotonic() + 12
    while status.running and not status.ready and time.monotonic() < deadline:
        time.sleep(0.1)
        status = detection_manager.status()
    if not status.ready:
        detection_manager.stop()
        camera_manager.resume_preview()
        raise HTTPException(503, "Pose pipeline did not produce a recent frame. Check the camera and Hailo runtime.")
    if not status.running:
        camera_manager.resume_preview()
    return DetectionStatusResponse(**status.__dict__)


@app.post("/detection/lease")
def renew_detection(payload: DetectionStartRequest) -> dict:
    try:
        detection_manager.renew(payload.session_id, payload.run_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"lease_seconds": 25}


@app.post("/detection/stop", response_model=DetectionStatusResponse)
def stop_detection() -> DetectionStatusResponse:
    status = detection_manager.stop()
    camera_manager.resume_preview()
    return DetectionStatusResponse(**status.__dict__)


@app.get("/detection/status", response_model=DetectionStatusResponse)
def detection_status() -> DetectionStatusResponse:
    status = detection_manager.status()
    if not status.running:
        camera_manager.resume_preview()
    return DetectionStatusResponse(**status.__dict__)


@app.get("/stream/status")
def stream_status() -> dict:
    status = detection_manager.status()
    if not status.running:
        camera_manager.resume_preview()
    source_status = camera_status()
    recorded = read_frame() if status.running else None
    overlay_payload = recorded[1] if recorded else None
    return {
        "available": source_status["camera_available"],
        "running": status.running,
        "cam_id": settings.edge_cam_id,
        **source_status,
        "session_id": status.session_id,
        "run_id": status.run_id,
        "ready": status.ready,
        "overlay_available": overlay_payload is not None,
        "recommended": {
            "width": 640,
            "height": 360,
            "fps": 8,
            "quality": 65,
        },
    }


@app.get("/stream/mjpeg")
def stream_mjpeg(
    width: int = 640,
    height: int = 360,
    fps: int = 8,
    quality: int = 65,
    overlay: bool = True,
) -> StreamingResponse:
    return StreamingResponse(
        mjpeg_frames(width=width, height=height, fps=fps, quality=quality, overlay=overlay),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/snapshot/latest")
def snapshot_latest(
    width: int = 640,
    height: int = 360,
    quality: int = 76,
    overlay: bool = True,
) -> Response:
    content = snapshot_jpeg(width=width, height=height, quality=quality, overlay=overlay)
    if content is None:
        raise HTTPException(status_code=503, detail="No recent camera frame is available")
    return Response(
        content=content,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/snapshot/frames/{frame_id}")
def snapshot_source(frame_id: int, run_id: str, overlay: bool = True) -> Response:
    frame = read_frame(run_id, frame_id, max_age=None)
    if frame is None:
        raise HTTPException(410, "The requested source frame is no longer buffered")
    content = snapshot_jpeg(run_id=run_id, frame_id=frame_id, overlay=overlay)
    if content is None:
        raise HTTPException(410, "Source frame expired")
    return Response(content, media_type="image/jpeg", headers={"Cache-Control": "no-store",
                    "X-Frame-Id": str(frame_id), "X-Run-Id": run_id})


@app.post("/overlay/latest")
def update_overlay(payload: dict) -> dict[str, str]:
    write_latest_overlay(payload)
    return {"status": "ok"}
