import math
from typing import Any


TABLE_A_REBA = (
    ((1, 2, 3, 4), (1, 2, 3, 4), (3, 3, 5, 6)),
    ((2, 3, 4, 5), (3, 4, 5, 6), (4, 5, 6, 7)),
    ((2, 4, 5, 6), (4, 5, 6, 7), (5, 6, 7, 8)),
    ((3, 5, 6, 7), (5, 6, 7, 8), (6, 7, 8, 9)),
    ((4, 6, 7, 8), (6, 7, 8, 9), (7, 8, 9, 9)),
)
TABLE_B_REBA = (
    ((1, 2, 2), (1, 2, 3)),
    ((1, 2, 3), (2, 3, 4)),
    ((3, 4, 5), (4, 5, 5)),
    ((4, 5, 5), (5, 6, 7)),
    ((6, 7, 8), (7, 8, 8)),
    ((7, 8, 8), (8, 9, 9)),
)
TABLE_C_REBA = (
    (1, 1, 1, 2, 3, 3, 4, 5, 6, 7, 7, 7),
    (1, 2, 2, 3, 4, 4, 5, 6, 6, 7, 7, 8),
    (2, 3, 3, 3, 4, 5, 6, 7, 7, 8, 8, 8),
    (3, 4, 4, 4, 5, 6, 7, 8, 8, 9, 9, 9),
    (4, 4, 4, 5, 6, 7, 8, 8, 9, 9, 9, 9),
    (6, 6, 6, 7, 8, 8, 9, 9, 10, 10, 10, 10),
    (7, 7, 7, 8, 9, 9, 9, 10, 10, 11, 11, 11),
    (8, 8, 8, 9, 10, 10, 10, 10, 10, 11, 11, 11),
    (9, 9, 9, 10, 10, 10, 11, 11, 11, 12, 12, 12),
    (10, 10, 10, 11, 11, 11, 11, 12, 12, 12, 12, 12),
    (11, 11, 11, 11, 12, 12, 12, 12, 12, 12, 12, 12),
    (12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12),
)
TABLE_A_RULA = (
    (((1, 2), (2, 2), (2, 3), (3, 3)), ((2, 2), (2, 2), (3, 3), (3, 3)), ((2, 3), (3, 3), (3, 3), (4, 4))),
    (((2, 3), (3, 3), (3, 4), (4, 4)), ((3, 3), (3, 3), (3, 4), (4, 4)), ((3, 4), (4, 4), (4, 4), (5, 5))),
    (((3, 3), (4, 4), (4, 4), (5, 5)), ((3, 4), (4, 4), (4, 4), (5, 5)), ((4, 4), (4, 4), (4, 5), (5, 5))),
    (((4, 4), (4, 4), (4, 5), (5, 5)), ((4, 4), (4, 4), (4, 5), (5, 5)), ((4, 4), (4, 5), (5, 5), (6, 6))),
    (((5, 5), (5, 5), (5, 6), (6, 7)), ((5, 6), (6, 6), (6, 7), (7, 7)), ((6, 6), (6, 7), (7, 7), (7, 8))),
    (((7, 7), (7, 7), (7, 8), (8, 9)), ((8, 8), (8, 8), (8, 9), (9, 9)), ((9, 9), (9, 9), (9, 9), (9, 9))),
)
TABLE_B_RULA = (
    ((1, 3), (2, 3), (3, 4), (5, 5), (6, 6), (7, 7)),
    ((2, 3), (2, 3), (4, 5), (5, 5), (6, 7), (7, 7)),
    ((3, 3), (3, 4), (4, 5), (5, 6), (6, 7), (7, 7)),
    ((5, 5), (5, 6), (6, 7), (7, 7), (7, 7), (8, 8)),
    ((7, 7), (7, 7), (7, 8), (8, 8), (8, 8), (8, 8)),
    ((8, 8), (8, 8), (8, 8), (8, 9), (9, 9), (9, 9)),
)
TABLE_C_RULA = (
    (1, 2, 3, 3, 4, 5, 5),
    (2, 2, 3, 4, 4, 5, 5),
    (3, 3, 3, 4, 4, 5, 6),
    (3, 3, 3, 4, 5, 6, 6),
    (4, 4, 4, 5, 6, 7, 7),
    (4, 4, 5, 6, 6, 7, 7),
    (5, 5, 6, 6, 7, 7, 7),
    (5, 5, 6, 7, 7, 7, 7),
)


