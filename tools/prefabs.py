"""Whole vanilla buildings copied out of the Knox County lots and pasted elsewhere (the user, 2026-10-04: "I like the
idea of copying vanilla buildings with small alterations"), instead of drawing buildings (designs.py kept breaking
vanilla's multi-part pieces).

extract(cell, building index, margin): every square of the building's rooms on every level, plus a border of
`margin` squares (south / east walls, roof edges, awnings, shower panes, gas station canopies and pumps). Border
squares keep their lot (pavement, parking, forecourt, lawn) but not the vanilla road (asphalt, lines, curbs) or trees, and skip squares of other
buildings' rooms. Rooms keep their names (loot). Buildings cannot be turned (sprites face fixed ways), so
`entrances()` says which sides have outside doors, to pick a building whose front faces the street.

paste(prefab, canvas, ox, oy): writes it into a buildkit.Canvas at (ox, oy) = the prefab's north-west corner."""
import re
from collections import Counter

import config
from pzmap.lotfiles import CELL, Cell

# Left behind from the border: the vanilla road itself (asphalt families, lane lines, curbs) and trees / bushes;
# everything else of the lot comes along, its ground included (pavement, parking, forecourt, lawn strips).
ROAD = re.compile(r"^(blends_street_01_(\d+)|street_trafficlines_|street_curbs_|e_|f_|vegetation_trees)")


_road_tree = None


def vanilla_road_squares(x0, y0, x1, y1):
    """Squares (absolute) inside a vanilla road polygon of Knox County's worldmap.xml (cached STRtree). Lots and
    forecourts use the same asphalt as roads, so only the world map tells them apart."""
    global _road_tree
    import os
    import pickle
    from shapely.geometry import Polygon, box
    from shapely.strtree import STRtree
    from pzmap import raster
    from pzmap.worldmap import read_features
    if _road_tree is None:
        cache = os.path.join(config.DATA, "vanilla_roads.pickle")
        if os.path.exists(cache):
            polys = pickle.load(open(cache, "rb"))
        else:
            polys = []
            for props, rings in read_features(os.path.join(config.VANILLA_MAP, "worldmap.xml")):
                if "highway" in props and rings and len(rings[0]) >= 3:
                    p = Polygon(rings[0]).buffer(0)
                    if not p.is_empty:
                        polys.append(p)
            pickle.dump(polys, open(cache, "wb"))
        _road_tree = (polys, STRtree(polys))
    polys, tree = _road_tree
    hits = [polys[i] for i in tree.query(box(x0, y0, x1 + 1, y1 + 1))]
    if not hits:
        return set()
    m = raster.mask(hits, x0, y0, x1 - x0 + 1, y1 - y0 + 1)
    ys, xs = m.nonzero()
    return {(x0 + int(x), y0 + int(y)) for x, y in zip(xs, ys)}


def _is_road(n):
    m = ROAD.match(n)
    if not m:
        return False
    if m.group(2) is not None:
        return int(m.group(2)) // 16 * 16 in (0, 32, 64, 80, 96)   # asphalt; 48 (sidewalk) and 16 (dirt) stay
    return True
WALL = re.compile(r"walls_\w+?_(\d+)$")


class Prefab:
    def __init__(self, src, w, h, squares, rooms, levels):
        self.src, self.w, self.h = src, w, h
        self.squares = squares    # (dx, dy, z) -> [tiles]; dx, dy from the north-west corner of the box
        self.rooms = rooms        # [(name, z, set of (dx, dy))]
        self.levels = levels


