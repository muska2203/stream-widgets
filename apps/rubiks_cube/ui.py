"""Stream overlay UI: top timer bar with outlined countdown, full-width vote
table at the bottom (bordered cells: flat pseudo-cube icon with the rotating
slice highlighted + direction arrow, command text and vote count), win
overlay."""

from __future__ import annotations

from ursina import Entity, Text, Texture, camera, color, window

from streamkit.overlay.crisp import CRISP_TEXT, CRISP_UNLIT

from apps.rubiks_cube.core import VALID_MOVES

VOTE_ROWS = [("u1", "u2", "u3", "wu"), ("d1", "d2", "d3", "wd"),
             ("l1", "l2", "l3", "wl"), ("r1", "r2", "r3", "wr")]

BAR_Y = 0.465
BAR_HEIGHT = 0.07

CELL_H = 0.075
BORDER = 0.004
TABLE_TOP = -0.5 + len(VOTE_ROWS) * CELL_H
ICON_SIZE = 0.05

COLOR_IDLE = color.gray
COLOR_ACTIVE = color.white
COLOR_LEADER = color.yellow
COLOR_CELL = color.rgba(0.05, 0.05, 0.05, 1)
COLOR_FRAME = color.gray

_ICON_TEXTURES: dict[str, Texture] = {}


def _move_icon(move: str) -> Texture:
    """Flat pseudo-cube icon: 3x3 grid, the rotating slice filled white
    (tinted by the entity color at runtime), a black arrow on top showing
    the turn direction (stays dark under the tint)."""
    if move in _ICON_TEXTURES:
        return _ICON_TEXTURES[move]
    from PIL import Image, ImageDraw

    size, margin, gap = 96, 8, 6
    cell = (size - 2 * margin - 2 * gap) // 3
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    prefix = move[0]
    idx = int(move[1]) - 1 if move[1].isdigit() else None

    def highlighted(r: int, c: int) -> bool:
        if prefix == "w":
            return True
        if prefix in "ud":
            return c == idx
        return r == idx

    for r in range(3):
        for c in range(3):
            x0, y0 = margin + c * (cell + gap), margin + r * (cell + gap)
            d.rounded_rectangle([x0, y0, x0 + cell, y0 + cell], radius=4,
                                fill=(255, 255, 255, 255) if highlighted(r, c)
                                else (24, 24, 24, 255))

    # arrow: u/wu up, d/wd down, l/wl left, r/wr right; slice moves run
    # along the highlighted line, whole-cube moves span the icon center
    direction = move[1] if prefix == "w" else prefix
    horizontal = direction in "lr"
    negative = direction in "ul"
    center = (size / 2 if prefix == "w"
              else margin + idx * (cell + gap) + cell / 2)

    lo, hi = 12.0, size - 12.0
    width, head = 5, 9
    if horizontal:
        line = [(lo, center), (hi, center)]
        tip = (lo, center) if negative else (hi, center)
        sign = -1 if negative else 1
        poly = [tip, (tip[0] - sign * head, center - head),
                (tip[0] - sign * head, center + head)]
    else:
        line = [(center, lo), (center, hi)]
        tip = (center, lo) if negative else (center, hi)
        sign = -1 if negative else 1
        poly = [tip, (center - head, tip[1] - sign * head),
                (center + head, tip[1] - sign * head)]
    d.line(line, fill=(0, 0, 0, 255), width=width)
    d.polygon(poly, fill=(0, 0, 0, 255))

    _ICON_TEXTURES[move] = Texture(img)
    return _ICON_TEXTURES[move]


_OUTLINE_D = 0.0028
_OUTLINE_OFFSETS = [(dx, dy) for dx in (-_OUTLINE_D, 0, _OUTLINE_D)
                    for dy in (-_OUTLINE_D, 0, _OUTLINE_D) if dx or dy]


class _OutlinedText:
    """Centered text with a fake outline: 8 dark copies offset around it."""

    def __init__(self, y: float, scale: float, fg=color.white, bg=color.black):
        self.parts = [Text("", parent=camera.ui, x=dx, y=y + dy, origin=(0, 0),
                           scale=scale, color=bg, z=-0.02, shader=CRISP_TEXT)
                      for dx, dy in _OUTLINE_OFFSETS]
        self.main = Text("", parent=camera.ui, y=y, origin=(0, 0), scale=scale,
                         color=fg, z=-0.03, shader=CRISP_TEXT)

    def set(self, text: str) -> None:
        self.main.text = text
        for part in self.parts:
            part.text = text


