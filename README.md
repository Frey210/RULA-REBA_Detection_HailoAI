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

## Development

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn edge_agent.app:app --host 0.0.0.0 --port 8765
```

## Raspberry Pi Detection Command

Configure the command used to start the heavy detection pipeline with:

```bash
export EDGE_DETECTION_COMMAND="python -m edge_agent.fake_detection"
```

Replace the fake command with the Hailo YOLO pose pipeline once the model wrapper is implemented.

