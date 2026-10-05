"""Tests for combat: mob scaling, per-unit cooldown auto-battle (squad
calibration, crit, armor, no dodge), outcomes."""

from __future__ import annotations

import random
import unittest

from apps.mini_rpg.core import (CHATTER_EMOJI, Combat, Hero, Item, Mob,
                                new_hero, scale_mob)

SEED = 20260930


def mob(**kwargs) -> Mob:
    fields = dict(name="Гоблин", icon="", hp=20, damage_min=3, damage_max=3,
                  xp=8, gold=5)
    fields.update(kwargs)
    return Mob(**fields)


def item(slot: str, **kwargs) -> Item:
    fields = dict(name="Тест", icon="", slot=slot, damage_min=None,
                  damage_max=None, armor=None, price=0)
    fields.update(kwargs)
    return Item(**fields)


def make_combat(hero: Hero | None = None, m: Mob | None = None,
                seed: int = SEED, **kwargs) -> Combat:
    hero = hero or new_hero(20)
    return Combat(hero, m or mob(), random.Random(seed), **kwargs)


def quiet_mob(**kwargs) -> Mob:
    """Моб, который не мешает тесту: не бьёт и атакует очень редко."""
    fields = dict(hp=1000, damage_min=0, damage_max=0, cooldown=99.0)
    fields.update(kwargs)
    return mob(**fields)


class ScalingTests(unittest.TestCase):
    def test_level_one_is_unscaled(self):
        scaled = scale_mob(mob(), hero_level=1)
        self.assertEqual((scaled.hp, scaled.damage_min, scaled.damage_max,
                          scaled.xp, scaled.gold), (20, 3, 3, 8, 5))

    def test_level_two_scales_by_15_percent(self):
        scaled = scale_mob(mob(), hero_level=2)
        self.assertEqual((scaled.hp, scaled.damage_min, scaled.damage_max,
                          scaled.xp, scaled.gold), (23, 3, 3, 9, 6))

    def test_scaling_scales_both_damage_bounds_half_up(self):
        scaled = scale_mob(mob(hp=10, damage_min=10, damage_max=10, xp=10,
                               gold=10), hero_level=2)
        self.assertEqual((scaled.hp, scaled.damage_min, scaled.damage_max,
                          scaled.xp, scaled.gold), (12, 12, 12, 12, 12))
        # 10 × 1.15 = 11.5 → 12

    def test_scaling_preserves_cooldown(self):
        scaled = scale_mob(mob(cooldown=3.5), hero_level=3)
        self.assertEqual(scaled.cooldown, 3.5)

    def test_original_mob_is_not_mutated(self):
        original = mob()
        make_combat(m=original)
        self.assertEqual((original.hp, original.damage_min, original.xp),
                         (20, 3, 8))


class HeroCooldownTests(unittest.TestCase):
    def test_base_cooldown_without_agility(self):
        combat = make_combat(hero_cooldown=5.0)
        self.assertEqual(combat.hero_cd, 5.0)
        self.assertEqual(combat.hero_cd_left, 5.0)  # полный КД от начала боя

    def test_agility_reduces_cooldown(self):
        hero = new_hero(20)
        hero.agility = 4
        combat = make_combat(hero, hero_cooldown=5.0, agility_cd_reduction=0.5)
        self.assertEqual(combat.hero_cd, 3.0)

    def test_cooldown_floored_at_min(self):
        hero = new_hero(20)
        hero.agility = 100
        combat = make_combat(hero, hero_cooldown=5.0, agility_cd_reduction=0.5,
                             min_cooldown=1.0)
        self.assertEqual(combat.hero_cd, 1.0)


class HeroHitTests(unittest.TestCase):
    def test_hero_hits_when_cooldown_elapses(self):
        hero = new_hero(20)
        hero.equip(item("melee", damage_min=2, damage_max=6))
        combat = make_combat(hero, quiet_mob(), hero_cooldown=2.0)
        for _ in range(5):
            hp_before = combat.mob_hp
            events = combat.update(2.0)
            self.assertEqual(len(events), 1)
            event = events[0]
            self.assertEqual((event.attacker, event.target), ("hero", "mob"))
            self.assertGreaterEqual(event.damage, 2)
            self.assertLessEqual(event.damage, 6)
            self.assertEqual(event.target_hp, hp_before - event.damage)
            self.assertFalse(event.crit)

    def test_no_attack_before_cooldown(self):
        combat = make_combat(m=quiet_mob(), hero_cooldown=2.0)
        self.assertEqual(combat.update(1.5), [])
        self.assertEqual(len(combat.update(0.5)), 1)  # КД дошёл ровно до 0

    def test_cooldown_remainder_kept(self):
        combat = make_combat(m=quiet_mob(), hero_cooldown=1.5)
        combat.update(2.0)  # удар, остаток −0.5 + 1.5
        self.assertAlmostEqual(combat.hero_cd_left, 1.0)

    def test_big_frame_resolves_several_attacks(self):
        combat = make_combat(m=quiet_mob(), hero_cooldown=1.0)
        events = combat.update(3.5)  # КД 1.0 → 3 удара (остаток 0.5)
        self.assertEqual([e.attacker for e in events],
                         ["hero", "hero", "hero"])
        self.assertAlmostEqual(combat.hero_cd_left, 0.5)

    def test_degenerate_range_adds_strength(self):
        hero = new_hero(20)
        hero.equip(item("melee", damage_min=2, damage_max=2))
        hero.strength = 1
        combat = make_combat(hero, quiet_mob(hp=20), hero_cooldown=1.0)
        events = combat.update(1.0)
        self.assertEqual(events[0].damage, 3)
        self.assertEqual(events[0].target_hp, 17)
        self.assertEqual(combat.mob_hp, 17)

    def test_crit_doubles_damage(self):
        hero = new_hero(20)
        hero.equip(item("melee", damage_min=2, damage_max=2))
        hero.strength = 1
        hero.luck = 100  # шанс 200% — крит гарантирован
        combat = make_combat(hero, quiet_mob(), hero_cooldown=1.0)
        event = combat.update(1.0)[0]
        self.assertTrue(event.crit)
        self.assertEqual(event.damage, 6)