class GameUI:
    def __init__(self):
        # top bar: dark track, azure fill that drains, countdown on the bar
        self.timer_track = Entity(parent=camera.ui, model="quad", y=BAR_Y,
                                  scale=(window.aspect_ratio, BAR_HEIGHT),
                                  color=color.dark_gray)
        self.timer_fill = Entity(parent=camera.ui, model="quad", y=BAR_Y, z=-0.01,
                                 scale=(window.aspect_ratio, BAR_HEIGHT),
                                 color=color.azure)
        self.timer_text = _OutlinedText(y=BAR_Y, scale=1.6)

        # vote table: one frame quad (borders show through the gaps between
        # cell backgrounds), one background quad + icon + label per cell
        self.table_frame = Entity(parent=camera.ui, model="quad",
                                  color=COLOR_FRAME, z=0.01)
        self.cells: dict[str, Entity] = {}
        self.icons: dict[str, Entity] = {}
        self.labels: dict[str, Text] = {}
        for row in VOTE_ROWS:
            for move in row:
                self.cells[move] = Entity(parent=camera.ui, model="quad",
                                          color=COLOR_CELL)
                self.icons[move] = Entity(parent=camera.ui, model="quad",
                                          texture=_move_icon(move),
                                          scale=ICON_SIZE, z=-0.01,
                                          shader=CRISP_UNLIT)
                self.labels[move] = Text("", parent=camera.ui,
                                         origin=(-0.5, 0), scale=1.15,
                                         z=-0.02, shader=CRISP_TEXT)
        self.relayout()

        self.win_overlay = Entity(parent=camera.ui, model="quad",
                                  color=color.rgba(0, 0, 0, 190),
                                  scale=(2, 2), z=-0.1, enabled=False)
        self.win_text = Text("КУБ СОБРАН!", parent=camera.ui, y=0.05,
                             origin=(0, 0), scale=3, color=color.yellow,
                             z=-0.2, enabled=False, shader=CRISP_TEXT)
        self.win_sub = Text("", parent=camera.ui, y=-0.05, origin=(0, 0),
                            scale=1.3, z=-0.2, enabled=False, shader=CRISP_TEXT)

        self.update_votes({}, None)

    def relayout(self) -> None:
        """Spread the vote table over the full window width (re-read on
        resize, same as the timer bar)."""
        w = window.aspect_ratio
        cols = len(VOTE_ROWS[0])
        cw = w / cols
        table_h = len(VOTE_ROWS) * CELL_H
        self.table_frame.scale = (w, table_h)
        self.table_frame.y = -0.5 + table_h / 2
        for row_i, row in enumerate(VOTE_ROWS):
            for col_i, move in enumerate(row):
                cx = -w / 2 + cw * (col_i + 0.5)
                cy = TABLE_TOP - CELL_H * (row_i + 0.5)
                self.cells[move].scale = (cw - BORDER, CELL_H - BORDER)
                self.cells[move].x, self.cells[move].y = cx, cy
                self.icons[move].x = cx - cw / 2 + 0.045
                self.icons[move].y = cy
                self.labels[move].x = cx - cw / 2 + 0.08
                self.labels[move].y = cy

    def update_votes(self, counts: dict[str, int], leader: str | None) -> None:
        for move in VALID_MOVES:
            n = counts.get(move, 0)
            c = (COLOR_LEADER if move == leader
                 else COLOR_ACTIVE if n else COLOR_IDLE)
            self.labels[move].text = f"{move}: {n}"
            self.labels[move].color = c
            self.icons[move].color = c

    def set_timer(self, remaining: float, total: float) -> None:
        frac = max(remaining, 0.0) / total if total else 0.0
        # the bar spans exactly the window width (re-read every call: resize)
        width = window.aspect_ratio
        self.timer_track.scale_x = width
        # keep the left edge pinned: shrink width and shift center left
        self.timer_fill.scale_x = width * frac
        self.timer_fill.x = -width * (1 - frac) / 2
        self.timer_text.set(f"{remaining:.0f}")

    def show_win(self, show: bool, countdown: float = 0.0) -> None:
        self.win_overlay.enabled = show
        self.win_text.enabled = show
        self.win_sub.enabled = show
        if show:
            self.win_sub.text = f"новая перемешка через {countdown:.0f}..."
