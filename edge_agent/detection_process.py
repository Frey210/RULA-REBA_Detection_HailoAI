import os
import signal
import shlex
import subprocess
import json
import threading
import time
from dataclasses import dataclass

from edge_agent.config import settings


@dataclass
class DetectionStatus:
    running: bool
    pid: int | None
    command: str
    session_id: str | None = None
    run_id: str | None = None
    ready: bool = False
    frame_age_ms: int | None = None


class DetectionProcessManager:
    def __init__(self) -> None:
        self.process: subprocess.Popen | None = None
        self.session_id = None
        self.run_id = None
        self.lease_until = 0.0
        self.lock = threading.RLock()
        threading.Thread(target=self._watchdog, name="detection-lease", daemon=True).start()

    def status(self) -> DetectionStatus:
        with self.lock:
            running = bool(self.process and self.process.poll() is None)
            age = None
            try:
                manifest = json.loads((settings.edge_data_dir / "latest_frame.json").read_text())
                if manifest.get("run_id") == self.run_id:
                    age = max(0, int((time.monotonic() - manifest["captured_monotonic"]) * 1000))
            except (OSError, ValueError, KeyError, TypeError):
                pass
            return DetectionStatus(running, self.process.pid if running else None,
                                   settings.edge_detection_command, self.session_id, self.run_id,
                                   running and age is not None and age < 2500, age)

    def start(self, session_id: str, backend_url: str, run_id: str) -> DetectionStatus:
        with self.lock:
            return self._start(session_id, backend_url, run_id)

    def _start(self, session_id: str, backend_url: str, run_id: str) -> DetectionStatus:
        current = self.status()
        if current.running:
            if (session_id, run_id) != (self.session_id, self.run_id):
                raise ValueError("This camera is already running another session")
            self.renew(session_id, run_id)
            return current

        if not settings.edge_detection_command:
            return DetectionStatus(False, None, "")

        from edge_agent.state import edge_state
        self.session_id, self.run_id = session_id, run_id
        self.lease_until = time.monotonic() + 25
        env = {
            **os.environ,
            "EDGE_SESSION_ID": session_id,
            "EDGE_RUN_ID": run_id,
            "EDGE_DEVICE_TOKEN": edge_state.read().get("device_token", ""),
            "EDGE_BACKEND_URL": backend_url,
            "EDGE_CAM_ID": settings.edge_cam_id,
            "EDGE_DATA_DIR": str(settings.edge_data_dir),
            "EDGE_CAMERA_DEVICE": settings.edge_camera_device,
            "EDGE_CAMERA_WIDTH": str(settings.edge_camera_width),
            "EDGE_CAMERA_HEIGHT": str(settings.edge_camera_height),
            "EDGE_CAMERA_FPS": str(settings.edge_camera_fps),
            "EDGE_HAILO_APPS_DIR": str(settings.edge_hailo_apps_dir),
            "EDGE_HAILO_MODEL": settings.edge_hailo_model,
            "EDGE_HAND_LANDMARK_MODEL": settings.edge_hand_landmark_model,
            "EDGE_HAND_LANDMARK_FPS": str(settings.edge_hand_landmark_fps),
            "EDGE_HAND_LANDMARK_CONFIDENCE": str(settings.edge_hand_landmark_confidence),
            "EDGE_INFERENCE_FRAME_FPS": str(settings.edge_inference_frame_fps),
            "EDGE_EVENT_FPS": str(settings.edge_event_fps),
            "EDGE_REID_SIGNATURE_FPS": str(settings.edge_reid_signature_fps),
            "EDGE_REID_TTL_SECONDS": str(settings.edge_reid_ttl_seconds),
            "EDGE_REID_SIMILARITY_THRESHOLD": str(settings.edge_reid_similarity_threshold),
            "EDGE_REID_TRACK_GRACE_SECONDS": str(settings.edge_reid_track_grace_seconds),
        }
        self.process = subprocess.Popen(
            shlex.split(settings.edge_detection_command),
            env=env,
            start_new_session=True,
        )
        return self.status()

    def renew(self, session_id: str, run_id: str) -> None:
        with self.lock:
            if (session_id, run_id) != (self.session_id, self.run_id) or not self.status().running:
                raise ValueError("Session is not running on this camera")
            self.lease_until = time.monotonic() + 25

    def _watchdog(self) -> None:
        while True:
            time.sleep(1)
            with self.lock:
                if self.process and self.process.poll() is None and time.monotonic() > self.lease_until:
                    self.stop()

    def stop(self) -> DetectionStatus:
        with self.lock:
            return self._stop()

    def _stop(self) -> DetectionStatus:
        if self.process and self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=2)
        return self.status()


detection_manager = DetectionProcessManager()
