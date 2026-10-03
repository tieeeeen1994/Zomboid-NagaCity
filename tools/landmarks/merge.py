"""Writes a buildkit.Canvas into the cells generate.py builds.

Each building's room defs go into the header of the cell holding its first room's north-west square; rects may run
past that cell's 256 squares (vanilla does it in ~18,000 of 152,317 rects), the tiles go to whichever cell they fall
in. The lotpack's per-square room index (ignored by the game) is only set inside the owning cell."""
from collections import defaultdict

import numpy as np

from pzmap.chunkdata import NO_LOT
from pzmap.lotfiles import CELL, Room


def rects_of(squares):
    """A set of (x, y) -> list of (x, y, w, h): row runs merged downwards while they keep the same span."""
    rows = defaultdict(list)
    for x, y in squares:
        rows[y].append(x)
    runs = defaultdict(list)  # (x0, x1) -> [y...]
    for y, xs in rows.items():
        xs.sort()
        start = prev = xs[0]
        for x in xs[1:] + [None]:
            if x is not None and x == prev + 1:
                prev = x
                continue
            runs[(start, prev)].append(y)
            if x is not None:
                start = prev = x
    out = []
    for (x0, x1), ys in runs.items():
        ys.sort()
        top = last = ys[0]
        for y in ys[1:] + [None]:
            if y is not None and y == last + 1:
                last = y
                continue
            out.append((x0, top, x1 - x0 + 1, last - top + 1))
            if y is not None:
                top = last = y
    return out


class LandmarkLayer:
    def __init__(self, canvas):
        self.canvas = canvas
        self.by_cell = defaultdict(list)
        for (x, y, z), tiles in canvas.squares.items():
            if tiles:
                self.by_cell[(x // CELL, y // CELL)].append((x, y, z, tiles))
        self.claimed = np.zeros(0)
        self.claimed_by_cell = defaultdict(set)
        for x, y in canvas.claimed:
            self.claimed_by_cell[(x // CELL, y // CELL)].add((x, y))
        self.buildings_by_cell = defaultdict(list)
        for rooms in canvas.buildings:
            if not rooms:
                continue
            x, y = min(canvas.rooms[rooms[0]][2], key=lambda p: (p[1], p[0]))
            self.buildings_by_cell[(x // CELL, y // CELL)].append(rooms)

    def claimed_mask(self, cx, cy):
        m = np.zeros((CELL, CELL), dtype=bool)
        for x, y in self.claimed_by_cell.get((cx, cy), ()):
            m[y - cy * CELL, x - cx * CELL] = True
        return m

    def apply(self, cx, cy, cell, cd):
        ox, oy = cx * CELL, cy * CELL
        local = {}
        for rooms in self.buildings_by_cell.get((cx, cy), ()):
            new = []
            for ri in rooms:
                name, level, squares = self.canvas.rooms[ri]
                local[ri] = len(cell.rooms) + len(new)
                new.append(Room(name, level, [(x - ox, y - oy, w, h) for x, y, w, h in rects_of(squares)]))
            cell.add_building(new)
        for x, y, z, tiles in self.by_cell.get((cx, cy), ()):
            ri = self.canvas.room_of.get((x, y, z))
            cell.set_square(x - ox, y - oy, z, tiles, local.get(ri, -1))
            if z == 0:
                cd.set(x - ox, y - oy, self.canvas.bits.get((x, y), 0))
        for x, y in self.claimed_by_cell.get((cx, cy), ()):
            if cd.get(x - ox, y - oy) & NO_LOT:
                cd.set(x - ox, y - oy, self.canvas.bits.get((x, y), 0))
