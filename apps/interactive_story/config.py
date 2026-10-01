"""App config: game-specific fields; loading via streamkit's TOML loader."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from streamkit import frozen_app_dir, load_toml_config


@dataclass
class Config:
    channel: str = ""
    select_duration: float = 20.0  # секунд на выбор истории чатом
    round_duration: float = 25.0   # секунд на ход целиком
    outcome_pause: float = 8.0     # показ последствий выбора
    sleep_duration: float = 30.0   # сон между ходами (скрыт контент, шапка с таймером остаётся)
    end_pause: float = 15.0        # экран концовки
    seed: int | None = None        # seed для MockChat/тай-брейков (None = случайно)
    overlay_port: int = 8765       # порт веб-оверлея (OBS Browser Source)
    mock_chat: bool = True


def default_config_path() -> Path:
    """Frozen builds read config.toml next to the exe; dev runs use the
    file bundled with the app."""
    frozen = frozen_app_dir()
    return ((frozen / "config.toml") if frozen
            else Path(__file__).resolve().parent / "config.toml")


def load_config(path: str | Path | None = None) -> Config:
    if path is None:
        path = default_config_path()
    return load_toml_config(Config, path)
