"""Tests for the Game state machine: full runs driven through
handle_chat_message directly (no real chat) with seeded rng and a mob pool
in a temp directory."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from apps.mini_rpg.config import Config
from apps.mini_rpg.core import Item
from apps.mini_rpg.game import (ATTACK, COMBAT, COMBAT_END, DEFENSE, ERROR,
                                EVENT, GAME_OVER, LEVELUP, MOB, OUTCOME, Game)

SEED = 20260930
DT = 0.5

MOB_TOML = """\
name = "{name}"
hp = {hp}
damage_min = {damage_min}
damage_max = {damage_max}
xp = {xp}
gold = {gold}
"""


def write_mob(directory: Path, filename: str = "mob.toml", **fields) -> None:
    defaults = dict(name="Тестовый моб", hp=4, damage_min=0, damage_max=0,
                    xp=0, gold=0)
    defaults.update(fields)
    (directory / filename).write_text(MOB_TOML.format(**defaults),
                                      encoding="utf-8")


def mob_door_digit(game: Game) -> str:
    """Digit of the first mob door; re-rolls the doors if none came up
    (since этап 9 doors are mixed: mobs + shop + rest)."""
    for _ in range(50):
        for i, door in enumerate(game.doors):
            if door.kind == MOB:
                return str(i + 1)
        game.enter_event()
    raise AssertionError("на дверях не выпало моба")


class GameTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.mobs_dir = Path(self._tmp.name)
        self.items_dir = self.mobs_dir / "items"  # нет каталога — пустой пул
        # один префикс — детерминированные боевые клички в тестах
        self.prefixes_path = self.mobs_dir / "cfg" / "prefixes.toml"
        self.prefixes_path.parent.mkdir()
        self.prefixes_path.write_text('prefixes = ["Тестовый"]\n',
                                      encoding="utf-8")

    def make_game(self, **cfg_over) -> Game:
        fields = dict(seed=SEED, event_duration=5.0, combat_duration=5.0,
                      combat_outcome_pause=1.0, levelup_duration=5.0,
                      combat_end_pause=1.0, gameover_pause=1.0)
        fields.update(cfg_over)
        return Game(Config(**fields), mobs_dir=self.mobs_dir,
                    items_dir=self.items_dir,
                    prefixes_path=self.prefixes_path)

    def drive(self, game: Game, cond, vote: str | None = None,
              max_ticks: int = 500) -> None:
        """Tick until cond(); while a vote is open, `vote` is cast by one
        viewer every tick (revoting the same digit is harmless)."""
        for _ in range(max_ticks):
            if cond():
                return
            if (vote is not None and game.vote_loop is not None
                    and game.vote_loop.active):
                game.handle_chat_message("viewer", vote)
            game.update(DT)
        self.fail("condition not reached")

    # --- полные прогоны ----------------------------------------------------

    def test_full_run_door_combat_levelup_next_event(self):
        write_mob(self.mobs_dir, hp=3, xp=10, gold=5)
        game = self.make_game()
        self.assertEqual(game.state, EVENT)
        self.assertEqual(len(game.doors), 3)
        # пул из одного моба — моб-двери повторяются
        mob_doors = [d for d in game.doors if d.kind == MOB]
        self.assertTrue(mob_doors)
        self.assertEqual({d.mob.name for d in mob_doors}, {"Тестовый моб"})

        game.handle_chat_message("viewer", mob_door_digit(game))
        self.drive(game, lambda: game.state == COMBAT)
        self.assertEqual(game.combat_phase, ATTACK)
        # боевая кличка: префикс + ник проголосовавшего (базовое имя — на двери)
        self.assertEqual(game.combat.mob.name, "Тестовый viewer")

        # бой до победы: «1» — ближнее в голову / блок головы
        self.drive(game, lambda: game.state == LEVELUP, vote="1")
        self.assertEqual(game.kills, 1)
        self.assertEqual(game.gold_earned, 5)
        self.assertEqual(game.hero.gold, 5)
        self.assertEqual(game.hero.level, 2)
        self.assertEqual(game.hero.hp, 20)  # моб с уроном 0 не пробил

        game.handle_chat_message("viewer", "1")  # прокачка: сила
        self.drive(game, lambda: game.state == COMBAT
                   and game.combat_phase == COMBAT_END)
        self.assertEqual(game.hero.strength, 1)

        # combat_end_pause → следующий EVENT, пул перечитан
        self.drive(game, lambda: game.state == EVENT)
        self.assertEqual(len(game.doors), 3)

    def test_door_mob_scaled_by_hero_level(self):
        """Моб на двери отображается/входит в бой уже со скейлом под
        уровень героя — без повторного скейла в Combat."""
        write_mob(self.mobs_dir, hp=20, damage_min=10, damage_max=10)
        game = self.make_game()
        game.hero.level = 2  # ×1.15: hp 20 → 23, урон 10 → 12
        game.enter_event()  # перебросить двери уже на новом уровне
        digit = mob_door_digit(game)  # сам перебрасывает двери до моба
        mob_doors = [d for d in game.doors if d.kind == MOB]
        self.assertTrue(mob_doors)
        for d in mob_doors:
            self.assertEqual(d.mob.hp, 23)
            self.assertEqual((d.mob.damage_min, d.mob.damage_max), (12, 12))

        game.handle_chat_message("viewer", digit)
        self.drive(game, lambda: game.state == COMBAT)
        self.assertEqual(game.combat.mob.hp, 23)
        self.assertEqual(game.combat.mob_hp, 23)

    def test_death_gameover_new_run(self):
        write_mob(self.mobs_dir, hp=1000, damage_min=50, damage_max=50)
        game = self.make_game()
        self.drive(game, lambda: game.state == COMBAT,
                   vote=mob_door_digit(game))
        game.handle_chat_message("viewer", "1")  # атака: моб не умирает
        self.drive(game, lambda: game.combat_phase == DEFENSE)
        # защита без голосов: моб бьёт 50 → герой умирает (через паузу итога)
        self.drive(game, lambda: game.state == GAME_OVER)
        self.assertFalse(game.hero.alive)
        self.assertEqual(game.run_summary,
                         {"level": 1, "kills": 0, "gold_earned": 0,
                          "defeated": []})

        # gameover_pause → автоматический новый забег
        self.drive(game, lambda: game.state == EVENT)
        self.assertTrue(game.hero.alive)
        self.assertEqual((game.hero.hp, game.hero.level), (20, 1))
        self.assertEqual((game.kills, game.gold_earned), (0, 0))
        self.assertIsNone(game.run_summary)

    # --- «нет голосов» -------------------------------------------------------

    def test_door_no_votes_restarts_with_same_doors(self):
        write_mob(self.mobs_dir, name="Гоблин", hp=5)
        game = self.make_game()
        doors_before = list(game.doors)
        game.update(game.cfg.event_duration + DT)
        self.assertEqual(game.state, EVENT)
        self.assertEqual(game.doors, doors_before)  # тот же состав
        self.assertTrue(game.vote_loop.active)
        self.assertEqual(game.time_left, game.cfg.event_duration)
        # после перезапуска голосование работает
        game.handle_chat_message("viewer", mob_door_digit(game))
        self.drive(game, lambda: game.state == COMBAT)

    def test_combat_no_votes_skips_turns(self):
        write_mob(self.mobs_dir, hp=10, damage_min=3, damage_max=3)
        game = self.make_game()
        self.drive(game, lambda: game.state == COMBAT,
                   vote=mob_door_digit(game))
        # атака без голосов — герой не бьёт, моб цел
        self.drive(game, lambda: game.combat_phase == OUTCOME)
        self.assertEqual((game.last_turn.actor, game.last_turn.direction,
                          game.last_turn.damage), ("hero", None, 0))
        self.assertEqual(game.combat.mob_hp, 10)
        # защита без голосов — моб бьёт без блока
        self.drive(game, lambda: game.combat_phase == OUTCOME
                   and game.last_turn.actor == "mob")
        self.assertFalse(game.last_turn.blocked)
        self.assertEqual(game.hero.hp, 17)
        # бой не встал: следующая атака открылась
        self.drive(game, lambda: game.combat_phase == ATTACK)
        self.assertEqual(game.state, COMBAT)

    def test_levelup_no_votes_restarts(self):
        write_mob(self.mobs_dir, hp=3, xp=10)
        game = self.make_game()
        self.drive(game, lambda: game.state == COMBAT,
                   vote=mob_door_digit(game))
        self.drive(game, lambda: game.state == LEVELUP, vote="1")
        self.assertEqual(game.hero.level, 2)
        game.update(game.cfg.levelup_duration + DT)  # нет голосов
        self.assertEqual(game.state, LEVELUP)  # окно перезапустилось
        self.assertEqual(game.hero.luck, 0)
        game.handle_chat_message("viewer", "5")  # удача
        self.drive(game, lambda: game.state == COMBAT
                   and game.combat_phase == COMBAT_END)
        self.assertEqual(game.hero.luck, 1)

    # --- пулы ----------------------------------------------------------------

    def test_empty_pool_is_error(self):
        game = self.make_game()
        self.assertEqual(game.state, ERROR)
        self.assertTrue(game.error_message)
        self.assertIsNone(game.vote_loop)
        game.update(10.0)  # не падает, состояние не меняется
        game.handle_chat_message("viewer", "1")
        self.assertEqual(game.state, ERROR)

    def test_broken_pool_is_error_with_filename(self):
        (self.mobs_dir / "broken.toml").write_text('name = "Битый"\n',
                                                   encoding="utf-8")
        game = self.make_game()
        self.assertEqual(game.state, ERROR)
        self.assertIn("broken.toml", game.error_message)

    # --- команды в бою -------------------------------------------------------

    def test_attack_commands_respect_ranged_slot(self):
        write_mob(self.mobs_dir, hp=100)
        game = self.make_game()
        self.drive(game, lambda: game.state == COMBAT,
                   vote=mob_door_digit(game))
        # без дальнего оружия 4..6 и мусор не принимаются
        for text in ("4", "6", "hello", ""):
            game.handle_chat_message("viewer", text)
        self.assertEqual(game.vote_loop.counts(), {})

    def test_ranged_attack_spends_use_and_breaks(self):
        write_mob(self.mobs_dir, hp=100)
        game = self.make_game()
        game.hero.equip(Item(name="Лук", icon="", slot="ranged", damage_min=5,
                             damage_max=5, uses=1, armor=None, price=0))
        self.drive(game, lambda: game.state == COMBAT,
                   vote=mob_door_digit(game))
        game.handle_chat_message("viewer", "4")  # дальнее в голову
        self.assertEqual(game.vote_loop.counts(), {"4": 1})
        self.drive(game, lambda: game.combat_phase == OUTCOME)
        self.assertIsNone(game.hero.ranged)  # последний выстрел — сломался

    # --- боевые клички и база чаттеров ---------------------------------------

    def test_battle_name_fallback_without_chatters(self):
        write_mob(self.mobs_dir)
        game = self.make_game()
        door = game.doors[int(mob_door_digit(game)) - 1]
        game.enter_combat(door.mob)  # без чата реестр пуст — кличка без ника
        self.assertEqual(game.combat.mob.name, "Тестовый Тестовый моб")

    def test_defeated_listed_in_run_summary(self):
        write_mob(self.mobs_dir, hp=3, xp=0, gold=0)
        game = self.make_game()
        self.drive(game, lambda: game.state == COMBAT,
                   vote=mob_door_digit(game))
        self.drive(game, lambda: game.state == COMBAT
                   and game.combat_phase == COMBAT_END, vote="1")
        self.assertEqual(game.defeated, ["Тестовый viewer"])
        game.enter_game_over()
        self.assertEqual(game.run_summary["defeated"],
                         ["Тестовый viewer"])

    def test_chat_message_registers_chatter_without_vote(self):
        game = self.make_game()  # пустой пул мобов → ERROR, голосования нет
        self.assertEqual(game.state, ERROR)
        game.handle_chat_message("someone", "привет")
        self.assertIn("someone", game.chatters.all)

    # --- шов оверлея ---------------------------------------------------------

    def test_ui_listener_receives_phase_calls(self):
        calls = []

        class Recorder:
            def __getattr__(self, name):
                return lambda *args: calls.append(name)

        write_mob(self.mobs_dir, hp=3)
        game = Game(Config(seed=SEED, event_duration=5.0), ui=Recorder(),
                    mobs_dir=self.mobs_dir, items_dir=self.items_dir)
        self.assertIn("show_event", calls)
        game.handle_chat_message("viewer", mob_door_digit(game))
        self.assertIn("update_votes", calls)
        self.drive(game, lambda: game.state == COMBAT)
        self.assertIn("show_combat", calls)

    def test_tie_holds_phase_then_applies_winner(self):
        calls = []

        class Recorder:
            def __getattr__(self, name):
                return lambda *args: calls.append((name, args))

        write_mob(self.mobs_dir, hp=3)
        game = Game(Config(seed=SEED, event_duration=5.0,
                           tie_resolve_pause=2.0),
                    ui=Recorder(), mobs_dir=self.mobs_dir,
                    items_dir=self.items_dir,
                    prefixes_path=self.prefixes_path)
        game.handle_chat_message("alice", "1")
        game.handle_chat_message("bob", "2")
        game.update(game.cfg.event_duration + DT)  # конец раунда — ничья 1:1

        # фаза держится на время рулетки, исход отложен
        self.assertEqual(game.state, EVENT)
        self.assertIsNone(game.vote_loop)
        self.assertEqual(game.time_left, game.cfg.tie_resolve_pause)
        resolves = [args for name, args in calls
                    if name == "show_tie_resolve"]
        self.assertEqual(len(resolves), 1)
        leaders, winner = resolves[0]
        self.assertEqual(leaders, ["1", "2"])
        self.assertIn(winner, leaders)
        game.handle_chat_message("carol", "3")  # во время рулетки не считается

        self.drive(game, lambda: game.state != EVENT)
        self.assertIsNone(game._pending_end)
        # перед применением в UI из лидеров остаётся один победитель
        self.assertIn(("update_votes", ({"1": 1, "2": 1}, [winner])), calls)


if __name__ == "__main__":
    unittest.main()
