import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np


HAND_LANDMARK_NAMES = (
    "wrist",
    "thumb_cmc",
    "thumb_mcp",
    "thumb_ip",
    "thumb_tip",
    "index_mcp",
    "index_pip",
    "index_dip",
    "index_tip",
    "middle_mcp",
    "middle_pip",
    "middle_dip",
    "middle_tip",
    "ring_mcp",
    "ring_pip",
    "ring_dip",
    "ring_tip",
    "pinky_mcp",
    "pinky_pip",
    "pinky_dip",
    "pinky_tip",
)


def _point_map(points: list[dict[str, Any]]) -> dict[int, tuple[float, float]]:
    return {
        int(point["id"]): (float(point["x"]), float(point["y"]))
        for point in points
        if isinstance(point, dict)
        and isinstance(point.get("id"), int)
        and float(point.get("score", 0)) >= 0.35
    }


def hand_crop_bounds(
    elbow: tuple[float, float], wrist: tuple[float, float]
) -> tuple[int, int, int]:
    dx, dy = wrist[0] - elbow[0], wrist[1] - elbow[1]
    forearm_length = math.hypot(dx, dy)
    if forearm_length < 8:
        return int(wrist[0] - 32), int(wrist[1] - 32), 64
    size = max(64, min(224, int(forearm_length * 2.0)))
    center_x = wrist[0] + dx / forearm_length * forearm_length * 0.35
    center_y = wrist[1] + dy / forearm_length * forearm_length * 0.35
    return int(center_x - size / 2), int(center_y - size / 2), size


def _crop_with_padding(frame: np.ndarray, left: int, top: int, size: int) -> np.ndarray:
    height, width = frame.shape[:2]
    crop = np.zeros((size, size, 3), dtype=np.uint8)
    source_left, source_top = max(0, left), max(0, top)
    source_right, source_bottom = min(width, left + size), min(height, top + size)
    if source_right > source_left and source_bottom > source_top:
        crop[
            source_top - top : source_bottom - top,
            source_left - left : source_right - left,
        ] = frame[source_top:source_bottom, source_left:source_right]
    return crop


def _aligned_hand_crop(
    frame: np.ndarray,
    elbow: tuple[float, float],
    wrist: tuple[float, float],
) -> tuple[np.ndarray, int, int, int, np.ndarray]:
    left, top, size = hand_crop_bounds(elbow, wrist)
    crop = _crop_with_padding(frame, left, top, size)
    angle = math.degrees(math.atan2(wrist[1] - elbow[1], wrist[0] - elbow[0])) + 90
    matrix = cv2.getRotationMatrix2D((size / 2, size / 2), angle, 1)
    aligned = cv2.warpAffine(crop, matrix, (size, size), flags=cv2.INTER_LINEAR)
    return aligned, left, top, size, cv2.invertAffineTransform(matrix)


class HandLandmarkDetector:
    def __init__(self, model_path: str, confidence_threshold: float = 0.5) -> None:
        self.enabled = False
        self.confidence_threshold = confidence_threshold
        path = Path(model_path)
        if not path.is_file():
            print(f"Hand landmarks disabled: model not found at {path}", flush=True)
            return

        try:
            from ai_edge_litert.interpreter import Interpreter

            self.interpreter = Interpreter(model_path=str(path), num_threads=2)
            self.interpreter.allocate_tensors()
            self.input_index = self.interpreter.get_input_details()[0]["index"]
            outputs = {item["name"]: item["index"] for item in self.interpreter.get_output_details()}
            self.landmark_index = outputs["Identity"]
            self.confidence_index = outputs["Identity_1"]
            self.enabled = True
        except Exception as exc:
            print(f"Hand landmarks disabled: {exc}", flush=True)

    def close(self) -> None:
        self.enabled = False

    def detect(self, frame: np.ndarray, body_points: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        body = _point_map(body_points)
        detected: list[dict[str, Any]] = []
        for side, elbow_id, wrist_id, id_offset in (
            ("left", 7, 9, 100),
            ("right", 8, 10, 200),
        ):
            elbow, wrist = body.get(elbow_id), body.get(wrist_id)
            if elbow is None or wrist is None:
                continue
            crop, left, top, size, inverse = _aligned_hand_crop(frame, elbow, wrist)
            model_input = cv2.resize(crop, (224, 224), interpolation=cv2.INTER_LINEAR)
            self.interpreter.set_tensor(
                self.input_index, model_input[np.newaxis, ...].astype(np.float32) / 255.0
            )
            self.interpreter.invoke()
            confidence = float(self.interpreter.get_tensor(self.confidence_index).reshape(-1)[0])
            if confidence < self.confidence_threshold:
                continue
            landmarks = self.interpreter.get_tensor(self.landmark_index).reshape(21, 3)
            for index, (x, y, _z) in enumerate(landmarks):
                crop_x, crop_y = inverse @ np.array(
                    [float(x) / 224 * size, float(y) / 224 * size, 1]
                )
                detected.append(
                    {
                        "id": id_offset + index,
                        "name": f"{side}_hand_{HAND_LANDMARK_NAMES[index]}",
                        "x": max(0.0, min(float(frame.shape[1] - 1), left + float(crop_x))),
                        "y": max(0.0, min(float(frame.shape[0] - 1), top + float(crop_y))),
                        "score": confidence,
                    }
                )
        return detected
