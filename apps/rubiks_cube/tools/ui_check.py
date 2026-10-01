"""Offscreen UI check: py apps/rubiks_cube/tools/ui_check.py

Screenshots land in apps/rubiks_cube/tools/shots/ regardless of the cwd
(Panda3D accepts only relative forward-slash paths, so we chdir first).
"""

import builtins
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root

from panda3d.core import Filename, loadPrcFileData

loadPrcFileData("", "window-type offscreen")

from ursina import Ursina, color, invoke, window  # noqa: E402

from apps.rubiks_cube.config import Config  # noqa: E402
from apps.rubiks_cube.game import Game  # noqa: E402

os.chdir(Path(__file__).resolve().parent)
Path("shots").mkdir(exist_ok=True)

app = Ursina(development_mode=False)
window.size = (800, 900)
window.color = color.rgb(0, 255, 0)

cfg = Config(round_duration=30.0, animation_duration=0.8, mock_chat=True)
game = Game(cfg)
game.chat = None  # детерминированный тест: отключаем случайные голоса мок-чата


def shot(name):
    ok = builtins.base.win.save_screenshot(Filename(f"shots/{name}"))
    print(f"saved {name}: {ok}", flush=True)


def inject_votes():
    votes = [("a", "u1"), ("b", "u1"), ("c", "u1"), ("d", "r2"), ("e", "r2"),
             ("f", "wd"), ("g", "l3"), ("h", "spam"), ("a", "u2")]  # a revotes
    for user, move in votes:
        game.handle_chat_message(user, move)
    print("votes injected", flush=True)


invoke(inject_votes, delay=2.0)
invoke(lambda: shot("ui_voting.png"), delay=3.0)   # u2=1 leader? u1=2,r2=2 tie...
invoke(lambda: game.vote_loop.finish(), delay=4.0)
invoke(lambda: shot("ui_applying.png"), delay=4.4)
invoke(lambda: game.ui.show_win(True, 7), delay=6.0)
invoke(lambda: shot("ui_win.png"), delay=6.5)
invoke(lambda: (print("done", flush=True), os._exit(0)), delay=8.0)

app.run()
