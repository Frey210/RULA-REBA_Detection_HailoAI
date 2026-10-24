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
from PIL import Image

from edge_agent.ergonomics import calculate_pose_angles
from edge_agent.hand_landmarks import HandLandmarkDetector
from edge_agent.soft_reid import SoftReIdentifier
from edge_agent.frame_store import write_frame


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
                async with websockets.connect(self.url, additional_headers={
                    "Authorization": "Bearer " + os.environ.get("EDGE_DEVICE_TOKEN", "")
                }) as websocket:
                    while not self.stop_event.is_set():
                        try:
                            event = await asyncio.to_thread(self.events.get, True, 0.5)
                        except queue.Empty:
                            continue
                        await websocket.send(json.dumps(event))
                        ack = json.loads(await asyncio.wait_for(websocket.recv(), timeout=3))
                        if ack.get("event_type") != "ack":
                            print("Backend rejected detection; check session and pairing", flush=True)
            except Exception as exc:
                print(f"Event publisher reconnecting after error: {exc}", flush=True)
                await asyncio.sleep(2)


class PoseCallbackData:
    def __init__(self, base_class, publisher: EventPublisher, data_dir: Path) -> None:
        self._base = base_class()
        self.publisher = publisher
        self.data_dir = data_dir
        self.last_event_publish = 0.0
        self.last_signature_at: dict[int, float] = {}
        self.signature_cache: dict[int, list[float]] = {}
        self.frame_interval = 1 / max(1, int(os.getenv("EDGE_INFERENCE_FRAME_FPS", "8")))
        self.event_interval = 1 / max(1, int(os.getenv("EDGE_EVENT_FPS", "4")))
        self.signature_interval = 1 / max(1, int(os.getenv("EDGE_REID_SIGNATURE_FPS", "2")))
        self.hand_interval = 1 / max(1, int(os.getenv("EDGE_HAND_LANDMARK_FPS", "3")))
        self.hand_detector: HandLandmarkDetector | None = None
        self.hand_detector_attempted = False
        self.reidentifier = SoftReIdentifier(
            ttl_seconds=float(os.getenv("EDGE_REID_TTL_SECONDS", "10")),
            similarity_threshold=float(os.getenv("EDGE_REID_SIMILARITY_THRESHOLD", "0.76")),
            track_grace_seconds=float(os.getenv("EDGE_REID_TRACK_GRACE_SECONDS", "1.5")),
        )

    def __getattr__(self, name):
        return getattr(self._base, name)


def point_score(point) -> float:
    for name in ("confidence", "score"):
        value = getattr(point, name, None)
        if isinstance(value, (int, float)):
            return float(value)
        if callable(value):
            try:
                return float(value())
            except (TypeError, ValueError):
                pass
    return 0.0


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


def eligible_body(detection: dict) -> bool:
    points = {p["id"] for p in detection["points"] if p["score"] >= 0.35}
    return (detection["tracking_id"] > 0 and detection["confidence"] >= 0.5
            and detection["bbox"][2] >= 32 and detection["bbox"][3] >= 90
            and {5, 6}.issubset(points) and bool({11, 12} & points)
            and len(points & set(range(5, 17))) >= 6)


class PoseFrameWorker:
    def __init__(self, user_data):
        self.user_data = user_data
        self.frames = queue.Queue(maxsize=1)
        self.stopped = threading.Event()
        self.candidates = {}
        self.last_hand = 0.0
        self.hand_cursor = 0
        self.dropped = 0
        self.thread = threading.Thread(target=self._run, name="pose-frame-worker", daemon=True)
        self.thread.start()

    def offer(self, item):
        try:
            self.frames.put_nowait(item)
        except queue.Full:
            try:
                self.frames.get_nowait()
            except queue.Empty:
                pass
            self.dropped += 1
            self.frames.put_nowait(item)

    def stop(self):
        self.stopped.set()
        self.thread.join(timeout=5)

    def _run(self):
        last = 0.0
        while not self.stopped.is_set():
            try:
                item = self.frames.get(timeout=0.2)
            except queue.Empty:
                continue
            if time.monotonic() - last < self.user_data.frame_interval:
                self.dropped += 1
                continue
            last = time.monotonic()
            try:
                self.process(*item)
            except Exception:
                import traceback
                traceback.print_exc()

    def process(self, frame, raw, frame_id, captured_at, timestamp):
        now = time.monotonic()
        if now - captured_at > 1.5:
            self.dropped += 1
            return
        data = self.user_data
        if not data.hand_detector_attempted:
            data.hand_detector_attempted = True
            data.hand_detector = HandLandmarkDetector(os.getenv("EDGE_HAND_LANDMARK_MODEL", "./models/hand_landmark_lite.tflite"),
                                                     float(os.getenv("EDGE_HAND_LANDMARK_CONFIDENCE", "0.5")))
        eligible = [d for d in raw if eligible_body(d)]
        active = {d["tracking_id"] for d in eligible}
        data.reidentifier.prepare_frame(active, now=now)
        for track in set(self.candidates) - active:
            self.candidates.pop(track)
        hand_target = None
        if eligible and now - self.last_hand >= data.hand_interval:
            hand_target = eligible[self.hand_cursor % len(eligible)]["tracking_id"]
            self.hand_cursor += 1
            self.last_hand = now
        detections = []
        for detection in eligible:
            track = detection["tracking_id"]
            count, first_seen = self.candidates.get(track, (0, now))
            self.candidates[track] = (count + 1, first_seen)
            if count < 2 or now - first_seen < 0.25:
                continue
            points = detection["points"]
            # Hand positions are used only for the frame on which they were measured.
            if track == hand_target and data.hand_detector is not None:
                points += data.hand_detector.detect(frame, points)
            signature = data.signature_cache.get(track)
            if signature is None or now - data.last_signature_at.get(track, 0) >= data.signature_interval:
                signature = appearance_signature(frame, detection["bbox"])
                data.signature_cache[track] = signature
                data.last_signature_at[track] = now
            worker, confidence, identity_status = data.reidentifier.assign(track, signature, now=now, bbox=detection["bbox"])
            assessment = calculate_pose_angles(points)
            detections.append({"worker_id": worker, "tracking_id": track,
                "confidence": detection["confidence"], "reid_confidence": confidence,
                "bbox": detection["bbox"], "keypoints": {"format": "coco17+hand21", "points": points},
                "metadata": {"source": "hailo_yolov8_pose", "identity_status": identity_status,
                             "reid_method": "motion_and_torso_appearance", "angles": assessment["angles"],
                             "assessment_quality": assessment["quality"]}})
        for track in set(data.signature_cache) - active:
            data.signature_cache.pop(track, None)
            data.last_signature_at.pop(track, None)
        event = {"schema_version": "1.1", "event_type": "detection",
                 "session_id": os.environ["EDGE_SESSION_ID"], "run_id": os.environ["EDGE_RUN_ID"],
                 "cam_id": os.environ.get("EDGE_CAM_ID", "CAM_01"), "timestamp": timestamp,
                 "frame_id": frame_id, "detections": detections}
        payload = {**event, "width": frame.shape[1], "height": frame.shape[0],
                   "captured_monotonic": captured_at, "dropped_frames": self.dropped}
        write_frame(Image.fromarray(frame), payload)
        if now - data.last_event_publish >= data.event_interval:
            data.publisher.publish(event)
            data.last_event_publish = now


