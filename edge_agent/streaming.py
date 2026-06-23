import io
import math
import time
from collections.abc import Generator
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from edge_agent.detection_process import detection_manager
from edge_agent.config import settings
from edge_agent.camera_source import camera_manager
from edge_agent.overlay_store import read_latest_overlay


def mjpeg_frames(
    *,
    width: int = 640,
    height: int = 360,
    fps: int = 8,
    quality: int = 65,
    overlay: bool = True,
) -> Generator[bytes, None, None]:
    width = min(max(width, 320), 960)
    height = min(max(height, 180), 540)
    fps = min(max(fps, 1), 12)
    quality = min(max(quality, 35), 85)
    frame_interval = 1 / fps
    frame_id = 0

    while True:
        started_at = time.monotonic()
        running = detection_manager.status().running
        frame_id += 1
        frame = camera_manager.read(width, height)
        if frame is None:
            image = render_frame(width, height, frame_id, overlay=overlay, running=running)
        else:
            image = render_camera_frame(frame, frame_id, overlay=overlay, running=running)
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=quality, optimize=True)
        jpeg = buffer.getvalue()
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n"
            + f"Content-Length: {len(jpeg)}\r\n\r\n".encode("ascii")
            + jpeg
            + b"\r\n"
        )

        elapsed = time.monotonic() - started_at
        time.sleep(max(0, frame_interval - elapsed))


def render_camera_frame(frame: Image.Image, frame_id: int, *, overlay: bool, running: bool) -> Image.Image:
    image = frame.convert("RGB")
    width, height = image.size
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    draw.rectangle((0, 0, width, 34), fill=(14, 107, 103))
    status = "RUNNING" if running else "IDLE"
    draw.text((12, 11), f"{settings.edge_cam_id}  CAMERA  {status}  {width}x{height}", fill=(245, 250, 249), font=font)
    if overlay and running:
        overlay_payload = read_latest_overlay()
        if overlay_payload:
            draw_detection_overlay(draw, width, height, overlay_payload)
        else:
            draw.text((12, height - 22), "waiting for pose overlay", fill=(245, 250, 249), font=font)
    elif not running:
        draw.text((12, height - 22), "detection stopped; preview only", fill=(245, 250, 249), font=font)
    draw.text((width - 88, height - 22), f"frame {frame_id}", fill=(245, 250, 249), font=font)
    return image


