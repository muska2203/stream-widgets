"""Game state machine: VOTING -> APPLYING -> WIN/restart (see docs/DESIGN.md)."""

from __future__ import annotations

import random

from ursina import Entity, time, window

from streamkit import MockChat, VoteLoop

from apps.rubiks_cube.config import Config
from apps.rubiks_cube.core import VALID_MOVES, Cube, normalize
from apps.rubiks_cube.cube_view import CubeView
from apps.rubiks_cube.ui import TABLE_TOP, GameUI

VOTING, APPLYING, WIN = "voting", "applying", "win"

GARBAGE = ("hello", "gg", "123")  # non-commands to exercise filtering


class Game(Entity):
    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        self.rng = random.Random()
        self.cube = Cube()
        self.view = CubeView(self.cube, animation_duration=cfg.animation_duration,
                             tilt=(cfg.cube_tilt_x, cfg.cube_tilt_y, 0))
        self.ui = GameUI()
        if cfg.mock_chat:
            self.chat = MockChat(self.handle_chat_message,
                                 list(VALID_MOVES) + list(GARBAGE),
                                 rng=self.rng)
        else:
            from streamkit import TwitchChat  # lazy: нужен twitchio и .env
            self.chat = TwitchChat(self.handle_chat_message, cfg.channel)
        self.vote_loop = VoteLoop(cfg.round_duration, self.on_round_end,
                                  validate=normalize, rng=self.rng)
        self.state = ""
        self.time_left = 0.0  # WIN-phase countdown (VOTING lives in vote_loop)
        self._aspect = 0.0
        self._fit_cube()
        self.new_game()

    def new_game(self) -> None:
        moves = self.cube.scramble(self.cfg.scramble_moves, self.rng)
        self.view.sync()
        print(f"scramble: {' '.join(moves)}", flush=True)
        self.start_round()

    def _fit_cube(self) -> None:
        self._aspect = window.aspect_ratio
        self.ui.relayout()
        # band free for the cube: from the top screen edge (the top sliver
        # slides under the opaque timer bar) down to the vote table
        self.view.fit_width(top_ui=0.5, bottom_ui=TABLE_TOP + 0.02)

    def start_round(self) -> None:
        self.vote_loop.start()
        self.state = VOTING
        self.ui.update_votes({}, None)

    def handle_chat_message(self, user: str, text: str) -> None:
        """Single entry point for chat commands (mock chat or Twitch)."""
        if self.state != VOTING:
            return
        if self.vote_loop.vote(user, text):
            leaders, _ = self.vote_loop.leaders()
            self.ui.update_votes(self.vote_loop.counts(),
                                 leaders[0] if leaders else None)

    def update(self) -> None:  # ursina per-frame hook
        if window.aspect_ratio != self._aspect:
            self._fit_cube()
        if self.state == VOTING:
            self.ui.set_timer(self.vote_loop.time_left, self.cfg.round_duration)
            if self.chat:
                self.chat.update(time.dt)
            self.vote_loop.update(time.dt)
        elif self.state == WIN:
            self.time_left -= time.dt
            self.ui.show_win(True, self.time_left)
            if self.time_left <= 0:
                self.ui.show_win(False)
                self.new_game()

    def on_round_end(self, move: str | None, counts: dict[str, int],
                     n_voters: int) -> None:
        if move is None:  # nobody voted — run the round again
            print("no votes, restarting round", flush=True)
            self.start_round()
            return
        print(f"winner: {move} ({n_voters} voters)", flush=True)
        self.state = APPLYING
        self.ui.set_timer(0, self.cfg.round_duration)
        self.cube.apply(move)
        self.view.animate_move(move, on_done=self.after_move)

    def after_move(self) -> None:
        if self.cube.is_solved():
            print("cube solved!", flush=True)
            self.state = WIN
            self.time_left = self.cfg.win_pause
            self.ui.show_win(True, self.time_left)
        else:
            self.start_round()
