"""Overlay state model for the web UI (OBS Browser Source).

Implements the NullUI listener interface from game.py: the Game calls
show_event / show_combat / show_combat_outcome / show_shop / show_rest /
show_levelup / show_gameover / show_error / update_votes / update_timer,
and WebUI folds each call into a plain JSON-serializable dict. The current
dict is published by an atomic reference swap (`_snapshot`), so the HTTP
handler threads in `server.py` (этап 7) can read it without locks.

WebUI keeps a reference to the Game and re-reads the volatile parts
(hero panel, phase timer, combat sub-phase, mob HP) at publish time.
The timer ticks every frame: Game.update() pushes it via update_timer(),
which republishes only when the displayed second changes — same pattern
as the story's set_header.

Phases: event | combat | shop | rest | levelup | game_over | error
(mirrors game.py).
"""

from __future__ import annotations

import copy
from typing import Any

from apps.mini_rpg.core import (DAMAGE_STAT, DIRECTIONS, STATS, WEAPON_SLOTS,
                                defense_choice)

PHASE_EVENT = "event"
PHASE_COMBAT = "combat"
PHASE_SHOP = "shop"
PHASE_REST = "rest"
PHASE_LEVELUP = "levelup"
PHASE_GAME_OVER = "game_over"
PHASE_ERROR = "error"

# combat sub-phases (mirror game.py)
ATTACK, DEFENSE, OUTCOME, COMBAT_END = "attack", "defense", "outcome", "end"

OPT_IDLE = "idle"
OPT_ACTIVE = "active"
OPT_LEADER = "leader"

STAT_NAMES = {
    "strength": "Сила",
    "agility": "Ловкость",
    "intellect": "Интеллект",
    "endurance": "Выносливость",
    "luck": "Удача",
}
STAT_HINTS = {
    "strength": "+1 к урону ближним оружием",
    "agility": "+1 к урону дальним оружием",
    "intellect": "+5 к макс. мане",
    "endurance": "+5 к макс. HP (текущее HP тоже +5)",
    "luck": "+2% к шансу крита (крит ×2)",
}
STAT_GEN = {"strength": "силы", "agility": "ловк."}
DIRECTION_NAMES = {"head": "голова", "body": "тело", "legs": "ноги"}
DIRECTION_ACC = {"head": "голову", "body": "тело", "legs": "ноги"}
WEAPON_NAMES = {"melee": "ближнее", "ranged": "дальнее"}
SLOT_NAMES = {"melee": "Ближнее оружие", "ranged": "Дальнее оружие",
              "armor": "Броня"}
SHORT_SLOT_NAMES = {"melee": "ближнее", "ranged": "дальнее",
                    "armor": "броня"}


def _option(n: int, label: str) -> dict[str, Any]:
    return {"n": n, "label": label, "votes": 0, "state": OPT_IDLE}


def _attack_commands(hero) -> list[dict[str, Any]]:
    """Команды 1–6: 1–3 ближнее, 4–6 дальнее (если есть) — нумерация
    совпадает с attack_choice из core.choices. У каждой готовые label
    («Короткий лук в голову») и detail (урон + бонус статы, заряды)."""
    commands = []
    n = 0
    for slot in WEAPON_SLOTS:
        weapon = getattr(hero, slot) if hero is not None else None
        if weapon is None:
            continue
        stat = getattr(hero, DAMAGE_STAT[slot])
        for direction in DIRECTIONS:
            n += 1
            detail = (f"урон {weapon.damage_min}–{weapon.damage_max} "
                      f"+{stat} {STAT_GEN[DAMAGE_STAT[slot]]}")
            if slot == "ranged":
                detail += f" · зарядов: {weapon.uses}"
            commands.append({"n": n, "icon": weapon.icon,
                             "label": f"{weapon.name} "
                                      f"в {DIRECTION_ACC[direction]}",
                             "detail": detail, "votes": 0,
                             "state": OPT_IDLE})
    return commands


def _defense_commands() -> list[dict[str, Any]]:
    return [_option(n, f"Защитить {DIRECTION_ACC[defense_choice(str(n))]}")
            for n in (1, 2, 3)]


def _slot_view(item, slot: str) -> dict[str, Any] | None:
    if item is None:
        return None
    view = {"slot": slot, "slot_name": SLOT_NAMES[slot],
            "icon": item.icon, "name": item.name}
    if slot in WEAPON_SLOTS:
        view["damage"] = f"{item.damage_min}–{item.damage_max}"
    if slot == "ranged":
        view["uses"] = item.uses
    if slot == "armor":
        view["armor"] = item.armor
    return view


def _item_detail(item) -> str:
    parts = []
    if item.slot in WEAPON_SLOTS:
        parts.append(f"урон {item.damage_min}–{item.damage_max}")
    if item.slot == "ranged":
        parts.append(f"зарядов: {item.uses}")
    if item.slot == "armor":
        parts.append(f"−{item.armor} урона")
    return ", ".join(parts)


