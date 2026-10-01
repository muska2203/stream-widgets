"""Chat command validators per voting phase, plus mappings from the winning
digit to game choices (docs/DESIGN.md). Digit sets overlap between phases
(doors 1..3, attack 1..6, defense 1..3) — the validator always comes from
the current phase, there is no global command table. Plugged into
streamkit VoteLoop via validate=.
"""

from __future__ import annotations

from collections.abc import Callable

from apps.mini_rpg.core.combat import DIRECTIONS
from apps.mini_rpg.core.hero import STATS

Validator = Callable[[str], str]

MELEE, RANGED = "melee", "ranged"


def make_door_validator() -> Validator:
    """Door vote: 1..3."""
    return _digits(1, 3)


def make_attack_validator(has_ranged: bool) -> Validator:
    """Attack vote: 1..6 with a ranged weapon, 1..3 without."""
    return _digits(1, 6 if has_ranged else 3)


def attack_choice(digit: str) -> tuple[str, str]:
    """Winning attack digit -> (weapon slot, direction):
    1..3 = melee head/body/legs, 4..6 = ranged head/body/legs."""
    n = _to_int(digit, 1, 6)
    return (MELEE if n <= 3 else RANGED), DIRECTIONS[(n - 1) % 3]


def make_defense_validator() -> Validator:
    """Defense vote: 1..3."""
    return _digits(1, 3)


def defense_choice(digit: str) -> str:
    """Winning defense digit -> direction: 1..3 = head/body/legs."""
    return DIRECTIONS[_to_int(digit, 1, 3) - 1]


def make_levelup_validator() -> Validator:
    """Levelup vote: 1..5."""
    return _digits(1, 5)


def levelup_choice(digit: str) -> str:
    """Winning levelup digit -> stat from STATS (1 = first)."""
    return STATS[_to_int(digit, 1, 5) - 1]


def make_shop_validator(count: int) -> Validator:
    """Shop vote: 0 = exit, 1..count = buy the shown item. Unaffordable
    items are cut before the list is built, the validator only knows the
    shown positions."""
    if count < 0:
        raise ValueError(f"count must be >= 0, got {count}")
    return _digits(0, count)


def _digits(lo: int, hi: int) -> Validator:
    """validate(text) -> canonical digit string; raises ValueError otherwise."""
    valid = frozenset(str(i) for i in range(lo, hi + 1))

    def validate(text: str) -> str:
        digit = text.strip()
        if digit not in valid:
            raise ValueError(f"не команда этой фазы: {text!r}")
        return digit

    return validate


def _to_int(digit: str, lo: int, hi: int) -> int:
    n = int(digit)
    if not lo <= n <= hi:
        raise ValueError(f"команда вне диапазона {lo}..{hi}: {digit!r}")
    return n
