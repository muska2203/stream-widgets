"""App config: game-specific fields; loading via streamkit's TOML loader."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from streamkit import load_toml_config


@dataclass
class Config:
    channel: str = ""
    round_duration: float = 15.0
    animation_duration: float = 2.5
    scramble_moves: int = 10
    win_pause: float = 10.0
    background_color: str = "#FF00FF"  # хромакей: не должен совпадать с цветами граней
    window_width: int = 800
    window_height: int = 900
    always_on_top: bool = False
    mock_chat: bool = True
    cube_tilt_x: float = -30.0  # наклон куба: вперёд/назад (показать верх/низ)
    cube_tilt_y: float = 35.0   # поворот куба влево/вправо


def load_config(path: str | Path | None = None) -> Config:
    if path is None:
        path = Path(__file__).resolve().parent / "config.toml"
    return load_toml_config(Config, path)
