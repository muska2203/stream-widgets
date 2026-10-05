"""Tests for the hero model: formulas, equipment, XP/levels, melee damage
range, auto-battle strike (crit), armor and attack cooldown."""

from __future__ import annotations

import random
import unittest

from apps.mini_rpg.core import Hero, Item, new_hero

SEED = 20260930


def item(slot: str, **kwargs) -> Item:
    fields = dict(name="Тест", icon="", slot=slot, damage_min=None,
                  damage_max=None, armor=None, price=0)
    fields.update(kwargs)
    return Item(**fields)


class NewHeroTests(unittest.TestCase):
    def test_starter_kit(self):
        hero = new_hero(base_hp=20)
        self.assertEqual(hero.level, 1)
        self.assertEqual((hero.xp, hero.gold), (0, 0))
        self.assertEqual((hero.strength, hero.agility, hero.intellect,
                          hero.endurance, hero.luck), (0, 0, 0, 0, 0))
        self.assertEqual((hero.hp, hero.max_hp), (20, 20))
        self.assertEqual((hero.mana, hero.max_mana), (0, 0))
        self.assertEqual(hero.melee.name, "Кулаки")
        self.assertEqual((hero.melee.damage_min, hero.melee.damage_max), (1, 2))
        self.assertIsNone(hero.armor)

    def test_custom_starter_equips_copy(self):
        paws = item("melee", name="Лапы", damage_min=3, damage_max=5)
        plate = item("armor", name="Панцирь", armor=1)
        hero = new_hero(20, [paws, plate])
        self.assertEqual(hero.melee.name, "Лапы")
        self.assertIsNot(hero.melee, paws)  # копия — пул не шарится
        self.assertEqual(hero.damage_range(), (3, 5))
        self.assertEqual(hero.armor.name, "Панцирь")
        self.assertIsNot(hero.armor, plate)
        self.assertEqual(hero.armor_value, 1)


class FormulaTests(unittest.TestCase):
    def test_max_hp_scales_with_endurance(self):
        hero = new_hero(20)
        hero.endurance = 3
        self.assertEqual(hero.max_hp, 35)

    def test_max_mana_scales_with_intellect(self):
        hero = new_hero(20)
        hero.intellect = 4
        self.assertEqual(hero.max_mana, 20)

    def test_crit_chance_scales_with_luck(self):
        hero = new_hero(20)
        hero.luck = 5
        self.assertAlmostEqual(hero.crit_chance, 0.10)

    def test_attack_cooldown_reduced_by_agility(self):
        hero = new_hero(20)
        hero.agility = 5
        self.assertAlmostEqual(hero.attack_cooldown(5.0, 0.5, 1.0), 2.5)

    def test_attack_cooldown_floored(self):
        hero = new_hero(20)
        hero.agility = 100
        self.assertEqual(hero.attack_cooldown(5.0, 0.5, 1.0), 1.0)


class DamageRangeTests(unittest.TestCase):
    def test_melee_damage_adds_strength(self):
        hero = new_hero(20)
        hero.equip(item("melee", damage_min=2, damage_max=4))
        hero.strength = 3
        self.assertEqual(hero.damage_range(), (5, 7))

    def test_fists_range(self):
        self.assertEqual(new_hero(20).damage_range(), (1, 2))

    def test_empty_slot_raises(self):
        hero = Hero(base_hp=20)  # без стартового набора слот melee пуст
        with self.assertRaises(ValueError):
            hero.damage_range()


class ArmorTests(unittest.TestCase):
    def test_no_armor_is_zero(self):
        self.assertEqual(new_hero(20).armor_value, 0)

    def test_armor_value_from_item(self):
        hero = new_hero(20)
        hero.equip(item("armor", armor=3))
        self.assertEqual(hero.armor_value, 3)


class StrikeTests(unittest.TestCase):
    def test_damage_within_range(self):
        hero = new_hero(20)
        hero.equip(item("melee", damage_min=2, damage_max=6))
        rng = random.Random(SEED)
        for _ in range(20):
            damage, crit = hero.strike(rng)
            self.assertGreaterEqual(damage, 2)
            self.assertLessEqual(damage, 6)
            self.assertFalse(crit)

    def test_degenerate_range_exact(self):
        hero = new_hero(20)
        hero.equip(item("melee", damage_min=2, damage_max=2))
        hero.strength = 3
        damage, crit = hero.strike(random.Random(SEED))
        self.assertEqual((damage, crit), (5, False))

    def test_crit_doubles_total_damage(self):
        hero = new_hero(20)
        hero.equip(item("melee", damage_min=2, damage_max=2))
        hero.strength = 3
        hero.luck = 100  # шанс 200% — крит гарантирован
        damage, crit = hero.strike(random.Random(SEED))
        self.assertEqual((damage, crit), (10, True))

    def test_empty_slot_raises(self):
        hero = Hero(base_hp=20)
        with self.assertRaises(ValueError):
            hero.strike(random.Random(SEED))


class EquipTests(unittest.TestCase):
    def test_equip_replaces_old_item(self):
        hero = new_hero(20)
        old = hero.melee
        hero.equip(item("melee", name="Меч", damage_min=2, damage_max=4))
        self.assertEqual(hero.melee.name, "Меч")
        self.assertIsNot(hero.melee, old)

    def test_equip_fills_armor_slot(self):
        hero = new_hero(20)
        hero.equip(item("armor", name="Кольчуга", armor=2))
        self.assertEqual(hero.armor.name, "Кольчуга")
        self.assertEqual(hero.armor_value, 2)

    def test_equip_bad_slot_raises(self):
        hero = new_hero(20)
        with self.assertRaises(ValueError):
            hero.equip(item("wand"))


class XpTests(unittest.TestCase):
    def test_threshold_is_10_per_level(self):
        hero = new_hero(20)
        self.assertEqual(hero.xp_to_next, 10)
        hero.level = 3
        self.assertEqual(hero.xp_to_next, 30)

    def test_gain_xp_below_threshold(self):
        hero = new_hero(20)
        self.assertEqual(hero.gain_xp(7), 0)
        self.assertEqual((hero.level, hero.xp), (1, 7))

    def test_gain_xp_subtracts_threshold(self):
        hero = new_hero(20)
        self.assertEqual(hero.gain_xp(12), 1)
        self.assertEqual((hero.level, hero.xp), (2, 2))

    def test_multi_level_up_from_one_kill(self):
        hero = new_hero(20)
        self.assertEqual(hero.gain_xp(100), 4)
        self.assertEqual((hero.level, hero.xp), (5, 0))


class LevelUpTests(unittest.TestCase):
    def test_stat_grows_by_one(self):
        hero = new_hero(20)
        hero.level_up("luck")
        self.assertEqual(hero.luck, 1)

    def test_endurance_up_heals_current_hp(self):
        hero = new_hero(20)
        hero.hp = 10
        hero.level_up("endurance")
        self.assertEqual(hero.max_hp, 25)
        self.assertEqual(hero.hp, 15)

    def test_unknown_stat_raises(self):
        hero = new_hero(20)
        with self.assertRaises(ValueError):
            hero.level_up("charisma")


if __name__ == "__main__":
    unittest.main()
