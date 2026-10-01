"""Offscreen render check: py apps/rubiks_cube/tools/render_check.py

Screenshots land in apps/rubiks_cube/tools/shots/ regardless of the cwd
(Panda3D accepts only relative forward-slash paths, so we chdir first).

Verifies the 3/4 default view and mid-animation rotation directions.
Sequential steps with generous delays (startup frames are slow).
"""

import builtins
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root

from panda3d.core import Filename, loadPrcFileData

loadPrcFileData("", "window-type offscreen")

from ursina import Ursina, color, invoke, window  # noqa: E402

from apps.rubiks_cube.core import Cube  # noqa: E402
from apps.rubiks_cube.cube_view import CubeView  # noqa: E402

os.chdir(Path(__file__).resolve().parent)
Path("shots").mkdir(exist_ok=True)

app = Ursina(development_mode=False)
window.size = (800, 900)
window.color = color.rgb(0, 255, 0)

cube = Cube()
view = CubeView(cube, animation_duration=2.0)  # default 3/4 tilt


def shot(name):
    ok = builtins.base.win.save_screenshot(Filename(f"shots/{name}"))
    print(f"saved {name}: {ok}", flush=True)


def reset(move=None):
    global cube
    cube = Cube()
    view.cube = cube
    if move:
        cube.apply(move)
    view.sync()
    print(f"state: move={move}", flush=True)


def start_anim(move):
    cube.apply(move)
    view.animate_move(move)
    print(f"animating: {move}", flush=True)


# t=2: solved 3/4 view -> white top, green front, red right
# t=4: animate u1; t=5 mid (front left column halfway UP); t=7.5 after
# t=9: animate r1; t=10 mid (front top row halfway RIGHT); t=11.5 after
invoke(lambda: shot("view_34.png"), delay=2.0)
invoke(lambda: start_anim("u1"), delay=4.0)
invoke(lambda: shot("anim_mid_u1.png"), delay=5.0)
invoke(lambda: shot("anim_after_u1.png"), delay=6.5)
invoke(lambda: reset(), delay=8.0)
invoke(lambda: start_anim("r1"), delay=9.0)
invoke(lambda: shot("anim_mid_r1.png"), delay=10.0)
invoke(lambda: shot("anim_after_r1.png"), delay=11.5)
# whole-cube move: all rows turn together, front goes right
invoke(lambda: reset(), delay=13.0)
invoke(lambda: start_anim("wr"), delay=14.0)
invoke(lambda: shot("anim_mid_wr.png"), delay=15.0)
invoke(lambda: shot("anim_after_wr.png"), delay=16.5)
# middle slice: the inner core is directly visible through the opened gaps
invoke(lambda: reset(), delay=18.0)
invoke(lambda: start_anim("u2"), delay=19.0)
invoke(lambda: shot("anim_mid_u2.png"), delay=20.0)
invoke(lambda: shot("anim_after_u2.png"), delay=21.5)
invoke(lambda: (print("done", flush=True), os._exit(0)), delay=23.0)

app.run()
