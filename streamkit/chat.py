"""Chat sources: Twitch IRC adapter and a mock generator.

Both share the same interface: the host app passes an `on_message(user, text)`
callback and calls `update(dt)` every frame from its main loop; queued
messages are forwarded to the callback from the main thread.

`twitchio` is imported lazily inside TwitchChat so the core package works
without it installed.
"""

from __future__ import annotations

import queue
import random
import threading
from pathlib import Path
from typing import Callable, Sequence

from streamkit.config import load_env
from streamkit.paths import frozen_app_dir

MessageCallback = Callable[[str, str], None]

MOCK_USERS = tuple(f"viewer{i}" for i in range(12))


class TwitchChat:
    def __init__(self, on_message: MessageCallback, channel: str,
                 env_path: str | Path | None = None):
        if env_path is None:
            frozen = frozen_app_dir()
            env_path = (frozen / ".env") if frozen else Path(".env")
        token = load_env(env_path).get("TWITCH_TOKEN", "")
        if not token:
            raise RuntimeError(
                "TWITCH_TOKEN не найден в .env — получи токен со scope "
                "chat:read на twitchtokengenerator.com и добавь в .env "
                "(см. .env.example), или включи mock_chat = true в config.toml"
            )
        if not channel:
            raise RuntimeError("channel не задан в config.toml")
        self.on_message = on_message
        self.incoming: queue.Queue[tuple[str, str]] = queue.Queue()
        self._token = token
        self._channel = channel
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        # Python 3.12+: get_event_loop() падает без явно созданного цикла,
        # а TwitchIO 2.x берёт цикл из __init__ — создаём его в этом потоке.
        import asyncio
        asyncio.set_event_loop(asyncio.new_event_loop())
        from twitchio import Client

        class _ChatClient(Client):
            def __init__(self, token: str, channel: str, out: queue.Queue):
                super().__init__(token=token, initial_channels=[channel])
                self._out = out
                self._channel = channel

            async def event_ready(self):
                print(f"twitch: connected as {self.nick}, "
                      f"channel #{self._channel}", flush=True)

            async def event_message(self, message):
                if message.author is None:
                    return
                # echo (сообщения аккаунта токена) НЕ отсекаем: приложения
                # сами в чат не пишут, а стримеру собственные сообщения
                # нужны для сольного теста и участия в голосовании
                # name — логин (всегда lowercase), display_name — ник с
                # регистром, как его видят зрители; в голосованиях и базе
                # чаттеров используем именно его
                user = message.author.display_name or message.author.name
                self._out.put((user, message.content))

        try:
            _ChatClient(self._token, self._channel, self.incoming).run()
        except Exception as e:
            print(f"twitch: соединение завершилось с ошибкой: {e!r}", flush=True)

    def update(self, dt: float = 0.0) -> None:
        while True:
            try:
                user, text = self.incoming.get_nowait()
            except queue.Empty:
                return
            self.on_message(user, text)


class MockChat:
    """Fake viewers voting at random, for development without Twitch.

    `messages` is the pool of texts viewers may send (include garbage to
    exercise filtering on the app side — MockChat does not filter).
    """

    def __init__(self, on_message: MessageCallback, messages: Sequence[str],
                 users: Sequence[str] = MOCK_USERS, interval: float = 0.35,
                 rng: random.Random | None = None):
        self.on_message = on_message
        self.messages = list(messages)
        self.users = list(users)
        self.interval = interval
        self.rng = rng or random.Random()
        self.timer = interval

    def update(self, dt: float) -> None:
        self.timer -= dt
        if self.timer > 0:
            return
        self.timer = self.interval
        for _ in range(self.rng.randint(0, 3)):
            self.on_message(self.rng.choice(self.users),
                            self.rng.choice(self.messages))
