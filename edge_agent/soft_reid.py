import math
import time
from dataclasses import dataclass


@dataclass
class Identity:
    worker_id: str
    signature: list[float]
    last_seen: float
    active_track_id: int | None = None


class SoftReIdentifier:
    def __init__(self, *, ttl_seconds: float = 10.0, similarity_threshold: float = 0.82) -> None:
        self.ttl_seconds = ttl_seconds
        self.similarity_threshold = similarity_threshold
        self.identities: dict[str, Identity] = {}
        self.track_to_worker: dict[int, str] = {}
        self.next_identity = 1

    def assign(
        self,
        track_id: int,
        signature: list[float] | None,
        *,
        now: float | None = None,
    ) -> tuple[str, float, str]:
        now = time.monotonic() if now is None else now
        self._expire_tracks(now)

        current_worker = self.track_to_worker.get(track_id)
        if current_worker:
            identity = self.identities[current_worker]
            identity.last_seen = now
            identity.active_track_id = track_id
            if signature:
                identity.signature = blend_signatures(identity.signature, signature)
            return current_worker, 1.0, "tracked"

        best_identity = None
        best_similarity = -1.0
        if signature:
            for identity in self.identities.values():
                if identity.active_track_id is not None:
                    continue
                if now - identity.last_seen > self.ttl_seconds:
                    continue
                similarity = cosine_similarity(identity.signature, signature)
                if similarity > best_similarity:
                    best_identity = identity
                    best_similarity = similarity

        if best_identity and best_similarity >= self.similarity_threshold:
            best_identity.active_track_id = track_id
            best_identity.last_seen = now
            best_identity.signature = blend_signatures(best_identity.signature, signature or [])
            self.track_to_worker[track_id] = best_identity.worker_id
            return best_identity.worker_id, best_similarity, "reacquired"

        worker_id = f"REID_{self.next_identity:04d}"
        self.next_identity += 1
        self.identities[worker_id] = Identity(
            worker_id=worker_id,
            signature=signature or [],
            last_seen=now,
            active_track_id=track_id,
        )
        self.track_to_worker[track_id] = worker_id
        return worker_id, 1.0 if signature else 0.0, "new"

    def mark_active_tracks(self, active_track_ids: set[int], *, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        for track_id, worker_id in list(self.track_to_worker.items()):
            if track_id in active_track_ids:
                continue
            identity = self.identities.get(worker_id)
            if identity:
                identity.active_track_id = None
                identity.last_seen = now
            self.track_to_worker.pop(track_id, None)
        self._expire_tracks(now)

    def _expire_tracks(self, now: float) -> None:
        for identity in self.identities.values():
            if identity.active_track_id is not None and now - identity.last_seen > self.ttl_seconds:
                self.track_to_worker.pop(identity.active_track_id, None)
                identity.active_track_id = None


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return max(0.0, min(1.0, dot / (left_norm * right_norm)))


def blend_signatures(previous: list[float], current: list[float], alpha: float = 0.2) -> list[float]:
    if not previous:
        return list(current)
    if not current or len(previous) != len(current):
        return list(previous)
    blended = [(1 - alpha) * old + alpha * new for old, new in zip(previous, current)]
    norm = math.sqrt(sum(value * value for value in blended))
    return [value / norm for value in blended] if norm else blended
