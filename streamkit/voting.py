"""Voting machinery: one vote per user per round, revotable, majority wins.

`VotingRound` is a single round of vote collection; `VoteLoop` adds the
round timer on top, driven by `update(dt)` from the host app's main loop.
Both are plain Python — no chat or UI dependencies.
"""

from __future__ import annotations

import random
from typing import Callable

Validator = Callable[[str], str]


def _default_validate(text: str) -> str:
    m = text.strip().lower()
    if not m:
        raise ValueError("empty message")
    return m


class VotingRound:
    def __init__(self, validate: Validator | None = None):
        """validate(text) -> canonical vote; must raise ValueError if invalid."""
        self._validate = validate or _default_validate
        self._votes: dict[str, str] = {}

    def vote(self, user: str, text: str) -> bool:
        """Cast or change user's vote. Returns True if the text is valid."""
        try:
            self._votes[user] = self._validate(text)
            return True
        except ValueError:
            return False

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for m in self._votes.values():
            out[m] = out.get(m, 0) + 1
        return out

    def leaders(self) -> tuple[list[str], int]:
        """Votes with the most support and their count. ([], 0) if no votes."""
        c = self.counts()
        if not c:
            return [], 0
        top = max(c.values())
        return sorted(m for m, v in c.items() if v == top), top

    def winner(self, rng: random.Random | None = None) -> str | None:
        """Random vote among the leaders; None if nobody voted."""
        moves, _ = self.leaders()
        if not moves:
            return None
        return (rng or random).choice(moves)

    def __len__(self) -> int:
        return len(self._votes)


class VoteLoop:
    """Timed voting rounds, ticked by update(dt) from the host's main loop.

    While a round is active, votes are accepted via vote(). When the timer
    expires the loop deactivates and fires on_round_end(winner, counts,
    n_voters) — winner is None if nobody voted. Call start() to open the
    next round (the host decides when, e.g. after an animation finishes).
    """

    def __init__(self, duration: float,
                 on_round_end: Callable[[str | None, dict[str, int], int], None],
                 validate: Validator | None = None,
                 rng: random.Random | None = None):
        self.duration = duration
        self.on_round_end = on_round_end
        self.rng = rng or random.Random()
        self._validate = validate
        self.round: VotingRound | None = None
        self.time_left = 0.0
        self.start()

    @property
    def active(self) -> bool:
        return self.round is not None

    def start(self) -> None:
        """Open a new round: fresh votes, full timer."""
        self.round = VotingRound(self._validate)
        self.time_left = self.duration

    def vote(self, user: str, text: str) -> bool:
        if self.round is None:
            return False
        return self.round.vote(user, text)

    def counts(self) -> dict[str, int]:
        return self.round.counts() if self.round else {}

    def leaders(self) -> tuple[list[str], int]:
        return self.round.leaders() if self.round else ([], 0)

    def finish(self) -> None:
        """End the active round immediately, firing on_round_end."""
        if self.round is None:
            return
        round_ = self.round
        self.round = None  # deactivate before the callback re-starts
        self.on_round_end(round_.winner(self.rng), round_.counts(), len(round_))

    def update(self, dt: float) -> None:
        if self.round is None:
            return
        self.time_left -= dt
        if self.time_left <= 0:
            self.finish()
