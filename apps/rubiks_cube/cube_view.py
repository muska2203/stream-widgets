"""Ursina rendering of a core.Cube: 27 cubies + 54 sticker quads.

Render coordinates mirror the model's z axis (model +z = toward the viewer,
Ursina camera looks from -z), so render (x, y, z) = model (x, y, -z).
Rotation angles are calibrated for that mirror in _ANGLES.

Look: classic "black plastic" cube. Each sticker is a quad with a shared
procedural texture — white rounded fill inside a dark border ring — tinted by
the entity color (black stays black, the white fill takes the tint). The dark
cubie bodies show through the gaps, forming the grid lines between cells and
the outer frame; a dark inner core keeps rotating layers from opening a
see-through gap into the chroma-key background.
"""

from __future__ import annotations

import itertools

from ursina import Entity, Texture, Vec3, color, curve, destroy, invoke

from streamkit.overlay.crisp import CRISP_UNLIT

from apps.rubiks_cube.core import FACES, Cube, move_info, sticker_transform

STICKER_COLORS = {
    "W": color.white,
    "Y": color.yellow,
    "G": color.green,
    "B": color.blue,
    "O": color.orange,
    "R": color.red,
}

# ursina 8 color.rgb is an alias of rgba and takes 0-1 floats (0-255 clamps
# to white), so plain float colors are used here.
CUBIE_COLOR = color.Color(0.05, 0.05, 0.05, 1.0)

# half-extent of the whole cube including stickers, in model units
# (cubie centers at ±1, half cubie 0.48, sticker offset beyond that)
CUBE_HALF_EXTENT = 1.55

# (axis, direction) -> degrees for ursina rotation_<axis>.
# Empirical (tools/render_check.py): ursina rotation_x=+90 brings D to front,
# rotation_y=+90 brings R to front; model "cw" is front->up / front->right.
_ANGLES = {("x", "cw"): 90.0, ("x", "ccw"): -90.0,
           ("y", "cw"): -90.0, ("y", "ccw"): 90.0}

_STICKER_TEXTURE = None


def _sticker_texture() -> Texture:
    """Shared sticker texture: white rounded fill, dark border ring.

    Tinted multiplicatively by the entity color: the white fill takes the
    sticker color, the near-black ring stays dark on every face.
    """
    global _STICKER_TEXTURE
    if _STICKER_TEXTURE is None:
        from PIL import Image, ImageDraw

        size, border, radius = 256, 16, 40
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius,
                            fill=(14, 14, 14, 255))
        d.rounded_rectangle([border, border, size - 1 - border, size - 1 - border],
                            radius=radius - border + 4, fill=(255, 255, 255, 255))
        _STICKER_TEXTURE = Texture(img)
    return _STICKER_TEXTURE


class CubeView:
    def __init__(self, cube: Cube, animation_duration: float = 0.6,
                 tilt: tuple[float, float, float] = (-30, 35, 0),
                 y_offset: float = 2.0):
        self.cube = cube
        self.animation_duration = animation_duration
        self.animating = False
        self.root = Entity(rotation=tilt, y=y_offset)

        # Small dark core deep inside: blocks see-through to the chroma-key
        # background on middle-slice turns. Kept well below the surface so a
        # turning outer layer reveals the recessed cubie walls (mechanism
        # slot look) instead of a flush black slab.
        self.core = Entity(parent=self.root, model="cube", color=CUBIE_COLOR,
                           scale=1.8)

        self.cubies = []
        for x, y, z in itertools.product((-1, 0, 1), repeat=3):
            e = Entity(parent=self.root, model="cube", color=CUBIE_COLOR,
                       scale=0.96, position=(x, y, z))
            e.cell = (x, y, z)
            self.cubies.append(e)

        self.stickers = {}
        for face in FACES:
            for r in range(3):
                for c in range(3):
                    s = Entity(parent=self.root, model="quad", double_sided=True,
                               texture=_sticker_texture(), scale=0.9,
                               shader=CRISP_UNLIT)
                    self.stickers[(face, r, c)] = s
        self.sync()

    def fit_width(self, margin: float = 0.98,
                  top_ui: float | None = None,
                  bottom_ui: float | None = None) -> None:
        """Scale the cube so its tilted silhouette spans the window width.

        If top_ui/bottom_ui (camera.ui y coords) are given, the scale is
        capped so the silhouette also fits between them vertically, and the
        cube is centered in that band."""
        import math

        from ursina import camera, window
        half_h = math.tan(math.radians(camera.fov / 2)) * abs(camera.z)
        half_w = half_h * window.aspect_ratio
        # screen extent of a rotated box = sum of |coord| of its basis vectors
        # (normalize: getRelativeVector includes the current root scale)
        basis = (self.root.right, self.root.up, self.root.forward)
        per_x = sum(abs(v.normalized().x) for v in basis)
        scale = half_w * margin / (CUBE_HALF_EXTENT * per_x)
        if top_ui is not None and bottom_ui is not None:
            per_y = sum(abs(v.normalized().y) for v in basis)
            band_half = (top_ui - bottom_ui) / 2 * 2 * half_h  # ui y: 0.5 == half_h
            scale = min(scale, band_half * margin / (CUBE_HALF_EXTENT * per_y))
            self.root.y = (top_ui + bottom_ui) / 2 * 2 * half_h
        self.root.scale = scale

    def sync(self) -> None:
        """Snap all sticker entities to the current model state."""
        for (face, r, c), s in self.stickers.items():
            pos, normal = sticker_transform(face, r, c)
            rn = (normal[0], normal[1], -normal[2])
            s.position = Vec3(pos[0], pos[1], -pos[2]) + Vec3(*rn) * 0.51
            s.rotation = (0, 90, 0) if rn[0] else (90, 0, 0) if rn[1] else (0, 0, 0)
            s.color = STICKER_COLORS[self.cube.faces[face][r][c]]
            s.cell = pos
        for e in self.cubies:
            e.position = e.cell
            e.rotation = (0, 0, 0)

    def animate_move(self, move: str, on_done=None) -> None:
        """Animate the layer rotation; the model must already be post-move."""
        axis, layer, direction = move_info(move)
        if axis is None:  # whole-cube move: wu/wd spin around x, wr/wl around y
            axis = "x" if move.strip().lower()[1] in "ud" else "y"
        axis_idx = {"x": 0, "y": 1}[axis]
        pivot = Entity(parent=self.root)
        movers = [e for e in itertools.chain(self.cubies, self.stickers.values())
                  if layer is None or e.cell[axis_idx] == layer]
        for e in movers:
            e.parent = pivot

        angle = _ANGLES[(axis, direction)]
        d = self.animation_duration
        self.animating = True
        if axis == "x":
            pivot.animate_rotation_x(angle, duration=d, curve=curve.linear)
        else:
            pivot.animate_rotation_y(angle, duration=d, curve=curve.linear)
        invoke(self._finish_move, pivot, on_done, delay=d + 0.05)

    def _finish_move(self, pivot, on_done) -> None:
        for e in list(pivot.children):
            e.world_parent = self.root
        destroy(pivot)
        self.sync()
        self.animating = False
        if on_done:
            on_done()
