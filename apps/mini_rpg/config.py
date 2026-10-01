"""App config: game-specific fields; loading via streamkit's TOML loader."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from streamkit import load_toml_config


@dataclass
class Config:
    channel: str = ""
    event_duration: float = 15.0        # секунд на выбор двери чатом
    combat_duration: float = 12.0       # секунд на одно голосование в бою
    combat_outcome_pause: float = 2.5   # показ итога хода боя
    levelup_duration: float = 15.0      # секунд на выбор статы при апе
    shop_duration: float = 25.0         # секунд на голосование в магазине
    combat_end_pause: float = 4.0       # пауза после боя до следующего события
    gameover_pause: float = 15.0        # экран итогов забега
    tie_resolve_pause: float = 3.0      # рулетка при ничьей (моргание лидеров)
    base_hp: int = 20                   # базовое HP героя (плюс 5×ВЫН)
    seed: int | None = None             # seed для MockChat/тай-брейков (None = случайно)
    overlay_port: int = 8766            # порт веб-оверлея (OBS Browser Source)
    mock_chat: bool = False


def default_config_path() -> Path:
    return Path(__file__).resolve().parent / "config.toml"


def load_config(path: str | Path | None = None) -> Config:
    if path is None:
        path = default_config_path()
    return load_toml_config(Config, path)