class SquadTests(unittest.TestCase):
    def test_join_creates_calibrated_unit(self):
        combat = make_combat(m=quiet_mob())
        self.assertTrue(combat.join("Viewer"))
        unit = combat.squad[0]
        self.assertEqual(unit.nick, "Viewer")
        self.assertIn(unit.emoji, CHATTER_EMOJI)
        self.assertGreaterEqual(unit.damage_min, 1)  # минимальный урон
        self.assertGreaterEqual(unit.damage_max, unit.damage_min)
        self.assertGreaterEqual(unit.cooldown, combat.chatter_cd_min)
        self.assertLessEqual(unit.cooldown, combat.chatter_cd_max)
        self.assertGreaterEqual(unit.cd_left, 0)
        self.assertLessEqual(unit.cd_left, unit.cooldown)
        self.assertTrue(unit.active)

    def test_emoji_deterministic_by_nick(self):
        c1 = make_combat(m=quiet_mob(), seed=1)
        c2 = make_combat(m=quiet_mob(), seed=2)
        c1.join("Viewer")
        c2.join("Viewer")
        self.assertEqual(c1.squad[0].emoji, c2.squad[0].emoji)

    def test_join_once_per_combat(self):
        combat = make_combat(m=quiet_mob())
        self.assertTrue(combat.join("viewer"))
        self.assertFalse(combat.join("viewer"))
        self.assertEqual([u.nick for u in combat.squad], ["viewer"])

    def test_join_after_finish_rejected(self):
        hero = new_hero(20)
        hero.equip(item("melee", damage_min=5, damage_max=5))
        combat = make_combat(hero, mob(hp=1, damage_min=0, damage_max=0),
                             hero_cooldown=1.0)
        combat.update(1.0)
        self.assertTrue(combat.finished)
        self.assertFalse(combat.join("late"))

    def test_calibration_matches_five_percent_of_hero_dps(self):
        hero = new_hero(20)
        hero.equip(item("melee", damage_min=40, damage_max=40))
        combat = make_combat(hero, quiet_mob(), hero_cooldown=5.0,
                             chatter_cd_min=3.0, chatter_cd_max=8.0,
                             chat_pct=5, seed=SEED)
        # hero DPS = 40 / 5 = 8 → цель чаттера 0.4 DPS
        for i in range(300):
            combat.join(f"user{i}")
        dps = [(u.damage_min + u.damage_max) / 2 / u.cooldown
               for u in combat.squad]
        self.assertTrue(all(u.damage_min >= 1 for u in combat.squad))
        self.assertAlmostEqual(sum(dps) / len(dps), 0.4, delta=0.04)

    def test_attacker_cap(self):
        combat = make_combat(m=quiet_mob(), chat_pct=5, chat_cap=100)
        for i in range(25):  # кап атакующих = 100 // 5 = 20
            combat.join(f"user{i}")
        self.assertEqual([u.active for u in combat.squad],
                         [True] * 20 + [False] * 5)

    def test_inactive_units_do_not_attack(self):
        combat = make_combat(m=quiet_mob(), chat_pct=5, chat_cap=5)  # кап = 1
        combat.join("active")
        combat.join("bench")
        bench = combat.squad[1]
        cd_before = bench.cd_left
        events = combat.update(20.0)  # хватит на несколько атак активного
        self.assertEqual(bench.cd_left, cd_before)  # КД не тикает
        self.assertNotIn("bench", [e.attacker for e in events])
        self.assertIn("active", [e.attacker for e in events])

    def test_chatter_hits_without_crit(self):
        combat = make_combat(m=quiet_mob(), hero_cooldown=99.0,
                             chatter_cd_min=2.0, chatter_cd_max=2.0)
        combat.join("Viewer")
        unit = combat.squad[0]
        unit.cd_left = 1.0
        hp_before = combat.mob_hp
        events = combat.update(1.0)
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual((event.attacker, event.target), ("Viewer", "mob"))
        self.assertFalse(event.crit)
        self.assertGreaterEqual(event.damage, unit.damage_min)
        self.assertLessEqual(event.damage, unit.damage_max)
        self.assertEqual(event.target_hp, hp_before - event.damage)

    def test_frame_order_hero_squad_mob(self):
        combat = make_combat(m=mob(hp=1000, damage_min=0, damage_max=0,
                                   cooldown=1.0),
                             hero_cooldown=1.0, chatter_cd_min=2.0,
                             chatter_cd_max=2.0)
        combat.join("Viewer")
        combat.squad[0].cd_left = 0.5
        events = combat.update(1.0)
        self.assertEqual([e.attacker for e in events],
                         ["hero", "Viewer", "mob"])

    def test_event_seq_is_monotonic(self):
        combat = make_combat(m=quiet_mob(), hero_cooldown=1.0)
        seqs = [e.seq for e in combat.update(1.0) + combat.update(1.0)]
        self.assertEqual(seqs, [1, 2])


