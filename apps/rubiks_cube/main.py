"""Entry point: py -m apps.rubiks_cube [--smoke]"""

from __future__ import annotations

import sys

from ursina import invoke

from streamkit.overlay import WindowManipulator, create_overlay

from apps.rubiks_cube.config import load_config
from apps.rubiks_cube.game import Game


def main() -> None:
    cfg = load_config()
    app = create_overlay(cfg, title="Twitch Rubik's Cube")

    Game(cfg)
    WindowManipulator()  # ЛКМ — перетаскивание окна, край — ресайз

    if "--smoke" in sys.argv:  # auto-quit smoke test
        import os
        invoke(lambda: os._exit(0), delay=20.0)

    app.run()


if __name__ == "__main__":
    main()
