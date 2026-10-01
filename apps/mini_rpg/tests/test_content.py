"""Tests for content pools: mob/item loading, validation, discovery."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from apps.mini_rpg.core import (DEFAULT_ITEMS_DIR, DEFAULT_MOBS_DIR,
                                ContentError, discover_items, discover_mobs,
                                load_item, load_items, load_mob, load_mobs)

MOB = """
name = "Гоблин"
icon = "👺"
hp = 20
damage_min = 2
damage_max = 5
xp = 8
gold = 5
"""

MELEE = """
name = "Меч"
icon = "🗡️"
slot = "melee"
damage_min = 2
damage_max = 4
price = 8
"""

RANGED = """
name = "Лук"
slot = "ranged"
damage_min = 3
damage_max = 7
uses = 5
price = 15
"""

ARMOR = """
name = "Кольчуга"
slot = "armor"
armor = 2
price = 20
"""


def write(tmp: Path, name: str, body: str) -> Path:
    path = tmp / name
    path.write_text(body, encoding="utf-8")
    return path


class PoolTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def check_mob(self, body: str, needle: str):
        with self.assertRaises(ContentError, msg=body) as cm:
            load_mob(write(self.tmp, "bad.toml", body))
        self.assertIn(needle, str(cm.exception))
        self.assertIn("bad.toml", str(cm.exception))

    def check_item(self, body: str, needle: str):
        with self.assertRaises(ContentError, msg=body) as cm:
            load_item(write(self.tmp, "bad.toml", body))
        self.assertIn(needle, str(cm.exception))
        self.assertIn("bad.toml", str(cm.exception))


class LoadMobTests(PoolTestCase):
    def test_loads_valid_mob(self):
        mob = load_mob(write(self.tmp, "goblin.toml", MOB))
        self.assertEqual(mob.name, "Гоблин")
        self.assertEqual(mob.icon, "👺")
        self.assertEqual(mob.hp, 20)
        self.assertEqual((mob.damage_min, mob.damage_max), (2, 5))
        self.assertEqual((mob.xp, mob.gold), (8, 5))

    def test_optional_fields_default(self):
        mob = load_mob(write(self.tmp, "bare.toml",
                             'name = "Б" \nhp = 5\ndamage_min = 1\n'
                             'damage_max = 1\n'))
        self.assertEqual(mob.icon, "")
        self.assertEqual((mob.xp, mob.gold), (0, 0))

    def test_unknown_keys_ignored(self):
        mob = load_mob(write(self.tmp, "x.toml", MOB + '\nflavor = "текст"\n'))
        self.assertEqual(mob.name, "Гоблин")

    def test_broken_toml(self):
        self.check_mob('name = \n', "ошибка TOML")

    def test_missing_name(self):
        self.check_mob("hp = 10\ndamage_min = 1\ndamage_max = 2\n", "name")

    def test_missing_hp(self):
        self.check_mob('name = "Б"\ndamage_min = 1\ndamage_max = 2\n', "hp")

    def test_max_below_min(self):
        self.check_mob('name = "Б"\nhp = 10\ndamage_min = 5\ndamage_max = 2\n',
                       "damage_max")

    def test_real_pool_is_valid(self):
        mobs = load_mobs(DEFAULT_MOBS_DIR)
        self.assertGreaterEqual(len(mobs), 3, "ожидаются стартовые мобы")


class LoadItemTests(PoolTestCase):
    def test_loads_melee(self):
        item = load_item(write(self.tmp, "sword.toml", MELEE))
        self.assertEqual(item.slot, "melee")
        self.assertEqual((item.damage_min, item.damage_max), (2, 4))
        self.assertIsNone(item.uses)
        self.assertIsNone(item.armor)

    def test_loads_ranged(self):
        item = load_item(write(self.tmp, "bow.toml", RANGED))
        self.assertEqual(item.slot, "ranged")
        self.assertEqual(item.uses, 5)
        self.assertEqual(item.icon, "")

    def test_loads_armor(self):
        item = load_item(write(self.tmp, "mail.toml", ARMOR))
        self.assertEqual(item.armor, 2)
        self.assertIsNone(item.damage_min)

    def test_unknown_keys_ignored(self):
        item = load_item(write(self.tmp, "x.toml", MELEE + '\nlore = "x"\n'))
        self.assertEqual(item.name, "Меч")

    def test_missing_slot(self):
        self.check_item('name = "X"\nprice = 1\n', "slot")

    def test_bad_slot(self):
        self.check_item('name = "X"\nslot = "wand"\nprice = 1\n', "slot")

    def test_missing_price(self):
        self.check_item('name = "X"\nslot = "armor"\narmor = 1\n', "price")

    def test_melee_without_damage(self):
        self.check_item('name = "X"\nslot = "melee"\nprice = 1\n',
                        "damage_min")

    def test_ranged_without_uses(self):
        self.check_item('name = "X"\nslot = "ranged"\ndamage_min = 1\n'
                        'damage_max = 2\nprice = 1\n', "uses")

    def test_ranged_zero_uses(self):
        self.check_item('name = "X"\nslot = "ranged"\ndamage_min = 1\n'
                        'damage_max = 2\nuses = 0\nprice = 1\n', "uses")

    def test_armor_without_armor(self):
        self.check_item('name = "X"\nslot = "armor"\nprice = 1\n', "armor")

    def test_real_pool_is_valid(self):
        items = load_items(DEFAULT_ITEMS_DIR)
        slots = {i.slot for i in items}
        self.assertGreaterEqual(len(items), 5)
        self.assertEqual(slots, {"melee", "ranged", "armor"})


class DiscoveryTests(PoolTestCase):
    def test_sorted_and_toml_only(self):
        write(self.tmp, "b.toml", MOB)
        write(self.tmp, "a.toml", MOB)
        write(self.tmp, "notes.txt", "не моб")
        names = [p.name for p in discover_mobs(self.tmp)]
        self.assertEqual(names, ["a.toml", "b.toml"])

    def test_missing_directory(self):
        self.assertEqual(discover_mobs(self.tmp / "nope"), [])
        self.assertEqual(discover_items(self.tmp / "nope"), [])

    def test_default_dirs_discoverable(self):
        self.assertTrue(discover_mobs(DEFAULT_MOBS_DIR))
        self.assertTrue(discover_items(DEFAULT_ITEMS_DIR))


if __name__ == "__main__":
    unittest.main()
