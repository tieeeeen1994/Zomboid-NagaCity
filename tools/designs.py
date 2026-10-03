"""Hand-drawn building designs (the user, 2026-10-04: "you draw them" — buildings designed on purpose to suit Zomboid
tiles, for street-level recognition; see CLAUDE.md "Designs").

A design is drawn with its street front at the bottom (south), one text grid per floor, north row first. Each
letter is a room ("." = outside); walls go wherever letters differ. Doors, windows and stairs are listed by square and
edge in the drawn orientation (edge N / S / E / W of that square). `place()` turns the design to face any street:
south as drawn, north mirrored, east / west rotated; stairs that would then climb south / east are laid the other way
in the same footprint (both ends of every stair bay are open floor in the designs). The ground floor's front edges in
the shop room become a glass shopfront (vanilla's `walls_commercial_01` row 80) with a glass door.

Rooms are furnished with the best-fitting vanilla room of their name and take its floor and wall set (rooms.py,
layout._roomtype); "{use}" stands for the business (pharmacy, bank...)."""
import random

import layout as L
import rooms as vanilla
from buildkit import Building, WallSet

SHOPFRONT = WallSet("walls_commercial_01", 5, 0)
GLASS_DOOR = {"W": "fixtures_doors_01_48", "N": "fixtures_doors_01_49"}

# Painted concrete for upper floors (vanilla exterior sets, colour rows).
PAINT = [WallSet("walls_commercial_03", 1, 0), WallSet("walls_exterior_house_01", 3, 0),
         WallSet("walls_exterior_house_01", 3, 1), WallSet("walls_commercial_03", 3, 0)]

DIRS = {"N": (0, -1), "S": (0, 1), "W": (-1, 0), "E": (1, 0)}


class Design:
    def __init__(self, name, floors, rooms, shop="P", notes=""):
        self.name, self.floors, self.rooms, self.shop, self.notes = name, floors, rooms, shop, notes
        self.h = len(floors[0]["rows"])
        self.w = max(len(r) for r in floors[0]["rows"])


def _turn(design, facing):
    """(cell transform, direction map, new w, new h) so the drawn south front faces `facing`."""
    w, h = design.w, design.h
    if facing == "S":
        return (lambda x, y: (x, y)), {"N": "N", "S": "S", "E": "E", "W": "W"}, w, h
    if facing == "N":
        return (lambda x, y: (x, h - 1 - y)), {"N": "S", "S": "N", "E": "E", "W": "W"}, w, h
    if facing == "E":
        return (lambda x, y: (y, w - 1 - x)), {"S": "E", "N": "W", "W": "S", "E": "N"}, h, w
    return (lambda x, y: (h - 1 - y, x)), {"S": "W", "N": "E", "E": "S", "W": "N"}, h, w


def _edge(x, y, d):
    """A square's edge in buildkit's form: (x, y, N|W) on the square south / east of it for S / E."""
    if d == "N":
        return (x, y, "N")
    if d == "W":
        return (x, y, "W")
    if d == "S":
        return (x, y + 1, "N")
    return (x + 1, y, "W")


