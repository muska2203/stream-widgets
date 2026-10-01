"""WebUI (модель состояния оверлея) и OverlayServer: переходы фаз,
JSON-снапшот, отдача страницы и состояния по HTTP. Headless."""

from __future__ import annotations

import json
import unittest
import urllib.request
from types import SimpleNamespace

from apps.interactive_story.server import OverlayServer
from apps.interactive_story.webui import WebUI

STORIES = [
    SimpleNamespace(title="Ночной обоз", description="Соль и лес"),
    SimpleNamespace(title="Станция-13", description=""),
]


def snapshot(ui: WebUI) -> dict:
    # JSON-сериализуемость — часть контракта
    return json.loads(json.dumps(ui.snapshot, ensure_ascii=False))


class WebUITest(unittest.TestCase):
    def test_initial_state(self):
        s = snapshot(WebUI())
        self.assertEqual(s["phase"], "select")
        self.assertEqual(s["options"], [])

    def test_select_flow(self):
        ui = WebUI()
        ui.show_select(STORIES)
        s = snapshot(ui)
        self.assertEqual(s["phase"], "select")
        self.assertEqual(len(s["select"]["items"]), 2)
        self.assertEqual(s["select"]["items"][0]["label"],
                         "Ночной обоз — Соль и лес")
        self.assertEqual(s["select"]["items"][1]["label"], "Станция-13")

        ui.update_select_votes({"1": 3, "2": 1}, leader="1")
        items = snapshot(ui)["select"]["items"]
        self.assertEqual(items[0]["votes"], 3)
        self.assertEqual(items[0]["state"], "leader")
        self.assertEqual(items[1]["state"], "active")

    def test_select_error(self):
        ui = WebUI()
        ui.show_select_error("Нет историй")
        s = snapshot(ui)
        self.assertEqual(s["phase"], "error")
        self.assertEqual(s["select"]["message"], "Нет историй")

    def test_move_outcome_sleep_cycle(self):
        ui = WebUI()
        ui.show_move("Текст сцены.")
        s = snapshot(ui)
        self.assertEqual(s["phase"], "move")
        self.assertEqual(s["scene"], "Текст сцены.")
        self.assertEqual(s["options"], [])

        ui.show_options(["Пойти влево", "Пойти вправо"])
        ui.update_votes({"1": 2, "2": 5}, leader="2")
        opts = snapshot(ui)["options"]
        self.assertEqual(opts[0]["state"], "active")
        self.assertEqual(opts[1]["state"], "leader")
        self.assertEqual(opts[1]["votes"], 5)

        ui.show_outcome(1, "Вы пошли вправо.")
        s = snapshot(ui)
        self.assertEqual(s["phase"], "move")  # итог виден только во сне
        self.assertEqual(s["options"][1]["state"], "chosen")
        self.assertEqual(s["result"], "Вы пошли вправо.")

        ui.enter_sleep()
        s = snapshot(ui)
        self.assertEqual(s["phase"], "sleep")
        self.assertEqual(s["options"], [])
        self.assertEqual(s["scene"], "")
        self.assertEqual(s["result"], "Вы пошли вправо.")

    def test_ending_and_header(self):
        ui = WebUI()
        ui.show_ending("Хорошая концовка", "Финальный текст.")
        s = snapshot(ui)
        self.assertEqual(s["phase"], "end")
        self.assertEqual(s["ending"]["label"], "Хорошая концовка")

        ui.set_header("«Ночной обоз» · Ход 2 · 7")
        self.assertEqual(snapshot(ui)["header"], "«Ночной обоз» · Ход 2 · 7")


class OverlayServerTest(unittest.TestCase):
    def test_serves_page_and_state(self):
        ui = WebUI()
        ui.show_move("Сцена для сервера.")
        server = OverlayServer(ui, port=0)  # эфемерный порт
        try:
            with urllib.request.urlopen(server.url + "/") as r:
                html = r.read().decode("utf-8")
            self.assertIn("state.json", html)

            with urllib.request.urlopen(server.url + "/state.json") as r:
                state = json.loads(r.read().decode("utf-8"))
            self.assertEqual(state["phase"], "move")
            self.assertEqual(state["scene"], "Сцена для сервера.")

            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(server.url + "/nope")
            self.assertEqual(ctx.exception.code, 404)
            ctx.exception.close()
        finally:
            server.stop()


if __name__ == "__main__":
    unittest.main()
