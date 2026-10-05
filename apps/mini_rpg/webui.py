"""Overlay state model for the web UI (OBS Browser Source).

Implements the NullUI listener interface from game.py: the Game calls
show_event / show_combat / show_combat_events / show_shop / show_rest /
show_levelup / show_gameover / show_error / update_votes / update_timer,
and WebUI folds each call into a plain JSON-serializable dict. The current
dict is published by an atomic reference swap (`_snapshot`), so the HTTP
handler threads in `server.py` (этап 7) can read it without locks.

WebUI keeps a reference to the Game and re-reads the volatile parts
(hero panel, phase timer, combat sub-phase, mob HP, cooldowns) at publish
time. The timer ticks every frame: Game.update() pushes it via
update_timer(), which republishes only when the displayed second changes —
same pattern as the story's set_header. In the FIGHT sub-phase there is no
phase timer (time_left is frozen at 0): publishes come from combat events
and squad joins.

Phases: event | combat | shop | rest | levelup | game_over | error
(mirrors game.py).
"""

from __future__ import annotations

import copy
import time
from typing import Any

from apps.mini_rpg.core import STATS

PHASE_EVENT = "event"
PHASE_COMBAT = "combat"
PHASE_SHOP = "shop"
PHASE_REST = "rest"
PHASE_LEVELUP = "levelup"
PHASE_GAME_OVER = "game_over"
PHASE_ERROR = "error"

# combat sub-phases (mirror game.py)
FIGHT, COMBAT_END = "fight", "end"

OPT_IDLE = "idle"
OPT_ACTIVE = "active"
OPT_LEADER = "leader"

# сколько последних боевых событий хранится в снапшоте
MAX_COMBAT_EVENTS = 50

STAT_NAMES = {
    "strength": "Сила",
    "agility": "Ловкость",
    "intellect": "Интеллект",
    "endurance": "Выносливость",
    "luck": "Удача",
}
STAT_HINTS = {
    "strength": "+1 к урону оружием",
    "agility": "−0.5 с к кулдауну атаки",
    "intellect": "+5 к макс. мане",
    "endurance": "+5 к макс. HP (текущее HP тоже +5)",
    "luck": "+2% к шансу крита (крит ×2)",
}
SLOT_NAMES = {"melee": "Ближнее оружие", "armor": "Броня"}
SHORT_SLOT_NAMES = {"melee": "ближнее", "armor": "броня"}


def _option(n: int, label: str, word: str | None = None) -> dict[str, Any]:
    return {"n": n, "word": word, "label": label, "votes": 0,
            "state": OPT_IDLE}


def _slot_view(item, slot: str) -> dict[str, Any] | None:
    if item is None:
        return None
    view = {"slot": slot, "slot_name": SLOT_NAMES[slot],
            "icon": item.icon, "name": item.name}
    if slot == "melee":
        view["damage"] = f"{item.damage_min}–{item.damage_max}"
    if slot == "armor":
        view["armor"] = item.armor
    return view


def _item_detail(item) -> str:
    if item.slot == "melee":
        return f"урон {item.damage_min}–{item.damage_max}"
    return f"броня {item.armor}"


