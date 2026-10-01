import unittest

from streamkit import VoteLoop


class TestVoteLoop(unittest.TestCase):
    def make_loop(self, duration=10.0, **kw):
        self.ended = []
        return VoteLoop(duration, lambda w, c, n: self.ended.append((w, c, n)),
                        **kw)

    def test_timer_expiry_fires_callback_with_winner(self):
        loop = self.make_loop()
        loop.vote("a", "u1")
        loop.vote("b", "u1")
        loop.vote("c", "r2")
        loop.update(9.0)
        self.assertEqual(self.ended, [])
        loop.update(1.5)
        self.assertEqual(len(self.ended), 1)
        winner, counts, n = self.ended[0]
        self.assertEqual(winner, "u1")
        self.assertEqual(counts, {"u1": 2, "r2": 1})
        self.assertEqual(n, 3)
        self.assertFalse(loop.active)

    def test_empty_round_reports_none_winner(self):
        loop = self.make_loop()
        loop.update(11.0)
        self.assertEqual(self.ended, [(None, {}, 0)])

    def test_votes_rejected_while_inactive(self):
        loop = self.make_loop()
        loop.update(10.0)  # fires and deactivates
        self.assertFalse(loop.vote("a", "u1"))

    def test_start_opens_fresh_round(self):
        loop = self.make_loop()
        loop.vote("a", "u1")
        loop.update(10.0)
        loop.start()
        self.assertTrue(loop.active)
        self.assertEqual(loop.time_left, 10.0)
        self.assertEqual(loop.counts(), {})
        self.assertTrue(loop.vote("b", "r2"))

    def test_finish_ends_round_immediately(self):
        loop = self.make_loop()
        loop.vote("a", "u1")
        loop.finish()
        self.assertEqual(len(self.ended), 1)
        self.assertFalse(loop.active)


if __name__ == "__main__":
    unittest.main()
