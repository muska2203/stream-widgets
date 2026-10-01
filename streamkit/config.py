"""Config loading helpers: generic TOML->dataclass loader and .env parser."""

from __future__ import annotations

import tomllib
from dataclasses import fields
from pathlib import Path


def load_toml_config(cls, path: str | Path = "config.toml"):
    """Build dataclass `cls` from a TOML file.

    Unknown TOML keys are ignored; a missing file means all defaults.
    """
    p = Path(path)
    if not p.exists():
        return cls()
    data = tomllib.loads(p.read_text(encoding="utf-8"))
    known = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in data.items() if k in known})


def load_env(path: str | Path = ".env") -> dict[str, str]:
    """Minimal .env parser (key=value lines, # comments).

    Tolerates Windows editors saving in cp1251 instead of UTF-8.
    """
    env = {}
    p = Path(path)
    if not p.exists():
        return env
    raw = p.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1251")
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env
