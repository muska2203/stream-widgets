"""Tests for the Game state machine: full runs driven through
handle_chat_message directly (no real chat) with seeded rng and a mob pool
in a temp directory."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from apps.mini_rpg.config import Config
from apps.mini_rpg.core import STATS, Item
from apps.mini_rpg.game import (ATTACK, COMBAT, COMBAT_END, DEFENSE, ERROR,
                                EVENT, GAME_OVER, LEVELUP, MOB, OUTCOME, Game)
from streamkit import ChatterRegistry

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


def word(game: Game, key: str) -> str:
    """Word alias of the canonical key in the currently open vote — chat
    votes with words, digits are rejected (streamkit VoteWords)."""
    return game.vote_key_words[key]


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
                      overtime_duration=2.0,
                      combat_end_pause=1.0, gameover_pause=1.0)
        fields.update(cfg_over)
        return Game(Config(**fields), mobs_dir=self.mobs_dir,
                    items_dir=self.items_dir,
                    prefixes_path=self.prefixes_path)

    def drive(self, game: Game, cond, vote: str | None = None,
              max_ticks: int = 500) -> None:
        """Tick until cond(); while a vote is open, `vote` (canonical key)
        is cast by one viewer every tick via the round's current word
        (words change every round, so the alias is re-read each tick)."""
        for _ in range(max_ticks):
            if cond():
                return
            if (vote is not None and game.vote_loop is not None
                    and game.vote_loop.active):
                game.handle_chat_message("viewer", word(game, vote))
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

        game.handle_chat_message("viewer", word(game, mob_door_digit(game)))
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

        game.handle_chat_message("viewer", word(game, "1"))  # прокачка: сила
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

        game.handle_chat_message("viewer", word(game, digit))
        self.drive(game, lambda: game.state == COMBAT)
        self.assertEqual(game.combat.mob.hp, 23)
        self.assertEqual(game.combat.mob_hp, 23)

    def test_death_gameover_new_run(self):
        write_mob(self.mobs_dir, hp=1000, damage_min=50, damage_max=50)
        game = self.make_game()
        self.drive(game, lambda: game.state == COMBAT,
                   vote=mob_door_digit(game))
        game.handle_chat_message("viewer", word(game, "1"))  # атака: моб не умирает
        self.drive(game, lambda: game.combat_phase == DEFENSE)
        # дальше без голосов: защита случайна (овертайм → рулетка всех),
        # рано или поздно моб пробивает 50 → герой умирает
        self.drive(game, lambda: game.state == GAME_OVER, max_ticks=2000)
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

    # --- «нет голосов»: овертайм → случайный выбор среди всех -----------------

    def test_door_no_votes_overtime_keeps_round_then_vote_counts(self):
        write_mob(self.mobs_dir, name="Гоблин", hp=5)
        game = self.make_game()
        doors_before = list(game.doors)
        words_before = dict(game.vote_key_words)
        game.update(game.cfg.event_duration + DT)
        # 0 голосов — овертайм: тот же состав и те же слова, голосование живо
        self.assertEqual(game.state, EVENT)
        self.assertTrue(game.vote_loop.active)
        self.assertTrue(game.overtime)
        self.assertEqual(game.time_left, game.cfg.overtime_duration)
        self.assertEqual(game.doors, doors_before)
        self.assertEqual(game.vote_key_words, words_before)
        # голос в овертайме засчитывается тем же словом
        game.handle_chat_message("viewer", word(game, mob_door_digit(game)))
        self.assertEqual(game.vote_loop.counts(), {mob_door_digit(game): 1})
        self.drive(game, lambda: game.state == COMBAT)

    def test_door_overtime_no_votes_random_among_all(self):
        calls = []

        class Recorder:
            def __getattr__(self, name):
                return lambda *args: calls.append((name, args))

        write_mob(self.mobs_dir, name="Гоблин", hp=5)
        game = Game(Config(seed=SEED, event_duration=5.0,
                           overtime_duration=2.0, tie_resolve_pause=2.0),
                    ui=Recorder(), mobs_dir=self.mobs_dir,
                    items_dir=self.items_dir,
                    prefixes_path=self.prefixes_path)
        game.update(game.cfg.event_duration + DT)   # 0 голосов — овертайм
        self.assertTrue(game.overtime)
        game.update(game.cfg.overtime_duration + DT)  # снова 0 — рулетка всех
        self.assertFalse(game.overtime)
        self.assertEqual(game.state, EVENT)  # фаза держится на рулетку
        self.assertIsNone(game.vote_loop)
        self.assertEqual(game.time_left, game.cfg.tie_resolve_pause)
        resolves = [args for name, args in calls
                    if name == "show_tie_resolve"]
        self.assertEqual(len(resolves), 1)
        leaders, winner = resolves[0]
        self.assertEqual(leaders, ["1", "2", "3"])  # ВСЕ варианты, не лидеры
        self.assertIn(winner, leaders)
        self.drive(game, lambda: game.state != EVENT)  # исход применён

    def test_combat_no_votes_random_turns(self):
        write_mob(self.mobs_dir, hp=10, damage_min=3, damage_max=3)
        game = self.make_game()
        self.drive(game, lambda: game.state == COMBAT,
                   vote=mob_door_digit(game))
        # атака без голосов: овертайм → случайная атака (не пропуск хода)
        self.drive(game, lambda: game.combat_phase == OUTCOME)
        self.assertEqual(game.last_turn.actor, "hero")
        self.assertIsNotNone(game.last_turn.direction)
        # защита без голосов: тоже случайный выбор, бой не встаёт
        self.drive(game, lambda: game.combat_phase == OUTCOME
                   and game.last_turn.actor == "mob")
        self.drive(game, lambda: game.combat_phase == ATTACK)
        self.assertEqual(game.state, COMBAT)

    def test_levelup_no_votes_random_stat(self):
        write_mob(self.mobs_dir, hp=3, xp=10)
        game = self.make_game()
        self.drive(game, lambda: game.state == COMBAT,
                   vote=mob_door_digit(game))
        self.drive(game, lambda: game.state == LEVELUP, vote="1")
        self.assertEqual(game.hero.level, 2)
        game.update(game.cfg.levelup_duration + DT)  # 0 голосов — овертайм
        self.assertEqual(game.state, LEVELUP)
        self.assertTrue(game.overtime)
        game.update(game.cfg.overtime_duration + DT)  # рулетка всех стат
        self.assertEqual(game.state, LEVELUP)  # исход отложен на рулетку
        self.drive(game, lambda: game.state == COMBAT
                   and game.combat_phase == COMBAT_END)
        self.assertFalse(game.overtime)
        stats = [getattr(game.hero, s) for s in STATS]
        self.assertEqual(sum(stats), 1)  # случайная стата поднялась

    def test_overtime_keeps_round_words(self):
        write_mob(self.mobs_dir, hp=3)
        game = self.make_game()
        first = dict(game.vote_key_words)
        self.assertTrue(all(first.values()))
        game.update(game.cfg.event_duration + DT)  # 0 голосов — овертайм
        # слова НЕ перевыдаются: зрители продолжают голосовать теми же
        self.assertEqual(game.vote_key_words, first)

    # --- голосование словами ---------------------------------------------------

    def test_digits_rejected_words_accepted(self):
        write_mob(self.mobs_dir, hp=3)
        game = self.make_game()
        # цифры и классические команды в words-режиме — не команды
        for text in ("1", "левая", "удар в голову", "блок ног"):
            game.handle_chat_message("viewer", text)
        self.assertEqual(game.vote_loop.counts(), {})
        game.handle_chat_message("viewer", word(game, "1"))
        self.assertEqual(game.vote_loop.counts(), {"1": 1})  # канонический ключ

    # --- классический режим (vote_mode = "classic") -----------------------------

    def test_classic_mode_door_commands(self):
        write_mob(self.mobs_dir, hp=3)
        game = self.make_game(vote_mode="classic")
        self.assertIsNone(game.vote_words)  # VoteWords не создаётся
        self.assertEqual(game.vote_key_words,
                         {"1": "левая", "2": "средняя", "3": "правая"})
        game.handle_chat_message("viewer", "левая")
        self.assertEqual(game.vote_loop.counts(), {"1": 1})
        # цифры и слова words-режима не принимаются
        for text in ("1", "меч", "привет"):
            game.handle_chat_message("viewer2", text)
        self.assertEqual(game.vote_loop.counts(), {"1": 1})

    def test_classic_mode_combat_and_levelup_commands(self):
        write_mob(self.mobs_dir, hp=3, xp=10)
        game = self.make_game(vote_mode="classic")
        game.handle_chat_message("viewer", word(game, mob_door_digit(game)))
        self.drive(game, lambda: game.state == COMBAT)
        # атака без дальнего: «удар в голову/удар в тело/удар в ноги»
        self.assertEqual(game.vote_key_words,
                         {"1": "удар в голову", "2": "удар в тело",
                          "3": "удар в ноги"})
        game.handle_chat_message("viewer", "удар в голову")
        self.assertEqual(game.vote_loop.counts(), {"1": 1})
        # бой до прокачки: «удар в голову» — ближнее в голову / «блок головы»
        self.drive(game, lambda: game.state == LEVELUP, vote="1")
        self.assertEqual(game.vote_key_words["5"], "удача")
        game.handle_chat_message("viewer", "удача")
        self.drive(game, lambda: game.state == COMBAT
                   and game.combat_phase == COMBAT_END)
        self.assertEqual(game.hero.luck, 1)

    def test_no_votes_restart_deals_new_words(self):
        write_mob(self.mobs_dir, hp=3)
        game = self.make_game()
        first = dict(game.vote_key_words)
        self.assertTrue(all(first.values()))
        # 0 голосов → овертайм (слова те же) → снова 0 → случайный выбор;
        # СЛЕДУЮЩЕЕ голосование на дверях получает новые слова
        game.update(game.cfg.event_duration + DT)
        game.update(game.cfg.overtime_duration + DT)  # рулетка всех дверей
        self.drive(game, lambda: game.state != EVENT)
        # переживаем исход (бой/отдых) до следующего выбора двери
        self.drive(game, lambda: game.state == EVENT, vote="1")
        self.assertTrue(all(game.vote_key_words.values()))
        self.assertNotEqual(game.vote_key_words, first)

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
        # без дальнего оружия у 4..6 нет слов в маппинге, а цифры и мусор
        # не принимаются (голосуют словами)
        self.assertNotIn("4", game.vote_key_words)
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
        game.handle_chat_message("viewer", word(game, "4"))  # дальнее в голову
        self.assertEqual(game.vote_loop.counts(), {"4": 1})  # канонический ключ
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

    def test_empty_persistent_registry_not_replaced(self):
        # регрессия: Game брал `chatters or ChatterRegistry()`, а у реестра
        # __len__ → пустой реестр с путём подменялся in-memory, база не писалась
        path = Path(self.mobs_dir) / "chatters.json"
        registry = ChatterRegistry(path)
        game = Game(Config(seed=SEED, event_duration=5.0),
                    mobs_dir=self.mobs_dir, items_dir=self.items_dir,
                    chatters=registry)
        self.assertIs(game.chatters, registry)
        game.handle_chat_message("someone", "привет")
        self.assertEqual(ChatterRegistry(path).all, {"someone"})

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
        game.handle_chat_message("viewer", word(game, mob_door_digit(game)))
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
        game.handle_chat_message("alice", word(game, "1"))
        game.handle_chat_message("bob", word(game, "2"))
        game.update(game.cfg.event_duration + DT)  # конец раунда — ничья 1:1

        # фаза держится на время рулетки, исход отложен
        self.assertEqual(game.state, EVENT)
        self.assertIsNone(game.vote_loop)
        self.assertEqual(game.time_left, game.cfg.tie_resolve_pause)
        resolves = [args for name, args in calls
                    if name == "show_tie_resolve"]
        self.assertEqual(len(resolves), 1)
        leaders, winner = resolves[0]
        self.assertEqual(leaders, ["1", "2"])  # канонические ключи, не слова
        self.assertIn(winner, leaders)
        game.handle_chat_message("carol", "мусор")  # во время рулетки не считается

        self.drive(game, lambda: game.state != EVENT)
        self.assertIsNone(game._pending_end)
        # перед применением в UI из лидеров остаётся один победитель
        self.assertIn(("update_votes", ({"1": 1, "2": 1}, [winner])), calls)


if __name__ == "__main__":
    unittest.main()
