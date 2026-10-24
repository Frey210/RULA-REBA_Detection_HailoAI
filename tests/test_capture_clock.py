from edge_agent.capture_clock import CaptureClock


def test_backend_clock_preserves_capture_age_without_device_wall_time(monkeypatch):
    monkeypatch.setenv("EDGE_CLOCK_UTC_MS", "1792823810000")
    monkeypatch.setenv("EDGE_CLOCK_MONOTONIC_S", "100")
    monkeypatch.setenv("EDGE_CLOCK_SOURCE", "backend_session_clock")
    monkeypatch.setattr("time.time", lambda: 1)
    clock = CaptureClock.from_environment()
    assert clock.source == "backend_session_clock"
    assert clock.timestamp_ms(100.75) == 1792823810750
    assert clock.timestamp_ms(99.5) == 1792823809500
    monkeypatch.setattr("time.time", lambda: 9999999999)
    assert clock.timestamp_ms(3700) == 1792827410000


def test_legacy_clock_is_explicitly_device_sourced(monkeypatch):
    monkeypatch.delenv("EDGE_CLOCK_UTC_MS", raising=False)
    monkeypatch.delenv("EDGE_CLOCK_MONOTONIC_S", raising=False)
    monkeypatch.setattr("time.time", lambda: 1000)
    monkeypatch.setattr("time.monotonic", lambda: 50)
    clock = CaptureClock.from_environment()
    assert clock.source == "device_clock"
    assert clock.timestamp_ms(51) == 1001000
