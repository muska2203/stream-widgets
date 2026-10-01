"""Game state machine: SELECT -> VOTING -> OUTCOME -> SLEEP -> ... -> END
(see docs/DESIGN.md). No votes = the story does not move: the round is
replayed on the same scene. Plain Python — the main loop in main.py calls
update(dt); the UI is a WebUI state model served to OBS Browser Source."""

from __future__ import annotations

import random

from streamkit import MockChat, VoteLoop

from apps.interactive_story.config import Config
from apps.interactive_story.core import (Option, Scene, Story, StoryError,
                                         load_stories, make_choice_validator)
from apps.interactive_story.narration import Narrator, NullNarrator
from apps.interactive_story.webui import WebUI

SELECT, VOTING, OUTCOME, SLEEP, END = ("select", "voting", "outcome",
                                       "sleep", "end")

GARBAGE = ("hello", "gg", "a", "0")  # non-commands to exercise filtering
MOCK_MESSAGES = [str(i) for i in range(1, 10)] + list(GARBAGE)

DEFAULT_RESULT = "Чат сделал свой выбор."


class Game:
    def __init__(self, cfg: Config, narrator: Narrator | None = None):
        self.cfg = cfg
        self.rng = random.Random(cfg.seed)
        self.ui = WebUI()
        self.narrator: Narrator = narrator or NullNarrator()
        if cfg.mock_chat:
            self.chat = MockChat(self.handle_chat_message, MOCK_MESSAGES,
                                 rng=self.rng)
        else:
            from streamkit import TwitchChat  # lazy: нужен twitchio и .env
            self.chat = TwitchChat(self.handle_chat_message, cfg.channel)
        self.state = ""
        self.vote_loop: VoteLoop | None = None
        self.stories: list[Story] = []
        self.story: Story | None = None
        self.scene: Scene | None = None
        self._pending_option: Option | None = None
        self.move_number = 0
        self.time_left = 0.0  # единый countdown фаз (VOTING — весь ход целиком)
        self.enter_select()

    # --- phases ----------------------------------------------------------

    def enter_select(self) -> None:
        self.narrator.stop()
        self.story = None
        self.scene = None
        self.move_number = 0
        self.ui.set_visible(True)
        try:
            self.stories = load_stories()  # перечитываем пул каждый раз
        except StoryError as e:
            print(f"story pool error: {e}", flush=True)
            self.ui.show_select_error(f"Ошибка истории: {e}")
            self.state = "error"
            return
        if not self.stories:
            self.ui.show_select_error("Нет историй — положите .toml "
                                      "в apps/interactive_story/stories/")
            self.state = "error"
            return
        if len(self.stories) == 1:
            self.start_story(self.stories[0])
            return
        self.state = SELECT
        self.ui.show_select(self.stories)
        self.vote_loop = VoteLoop(self.cfg.select_duration, self.on_select_end,
                                  validate=make_choice_validator(
                                      len(self.stories)),
                                  rng=self.rng)
        self._update_header(self.cfg.select_duration)

    def on_select_end(self, winner: str | None, counts: dict[str, int],
                      n_voters: int) -> None:
        if winner is None:
            print("no votes, restarting story select", flush=True)
            self.vote_loop.start()
            self.ui.update_select_votes({}, None)
            return
        story = self.stories[int(winner) - 1]
        print(f"story chosen: {story.name} ({n_voters} voters)", flush=True)
        self.start_story(story)

    def start_story(self, story: Story) -> None:
        self.story = story
        self.scene = story.scene(story.start)
        self.move_number = 0
        print(f"story started: {story.name}", flush=True)
        self.enter_voting()

    def enter_voting(self) -> None:
        """Show the scene and open voting immediately; the single move
        timer (round_duration) runs from scene show to voting end."""
        self.state = VOTING
        self.vote_loop = None
        self.time_left = self.cfg.round_duration  # единый таймер хода
        self.ui.set_visible(True)  # пробуждение после сна
        self.ui.show_move(self.scene.text)
        self._open_options()
        self._update_header(self.time_left)
        self.narrator.say_scene(self.scene.text)

    def _open_options(self) -> None:
        labels = [o.text for o in self.scene.options]
        self.ui.show_options(labels)
        # длительность роли не играет: тикает единый таймер хода, раунд
        # закрывается через finish() при time_left <= 0
        self.vote_loop = VoteLoop(self.cfg.round_duration, self.on_round_end,
                                  validate=make_choice_validator(len(labels)),
                                  rng=self.rng)

    def on_round_end(self, winner: str | None, counts: dict[str, int],
                     n_voters: int) -> None:
        if winner is None:  # никто не голосовал — история не двигается
            print("no votes, replaying the move", flush=True)
            self.enter_voting()
            return
        idx = int(winner) - 1
        self._pending_option = self.scene.options[idx]
        self.move_number += 1
        print(f"move {self.move_number}: option {winner} "
              f"({n_voters} voters)", flush=True)
        self.state = OUTCOME
        result = self._pending_option.result or DEFAULT_RESULT
        self.ui.show_outcome(idx, result)
        self.narrator.say_result(result)
        self.time_left = self.cfg.outcome_pause
        self._update_header(self.time_left)

    def advance(self) -> None:
        self.narrator.stop()
        self.scene = self.story.scene(self._pending_option.next)
        if self.scene.ending:
            print(f"ending: {self.scene.ending_label or self.scene.id}",
                  flush=True)
            self.state = END
            self.ui.show_ending(self.scene.ending_label or "",
                                self.scene.text)
            self.time_left = self.cfg.end_pause
        else:
            self.state = SLEEP
            self.ui.enter_sleep()  # шапка и текст результата остаются
            self.time_left = self.cfg.sleep_duration

    def _tick_timeout(self) -> None:
        if self.state == OUTCOME:
            self.advance()
        elif self.state == SLEEP:
            self.enter_voting()
        elif self.state == END:
            self.enter_select()

    # --- chat ------------------------------------------------------------

    def handle_chat_message(self, user: str, text: str) -> None:
        """Single entry point for chat commands (mock chat or Twitch)."""
        if self.state not in (SELECT, VOTING) or not self.vote_loop:
            return
        if self.vote_loop.vote(user, text):
            leaders, _ = self.vote_loop.leaders()
            leader = leaders[0] if leaders else None
            counts = self.vote_loop.counts()
            if self.state == SELECT:
                self.ui.update_select_votes(counts, leader)
            else:
                self.ui.update_votes(counts, leader)

    # --- per-frame ---------------------------------------------------------

    def update(self, dt: float) -> None:
        if self.chat and self.state in (SELECT, VOTING):
            self.chat.update(dt)
        if self.state == SELECT:
            self.vote_loop.update(dt)
            # коллбэк мог выбрать историю (фаза сменилась, vote_loop = None)
            if self.state == SELECT and self.vote_loop:
                self._update_header(self.vote_loop.time_left)
        elif self.state == VOTING:
            self.time_left -= dt
            self._update_header(self.time_left)
            if self.time_left <= 0 and self.vote_loop:
                self.vote_loop.finish()  # вызывает on_round_end
        elif self.state in (OUTCOME, SLEEP, END):
            self.time_left -= dt
            self._update_header(self.time_left)
            if self.time_left <= 0:
                self._tick_timeout()

    def _update_header(self, seconds: float) -> None:
        sec = max(0, int(seconds + 0.5))
        if self.state == SELECT:
            text = f"Выбор истории · {sec}"
        elif self.story is None:
            return
        elif self.state in (VOTING, SLEEP):  # в сне: таймер до след. хода
            text = f"«{self.story.title}» · Ход {self.move_number + 1} · {sec}"
        elif self.state == END:
            text = f"«{self.story.title}» · Финал · {sec}"
        else:  # OUTCOME
            text = f"«{self.story.title}» · Ход {self.move_number} · {sec}"
        self.ui.set_header(text)
