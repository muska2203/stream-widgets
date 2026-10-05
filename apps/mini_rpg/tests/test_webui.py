"""WebUI (модель состояния оверлея): начальный снапшот, фазы, голоса,
таймер, JSON-сериализуемость, атомарная публикация. Headless: игра
подменяется SimpleNamespace с настоящими Hero/Mob/Combat."""

from __future__ import annotations

import json
import random
import unittest
from types import SimpleNamespace

from apps.mini_rpg.core import Combat, Item, Mob, new_hero
from apps.mini_rpg.game import Door
from apps.mini_rpg.webui import WebUI

BASE_HP = 20


def make_game(**over) -> SimpleNamespace:
    fields = dict(state="event", hero=new_hero(BASE_HP), doors=[],
                  combat=None, combat_phase="",
                  shop_items=[], time_left=0.0, run_summary=None,
                  error_message="", vote_key_words={}, overtime=False)
    fields.update(over)
    return SimpleNamespace(**fields)


def make_mob(**over) -> Mob:
    fields = dict(name="Гоблин", icon="👺", hp=20, damage_min=2, damage_max=4,
                  xp=8, gold=5)
    fields.update(over)
    return Mob(**fields)


def make_sword(**over) -> Item:
    fields = dict(name="Меч", icon="🗡️", slot="melee", damage_min=3,
                  damage_max=7, armor=None, price=15)
    fields.update(over)
    return Item(**fields)


def make_armor(**over) -> Item:
    fields = dict(name="Кольчуга", icon="🛡️", slot="armor", damage_min=None,
                  damage_max=None, armor=2, price=20)
    fields.update(over)
    return Item(**fields)


def make_combat(game, mob: Mob | None = None, seed: int = 1) -> Combat:
    combat = Combat(game.hero, mob or make_mob(), random.Random(seed))
    game.combat = combat
    return combat


def snapshot(ui: WebUI) -> dict:
    # JSON-сериализуемость — часть контракта
    return json.loads(json.dumps(ui.snapshot, ensure_ascii=False))


