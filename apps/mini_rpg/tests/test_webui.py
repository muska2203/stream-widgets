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
                  combat=None, combat_phase="", last_turn=None,
                  shop_items=[], time_left=0.0, run_summary=None,
                  error_message="")
    fields.update(over)
    return SimpleNamespace(**fields)


def make_mob(**over) -> Mob:
    fields = dict(name="Гоблин", icon="👺", hp=20, damage_min=2,
                  damage_max=5, xp=8, gold=5)
    fields.update(over)
    return Mob(**fields)


def make_ranged(**over) -> Item:
    fields = dict(name="Короткий лук", icon="🏹", slot="ranged",
                  damage_min=3, damage_max=7, uses=5, armor=None, price=15)
    fields.update(over)
    return Item(**fields)


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
        self.assertEqual((hero["hp"], hero["max_hp"]), (BASE_HP, BASE_HP))
        self.assertEqual((hero["mana"], hero["max_mana"]), (0, 0))
        self.assertEqual([st["key"] for st in hero["stats"]],
                         ["strength", "agility", "intellect", "endurance",
                          "luck"])
        self.assertEqual(hero["stats"][0]["name"], "Сила")
        self.assertEqual(hero["stats"][4]["name"], "Удача")
        self.assertTrue(all(st["value"] == 0 for st in hero["stats"]))

        slots = hero["slots"]
        self.assertEqual(slots["melee"]["name"], "Кулаки")
        self.assertEqual(slots["melee"]["damage"], "1–2")
        self.assertIsNone(slots["ranged"])
        self.assertIsNone(slots["armor"])

    def test_event_doors_and_votes(self):
        doors = [Door("mob", make_mob(name="Гоблин")),
                 Door("mob", make_mob(name="Скелет", icon="💀")),
                 Door("shop"), ]
        ui = WebUI(make_game(doors=doors))
        s = snapshot(ui)
        self.assertEqual(s["phase"], "event")
        shown = s["event"]["doors"]
        self.assertEqual([d["n"] for d in shown], [1, 2, 3])
        self.assertEqual([d["name"] for d in shown],
                         ["Гоблин", "Скелет", "Магазин"])
        self.assertEqual(shown[1]["icon"], "💀")
        self.assertEqual(shown[2]["icon"], "🏪")  # иконка типа события
        self.assertEqual(shown[0]["threat"], "HP 20 · урон 2–5")
        self.assertIsNone(shown[2]["threat"])  # угроза только у моб-дверей
        self.assertTrue(all(d["votes"] == 0 and d["state"] == "idle"
                            for d in shown))

        ui.update_votes({"1": 2, "3": 1}, leader="1")
        shown = snapshot(ui)["event"]["doors"]
        self.assertEqual((shown[0]["votes"], shown[0]["state"]), (2, "leader"))
        self.assertEqual(shown[1]["state"], "idle")
        self.assertEqual((shown[2]["votes"], shown[2]["state"]), (1, "active"))

    def test_combat_attack_commands(self):
        game = make_game(state="combat", combat_phase="attack")
        combat = Combat(game.hero, make_mob(), random.Random(1))
        game.combat = combat
        ui = WebUI(game)
        s = snapshot(ui)
        self.assertEqual(s["phase"], "combat")
        self.assertEqual(s["combat"]["subphase"], "attack")
        self.assertEqual(s["combat"]["mob"],
                         {"icon": "👺", "name": "Гоблин", "hp": 20,
                          "max_hp": 20, "damage": "2–5"})
        commands = s["combat"]["commands"]
        self.assertEqual([c["n"] for c in commands], [1, 2, 3])
        self.assertEqual([c["label"] for c in commands],
                         ["Кулаки в голову", "Кулаки в тело",
                          "Кулаки в ноги"])
        self.assertEqual(commands[0]["icon"], "👊")
        self.assertEqual(commands[0]["detail"], "урон 1–2 +0 силы")

        game.hero.equip(make_ranged())
        ui.show_combat(combat, "attack")
        s = snapshot(ui)
        commands = s["combat"]["commands"]
        self.assertEqual(len(commands), 6)
        self.assertEqual(commands[3]["label"], "Короткий лук в голову")
        self.assertEqual(commands[3]["detail"],
                         "урон 3–7 +0 ловк. · зарядов: 5")
        self.assertEqual(commands[5]["label"], "Короткий лук в ноги")
        self.assertEqual(s["hero"]["slots"]["ranged"]["uses"], 5)

    def test_combat_defense_and_votes(self):
        game = make_game(state="combat", combat_phase="defense")
        game.combat = Combat(game.hero, make_mob(), random.Random(1))
        ui = WebUI(game)
        labels = [c["label"] for c in snapshot(ui)["combat"]["commands"]]
        self.assertEqual(labels, ["Защитить голову", "Защитить тело",
                                  "Защитить ноги"])

        ui.update_votes({"2": 4}, leader="2")
        commands = snapshot(ui)["combat"]["commands"]
        self.assertEqual((commands[1]["votes"], commands[1]["state"]),
                         (4, "leader"))

    def test_combat_outcome_hero_attack(self):
        game = make_game(state="combat", combat_phase="attack")
        combat = Combat(game.hero, make_mob(), random.Random(1))
        game.combat = combat
        ui = WebUI(game)

        result = combat.hero_turn("melee", "head")
        game.combat_phase = "outcome"
        game.last_turn = result
        ui.show_combat_outcome(result)
        block = snapshot(ui)["combat"]
        self.assertEqual(block["subphase"], "outcome")
        self.assertEqual(block["commands"], [])
        self.assertEqual(block["mob"]["hp"], combat.mob_hp)
        turn = block["turn"]
        self.assertEqual(turn["actor"], "hero")
        self.assertEqual(turn["weapon_label"], "Кулаки")
        self.assertEqual(turn["direction_name"], "голова")
        self.assertEqual(turn["target_hp"], combat.mob_hp)
        self.assertFalse(turn["crit"])

    def test_combat_outcome_mob_attack(self):
        game = make_game(state="combat", combat_phase="defense")
        combat = Combat(game.hero, make_mob(), random.Random(1))
        game.combat = combat
        ui = WebUI(game)

        result = combat.mob_turn("head")
        game.combat_phase = "outcome"
        ui.show_combat_outcome(result)
        turn = snapshot(ui)["combat"]["turn"]
        self.assertEqual(turn["actor"], "mob")
        self.assertIsNone(turn["weapon"])
        self.assertIsNone(turn["weapon_label"])
        self.assertEqual(turn["armor"], 0)  # броня героя для строки итога
        self.assertEqual(turn["target_hp"], game.hero.hp)
        self.assertEqual(snapshot(ui)["hero"]["hp"], game.hero.hp)

    def test_combat_end_subphase_from_game(self):
        game = make_game(state="combat", combat_phase="attack",
                         time_left=5.0)
        game.combat = Combat(game.hero, make_mob(), random.Random(1))
        ui = WebUI(game)
        game.combat_phase = "end"  # Game входит в COMBAT_END без вызова ui
        game.time_left = 4.0
        ui.update_timer()
        block = snapshot(ui)["combat"]
        self.assertEqual(block["subphase"], "end")
        self.assertEqual(block["commands"], [])

    def test_new_combat_resets_turn(self):
        game = make_game(state="combat", combat_phase="attack")
        combat1 = Combat(game.hero, make_mob(), random.Random(1))
        game.combat = combat1
        ui = WebUI(game)
        result = combat1.hero_turn("melee", "head")
        game.combat_phase = "outcome"
        ui.show_combat_outcome(result)
        self.assertIsNotNone(snapshot(ui)["combat"]["turn"])

        combat2 = Combat(game.hero, make_mob(name="Скелет"), random.Random(2))
        game.combat = combat2
        game.combat_phase = "attack"
        ui.show_combat(combat2, "attack")
        block = snapshot(ui)["combat"]
        self.assertIsNone(block["turn"])
        self.assertEqual(block["mob"]["name"], "Скелет")

    def test_levelup_and_votes(self):
        game = make_game(state="levelup")
        game.hero.strength = 2
        ui = WebUI(game)
        s = snapshot(ui)
        self.assertEqual(s["phase"], "levelup")
        options = s["levelup"]["options"]
        self.assertEqual(len(options), 5)
        self.assertEqual(options[0], {"n": 1, "key": "strength",
                                      "name": "Сила", "value": 2,
                                      "hint": "+1 к урону ближним оружием",
                                      "votes": 0, "state": "idle"})
        self.assertEqual(options[4]["key"], "luck")

        ui.update_votes({"5": 3, "1": 1}, leader="5")
        options = snapshot(ui)["levelup"]["options"]
        self.assertEqual((options[4]["votes"], options[4]["state"]),
                         (3, "leader"))
        self.assertEqual(options[0]["state"], "active")

    def test_shop_items_and_votes(self):
        items = [make_ranged(),
                 Item(name="Кольчуга", icon="🛡️", slot="armor",
                      damage_min=None, damage_max=None, uses=None, armor=2,
                      price=20)]
        ui = WebUI(make_game(state="shop", shop_items=items))
        s = snapshot(ui)
        self.assertEqual(s["phase"], "shop")
        shown = s["shop"]["items"]
        self.assertEqual([o["n"] for o in shown], [1, 2])
        self.assertEqual(shown[0], {"n": 1, "icon": "🏹",
                                    "label": "Короткий лук",
                                    "slot_name": "дальнее",
                                    "detail": "урон 3–7, зарядов: 5",
                                    "current": "сейчас: пусто",
                                    "price": 15, "votes": 0,
                                    "state": "idle"})
        self.assertEqual(shown[1]["label"], "Кольчуга")
        self.assertEqual(shown[1]["slot_name"], "броня")
        self.assertEqual(shown[1]["detail"], "−2 урона")
        self.assertEqual(s["shop"]["exit"],
                         {"n": 0, "label": "Выйти", "votes": 0,
                          "state": "idle"})

        ui.update_votes({"1": 2, "0": 1}, leader="1")
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
        summary = {"level": 3, "kills": 5, "gold_earned": 42}
        ui = WebUI(make_game(state="game_over", run_summary=summary))
        s = snapshot(ui)
        self.assertEqual(s["phase"], "game_over")
        self.assertEqual(s["game_over"], summary)

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

    def test_snapshot_is_atomic(self):
        game = make_game(doors=[Door("mob", make_mob())])
        ui = WebUI(game)
        before = snapshot(ui)

        game.hero.hp = 7
        ui.update_votes({"1": 5}, leader="1")
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
        game.combat_phase = "attack"
        ui.show_combat(combat, "attack")
        snapshot(ui)
        game.combat_phase = "outcome"
        ui.show_combat_outcome(combat.hero_turn("melee", "head"))
        snapshot(ui)
        ui.show_levelup(game.hero)
        snapshot(ui)
        ui.show_shop([make_ranged()])
        snapshot(ui)
        ui.show_rest(game.hero)
        snapshot(ui)
        ui.show_gameover({"level": 1, "kills": 0, "gold_earned": 0})
        snapshot(ui)
        ui.show_error("ошибка")
        snapshot(ui)


if __name__ == "__main__":
    unittest.main()
