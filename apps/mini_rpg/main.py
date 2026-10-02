"""Entry point: py -m apps.mini_rpg [--smoke] [--mock]

Консольное приложение: игровой цикл на monotonic, оверлей — локальная
веб-страница (OBS Browser Source, адрес печатается при старте).
--smoke — авто-выход через 20 с (всегда с мок-чатом, живой Twitch не
трогает); --mock — принудительный мок-чат независимо от config.toml.
"""

from __future__ import annotations

import random
import sys
import time
from pathlib import Path

from apps.mini_rpg.config import Config, load_config
from apps.mini_rpg.game import Game
from apps.mini_rpg.server import OverlayServer
from apps.mini_rpg.webui import WebUI

TICK = 1 / 60
SMOKE_SECONDS = 20.0

# база ников чаттеров для боевых кличек мобов (только живой Twitch —
# мок-чат не засоряет файл)
CHATTERS_PATH = Path(__file__).resolve().parent / "chatters.json"

# чекпоинт прогресса забега между сессиями — тоже только в живом режиме
SAVE_PATH = Path(__file__).resolve().parent / "savegame.json"

# мусор для проверки фильтрации на стороне игры (цифры теперь тоже мусор —
# голосуют словами текущего раунда)
GARBAGE = ("hello", "gg", "a", "1", "7")


def _mock_pool(game: Game):
    """Пул сообщений мок-чата: преимущественно валидные слова активного
    голосования (перечитываются каждый тик — слова меняются каждый раунд)
    плюс немного мусора."""
    return lambda: game.current_vote_words() * 3 + list(GARBAGE)


def make_chat(cfg: Config, game: Game, force_mock: bool):
    from streamkit import MockChat
    if force_mock or cfg.mock_chat:
        return MockChat(game.handle_chat_message, _mock_pool(game),
                        rng=random.Random(cfg.seed))
    from streamkit import TwitchChat  # lazy: нужен twitchio и .env
    return TwitchChat(game.handle_chat_message, cfg.channel)


def main() -> None:
    smoke = "--smoke" in sys.argv
    cfg = load_config()
    use_mock = smoke or "--mock" in sys.argv or cfg.mock_chat
    from streamkit import ChatterRegistry
    # мок-режим — реестр в памяти: клички видны, но viewerN не пишутся в файл
    chatters = ChatterRegistry() if use_mock else ChatterRegistry(CHATTERS_PATH)
    game = Game(cfg, chatters=chatters,
                save_path=None if use_mock else SAVE_PATH)
    ui = WebUI(game)
    game.ui = ui
    chat = make_chat(cfg, game, force_mock=smoke or "--mock" in sys.argv)
    server = OverlayServer(ui, cfg.overlay_port)
    print(f"Оверлей: {server.url} — добавь этот адрес в OBS "
          f"(источник «Браузер» / Browser Source)", flush=True)

    started = time.monotonic()
    last = started
    try:
        while True:
            now = time.monotonic()
            dt = now - last
            last = now
            chat.update(dt)
            game.update(dt)
            if smoke and now - started >= SMOKE_SECONDS:
                break
            time.sleep(TICK)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()


if __name__ == "__main__":
    main()
