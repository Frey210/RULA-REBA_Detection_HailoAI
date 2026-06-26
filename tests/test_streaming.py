from io import BytesIO
from types import SimpleNamespace

from PIL import Image

from edge_agent import streaming


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