class WebUITest(unittest.TestCase):
    def test_initial_snapshot(self):
        s = snapshot(WebUI(make_game()))
        self.assertEqual(s["phase"], "event")
        self.assertEqual(s["time_left"], 0)
        self.assertEqual(s["event"], {"doors": []})

        hero = s["hero"]
        self.assertEqual(hero["level"], 1)
        self.assertEqual(hero["xp"], 0)
        self.assertEqual(hero["xp_to_next"], 10)
        self.assertEqual(hero["gold"], 0)
        self.assertEqual(hero["deaths"], 0)
        self.assertEqual((hero["hp"], hero["max_hp"]), (BASE_HP, BASE_HP))
        self.assertEqual((hero["mana"], hero["max_mana"]), (0, 0))
        self.assertEqual([st["key"] for st in hero["stats"]],
                         ["strength", "agility", "intellect", "endurance",
                          "luck"])
        self.assertEqual(hero["stats"][0]["name"], "Сила")
        self.assertEqual(hero["stats"][4]["name"], "Удача")
        self.assertTrue(all(st["value"] == 0 for st in hero["stats"]))

        slots = hero["slots"]
        self.assertEqual(set(slots), {"melee", "armor"})
        self.assertEqual(slots["melee"]["name"], "Кулаки")
        self.assertEqual(slots["melee"]["damage"], "1–2")
        self.assertIsNone(slots["armor"])

    def test_hero_panel_armor_slot(self):
        game = make_game()
        game.hero.equip(make_armor())
        s = snapshot(WebUI(game))
        armor = s["hero"]["slots"]["armor"]
        self.assertEqual(armor["slot_name"], "Броня")
        self.assertEqual(armor["name"], "Кольчуга")
        self.assertEqual(armor["armor"], 2)

    def test_event_doors_and_votes(self):
        doors = [Door("mob", make_mob(name="Гоблин")),
                 Door("mob", make_mob(name="Скелет", icon="💀")),
                 Door("shop"), ]
        words = {"1": "меч", "2": "волк", "3": "гора"}
        ui = WebUI(make_game(doors=doors, vote_key_words=words))
        s = snapshot(ui)
        self.assertEqual(s["phase"], "event")
        shown = s["event"]["doors"]
        self.assertEqual([d["n"] for d in shown], [1, 2, 3])
        # слово-алиас раунда (по нему голосуют в чате) рядом с ключом
        self.assertEqual([d["word"] for d in shown], ["меч", "волк", "гора"])
        self.assertEqual([d["name"] for d in shown],
                         ["Гоблин", "Скелет", "Магазин"])
        self.assertEqual(shown[1]["icon"], "💀")
        self.assertEqual(shown[2]["icon"], "🏪")  # иконка типа события
        self.assertEqual(shown[0]["threat"], "HP 20 · урон 2–4")
        self.assertIsNone(shown[2]["threat"])  # угроза только у моб-дверей
        self.assertTrue(all(d["votes"] == 0 and d["state"] == "idle"
                            for d in shown))

        ui.update_votes({"1": 2, "3": 1}, ["1"])
        shown = snapshot(ui)["event"]["doors"]
        self.assertEqual((shown[0]["votes"], shown[0]["state"]), (2, "leader"))
        self.assertEqual(shown[1]["state"], "idle")
        self.assertEqual((shown[2]["votes"], shown[2]["state"]), (1, "active"))

    def test_event_tie_all_leaders_highlighted(self):
        doors = [Door("mob", make_mob(name="Гоблин")),
                 Door("mob", make_mob(name="Скелет", icon="💀")),
                 Door("shop")]
        ui = WebUI(make_game(doors=doors))
        ui.update_votes({"1": 2, "3": 2, "2": 1}, ["1", "3"])
        shown = snapshot(ui)["event"]["doors"]
        self.assertEqual([d["state"] for d in shown],
                         ["leader", "active", "leader"])

    def test_tie_resolve_block_lives_one_snapshot(self):
        doors = [Door("mob", make_mob(name="Гоблин")), Door("shop"),
                 Door("rest")]
        ui = WebUI(make_game(doors=doors, time_left=3.0))
        ui.show_tie_resolve(["1", "3"], "3")
        resolve = snapshot(ui)["resolve"]
        self.assertEqual(resolve["leaders"], ["1", "3"])
        self.assertEqual(resolve["winner"], "3")
        self.assertEqual(resolve["duration"], 3.0)
        # блок живёт одну публикацию: следующая — уже без него,
        # чтобы повторная ничья перезапускала анимацию
        ui.show_error("поздняя публикация")
        self.assertIsNone(snapshot(ui)["resolve"])

    def test_combat_fight_snapshot(self):
        game = make_game(state="combat", combat_phase="fight")
        make_combat(game)
        s = snapshot(WebUI(game))
        self.assertEqual(s["phase"], "combat")
        block = s["combat"]
        self.assertEqual(block["subphase"], "fight")
        self.assertEqual(block["mob"],
                         {"icon": "👺", "name": "Гоблин", "hp": 20,
                          "max_hp": 20, "damage": "2–4", "cooldown": 5.0,
                          "cd_left": 5.0})
        self.assertEqual(block["hero_cd"], {"cooldown": 5.0, "cd_left": 5.0})
        self.assertEqual(block["squad"], [])
        self.assertEqual(block["events"], [])

    def test_combat_squad_entries_in_join_order(self):
        game = make_game(state="combat", combat_phase="fight")
        combat = make_combat(game)
        combat.join("bob")
        combat.join("alice")
        ui = WebUI(game)
        ui.show_combat(combat, "fight")  # републикация отряда (как в Game)
        squad = snapshot(ui)["combat"]["squad"]
        self.assertEqual([u["nick"] for u in squad], ["bob", "alice"])
        for entry in squad:
            self.assertEqual(set(entry), {"nick", "emoji", "damage",
                                          "cooldown", "cd_left", "active"})
            self.assertTrue(entry["emoji"])
            self.assertTrue(entry["active"])
            self.assertGreaterEqual(entry["cooldown"], 3.0)
            self.assertLessEqual(entry["cooldown"], 8.0)
            self.assertGreaterEqual(entry["cd_left"], 0)
            self.assertLessEqual(entry["cd_left"], entry["cooldown"])
            lo, hi = entry["damage"].split("–")
            self.assertGreaterEqual(int(lo), 1)
            self.assertGreaterEqual(int(hi), int(lo))

    def test_combat_events_snapshot(self):
        game = make_game(state="combat", combat_phase="fight")
        game.hero.equip(make_sword(damage_min=3, damage_max=3))
        combat = make_combat(game, make_mob(damage_min=0, damage_max=0,
                                            cooldown=99.0))
        ui = WebUI(game)
        # детерминированный кадр: вырожденный урон, крита нет, моб молчит
        events = combat.update(5.0)  # КД героя 5.0 — первая атака
        self.assertEqual(len(events), 1)
        ui.show_combat_events(events)
        block = snapshot(ui)["combat"]
        self.assertEqual(block["events"],
                         [{"seq": 1, "attacker": "hero", "target": "mob",
                           "damage": 3, "crit": False, "armor_absorbed": 0,
                           "target_hp": 17}])
        self.assertEqual(block["mob"]["hp"], 17)  # HP моба на плашке живое

    def test_publish_rereads_live_cooldowns(self):
        game = make_game(state="combat", combat_phase="fight")
        combat = make_combat(game, make_mob(damage_min=0, damage_max=0,
                                            cooldown=99.0))
        ui = WebUI(game)
        combat.update(2.0)  # без событий: КД тикают, атак ещё нет
        ui.show_combat_events([])
        block = snapshot(ui)["combat"]
        self.assertEqual(block["hero_cd"]["cd_left"], 3.0)
        self.assertEqual(block["mob"]["cd_left"], 97.0)

    def test_fresh_snapshot_extrapolates_cooldowns(self):
        game = make_game(state="combat", combat_phase="fight")
        combat = make_combat(game, make_mob(damage_min=0, damage_max=0,
                                            cooldown=99.0))
        combat.join("bob")
        ui = WebUI(game)
        ui.show_combat(combat, "fight")
        stored = snapshot(ui)["combat"]
        ui._published_at -= 2.0  # публикация была 2 с назад
        fresh = ui.fresh_snapshot()["combat"]
        self.assertEqual(fresh["hero_cd"]["cd_left"],
                         round(stored["hero_cd"]["cd_left"] - 2.0, 2))
        self.assertEqual(fresh["mob"]["cd_left"],
                         round(stored["mob"]["cd_left"] - 2.0, 2))
        self.assertEqual(
            fresh["squad"][0]["cd_left"],
            round(max(0.0, stored["squad"][0]["cd_left"] - 2.0), 2))
        self.assertEqual(snapshot(ui)["combat"], stored)  # стор не мутировал
        # большой возраст — кламп в 0
        ui._published_at -= 1000.0
        clamped = ui.fresh_snapshot()["combat"]
        self.assertEqual(clamped["hero_cd"]["cd_left"], 0)
        self.assertEqual(clamped["mob"]["cd_left"], 0)
        self.assertEqual(clamped["squad"][0]["cd_left"], 0)
        # вне боя — тот же объект, без копий
        ui.show_rest(game.hero)
        self.assertIs(ui.fresh_snapshot(), ui.snapshot)
        json.dumps(ui.fresh_snapshot(), ensure_ascii=False)  # сериализуем

    def test_events_queue_keeps_last_50(self):
        game = make_game(state="combat", combat_phase="fight")
        make_combat(game)
        ui = WebUI(game)
        events = [SimpleNamespace(seq=i, attacker="hero", target="mob",
                                  damage=1, crit=False, armor_absorbed=0,
                                  target_hp=100 - i)
                  for i in range(1, 61)]
        ui.show_combat_events(events)
        shown = snapshot(ui)["combat"]["events"]
        self.assertEqual(len(shown), 50)
        self.assertEqual([e["seq"] for e in shown], list(range(11, 61)))

    def test_update_votes_ignored_in_combat(self):
        game = make_game(state="combat", combat_phase="fight")
        make_combat(game)
        ui = WebUI(game)
        snap = ui.snapshot
        ui.update_votes({"1": 5}, ["1"])  # в бою голосований нет
        self.assertIs(ui.snapshot, snap)  # без републикации

    def test_combat_end_subphase_from_game(self):
        game = make_game(state="combat", combat_phase="fight",
                         time_left=5.0)
        make_combat(game)
        ui = WebUI(game)
        game.combat_phase = "end"  # Game входит в COMBAT_END без вызова ui
        game.time_left = 4.0
        ui.update_timer()
        block = snapshot(ui)["combat"]
        self.assertEqual(block["subphase"], "end")

    def test_new_combat_resets_block(self):
        game = make_game(state="combat", combat_phase="fight")
        combat1 = make_combat(game)
        ui = WebUI(game)
        combat1.join("bob")
        ui.show_combat(combat1, "fight")
        ui.show_combat_events(combat1.update(5.0))
        self.assertNotEqual(snapshot(ui)["combat"]["events"], [])

        combat2 = Combat(game.hero, make_mob(name="Скелет"), random.Random(2))
        game.combat = combat2
        ui.show_combat(combat2, "fight")
        block = snapshot(ui)["combat"]
        self.assertEqual(block["events"], [])
        self.assertEqual(block["squad"], [])
        self.assertEqual(block["mob"]["name"], "Скелет")

    def test_levelup_and_votes(self):
        game = make_game(state="levelup")
        game.hero.strength = 2
        ui = WebUI(game)
        s = snapshot(ui)
        self.assertEqual(s["phase"], "levelup")
        options = s["levelup"]["options"]
        self.assertEqual(len(options), 5)
        self.assertEqual(options[0], {"n": 1, "word": None, "key": "strength",
                                      "name": "Сила", "value": 2,
                                      "hint": "+1 к урону оружием",
                                      "votes": 0, "state": "idle"})
        self.assertEqual(options[1]["hint"], "−0.5 с к кулдауну атаки")
        self.assertEqual(options[4]["key"], "luck")

        ui.update_votes({"5": 3, "1": 1}, ["5"])
        options = snapshot(ui)["levelup"]["options"]
        self.assertEqual((options[4]["votes"], options[4]["state"]),
                         (3, "leader"))
        self.assertEqual(options[0]["state"], "active")

    def test_shop_items_and_votes(self):
        items = [make_sword(), make_armor()]
        ui = WebUI(make_game(state="shop", shop_items=items))
        s = snapshot(ui)
        self.assertEqual(s["phase"], "shop")
        shown = s["shop"]["items"]
        self.assertEqual([o["n"] for o in shown], [1, 2])
        self.assertEqual(shown[0], {"n": 1, "word": None, "icon": "🗡️",
                                    "label": "Меч",
                                    "slot_name": "ближнее",
                                    "detail": "урон 3–7",
                                    "current": "сейчас: Кулаки (урон 1–2)",
                                    "price": 15, "votes": 0,
                                    "state": "idle"})
        self.assertEqual(shown[1]["label"], "Кольчуга")
        self.assertEqual(shown[1]["slot_name"], "броня")
        self.assertEqual(shown[1]["detail"], "броня 2")
        self.assertEqual(shown[1]["current"], "сейчас: пусто")
        self.assertEqual(s["shop"]["exit"],
                         {"n": 0, "word": None, "label": "Выйти", "votes": 0,
                          "state": "idle"})

        ui.update_votes({"1": 2, "0": 1}, ["1"])
        shop = snapshot(ui)["shop"]
        self.assertEqual((shop["items"][0]["votes"],
                          shop["items"][0]["state"]), (2, "leader"))
        self.assertEqual(shop["items"][1]["state"], "idle")
        self.assertEqual((shop["exit"]["votes"], shop["exit"]["state"]),
                         (1, "active"))

    def test_rest_phase(self):
        game = make_game(state="rest")
        game.hero.hp = 5
        ui = WebUI(game)
        s = snapshot(ui)
        self.assertEqual(s["phase"], "rest")
        self.assertEqual(s["rest"], {})
        self.assertEqual(s["hero"]["hp"], 5)  # панель героя живая

    def test_gameover(self):
        summary = {"kills": 5, "gold_earned": 42,
                   "defeated": ["Гнусный viewer1"]}
        ui = WebUI(make_game(state="game_over", run_summary=summary,
                             deaths=2))
        s = snapshot(ui)
        self.assertEqual(s["phase"], "game_over")
        self.assertEqual(s["game_over"], summary)
        self.assertEqual(s["hero"]["deaths"], 2)  # счётчик и на панели героя

    def test_error(self):
        ui = WebUI(make_game(state="error", error_message="Пул мобов пуст"))
        s = snapshot(ui)
        self.assertEqual(s["phase"], "error")
        self.assertEqual(s["error"]["message"], "Пул мобов пуст")

    def test_timer_updates_only_on_second_change(self):
        game = make_game(time_left=10.0)
        ui = WebUI(game)
        self.assertEqual(snapshot(ui)["time_left"], 10)

        snap = ui.snapshot
        game.time_left = 9.6  # тот же показываемый секунд — без републикации
        ui.update_timer()
        self.assertIs(ui.snapshot, snap)

        game.time_left = 9.4
        ui.update_timer()
        self.assertIsNot(ui.snapshot, snap)
        self.assertEqual(snapshot(ui)["time_left"], 9)

    def test_overtime_flag_republishes_without_second_change(self):
        game = make_game(time_left=10.0)
        ui = WebUI(game)
        self.assertFalse(snapshot(ui)["overtime"])

        snap = ui.snapshot
        game.overtime = True  # 0 голосов — овертайм, таймер на странице мигает
        ui.update_timer()
        self.assertIsNot(ui.snapshot, snap)  # републикация без смены секунды
        self.assertTrue(snapshot(ui)["overtime"])

        snap = ui.snapshot
        game.overtime = False
        ui.update_timer()
        self.assertIsNot(ui.snapshot, snap)
        self.assertFalse(snapshot(ui)["overtime"])

    def test_snapshot_is_atomic(self):
        game = make_game(doors=[Door("mob", make_mob())])
        ui = WebUI(game)
        before = snapshot(ui)

        game.hero.hp = 7
        ui.update_votes({"1": 5}, ["1"])
        ui.show_error("позднее состояние")

        self.assertEqual(before["phase"], "event")
        self.assertEqual(before["hero"]["hp"], BASE_HP)
        self.assertEqual(before["event"]["doors"][0]["votes"], 0)
        self.assertEqual(snapshot(ui)["phase"], "error")

    def test_all_phases_json_serializable(self):
        game = make_game()
        ui = WebUI(game)
        ui.show_event([Door("mob", make_mob())])
        combat = Combat(game.hero, make_mob(), random.Random(1))
        game.combat = combat
        game.combat_phase = "fight"
        ui.show_combat(combat, "fight")
        snapshot(ui)
        ui.show_combat_events(combat.update(5.0))
        snapshot(ui)
        game.combat_phase = "end"
        ui.show_combat(combat, "end")
        snapshot(ui)
        ui.show_levelup(game.hero)
        snapshot(ui)
        ui.show_shop([make_sword(), make_armor()])
        snapshot(ui)
        ui.show_rest(game.hero)
        snapshot(ui)
        ui.show_gameover({"level": 1, "kills": 0, "gold_earned": 0})
        snapshot(ui)
        ui.show_error("ошибка")
        snapshot(ui)


if __name__ == "__main__":
    unittest.main()
