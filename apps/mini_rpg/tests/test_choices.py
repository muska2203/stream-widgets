"""Tests for chat command validators and digit->choice mappings."""

from __future__ import annotations

import unittest

from apps.mini_rpg.core.choices import (attack_choice, defense_choice,
                                        levelup_choice,
                                        make_attack_validator,
                                        make_defense_validator,
                                        make_door_validator,
                                        make_levelup_validator,
                                        make_shop_validator)
from apps.mini_rpg.core.combat import DIRECTIONS
from apps.mini_rpg.core.hero import STATS


class DoorValidatorTests(unittest.TestCase):
    def setUp(self):
        self.validate = make_door_validator()

    def test_accepts_1_to_3(self):
        for digit in ("1", "2", "3"):
            self.assertEqual(self.validate(digit), digit)

    def test_rejects_everything_else(self):
        for text in ("0", "4", "9", "", "abc", "12", "1 2"):
            with self.assertRaises(ValueError):
                self.validate(text)

    def test_strips_whitespace(self):
        self.assertEqual(self.validate("  2 \n"), "2")


class AttackValidatorTests(unittest.TestCase):
    def test_with_ranged_accepts_1_to_6(self):
        validate = make_attack_validator(has_ranged=True)
        for digit in ("1", "2", "3", "4", "5", "6"):
            self.assertEqual(validate(digit), digit)
        for text in ("0", "7", "x"):
            with self.assertRaises(ValueError):
                validate(text)

    def test_without_ranged_accepts_only_1_to_3(self):
        validate = make_attack_validator(has_ranged=False)
        for digit in ("1", "2", "3"):
            self.assertEqual(validate(digit), digit)
        for text in ("4", "5", "6"):
            with self.assertRaises(ValueError):
                validate(text)


class AttackChoiceTests(unittest.TestCase):
    def test_melee_digits(self):
        for digit, direction in zip(("1", "2", "3"), DIRECTIONS):
            self.assertEqual(attack_choice(digit), ("melee", direction))

    def test_ranged_digits(self):
        for digit, direction in zip(("4", "5", "6"), DIRECTIONS):
            self.assertEqual(attack_choice(digit), ("ranged", direction))

    def test_out_of_range_raises(self):
        for digit in ("0", "7"):
            with self.assertRaises(ValueError):
                attack_choice(digit)


class DefenseValidatorTests(unittest.TestCase):
    def test_accepts_1_to_3(self):
        validate = make_defense_validator()
        for digit in ("1", "2", "3"):
            self.assertEqual(validate(digit), digit)
        for text in ("0", "4", ""):
            with self.assertRaises(ValueError):
                validate(text)


class DefenseChoiceTests(unittest.TestCase):
    def test_digits_map_to_directions(self):
        for digit, direction in zip(("1", "2", "3"), DIRECTIONS):
            self.assertEqual(defense_choice(digit), direction)

    def test_out_of_range_raises(self):
        with self.assertRaises(ValueError):
            defense_choice("4")


class LevelupValidatorTests(unittest.TestCase):
    def test_accepts_1_to_5(self):
        validate = make_levelup_validator()
        for digit in ("1", "2", "3", "4", "5"):
            self.assertEqual(validate(digit), digit)
        for text in ("0", "6", "стата"):
            with self.assertRaises(ValueError):
                validate(text)


class LevelupChoiceTests(unittest.TestCase):
    def test_digits_map_to_stats(self):
        for digit, stat in zip(("1", "2", "3", "4", "5"), STATS):
            self.assertEqual(levelup_choice(digit), stat)

    def test_out_of_range_raises(self):
        for digit in ("0", "6"):
            with self.assertRaises(ValueError):
                levelup_choice(digit)


class ShopValidatorTests(unittest.TestCase):
    def test_accepts_zero_to_count(self):
        validate = make_shop_validator(3)
        for digit in ("0", "1", "2", "3"):
            self.assertEqual(validate(digit), digit)
        for text in ("4", "9", "-1"):
            with self.assertRaises(ValueError):
                validate(text)

    def test_empty_shop_accepts_only_exit(self):
        validate = make_shop_validator(0)
        self.assertEqual(validate("0"), "0")
        with self.assertRaises(ValueError):
            validate("1")

    def test_negative_count_raises(self):
        with self.assertRaises(ValueError):
            make_shop_validator(-1)


if __name__ == "__main__":
    unittest.main()
