"""Tests for canonical vote keys per phase and key->choice mappings.
Viewer-facing validation (word -> key) lives in streamkit VoteWords —
see streamkit/tests/test_votewords.py. Combat has no votes (auto-battle):
the chat joins the squad with the fixed «бой» command (core.combat)."""

from __future__ import annotations

import unittest

from apps.mini_rpg.core.choices import (door_commands, door_keys,
                                        levelup_choice, levelup_commands,
                                        levelup_keys, shop_commands,
                                        shop_keys)
from apps.mini_rpg.core.hero import STATS


class DoorKeysTests(unittest.TestCase):
    def test_keys_1_to_3(self):
        self.assertEqual(door_keys(), ["1", "2", "3"])


class LevelupKeysTests(unittest.TestCase):
    def test_keys_1_to_5(self):
        self.assertEqual(levelup_keys(), ["1", "2", "3", "4", "5"])


class LevelupChoiceTests(unittest.TestCase):
    def test_digits_map_to_stats(self):
        for digit, stat in zip(("1", "2", "3", "4", "5"), STATS):
            self.assertEqual(levelup_choice(digit), stat)

    def test_out_of_range_raises(self):
        for digit in ("0", "6"):
            with self.assertRaises(ValueError):
                levelup_choice(digit)


class ShopKeysTests(unittest.TestCase):
    def test_zero_to_count(self):
        self.assertEqual(shop_keys(3), ["0", "1", "2", "3"])

    def test_empty_shop_has_only_exit(self):
        self.assertEqual(shop_keys(0), ["0"])

    def test_negative_count_raises(self):
        with self.assertRaises(ValueError):
            shop_keys(-1)


class ClassicCommandsTests(unittest.TestCase):
    """Fixed command table of the "classic" vote mode: every phase maps its
    canonical keys to meaningful short commands (docs/DESIGN.md)."""

    def test_door_commands(self):
        self.assertEqual(door_commands(),
                         {"1": "левая", "2": "средняя", "3": "правая"})

    def test_levelup_commands_match_stats(self):
        self.assertEqual(levelup_commands(),
                         {"1": "сила", "2": "ловкость", "3": "интеллект",
                          "4": "выносливость", "5": "удача"})

    def test_shop_commands(self):
        self.assertEqual(shop_commands(3),
                         {"0": "выход", "1": "1", "2": "2", "3": "3"})

    def test_shop_commands_empty_shop_exit_only(self):
        self.assertEqual(shop_commands(0), {"0": "выход"})

    def test_shop_commands_negative_count_raises(self):
        with self.assertRaises(ValueError):
            shop_commands(-1)

    def test_commands_cover_same_keys_as_key_functions(self):
        self.assertEqual(list(door_commands()), door_keys())
        self.assertEqual(list(levelup_commands()), levelup_keys())
        self.assertEqual(list(shop_commands(4)), shop_keys(4))


if __name__ == "__main__":
    unittest.main()
