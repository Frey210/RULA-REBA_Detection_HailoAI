import unittest

from edge_agent.soft_reid import SoftReIdentifier, cosine_similarity


class SoftReIdentifierTest(unittest.TestCase):
    def test_track_keeps_identity(self):
        reid = SoftReIdentifier()
        first = reid.assign(1, [1.0, 0.0], now=1)
        second = reid.assign(1, [0.98, 0.02], now=2)
        self.assertEqual(first[0], second[0])
        self.assertEqual(second[2], "tracked")

    def test_reacquires_recent_matching_identity(self):
        reid = SoftReIdentifier(ttl_seconds=10, similarity_threshold=0.8)
        worker_id, _, _ = reid.assign(1, [1.0, 0.0], now=1)
        reid.mark_active_tracks(set(), now=3)
        reacquired = reid.assign(7, [0.99, 0.01], now=5)
        self.assertEqual(reacquired[0], worker_id)
        self.assertEqual(reacquired[2], "reacquired")

    def test_does_not_merge_active_workers(self):
        reid = SoftReIdentifier(similarity_threshold=0.8)
        first = reid.assign(1, [1.0, 0.0], now=1)
        second = reid.assign(2, [0.99, 0.01], now=1)
        self.assertNotEqual(first[0], second[0])

    def test_does_not_reacquire_after_ttl(self):
        reid = SoftReIdentifier(ttl_seconds=10, similarity_threshold=0.8)
        first = reid.assign(1, [1.0, 0.0], now=1)
        reid.mark_active_tracks(set(), now=2)
        second = reid.assign(2, [1.0, 0.0], now=13)
        self.assertNotEqual(first[0], second[0])

    def test_cosine_similarity(self):
        self.assertAlmostEqual(cosine_similarity([1, 0], [1, 0]), 1.0)
        self.assertAlmostEqual(cosine_similarity([1, 0], [0, 1]), 0.0)


if __name__ == "__main__":
    unittest.main()
