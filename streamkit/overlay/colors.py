"""Color helpers for ursina overlays."""

from __future__ import annotations

from ursina import color


def hex_color(value: str):
    """'#RRGGBB' -> ursina Color (0-1 floats; 0-255 values clamp to white)."""
    s = value.lstrip("#")
    return color.Color(int(s[0:2], 16) / 255, int(s[2:4], 16) / 255,
                       int(s[4:6], 16) / 255, 1.0)
