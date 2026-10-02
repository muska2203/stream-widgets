"""Voting by short chat words instead of digits.

Apps that want viewers to vote with words (e.g. to dodge Twitch's
duplicate-message block) build a per-round alias table with `VoteWords`:
each canonical vote key gets a random word from the pool, viewers type the
word, and `validator()` folds it back to the canonical key. The rest of the
app (VoteLoop, tie resolve, UI state) keeps working with canonical keys.

Words issued within the last `cooldown` seconds (by the injectable `clock`)
are not re-issued, so the same word does not reappear while a chat platform
might still reject it as a duplicate. If the free pool is too small for the
requested keys, the cooldown is ignored for that round (uniqueness within
the round is always kept).

The default pool is the curated `votewords.toml` next to this module
(package data); apps may pass their own path to `from_file()`.
"""

from __future__ import annotations

import random
import time
import tomllib
from pathlib import Path
from typing import Callable, Sequence

Validator = Callable[[str], str]

DEFAULT_POOL_PATH = Path(__file__).resolve().with_name("votewords.toml")


class VoteWords:
    """Random word aliases for one app's voting rounds."""

    def __init__(self, words: Sequence[str], rng: random.Random | None = None,
                 cooldown: float = 60.0,
                 clock: Callable[[], float] = time.monotonic):
        cleaned = [w.strip().lower() for w in words if w and w.strip()]
        if not cleaned:
            raise ValueError("пул слов пуст")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("в пуле слов дубликаты")
        self.words = tuple(cleaned)
        self.rng = rng or random.Random()
        self.cooldown = float(cooldown)
        self.clock = clock
        self._issued: dict[str, float] = {}  # слово -> момент последней выдачи

    @classmethod
    def from_file(cls, path: str | Path = DEFAULT_POOL_PATH, **kwargs
                  ) -> "VoteWords":
        """Pool from a TOML file (`words = [...]`); kwargs go to __init__."""
        path = Path(path)
        try:
            with path.open("rb") as f:
                data = tomllib.load(f)
        except (tomllib.TOMLDecodeError, OSError) as e:
            raise ValueError(f"{path.name}: пул слов не читается: {e}") from e
        words = data.get("words")
        if not isinstance(words, list) or not all(
                isinstance(w, str) for w in words):
            raise ValueError(f"{path.name}: words обязателен, список строк")
        return cls(words, **kwargs)

    def assign(self, keys: Sequence[str]) -> dict[str, str]:
        """Deal a unique word to each key; returns {word: key}.

        Words issued < cooldown seconds ago are skipped while enough free
        words remain; otherwise the cooldown is ignored for this round.
        """
        keys = list(keys)
        if len(keys) > len(self.words):
            raise ValueError(f"пул из {len(self.words)} слов не покрывает "
                             f"{len(keys)} ключей")
        now = self.clock()
        free = [w for w in self.words
                if now - self._issued.get(w, -self.cooldown) >= self.cooldown]
        pool = free if len(free) >= len(keys) else list(self.words)
        chosen = self.rng.sample(pool, len(keys))
        for word in chosen:
            self._issued[word] = now
        return dict(zip(chosen, keys))

    @staticmethod
    def validator(mapping: dict[str, str]) -> Validator:
        """validate(text) -> canonical key for the word; ValueError otherwise.

        Case- and whitespace-insensitive on the viewer's side; anything not
        in this round's mapping (digits, garbage, words of other rounds) is
        rejected.
        """

        def validate(text: str) -> str:
            word = text.strip().lower()
            if word not in mapping:
                raise ValueError(f"не слово этого раунда: {text!r}")
            return mapping[word]

        return validate