def build_callback(hailo, get_caps_from_pad, get_numpy_from_buffer):
    def app_callback(element, buffer, user_data):
        if buffer is None:
            return
        fmt, width, height = get_caps_from_pad(element.get_static_pad("src"))
        if not width or not height:
            return
        frame = get_numpy_from_buffer(buffer, fmt, width, height)
        if frame is None:
            return
        age = 0.0
        clock = element.get_clock()
        if clock and buffer.pts < 2**63:
            age = max(0.0, (clock.get_time() - element.get_base_time() - buffer.pts) / 1e9)
        captured_at = time.monotonic() - age
        timestamp = int((time.time() - age) * 1000)
        raw = []
        for detection in hailo.get_roi_from_buffer(buffer).get_objects_typed(hailo.HAILO_DETECTION):
            if detection.get_label() != "person":
                continue
            tracks = detection.get_objects_typed(hailo.HAILO_UNIQUE_ID)
            if not tracks:
                continue
            bbox = detection.get_bbox()
            landmarks = detection.get_objects_typed(hailo.HAILO_LANDMARKS)
            points = []
            if landmarks:
                for index, point in enumerate(landmarks[0].get_points()[:17]):
                    points.append({"id": index, "name": COCO_KEYPOINTS[index],
                        "x": (float(point.x()) * float(bbox.width()) + float(bbox.xmin())) * width,
                        "y": (float(point.y()) * float(bbox.height()) + float(bbox.ymin())) * height,
                        "score": point_score(point)})
            raw.append({"tracking_id": int(tracks[0].get_id()), "points": points,
                        "confidence": float(detection.get_confidence()),
                        "bbox": [float(bbox.xmin()) * width, float(bbox.ymin()) * height,
                                 float(bbox.width()) * width, float(bbox.height()) * height]})
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB) if fmt == "BGR" else frame.copy()
        user_data.processor.offer((rgb, raw, user_data.get_count(), captured_at, timestamp))
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

    class LowLatencyPose(GStreamerPoseEstimationApp):
        def get_pipeline_string(self):
            self.batch_size = 1
            return super().get_pipeline_string()

    user_data.processor = PoseFrameWorker(user_data)
    app = LowLatencyPose(callback, user_data)
    from gi.repository import Gst
    caps = app.pipeline.get_by_name("source_fps_caps")
    if caps is None:
        raise RuntimeError("Hailo source FPS control was not found")
    caps.set_property("caps", Gst.Caps.from_string(f"video/x-raw,framerate={settings_fps()}/1"))
    for name in ("source_queue_decode", "source_scale_q", "source_convert_q"):
        source_queue = app.pipeline.get_by_name(name)
        if source_queue is not None:
            source_queue.set_property("max-size-buffers", 1)
            source_queue.set_property("leaky", 2)

    def stop_pipeline(_signum, _frame):
        app.shutdown()

    signal.signal(signal.SIGTERM, stop_pipeline)
    signal.signal(signal.SIGINT, stop_pipeline)
    try:
        app.run()
    finally:
        user_data.processor.stop()
        if user_data.hand_detector is not None:
            user_data.hand_detector.close()
        publisher.stop()


def settings_fps() -> int:
    return max(1, min(30, int(os.getenv("EDGE_CAMERA_FPS", "12"))))


if __name__ == "__main__":
    main()
