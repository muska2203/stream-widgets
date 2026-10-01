"""Narration hook: seam for future TTS of scene/result text.

Game calls the narrator at the moments where voice-over would happen —
today with a no-op default, so adding real TTS later means writing a class
with the same protocol and passing it to Game, no game code changes.
"""

from __future__ import annotations

from typing import Protocol


class Narrator(Protocol):
    def say_scene(self, text: str) -> None:
        """Scene text was just shown (start of a move)."""

    def say_result(self, text: str) -> None:
        """Outcome text was just shown (consequences of the choice)."""

    def stop(self) -> None:
        """Cut the speech: sleep, ending or story switch."""


class NullNarrator:
    """Default narrator: no speech at all."""

    def say_scene(self, text: str) -> None:
        pass

    def say_result(self, text: str) -> None:
        pass

    def stop(self) -> None:
        pass
