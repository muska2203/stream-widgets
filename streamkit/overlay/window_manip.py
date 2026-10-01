"""Borderless window manipulation: drag to move, drag right/bottom edge to resize.

ЛКМ по окну — перетаскивание; ЛКМ в полосе у правого/нижнего края (или угла) —
ресайз. Позиция курсора берётся в экранных координатах через Win32
GetCursorPos (оконные координаты «замораживаются» при движении окна).
Windows-only, как и весь проект.
"""

from __future__ import annotations

import builtins
import ctypes

from ursina import Entity, mouse
from panda3d.core import WindowProperties

EDGE_MARGIN = 12  # px, зона ресайза у правого/нижнего края
MIN_WIDTH, MIN_HEIGHT = 320, 240

_IDC_ARROW = 32512
_IDC_SIZENWSE = 32642
_IDC_SIZEWE = 32644
_IDC_SIZENS = 32645


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def _cursor_screen_pos() -> tuple[int, int]:
    p = _POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def _set_cursor(idc: int) -> None:
    try:
        ctypes.windll.user32.SetCursor(ctypes.windll.user32.LoadCursorW(None, idc))
    except OSError:
        pass


class WindowManipulator(Entity):
    """ЛКМ-перетаскивание окна и ресайз за правый/нижний край."""

    def __init__(self, edge_margin: int = EDGE_MARGIN,
                 min_size: tuple[int, int] = (MIN_WIDTH, MIN_HEIGHT)):
        super().__init__()
        self.edge_margin = edge_margin
        self.min_size = min_size
        self.mode: tuple | None = None  # ("move",) | ("resize", right, bottom)
        self._grab = (0, 0)    # экранные координаты курсора в момент нажатия
        self._origin = (0, 0)  # origin окна в момент нажатия
        self._size = (0, 0)    # размер окна в момент нажатия

    def _zone(self, x: float, y: float, w: int, h: int) -> tuple[bool, bool] | None:
        if x < 0 or y < 0 or x >= w or y >= h:
            return None
        right = x >= w - self.edge_margin
        bottom = y >= h - self.edge_margin
        return (right, bottom) if (right or bottom) else None

    def update(self) -> None:  # ursina per-frame hook
        win = builtins.base.win
        props = win.get_properties()
        w, h = props.get_size()
        ptr = win.get_pointer(0)

        if self.mode is None:
            zone = self._zone(ptr.get_x(), ptr.get_y(), w, h)
            if zone is None:
                _set_cursor(_IDC_ARROW)
            elif zone[0] and zone[1]:
                _set_cursor(_IDC_SIZENWSE)
            elif zone[0]:
                _set_cursor(_IDC_SIZEWE)
            else:
                _set_cursor(_IDC_SIZENS)
            if mouse.left:
                self.mode = ("resize", *zone) if zone else ("move",)
                self._grab = _cursor_screen_pos()
                self._origin = tuple(props.get_origin())
                self._size = (w, h)
            return

        if not mouse.left:
            self.mode = None
            return

        cx, cy = _cursor_screen_pos()
        dx, dy = cx - self._grab[0], cy - self._grab[1]
        req = WindowProperties()
        if self.mode[0] == "move":
            _set_cursor(_IDC_ARROW)
            req.set_origin(self._origin[0] + dx, self._origin[1] + dy)
        else:
            _, right, bottom = self.mode
            _set_cursor(_IDC_SIZENWSE if right and bottom
                        else _IDC_SIZEWE if right else _IDC_SIZENS)
            nw = self._size[0] + dx if right else self._size[0]
            nh = self._size[1] + dy if bottom else self._size[1]
            req.set_size(max(nw, self.min_size[0]), max(nh, self.min_size[1]))
        win.request_properties(req)
