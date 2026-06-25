import asyncio
import json
import os
import queue
import signal
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import cv2

from edge_agent.ergonomics import assess_pose
from edge_agent.soft_reid import SoftReIdentifier


COCO_KEYPOINTS = [
    "nose",
    "left_eye",
    "right_eye",
    "left_ear",
    "right_ear",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
]


def websocket_url(backend_url: str, cam_id: str) -> str:
    parsed = urlparse(backend_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return f"{scheme}://{parsed.netloc}/ws/v1/edge/{cam_id}"


class EventPublisher:
    def __init__(self, url: str) -> None:
        self.url = url
        self.events: queue.Queue[dict] = queue.Queue(maxsize=4)
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name="edge-event-publisher", daemon=True)
        self.thread.start()

    def publish(self, event: dict) -> None:
        if self.events.full():
            try:
                self.events.get_nowait()
            except queue.Empty:
                pass
        self.events.put_nowait(event)

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=3)

    def _run(self) -> None:
        asyncio.run(self._publish_loop())

    async def _publish_loop(self) -> None:
        import websockets

        while not self.stop_event.is_set():
            try:
                async with websockets.connect(self.url) as websocket:
                    while not self.stop_event.is_set():
                        try:
                            event = await asyncio.to_thread(self.events.get, True, 0.5)
                        except queue.Empty:
                            continue
                        await websocket.send(json.dumps(event))
                        await asyncio.wait_for(websocket.recv(), timeout=3)
            except Exception as exc:
                print(f"Event publisher reconnecting after error: {exc}", flush=True)
                await asyncio.sleep(2)


class PoseCallbackData:
    def __init__(self, base_class, publisher: EventPublisher, data_dir: Path) -> None:
        self._base = base_class()
        self.publisher = publisher
        self.data_dir = data_dir
        self.last_frame_write = 0.0
        self.frame_interval = 1 / max(1, int(os.getenv("EDGE_INFERENCE_FRAME_FPS", "8")))
        self.reidentifier = SoftReIdentifier(
            ttl_seconds=float(os.getenv("EDGE_REID_TTL_SECONDS", "10")),
            similarity_threshold=float(os.getenv("EDGE_REID_SIMILARITY_THRESHOLD", "0.82")),
        )

    def __getattr__(self, name):
        return getattr(self._base, name)


def point_score(point) -> float:
    for name in ("confidence", "score"):
        value = getattr(point, name, None)
        if callable(value):
            try:
                return float(value())
            except (TypeError, ValueError):
                pass
    return 1.0


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({**payload, "updated_at": time.time()}), encoding="utf-8")
    temporary.replace(path)


