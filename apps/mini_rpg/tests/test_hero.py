"""Tests for the hero model: formulas, equipment, XP/levels, ranged uses."""

from __future__ import annotations

import random
import unittest

from apps.mini_rpg.core import Hero, Item, new_hero

SEED = 20260930


def item(slot: str, **kwargs) -> Item:
    fields = dict(name="Тест", icon="", slot=slot, damage_min=None,
                  damage_max=None, uses=None, armor=None, price=0)
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
        self.assertIsNone(hero.ranged)
        self.assertIsNone(hero.armor)


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

    def test_melee_damage_adds_strength(self):
        hero = new_hero(20)
        hero.equip(item("melee", damage_min=2, damage_max=2))
        hero.strength = 3
        damage, crit = hero.roll_damage("melee", random.Random(SEED))
        self.assertEqual((damage, crit), (5, False))

    def test_ranged_damage_adds_agility(self):
        hero = new_hero(20)
        hero.equip(item("ranged", damage_min=4, damage_max=4, uses=3))
        hero.agility = 2
        damage, crit = hero.roll_damage("ranged", random.Random(SEED))
        self.assertEqual((damage, crit), (6, False))

    def test_roll_within_weapon_range(self):
        hero = new_hero(20)  # кулаки 1–2, без статов
        rng = random.Random(SEED)
        rolls = {hero.roll_damage("melee", rng)[0] for _ in range(50)}
        self.assertEqual(rolls, {1, 2})

    def test_crit_doubles_total_damage(self):
        hero = new_hero(20)
        hero.equip(item("melee", damage_min=2, damage_max=2))
        hero.strength = 3
        hero.luck = 100  # шанс 200% — крит гарантирован
        damage, crit = hero.roll_damage("melee", random.Random(SEED))
        self.assertEqual((damage, crit), (10, True))

    def test_roll_damage_empty_slot_raises(self):
        hero = new_hero(20)
        with self.assertRaises(ValueError):
            hero.roll_damage("ranged", random.Random(SEED))
        with self.assertRaises(ValueError):
            hero.roll_damage("armor", random.Random(SEED))


class EquipTests(unittest.TestCase):
    def test_equip_replaces_old_item(self):
        hero = new_hero(20)
        old = hero.melee
        hero.equip(item("melee", name="Меч", damage_min=2, damage_max=4))
        self.assertEqual(hero.melee.name, "Меч")
        self.assertIsNot(hero.melee, old)

    def test_equip_fills_empty_slots(self):
        hero = new_hero(20)
        hero.equip(item("ranged", damage_min=3, damage_max=7, uses=5))
        hero.equip(item("armor", armor=2))
        self.assertEqual(hero.ranged.uses, 5)
        self.assertEqual(hero.armor_value, 2)

    def test_armor_value_without_armor_is_zero(self):
        self.assertEqual(new_hero(20).armor_value, 0)

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


class RangedUseTests(unittest.TestCase):
    def test_use_ranged_spends_use(self):
        hero = new_hero(20)
        hero.equip(item("ranged", damage_min=3, damage_max=7, uses=2))
        hero.use_ranged()
        self.assertEqual(hero.ranged.uses, 1)

    def test_weapon_breaks_at_zero_uses(self):
        hero = new_hero(20)
        hero.equip(item("ranged", damage_min=3, damage_max=7, uses=1))
        hero.use_ranged()
        self.assertIsNone(hero.ranged)

    def test_use_ranged_without_weapon_raises(self):
        hero = new_hero(20)
        with self.assertRaises(ValueError):
            hero.use_ranged()


if __name__ == "__main__":
    unittest.main()
