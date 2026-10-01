"""VotingRound integration with the cube command validator."""

import unittest

from streamkit import VotingRound

from apps.rubiks_cube.core import normalize


class TestCubeVoting(unittest.TestCase):
    def test_cube_moves_validated_case_insensitively(self):
        r = VotingRound(validate=normalize)
        self.assertTrue(r.vote("alice", "u1"))
        self.assertTrue(r.vote("bob", "U1"))
        self.assertTrue(r.vote("carol", "r2"))
        self.assertEqual(r.counts(), {"u1": 2, "r2": 1})

    def test_non_commands_rejected(self):
        r = VotingRound(validate=normalize)
        for bad in ("hello", "u9", "", "u1 " + "x" * 50):
            self.assertFalse(r.vote("troll", bad), msg=bad)
        self.assertEqual(len(r), 0)


if __name__ == "__main__":
    unittest.main()
