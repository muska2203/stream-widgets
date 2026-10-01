"""Overlay state model for the web UI (OBS Browser Source).

Same duck-typed interface as the old ursina StoryUI: the Game calls
set_header / show_select / show_move / show_options / update_votes /
show_outcome / enter_sleep / show_ending, and WebUI folds each call into
a plain JSON-serializable dict. The current dict is published by an
atomic reference swap (`_snapshot`), so the HTTP handler threads in
`server.py` can read it without locks.

Phases: select | move | sleep | end | error (mirrors docs/DESIGN.md).
"""

from __future__ import annotations

import copy
from typing import Any

PHASE_SELECT = "select"
PHASE_MOVE = "move"
PHASE_SLEEP = "sleep"
PHASE_END = "end"
PHASE_ERROR = "error"

OPT_IDLE = "idle"
OPT_ACTIVE = "active"
OPT_LEADER = "leader"
OPT_CHOSEN = "chosen"


def _option(n: int, label: str) -> dict[str, Any]:
    return {"n": n, "label": label, "votes": 0, "state": OPT_IDLE}


class WebUI:
    def __init__(self):
        self._state: dict[str, Any] = {
            "phase": PHASE_SELECT,
            "header": "",
            "scene": "",
            "options": [],
            "result": "",
            "ending": {"label": "", "text": ""},
            "select": {"title": "", "message": "", "items": []},
        }
        self._snapshot = copy.deepcopy(self._state)

    @property
    def snapshot(self) -> dict[str, Any]:
        """Last published state; safe to read from other threads."""
        return self._snapshot

    def _publish(self) -> None:
        self._snapshot = copy.deepcopy(self._state)

    # --- generic ---------------------------------------------------------

    def set_visible(self, visible: bool) -> None:
        # Окна больше нет: контент всегда «виден», фазы решают, что
        # показывать. Оставлено для совместимости интерфейса с Game.
        pass

    def relayout(self) -> None:
        pass

    def set_header(self, text: str) -> None:
        if text != self._state["header"]:
            self._state["header"] = text
            self._publish()

    # --- story select ----------------------------------------------------

    def show_select(self, stories) -> None:
        self._state["phase"] = PHASE_SELECT
        self._state["select"] = {
            "title": "Выберите историю — пишите цифру в чат",
            "message": "",
            "items": [_option(i + 1, s.title if not s.description
                              else f"{s.title} — {s.description}")
                      for i, s in enumerate(stories)],
        }
        self._publish()

    def update_select_votes(self, counts: dict[str, int],
                            leader: str | None) -> None:
        self._apply_votes(self._state["select"]["items"], counts, leader)

    def show_select_error(self, message: str) -> None:
        self._state["phase"] = PHASE_ERROR
        self._state["select"] = {"title": "", "message": message, "items": []}
        self._publish()

    # --- move ------------------------------------------------------------

    def show_move(self, scene_text: str) -> None:
        self._state["phase"] = PHASE_MOVE
        self._state["scene"] = scene_text
        self._state["options"] = []
        self._state["result"] = ""
        self._publish()

    def show_options(self, labels: list[str]) -> None:
        self._state["options"] = [_option(i + 1, label)
                                  for i, label in enumerate(labels)]
        self._publish()

    def hide_options(self) -> None:
        if self._state["options"]:
            self._state["options"] = []
            self._publish()

    def update_votes(self, counts: dict[str, int], leader: str | None) -> None:
        self._apply_votes(self._state["options"], counts, leader)

    def show_outcome(self, winner_idx: int, result_text: str) -> None:
        options = self._state["options"]
        if 0 <= winner_idx < len(options):
            options[winner_idx]["state"] = OPT_CHOSEN
        self._state["result"] = result_text
        self._publish()

    def enter_sleep(self) -> None:
        self._state["phase"] = PHASE_SLEEP
        self._state["scene"] = ""
        self._state["options"] = []
        self._publish()

    # --- ending ----------------------------------------------------------

    def show_ending(self, label: str, text: str) -> None:
        self._state["phase"] = PHASE_END
        self._state["ending"] = {"label": label, "text": text}
        self._state["options"] = []
        self._publish()

    # --- helpers -----------------------------------------------------------

    def _apply_votes(self, items: list[dict[str, Any]],
                     counts: dict[str, int], leader: str | None) -> None:
        changed = False
        for opt in items:
            digit = str(opt["n"])
            votes = counts.get(digit, 0)
            state = (OPT_LEADER if digit == leader and leader is not None
                     else OPT_ACTIVE if votes
                     else OPT_IDLE)
            if opt["votes"] != votes or opt["state"] != state:
                opt["votes"] = votes
                opt["state"] = state
                changed = True
        if changed:
            self._publish()
