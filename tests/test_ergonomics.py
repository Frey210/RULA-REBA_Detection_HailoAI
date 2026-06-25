import unittest

from edge_agent.ergonomics import assess_pose, calculate_pose_angles


def point(point_id: int, x: float, y: float, score: float = 0.95) -> dict:
    return {"id": point_id, "x": x, "y": y, "score": score}


STANDING_POSE = [
    point(0, 100, 35),
    point(3, 92, 42),
    point(4, 108, 42),
    point(5, 80, 70),
    point(6, 120, 70),
    point(7, 80, 115),
    point(8, 120, 115),
    point(9, 80, 150),
    point(10, 120, 150),
    point(11, 85, 155),
    point(12, 115, 155),
    point(13, 85, 220),
    point(14, 115, 220),
    point(15, 85, 285),
    point(16, 115, 285),
]


class ErgonomicsTest(unittest.TestCase):
    def test_standing_pose_has_complete_measurements(self):
        result = calculate_pose_angles(STANDING_POSE)
        self.assertEqual(result["quality"]["status"], "good")
        self.assertEqual(result["quality"]["measured_components"], 8)
        self.assertLess(result["angles"]["neck"], 1)
        self.assertLess(result["angles"]["trunk"], 1)

    def test_assessment_returns_rula_and_reba(self):
        result = assess_pose(STANDING_POSE)
        self.assertIsNotNone(result["rula"])
        self.assertIsNotNone(result["reba"])
        self.assertGreaterEqual(result["rula"]["score"], 1)
        self.assertGreaterEqual(result["reba"]["score"], 1)

    def test_low_confidence_pose_is_rejected(self):
        result = assess_pose([point(5, 80, 70, 0.1), point(6, 120, 70, 0.1)])
        self.assertEqual(result["quality"]["status"], "insufficient")
        self.assertIsNone(result["rula"])
        self.assertIsNone(result["reba"])


if __name__ == "__main__":
    unittest.main()
