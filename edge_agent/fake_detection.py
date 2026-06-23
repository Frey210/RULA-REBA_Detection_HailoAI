import asyncio
import json
import os
import time
from urllib.parse import urlparse

import httpx
import websockets


def websocket_url(backend_url: str, cam_id: str) -> str:
    parsed = urlparse(backend_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    netloc = parsed.netloc or parsed.path
    return f"{scheme}://{netloc}/ws/v1/edge/{cam_id}"


def fake_keypoints(frame_id: int, base_x: int, base_y: int) -> list[dict]:
    offset = (frame_id % 30) - 15
    return [
        {"id": index, "name": f"kp_{index}", "x": base_x + index * 5 + offset, "y": base_y + index * 5, "score": 0.82}
        for index in range(17)
    ]


def fake_detections(frame_id: int) -> list[dict]:
    offset = (frame_id % 30) - 15
    workers = [
        ("worker-a", 1, 165 + offset, 72, 145, 265, 0.91, 0.87, 4, 5, "medium"),
        ("worker-b", 2, 350 - offset, 92, 135, 245, 0.86, 0.78, 6, 7, "high"),
    ]
    return [
        {
            "worker_id": worker_id,
            "tracking_id": tracking_id,
            "confidence": confidence,
            "reid_confidence": reid_confidence,
            "bbox": [x, y, width, height],
            "keypoints": {"format": "coco17", "points": fake_keypoints(frame_id, x + 35, y + 45)},
            "metadata": {
                "source": "fake_detection",
                "rula": {"score": rula, "risk": risk},
                "reba": {"score": reba, "risk": risk},
            },
        }
        for worker_id, tracking_id, x, y, width, height, confidence, reid_confidence, rula, reba, risk in workers
    ]


def fake_overlay(frame_id: int) -> dict:
    detections = fake_detections(frame_id)
    return {
        "width": 640,
        "height": 360,
        "detections": [
            {
                "worker_id": detection["worker_id"],
                "tracking_id": detection["tracking_id"],
                "bbox": detection["bbox"],
                "keypoints": detection["keypoints"],
            }
            for detection in detections
        ],
    }


def fake_event(session_id: str, cam_id: str, frame_id: int) -> dict:
    return {
        "schema_version": "1.0",
        "event_type": "detection",
        "cam_id": cam_id,
        "session_id": session_id,
        "timestamp": int(time.time() * 1000),
        "frame_id": frame_id,
        "detections": fake_detections(frame_id),
    }


async def stream_events() -> None:
    session_id = os.getenv("EDGE_SESSION_ID", "SESSION_UNKNOWN")
    cam_id = os.getenv("EDGE_CAM_ID", "CAM_01")
    backend_url = os.getenv("EDGE_BACKEND_URL", "http://127.0.0.1:8000")
    overlay_url = os.getenv("EDGE_OVERLAY_URL", "http://127.0.0.1:8765/overlay/latest")
    url = websocket_url(backend_url, cam_id)
    frame_id = 0

    while True:
        try:
            async with websockets.connect(url) as websocket, httpx.AsyncClient(timeout=1) as client:
                print(f"fake detection connected to {url} for {session_id} on {cam_id}", flush=True)
                while True:
                    frame_id += 1
                    await websocket.send(json.dumps(fake_event(session_id, cam_id, frame_id)))
                    try:
                        await client.post(overlay_url, json=fake_overlay(frame_id))
                    except httpx.HTTPError as exc:
                        print(f"fake overlay update failed: {exc}", flush=True)
                    await asyncio.sleep(1)
        except Exception as exc:
            print(f"fake detection reconnecting after error: {exc}", flush=True)
            await asyncio.sleep(2)


def main() -> None:
    asyncio.run(stream_events())


if __name__ == "__main__":
    main()
