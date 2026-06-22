import os
import shlex
import subprocess
from dataclasses import dataclass

from edge_agent.config import settings


@dataclass
class DetectionStatus:
    running: bool
    pid: int | None
    command: str


class DetectionProcessManager:
    def __init__(self) -> None:
        self.process: subprocess.Popen | None = None

    def status(self) -> DetectionStatus:
        if self.process and self.process.poll() is None:
            return DetectionStatus(True, self.process.pid, settings.edge_detection_command)
        return DetectionStatus(False, None, settings.edge_detection_command)

    def start(self, session_id: str, backend_url: str) -> DetectionStatus:
        current = self.status()
        if current.running:
            return current

        if not settings.edge_detection_command:
            return DetectionStatus(False, None, "")

        env = {
            **os.environ,
            "EDGE_SESSION_ID": session_id,
            "EDGE_BACKEND_URL": backend_url,
            "EDGE_CAM_ID": settings.edge_cam_id,
        }
        self.process = subprocess.Popen(
            shlex.split(settings.edge_detection_command),
            env=env,
        )
        return self.status()

    def stop(self) -> DetectionStatus:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
        return self.status()


detection_manager = DetectionProcessManager()
