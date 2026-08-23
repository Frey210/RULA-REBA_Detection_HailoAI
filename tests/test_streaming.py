from io import BytesIO
from types import SimpleNamespace

from PIL import Image

from edge_agent import streaming
from edge_agent.hand_landmarks import hand_crop_bounds


def test_snapshot_jpeg_uses_existing_camera_frame(monkeypatch) -> None:
    monkeypatch.setattr(
        streaming.camera_manager,
        "read",
        lambda width, height: Image.new("RGB", (width, height), color=(20, 90, 84)),
    )
    monkeypatch.setattr(
        streaming.detection_manager,
        "status",
        lambda: SimpleNamespace(running=True),
    )
    monkeypatch.setattr(streaming, "read_latest_overlay", lambda: None)

    content = streaming.snapshot_jpeg(width=640, height=360, quality=70, overlay=True)

    assert content is not None
    with Image.open(BytesIO(content)) as image:
        assert image.format == "JPEG"
        assert image.size == (640, 360)


def test_hand_overlay_draws_finger_connections() -> None:
    image = Image.new("RGB", (100, 100), color=(0, 0, 0))
    draw = streaming.ImageDraw.Draw(image)
    points = [
        {"id": 9, "name": "left_wrist", "x": 20, "y": 50, "score": 0.9},
        {"id": 100, "name": "left_hand_wrist", "x": 22, "y": 50, "score": 0.9},
        {"id": 101, "name": "left_hand_thumb_cmc", "x": 30, "y": 45, "score": 0.9},
        {"id": 102, "name": "left_hand_thumb_mcp", "x": 38, "y": 40, "score": 0.9},
    ]

    streaming.draw_keypoints(draw, points, 1, 1)

    assert image.getpixel((34, 42)) == (255, 198, 41)
    assert hand_crop_bounds((10, 10), (10, 50)) == (-30, 24, 80)
