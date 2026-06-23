import socket
from datetime import UTC, datetime

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from edge_agent.config import settings
from edge_agent.detection_process import detection_manager
from edge_agent.schemas import (
    DetectionStartRequest,
    DetectionStatusResponse,
    PairingCompleteRequest,
    PairingCompleteResponse,
    PairingInfo,
)
from edge_agent.state import edge_state
from edge_agent.streaming import mjpeg_frames

app = FastAPI(title="ErgoQuipt Edge Agent", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    )


@app.post("/pairing/complete", response_model=PairingCompleteResponse)
async def complete_pairing(payload: PairingCompleteRequest) -> PairingCompleteResponse:
    backend_url = payload.backend_url.rstrip("/")
    request_payload = {
        "pairing_code": payload.pairing_code,
        "cam_id": settings.edge_cam_id,
        "hostname": socket.gethostname(),
        "device_type": "raspberry_pi_5_hailo8",
        "metadata": {
            "agent_version": "0.1.0",
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
            "paired_at": datetime.now(UTC).isoformat(),
        }
    )
    return PairingCompleteResponse(status="paired", cam_id=settings.edge_cam_id, backend_url=backend_url)


@app.post("/detection/start", response_model=DetectionStatusResponse)
def start_detection(payload: DetectionStartRequest) -> DetectionStatusResponse:
    state = edge_state.read()
    if not state.get("paired"):
        raise HTTPException(status_code=403, detail="Edge node is not paired")

    backend_url = payload.backend_url or state.get("backend_url") or settings.edge_backend_url
    status = detection_manager.start(payload.session_id, backend_url)
    return DetectionStatusResponse(**status.__dict__)


@app.post("/detection/stop", response_model=DetectionStatusResponse)
def stop_detection() -> DetectionStatusResponse:
    status = detection_manager.stop()
    return DetectionStatusResponse(**status.__dict__)


@app.get("/detection/status", response_model=DetectionStatusResponse)
def detection_status() -> DetectionStatusResponse:
    status = detection_manager.status()
    return DetectionStatusResponse(**status.__dict__)


@app.get("/stream/status")
def stream_status() -> dict:
    status = detection_manager.status()
    return {
        "available": True,
        "running": status.running,
        "cam_id": settings.edge_cam_id,
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
