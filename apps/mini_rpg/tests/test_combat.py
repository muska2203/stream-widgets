"""Tests for combat: blocks, armor, ranged uses, scaling, outcomes."""

from __future__ import annotations

import random
import unittest

from apps.mini_rpg.core import DIRECTIONS, Combat, Hero, Item, Mob, new_hero, scale_mob

SEED = 20260930


def mob(**kwargs) -> Mob:
    fields = dict(name="Гоблин", icon="", hp=20, damage_min=3, damage_max=3,
                  xp=8, gold=5)
    fields.update(kwargs)
    return Mob(**fields)


def item(slot: str, **kwargs) -> Item:
    fields = dict(name="Тест", icon="", slot=slot, damage_min=None,
                  damage_max=None, uses=None, armor=None, price=0)
    fields.update(kwargs)
    return Item(**fields)


def peek_choice(rng: random.Random, seq) -> str:
    """What rng.choice(seq) will return next, without consuming it."""
    state = rng.getstate()
    value = rng.choice(seq)
    rng.setstate(state)
    return value


def other_direction(direction: str) -> str:
    return next(d for d in DIRECTIONS if d != direction)


def make_combat(hero: Hero | None = None, m: Mob | None = None,
                seed: int = SEED) -> Combat:
    hero = hero or new_hero(20)
    return Combat(hero, m or mob(), random.Random(seed))


class ScalingTests(unittest.TestCase):
    def test_level_one_is_unscaled(self):
        scaled = scale_mob(mob(), hero_level=1)
        self.assertEqual((scaled.hp, scaled.damage_min, scaled.damage_max,
                          scaled.xp, scaled.gold), (20, 3, 3, 8, 5))

    def test_level_two_scales_by_15_percent(self):
        scaled = scale_mob(mob(), hero_level=2)
        self.assertEqual((scaled.hp, scaled.damage_min, scaled.damage_max,
                          scaled.xp, scaled.gold), (23, 3, 3, 9, 6))

    def test_original_mob_is_not_mutated(self):
        original = mob()
        make_combat(m=original)
        self.assertEqual((original.hp, original.xp), (20, 8))


class HeroTurnTests(unittest.TestCase):
    def test_unblocked_hit_deals_weapon_plus_stat(self):
        hero = new_hero(20)
        hero.equip(item("melee", damage_min=2, damage_max=2))
        hero.strength = 1
        combat = make_combat(hero)
        block = peek_choice(combat.rng, DIRECTIONS)
        result = combat.hero_turn("melee", other_direction(block))
        self.assertFalse(result.blocked)
        self.assertEqual(result.damage, 3)
        self.assertEqual(combat.mob_hp, 17)
        self.assertEqual((result.actor, result.weapon, result.target_hp),
                         ("hero", "melee", 17))

    def test_block_absorbs_all_damage(self):
        combat = make_combat()
        block = peek_choice(combat.rng, DIRECTIONS)
        result = combat.hero_turn("melee", block)
        self.assertTrue(result.blocked)
        self.assertEqual(result.damage, 0)
        self.assertEqual(combat.mob_hp, combat.mob.hp)

    def test_crit_doubles_damage(self):
        hero = new_hero(20)
        hero.equip(item("melee", damage_min=2, damage_max=2))
        hero.strength = 1
        hero.luck = 100
        combat = make_combat(hero)
        block = peek_choice(combat.rng, DIRECTIONS)
        result = combat.hero_turn("melee", other_direction(block))
        self.assertTrue(result.crit)
        self.assertEqual(result.damage, 6)

    def test_ranged_use_spent_even_on_block(self):
        hero = new_hero(20)
        hero.equip(item("ranged", damage_min=5, damage_max=5, uses=1))
        combat = make_combat(hero)
        block = peek_choice(combat.rng, DIRECTIONS)
        result = combat.hero_turn("ranged", block)
        self.assertTrue(result.blocked)
        self.assertEqual(result.damage, 0)
        self.assertIsNone(hero.ranged)  # последний use потрачен — сломалось

    def test_ranged_use_spent_on_hit(self):
        hero = new_hero(20)
        hero.equip(item("ranged", damage_min=5, damage_max=5, uses=2))
        combat = make_combat(hero)
        block = peek_choice(combat.rng, DIRECTIONS)
        combat.hero_turn("ranged", other_direction(block))
        self.assertEqual(hero.ranged.uses, 1)

    def test_empty_or_unknown_weapon_raises(self):
        combat = make_combat()
        with self.assertRaises(ValueError):
            combat.hero_turn("ranged", "head")
        with self.assertRaises(ValueError):
            combat.hero_turn("armor", "head")
        with self.assertRaises(ValueError):
            combat.hero_turn("melee", "back")

    def test_hero_skip(self):
        combat = make_combat()
        result = combat.hero_skip()
        self.assertEqual((result.actor, result.weapon, result.direction,
                          result.damage, result.blocked),
                         ("hero", None, None, 0, False))
        self.assertEqual(combat.mob_hp, combat.mob.hp)
        self.assertFalse(combat.finished)


