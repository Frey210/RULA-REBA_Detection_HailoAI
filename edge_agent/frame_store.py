import json
import time
from pathlib import Path
from uuid import UUID

from PIL import Image

from edge_agent.config import settings

MAX_FRAMES = 36


def frame_paths(run_id: str, frame_id: int) -> tuple[Path, Path]:
    UUID(run_id)
    if frame_id < 0:
        raise ValueError("Invalid frame ID")
    directory = settings.edge_data_dir / "frames"
    directory.mkdir(parents=True, exist_ok=True)
    base = directory / f"{run_id}_{frame_id:012d}"
    return base.with_suffix(".jpg"), base.with_suffix(".json")


def write_frame(image: Image.Image, payload: dict) -> None:
    jpeg, metadata = frame_paths(payload["run_id"], payload["frame_id"])
    temporary = jpeg.with_suffix(".tmp.jpg")
    image.save(temporary, format="JPEG", quality=82)
    temporary.replace(jpeg)
    temporary = metadata.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload), encoding="utf-8")
    temporary.replace(metadata)
    latest = settings.edge_data_dir / "latest_frame.json"
    temporary = latest.with_suffix(".tmp")
    temporary.write_text(json.dumps({key: payload[key] for key in
                                    ("run_id", "frame_id", "captured_monotonic", "timestamp")}), encoding="utf-8")
    temporary.replace(latest)
    files = sorted(metadata.parent.glob("*.json"), key=lambda p: p.stat().st_mtime)
    for expired in files[:-MAX_FRAMES]:
        expired.with_suffix(".jpg").unlink(missing_ok=True)
        expired.unlink(missing_ok=True)


def read_frame(run_id: str | None = None, frame_id: int | None = None, *, max_age: float | None = 2.5):
    try:
        if run_id is None:
            latest = json.loads((settings.edge_data_dir / "latest_frame.json").read_text())
            run_id, frame_id = latest["run_id"], latest["frame_id"]
        jpeg, metadata = frame_paths(run_id, frame_id)
        payload = json.loads(metadata.read_text())
        if max_age is not None and not 0 <= time.monotonic() - payload["captured_monotonic"] <= max_age:
            return None
        with Image.open(jpeg) as image:
            return image.convert("RGB"), payload
    except (OSError, ValueError, KeyError, TypeError):
        return None
