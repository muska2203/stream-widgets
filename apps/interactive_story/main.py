"""Entry point: py -m apps.interactive_story [--smoke] [--setup]

Консольное приложение: игровой цикл на monotonic, оверлей — локальная
веб-страница (OBS Browser Source, адрес печатается при старте).
"""

from __future__ import annotations

import sys
import time

from apps.interactive_story.config import load_config
from apps.interactive_story.game import Game
from apps.interactive_story.server import OverlayServer

TICK = 1 / 60
SMOKE_SECONDS = 20.0


def main() -> None:
    from apps.interactive_story.setup_wizard import run_setup_if_needed
    if not run_setup_if_needed():  # отмена в мастере настройки
        return
    cfg = load_config()
    game = Game(cfg)
    server = OverlayServer(game.ui, cfg.overlay_port)
    print(f"Оверлей: {server.url} — добавь этот адрес в OBS "
          f"(источник «Браузер» / Browser Source)", flush=True)

    smoke = "--smoke" in sys.argv
    started = time.monotonic()
    last = started
    try:
        while True:
            now = time.monotonic()
            game.update(now - last)
            last = now
            if smoke and now - started >= SMOKE_SECONDS:
                break
            time.sleep(TICK)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()


if __name__ == "__main__":
    main()
