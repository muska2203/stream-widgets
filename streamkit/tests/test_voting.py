import random
import unittest

from streamkit import VotingRound

OPTIONS = ("rock", "paper", "scissors")


def validate(text: str) -> str:
    t = text.strip().lower()
    if t not in OPTIONS:
        raise ValueError(t)
    return t


def rps_round():
    return VotingRound(validate=validate)


class TestVoting(unittest.TestCase):
    def test_vote_accepted_and_counted(self):
        r = rps_round()
        self.assertTrue(r.vote("alice", "rock"))
        self.assertTrue(r.vote("bob", "ROCK"))
        self.assertTrue(r.vote("carol", "paper"))
        self.assertEqual(r.counts(), {"rock": 2, "paper": 1})
        self.assertEqual(len(r), 3)

    def test_revote_replaces_previous(self):
        r = rps_round()
        r.vote("alice", "rock")
        r.vote("alice", "scissors")
        self.assertEqual(r.counts(), {"scissors": 1})

    def test_invalid_votes_ignored(self):
        r = rps_round()
        for bad in ("hello", "r9", "", "rock " + "x" * 50):
            self.assertFalse(r.vote("troll", bad), msg=bad)
        self.assertEqual(len(r), 0)

    def test_majority_winner(self):
        r = rps_round()
        for user in ("a", "b", "c"):
            r.vote(user, "paper")
        r.vote("d", "rock")
        self.assertEqual(r.winner(random.Random(0)), "paper")

    def test_tie_breaks_among_leaders_only(self):
        r = rps_round()
        r.vote("a", "rock")
        r.vote("b", "rock")
        r.vote("c", "paper")
        r.vote("d", "paper")
        r.vote("e", "scissors")
        seen = {r.winner(random.Random(s)) for s in range(200)}
        self.assertEqual(seen, {"rock", "paper"})

    def test_empty_round_has_no_winner(self):
        self.assertIsNone(rps_round().winner())

    def test_default_validator_accepts_any_nonempty_text(self):
        r = VotingRound()
        self.assertTrue(r.vote("a", "Hello World"))
        self.assertFalse(r.vote("b", "   "))
        self.assertEqual(r.counts(), {"hello world": 1})


if __name__ == "__main__":
    unittest.main()