def place(design, ox, oy, facing, use, exterior=None, seed=0):
    """A buildkit.Building of the design, its north-west corner at (ox, oy), front towards `facing`."""
    rng = random.Random(seed)
    cell, dmap, w, h = _turn(design, facing)
    b = Building(design.name, ox, oy, exterior or rng.choice(PAINT))
    b.fixed_windows = set()
    names = {k: (use if v == "{use}" else v) for k, v in design.rooms.items()}
    keys = iter(L.T.KEYS)
    key_of = {}  # (letter, z) -> one-character room key, unique across floors
    for z, fl in enumerate(design.floors):
        grid = [["."] * w for _ in range(h)]
        for y, row in enumerate(fl["rows"]):
            for x, k in enumerate(row):
                if k != ".":
                    nx, ny = cell(x, y)
                    grid[ny][nx] = k
        legend = {}
        for k in {k for row in grid for k in row if k != "."}:
            sq = [(x, y) for y in range(h) for x in range(w) if grid[y][x] == k]
            x0, y0 = min(p[0] for p in sq), min(p[1] for p in sq)
            x1, y1 = max(p[0] for p in sq), max(p[1] for p in sq)
            name = names[k]
            stamp = _stamp(name, x1 - x0 + 1, y1 - y0 + 1, rng)
            if stamp is None:
                rt = L.HALL if name == "hall" else L._roomtype(name, {})
            else:
                rt = L._roomtype(name, stamp)
                inside = set(sq)
                for dx, dy, tiles in stamp["items"]:
                    if (x0 + dx, y0 + dy) in inside:
                        b.furniture.append((z, x0 + dx, y0 + dy, tiles))
                        b.furnished.add((z, x0 + dx, y0 + dy))
            key_of[(k, z)] = next(keys)
            legend[key_of[(k, z)]] = rt
        b.floor(z, ["".join(key_of[(c, z)] if c != "." else "." for c in row) for row in grid], legend)
        for x, y, d, *flags in fl.get("doors", []):
            nx, ny = cell(x, y)
            e = (z,) + _edge(nx, ny, dmap[d])
            b.doors.add(e)
            if "glass" in flags:
                b.door_tiles[e] = GLASS_DOOR[e[3]]
        for x, y, d in fl.get("windows", []):
            nx, ny = cell(x, y)
            b.fixed_windows.add((z,) + _edge(nx, ny, dmap[d]))
        for x, y, d in fl.get("stairs", []):  # top square (west of the two) and climb direction, as drawn
            squares = [(x + i * DIRS[_opp(d)][0] + j * _side(d)[0], y + i * DIRS[_opp(d)][1] + j * _side(d)[1])
                       for i in range(3) for j in range(2)]
            turned = [cell(*p) for p in squares]
            xs, ys = [p[0] for p in turned], [p[1] for p in turned]
            if max(ys) - min(ys) == 2:   # runs north-south: climb north
                b.stairs.append((z, min(xs), min(ys)))
            else:                        # runs east-west: climb west
                b.stairs.append((z, min(xs), min(ys), "W"))
        if z == 0 and design.shop:
            for x in range(design.w):
                if fl["rows"][design.h - 1][x] == design.shop:
                    nx, ny = cell(x, design.h - 1)
                    b.edge_walls[(0,) + _edge(nx, ny, dmap["S"])] = SHOPFRONT
    return b


def _opp(d):
    return {"N": "S", "S": "N", "E": "W", "W": "E"}[d]


def _side(d):
    """Second stair column, to the right of the climb when drawn (east of a north climb)."""
    return {"N": (1, 0), "S": (1, 0), "W": (0, 1), "E": (0, 1)}[d]


def _stamp(name, w, h, rng):
    if name in vanilla.NO_FURNITURE:
        return None
    lib = vanilla.library()
    fits = [st for st in lib.get(name, []) if st["w"] <= w and st["h"] <= h and len(st["items"]) >= 2]
    if not fits:
        return None
    fits.sort(key=lambda st: (w - st["w"]) + (h - st["h"]))
    return rng.choice(fits[:5])


# --- the designs -------------------------------------------------------------------------------------------------

SHOPHOUSE_8 = Design(
    "shophouse 8x14, 2 floors",
    notes="Naga's commonest street building: a shop on the ground floor behind a glass front, a stair hall and "
          "storeroom at the back, the family upstairs (kitchen, bathroom, bedroom, front living room).",
    rooms={"h": "hall", "s": "storage", "P": "{use}", "k": "kitchen", "b": "bathroom", "r": "bedroom",
           "l": "livingroom"},
    floors=[
        {"rows": ["hhssssss",
                  "hhssssss",
                  "hhssssss",
                  "hhssssss",
                  "hhssssss",
                  "PPPPPPPP",
                  "PPPPPPPP",
                  "PPPPPPPP",
                  "PPPPPPPP",
                  "PPPPPPPP",
                  "PPPPPPPP",
                  "PPPPPPPP",
                  "PPPPPPPP",
                  "PPPPPPPP"],
         "doors": [(0, 4, "S"), (5, 4, "S"), (3, 13, "S", "glass")],
         "windows": [(5, 0, "N")],
         "stairs": [(0, 1, "N")]},
        {"rows": ["hhkkkkkk",
                  "hhkkkkkk",
                  "hhkkkkkk",
                  "hhkkkkkk",
                  "hhbbbbbb",
                  "hhbbbbbb",
                  "hhbbbbbb",
                  "hhrrrrrr",
                  "hhrrrrrr",
                  "hhrrrrrr",
                  "hhrrrrrr",
                  "hhllllll",
                  "hhllllll",
                  "hhllllll"],
         "doors": [(2, 1, "W"), (2, 5, "W"), (2, 8, "W"), (2, 12, "W")],
         "windows": [(4, 0, "N"), (6, 0, "N"), (3, 13, "S"), (6, 13, "S"), (1, 13, "S")]},
    ])
