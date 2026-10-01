"""CLI check: py -m apps.rubiks_cube.core [scramble_moves] [seed]"""

import random
import sys

from apps.rubiks_cube.core.cube import Cube


def main():
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else None

    cube = Cube()
    print("Solved cube:")
    print(cube)
    print(f"is_solved: {cube.is_solved()}\n")

    moves = cube.scramble(count, random.Random(seed))
    print(f"Scramble ({count} moves, seed={seed}): {' '.join(moves)}")
    print(cube)
    print(f"is_solved: {cube.is_solved()}")


if __name__ == "__main__":
    main()
