"""App config: game-specific fields; loading via streamkit's TOML loader."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from streamkit import load_toml_config


@dataclass
class Config:
    channel: str = ""
    event_duration: float = 15.0        # секунд на выбор двери чатом
    hero_cooldown: float = 5.0          # базовый КД атаки героя, сек
    agility_cd_reduction: float = 0.5   # −сек к КД героя за очко Ловкости
    min_cooldown: float = 1.0           # нижний предел КД героя, сек
    chatter_cd_min: float = 3.0         # диапазон броска КД чаттера отряда, сек
    chatter_cd_max: float = 8.0
    chat_damage_pct: int = 5            # DPS чаттера отряда = % от среднего DPS героя
    chat_damage_cap_pct: int = 100      # макс. атакующих в отряде = cap // pct
    levelup_duration: float = 15.0      # секунд на выбор статы при апе
    shop_duration: float = 25.0         # секунд на голосование в магазине
    overtime_duration: float = 5.0      # овертайм голосования при 0 голосов (один раз на раунд)
    combat_end_pause: float = 4.0       # пауза после боя до следующего события
    gameover_pause: float = 15.0        # экран итогов забега
    tie_resolve_pause: float = 3.0      # рулетка при ничьей (моргание лидеров)
    vote_mode: str = "words"            # "words" (случайные слова раунда) | "classic" (фиксированные команды)
    base_hp: int = 20                   # базовое HP героя (плюс 5×ВЫН)
    seed: int | None = None             # seed для MockChat/тай-брейков (None = случайно)
    overlay_port: int = 8766            # порт веб-оверлея (OBS Browser Source)
    mock_chat: bool = False


VOTE_MODES = ("words", "classic")


def default_config_path() -> Path:
    return Path(__file__).resolve().parent / "config.toml"


def load_config(path: str | Path | None = None) -> Config:
    if path is None:
        path = default_config_path()
    cfg = load_toml_config(Config, path)
    if cfg.vote_mode not in VOTE_MODES:
        raise ValueError(f"vote_mode должен быть одним из {VOTE_MODES}, "
                         f"получено {cfg.vote_mode!r}")
    return cfg
