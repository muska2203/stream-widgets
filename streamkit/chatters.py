"""Chatter registry: remembers everyone who writes in chat.

App-agnostic building block: the host feeds every chat message's author via
`add(user)` and asks for a random nick via `pick(rng)` (e.g. mini_rpg names
monsters after chatters). With a `path` the base persists to a JSON file
between runs; `path=None` keeps it in memory only (tests, mock chat).

Selection prefers viewers active in the current session; when the session
pool is empty, falls back to the whole persistent base.
"""

from __future__ import annotations

import json
import random
from pathlib import Path


class ChatterRegistry:
    """Set of known chatters plus the current session's active ones."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else None
        self.all: set[str] = set()
        self.session: list[str] = []  # активные за текущий запуск, без повторов
        if self.path is not None:
            self._load()

    def __len__(self) -> int:
        return len(self.all)

    def add(self, user: str) -> None:
        """Register a chatter; persists immediately if a path is set."""
        user = user.strip()
        if not user:
            return
        if user not in self.session:
            self.session.append(user)
        if user in self.all:
            return
        self.all.add(user)
        if self.path is not None:
            self.save()

    def pick(self, rng: random.Random) -> str | None:
        """Random nick: session-active first, whole base as fallback."""
        if self.session:
            return rng.choice(self.session)
        if self.all:
            return rng.choice(sorted(self.all))
        return None

    def save(self) -> None:
        """Atomic dump: tmp file + replace, so a crash never halves the base."""
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps({"chatters": sorted(self.all)},
                       ensure_ascii=False, indent=1),
            encoding="utf-8")
        tmp.replace(self.path)

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            names = data["chatters"]
            if not isinstance(names, list):
                raise ValueError("chatters не список")
            self.all = {str(n) for n in names}
        except FileNotFoundError:
            pass
        except (OSError, ValueError, KeyError, TypeError) as e:
            print(f"chatters: база {self.path} не читается ({e}) — "
                  "начинаем с пустой", flush=True)
            self.all = set()