def atomic_write_frame(path: Path, frame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp.jpg")
    if cv2.imwrite(str(temporary), frame, [cv2.IMWRITE_JPEG_QUALITY, 72]):
        temporary.replace(path)


def appearance_signature(frame, bbox: list[float]) -> list[float] | None:
    if frame is None:
        return None
    height, width = frame.shape[:2]
    x, y, box_width, box_height = bbox
    left = max(0, min(width - 1, int(x + box_width * 0.15)))
    right = max(left + 1, min(width, int(x + box_width * 0.85)))
    top = max(0, min(height - 1, int(y + box_height * 0.15)))
    bottom = max(top + 1, min(height, int(y + box_height * 0.7)))
    crop = frame[top:bottom, left:right]
    if crop.size == 0:
        return None
    hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
    histogram = cv2.calcHist([hsv], [0, 1], None, [12, 8], [0, 180, 0, 256])
    cv2.normalize(histogram, histogram)
    return histogram.flatten().astype(float).tolist()


def build_callback(hailo, get_caps_from_pad, get_numpy_from_buffer):
    def app_callback(element, buffer, user_data):
        if buffer is None:
            return

        pad = element.get_static_pad("src")
        image_format, width, height = get_caps_from_pad(pad)
        if not width or not height:
            return

        frame = get_numpy_from_buffer(buffer, image_format, width, height) if user_data.use_frame else None
        roi = hailo.get_roi_from_buffer(buffer)
        detections = []
        active_track_ids = set()
        for detection in roi.get_objects_typed(hailo.HAILO_DETECTION):
            if detection.get_label() != "person":
                continue

            bbox = detection.get_bbox()
            left = float(bbox.xmin()) * width
            top = float(bbox.ymin()) * height
            box_width = float(bbox.width()) * width
            box_height = float(bbox.height()) * height
            track_id = 0
            tracks = detection.get_objects_typed(hailo.HAILO_UNIQUE_ID)
            if tracks:
                track_id = int(tracks[0].get_id())
            active_track_ids.add(track_id)

            points = []
            landmarks = detection.get_objects_typed(hailo.HAILO_LANDMARKS)
            if landmarks:
                for index, point in enumerate(landmarks[0].get_points()[: len(COCO_KEYPOINTS)]):
                    points.append(
                        {
                            "id": index,
                            "name": COCO_KEYPOINTS[index],
                            "x": (float(point.x()) * float(bbox.width()) + float(bbox.xmin())) * width,
                            "y": (float(point.y()) * float(bbox.height()) + float(bbox.ymin())) * height,
                            "score": point_score(point),
                        }
                    )

            bbox_values = [left, top, box_width, box_height]
            signature = appearance_signature(frame, bbox_values)
            worker_id, reid_confidence, identity_status = user_data.reidentifier.assign(
                track_id,
                signature,
            )
            assessment = assess_pose(points)
            detections.append(
                {
                    "worker_id": worker_id,
                    "tracking_id": track_id,
                    "confidence": float(detection.get_confidence()),
                    "reid_confidence": reid_confidence,
                    "bbox": bbox_values,
                    "keypoints": {"format": "coco17", "points": points},
                    "metadata": {
                        "source": "hailo_yolov8_pose",
                        "identity_status": identity_status,
                        "reid_method": "torso_hsv_histogram",
                        "reid_ttl_seconds": user_data.reidentifier.ttl_seconds,
                        "angles": assessment["angles"],
                        "assessment_quality": assessment["quality"],
                        "rula": assessment["rula"],
                        "reba": assessment["reba"],
                    },
                }
            )
        user_data.reidentifier.mark_active_tracks(active_track_ids)

        frame_id = user_data.get_count()
        event = {
            "schema_version": "1.0",
            "event_type": "detection",
            "session_id": os.environ["EDGE_SESSION_ID"],
            "cam_id": os.environ.get("EDGE_CAM_ID", "CAM_01"),
            "timestamp": int(time.time() * 1000),
            "frame_id": frame_id,
            "detections": detections,
        }
        user_data.publisher.publish(event)
        atomic_write_json(
            user_data.data_dir / "latest_overlay.json",
            {"width": width, "height": height, "detections": detections},
        )

        now = time.monotonic()
        if user_data.use_frame and now - user_data.last_frame_write >= user_data.frame_interval:
            if frame is not None:
                if image_format == "RGB":
                    frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                atomic_write_frame(user_data.data_dir / "latest_inference_frame.jpg", frame)
                user_data.last_frame_write = now

    return app_callback


def main() -> None:
    hailo_apps_dir = Path(os.getenv("EDGE_HAILO_APPS_DIR", "/home/admin/hailo-apps"))
    sys.path.insert(0, str(hailo_apps_dir))

    import hailo
    from hailo_apps.python.core.common.buffer_utils import get_caps_from_pad, get_numpy_from_buffer
    from hailo_apps.python.core.gstreamer import gstreamer_app
    from hailo_apps.python.core.gstreamer.gstreamer_app import app_callback_class
    from hailo_apps.python.pipeline_apps.pose_estimation.pose_estimation_pipeline import GStreamerPoseEstimationApp

    gstreamer_app.GST_VIDEO_SINK = "fakesink"
    cam_id = os.getenv("EDGE_CAM_ID", "CAM_01")
    publisher = EventPublisher(websocket_url(os.environ["EDGE_BACKEND_URL"], cam_id))
    user_data = PoseCallbackData(app_callback_class, publisher, Path(os.getenv("EDGE_DATA_DIR", "./data")))
    callback = build_callback(hailo, get_caps_from_pad, get_numpy_from_buffer)

    original_argv = sys.argv
    sys.argv = [
        original_argv[0],
        "--input",
        os.getenv("EDGE_CAMERA_DEVICE", "/dev/video0"),
        "--hef-path",
        os.getenv("EDGE_HAILO_MODEL", "/usr/local/hailo/resources/models/hailo8/yolov8m_pose.hef"),
        "--arch",
        "hailo8",
        "--use-frame",
        "--width",
        os.getenv("EDGE_CAMERA_WIDTH", "640"),
        "--height",
        os.getenv("EDGE_CAMERA_HEIGHT", "360"),
        "--frame-rate",
        os.getenv("EDGE_CAMERA_FPS", "12"),
        "--disable-sync",
    ]

    app = GStreamerPoseEstimationApp(callback, user_data)

    def stop_pipeline(_signum, _frame):
        app.shutdown()

    signal.signal(signal.SIGTERM, stop_pipeline)
    signal.signal(signal.SIGINT, stop_pipeline)
    try:
        app.run()
    finally:
        publisher.stop()


if __name__ == "__main__":
    main()
