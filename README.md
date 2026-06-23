# RULA-REBA Detection HailoAI

Edge node software for Raspberry Pi 5 + Hailo-8.

Current scope:

- Lightweight local edge agent.
- LAN discovery endpoint for Electron.
- Pairing handoff to the central FastAPI backend.
- Start/stop lifecycle wrapper for the heavy detection pipeline.

The heavy Hailo pose pipeline is intentionally not started on boot. The Raspberry Pi should run only the lightweight agent until an authenticated desktop/backend session starts detection.

## Local Agent

Default local API:

```text
http://0.0.0.0:8765
```

Endpoints:

- `GET /health`
- `GET /pairing/info`
- `POST /pairing/complete`
- `POST /detection/start`
- `POST /detection/stop`
- `GET /detection/status`
- `GET /stream/status`
- `GET /stream/mjpeg`

## Development

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn edge_agent.app:app --host 0.0.0.0 --port 8765
```

## Raspberry Pi Detection Command

Configure the Hailo Apps environment with the `websockets` package:

```bash
/home/admin/hailo-apps/venv_hailo_apps/bin/pip install websockets
```

Then configure the command used to start the heavy detection pipeline:

```bash
export EDGE_DETECTION_COMMAND="/home/admin/hailo-apps/venv_hailo_apps/bin/python -m edge_agent.hailo_pose_detection"
export EDGE_HAILO_APPS_DIR=/home/admin/hailo-apps
export EDGE_HAILO_MODEL=/usr/local/hailo/resources/models/hailo8/yolov8m_pose.hef
```

Use `python -m edge_agent.fake_detection` only as a development fallback without Hailo hardware.

## Camera Preview Stream

The local MJPEG stream is intentionally low bandwidth by default. It uses the attached camera when available and falls back to a generated preview frame if the camera cannot be opened.

```bash
export EDGE_STREAM_SOURCE=auto
export EDGE_CAMERA_INDEX=0
export EDGE_CAMERA_DEVICE=/dev/video0
export EDGE_CAMERA_WIDTH=640
export EDGE_CAMERA_HEIGHT=360
export EDGE_CAMERA_FPS=12
```

Use `EDGE_STREAM_SOURCE=demo` to force the generated preview. The Electron client can lower preview FPS to 4 or 8 without stopping detection.

Camera overlays are drawn only from fresh detection coordinates. A detection pipeline can update the preview overlay by posting the latest frame dimensions and detections to:

```text
POST /overlay/latest
```

Payload shape:

```json
{
  "width": 640,
  "height": 360,
  "detections": [
    {
      "worker_id": "worker-1",
      "tracking_id": 1,
      "bbox": [220, 120, 180, 320],
      "keypoints": {"format": "coco17", "points": []}
    }
  ]
}
```
