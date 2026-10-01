"""Borderless chroma-key overlay window setup for OBS capture.

`create_overlay` reads window_width / window_height / background_color /
always_on_top from the passed config object via getattr with defaults, so
any dataclass or namespace with those attributes works.
"""

from __future__ import annotations

import builtins

from ursina import Ursina, window

from streamkit.overlay.colors import hex_color


def set_always_on_top() -> None:
    from panda3d.core import WindowProperties
    props = WindowProperties()
    props.set_z_order(WindowProperties.Z_top)
    builtins.base.win.request_properties(props)


def create_overlay(cfg, title: str = "StreamKit overlay") -> Ursina:
    """Ursina app with a borderless chroma-key window, OBS-ready."""
    app = Ursina(title=title, development_mode=False,
                 show_ursina_splash=False)
    window.borderless = True
    window.fullscreen = False
    window.size = (getattr(cfg, "window_width", 800),
                   getattr(cfg, "window_height", 900))
    window.color = hex_color(getattr(cfg, "background_color", "#FF00FF"))
    window.exit_button.visible = False
    window.fps_counter.enabled = False
    if getattr(cfg, "always_on_top", False):
        set_always_on_top()
    return app