def clamp(value: int | float, minimum: int, maximum: int) -> int:
    return max(minimum, min(int(value), maximum))


def _point_map(points: list[dict[str, Any]], threshold: float) -> dict[int, tuple[float, float]]:
    return {
        int(point["id"]): (float(point["x"]), float(point["y"]))
        for point in points
        if isinstance(point, dict)
        and isinstance(point.get("id"), int)
        and float(point.get("score", 0)) >= threshold
    }


def _midpoint(a: tuple[float, float] | None, b: tuple[float, float] | None):
    if a is None or b is None:
        return None
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def _vector_angle(a: tuple[float, float], b: tuple[float, float]) -> float:
    dot = a[0] * b[0] + a[1] * b[1]
    denominator = math.hypot(*a) * math.hypot(*b)
    if denominator == 0:
        return 0.0
    return math.degrees(math.acos(max(-1.0, min(1.0, dot / denominator))))


def _joint_angle(a, b, c) -> float | None:
    if a is None or b is None or c is None:
        return None
    return _vector_angle((b[0] - a[0], b[1] - a[1]), (c[0] - b[0], c[1] - b[1]))


def _segment_angle(origin, endpoint, reference) -> float | None:
    if origin is None or endpoint is None or reference is None:
        return None
    return _vector_angle(
        (endpoint[0] - origin[0], endpoint[1] - origin[1]),
        (reference[0] - origin[0], reference[1] - origin[1]),
    )


def _neck_angle(shoulder_mid, ear_mid, hip_mid) -> float | None:
    if shoulder_mid is None or ear_mid is None or hip_mid is None:
        return None
    return _vector_angle(
        (ear_mid[0] - shoulder_mid[0], ear_mid[1] - shoulder_mid[1]),
        (shoulder_mid[0] - hip_mid[0], shoulder_mid[1] - hip_mid[1]),
    )


def calculate_pose_angles(points: list[dict[str, Any]], threshold: float = 0.35) -> dict[str, Any]:
    p = _point_map(points, threshold)
    shoulder_mid = _midpoint(p.get(5), p.get(6))
    hip_mid = _midpoint(p.get(11), p.get(12))
    ear_mid = _midpoint(p.get(3), p.get(4)) or p.get(0)

    angles = {
        "neck": _neck_angle(shoulder_mid, ear_mid, hip_mid),
        "trunk": _segment_angle(hip_mid, shoulder_mid, (hip_mid[0], hip_mid[1] - 100)) if hip_mid else None,
        "ua_l": _segment_angle(p.get(5), p.get(7), p.get(11)),
        "ua_r": _segment_angle(p.get(6), p.get(8), p.get(12)),
        "la_l": _joint_angle(p.get(5), p.get(7), p.get(9)),
        "la_r": _joint_angle(p.get(6), p.get(8), p.get(10)),
        "leg_l": _joint_angle(p.get(11), p.get(13), p.get(15)),
        "leg_r": _joint_angle(p.get(12), p.get(14), p.get(16)),
    }
    present = sum(value is not None for value in angles.values())
    angles.update(
        {
            "wrist_l": 0.0,
            "wrist_r": 0.0,
            "wrist_twist": 1,
            "neck_twist_bend": 0,
            "trunk_twist_bend": int(
                angles["trunk"] is not None and float(angles["trunk"]) > 10
            ),
            "ua_l_mod": 0,
            "ua_r_mod": 0,
            "is_lifting": 0,
        }
    )
    rounded = {
        key: round(float(value), 1) if isinstance(value, float) else value
        for key, value in angles.items()
    }
    return {
        "angles": rounded,
        "quality": {
            "status": "good" if present == 8 else "partial" if present >= 5 else "insufficient",
            "measured_components": present,
            "required_components": 8,
            "keypoints_used": len(p),
            "confidence_threshold": threshold,
            "limitations": ["2d_single_camera", "wrist_neutral_estimate"],
        },
    }


