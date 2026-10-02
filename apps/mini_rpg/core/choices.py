"""Canonical vote keys per voting phase, mappings from the winning key to
game choices, and the fixed command table of the "classic" vote mode
(docs/DESIGN.md). Keys are digits ("1", "2", ...) and stay internal:
viewers vote with chat commands — either a random word per round dealt by
`streamkit.VoteWords` (vote_mode "words") or a fixed meaningful command
from the tables below (vote_mode "classic"); `Game` builds the validator
from the active mapping, so this module defines WHICH keys each phase has
and WHAT the classic commands are. Key sets overlap between phases (doors
1..3, attack 1..6, defense 1..3) — the mapping always comes from the
current phase, there is no global command table. Mappings `*_choice` work
with canonical keys only.
"""

from __future__ import annotations

from apps.mini_rpg.core.combat import DIRECTIONS
from apps.mini_rpg.core.hero import STATS

MELEE, RANGED = "melee", "ranged"

# Классические команды (vote_mode = "classic"): фиксированные осмысленные
# команды вместо случайных слов раунда. Совпадают по смыслу с подписями
# вариантов на оверлее (webui.py). «выстрел …» для дальнего боя — нейтрально
# к конкретному оружию (в пуле и лук, и арбалет).
DOOR_COMMANDS = ("левая", "средняя", "правая")
ATTACK_COMMANDS_MELEE = ("удар в голову", "удар в тело", "удар в ноги")
ATTACK_COMMANDS_RANGED = ("выстрел в голову", "выстрел в тело", "выстрел в ноги")
DEFENSE_COMMANDS = ("блок головы", "блок тела", "блок ног")
LEVELUP_COMMANDS = ("сила", "ловкость", "интеллект", "выносливость",
                    "удача")
SHOP_EXIT_COMMAND = "выход"  # товары — числовые команды «1»..«N»


def door_keys() -> list[str]:
    """Door vote keys: 1..3."""
    return _digits(1, 3)


def door_commands() -> dict[str, str]:
    """Classic door vote: key -> command (1..3 слева направо)."""
    return dict(zip(door_keys(), DOOR_COMMANDS))


def attack_keys(has_ranged: bool) -> list[str]:
    """Attack vote keys: 1..6 with a ranged weapon, 1..3 without."""
    return _digits(1, 6 if has_ranged else 3)


def attack_commands(has_ranged: bool) -> dict[str, str]:
    """Classic attack vote: key -> command (1..3 ближнее, 4..6 дальнее)."""
    commands = list(ATTACK_COMMANDS_MELEE)
    if has_ranged:
        commands += ATTACK_COMMANDS_RANGED
    return dict(zip(attack_keys(has_ranged), commands))


def attack_choice(digit: str) -> tuple[str, str]:
    """Winning attack key -> (weapon slot, direction):
    1..3 = melee head/body/legs, 4..6 = ranged head/body/legs."""
    n = _to_int(digit, 1, 6)
    return (MELEE if n <= 3 else RANGED), DIRECTIONS[(n - 1) % 3]


def defense_keys() -> list[str]:
    """Defense vote keys: 1..3."""
    return _digits(1, 3)


def defense_commands() -> dict[str, str]:
    """Classic defense vote: key -> command."""
    return dict(zip(defense_keys(), DEFENSE_COMMANDS))


def defense_choice(digit: str) -> str:
    """Winning defense key -> direction: 1..3 = head/body/legs."""
    return DIRECTIONS[_to_int(digit, 1, 3) - 1]


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