def extract(cell_xy, building, margin=1):
    cell = Cell.load(config.VANILLA_MAP, *cell_xy)
    own, others = set(), set()
    rooms = []
    for bi, b in enumerate(cell.buildings):
        for ri in b:
            r = cell.rooms[ri]
            sq = {(x + i, y + j) for x, y, w, h in r.rects for i in range(w) for j in range(h)}
            if bi == building:
                own |= {(x, y, r.level) for x, y in sq}
                rooms.append((r.name.strip(), r.level, sq))
            else:
                others |= {(x, y, r.level) for x, y in sq}
    near = {(x + dx, y + dy, z) for x, y, z in others for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
    for x, y, z in list(near):
        near |= {(x, y, z + k) for k in (1, 2)}   # their roofs and upper walls
    own2d = {(x, y) for x, y, z in own}
    rim = {(x + dx, y + dy) for x, y in own2d for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
    xs = [p[0] for p in own]
    ys = [p[1] for p in own]
    x0, y0, x1, y1 = min(xs) - margin, min(ys) - margin, max(xs) + margin, max(ys) + margin
    zs = sorted({p[2] for p in own})
    road = vanilla_road_squares(cell_xy[0] * CELL + x0, cell_xy[1] * CELL + y0, cell_xy[0] * CELL + x1,
                                cell_xy[1] * CELL + y1)
    squares = {}
    for z in range(min(zs), max(zs) + 3):
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                if not (0 <= x < CELL and 0 <= y < CELL):
                    continue
                t = cell.get_square(x, y, z)
                if not t:
                    continue
                if (x, y, z) in own:
                    keep = list(t)
                elif (x, y, z) in others:
                    continue
                elif (x, y, z) in near and (x, y) not in rim:
                    continue  # a neighbour's walls / roof, unless on our own one-square rim (our south / east walls)
                elif z == 0 and (cell_xy[0] * CELL + x, cell_xy[1] * CELL + y) in road:
                    keep = [n for n in t if not _is_road(n)]
                elif z == 0:
                    keep = [n for n in t if not n.startswith(("e_", "f_", "vegetation_trees"))]
                else:
                    keep = list(t)
                if keep:
                    squares[(x - x0, y - y0, z)] = keep
    rooms = [(n, z, {(x - x0, y - y0) for x, y in sq}) for n, z, sq in rooms]
    origin = (cell_xy[0] * CELL + x0, cell_xy[1] * CELL + y0)  # where it sits in Knox County
    prefab = Prefab("%d_%d #%d" % (cell_xy[0], cell_xy[1], building), x1 - x0 + 1, y1 - y0 + 1, squares, rooms,
                  max(zs) + 1)
    prefab.origin = origin
    return prefab


def entrances(p):
    """Counter of the sides (N / S / E / W) with doors between a room square and the outside, on level 0."""
    room0 = set().union(*[sq for n, z, sq in p.rooms if z == 0]) if p.rooms else set()
    out = Counter()
    for (x, y, z), tiles in p.squares.items():
        if z != 0 or not any(t.startswith("fixtures_doors") for t in tiles):
            continue
        for t in tiles:
            m = WALL.match(t)
            if not m:
                continue
            k = int(m.group(1)) % 16
            if k in (10, 14):    # west door frame: between (x - 1, y) and (x, y)
                a, b = (x, y) in room0, (x - 1, y) in room0
                if a != b:
                    out["W" if a else "E"] += 1
            elif k in (11, 15):  # north door frame: between (x, y - 1) and (x, y)
                a, b = (x, y) in room0, (x, y - 1) in room0
                if a != b:
                    out["N" if a else "S"] += 1
    return out


def paste(p, canvas, ox, oy):
    from pzmap.chunkdata import ROOM, WALL_N, WALL_W
    first = len(canvas.rooms)
    for (dx, dy, z), tiles in p.squares.items():
        x, y = ox + dx, oy + dy
        key = (x, y, z)
        floorish = tiles[0].startswith(("floors_", "blends_", "carpentry_02"))
        if z == 0 and not floorish and key in canvas.squares:
            canvas.squares[key] = [canvas.squares[key][0]] + list(tiles)   # objects over the existing ground
            canvas.ground_only.discard(key)
        else:
            canvas.squares[key] = list(tiles)
            canvas.ground_only.discard(key)
        if z == 0:
            canvas.claimed.add((x, y))
            for t in tiles:
                m = WALL.match(t)
                if m:
                    k = int(m.group(1)) % 16
                    canvas.bits[(x, y)] |= WALL_N if k in (1, 5, 9, 11, 13, 15, 2, 6) else 0
                    canvas.bits[(x, y)] |= WALL_W if k in (0, 4, 8, 10, 12, 14, 2, 6) else 0
    for name, z, sq in p.rooms:
        ri = len(canvas.rooms)
        canvas.rooms.append([name, z, {(ox + x, oy + y) for x, y in sq}])
        for x, y in sq:
            canvas.room_of[(ox + x, oy + y, z)] = ri
            if z == 0:
                canvas.bits[(ox + x, oy + y)] |= ROOM
    canvas.buildings.append(list(range(first, len(canvas.rooms))))
