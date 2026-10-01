import random
import unittest
from collections import Counter

from apps.rubiks_cube.core import VALID_MOVES, Cube, inverse, normalize


def face_color(cube, face):
    return cube.faces[face][0][0]


class TestParsing(unittest.TestCase):
    def test_sixteen_valid_moves(self):
        self.assertEqual(len(VALID_MOVES), 16)

    def test_normalize_is_case_insensitive_and_strips(self):
        self.assertEqual(normalize(" U2 "), "u2")
        self.assertEqual(normalize("WU"), "wu")

    def test_invalid_move_raises(self):
        for bad in ("", "u0", "u4", "x1", "ww", "u", "uup"):
            with self.assertRaises(ValueError, msg=bad):
                normalize(bad)

    def test_inverse_roundtrip(self):
        for m in VALID_MOVES:
            self.assertEqual(inverse(inverse(m)), m)


class TestMoves(unittest.TestCase):
    def test_initial_cube_is_solved(self):
        self.assertTrue(Cube().is_solved())

    def test_every_move_four_times_is_identity(self):
        for m in VALID_MOVES:
            cube = Cube()
            cube.apply_sequence([m] * 4)
            self.assertEqual(cube, Cube(), msg=m)
            self.assertTrue(cube.is_solved(), msg=m)

    def test_move_then_inverse_is_identity(self):
        for m in VALID_MOVES:
            cube = Cube()
            cube.apply_sequence([m, inverse(m)])
            self.assertEqual(cube, Cube(), msg=m)

    def test_column_up_cycles_side_stickers(self):
        # u2: front column goes up, so new F column gets old D (Y),
        # U gets old F (G), B gets old U (W), D gets old B (B).
        cube = Cube()
        cube.apply("u2")
        self.assertEqual([cube.faces["F"][r][1] for r in range(3)], ["Y"] * 3)
        self.assertEqual([cube.faces["U"][r][1] for r in range(3)], ["G"] * 3)
        self.assertEqual([cube.faces["B"][r][1] for r in range(3)], ["W"] * 3)
        self.assertEqual([cube.faces["D"][r][1] for r in range(3)], ["B"] * 3)

    def test_row_right_cycles_side_stickers(self):
        # r1: front row goes right, so new F row gets old L (O).
        cube = Cube()
        cube.apply("r1")
        self.assertEqual(cube.faces["F"][0], ["O"] * 3)
        self.assertEqual(cube.faces["R"][0], ["G"] * 3)
        self.assertEqual(cube.faces["B"][0], ["R"] * 3)
        self.assertEqual(cube.faces["L"][0], ["B"] * 3)

    def test_edge_column_rotates_side_face(self):
        # u1 turns the x=-1 slice: L face itself must rotate (not stay rigid).
        cube = Cube()
        cube.apply_sequence(["r1", "u1"])  # disturb L face first
        self.assertNotEqual(cube, Cube())
        cube.apply_sequence(["u1"] * 3)    # complete 4 turns
        cube.apply("l1")
        self.assertEqual(cube, Cube())

    def test_whole_cube_right_rotates_all_faces(self):
        # wr: front goes right -> new F is old L, new R is old F, etc.
        cube = Cube()
        cube.apply("wr")
        self.assertEqual(face_color(cube, "F"), "O")
        self.assertEqual(face_color(cube, "R"), "G")
        self.assertEqual(face_color(cube, "B"), "R")
        self.assertEqual(face_color(cube, "L"), "B")
        self.assertEqual(face_color(cube, "U"), "W")
        self.assertEqual(face_color(cube, "D"), "Y")

    def test_whole_cube_up_cycles(self):
        # wu: front goes up -> new F is old D.
        cube = Cube()
        cube.apply("wu")
        self.assertEqual(face_color(cube, "F"), "Y")
        self.assertEqual(face_color(cube, "U"), "G")
        self.assertEqual(face_color(cube, "B"), "W")
        self.assertEqual(face_color(cube, "D"), "B")


class TestScramble(unittest.TestCase):
    def test_scramble_returns_requested_count_of_valid_moves(self):
        moves = Cube().scramble(10, random.Random(42))
        self.assertEqual(len(moves), 10)
        self.assertTrue(all(m in VALID_MOVES for m in moves))

    def test_scramble_never_undoes_previous_move(self):
        for seed in range(20):
            moves = Cube().scramble(30, random.Random(seed))
            for a, b in zip(moves, moves[1:]):
                self.assertNotEqual(b, inverse(a), msg=f"{a} {b}")

    def test_scramble_is_reproducible_with_seed(self):
        a, b = Cube(), Cube()
        self.assertEqual(a.scramble(10, random.Random(7)),
                         b.scramble(10, random.Random(7)))
        self.assertEqual(a, b)

    def test_sticker_conservation_after_random_moves(self):
        cube = Cube()
        cube.scramble(100, random.Random(1))
        counts = Counter(
            cell for grid in cube.faces.values() for row in grid for cell in row
        )
        self.assertEqual(sum(counts.values()), 54)
        for color in "WYGBOR":
            self.assertEqual(counts[color], 9, msg=color)


if __name__ == "__main__":
    unittest.main()
