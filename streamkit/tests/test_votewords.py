"""Tests for VoteWords: word aliases for voting rounds (assign, validator,
cooldown via injected clock, pool shortage, TOML pool loading)."""

from __future__ import annotations

import random
import tempfile
import unittest
from pathlib import Path

from streamkit import VoteWords
from streamkit.votewords import DEFAULT_POOL_PATH


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


POOL = ("меч", "волк", "гора", "река", "дуб", "лес")


def make_words(words=POOL, cooldown=60.0, clock=None, seed=1) -> VoteWords:
    return VoteWords(words, rng=random.Random(seed), cooldown=cooldown,
                     clock=clock or FakeClock())


class AssignTests(unittest.TestCase):
    def test_words_unique_and_mapped_to_all_keys(self):
        vw = make_words()
        mapping = vw.assign(["1", "2", "3"])
        self.assertEqual(sorted(mapping.values()), ["1", "2", "3"])
        self.assertEqual(len(mapping), 3)  # слова не повторяются в раунде
        for word in mapping:
            self.assertIn(word, POOL)

    def test_more_keys_than_words_raises(self):
        vw = make_words(words=("меч", "волк"))
        with self.assertRaises(ValueError):
            vw.assign(["1", "2", "3"])

    def test_duplicate_pool_words_rejected(self):
        with self.assertRaises(ValueError):
            VoteWords(["меч", "меч"])

    def test_empty_pool_rejected(self):
        with self.assertRaises(ValueError):
            VoteWords([])


class CooldownTests(unittest.TestCase):
    def test_recent_words_not_reissued_within_cooldown(self):
        clock = FakeClock()
        vw = make_words(words=("меч", "волк", "гора", "река"), clock=clock)
        first = set(vw.assign(["1", "2"]))
        clock.now += 10  # в пределах cooldown
        second = set(vw.assign(["1", "2"]))
        self.assertFalse(first & second)  # только свободные слова

    def test_words_reusable_after_cooldown(self):
        clock = FakeClock()
        vw = make_words(words=("меч", "волк", "гора", "река"), clock=clock)
        first = set(vw.assign(["1", "2"]))
        second = set(vw.assign(["1", "2"]))  # остаток пула
        clock.now += 61  # cooldown истёк — все слова снова свободны
        third = set(vw.assign(["1", "2"]))
        self.assertTrue(third & first)  # повтор разрешён
        self.assertEqual(len(third), 2)

    def test_shortage_ignores_cooldown_but_keeps_uniqueness(self):
        clock = FakeClock()
        vw = make_words(words=("меч", "волк", "гора"), clock=clock)
        vw.assign(["1", "2", "3"])  # весь пул выдан
        mapping = vw.assign(["1", "2", "3"])  # свободных нет — всё равно ок
        self.assertEqual(len(mapping), 3)
        self.assertEqual(sorted(mapping.values()), ["1", "2", "3"])


class ValidatorTests(unittest.TestCase):
    def setUp(self):
        self.vw = make_words()
        self.mapping = self.vw.assign(["1", "2", "3"])
        self.validate = self.vw.validator(self.mapping)

    def test_word_maps_to_key(self):
        for word, key in self.mapping.items():
            self.assertEqual(self.validate(word), key)

    def test_case_and_whitespace_insensitive(self):
        word, key = next(iter(self.mapping.items()))
        self.assertEqual(self.validate(f"  {word.upper()} \n"), key)

    def test_rejects_digits_garbage_and_foreign_words(self):
        for text in ("1", "2", "hello", "", "слово"):
            with self.assertRaises(ValueError):
                self.validate(text)
        # слово из пула, но не этого раунда — тоже мимо
        foreign = next(w for w in POOL if w not in self.mapping)
        with self.assertRaises(ValueError):
            self.validate(foreign)


class FromFileTests(unittest.TestCase):
    def test_default_pool_loads(self):
        vw = VoteWords.from_file(rng=random.Random(1))
        self.assertGreaterEqual(len(vw.words), 150)
        for w in vw.words:
            self.assertTrue(3 <= len(w) <= 7, w)
            self.assertNotIn("ё", w)
            self.assertTrue(w.isalpha(), w)
        mapping = vw.assign(["1", "2", "3"])
        self.assertEqual(len(mapping), 3)

    def test_custom_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pool.toml"
            path.write_text('words = ["меч", "волк"]\n', encoding="utf-8")
            vw = VoteWords.from_file(path, rng=random.Random(1))
            self.assertEqual(vw.words, ("меч", "волк"))

    def test_broken_file_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pool.toml"
            path.write_text("words = [\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                VoteWords.from_file(path)

    def test_missing_file_raises(self):
        with self.assertRaises(ValueError):
            VoteWords.from_file("no_such_pool.toml")

    def test_default_pool_path_exists(self):
        self.assertTrue(DEFAULT_POOL_PATH.is_file())


if __name__ == "__main__":
    unittest.main()
