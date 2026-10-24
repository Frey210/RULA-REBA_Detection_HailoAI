import os
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class CaptureClock:
    utc_ms: int
    monotonic_s: float
    source: str = "device_clock"

    def timestamp_ms(self, captured_monotonic: float) -> int:
        return int(self.utc_ms + (captured_monotonic - self.monotonic_s) * 1000)

    @classmethod
    def from_environment(cls):
        if os.environ.get("EDGE_CLOCK_UTC_MS") and os.environ.get("EDGE_CLOCK_MONOTONIC_S"):
            return cls(int(os.environ["EDGE_CLOCK_UTC_MS"]), float(os.environ["EDGE_CLOCK_MONOTONIC_S"]),
                       os.environ.get("EDGE_CLOCK_SOURCE", "backend_session_clock"))
        return cls(int(time.time() * 1000), time.monotonic())