class MobHitTests(unittest.TestCase):
    def make_quiet_hero_combat(self, hero: Hero, m: Mob) -> Combat:
        # герой не атакует (КД 99), моб бьёт раз в секунду
        return make_combat(hero, m, hero_cooldown=99.0)

    def test_mob_damage_within_range(self):
        hero = new_hero(1000)  # жить хватит на весь тест
        combat = self.make_quiet_hero_combat(
            hero, mob(hp=1000, damage_min=2, damage_max=5, cooldown=1.0))
        for _ in range(5):
            events = combat.update(1.0)
            self.assertEqual(len(events), 1)
            event = events[0]
            self.assertEqual((event.attacker, event.target), ("mob", "hero"))
            self.assertGreaterEqual(event.damage, 2)
            self.assertLessEqual(event.damage, 5)
            self.assertEqual(event.armor_absorbed, 0)  # брони нет
            self.assertEqual(event.target_hp, hero.hp)

    def test_armor_absorbs_flat(self):
        hero = new_hero(20)
        hero.equip(item("armor", armor=2))
        combat = self.make_quiet_hero_combat(hero, mob(cooldown=1.0))  # 3–3
        event = combat.update(1.0)[0]
        self.assertEqual(event.armor_absorbed, 2)
        self.assertEqual(event.damage, 1)
        self.assertEqual(hero.hp, 19)

    def test_armor_never_below_zero_damage(self):
        hero = new_hero(20)
        hero.equip(item("armor", armor=5))
        combat = self.make_quiet_hero_combat(hero, mob(cooldown=1.0))  # 3–3
        event = combat.update(1.0)[0]
        self.assertEqual(event.armor_absorbed, 3)  # не больше броска
        self.assertEqual(event.damage, 0)
        self.assertEqual(hero.hp, 20)

    def test_no_dodge_agility_does_not_protect(self):
        hero = new_hero(20)
        hero.agility = 50  # раньше — 100% уклонение; теперь только КД героя
        combat = self.make_quiet_hero_combat(hero, mob(cooldown=1.0))
        event = combat.update(1.0)[0]
        self.assertEqual(event.damage, 3)
        self.assertEqual(hero.hp, 17)

    def test_dead_mob_does_not_hit_back(self):
        hero = new_hero(20)
        hero.equip(item("melee", damage_min=5, damage_max=5))
        combat = make_combat(hero, mob(hp=4, damage_min=3, damage_max=3,
                                       cooldown=1.0),
                             hero_cooldown=1.0)
        events = combat.update(1.0)
        self.assertEqual([e.attacker for e in events], ["hero"])  # моб не ответил
        self.assertEqual(combat.mob_hp, 0)
        self.assertEqual(hero.hp, 20)


class OutcomeTests(unittest.TestCase):
    def test_victory_gives_scaled_rewards(self):
        hero = new_hero(20)
        hero.level = 2  # награды ×1.15: 8→9, 5→6
        hero.equip(item("melee", damage_min=5, damage_max=5))
        combat = make_combat(hero, mob(hp=4, damage_min=0, damage_max=0),
                             hero_cooldown=1.0)
        combat.update(1.0)
        self.assertTrue(combat.finished)
        self.assertTrue(combat.hero_won)
        self.assertEqual(combat.rewards, (9, 6))

    def test_hero_death_is_defeat(self):
        hero = new_hero(20)
        hero.hp = 2
        combat = make_combat(hero, mob(damage_min=5, damage_max=5,
                                       cooldown=1.0),
                             hero_cooldown=99.0)
        combat.update(1.0)
        self.assertTrue(combat.finished)
        self.assertFalse(combat.hero_won)
        self.assertIsNone(combat.rewards)
        self.assertEqual(hero.hp, 0)
        self.assertFalse(hero.alive)

    def test_rewards_none_while_fighting(self):
        combat = make_combat()
        self.assertIsNone(combat.rewards)

    def test_update_after_finish_raises(self):
        hero = new_hero(20)
        hero.hp = 1
        combat = make_combat(hero, mob(damage_min=5, damage_max=5,
                                       cooldown=1.0),
                             hero_cooldown=99.0)
        combat.update(1.0)
        with self.assertRaises(RuntimeError):
            combat.update(1.0)


if __name__ == "__main__":
    unittest.main()
