"""Chat vote validator for scene options: digits 1..n (see docs/DESIGN.md)."""

from __future__ import annotations

from collections.abc import Callable

Validator = Callable[[str], str]


def make_choice_validator(n_options: int) -> Validator:
    """validate(text) -> canonical digit string; raises ValueError otherwise."""
    if not 1 <= n_options <= 9:
        raise ValueError(f"n_options must be 1..9, got {n_options}")
    valid = frozenset(str(i) for i in range(1, n_options + 1))

    def validate(text: str) -> str:
        digit = text.strip()
        if digit not in valid:
            raise ValueError(f"not an option number 1..{n_options}: {text!r}")
        return digit

    return validate