def _upper_arm_score(value: float) -> int:
    if value <= 20:
        return 1
    if value <= 45:
        return 2
    if value <= 90:
        return 3
    return 4


def calculate_reba(angles: dict[str, Any]) -> dict[str, Any]:
    neck = float(angles.get("neck") or 0)
    trunk = float(angles.get("trunk") or 0)
    neck_score = clamp((1 if neck <= 20 else 2) + int(angles.get("neck_twist_bend", 0)), 1, 3)
    trunk_score = 1 if trunk <= 5 else 2 if trunk <= 20 else 3 if trunk <= 60 else 4
    trunk_score = clamp(trunk_score + int(angles.get("trunk_twist_bend", 0)), 1, 5)
    left_leg = float(angles.get("leg_l") or 0)
    right_leg = float(angles.get("leg_r") or 0)
    leg_score = 2 if abs(left_leg - right_leg) > 40 else 1
    maximum_leg = max(left_leg, right_leg)
    leg_score = clamp(leg_score + (2 if maximum_leg > 60 else 1 if maximum_leg >= 30 else 0), 1, 4)
    score_a = TABLE_A_REBA[trunk_score - 1][neck_score - 1][leg_score - 1]

    upper_arm = clamp(max(_upper_arm_score(float(angles.get("ua_l") or 0)), _upper_arm_score(float(angles.get("ua_r") or 0))), 1, 6)
    lower_arm = 1 if all(60 <= float(angles.get(side) or 0) <= 100 for side in ("la_l", "la_r")) else 2
    wrist = 1
    score_b = TABLE_B_REBA[upper_arm - 1][lower_arm - 1][wrist - 1]
    score = TABLE_C_REBA[clamp(score_a, 1, 12) - 1][clamp(score_b, 1, 12) - 1]
    risk = "Negligible" if score == 1 else "Low" if score <= 3 else "Medium" if score <= 7 else "High" if score <= 10 else "Very High"
    return {"score": score, "risk": risk, "breakdown": {"score_a": score_a, "score_b": score_b, "trunk_score": trunk_score, "neck_score": neck_score, "leg_score": leg_score, "ua_score": upper_arm, "la_score": lower_arm, "wrist_score": wrist}}


def calculate_rula(angles: dict[str, Any]) -> dict[str, Any]:
    upper_arm = clamp(max(_upper_arm_score(float(angles.get("ua_l") or 0)), _upper_arm_score(float(angles.get("ua_r") or 0))), 1, 6)
    lower_arm = 1 if all(60 <= float(angles.get(side) or 0) <= 100 for side in ("la_l", "la_r")) else 2
    wrist = 1
    twist = 1
    score_a = TABLE_A_RULA[upper_arm - 1][lower_arm - 1][wrist - 1][twist - 1]

    neck = float(angles.get("neck") or 0)
    neck_score = 1 if neck <= 10 else 2 if neck <= 20 else 3
    trunk = float(angles.get("trunk") or 0)
    trunk_score = 1 if trunk <= 5 else 2 if trunk <= 20 else 3 if trunk <= 60 else 4
    left_leg = float(angles.get("leg_l") or 0)
    right_leg = float(angles.get("leg_r") or 0)
    leg_score = 2 if abs(left_leg - right_leg) > 40 else 1
    score_b = TABLE_B_RULA[neck_score - 1][trunk_score - 1][leg_score - 1]
    score = TABLE_C_RULA[clamp(score_a, 1, 8) - 1][clamp(score_b, 1, 7) - 1]
    risk = "Acceptable" if score <= 2 else "Further Investigate" if score <= 4 else "Investigate Soon" if score <= 6 else "Investigate Immediately"
    return {"score": score, "risk": risk, "breakdown": {"score_a": score_a, "score_b": score_b, "ua_score": upper_arm, "la_score": lower_arm, "wrist_score": wrist, "neck_score": neck_score, "trunk_score": trunk_score, "leg_score": leg_score}}


def assess_pose(points: list[dict[str, Any]]) -> dict[str, Any]:
    result = calculate_pose_angles(points)
    if result["quality"]["status"] == "insufficient":
        return {**result, "rula": None, "reba": None}
    return {
        **result,
        "rula": calculate_rula(result["angles"]),
        "reba": calculate_reba(result["angles"]),
    }
