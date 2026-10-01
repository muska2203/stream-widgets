"""Pure Rubik's cube model: state, moves, scramble, solved check.

Coordinate system: x = right, y = up, z = toward viewer (Front face).
Each face is a 3x3 grid viewed face-on with the cube held U-up, F-front:

    U: row 0 = back  side, col 0 = left
    D: row 0 = front side, col 0 = left
    F: row 0 = up,         col 0 = left
    B: row 0 = up,         col 0 = right (viewed from behind)
    R: row 0 = up,         col 0 = front
    L: row 0 = up,         col 0 = back

Chat commands (case-insensitive):
    u1..u3  column N up      (columns numbered left->right as seen from front)
    d1..d3  column N down
    r1..r3  row N right      (rows numbered top->bottom)
    l1..l3  row N left
    wu/wd/wl/wr  whole-cube rotation up/down/left/right
"""

from __future__ import annotations

import random

FACES = ("U", "D", "F", "B", "L", "R")
FACE_COLORS = {"U": "W", "D": "Y", "F": "G", "B": "B", "L": "O", "R": "R"}

VALID_MOVES = tuple(f"{p}{i}" for p in "udlr" for i in (1, 2, 3)) + (
    "wu", "wd", "wl", "wr",
)

_INVERSE = {}
for _p, _q in (("u", "d"), ("d", "u"), ("r", "l"), ("l", "r")):
    for _i in (1, 2, 3):
        _INVERSE[f"{_p}{_i}"] = f"{_q}{_i}"
_INVERSE.update({"wu": "wd", "wd": "wu", "wl": "wr", "wr": "wl"})


def inverse(move: str) -> str:
    """Return the move that undoes `move`."""
    return _INVERSE[normalize(move)]


def move_info(move: str) -> tuple[str | None, int | None, str]:
    """Describe a move for rendering: (axis, layer, direction).

    axis is "x" or "y" (None for whole-cube moves), layer is the axis
    coordinate of the rotating slice in {-1, 0, 1} (None for whole-cube),
    direction is "cw" (front->up / front->right) or "ccw".
    """
    rot, axis, layer = _MOVE_TABLE[normalize(move)]
    direction = "cw" if rot in (_rot_x_cw, _rot_y_cw) else "ccw"
    axis_name = {0: "x", 1: "y", None: None}[axis]
    return axis_name, layer, direction


def normalize(move: str) -> str:
    """Validate and canonicalize a chat command; raise ValueError if invalid."""
    m = move.strip().lower()
    if m not in VALID_MOVES:
        raise ValueError(f"invalid move: {move!r}")
    return m


def sticker_transform(face: str, r: int, c: int) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """(position, normal) of facelet (face, row, col) in cube coordinates."""
    return _TO_POS[face](r, c), _NORMALS[face]


# 90-degree rotations of a (x, y, z) vector. All components stay in {-1, 0, 1}.

def _rot_x_cw(p):  # around x, front -> up
    x, y, z = p
    return (x, z, -y)


def _rot_x_ccw(p):  # around x, front -> down
    x, y, z = p
    return (x, -z, y)


def _rot_y_cw(p):  # around y, front -> right
    x, y, z = p
    return (z, y, -x)


def _rot_y_ccw(p):  # around y, front -> left
    x, y, z = p
    return (-z, y, x)


_TO_POS = {
    "F": lambda r, c: (c - 1, 1 - r, 1),
    "B": lambda r, c: (1 - c, 1 - r, -1),
    "U": lambda r, c: (c - 1, 1, r - 1),
    "D": lambda r, c: (c - 1, -1, 1 - r),
    "R": lambda r, c: (1, 1 - r, 1 - c),
    "L": lambda r, c: (-1, 1 - r, c - 1),
}

_NORMALS = {
    "F": (0, 0, 1), "B": (0, 0, -1), "U": (0, 1, 0),
    "D": (0, -1, 0), "R": (1, 0, 0), "L": (-1, 0, 0),
}

# normal -> (position -> (face, row, col))
_FROM_POS = {
    (0, 0, 1): lambda p: ("F", 1 - p[1], p[0] + 1),
    (0, 0, -1): lambda p: ("B", 1 - p[1], 1 - p[0]),
    (0, 1, 0): lambda p: ("U", p[2] + 1, p[0] + 1),
    (0, -1, 0): lambda p: ("D", 1 - p[2], p[0] + 1),
    (1, 0, 0): lambda p: ("R", 1 - p[1], 1 - p[2]),
    (-1, 0, 0): lambda p: ("L", 1 - p[1], p[2] + 1),
}

# move -> (rotation, axis_index, layer_value); axis/layer None = whole cube
_MOVE_TABLE = {
    "wu": (_rot_x_cw, None, None),
    "wd": (_rot_x_ccw, None, None),
    "wr": (_rot_y_cw, None, None),
    "wl": (_rot_y_ccw, None, None),
}
for _i in (1, 2, 3):
    _MOVE_TABLE[f"u{_i}"] = (_rot_x_cw, 0, _i - 2)   # column i, x = i-2
    _MOVE_TABLE[f"d{_i}"] = (_rot_x_ccw, 0, _i - 2)
    _MOVE_TABLE[f"r{_i}"] = (_rot_y_cw, 1, 2 - _i)   # row i, y = 2-i
    _MOVE_TABLE[f"l{_i}"] = (_rot_y_ccw, 1, 2 - _i)


class Cube:
    """A 3x3 Rubik's cube. `faces` maps face name -> 3x3 list of color chars."""

    def __init__(self):
        self.faces = {f: [[FACE_COLORS[f]] * 3 for _ in range(3)] for f in FACES}

    def copy(self) -> Cube:
        c = Cube.__new__(Cube)
        c.faces = {f: [row[:] for row in grid] for f, grid in self.faces.items()}
        return c

    def apply(self, move: str) -> None:
        rot, axis, layer = _MOVE_TABLE[normalize(move)]
        stickers = []
        for face, grid in self.faces.items():
            for r in range(3):
                for c in range(3):
                    stickers.append((_TO_POS[face](r, c), _NORMALS[face], grid[r][c]))

        new = {f: [[None] * 3 for _ in range(3)] for f in FACES}
        for pos, normal, color in stickers:
            if axis is None or pos[axis] == layer:
                pos = rot(pos)
                normal = rot(normal)
            f, r, c = _FROM_POS[normal](pos)
            new[f][r][c] = color
        self.faces = new

    def apply_sequence(self, moves) -> None:
        for m in moves:
            self.apply(m)

    def is_solved(self) -> bool:
        return all(
            all(cell == grid[0][0] for row in grid for cell in row)
            for grid in self.faces.values()
        )

    def scramble(self, count: int = 10, rng: random.Random | None = None) -> list[str]:
        """Apply `count` random moves (never a direct undo of the previous one)."""
        rng = rng or random
        moves = []
        while len(moves) < count:
            m = rng.choice(VALID_MOVES)
            if moves and m == _INVERSE[moves[-1]]:
                continue
            moves.append(m)
        self.apply_sequence(moves)
        return moves

    def __eq__(self, other):
        return isinstance(other, Cube) and self.faces == other.faces

    def __str__(self) -> str:
        f = self.faces

        def row(face, r):
            return " ".join(f[face][r])

        lines = [f"      {row('U', r)}" for r in range(3)]
        for r in range(3):
            lines.append(f"{row('L', r)}  {row('F', r)}  {row('R', r)}  {row('B', r)}")
        lines += [f"      {row('D', r)}" for r in range(3)]
        return "\n".join(lines)
