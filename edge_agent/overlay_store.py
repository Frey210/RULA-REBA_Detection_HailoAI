import json
import time
from pathlib import Path
from typing import Any

from edge_agent.config import settings


OVERLAY_TTL_SECONDS = 2.5


def overlay_path() -> Path:
    return settings.edge_data_dir / "latest_overlay.json"


def read_latest_overlay() -> dict[str, Any] | None:
    path = overlay_path()
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    updated_at = payload.get("updated_at")
    if not isinstance(updated_at, (int, float)):
        return None
    if time.time() - float(updated_at) > OVERLAY_TTL_SECONDS:
        return None
    return payload


def write_latest_overlay(payload: dict[str, Any]) -> None:
    path = overlay_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {**payload, "updated_at": time.time()}
    path.write_text(json.dumps(payload), encoding="utf-8")
