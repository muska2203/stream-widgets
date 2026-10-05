"""CLI check of the content pools:
py -m apps.mini_rpg.core [mobs_dir [items_dir [prefixes_path]]]"""

from __future__ import annotations

import sys
from pathlib import Path

from apps.mini_rpg.core.content import (DEFAULT_ITEMS_DIR, DEFAULT_MOBS_DIR,
                                        DEFAULT_PREFIXES_PATH, ContentError,
                                        Item, Mob, discover_items,
                                        discover_mobs, find_starters,
                                        load_item, load_items, load_mob,
                                        load_prefixes)


def main() -> None:
    # консоль Windows (cp1251) не умеет эмодзи иконок — заменяем на '?'
    sys.stdout.reconfigure(errors="replace")
    mobs_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_MOBS_DIR
    items_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_ITEMS_DIR
    prefixes_path = (Path(sys.argv[3]) if len(sys.argv) > 3
                     else DEFAULT_PREFIXES_PATH)
    failed = _check_pool(mobs_dir, discover_mobs, load_mob, _format_mob)
    items_failed = _check_pool(items_dir, discover_items, load_item,
                               _format_item)
    failed += items_failed
    if not items_failed:
        failed += _check_starters(items_dir)
    failed += _check_prefixes(prefixes_path)
    sys.exit(1 if failed else 0)


def _check_starters(items_dir: Path) -> int:
    try:
        starters = find_starters(load_items(items_dir))
    except ContentError as e:
        print(f"  FAIL стартовый набор: {e}", flush=True)
        return 1
    names = ", ".join(it.name for it in starters)
    print(f"  OK   стартовый набор: {names}", flush=True)
    return 0


def _check_prefixes(path: Path) -> int:
    print(f"[{path.name}]", flush=True)
    try:
        prefixes = load_prefixes(path)
    except ContentError as e:
        print(f"  FAIL {e}", flush=True)
        return 1
    print(f"  OK   {len(prefixes)} префиксов: {', '.join(prefixes)}", flush=True)
    return 0


def _check_pool(directory, discover, load, format_) -> int:
    print(f"[{directory.name}]", flush=True)
    paths = discover(directory)
    if not paths:
        print(f"  пусто: нет .toml в {directory}", flush=True)
        return 1
    failed = 0
    for path in paths:
        try:
            entity = load(path)
        except ContentError as e:
            failed += 1
            print(f"  FAIL {e}", flush=True)
            continue
        print(f"  OK   {format_(entity)}", flush=True)
    return failed


def _format_mob(mob: Mob) -> str:
    return (f"{mob.icon} {mob.name} — hp {mob.hp}, "
            f"урон {mob.damage_min}..{mob.damage_max}, "
            f"награда {mob.xp} xp / {mob.gold} золота")


def _format_item(item: Item) -> str:
    if item.slot == "armor":
        stats = f"броня {item.armor}"
    else:
        stats = f"урон {item.damage_min}..{item.damage_max}"
    line = f"{item.icon} {item.name} [{item.slot}] — {stats}, цена {item.price}"
    return line + (", стартовый" if item.starter else "")


if __name__ == "__main__":
    main()
