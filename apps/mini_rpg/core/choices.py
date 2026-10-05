"""Canonical vote keys per voting phase, mappings from the winning key to
game choices, and the fixed command table of the "classic" vote mode
(docs/DESIGN.md). Keys are digits ("1", "2", ...) and stay internal:
viewers vote with chat commands — either a random word per round dealt by
`streamkit.VoteWords` (vote_mode "words") or a fixed meaningful command
from the tables below (vote_mode "classic"); `Game` builds the validator
from the active mapping, so this module defines WHICH keys each phase has
and WHAT the classic commands are. Key sets overlap between phases (doors
1..3, levelup 1..5, shop 0..N) — the mapping always comes from the
current phase, there is no global command table. Mappings `*_choice` work
with canonical keys only. Combat has no votes (auto-battle, docs/DESIGN.md
«Бой») — the chat joins the squad with the fixed «бой» command, see
core.combat.
"""

from __future__ import annotations

from apps.mini_rpg.core.hero import STATS

# Классические команды (vote_mode = "classic"): фиксированные осмысленные
# команды вместо случайных слов раунда. Совпадают по смыслу с подписями
# вариантов на оверлее (webui.py).
DOOR_COMMANDS = ("левая", "средняя", "правая")
LEVELUP_COMMANDS = ("сила", "ловкость", "интеллект", "выносливость",
                    "удача")
SHOP_EXIT_COMMAND = "выход"  # товары — числовые команды «1»..«N»


def door_keys() -> list[str]:
    """Door vote keys: 1..3."""
    return _digits(1, 3)


def door_commands() -> dict[str, str]:
    """Classic door vote: key -> command (1..3 слева направо)."""
    return dict(zip(door_keys(), DOOR_COMMANDS))


def levelup_keys() -> list[str]:
    """Levelup vote keys: 1..5."""
    return _digits(1, 5)


def levelup_commands() -> dict[str, str]:
    """Classic levelup vote: key -> stat name command."""
    return dict(zip(levelup_keys(), LEVELUP_COMMANDS))


def levelup_choice(digit: str) -> str:
    """Winning levelup key -> stat from STATS (1 = first)."""
    return STATS[_to_int(digit, 1, 5) - 1]


def shop_keys(count: int) -> list[str]:
    """Shop vote keys: 0 = exit, 1..count = buy the shown item. Unaffordable
    items are cut before the list is built, the key set only knows the
    shown positions."""
    if count < 0:
        raise ValueError(f"count must be >= 0, got {count}")
    return _digits(0, count)


def shop_commands(count: int) -> dict[str, str]:
    """Classic shop vote: key -> command (выход = «выход», товары = «1»..)."""
    return {key: (SHOP_EXIT_COMMAND if key == "0" else key)
            for key in shop_keys(count)}


def _digits(lo: int, hi: int) -> list[str]:
    return [str(i) for i in range(lo, hi + 1)]


def _to_int(digit: str, lo: int, hi: int) -> int:
    n = int(digit)
    if not lo <= n <= hi:
        raise ValueError(f"команда вне диапазона {lo}..{hi}: {digit!r}")
    return n