class WebUI:
    def __init__(self, game):
        self.game = game
        self._state: dict[str, Any] = {
            "phase": PHASE_EVENT,
            "event": {"doors": []},
            "combat": {"subphase": "", "mob": None, "commands": [],
                       "turn": None},
            "shop": {"items": [], "exit": _option(0, "Выйти")},
            "rest": {},
            "levelup": {"options": []},
            "game_over": {"level": 0, "kills": 0, "gold_earned": 0,
                          "defeated": []},
            "error": {"message": ""},
            # ничья: рулетка среди лидеров (None вне тай-брейка)
            "resolve": None,
        }
        self._combat = None  # последний показанный Combat (сброс turn на новом)
        self._published_seconds: int | None = None
        self._snapshot: dict[str, Any] = {}
        self.refresh()  # Game уже мог войти в первую фазу до подключения UI

    @property
    def snapshot(self) -> dict[str, Any]:
        """Last published state; safe to read from other threads."""
        return self._snapshot

    def refresh(self) -> None:
        """Rebuild the snapshot from the current Game state."""
        g = self.game
        if g.state == PHASE_EVENT:
            self.show_event(g.doors)
        elif g.state == PHASE_COMBAT and g.combat is not None:
            self.show_combat(g.combat, g.combat_phase)
            if g.combat_phase in (OUTCOME, COMBAT_END) and g.last_turn:
                self.show_combat_outcome(g.last_turn)
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
        self._state["phase"] = PHASE_EVENT
        self._state["event"] = {"doors": [
            {"n": i + 1, "icon": d.icon, "name": d.name,
             "threat": (f"HP {d.mob.hp} · урон "
                        f"{d.mob.damage_min}–{d.mob.damage_max}"
                        if d.mob is not None else None),
             "votes": 0, "state": OPT_IDLE}
            for i, d in enumerate(doors)]}
        self._publish()

    def show_combat(self, combat, phase: str) -> None:
        if combat is not self._combat:  # новый бой — сбросить итог прошлого
            self._combat = combat
            self._state["combat"] = {"subphase": "", "mob": None,
                                     "commands": [], "turn": None}
        self._state["phase"] = PHASE_COMBAT
        block = self._state["combat"]
        block["subphase"] = phase
        block["mob"] = {"icon": combat.mob.icon, "name": combat.mob.name,
                        "hp": combat.mob_hp, "max_hp": combat.mob.hp,
                        "damage": f"{combat.mob.damage_min}–"
                                  f"{combat.mob.damage_max}"}
        if phase == ATTACK:
            block["commands"] = _attack_commands(self.game.hero)
        elif phase == DEFENSE:
            block["commands"] = _defense_commands()
        else:
            block["commands"] = []
        self._publish()

    def show_combat_outcome(self, result) -> None:
        self._state["phase"] = PHASE_COMBAT
        block = self._state["combat"]
        block["subphase"] = OUTCOME
        block["commands"] = []
        block["turn"] = self._turn_view(result)
        self._publish()

    def _turn_view(self, result) -> dict[str, Any]:
        hero = self.game.hero
        weapon_label = None
        if result.weapon is not None:
            item = getattr(hero, result.weapon, None) if hero else None
            weapon_label = (item.name if item is not None
                            else WEAPON_NAMES.get(result.weapon))
        return {"actor": result.actor,
                "weapon": result.weapon,
                "weapon_label": weapon_label,
                "direction": result.direction,
                "direction_name": DIRECTION_NAMES.get(result.direction),
                "blocked": result.blocked,
                "damage": result.damage,
                "crit": result.crit,
                "target_hp": result.target_hp,
                "armor": hero.armor_value if hero is not None else 0}

    def _shop_item(self, item, n: int) -> dict[str, Any]:
        hero = self.game.hero
        equipped = getattr(hero, item.slot, None) if hero else None
        current = (f"сейчас: {equipped.name} ({_item_detail(equipped)})"
                   if equipped is not None else "сейчас: пусто")
        return {"n": n, "icon": item.icon, "label": item.name,
                "slot_name": SHORT_SLOT_NAMES[item.slot],
                "detail": _item_detail(item), "current": current,
                "price": item.price, "votes": 0, "state": OPT_IDLE}

    def show_shop(self, items) -> None:
        self._state["phase"] = PHASE_SHOP
        self._state["shop"] = {
            "items": [self._shop_item(item, i + 1)
                      for i, item in enumerate(items)],
            "exit": _option(0, "Выйти")}
        self._publish()

    def show_rest(self, hero) -> None:
        self._state["phase"] = PHASE_REST
        self._state["rest"] = {}
        self._publish()

    def show_levelup(self, hero) -> None:
        self._state["phase"] = PHASE_LEVELUP
        self._state["levelup"] = {"options": [
            {"n": i + 1, "key": stat, "name": STAT_NAMES[stat],
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
        elif phase == PHASE_COMBAT:
            items = self._state["combat"]["commands"]
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
        """Called by Game.update() every frame; republishes only when the
        displayed second changes."""
        if self._seconds() != self._published_seconds:
            self._publish()

    # --- helpers -----------------------------------------------------------

    def _publish(self) -> None:
        snap = copy.deepcopy(self._state)
        snap["hero"] = self._hero_panel()
        snap["time_left"] = self._seconds()
        if snap["phase"] == PHASE_COMBAT and self.game.combat is not None:
            block = snap["combat"]
            block["subphase"] = self.game.combat_phase
            if block["mob"] is not None:
                block["mob"]["hp"] = self.game.combat.mob_hp
            if block["subphase"] in (OUTCOME, COMBAT_END):
                block["commands"] = []
        self._published_seconds = snap["time_left"]
        self._snapshot = snap

    def _seconds(self) -> int:
        return max(0, int(self.game.time_left + 0.5))

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
            "stats": [{"key": s, "name": STAT_NAMES[s],
                       "value": getattr(hero, s)} for s in STATS],
            "slots": {slot: _slot_view(getattr(hero, slot), slot)
                      for slot in ("melee", "ranged", "armor")},
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
