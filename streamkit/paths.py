"""Path helpers for frozen (PyInstaller) builds.

Dev runs keep their usual locations (app dir, repo root). Frozen builds keep
user-editable files (config.toml, .env, stories/) next to the exe; read-only
bundled defaults live in `sys._MEIPASS/defaults` and are copied out on first
run by the app.
"""

from __future__ import annotations

import sys
from pathlib import Path


def frozen_app_dir() -> Path | None:
    """Directory of the frozen exe, or None in a regular dev run."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return None


def bundled_defaults_dir() -> Path | None:
    """Read-only defaults inside the PyInstaller bundle, or None in dev."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass is None:
        return None
    return Path(meipass) / "defaults"


def bundled_dir() -> Path | None:
    """Root of the PyInstaller bundle (sys._MEIPASS), or None in dev.

    For read-only app assets packaged as data files (e.g. web overlay
    pages) — unlike bundled_defaults_dir, which is for defaults that get
    copied out next to the exe for the user to edit.
    """
    meipass = getattr(sys, "_MEIPASS", None)
    return Path(meipass) if meipass is not None else None
