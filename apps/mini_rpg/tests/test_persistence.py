"""Tests for savegame checkpoints (apps/mini_rpg/persistence.py): hero +
run counters round-trip, restore into a fresh EVENT, broken/outdated saves
falling back to a new run without crashing."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from apps.mini_rpg.config import Config
from apps.mini_rpg.core import Item
from apps.mini_rpg.game import EVENT, Game
from apps.mini_rpg.persistence import (SAVE_VERSION, load_checkpoint,
                                       save_checkpoint)

SEED = 20260930

MOB_TOML = """\
name = "Тестовый моб"
hp = 4
damage_min = 0
damage_max = 0
xp = 0
gold = 0
"""


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.mobs_dir = self.tmp / "mobs"
        self.mobs_dir.mkdir()
        (self.mobs_dir / "mob.toml").write_text(MOB_TOML, encoding="utf-8")
        self.items_dir = self.tmp / "items"  # нет каталога — пустой пул
        self.prefixes_path = self.tmp / "prefixes.toml"  # нет — дефолт
        self.save_path = self.tmp / "savegame.json"

    def make_game(self, save=True) -> Game:
        return Game(Config(seed=SEED, event_duration=5.0),
                    mobs_dir=self.mobs_dir, items_dir=self.items_dir,
                    prefixes_path=self.prefixes_path,
                    save_path=self.save_path if save else None)

    def progress(self, game: Game) -> None:
        """Мутируем героя и счётчики, как после пары боёв и магазина."""
        hero = game.hero
        hero.level_up("strength")
        hero.level_up("endurance")
        hero.gold = 37
        hero.hp = hero.max_hp - 3
        hero.mana = 0
        hero.equip(Item(name="Ржавый меч", icon="🗡️", slot="melee",
                        damage_min=1, damage_max=4, armor=None, price=8))
        hero.equip(Item(name="Кольчуга", icon="🛡", slot="armor",
                        damage_min=None, damage_max=None, armor=2, price=20))
        game.kills = 3
        game.gold_earned = 21
        game.deaths = 2
        game.defeated = ["Злой Вася", "Хилый viewer2"]

    def test_save_version_is_3(self):
        self.assertEqual(SAVE_VERSION, 3)

    def test_roundtrip_hero_and_counters(self):
        game = self.make_game()
        self.progress(game)
        game.pending_levelups = 1
        game._save_checkpoint()
        data = load_checkpoint(self.save_path)
        self.assertIsNotNone(data)
        hero = data["hero"]
        self.assertEqual(hero.strength, 1)
        self.assertEqual(hero.endurance, 1)
        self.assertEqual(hero.gold, 37)
        self.assertEqual(hero.hp, hero.max_hp - 3)
        self.assertEqual(hero.mana, 0)
        self.assertEqual(hero.melee.name, "Ржавый меч")
        self.assertEqual((hero.melee.damage_min, hero.melee.damage_max), (1, 4))
        self.assertEqual(hero.damage_range(), (2, 5))  # +1 сила
        self.assertEqual(hero.armor.name, "Кольчуга")
        self.assertEqual(hero.armor.armor, 2)
        self.assertEqual(hero.armor_value, 2)
        self.assertEqual(data["kills"], 3)
        self.assertEqual(data["gold_earned"], 21)
        self.assertEqual(data["deaths"], 2)
        self.assertEqual(data["defeated"], ["Злой Вася", "Хилый viewer2"])
        self.assertEqual(data["pending_levelups"], 1)

    def test_no_legacy_fields_in_save(self):
        # старых полей (ranged/shield/uses/block) в сейве больше нет
        game = self.make_game()
        self.progress(game)
        game._save_checkpoint()
        data = json.loads(self.save_path.read_text(encoding="utf-8"))
        hero = data["hero"]
        self.assertIn("melee", hero)
        self.assertIn("armor", hero)
        for legacy in ("ranged", "shield", "uses", "block_min", "block_max"):
            self.assertNotIn(legacy, hero)
            self.assertNotIn(legacy, hero["melee"])
            self.assertNotIn(legacy, hero["armor"])

    def test_new_game_restores_progress_into_fresh_event(self):
        game = self.make_game()
        self.progress(game)
        game._save_checkpoint()
        restored = self.make_game()
        self.assertEqual(restored.state, EVENT)  # свежие двери, не бой
        self.assertEqual(restored.hero.strength, 1)
        self.assertEqual(restored.hero.gold, 37)
        self.assertEqual(restored.hero.hp, restored.hero.max_hp - 3)
        self.assertEqual(restored.kills, 3)
        self.assertEqual(restored.defeated, ["Злой Вася", "Хилый viewer2"])

    def test_event_entry_writes_checkpoint(self):
        game = self.make_game()
        self.assertTrue(self.save_path.is_file())  # конструктор → EVENT
        game.enter_event()
        data = json.loads(self.save_path.read_text(encoding="utf-8"))
        self.assertEqual(data["version"], SAVE_VERSION)

    def test_new_run_wipes_progress(self):
        game = self.make_game()
        self.progress(game)
        game._save_checkpoint()
        game.enter_run_start()  # свежий старт (битый сейв) → герой 1 уровня
        restored = self.make_game()
        self.assertEqual(restored.hero.level, 1)
        self.assertEqual(restored.kills, 0)

    def test_death_checkpoint_resets_run_stats(self):
        game = self.make_game()
        self.progress(game)
        game.hero.xp = 8
        game.hero.hp = 0  # погиб в бою
        game.enter_game_over()  # чекпоинт пишется сразу после сброса
        restored = self.make_game()
        self.assertEqual(restored.state, EVENT)
        self.assertEqual(restored.hero.strength, 1)
        self.assertEqual(restored.hero.armor.armor, 2)
        self.assertEqual((restored.hero.gold, restored.hero.xp), (0, 0))
        self.assertEqual(restored.hero.hp, restored.hero.max_hp)
        self.assertEqual(restored.kills, 0)      # статистика забега сброшена
        self.assertEqual(restored.gold_earned, 0)
        self.assertEqual(restored.defeated, [])
        self.assertEqual(restored.deaths, 3)  # 2 из progress + смерть

    def test_save_without_deaths_rejected(self):
        # deaths — обязательное поле SAVE_VERSION=3; сейв без него битый
        game = self.make_game()
        self.progress(game)
        game._save_checkpoint()
        data = json.loads(self.save_path.read_text(encoding="utf-8"))
        del data["deaths"]
        self.save_path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIsNone(load_checkpoint(self.save_path))
        restored = self.make_game()  # новый забег вместо падения
        self.assertEqual(restored.deaths, 0)
        self.assertEqual(restored.kills, 0)
        self.assertEqual(restored.hero.level, 1)

    def test_broken_json_falls_back_to_new_run(self):
        self.save_path.write_text("{не json", encoding="utf-8")
        game = self.make_game()
        self.assertEqual(game.state, EVENT)
        self.assertEqual(game.hero.level, 1)
        # битый файл отложен в .bak, но свежий чекпоинт уже перезаписал сейв
        self.assertTrue((self.tmp / "savegame.json.bak").is_file())

    def test_wrong_version_falls_back_to_new_run(self):
        game = self.make_game()
        game._save_checkpoint()
        data = json.loads(self.save_path.read_text(encoding="utf-8"))
        data["version"] = SAVE_VERSION + 1
        self.save_path.write_text(json.dumps(data), encoding="utf-8")
        fresh = self.make_game()
        self.assertEqual(fresh.hero.level, 1)

    def test_missing_fields_fall_back_to_new_run(self):
        self.save_path.write_text(json.dumps(
            {"version": SAVE_VERSION, "hero": {"base_hp": 20}}),
            encoding="utf-8")
        self.assertIsNone(load_checkpoint(self.save_path))

    def test_hp_clamped_to_max_on_load(self):
        game = self.make_game()
        game._save_checkpoint()
        data = json.loads(self.save_path.read_text(encoding="utf-8"))
        data["hero"]["hp"] = 999
        self.save_path.write_text(json.dumps(data, ensure_ascii=False),
                                  encoding="utf-8")
        restored = load_checkpoint(self.save_path)
        self.assertEqual(restored["hero"].hp, restored["hero"].max_hp)

    def test_dead_hero_save_rejected(self):
        game = self.make_game()
        game._save_checkpoint()
        data = json.loads(self.save_path.read_text(encoding="utf-8"))
        data["hero"]["hp"] = 0
        self.save_path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIsNone(load_checkpoint(self.save_path))

    def test_no_save_path_writes_nothing(self):
        game = self.make_game(save=False)
        game._save_checkpoint()  # no-op
        game.enter_event()
        self.assertEqual(list(self.tmp.glob("*.json")), [])


if __name__ == "__main__":
    unittest.main()
