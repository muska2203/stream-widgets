"""First-run setup for frozen builds: extract user-editable defaults next to
the exe and, when the config is incomplete (no channel / no Twitch token),
ask for them in a small tkinter wizard before the game window opens.

File helpers (write_token, set_channel, needs_setup) are pure and
unit-tested; the tkinter window is a thin layer over them. Dev runs are
unaffected unless --setup is passed explicitly.
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

from streamkit import bundled_defaults_dir, frozen_app_dir, load_env

from apps.interactive_story.config import Config, default_config_path, load_config

TOKEN_KEY = "TWITCH_TOKEN"
TOKEN_URL = "https://twitchtokengenerator.com"


def needs_setup(cfg: Config, env_path: str | Path) -> bool:
    """Live chat needs a channel and a token; mock chat needs nothing."""
    if cfg.mock_chat:
        return False
    if not cfg.channel:
        return True
    return not load_env(env_path).get(TOKEN_KEY, "")


def ensure_user_files() -> None:
    """Frozen builds: copy bundled defaults (config.toml, .env.example,
    stories/) next to the exe when missing. No-op in dev runs."""
    frozen = frozen_app_dir()
    defaults = bundled_defaults_dir()
    if frozen is None or defaults is None:
        return
    for name in ("config.toml", ".env.example"):
        dst = frozen / name
        if not dst.exists() and (defaults / name).exists():
            shutil.copy(defaults / name, dst)
    src = defaults / "stories"
    dst = frozen / "stories"
    if src.is_dir():
        dst.mkdir(exist_ok=True)
        for f in src.glob("*.toml"):
            if not (dst / f.name).exists():
                shutil.copy(f, dst / f.name)


def write_token(env_path: str | Path, token: str) -> None:
    """Create or update the TWITCH_TOKEN line in the .env file."""
    env_path = Path(env_path)
    lines = (env_path.read_text(encoding="utf-8").splitlines()
             if env_path.exists() else [])
    prefix = f"{TOKEN_KEY}="
    for i, line in enumerate(lines):
        if line.strip().startswith(prefix):
            lines[i] = prefix + token
            break
    else:
        lines.append(prefix + token)
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def set_channel(config_path: str | Path, channel: str) -> None:
    """Set or add the top-level `channel = "..."` key in config.toml."""
    config_path = Path(config_path)
    text = (config_path.read_text(encoding="utf-8")
            if config_path.exists() else "")
    line = f'channel = "{channel}"'
    new, n = re.subn(r"(?m)^channel\s*=.*$", line, text)
    if not n:
        new = text.rstrip("\n") + ("\n" if text.strip() else "") + line + "\n"
    config_path.write_text(new, encoding="utf-8")


def run_wizard(channel: str = "") -> tuple[str, str] | None:
    """Modal tkinter dialog: channel + OAuth token. None when cancelled."""
    import tkinter as tk
    import webbrowser

    result: list[tuple[str, str]] = []

    root = tk.Tk()
    root.title("Interactive Story — первоначальная настройка")
    root.resizable(False, False)
    pad = {"padx": 12, "pady": 4}

    tk.Label(root, text="Канал Twitch (ник):",
             anchor="w").grid(row=0, column=0, sticky="w", **pad)
    channel_var = tk.StringVar(value=channel)
    tk.Entry(root, textvariable=channel_var,
             width=36).grid(row=0, column=1, **pad)

    tk.Label(root, text="OAuth-токен (scope chat:read):",
             anchor="w").grid(row=1, column=0, sticky="w", **pad)
    token_var = tk.StringVar()
    tk.Entry(root, textvariable=token_var, width=36,
             show="*").grid(row=1, column=1, **pad)

    link = tk.Label(root, fg="blue", cursor="hand2",
                    text="Получить токен: twitchtokengenerator.com "
                         "(Custom Scope → Chat: Read)")
    link.grid(row=2, column=0, columnspan=2, sticky="w", **pad)
    link.bind("<Button-1>", lambda e: webbrowser.open(TOKEN_URL))

    error_var = tk.StringVar()
    tk.Label(root, textvariable=error_var,
             fg="red").grid(row=3, column=0, columnspan=2, sticky="w", **pad)

    def save() -> None:
        ch = channel_var.get().strip().lstrip("#")
        tok = token_var.get().strip()
        if not ch or not tok:
            error_var.set("Заполни оба поля.")
            return
        if not tok.startswith("oauth:"):
            tok = "oauth:" + tok
        result.append((ch, tok))
        root.destroy()

    btns = tk.Frame(root)
    btns.grid(row=4, column=0, columnspan=2, sticky="e", **pad)
    tk.Button(btns, text="Сохранить и запустить",
              command=save).pack(side="left", padx=4)
    tk.Button(btns, text="Отмена", command=root.destroy).pack(side="left",
                                                              padx=4)
    root.mainloop()
    return result[0] if result else None


def run_setup_if_needed() -> bool:
    """Frozen builds (or --setup in dev): extract defaults, then show the
    wizard when the config is incomplete. False = user cancelled, exit."""
    frozen = frozen_app_dir()
    if frozen is None and "--setup" not in sys.argv:
        return True
    ensure_user_files()
    cfg = load_config()
    env_path = (frozen / ".env") if frozen else Path(".env")
    if not needs_setup(cfg, env_path):
        return True
    res = run_wizard(cfg.channel)
    if res is None:
        print("setup cancelled, exiting", flush=True)
        return False
    channel, token = res
    write_token(env_path, token)
    set_channel(default_config_path(), channel)
    print(f"setup saved: channel={channel}", flush=True)
    return True
