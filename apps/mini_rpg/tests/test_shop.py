"""Tests for the SHOP and REST states and the mixed door roll (этап 9):
price filter, purchase equips a copy (the item pool never mutates), exit
by "0" and by timeout, rest heals to full, mixed doors (types repeat,
concrete mobs don't), empty/broken item pool."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from apps.mini_rpg.config import Config
from apps.mini_rpg.game import (ERROR, EVENT, MOB, REST, REST_KIND, SHOP,
                                SHOP_KIND, Game)

SEED = 20260930
DT = 0.5

MOB_TOML = """\
name = "{name}"
hp = 4
damage_min = 0
damage_max = 0
xp = 0
gold = 0
"""


def write_mob(directory: Path, filename: str, name: str) -> None:
    (directory / filename).write_text(MOB_TOML.format(name=name),
                                      encoding="utf-8")


def write_item(directory: Path, filename: str, **fields) -> None:
    defaults = dict(name="Тестовый предмет", slot="melee", damage_min=2,
                    damage_max=4, price=5)
    defaults.update(fields)
    lines = []
    for key, value in defaults.items():
        if value is None:
            continue
        value = f'"{value}"' if isinstance(value, str) else value
        lines.append(f"{key} = {value}")
    (directory / filename).write_text("\n".join(lines) + "\n",
                                      encoding="utf-8")


def door_digit(game: Game, kind: str) -> str | None:
    for i, door in enumerate(game.doors):
        if door.kind == kind:
            return str(i + 1)
    return None


class ShopRestTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.mobs_dir = Path(self._tmp.name) / "mobs"
        self.items_dir = Path(self._tmp.name) / "items"
        self.mobs_dir.mkdir()
        self.items_dir.mkdir()
        write_mob(self.mobs_dir, "mob.toml", "Тестовый моб")

    def make_game(self, **cfg_over) -> Game:
        fields = dict(seed=SEED, event_duration=5.0, shop_duration=5.0,
                      combat_end_pause=1.0)
        fields.update(cfg_over)
        return Game(Config(**fields), mobs_dir=self.mobs_dir,
                    items_dir=self.items_dir)

    def drive(self, game: Game, cond, max_ticks: int = 500) -> None:
        for _ in range(max_ticks):
            if cond():
                return
            game.update(DT)
        self.fail("condition not reached")

    def open_shop(self, game: Game, gold: int) -> None:
        game.hero.gold = gold
        game.enter_shop()
        self.assertEqual(game.state, SHOP)

    # --- магазин ---------------------------------------------------------------

    def test_price_filter_hides_unaffordable(self):
        write_item(self.items_dir, "cheap.toml", name="Дешёвый", price=5)
        write_item(self.items_dir, "edge.toml", name="Ровно", price=10)
        write_item(self.items_dir, "pricey.toml", name="Дорогой", price=15)
        game = self.make_game()
        self.open_shop(game, gold=10)
        self.assertEqual(sorted(it.name for it in game.shop_items),
                         ["Дешёвый", "Ровно"])  # дороже золота — не показан

    def test_max_9_distinct_items(self):
        for i in range(12):
            write_item(self.items_dir, f"item{i}.toml",
                       name=f"Предмет {i}", price=0)
        game = self.make_game()
        self.open_shop(game, gold=10)
        self.assertEqual(len(game.shop_items), 9)
        self.assertEqual(len({it.name for it in game.shop_items}), 9)

    def test_purchase_equips_copy_pool_intact(self):
        write_item(self.items_dir, "bow.toml", name="Лук", slot="ranged",
                   uses=3, price=5)
        game = self.make_game()
        self.open_shop(game, gold=10)
        game.handle_chat_message("viewer", "1")
        game.update(game.cfg.shop_duration + DT)

        bow = game.hero.ranged
        self.assertIsNotNone(bow)
        self.assertEqual(bow.name, "Лук")
        self.assertEqual(game.hero.gold, 5)
        pool_item = game.items_pool[0]
        self.assertIsNot(bow, pool_item)  # экипирована копия
        game.hero.use_ranged()
        self.assertEqual(bow.uses, 2)
        self.assertEqual(pool_item.uses, 3)  # пул не мутировал

        self.assertEqual(game.state, SHOP)  # пауза перед возвратом
        game.update(game.cfg.combat_end_pause + DT)
        self.assertEqual(game.state, EVENT)

    def test_purchase_replaces_old_item(self):
        write_item(self.items_dir, "sword.toml", name="Меч", damage_min=3,
                   damage_max=5, price=4)
        game = self.make_game()
        old = game.hero.melee  # стартовые «Кулаки»
        self.open_shop(game, gold=10)
        game.handle_chat_message("viewer", "1")
        game.update(game.cfg.shop_duration + DT)
        self.assertEqual(game.hero.melee.name, "Меч")
        self.assertIsNot(game.hero.melee, old)  # старый потерян

    def test_exit_by_zero(self):
        write_item(self.items_dir, "sword.toml", name="Меч", price=5)
        game = self.make_game()
        self.open_shop(game, gold=10)
        game.handle_chat_message("viewer", "0")
        game.update(game.cfg.shop_duration + DT)
        self.assertEqual(game.hero.gold, 10)  # без покупки
        self.assertEqual(game.hero.melee.name, "Кулаки")
        game.update(game.cfg.combat_end_pause + DT)
        self.assertEqual(game.state, EVENT)

    def test_exit_by_timeout_no_votes(self):
        write_item(self.items_dir, "sword.toml", name="Меч", price=5)
        game = self.make_game()
        self.open_shop(game, gold=10)
        game.update(game.cfg.shop_duration + DT)  # нет голосов — выход
        self.assertEqual(game.hero.gold, 10)
        self.assertEqual(game.hero.melee.name, "Кулаки")
        game.update(game.cfg.combat_end_pause + DT)
        self.assertEqual(game.state, EVENT)

    def test_all_unaffordable_only_exit_remains(self):
        write_item(self.items_dir, "pricey.toml", name="Дорогой", price=50)
        game = self.make_game()
        self.open_shop(game, gold=0)
        self.assertEqual(game.shop_items, [])
        game.handle_chat_message("viewer", "1")  # нечего покупать
        self.assertEqual(game.vote_loop.counts(), {})
        game.handle_chat_message("viewer", "0")  # только выход
        self.assertEqual(game.vote_loop.counts(), {"0": 1})
        game.update(game.cfg.shop_duration + DT)
        game.update(game.cfg.combat_end_pause + DT)
        self.assertEqual(game.state, EVENT)

    # --- отдых -----------------------------------------------------------------

    def test_rest_heals_to_full(self):
        game = self.make_game()
        hero = game.hero
        hero.intellect = 2  # max_mana = 10
        hero.hp = 5
        hero.mana = 3
        game.enter_rest()
        self.assertEqual(game.state, REST)
        self.assertIsNone(game.vote_loop)  # голосований нет
        self.assertEqual((hero.hp, hero.mana), (hero.max_hp, hero.max_mana))
        game.update(game.cfg.combat_end_pause + DT)
        self.assertEqual(game.state, EVENT)

    # --- двери -----------------------------------------------------------------

    def test_door_vote_opens_shop_and_rest(self):
        write_item(self.items_dir, "sword.toml", name="Меч", price=1)
        game = self.make_game()
        game.hero.gold = 10
        for kind, state in ((SHOP_KIND, SHOP), (REST_KIND, REST)):
            digit = None
            for _ in range(50):
                digit = door_digit(game, kind)
                if digit is not None:
                    break
                game.enter_event()  # переброс дверей
            self.assertIsNotNone(digit, f"{kind} не выпал за 50 перебросов")
            game.handle_chat_message("viewer", digit)
            self.drive(game, lambda: game.state == state)
            self.drive(game, lambda: game.state == EVENT)  # фаза до конца

    def test_mixed_doors_types_repeat_mobs_distinct(self):
        for i in range(4):
            write_mob(self.mobs_dir, f"mob{i}.toml", f"Моб {i}")
        write_item(self.items_dir, "sword.toml", name="Меч", price=1)
        game = self.make_game()
        seen_kinds, type_repeat_seen = set(), False
        for _ in range(40):
            game.enter_event()
            kinds = [d.kind for d in game.doors]
            seen_kinds.update(kinds)
            type_repeat_seen |= len(set(kinds)) < len(kinds)
            mobs = [d.mob.name for d in game.doors if d.kind == MOB]
            self.assertEqual(len(mobs), len(set(mobs)))  # моб не дублируется
        self.assertEqual(seen_kinds, {MOB, SHOP_KIND, REST_KIND})
        self.assertTrue(type_repeat_seen)  # типы повторяются

    def test_empty_items_pool_no_shop_doors(self):
        game = self.make_game()  # items_dir пуст — магазин не предлагается
        self.assertEqual(game.state, EVENT)
        for _ in range(20):
            game.enter_event()
            self.assertEqual(game.state, EVENT)
            self.assertIsNone(door_digit(game, SHOP_KIND))

    def test_broken_items_pool_is_error(self):
        (self.items_dir / "broken.toml").write_text('name = "Битый"\n',
                                                    encoding="utf-8")
        game = self.make_game()
        self.assertEqual(game.state, ERROR)
        self.assertIn("broken.toml", game.error_message)


if __name__ == "__main__":
    unittest.main()
