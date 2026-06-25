import os
import signal
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
            "EDGE_DATA_DIR": str(settings.edge_data_dir),
            "EDGE_CAMERA_DEVICE": settings.edge_camera_device,
            "EDGE_CAMERA_WIDTH": str(settings.edge_camera_width),
            "EDGE_CAMERA_HEIGHT": str(settings.edge_camera_height),
            "EDGE_HAILO_APPS_DIR": str(settings.edge_hailo_apps_dir),
            "EDGE_HAILO_MODEL": settings.edge_hailo_model,
            "EDGE_INFERENCE_FRAME_FPS": str(settings.edge_inference_frame_fps),
            "EDGE_REID_TTL_SECONDS": str(settings.edge_reid_ttl_seconds),
            "EDGE_REID_SIMILARITY_THRESHOLD": str(settings.edge_reid_similarity_threshold),
        }
        self.process = subprocess.Popen(
            shlex.split(settings.edge_detection_command),
            env=env,
            start_new_session=True,
        )
        return self.status()

    def stop(self) -> DetectionStatus:
        if self.process and self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=2)
        return self.status()


detection_manager = DetectionProcessManager()