class MobTurnTests(unittest.TestCase):
    def test_defense_absorbs_all_damage(self):
        hero = new_hero(20)
        combat = make_combat(hero)
        attack = peek_choice(combat.rng, DIRECTIONS)
        result = combat.mob_turn(attack)
        self.assertTrue(result.blocked)
        self.assertEqual(result.damage, 0)
        self.assertEqual(hero.hp, 20)

    def test_undefended_hit_deals_mob_damage(self):
        hero = new_hero(20)
        combat = make_combat(hero)
        attack = peek_choice(combat.rng, DIRECTIONS)
        result = combat.mob_turn(other_direction(attack))
        self.assertFalse(result.blocked)
        self.assertEqual(result.damage, 3)
        self.assertEqual(result.direction, attack)
        self.assertEqual((hero.hp, result.target_hp), (17, 17))

    def test_armor_reduces_damage(self):
        hero = new_hero(20)
        hero.equip(item("armor", armor=2))
        combat = make_combat(hero)
        attack = peek_choice(combat.rng, DIRECTIONS)
        result = combat.mob_turn(other_direction(attack))
        self.assertEqual(result.damage, 1)

    def test_armor_never_below_zero(self):
        hero = new_hero(20)
        hero.equip(item("armor", armor=10))
        combat = make_combat(hero)
        attack = peek_choice(combat.rng, DIRECTIONS)
        result = combat.mob_turn(other_direction(attack))
        self.assertEqual(result.damage, 0)
        self.assertEqual(hero.hp, 20)

    def test_skipped_defense_never_blocks(self):
        hero = new_hero(20)
        combat = make_combat(hero)
        result = combat.mob_turn(None)
        self.assertFalse(result.blocked)
        self.assertEqual(result.damage, 3)

    def test_unknown_defense_raises(self):
        combat = make_combat()
        with self.assertRaises(ValueError):
            combat.mob_turn("back")


class OutcomeTests(unittest.TestCase):
    def test_victory_gives_scaled_rewards(self):
        hero = new_hero(20)
        hero.level = 2  # награды ×1.15: 8→9, 5→6
        hero.equip(item("melee", damage_min=5, damage_max=5))
        combat = make_combat(hero, mob(hp=4, damage_min=0, damage_max=0))
        block = peek_choice(combat.rng, DIRECTIONS)
        combat.hero_turn("melee", other_direction(block))
        self.assertTrue(combat.finished)
        self.assertTrue(combat.hero_won)
        self.assertEqual(combat.rewards, (9, 6))

    def test_hero_death_is_defeat(self):
        hero = new_hero(20)
        hero.hp = 2
        combat = make_combat(hero, mob(damage_min=5, damage_max=5))
        attack = peek_choice(combat.rng, DIRECTIONS)
        combat.mob_turn(other_direction(attack))
        self.assertTrue(combat.finished)
        self.assertFalse(combat.hero_won)
        self.assertIsNone(combat.rewards)
        self.assertEqual(hero.hp, 0)
        self.assertFalse(hero.alive)

    def test_rewards_none_while_fighting(self):
        combat = make_combat()
        self.assertIsNone(combat.rewards)

    def test_turns_after_finish_raise(self):
        hero = new_hero(20)
        hero.hp = 1
        combat = make_combat(hero, mob(damage_min=5, damage_max=5))
        combat.mob_turn(None)
        with self.assertRaises(RuntimeError):
            combat.hero_turn("melee", "head")
        with self.assertRaises(RuntimeError):
            combat.mob_turn(None)
        with self.assertRaises(RuntimeError):
            combat.hero_skip()


if __name__ == "__main__":
    unittest.main()
