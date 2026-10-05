"""Tests for content pools: mob/item loading, validation, discovery."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from apps.mini_rpg.core import (DEFAULT_ITEMS_DIR, DEFAULT_MOBS_DIR,
                                DEFAULT_PREFIXES, DEFAULT_STARTER, ContentError,
                                discover_items, discover_mobs, find_starters,
                                load_item, load_items, load_mob, load_mobs,
                                load_prefixes)

MOB = """
name = "Гоблин"
icon = "👺"
hp = 20
damage_min = 2
damage_max = 4
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

ARMOR = """
name = "Кольчуга"
icon = "🛡️"
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
        self.assertEqual((mob.damage_min, mob.damage_max), (2, 4))
        self.assertEqual((mob.xp, mob.gold), (8, 5))

    def test_optional_fields_default(self):
        mob = load_mob(write(self.tmp, "bare.toml",
                             'name = "Б" \nhp = 5\ndamage_min = 1\n'
                             'damage_max = 1\n'))
        self.assertEqual(mob.icon, "")
        self.assertEqual((mob.xp, mob.gold), (0, 0))
        self.assertEqual(mob.cooldown, 5.0)

    def test_cooldown_loads(self):
        mob = load_mob(write(self.tmp, "slow.toml", MOB + "cooldown = 3.5\n"))
        self.assertEqual(mob.cooldown, 3.5)
        mob = load_mob(write(self.tmp, "int.toml", MOB + "cooldown = 7\n"))
        self.assertEqual(mob.cooldown, 7.0)  # целое в TOML — тоже валидно

    def test_cooldown_must_be_positive(self):
        self.check_mob(MOB + "cooldown = 0\n", "cooldown")
        self.check_mob(MOB + "cooldown = -1.5\n", "cooldown")

    def test_cooldown_must_be_numeric(self):
        self.check_mob(MOB + 'cooldown = "быстро"\n', "cooldown")

    def test_unknown_keys_ignored(self):
        mob = load_mob(write(self.tmp, "x.toml", MOB + '\nflavor = "текст"\n'))
        self.assertEqual(mob.name, "Гоблин")

    def test_broken_toml(self):
        self.check_mob('name = \n', "ошибка TOML")

    def test_missing_name(self):
        self.check_mob("hp = 10\ndamage_min = 1\ndamage_max = 1\n", "name")

    def test_missing_hp(self):
        self.check_mob('name = "Б"\ndamage_min = 1\ndamage_max = 1\n', "hp")

    def test_missing_damage(self):
        self.check_mob('name = "Б"\nhp = 10\ndamage_max = 1\n', "damage_min")
        self.check_mob('name = "Б"\nhp = 10\ndamage_min = 1\n', "damage_max")

    def test_negative_damage(self):
        self.check_mob('name = "Б"\nhp = 10\ndamage_min = -1\ndamage_max = 1\n',
                       "damage_min")

    def test_damage_max_below_min(self):
        self.check_mob('name = "Б"\nhp = 10\ndamage_min = 5\ndamage_max = 2\n',
                       "damage_max")

    def test_real_pool_is_valid(self):
        mobs = load_mobs(DEFAULT_MOBS_DIR)
        self.assertEqual({m.name for m in mobs},
                         {"Гоблин", "Орк", "Скелет", "Слайм"})
        for m in mobs:
            self.assertGreaterEqual(m.damage_max, m.damage_min)
            self.assertGreater(m.cooldown, 0)


class LoadItemTests(PoolTestCase):
    def test_loads_melee(self):
        item = load_item(write(self.tmp, "sword.toml", MELEE))
        self.assertEqual(item.slot, "melee")
        self.assertEqual((item.damage_min, item.damage_max), (2, 4))
        self.assertIsNone(item.armor)

    def test_loads_armor(self):
        item = load_item(write(self.tmp, "armor.toml", ARMOR))
        self.assertEqual(item.slot, "armor")
        self.assertEqual(item.armor, 2)
        self.assertEqual(item.icon, "🛡️")
        self.assertIsNone(item.damage_min)
        self.assertIsNone(item.damage_max)

    def test_unknown_keys_ignored(self):
        item = load_item(write(self.tmp, "x.toml", MELEE + '\nlore = "x"\n'))
        self.assertEqual(item.name, "Меч")

    def test_missing_slot(self):
        self.check_item('name = "X"\nprice = 1\n', "slot")

    def test_bad_slot(self):
        self.check_item('name = "X"\nslot = "wand"\nprice = 1\n', "slot")
        self.check_item('name = "X"\nslot = "shield"\nblock_min = 1\n'
                        'block_max = 2\nprice = 1\n', "slot")  # щита больше нет
        self.check_item('name = "X"\nslot = "ranged"\ndamage_min = 1\n'
                        'damage_max = 2\nprice = 1\n', "slot")  # и дальнего нет

    def test_missing_price(self):
        self.check_item('name = "X"\nslot = "armor"\narmor = 1\n', "price")

    def test_melee_without_damage(self):
        self.check_item('name = "X"\nslot = "melee"\nprice = 1\n',
                        "damage_min")
        self.check_item('name = "X"\nslot = "melee"\ndamage_min = 1\n'
                        'price = 1\n', "damage_max")

    def test_damage_max_below_min(self):
        self.check_item('name = "X"\nslot = "melee"\ndamage_min = 5\n'
                        'damage_max = 2\nprice = 1\n', "damage_max")

    def test_armor_without_armor_value(self):
        self.check_item('name = "X"\nslot = "armor"\nprice = 1\n', "armor")

    def test_starter_defaults_to_false(self):
        item = load_item(write(self.tmp, "sword.toml", MELEE))
        self.assertFalse(item.starter)

    def test_starter_flag_loads(self):
        item = load_item(write(self.tmp, "fists.toml", MELEE +
                               "starter = true\n"))
        self.assertTrue(item.starter)

    def test_starter_not_bool(self):
        self.check_item(MELEE + 'starter = "да"\n', "starter")

    def test_starter_any_slot_loads(self):
        armor = load_item(write(self.tmp, "a.toml",
                                ARMOR + "starter = true\n"))
        self.assertTrue(armor.starter)

    def test_real_pool_is_valid(self):
        items = load_items(DEFAULT_ITEMS_DIR)
        self.assertEqual({i.slot for i in items}, {"melee", "armor"})
        self.assertEqual({i.name for i in items},
                         {"Боевой топор", "Кулаки", "Ржавый меч",
                          "Картонная броня", "Кожаная куртка", "Кольчуга",
                          "Рыцарский доспех"})


class FindStartersTests(PoolTestCase):
    def test_picks_starters_one_per_slot(self):
        fists = load_item(write(self.tmp, "fists.toml",
                                MELEE + "starter = true\n"))
        armor = load_item(write(self.tmp, "armor.toml",
                                ARMOR + "starter = true\n"))
        sword = load_item(write(self.tmp, "sword.toml", MELEE))
        self.assertEqual(find_starters([sword, fists, armor]),
                         [fists, armor])

    def test_falls_back_to_default(self):
        sword = load_item(write(self.tmp, "sword.toml", MELEE))
        self.assertEqual(find_starters([sword]), [DEFAULT_STARTER])
        self.assertEqual(find_starters([]), [DEFAULT_STARTER])

    def test_melee_starter_required(self):
        armor = load_item(write(self.tmp, "armor.toml",
                                ARMOR + "starter = true\n"))
        with self.assertRaises(ContentError):
            find_starters([armor])

    def test_two_starters_same_slot_rejected(self):
        a = load_item(write(self.tmp, "a.toml", MELEE + "starter = true\n"))
        b = load_item(write(self.tmp, "b.toml", MELEE + "starter = true\n"))
        with self.assertRaises(ContentError):
            find_starters([a, b])

    def test_real_pool_starter_kit(self):
        kit = {it.slot: it
               for it in find_starters(load_items(DEFAULT_ITEMS_DIR))}
        self.assertEqual(kit["melee"].name, "Кулаки")  # items/fists.toml
        self.assertEqual((kit["melee"].damage_min, kit["melee"].damage_max),
                         (2, 3))
        self.assertEqual(kit["armor"].name, "Картонная броня")
        self.assertEqual(kit["armor"].armor, 0)


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


class LoadPrefixesTests(PoolTestCase):
    def test_loads_list(self):
        path = write(self.tmp, "prefixes.toml",
                     'prefixes = ["Гнусный", "Смешной"]\n')
        self.assertEqual(load_prefixes(path), ["Гнусный", "Смешной"])

    def test_missing_file_falls_back_to_defaults(self):
        self.assertEqual(load_prefixes(self.tmp / "nope.toml"),
                         list(DEFAULT_PREFIXES))

    def test_empty_list_falls_back_to_defaults(self):
        path = write(self.tmp, "prefixes.toml", "prefixes = []\n")
        self.assertEqual(load_prefixes(path), list(DEFAULT_PREFIXES))

    def test_broken_toml_raises(self):
        path = write(self.tmp, "prefixes.toml", 'prefixes = ["а",\n')
        with self.assertRaises(ContentError):
            load_prefixes(path)

    def test_missing_key_raises(self):
        path = write(self.tmp, "prefixes.toml", 'other = ["а"]\n')
        with self.assertRaises(ContentError):
            load_prefixes(path)

    def test_non_string_entries_raise(self):
        path = write(self.tmp, "prefixes.toml", 'prefixes = ["а", 5]\n')
        with self.assertRaises(ContentError):
            load_prefixes(path)


if __name__ == "__main__":
    unittest.main()