def render_frame(width: int, height: int, frame_id: int, *, overlay: bool, running: bool) -> Image.Image:
    image = Image.new("RGB", (width, height), color=(18, 24, 27))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()

    grid_color = (37, 48, 52)
    for x in range(0, width, 64):
        draw.line((x, 0, x, height), fill=grid_color)
    for y in range(0, height, 48):
        draw.line((0, y, width, y), fill=grid_color)

    draw.rectangle((0, 0, width, 34), fill=(14, 107, 103))
    status = "RUNNING" if running else "IDLE"
    draw.text((12, 11), f"{settings.edge_cam_id}  {status}  {width}x{height}", fill=(245, 250, 249), font=font)

    if not running:
        draw.text((width // 2 - 70, height // 2 - 8), "stream idle", fill=(190, 202, 205), font=font)
        return image

    phase = math.sin(frame_id / 8) * 18
    center_x = width // 2 + int(phase)
    bbox = (
        center_x - width // 8,
        64,
        center_x + width // 8,
        height - 30,
    )

    if overlay:
        draw.rectangle(bbox, outline=(33, 212, 165), width=3)
        draw.text((bbox[0], max(38, bbox[1] - 16)), "worker #1  conf 0.91", fill=(33, 212, 165), font=font)
        draw_skeleton(draw, center_x, height)
    else:
        draw.rectangle(bbox, outline=(118, 133, 138), width=2)

    draw.text((12, height - 22), f"frame {frame_id}", fill=(190, 202, 205), font=font)
    return image


def draw_skeleton(draw: ImageDraw.ImageDraw, center_x: int, height: int) -> None:
    joints = {
        "head": (center_x, 84),
        "neck": (center_x, 126),
        "left_shoulder": (center_x - 44, 142),
        "right_shoulder": (center_x + 44, 142),
        "left_elbow": (center_x - 72, 190),
        "right_elbow": (center_x + 75, 188),
        "left_wrist": (center_x - 92, 238),
        "right_wrist": (center_x + 98, 230),
        "hip": (center_x, 228),
        "left_knee": (center_x - 34, 292),
        "right_knee": (center_x + 38, 292),
        "left_ankle": (center_x - 48, height - 42),
        "right_ankle": (center_x + 52, height - 42),
    }
    bones = [
        ("head", "neck"),
        ("neck", "left_shoulder"),
        ("neck", "right_shoulder"),
        ("left_shoulder", "left_elbow"),
        ("left_elbow", "left_wrist"),
        ("right_shoulder", "right_elbow"),
        ("right_elbow", "right_wrist"),
        ("neck", "hip"),
        ("hip", "left_knee"),
        ("hip", "right_knee"),
        ("left_knee", "left_ankle"),
        ("right_knee", "right_ankle"),
    ]
    for start, end in bones:
        draw.line((*joints[start], *joints[end]), fill=(255, 198, 41), width=4)
    for x, y in joints.values():
        draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=(255, 255, 255), outline=(17, 109, 106), width=2)


def draw_detection_overlay(draw: ImageDraw.ImageDraw, width: int, height: int, payload: dict[str, Any]) -> None:
    detections = payload.get("detections")
    if not isinstance(detections, list):
        return
    source_width = float(payload.get("width") or width)
    source_height = float(payload.get("height") or height)
    scale_x = width / source_width
    scale_y = height / source_height
    font = ImageFont.load_default()

    for detection in detections[:8]:
        if not isinstance(detection, dict):
            continue
        bbox = detection.get("bbox")
        if isinstance(bbox, list) and len(bbox) >= 4:
            x, y, box_width, box_height = [float(value) for value in bbox[:4]]
            left = int(x * scale_x)
            top = int(y * scale_y)
            right = int((x + box_width) * scale_x)
            bottom = int((y + box_height) * scale_y)
            draw.rectangle((left, top, right, bottom), outline=(33, 212, 165), width=3)
            label = str(detection.get("worker_id") or f"track {detection.get('tracking_id', '-')}")
            draw.text((left, max(36, top - 16)), label, fill=(33, 212, 165), font=font)

        keypoints = detection.get("keypoints")
        points = keypoints.get("points") if isinstance(keypoints, dict) else None
        if isinstance(points, list):
            draw_keypoints(draw, points, scale_x, scale_y)


def draw_keypoints(draw: ImageDraw.ImageDraw, points: list, scale_x: float, scale_y: float) -> None:
    point_map = {}
    for point in points:
        if not isinstance(point, dict):
            continue
        score = point.get("score")
        if isinstance(score, (int, float)) and score < 0.35:
            continue
        point_id = point.get("id")
        if not isinstance(point_id, int):
            continue
        point_map[point_id] = (int(float(point.get("x", 0)) * scale_x), int(float(point.get("y", 0)) * scale_y))

    coco_bones = [
        (5, 7),
        (7, 9),
        (6, 8),
        (8, 10),
        (5, 6),
        (5, 11),
        (6, 12),
        (11, 12),
        (11, 13),
        (13, 15),
        (12, 14),
        (14, 16),
        (0, 5),
        (0, 6),
    ]
    for start, end in coco_bones:
        if start in point_map and end in point_map:
            draw.line((*point_map[start], *point_map[end]), fill=(255, 198, 41), width=3)
    for x, y in point_map.values():
        draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=(255, 255, 255), outline=(17, 109, 106), width=2)