class WebUI:
    def __init__(self, game):
        self.game = game
        self._state: dict[str, Any] = {
            "phase": PHASE_EVENT,
            "event": {"doors": []},
            "combat": {"subphase": "", "mob": None, "hero_cd": None,
                       "squad": [], "events": []},
            "shop": {"items": [], "exit": _option(0, "Выйти")},
            "rest": {},
            "levelup": {"options": []},
            "game_over": {"kills": 0, "gold_earned": 0, "defeated": []},
            "error": {"message": ""},
            # ничья: рулетка среди лидеров (None вне тай-брейка)
            "resolve": None,
        }
        self._combat = None  # последний показанный Combat (сброс на новом)
        self._published_seconds: int | None = None
        self._published_overtime: bool | None = None
        self._published_at = 0.0  # monotonic момент последней публикации
        self._snapshot: dict[str, Any] = {}
        self.refresh()  # Game уже мог войти в первую фазу до подключения UI

    def _words(self) -> dict[str, str]:
        """Ключ -> слово-алиас текущего голосования (Game._assign_words)."""
        return getattr(self.game, "vote_key_words", None) or {}

    @property
    def snapshot(self) -> dict[str, Any]:
        """Last published state; safe to read from other threads."""
        return self._snapshot

    def fresh_snapshot(self) -> dict[str, Any]:
        """Snapshot for serving over HTTP: combat cooldowns extrapolated
        to NOW. Publishes in a fight are event-driven (no phase timer), so
        raw cd_left in the last published snapshot goes stale between
        events; a client resyncing against it saw the countdown jump back.
        Cooldowns tick in real time, so subtracting the publish age is
        exact (clamped at 0; a finished combat freezes server-side anyway).
        The stored snapshot is not mutated — copies are made on the path."""
        snap = self._snapshot
        combat = snap.get("combat")
        if snap.get("phase") != PHASE_COMBAT or not combat:
            return snap
        age = time.monotonic() - self._published_at
        if age <= 0:
            return snap
        snap = dict(snap)
        combat = dict(combat)
        snap["combat"] = combat
        if combat.get("mob") is not None:
            mob = dict(combat["mob"])
            mob["cd_left"] = round(max(0.0, mob["cd_left"] - age), 2)
            combat["mob"] = mob
        if combat.get("hero_cd") is not None:
            hero_cd = dict(combat["hero_cd"])
            hero_cd["cd_left"] = round(max(0.0, hero_cd["cd_left"] - age), 2)
            combat["hero_cd"] = hero_cd
        combat["squad"] = [
            {**u, "cd_left": round(max(0.0, u["cd_left"] - age), 2)}
            for u in combat.get("squad", [])]
        return snap

    def refresh(self) -> None:
        """Rebuild the snapshot from the current Game state."""
        g = self.game
        if g.state == PHASE_EVENT:
            self.show_event(g.doors)
        elif g.state == PHASE_COMBAT and g.combat is not None:
            self.show_combat(g.combat, g.combat_phase)
        elif g.state == PHASE_SHOP:
            self.show_shop(g.shop_items)
        elif g.state == PHASE_REST:
            self.show_rest(g.hero)
        elif g.state == PHASE_LEVELUP:
            self.show_levelup(g.hero)
        elif g.state == PHASE_GAME_OVER:
            self.show_gameover(g.run_summary or {})
        elif g.state == PHASE_ERROR:
            self.show_error(g.error_message)
        else:
            self._publish()

    # --- phase calls (NullUI interface) -----------------------------------

    def show_event(self, doors) -> None:
        words = self._words()
        self._state["phase"] = PHASE_EVENT
        self._state["event"] = {"doors": [
            {"n": i + 1, "word": words.get(str(i + 1)), "icon": d.icon,
             "name": d.name,
             "threat": (f"HP {d.mob.hp} · урон "
                        f"{d.mob.damage_min}–{d.mob.damage_max}"
                        if d.mob is not None else None),
             "votes": 0, "state": OPT_IDLE}
            for i, d in enumerate(doors)]}
        self._publish()

    def show_combat(self, combat, phase: str) -> None:
        if combat is not self._combat:  # новый бой — сбросить блок целиком
            self._combat = combat
            self._state["combat"] = {"subphase": "", "mob": None,
                                     "hero_cd": None, "squad": [],
                                     "events": []}
        self._state["phase"] = PHASE_COMBAT
        block = self._state["combat"]
        block["subphase"] = phase
        block["mob"] = {"icon": combat.mob.icon, "name": combat.mob.name,
                        "hp": combat.mob_hp, "max_hp": combat.mob.hp,
                        "damage": f"{combat.mob.damage_min}–"
                                  f"{combat.mob.damage_max}",
                        "cooldown": combat.mob.cooldown,
                        "cd_left": round(combat.mob_cd_left, 2)}
        block["hero_cd"] = {"cooldown": round(combat.hero_cd, 2),
                            "cd_left": round(combat.hero_cd_left, 2)}
        block["squad"] = [self._squad_entry(u) for u in combat.squad]
        self._publish()

    def show_combat_events(self, events) -> None:
        """Append the frame's combat events to the snapshot queue (last
        MAX_COMBAT_EVENTS kept) and republish."""
        self._state["phase"] = PHASE_COMBAT
        block = self._state["combat"]
        block["events"].extend(
            {"seq": e.seq, "attacker": e.attacker, "target": e.target,
             "damage": e.damage, "crit": e.crit,
             "armor_absorbed": e.armor_absorbed, "target_hp": e.target_hp}
            for e in events)
        del block["events"][:-MAX_COMBAT_EVENTS]
        self._publish()

    @staticmethod
    def _squad_entry(unit) -> dict[str, Any]:
        return {"nick": unit.nick, "emoji": unit.emoji,
                "damage": f"{unit.damage_min}–{unit.damage_max}",
                "cooldown": round(unit.cooldown, 2),
                "cd_left": round(unit.cd_left, 2), "active": unit.active}

    def _shop_item(self, item, n: int, word: str | None) -> dict[str, Any]:
        hero = self.game.hero
        equipped = getattr(hero, item.slot, None) if hero else None
        current = (f"сейчас: {equipped.name} ({_item_detail(equipped)})"
                   if equipped is not None else "сейчас: пусто")
        return {"n": n, "word": word, "icon": item.icon, "label": item.name,
                "slot_name": SHORT_SLOT_NAMES[item.slot],
                "detail": _item_detail(item), "current": current,
                "price": item.price, "votes": 0, "state": OPT_IDLE}

    def show_shop(self, items) -> None:
        words = self._words()
        self._state["phase"] = PHASE_SHOP
        self._state["shop"] = {
            "items": [self._shop_item(item, i + 1, words.get(str(i + 1)))
                      for i, item in enumerate(items)],
            "exit": _option(0, "Выйти", words.get("0"))}
        self._publish()

    def show_rest(self, hero) -> None:
        self._state["phase"] = PHASE_REST
        self._state["rest"] = {}
        self._publish()

    def show_levelup(self, hero) -> None:
        words = self._words()
        self._state["phase"] = PHASE_LEVELUP
        self._state["levelup"] = {"options": [
            {"n": i + 1, "word": words.get(str(i + 1)), "key": stat,
             "name": STAT_NAMES[stat],
             "value": getattr(hero, stat), "hint": STAT_HINTS[stat],
             "votes": 0, "state": OPT_IDLE}
            for i, stat in enumerate(STATS)]}
        self._publish()

    def show_gameover(self, summary: dict) -> None:
        self._state["phase"] = PHASE_GAME_OVER
        self._state["game_over"] = dict(summary)
        self._publish()

    def show_error(self, message: str) -> None:
        self._state["phase"] = PHASE_ERROR
        self._state["error"] = {"message": message}
        self._publish()

    # --- per-frame updates ---------------------------------------------------

    def update_votes(self, counts: dict[str, int], leaders: list[str]) -> None:
        phase = self._state["phase"]
        if phase == PHASE_EVENT:
            items = self._state["event"]["doors"]
        elif phase == PHASE_SHOP:
            shop = self._state["shop"]
            items = shop["items"] + [shop["exit"]]
        elif phase == PHASE_LEVELUP:
            items = self._state["levelup"]["options"]
        else:
            return
        self._apply_votes(items, counts, leaders)

    def show_tie_resolve(self, leaders: list[str], winner: str) -> None:
        """Ничья: один снапшот с блоком resolve — оверлей запускает рулетку
        (Game держит фазу на tie_resolve_pause и применяет winner после).
        Блок живёт ровно одну публикацию: повторная ничья с тем же составом
        должна перезапускать анимацию."""
        self._state["resolve"] = {"leaders": leaders, "winner": winner,
                                  "duration": self.game.time_left}
        self._publish()
        self._state["resolve"] = None

    def update_timer(self) -> None:
        """Called by Game.update() every frame; republishes when the
        displayed second or the overtime flag changes."""
        if (self._seconds() != self._published_seconds
                or self._overtime() != self._published_overtime):
            self._publish()

    # --- helpers -----------------------------------------------------------

    def _publish(self) -> None:
        snap = copy.deepcopy(self._state)
        snap["hero"] = self._hero_panel()
        snap["time_left"] = self._seconds()
        # овертайм голосования (0 голосов): таймер на странице мигает
        snap["overtime"] = self._overtime()
        if snap["phase"] == PHASE_COMBAT and self.game.combat is not None:
            combat = self.game.combat
            block = snap["combat"]
            block["subphase"] = self.game.combat_phase
            if block["mob"] is not None:
                block["mob"]["hp"] = combat.mob_hp
                block["mob"]["cd_left"] = round(combat.mob_cd_left, 2)
            if block["hero_cd"] is not None:
                block["hero_cd"]["cd_left"] = round(combat.hero_cd_left, 2)
            live = {u.nick: u for u in combat.squad}
            for entry in block["squad"]:
                unit = live.get(entry["nick"])
                if unit is not None:
                    entry["cd_left"] = round(unit.cd_left, 2)
        self._published_seconds = snap["time_left"]
        self._published_overtime = snap["overtime"]
        self._published_at = time.monotonic()
        self._snapshot = snap

    def _seconds(self) -> int:
        return max(0, int(self.game.time_left + 0.5))

    def _overtime(self) -> bool:
        return bool(getattr(self.game, "overtime", False))

    def _hero_panel(self) -> dict[str, Any] | None:
        hero = self.game.hero
        if hero is None:
            return None
        return {
            "level": hero.level,
            "xp": hero.xp,
            "xp_to_next": hero.xp_to_next,
            "gold": hero.gold,
            "hp": hero.hp,
            "max_hp": hero.max_hp,
            "mana": hero.mana,
            "max_mana": hero.max_mana,
            # getattr: headless-тесты подменяют игру SimpleNamespace
            "deaths": getattr(self.game, "deaths", 0),
            "stats": [{"key": s, "name": STAT_NAMES[s],
                       "value": getattr(hero, s)} for s in STATS],
            "slots": {slot: _slot_view(getattr(hero, slot), slot)
                      for slot in ("melee", "armor")},
        }

    def _apply_votes(self, items: list[dict[str, Any]],
                     counts: dict[str, int], leaders: list[str]) -> None:
        changed = False
        for opt in items:
            digit = str(opt["n"])
            votes = counts.get(digit, 0)
            state = (OPT_LEADER if digit in leaders
                     else OPT_ACTIVE if votes
                     else OPT_IDLE)
            if opt["votes"] != votes or opt["state"] != state:
                opt["votes"] = votes
                opt["state"] = state
                changed = True
        if changed:
            self._publish()
