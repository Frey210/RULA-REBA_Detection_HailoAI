import sys
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


class CameraFrameSource:
    def __init__(self, width: int, height: int, fps: int) -> None:
        self.width = width
        self.height = height
        self.fps = fps
        self.cv2 = import_cv2()
        self.capture = None
        self.available = False
        self.detail = "OpenCV is not available"

    def __enter__(self) -> "CameraFrameSource":
        if settings.edge_stream_source == "demo":
            self.detail = "Stream source is forced to demo"
            return self
        if self.cv2 is None:
            return self

        capture = self.cv2.VideoCapture(settings.edge_camera_index)
        capture.set(self.cv2.CAP_PROP_FRAME_WIDTH, self.width)
        capture.set(self.cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        capture.set(self.cv2.CAP_PROP_FPS, self.fps)

        if not capture.isOpened():
            capture.release()
            self.detail = f"Camera index {settings.edge_camera_index} could not be opened"
            return self

        ok, _frame = capture.read()
        if not ok:
            capture.release()
            self.detail = f"Camera index {settings.edge_camera_index} opened but did not return frames"
            return self

        self.capture = capture
        self.available = True
        self.detail = f"Camera index {settings.edge_camera_index}"
        return self

    def __exit__(self, *_exc) -> None:
        if self.capture is not None:
            self.capture.release()

    def read(self) -> Image.Image | None:
        if not self.available or self.capture is None or self.cv2 is None:
            return None
        ok, frame = self.capture.read()
        if not ok:
            return None
        frame = self.cv2.resize(frame, (self.width, self.height))
        rgb = self.cv2.cvtColor(frame, self.cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb)


def camera_status(width: int = 640, height: int = 360, fps: int = 8) -> dict:
    if settings.edge_stream_source == "demo":
        return {"source": "demo", "camera_available": False, "detail": "Stream source is forced to demo"}
    with CameraFrameSource(width, height, fps) as source:
        return {
            "source": "camera" if source.available else "demo",
            "camera_available": source.available,
            "detail": source.detail,
        }
