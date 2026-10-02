"""Run progress persistence between sessions (checkpoint at event entry).

Only the durable layer is saved: the hero (stats, level, xp, gold, hp/mana,
equipment) and the run counters (kills, gold_earned, defeated,
pending_levelups). The state machine — phase, combat, votes, timers — is
transient and never persisted; a restore re-enters EVENT with freshly rolled
doors. The file is versioned JSON written atomically (tmp + replace, like
streamkit.ChatterRegistry); a broken or outdated file is renamed to .bak and
the game starts a fresh run — a savegame never crashes the stream.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from apps.mini_rpg.core import Hero, Item
from apps.mini_rpg.core.content import SLOTS

if TYPE_CHECKING:
    from apps.mini_rpg.game import Game

SAVE_VERSION = 1

_HERO_SCALARS = ("base_hp", "strength", "agility", "intellect", "endurance",
                 "luck", "level", "xp", "gold", "hp", "mana")
_ITEM_FIELDS = ("name", "icon", "slot", "damage_min", "damage_max", "uses",
                "armor", "price")


def default_save_path() -> Path:
    return Path(__file__).resolve().parent / "savegame.json"


def save_checkpoint(path: str | Path, game: Game) -> None:
    """Atomic dump of hero + run counters; write errors only warn."""
    payload = {"version": SAVE_VERSION,
               "hero": asdict(game.hero),
               "kills": game.kills,
               "gold_earned": game.gold_earned,
               "defeated": list(game.defeated),
               "pending_levelups": game.pending_levelups}
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        tmp.replace(path)
    except OSError as e:
        print(f"savegame: не удалось записать {path} ({e})", flush=True)


def load_checkpoint(path: str | Path) -> dict | None:
    """{"hero": Hero, counters...} from a save file; None if missing/invalid.

    Invalid files (broken JSON, wrong version, bad fields) are renamed to
    .bak best-effort and reported — the caller then starts a fresh run.
    """
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        return _reject(path, f"не читается: {e}")
    try:
        if not isinstance(data, dict) or data.get("version") != SAVE_VERSION:
            raise ValueError(f"нужна версия {SAVE_VERSION}")
        hero = _hero_from_dict(data["hero"])
        kills = _nonneg_int(data["kills"], "kills")
        gold_earned = _nonneg_int(data["gold_earned"], "gold_earned")
        pending = _nonneg_int(data["pending_levelups"], "pending_levelups")
        defeated = data["defeated"]
        if not isinstance(defeated, list) or \
                not all(isinstance(x, str) for x in defeated):
            raise ValueError("defeated — список строк")
    except (KeyError, TypeError, ValueError) as e:
        return _reject(path, f"битые данные: {e}")
    # балансные константы могли измениться между сессиями
    hero.hp = min(hero.hp, hero.max_hp)
    hero.mana = min(hero.mana, hero.max_mana)
    return {"hero": hero, "kills": kills, "gold_earned": gold_earned,
            "defeated": defeated, "pending_levelups": pending}


def _reject(path: Path, reason: str) -> None:
    print(f"savegame: {path} {reason} — новый забег", flush=True)
    try:
        path.replace(path.with_suffix(path.suffix + ".bak"))
    except OSError:
        pass
    return None


def _hero_from_dict(data) -> Hero:
    if not isinstance(data, dict):
        raise ValueError("hero — объект")
    values = {key: _nonneg_int(data[key], f"hero.{key}")
              for key in _HERO_SCALARS}
    if values["hp"] < 1:
        raise ValueError("hero.hp < 1 — мёртвый герой не сохраняется")
    for slot in SLOTS:
        values[slot] = _item_from_dict(data.get(slot), f"hero.{slot}")
    return Hero(**values)


def _item_from_dict(data, where: str) -> Item | None:
    if data is None:
        return None
    if not isinstance(data, dict):
        raise ValueError(f"{where} — объект или null")
    values = {key: data.get(key) for key in _ITEM_FIELDS}
    if values["slot"] not in SLOTS:
        raise ValueError(f"{where}.slot — одно из {SLOTS}")
    if not isinstance(values["name"], str) or \
            not isinstance(values["icon"], str):
        raise ValueError(f"{where}: name/icon — строки")
    if not isinstance(values["price"], int):
        raise ValueError(f"{where}.price — целое")
    for key in ("damage_min", "damage_max", "uses", "armor"):
        if values[key] is not None and not isinstance(values[key], int):
            raise ValueError(f"{where}.{key} — целое или null")
    return Item(**values)


def _nonneg_int(value, where: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{where} — целое >= 0")
    return value
