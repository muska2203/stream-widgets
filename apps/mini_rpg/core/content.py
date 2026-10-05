"""Content pools: TOML loading and validation of mobs and items.

One entity = one file `mobs/<name>.toml` or `items/<name>.toml` (field
formats and rules — docs/DESIGN.md); adding/removing a file is all it takes
to change the pool.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MOBS_DIR = Path(__file__).resolve().parent.parent / "mobs"
DEFAULT_ITEMS_DIR = Path(__file__).resolve().parent.parent / "items"
DEFAULT_PREFIXES_PATH = Path(__file__).resolve().parent.parent / "prefixes.toml"

# фолбэк, если prefixes.toml отсутствует или список в нём пуст
DEFAULT_PREFIXES = ("Гнусный", "Смешной", "Горючий", "Хилый", "Жирный")

SLOTS = ("melee", "armor")


class ContentError(ValueError):
    """Invalid content file (broken TOML, missing fields, bad values)."""


@dataclass
class Mob:
    name: str
    icon: str
    hp: int
    damage_min: int
    damage_max: int
    xp: int
    gold: int
    cooldown: float = 5.0  # секунд между атаками моба


@dataclass
class Item:
    name: str
    icon: str
    slot: str  # melee | armor
    damage_min: int | None  # для melee
    damage_max: int | None
    armor: int | None       # для armor — флэт-поглощение удара моба
    price: int
    starter: bool = False   # стартовый предмет героя; в магазин не попадает


# фолбэк стартового оружия, если в items/ нет предмета со starter = true
# (как DEFAULT_PREFIXES для prefixes.toml)
DEFAULT_STARTER = Item(name="Кулаки", icon="👊", slot="melee", damage_min=1,
                       damage_max=2, armor=None, price=0, starter=True)


def load_mob(path: str | Path) -> Mob:
    """Parse and validate one mob file; raises ContentError on any problem."""
    data, name = _read_toml(path)
    mob_name = _require_str(name, data, "name")
    icon = _optional_str(name, data, "icon")
    hp = _require_int(name, data, "hp", minimum=1)
    damage_min, damage_max = _require_damage(name, data)
    xp = _optional_int(name, data, "xp", minimum=0)
    gold = _optional_int(name, data, "gold", minimum=0)
    cooldown = _optional_float(name, data, "cooldown", default=5.0)
    return Mob(name=mob_name, icon=icon, hp=hp, damage_min=damage_min,
               damage_max=damage_max, xp=xp, gold=gold, cooldown=cooldown)


def load_item(path: str | Path) -> Item:
    """Parse and validate one item file; raises ContentError on any problem."""
    data, name = _read_toml(path)
    item_name = _require_str(name, data, "name")
    icon = _optional_str(name, data, "icon")
    slot = data.get("slot")
    if slot not in SLOTS:
        raise ContentError(f"{name}: slot обязателен, одно из {SLOTS}")
    price = _require_int(name, data, "price", minimum=0)

    damage_min = damage_max = armor = None
    if slot == "melee":
        damage_min, damage_max = _require_damage(name, data)
    if slot == "armor":
        armor = _require_int(name, data, "armor", minimum=0)
    starter = data.get("starter", False)
    if not isinstance(starter, bool):
        raise ContentError(f"{name}: starter — true/false")
    return Item(name=item_name, icon=icon, slot=slot, damage_min=damage_min,
                damage_max=damage_max, armor=armor, price=price,
                starter=starter)


def discover_mobs(directory: str | Path = DEFAULT_MOBS_DIR) -> list[Path]:
    """Sorted list of mob files (*.toml) in the pool directory."""
    return _discover(directory)


def discover_items(directory: str | Path = DEFAULT_ITEMS_DIR) -> list[Path]:
    """Sorted list of item files (*.toml) in the pool directory."""
    return _discover(directory)


def load_mobs(directory: str | Path = DEFAULT_MOBS_DIR) -> list[Mob]:
    """Load the whole pool; ContentError names the broken file."""
    return [load_mob(p) for p in discover_mobs(directory)]


def load_items(directory: str | Path = DEFAULT_ITEMS_DIR) -> list[Item]:
    """Load the whole pool; ContentError names the broken file."""
    return [load_item(p) for p in discover_items(directory)]


def find_starters(items: list[Item]) -> list[Item]:
    """Starter kit: items with starter = true, at most one per slot; a melee
    starter is required (без ближнего оружия бой не стартует). No starter
    items at all → [DEFAULT_STARTER]."""
    starters = []
    seen = set()
    for it in items:
        if not it.starter:
            continue
        if it.slot in seen:
            raise ContentError(f"два стартовых предмета в слоте {it.slot}")
        seen.add(it.slot)
        starters.append(it)
    if not starters:
        return [DEFAULT_STARTER]
    if "melee" not in seen:
        raise ContentError("стартовый набор без ближнего оружия "
                           "(starter = true, slot = melee)")
    return starters


def load_prefixes(path: str | Path = DEFAULT_PREFIXES_PATH) -> list[str]:
    """Battle-name prefixes from one TOML file (`prefixes = [...]`).

    Missing file or empty list → DEFAULT_PREFIXES fallback; broken TOML or
    non-string entries → ContentError (error screen, like mobs/items).
    """
    path = Path(path)
    if not path.is_file():
        return list(DEFAULT_PREFIXES)
    data, name = _read_toml(path)
    prefixes = data.get("prefixes")
    if not isinstance(prefixes, list):
        raise ContentError(f"{name}: prefixes обязателен, список строк")
    if not all(isinstance(p, str) for p in prefixes):
        raise ContentError(f"{name}: prefixes — только строки")
    cleaned = [p.strip() for p in prefixes if p.strip()]
    return cleaned or list(DEFAULT_PREFIXES)


def _read_toml(path: str | Path) -> tuple[dict, str]:
    path = Path(path)
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ContentError(f"{path.name}: ошибка TOML: {e}") from e
    except OSError as e:
        raise ContentError(f"{path.name}: не читается: {e}") from e
    return data, path.name


def _discover(directory: str | Path) -> list[Path]:
    directory = Path(directory)
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.iterdir() if p.suffix == ".toml")


def _require_str(file: str, data: dict, key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ContentError(f"{file}: {key} обязателен и не пуст")
    return value.strip()


def _optional_str(file: str, data: dict, key: str) -> str:
    value = data.get(key, "")
    if not isinstance(value, str):
        raise ContentError(f"{file}: {key} должен быть строкой")
    return value


def _require_int(file: str, data: dict, key: str, minimum: int) -> int:
    value = data.get(key)
    if not isinstance(value, int) or value < minimum:
        raise ContentError(f"{file}: {key} обязателен, целое >= {minimum}")
    return value


def _optional_int(file: str, data: dict, key: str, minimum: int) -> int:
    value = data.get(key, 0)
    if not isinstance(value, int) or value < minimum:
        raise ContentError(f"{file}: {key} — целое >= {minimum}")
    return value


def _optional_float(file: str, data: dict, key: str, default: float) -> float:
    value = data.get(key, default)
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or value <= 0):
        raise ContentError(f"{file}: {key} — число > 0")
    return float(value)


def _require_damage(file: str, data: dict) -> tuple[int, int]:
    damage_min = _require_int(file, data, "damage_min", minimum=0)
    damage_max = _require_int(file, data, "damage_max", minimum=0)
    if damage_max < damage_min:
        raise ContentError(f"{file}: damage_max ({damage_max}) меньше "
                           f"damage_min ({damage_min})")
    return damage_min, damage_max
