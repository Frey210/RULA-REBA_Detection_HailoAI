import sys
import threading
import time
from pathlib import Path

from PIL import Image

from edge_agent.config import settings


def import_cv2():
    try:
        import cv2  # type: ignore

        return cv2
    except ImportError:
        system_packages = Path("/usr/lib/python3/dist-packages")
        if system_packages.exists() and str(system_packages) not in sys.path:
            sys.path.append(str(system_packages))
        try:
            import cv2  # type: ignore

            return cv2
        except ImportError:
            return None


class CameraManager:
    def __init__(self) -> None:
        self.cv2 = import_cv2()
        self.lock = threading.Lock()
        self.thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.latest_frame = None
        self.latest_frame_at = 0.0
        self.opened = False
        self.detail = "Camera has not started"
        self.frame_count = 0

    def ensure_started(self) -> None:
        if settings.edge_stream_source == "demo":
            self.detail = "Stream source is forced to demo"
            return
        if self.cv2 is None:
            self.detail = "OpenCV is not available"
            return
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, name="edge-camera-reader", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=2)

    def read(self, width: int, height: int) -> Image.Image | None:
        self.ensure_started()
        with self.lock:
            if self.latest_frame is None:
                return None
            frame = self.latest_frame.copy()
        if frame.size != (width, height):
            frame = frame.resize((width, height), Image.Resampling.BILINEAR)
        return frame

    def status(self) -> dict:
        self.ensure_started()
        with self.lock:
            age = time.monotonic() - self.latest_frame_at if self.latest_frame_at else None
            healthy = self.opened and age is not None and age < 3
            frame_count = self.frame_count
            detail = self.detail
        return {
            "source": "camera" if healthy else "demo",
            "camera_available": healthy,
            "detail": detail,
            "frame_count": frame_count,
            "frame_age_ms": round(age * 1000) if age is not None else None,
        }

    def _run(self) -> None:
        while not self.stop_event.is_set():
            capture = self._open_capture()
            if capture is None:
                time.sleep(2)
                continue

            try:
                while not self.stop_event.is_set():
                    ok, frame = capture.read()
                    if not ok:
                        self._set_status(False, "Camera read failed; retrying")
                        break

                    rgb = self.cv2.cvtColor(frame, self.cv2.COLOR_BGR2RGB)
                    image = Image.fromarray(rgb)
                    with self.lock:
                        self.latest_frame = image
                        self.latest_frame_at = time.monotonic()
                        self.opened = True
                        self.detail = f"Camera index {settings.edge_camera_index}"
                        self.frame_count += 1
            finally:
                capture.release()
                self._set_status(False, "Camera released; retrying")
                time.sleep(1)

    def _open_capture(self):
        backend = getattr(self.cv2, "CAP_V4L2", 0)
        capture = self.cv2.VideoCapture(settings.edge_camera_index, backend)
        if not capture.isOpened():
            capture.release()
            self._set_status(False, f"Camera index {settings.edge_camera_index} could not be opened")
            return None

        fourcc = self.cv2.VideoWriter_fourcc(*"MJPG")
        capture.set(self.cv2.CAP_PROP_FOURCC, fourcc)
        capture.set(self.cv2.CAP_PROP_FRAME_WIDTH, settings.edge_camera_width)
        capture.set(self.cv2.CAP_PROP_FRAME_HEIGHT, settings.edge_camera_height)
        capture.set(self.cv2.CAP_PROP_FPS, settings.edge_camera_fps)
        if hasattr(self.cv2, "CAP_PROP_BUFFERSIZE"):
            capture.set(self.cv2.CAP_PROP_BUFFERSIZE, 1)

        ok, frame = capture.read()
        if not ok:
            capture.release()
            self._set_status(False, f"Camera index {settings.edge_camera_index} opened but did not return frames")
            return None

        rgb = self.cv2.cvtColor(frame, self.cv2.COLOR_BGR2RGB)
        with self.lock:
            self.latest_frame = Image.fromarray(rgb)
            self.latest_frame_at = time.monotonic()
            self.opened = True
            self.detail = f"Camera index {settings.edge_camera_index}"
            self.frame_count += 1
        return capture

    def _set_status(self, opened: bool, detail: str) -> None:
        with self.lock:
            self.opened = opened
            self.detail = detail


camera_manager = CameraManager()


def camera_status() -> dict:
    if settings.edge_stream_source == "demo":
        return {"source": "demo", "camera_available": False, "detail": "Stream source is forced to demo"}
    return camera_manager.status()
