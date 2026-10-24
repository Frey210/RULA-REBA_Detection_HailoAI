import json
import os
import threading
import uuid
from pathlib import Path
from typing import Any

from edge_agent.config import settings


class EdgeState:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()

    def read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        with self.lock:
            return json.loads(self.path.read_text(encoding="utf-8"))

    def write(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock:
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps({**self.read(), **payload}, indent=2), encoding="utf-8")
            os.chmod(temporary, 0o600)
            temporary.replace(self.path)

    def device_id(self) -> str:
        with self.lock:
            value = self.read().get("device_id")
            if not value:
                value = str(uuid.uuid4())
                self.write({"device_id": value})
            return value


edge_state = EdgeState(settings.edge_data_dir / "edge_state.json")

