"""Tests for the digit vote validator and its VotingRound integration."""

from __future__ import annotations

import unittest

from streamkit import VotingRound

from apps.interactive_story.core import make_choice_validator


class ValidatorTests(unittest.TestCase):
    def setUp(self):
        self.validate = make_choice_validator(3)

    def test_accepts_digits_in_range(self):
        for text, want in [("1", "1"), ("2", "2"), ("3", "3"), (" 2 ", "2")]:
            with self.subTest(text=text):
                self.assertEqual(self.validate(text), want)

    def test_rejects_out_of_range_and_garbage(self):
        for text in ["0", "4", "10", "a", "hello", "", "один", "1!"]:
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    self.validate(text)

    def test_validator_bounds(self):
        with self.assertRaises(ValueError):
            make_choice_validator(0)
        with self.assertRaises(ValueError):
            make_choice_validator(10)
        make_choice_validator(1)
        make_choice_validator(9)


class VotingRoundIntegrationTests(unittest.TestCase):
    def test_round_with_validator(self):
        rnd = VotingRound(validate=make_choice_validator(2))
        self.assertTrue(rnd.vote("u1", "1"))
        self.assertTrue(rnd.vote("u2", " 2 "))
        self.assertFalse(rnd.vote("u3", "3"))   # вне диапазона
        self.assertFalse(rnd.vote("u4", "gg"))  # мусор
        self.assertTrue(rnd.vote("u1", "2"))    # переголосование
        self.assertEqual(rnd.counts(), {"2": 2})
        self.assertEqual(len(rnd), 2)


if __name__ == "__main__":
    unittest.main()
