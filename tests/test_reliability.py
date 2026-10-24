import time
import subprocess
import sys
from uuid import uuid4

from fastapi.testclient import TestClient
from PIL import Image

from edge_agent import frame_store
from edge_agent.app import app
from edge_agent.camera_source import CameraManager
from edge_agent.config import settings
from edge_agent.soft_reid import SoftReIdentifier
from edge_agent.state import EdgeState


def test_persistent_device_identity_and_authentication(tmp_path, monkeypatch):
    state = EdgeState(tmp_path / "state.json")
    identity = state.device_id()
    state.write({"paired": True, "device_token": "test-secret"})
    assert EdgeState(state.path).device_id() == identity
    monkeypatch.setattr("edge_agent.app.edge_state", state)
    client = TestClient(app)
    assert client.get("/pairing/info").json()["device_id"] == identity
    for path in ("/stream/status", "/snapshot/latest", "/network/status", "/detection/status"):
        assert client.get(path).status_code == 403
    assert client.post("/pairing/complete", json={}).status_code == 403
    response = client.get("/detection/status", headers={"Authorization": "Bearer test-secret"})
    assert response.status_code == 200 and response.headers["x-device-id"] == identity


def test_frame_and_overlay_are_one_record_and_buffer_is_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "edge_data_dir", tmp_path)
    run = str(uuid4())
    for frame_id in range(frame_store.MAX_FRAMES + 1):
        frame_store.write_frame(Image.new("RGB", (16, 16), (frame_id, 0, 0)), {
            "run_id": run, "frame_id": frame_id, "captured_monotonic": time.monotonic(),
            "timestamp": 1234, "detections": [{"worker_id": str(frame_id)}],
        }, data_dir=tmp_path)
    assert frame_store.read_frame(run, 0) is None
    image, metadata = frame_store.read_frame()
    assert metadata["frame_id"] == frame_store.MAX_FRAMES
    assert metadata["detections"][0]["worker_id"] == str(frame_store.MAX_FRAMES)
    assert len(list((tmp_path / "frames").glob("*.jpg"))) == frame_store.MAX_FRAMES
    assert frame_store.read_frame("../../outside", 1) is None


def test_hailo_frame_writer_does_not_import_agent_settings(tmp_path):
    subprocess.run([sys.executable, "-c", """
import sys, time
from pathlib import Path
from uuid import uuid4
sys.modules['pydantic_settings'] = None
sys.modules['edge_agent.config'] = None
from PIL import Image
from edge_agent.frame_store import write_frame
write_frame(Image.new('RGB', (16, 16)), {
    'run_id': str(uuid4()), 'frame_id': 1,
    'captured_monotonic': time.monotonic(), 'timestamp': 1,
}, data_dir=Path(sys.argv[1]))
""", str(tmp_path)], check=True, timeout=10)
    assert (tmp_path / "latest_frame.json").is_file()


def test_disconnected_camera_cannot_return_cached_image(monkeypatch):
    camera = CameraManager()
    camera.paused_for_detection = True
    camera.latest_frame = Image.new("RGB", (320, 180))
    camera.latest_frame_at = time.monotonic() - 120
    camera.opened = False
    monkeypatch.setattr(camera, "_read_inference_frame", lambda: None)
    assert camera.read(320, 180) is None


def test_motion_recovers_short_track_gap_without_identity_growth():
    reid = SoftReIdentifier()
    original = reid.assign(1, [1, 0], bbox=[0, 0, 100, 200], now=1)[0]
    reid.prepare_frame({2}, now=1.2)
    recovered = reid.assign(2, [0, 1], bbox=[5, 0, 100, 200], now=1.2)[0]
    assert original == recovered
    for track in range(3, 300):
        reid.prepare_frame({track}, now=track * 20)
        reid.assign(track, [1, 0], now=track * 20)
    assert len(reid.identities) == 1


def test_similar_workers_are_not_forced_into_an_ambiguous_identity():
    reid = SoftReIdentifier()
    first = reid.assign(1, [1, 0], now=1)[0]
    second = reid.assign(2, [1, 0], now=1)[0]
    reid.prepare_frame(set(), now=2)
    third = reid.assign(3, [1, 0], now=2)[0]
    assert third not in {first, second}
