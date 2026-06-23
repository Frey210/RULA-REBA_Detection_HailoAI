import asyncio
import json
import os
import time
from urllib.parse import urlparse

import websockets


def websocket_url(backend_url: str, cam_id: str) -> str:
    parsed = urlparse(backend_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    netloc = parsed.netloc or parsed.path
    return f"{scheme}://{netloc}/ws/v1/edge/{cam_id}"


def fake_keypoints(frame_id: int) -> list[dict]:
    offset = (frame_id % 30) - 15
    return [
        {"id": index, "name": f"kp_{index}", "x": 260 + index * 8 + offset, "y": 140 + index * 6, "score": 0.82}
        for index in range(17)
    ]


def fake_event(session_id: str, cam_id: str, frame_id: int) -> dict:
    return {
        "schema_version": "1.0",
        "event_type": "detection",
        "cam_id": cam_id,
        "session_id": session_id,
        "timestamp": int(time.time() * 1000),
        "frame_id": frame_id,
        "detections": [
            {
                "worker_id": "demo-worker-1",
                "tracking_id": 1,
                "confidence": 0.91,
                "reid_confidence": 0.87,
                "bbox": [220, 120, 180, 320],
                "keypoints": {"format": "coco17", "points": fake_keypoints(frame_id)},
                "metadata": {
                    "source": "fake_detection",
                    "rula": {"score": 4, "risk": "medium"},
                    "reba": {"score": 5, "risk": "medium"},
                },
            }
        ],
    }


async def stream_events() -> None:
    session_id = os.getenv("EDGE_SESSION_ID", "SESSION_UNKNOWN")
    cam_id = os.getenv("EDGE_CAM_ID", "CAM_01")
    backend_url = os.getenv("EDGE_BACKEND_URL", "http://127.0.0.1:8000")
    url = websocket_url(backend_url, cam_id)
    frame_id = 0

    while True:
        try:
            async with websockets.connect(url) as websocket:
                print(f"fake detection connected to {url} for {session_id} on {cam_id}", flush=True)
                while True:
                    frame_id += 1
                    await websocket.send(json.dumps(fake_event(session_id, cam_id, frame_id)))
                    await asyncio.sleep(1)
        except Exception as exc:
            print(f"fake detection reconnecting after error: {exc}", flush=True)
            await asyncio.sleep(2)


def main() -> None:
    asyncio.run(stream_events())


if __name__ == "__main__":
    main()
