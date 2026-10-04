"""Generate Naga City's map files into Contents/mods/NagaCity/common/media/maps/Naga City, PH/.

Ground only so far: the roads of the road plan (plan/roads.json, roadplan.py; OSM roads are no longer read here) laid
with vanilla's street recipe (asphalt, sidewalks, curbs, grass edges, centre lines), rivers, biome maps, the connector from Raven Creek, the
in-game map, a test spawn. Squares left empty are filled by B42 worldgen from the biome maps.

    tools/.venv/Scripts/python.exe tools/generate.py [x0 y0 x1 y1]   (PZ cell range, default: everything)"""
import math
import os
import sys
import time
from collections import defaultdict

import numpy as np
from shapely.geometry import LineString, box
from shapely.ops import unary_union
from shapely.strtree import STRtree

import config
import osm
import roadplan
import roads as roadnet
import landmarks
import tiles
from landmarks.merge import LandmarkLayer
from pzmap import biome, raster
from pzmap.chunkdata import NO_LOT, WATER, ChunkData
from pzmap.lotfiles import CELL, Cell
from pzmap.worldmap import WorldMapWriter

# Surface codes; a higher code wins where rectangles overlap (major roads over minor ones, roads over sidewalks and
# water: roads cross rivers as causeways until there are bridges).
NONE, S_WATER, S_SIDEWALK, S_DIRT, S_MINOR, S_MAJOR = 0, 1, 2, 3, 4, 5
ROADS = (S_DIRT, S_MINOR, S_MAJOR)
PAVED = (S_MINOR, S_MAJOR)
MAJOR_RANK = 5  # trunk, primary, secondary get dark asphalt and sidewalks
DIRS = (("N", 0, -1), ("W", -1, 0), ("E", 1, 0), ("S", 0, 1))
SIDEWALK_MIN = 12  # straight pieces shorter than this get no sidewalk (stubs at corners)
CENTER_MIN = 6  # visible centre line shorter than this is left out (a dash inside a junction)
M = 16  # margin squares around a cell: edges and curbs see their neighbours, and sidewalk bits / grass pockets up to
#        POCKET_SPAN / SIDEWALK_MIN long are judged whole, the same way from every cell they touch
POCKET_SPAN = 16  # enclosed grass up to this many squares across and POCKET_AREA squares, inside junctions, is paved
POCKET_AREA = 30

WM_HIGHWAY = {S_MAJOR: "primary", S_MINOR: "tertiary", S_DIRT: "trail"}

# Coverage of a square as four triangles (centre to edge): N 1, E 2, S 4, W 8. A 45-degree road edge cuts a square
# along a diagonal, leaving half of it: N+E (right half on screen), W+S (left), N+W (upper), E+S (lower). Vanilla's
# half tiles are the family base + 1 (upper), + 2 (lower), + 3 (left), + 4 (right), the other half grass.
FULL = 15
HALF_OFFSET = {9: 1, 6: 2, 12: 3, 3: 4}
FAMILY = {S_MAJOR: 80, S_MINOR: 96, S_SIDEWALK: 48, S_DIRT: 16}


class Rect:
    """A straight strip. `strip`: a road's sidewalk (trimmed near 45-degree roads), not a paved area or path."""
    __slots__ = ("x0", "y0", "x1", "y1", "code", "horizontal", "strip")

    def __init__(self, r, code, horizontal, strip=False):
        self.x0, self.y0, self.x1, self.y1 = r
        self.code, self.horizontal, self.strip = code, horizontal, strip

    def paint(self, surf, mask, gx, gy, aux):
        size = surf.shape[0]
        x0, x1 = max(self.x0 - gx, 0), min(self.x1 - gx, size)
        y0, y1 = max(self.y0 - gy, 0), min(self.y1 - gy, size)
        if x0 >= x1 or y0 >= y1:
            return
        region = surf[y0:y1, x0:x1]
        np.maximum(region, self.code, out=region)
        mask[y0:y1, x0:x1] = FULL
        if self.code in PAVED:
            aux["h" if self.horizontal else "v"][y0:y1, x0:x1] = True
        if self.strip:
            aux["strip_h" if self.horizontal else "strip_v"][y0:y1, x0:x1] = True


class Diag:
    """A 45-degree road piece. Falling pieces (north-west to south-east) are bounded by lines x - y = c1 and c2,
    rising ones by x + y = c1 and c2; c is measured at square centres (x - y = i - j, x + y = i + j + 1), so squares
    with c strictly between are full and squares with c on a bound are cut in half along their diagonal. Clipped
    across the piece at its two ends."""
    __slots__ = ("x0", "y0", "x1", "y1", "code", "falling", "c1", "c2", "t0", "t1", "line", "width")

    def __init__(self, piece, width, code):
        (ax, ay), (bx, by) = piece.a, piece.b
        self.code, self.falling, self.width = code, piece.falling, width
        h = max(1, round(width / math.sqrt(2)))
        k = ax - ay if self.falling else ax + ay
        self.c1, self.c2 = k - h, k + h
        ta, tb = (ax + ay, bx + by) if self.falling else (ax - ay, bx - by)
        self.t0, self.t1 = min(ta, tb), max(ta, tb)
        self.x0, self.y0 = min(ax, bx) - width, min(ay, by) - width
        self.x1, self.y1 = max(ax, bx) + width, max(ay, by) + width
        self.line = (piece.a, piece.b)

    def paint(self, surf, mask, gx, gy, aux):
        size = surf.shape[0]
        x0, x1 = max(self.x0 - gx, 0), min(self.x1 - gx, size)
        y0, y1 = max(self.y0 - gy, 0), min(self.y1 - gy, size)
        if x0 >= x1 or y0 >= y1:
            return
        j, i = np.mgrid[y0 + gy:y1 + gy, x0 + gx:x1 + gx]
        c, t = (i - j, i + j + 1) if self.falling else (i + j + 1, i - j)
        along = (t >= self.t0) & (t <= self.t1)
        full = along & (c > self.c1) & (c < self.c2)
        low, high = along & (c == self.c1), along & (c == self.c2)
        cover = np.zeros(full.shape, dtype=np.uint8)
        cover[full] = FULL
        cover[low] = 3 if self.falling else 6
        cover[high] = 12 if self.falling else 9
        _paint_cover(self.code, cover, surf, mask, aux, y0, y1, x0, x1)


def _strip_inside(piece, width, cx, cy):
    """Whether points (arrays) lie inside the endless strip of a piece: what the piece would cover without its ends
    (Rect / Diag edges: straight ones on square boundaries, 45-degree ones through square diagonals)."""
    (ax, ay), (bx, by) = piece.a, piece.b
    if ay == by:
        return np.abs(cy - ay) < width / 2
    if ax == bx:
        return np.abs(cx - ax) < width / 2
    h = max(1, round(width / math.sqrt(2)))
    if piece.falling:
        c, k = cx - cy, ax - ay
    else:
        c, k = cx + cy, ax + ay
    return (c > k - h) & (c < k + h)


class Joint:
    """Where a road turns (a bend in one road, or two roads joined end to end at an angle): the overlap of the two
    pieces' endless strips, which is exactly the mitred corner. Pieces end flat at their end points, so without it
    the outer side of a bend had a gap and with square ends a nub."""
    __slots__ = ("x0", "y0", "x1", "y1", "code", "p", "q", "wp", "wq")

    def __init__(self, p, q, wp, wq, code):
        vx, vy = p.b if p.b in (q.a, q.b) else p.a
        reach = max(wp, wq) + 2
        self.x0, self.y0, self.x1, self.y1 = vx - reach, vy - reach, vx + reach, vy + reach
        self.p, self.q, self.wp, self.wq, self.code = p, q, wp, wq, code

    def paint(self, surf, mask, gx, gy, aux):
        size = surf.shape[0]
        x0, x1 = max(self.x0 - gx, 0), min(self.x1 - gx, size)
        y0, y1 = max(self.y0 - gy, 0), min(self.y1 - gy, size)
        if x0 >= x1 or y0 >= y1:
            return
        j, i = np.mgrid[y0 + gy:y1 + gy, x0 + gx:x1 + gx].astype(float)
        cover = np.zeros(i.shape, dtype=np.uint8)
        for bit, (dx, dy) in ((1, (0.5, 1 / 6)), (2, (5 / 6, 0.5)), (4, (0.5, 5 / 6)), (8, (1 / 6, 0.5))):
            cx, cy = i + dx, j + dy
            inside = _strip_inside(self.p, self.wp, cx, cy) & _strip_inside(self.q, self.wq, cx, cy)
            cover[inside] |= bit
        _paint_cover(self.code, cover, surf, mask, aux, y0, y1, x0, x1)


def _offset(piece, width, cx, cy):
    """Signed distance of points from a piece's centre line, and the strip's half-width, in matching units (x or y
    for straight pieces, x - y or x + y for 45-degree ones)."""
    (ax, ay), (bx, by) = piece.a, piece.b
    if ay == by:
        return cy - ay, width / 2
    if ax == bx:
        return cx - ax, width / 2
    h = max(1, round(width / math.sqrt(2)))
    if piece.falling:
        return (cx - cy) - (ax - ay), h
    return (cx + cy) - (ax + ay), h


class EndJoint(Joint):
    """A road ending on a road that goes straight through: it carries on to the through road's far edge, so its flat
    end is hidden inside it and its sides meet the through road's edges (a narrower 45-degree road left a corner of
    the flat end showing beside the sidewalk)."""
    __slots__ = ()

    def paint(self, surf, mask, gx, gy, aux):
        size = surf.shape[0]
        x0, x1 = max(self.x0 - gx, 0), min(self.x1 - gx, size)
        y0, y1 = max(self.y0 - gy, 0), min(self.y1 - gy, size)
        if x0 >= x1 or y0 >= y1:
            return
        p, q = self.p, self.q
        v = p.b if p.b in (q.a, q.b) else p.a
        far_p = p.a if v == p.b else p.b
        side, _ = _offset(q, self.wq, float(far_p[0]) + 0.5, float(far_p[1]) + 0.5)
        sign = 1 if side > 0 else -1
        j, i = np.mgrid[y0 + gy:y1 + gy, x0 + gx:x1 + gx].astype(float)
        cover = np.zeros(i.shape, dtype=np.uint8)
        for bit, (dx, dy) in ((1, (0.5, 1 / 6)), (2, (5 / 6, 0.5)), (4, (0.5, 5 / 6)), (8, (1 / 6, 0.5))):
            cx, cy = i + dx, j + dy
            off, half = _offset(q, self.wq, cx, cy)
            inside = _strip_inside(p, self.wp, cx, cy) & (off * sign > -half)
            cover[inside] |= bit
        _paint_cover(self.code, cover, surf, mask, aux, y0, y1, x0, x1)


def _sidewalk_band(piece, width, side, cx, cy):
    """Whether points lie in the endless sidewalk bands (both sides) of a straight piece."""
    (ax, ay), (bx, by) = piece.a, piece.b
    d = np.abs(cy - ay) if ay == by else np.abs(cx - ax)
    return (d > width / 2) & (d < width / 2 + side)


class SidewalkJoint(Joint):
    """At a turn, a straight piece's sidewalk carries on past the corner point until it meets the next piece's road
    (and that piece's sidewalk, when it has one): it ends flush with a 45-degree road's edge, and a square corner
    gets its outer corner square, instead of stopping flat at the corner point and leaving a grass notch."""
    __slots__ = ("sp", "sq")

    def __init__(self, p, q, wp, wq, sp, sq):
        Joint.__init__(self, p, q, wp, wq, S_SIDEWALK)
        self.sp, self.sq = sp, sq  # sidewalk widths: p's (drawn), q's (0 when q has none)
        reach = max(wp, wq) + 2 * max(sp, sq) + 2
        vx, vy = p.b if p.b in (q.a, q.b) else p.a
        self.x0, self.y0, self.x1, self.y1 = vx - reach, vy - reach, vx + reach, vy + reach

    def paint(self, surf, mask, gx, gy, aux):
        size = surf.shape[0]
        x0, x1 = max(self.x0 - gx, 0), min(self.x1 - gx, size)
        y0, y1 = max(self.y0 - gy, 0), min(self.y1 - gy, size)
        if x0 >= x1 or y0 >= y1:
            return
        # Only on the outside of the turn and past the corner point (elsewhere it left shards along the next road).
        p, q = self.p, self.q
        v = p.b if p.b in (q.a, q.b) else p.a
        far_p = p.a if v == p.b else p.b
        far_q = q.b if v == q.a else q.a
        dp = roadplan._direction(far_p, v)   # travelling into the corner
        dq = roadplan._direction(v, far_q)   # leaving it
        turn = dp[0] * dq[1] - dp[1] * dq[0]
        if turn == 0:
            return
        n = (-dp[1], dp[0])                  # p's left normal; the inside of the turn is n when turn > 0
        j, i = np.mgrid[y0 + gy:y1 + gy, x0 + gx:x1 + gx].astype(float)
        cover = np.zeros(i.shape, dtype=np.uint8)
        for bit, (dx, dy) in ((1, (0.5, 1 / 6)), (2, (5 / 6, 0.5)), (4, (0.5, 5 / 6)), (8, (1 / 6, 0.5))):
            cx, cy = i + dx, j + dy
            side = ((cx - v[0]) * n[0] + (cy - v[1]) * n[1]) * turn < 0
            past = (cx - v[0]) * dp[0] + (cy - v[1]) * dp[1] > 0
            inside = side & past & _sidewalk_band(p, self.wp, self.sp, cx, cy) &                 _strip_inside(q, self.wq + 2 * self.sq, cx, cy)
            cover[inside] |= bit
        _paint_cover(S_SIDEWALK, cover, surf, mask, aux, y0, y1, x0, x1)


def _paint_cover(code, cover, surf, mask, aux, y0, y1, x0, x1):
    """Coverage bits (N 1, E 2, S 4, W 8) painted with a surface code. Over a lower surface the new edge replaces the
    old coverage (OR-ing it in made edge squares full: notches), and the other half of an edge square shows what was
    there (a sidewalk, a lower road, a path, a plaza, water), not grass."""
    hit = cover > 0
    region, mregion = surf[y0:y1, x0:x1], mask[y0:y1, x0:x1]
    up = hit & (region < code)
    same = hit & (region == code)
    below = hit & (region > code) & (mregion != FULL) & (mregion != 0)  # a higher road's half square: fill under it
    mregion[up] = cover[up]
    mregion[same] |= cover[same]
    under = aux["under"][y0:y1, x0:x1]
    under[below & (under == NONE)] = code
    keep = up & (region > NONE)
    under[keep] = region[keep]
    under[up & ~keep] = NONE
    region[hit] = np.maximum(region[hit], code)
    aux["d"][y0:y1, x0:x1] |= hit


def road_code(road):
    if road.surface == "dirt":
        return S_DIRT
    if road.surface == "sidewalk":
        return S_SIDEWALK
    return S_MAJOR if roadnet.RANK.get(road.cls, 3) >= MAJOR_RANK else S_MINOR


def build_network(plan):
    pieces, plan_roads = roadplan.pieces(plan)
    rects, lines_h, lines_v = [], {}, {}
    for p in pieces:
        r = plan_roads[p.road]
        half = r.width // 2
        code = road_code(r)
        if p.diagonal:
            rects.append(Diag(p, r.width, code))
            continue
        flat = (p.x0, p.y0 - half, p.x1, p.y1 + half) if p.horizontal else (p.x0 - half, p.y0, p.x1 + half, p.y1)
        rects.append(Rect(flat, code, p.horizontal))  # flat ends: bends get a Joint, junctions are covered
        if has_sidewalk(p, r):
            x0, y0, x1, y1 = flat  # widened across the road only: no sidewalk past the road's end
            s = r.sidewalk
            box_ = (x0, y0 - s, x1, y1 + s) if p.horizontal else (x0 - s, y0, x1 + s, y1)
            rects.append(Rect(box_, S_SIDEWALK, p.horizontal, strip=True))
        if r.center_line and max(p.x1 - p.x0, p.y1 - p.y0) - r.width - 4 >= CENTER_MIN:  # no stray dashes
            if p.horizontal:
                for x in range(p.x0 + half + 2, p.x1 - half - 2):
                    lines_h.setdefault((x, p.y0 - 1), []).append(tiles.YELLOW["S"])
                    lines_h.setdefault((x, p.y0), []).append(tiles.YELLOW["N"])
            else:
                for y in range(p.y0 + half + 2, p.y1 - half - 2):
                    lines_v.setdefault((p.x0 - 1, y), []).append(tiles.YELLOW["E"])
                    lines_v.setdefault((p.x0, y), []).append(tiles.YELLOW["W"])
    rects += joints(pieces, plan_roads)
    for a in plan["areas"]:  # pedestrian areas (plazas)
        code = {"sidewalk": S_SIDEWALK, "dirt": S_DIRT}.get(a["surface"], S_MINOR)
        rects.append(Rect(tuple(a["rect"]), code, True))
    end = tuple(plan["nodes"][plan["connector_end"]])
    return rects, lines_h, lines_v, end


def joints(pieces, plan_roads):
    """Corner fills where road pieces meet at a point:
    - every two pieces leaving a point at 90 or 135 degrees to each other (a bend, a corner where one road turns into
      another, a junction's corners) get a Joint (mitred corner) and, for a piece with a sidewalk, a SidewalkJoint
      (the sidewalk wraps the outside of the corner); pieces at 45 degrees (a hairpin) get none, their mitre would
      stick out behind the point;
    - a piece ending on a road that goes straight through gets an EndJoint (it carries on to the far edge)."""
    out, arms = [], defaultdict(list)
    for p in pieces:
        arms[p.a].append(p)
        arms[p.b].append(p)
    direction = lambda p, v: roadplan._direction(v, p.b if p.a == v else p.a)
    for v, here in arms.items():
        if len(here) < 2:
            continue
        dirs = [direction(p, v) for p in here]
        for x, p in enumerate(here):
            for y in range(x + 1, len(here)):
                q = here[y]
                dp, dq = dirs[x], dirs[y]
                if dp == dq or dp == (-dq[0], -dq[1]) or dp[0] * dq[0] + dp[1] * dq[1] > 0:
                    continue  # same way (overlapping roads), straight on, or a hairpin
                rp, rq = plan_roads[p.road], plan_roads[q.road]
                out.append(Joint(p, q, rp.width, rq.width, max(road_code(rp), road_code(rq))))
                for a, c, ra, rc in ((p, q, rp, rq), (q, p, rq, rp)):
                    if has_sidewalk(a, ra):
                        out.append(SidewalkJoint(a, c, ra.width, rc.width, ra.sidewalk,
                                                 rc.sidewalk if has_sidewalk(c, rc) else 0))
        for x, a in enumerate(here):  # roads ending on a road going straight through
            for y in range(x + 1, len(here)):
                if dirs[x] != (-dirs[y][0], -dirs[y][1]):
                    continue
                for k, p in enumerate(here):
                    if k not in (x, y) and dirs[k] not in (dirs[x], dirs[y]):
                        rp, ra = plan_roads[p.road], plan_roads[a.road]
                        out.append(EndJoint(p, a, rp.width, ra.width, road_code(rp)))
    return out


def has_sidewalk(p, r):
    """Whether build_network draws a sidewalk along piece p of road r."""
    return (bool(r.sidewalk) and road_code(r) != S_SIDEWALK and not p.diagonal
            and max(p.x1 - p.x0, p.y1 - p.y0) >= SIDEWALK_MIN)


def connector(end, rects, marks):
    """Raven Creek's road continued east along y = 15404, a square corner, south to Calabanga Road's north end."""
    cy, half = config.RC_LINK_CENTER, config.CONNECTOR_WIDTH // 2
    ex, ey = end
    for a, b, horizontal in (((config.RC_LINK_END_X + 1, cy), (ex, cy), True), ((ex, cy), (ex, ey), False)):
        p = roadnet.Piece(a, b, None)
        rects.append(Rect(p.rect(half), S_MAJOR, horizontal))
    for x in range(config.RC_LINK_END_X + 1, ex - half):
        add = marks.setdefault
        add((x, cy - half), []).append(tiles.pick(tiles.EDGE_N, x, cy - half))
        add((x, cy + half - 1), []).append(tiles.pick(tiles.EDGE_S, x, cy + half - 1))
        add((x, cy - 1), []).append(tiles.YELLOW["S"])
        add((x, cy), []).append(tiles.YELLOW["N"])
        if tiles.dash_on(x):
            add((x, cy - 4), []).append(tiles.WHITE["N"])
            add((x, cy + 3), []).append(tiles.WHITE["S"])
    for y in range(cy + half, ey - 4):
        add = marks.setdefault
        add((ex - 1, y), []).append(tiles.YELLOW["E"])
        add((ex, y), []).append(tiles.YELLOW["W"])
        if tiles.dash_on(y):
            add((ex - 4, y), []).append(tiles.WHITE["W"])
            add((ex + 3, y), []).append(tiles.WHITE["E"])


def bucket(rects):
    out = defaultdict(list)
    for r in rects:
        for cx in range((r.x0 - M) // CELL, (r.x1 + M) // CELL + 1):
            for cy in range((r.y0 - M) // CELL, (r.y1 + M) // CELL + 1):
                out[(cx, cy)].append(r)
    return out


class Water:
    def __init__(self, data):
        self.geoms = data["water"] + [line.buffer(w / 2, cap_style="flat") for line, w, _, _ in data["waterways"]]
        self.tree = STRtree(self.geoms) if self.geoms else None

    def mask(self, ox, oy, size):
        if self.tree is None:
            return np.zeros((size, size), dtype=bool)
        hits = [self.geoms[i] for i in self.tree.query(box(ox, oy, ox + size, oy + size))]
        return raster.mask(hits, ox, oy, size, size) if hits else np.zeros((size, size), dtype=bool)


class Biomes:
    def __init__(self, data, water):
        town = data["town"] + [p.buffer(25) for p, _, _ in data["buildings"]]
        layers = [(biome.FARM_MIX_FOREST, data["forest"]), (biome.FARMLAND, data["farm"]), (biome.TOWN, town),
                  (biome.WATER, water.geoms)]
        self.layers = [(v, g, STRtree(g) if g else None) for v, g in layers]

    def cell(self, ox, oy):
        out = np.full((CELL, CELL), biome.FARMLAND, dtype=np.uint8)
        area = box(ox, oy, ox + CELL, oy + CELL)
        for value, geoms, tree in self.layers:
            if tree is not None:
                hits = [geoms[i] for i in tree.query(area)]
                if hits:
                    out[raster.mask(hits, ox, oy)] = value
        return out


def surfaces(cell_rects, water, ox, oy):
    """Surface codes, coverage masks and H / V asphalt masks for the cell plus a margin of M squares."""
    size = CELL + 2 * M
    gx, gy = ox - M, oy - M
    surf = np.zeros((size, size), dtype=np.uint8)
    mask = np.zeros((size, size), dtype=np.uint8)
    wet = water.mask(gx, gy, size)
    surf[wet] = S_WATER
    mask[wet] = FULL
    aux = {k: np.zeros((size, size), dtype=bool) for k in ("h", "v", "d", "strip_h", "strip_v")}
    aux["under"] = np.zeros((size, size), dtype=np.uint8)
    for r in sorted(cell_rects, key=lambda r: r.code):
        r.paint(surf, mask, gx, gy, aux)
    mask[(mask != 0) & ~np.isin(mask, list(HALF_OFFSET))] = FULL
    aux["under"][mask == FULL] = NONE
    drop_sidewalk_bits(cell_rects, surf, mask, aux, gx, gy)
    fill_pockets(surf, mask, aux["under"])
    smooth_shore(surf, mask)
    return surf, mask, aux["h"], aux["v"], aux["under"]


def drop_sidewalk_bits(cell_rects, surf, mask, aux, gx, gy):
    """A road's sidewalk strip is cut where other roads cross it; pieces shorter than SIDEWALK_MIN that are left
    (a scrap between two roads at a junction) are dropped. Sidewalk showing under a half tile counts as sidewalk."""
    size = surf.shape[0]
    shows = (surf == S_SIDEWALK) | ((mask != FULL) & (mask != 0) & (aux["under"] == S_SIDEWALK))
    for r in cell_rects:
        if not getattr(r, "strip", False):
            continue
        x0, x1 = max(r.x0 - gx, 0), min(r.x1 - gx, size)
        y0, y1 = max(r.y0 - gy, 0), min(r.y1 - gy, size)
        if x0 >= x1 or y0 >= y1:
            continue
        box_ = shows[y0:y1, x0:x1]
        along = box_.any(axis=0) if r.horizontal else box_.any(axis=1)
        n, k = len(along), 0
        lo = x0 if r.horizontal else y0
        while k < n:
            if not along[k]:
                k += 1
                continue
            e = k
            while e < n and along[e]:
                e += 1
            touches_edge = lo + k == 0 or lo + e == size
            if e - k < SIDEWALK_MIN and not touches_edge:
                if r.horizontal:
                    sl = (slice(y0, y1), slice(x0 + k, x0 + e))
                else:
                    sl = (slice(y0 + k, y0 + e), slice(x0, x1))
                own = surf[sl] == S_SIDEWALK
                surf[sl][own] = NONE
                mask[sl][own] = 0
                und = aux["under"][sl]
                und[und == S_SIDEWALK] = NONE
            k = e


def fill_pockets(surf, mask, under):
    """Grass shut in between roads at a junction (at most POCKET_SPAN across, not reaching the margin's edge) is
    paved: with sidewalk when it touches sidewalk, else with the asphalt around it. Small enclosed grass corners
    looked like squares cut out of the junction."""
    from scipy import ndimage
    empty = surf == NONE
    labels, count = ndimage.label(empty)
    if not count:
        return
    size = surf.shape[0]
    for k, sl in enumerate(ndimage.find_objects(labels), start=1):
        if sl is None:
            continue
        ys, xs = sl
        if ys.stop - ys.start > POCKET_SPAN or xs.stop - xs.start > POCKET_SPAN:
            continue
        if ys.start == 0 or xs.start == 0 or ys.stop == size or xs.stop == size:
            continue
        if int((labels[sl] == k).sum()) > POCKET_AREA:
            continue  # a traffic island, left as grass
        yy0, yy1, xx0, xx1 = max(ys.start - 1, 0), min(ys.stop + 1, size), max(xs.start - 1, 0), min(xs.stop + 1, size)
        pocket = labels[yy0:yy1, xx0:xx1] == k
        ring = np.zeros_like(pocket)
        ring[1:, :] |= pocket[:-1, :]
        ring[:-1, :] |= pocket[1:, :]
        ring[:, 1:] |= pocket[:, :-1]
        ring[:, :-1] |= pocket[:, 1:]
        ring &= ~pocket
        around = surf[yy0:yy1, xx0:xx1][ring]
        if (around == S_WATER).any() or (around == NONE).any():
            continue
        code = S_SIDEWALK if (around == S_SIDEWALK).any() else int(around.max())
        surf[yy0:yy1, xx0:xx1][pocket] = code
        mask[yy0:yy1, xx0:xx1][pocket] = FULL
        half = ring & (mask[yy0:yy1, xx0:xx1] != FULL) & (under[yy0:yy1, xx0:xx1] == NONE)
        under[yy0:yy1, xx0:xx1][half] = code


def smooth_shore(surf, mask):
    """Rasterised rivers make a staircase shoreline (jagged on screen). A bare square with water on exactly two
    adjacent sides becomes half water, cut along its diagonal: N+W water -> upper half, E+S -> lower, W+S -> left,
    N+E -> right."""
    wet = (surf == S_WATER) & (mask == FULL)
    n, s = np.zeros_like(wet), np.zeros_like(wet)
    w, e = np.zeros_like(wet), np.zeros_like(wet)
    n[1:, :], s[:-1, :] = wet[:-1, :], wet[1:, :]
    w[:, 1:], e[:, :-1] = wet[:, :-1], wet[:, 1:]
    bare = surf == NONE
    for half, (a, b, c, d) in ((9, (n, w, s, e)), (6, (e, s, n, w)), (12, (w, s, n, e)), (3, (n, e, s, w))):
        hit = bare & a & b & ~c & ~d
        surf[hit] = S_WATER
        mask[hit] = half


UNDER_TILE = {S_WATER: tiles.WATER, S_SIDEWALK: tiles.SIDEWALK, S_DIRT: tiles.DIRT_ROAD, S_MINOR: tiles.ASPHALT_MINOR,
              S_MAJOR: tiles.ASPHALT_MAJOR}


def square_tiles(surf, mask, hmask, vmask, lx, ly, x, y, lines_h, lines_v, marks, under=None):
    """lx, ly index the margin grid; x, y are absolute."""
    s = int(surf[ly, lx])
    m = int(mask[ly, lx])
    if s == S_WATER:
        if m != FULL:
            return [tiles.pick(tiles.GRASS, x, y), "blends_natural_02_%d" % HALF_OFFSET[m]]
        return [tiles.pick(tiles.WATER, x, y)]
    if m != FULL:
        u = int(under[ly, lx]) if under is not None else NONE
        base = tiles.pick(UNDER_TILE.get(u, tiles.GRASS), x, y)
        return [base, "blends_street_01_%d" % (FAMILY[s] + HALF_OFFSET[m])]
    base = {S_SIDEWALK: tiles.SIDEWALK, S_DIRT: tiles.DIRT_ROAD, S_MINOR: tiles.ASPHALT_MINOR,
            S_MAJOR: tiles.ASPHALT_MAJOR}[s]
    out = [tiles.pick(base, x, y)]
    for name, dx, dy in DIRS:
        if surf[ly + dy, lx + dx] == NONE:
            out.append(tiles.pick(tiles.GRASS_EDGE[name], x, y))
    south = int(surf[ly + 1, lx]) if mask[ly + 1, lx] == FULL else NONE
    east = int(surf[ly, lx + 1]) if mask[ly, lx + 1] == FULL else NONE
    if s == S_SIDEWALK and south in PAVED:
        out.append(tiles.CURB_SIDEWALK_S)
    if s in PAVED and south == S_SIDEWALK:
        out.append(tiles.CURB_ROAD_S)
    if s == S_SIDEWALK and east in PAVED:
        out.append(tiles.CURB_SIDEWALK_E)
    if s in PAVED and east == S_SIDEWALK:
        out.append(tiles.CURB_ROAD_E)
    if s in PAVED:
        if (x, y) in marks:
            out += marks[(x, y)]
        else:
            if (x, y) in lines_h and not vmask[ly, lx]:
                out += lines_h[(x, y)]
            if (x, y) in lines_v and not hmask[ly, lx]:
                out += lines_v[(x, y)]
    return out


def build_cell(cx, cy, rects, water, lines_h, lines_v, marks, from_vanilla, layer=None):
    ox, oy = cx * CELL, cy * CELL
    surf, mask, hmask, vmask, under = surfaces(rects, water, ox, oy)
    if from_vanilla:
        cell = Cell.load(config.VANILLA_MAP, cx, cy)
        cd = ChunkData.from_bytes(open(os.path.join(config.VANILLA_MAP, "chunkdata_%d_%d.bin" % (cx, cy)), "rb").read())
    else:
        cell, cd = Cell(cx, cy), ChunkData()
    core = surf[M:M + CELL, M:M + CELL]
    claimed = layer.claimed_mask(cx, cy) if layer else np.zeros((CELL, CELL), dtype=bool)
    core[claimed] = NONE  # landmarks draw their own ground there
    for ly, lx in zip(*np.nonzero(core)):
        lx, ly = int(lx), int(ly)
        s = int(core[ly, lx])
        if from_vanilla and s not in ROADS:
            continue  # only the connector is laid over vanilla cells
        x, y = ox + lx, oy + ly
        cell.set_square(lx, ly, 0, square_tiles(surf, mask, hmask, vmask, lx + M, ly + M, x, y, lines_h, lines_v,
                                                marks, under))
        cd.set(lx, ly, WATER if s == S_WATER and mask[ly + M, lx + M] == FULL else 0)
    if not from_vanilla:
        for ly, lx in zip(*np.nonzero((core == NONE) & ~claimed)):
            cd.set(int(lx), int(ly), NO_LOT)
    if layer:
        layer.apply(cx, cy, cell, cd)
    return cell, cd, np.where(mask[M:M + CELL, M:M + CELL] == FULL, core, NONE)


def clean_map_dir(cells):
    os.makedirs(os.path.join(config.MAP_DIR, "maps"), exist_ok=True)
    names = set()
    for cx, cy in cells:
        names |= {"%d_%d.lotheader" % (cx, cy), "world_%d_%d.lotpack" % (cx, cy), "chunkdata_%d_%d.bin" % (cx, cy)}
    for f in os.listdir(config.MAP_DIR):
        if f in names:
            os.remove(os.path.join(config.MAP_DIR, f))


def write_spawn(candidates):
    px, py = config.project(*config.PLAZA_RIZAL)
    x, y = min(candidates, key=lambda p: (p[0] + 0.5 - px) ** 2 + (p[1] + 0.5 - py) ** 2)
    point = "    { worldX = %d, worldY = %d, posX = %d, posY = %d, posZ = 0 },\n" % (x // 300, y // 300, x % 300, y % 300)
    with open(os.path.join(config.MAP_DIR, "spawnpoints.lua"), "w", newline="\n") as f:
        f.write("function SpawnPoints()\nreturn {\n  unemployed = {\n" + point + "  },\n}\nend\n")
    with open(os.path.join(config.MAP_DIR, "spawnregions.lua"), "w", newline="\n") as f:
        f.write('function SpawnRegions()\nreturn {\n{ name = "%s", file = "media/maps/%s/spawnpoints.lua" }\n}\nend\n'
                % (config.MAP_NAME, config.MAP_NAME))
    return x, y


def street_name(name):
    """Map label text: compatibility forms folded (Santiago Ⅲ Street -> Santiago III Street; the map's font has no
    Roman-numeral symbols), letters like n-tilde kept."""
    import unicodedata
    return " ".join(unicodedata.normalize("NFKC", name).split())


def _join(a, b):
    """Two (start node, end node, points, width) chains joined end to end, or None."""
    (a0, a1, pa, wa), (b0, b1, pb, wb) = a, b
    w = max(wa, wb)
    if a1 == b0:
        return a0, b1, pa + pb[1:], w
    if a1 == b1:
        return a0, b0, pa + pb[::-1][1:], w
    if a0 == b1:
        return b0, a1, pb + pa[1:], w
    if a0 == b0:
        return b1, a1, pb[::-1] + pa[1:], w
    return None


def write_streets(plan):
    """streets.xml: every named road of the plan, for the in-game world map's street names. The game also makes each
    street a "Nav" zone (WorldMapStreet.registerNavZones, from metazoneHandler's OnLoadMapZones), where randomized
    vehicle stories (crashes, roadside scenes) spawn and road foraging applies; streets named like a railroad are
    skipped by the game. Format (zombie/worldMap/streets/WorldMapStreetsXML): <streets version="1">, <street name
    width>, <points><point x y/>. Roads of one name that meet end to end are written as one street."""
    from xml.sax.saxutils import quoteattr
    by_name = defaultdict(list)
    for r in plan["roads"]:
        if r.get("name", "").strip():
            by_name[street_name(r["name"])].append(r)
    streets = []
    for name, roads in sorted(by_name.items()):
        chains = [(r["points"][0], r["points"][-1], roadplan.polyline(plan, r), r["width"]) for r in roads]
        joined = True
        while joined:  # join chains sharing an end node
            joined = False
            for i in range(len(chains)):
                for j in range(i + 1, len(chains)):
                    c = _join(chains[i], chains[j])
                    if c:
                        chains[i] = c
                        del chains[j]
                        joined = True
                        break
                if joined:
                    break
        streets += [(name, c[3], c[2]) for c in chains]
    out = ['<streets version="1">']
    for name, width, pts in streets:
        out.append('    <street name=%s width="%d">' % (quoteattr(name), width))
        out.append("        <points>")
        out += ['            <point x="%.1f" y="%.1f"/>' % (x, y) for x, y in pts]
        out.append("        </points>")
        out.append("    </street>")
    out.append("</streets>")
    with open(os.path.join(config.MAP_DIR, "streets.xml"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")
    return len(streets), len(by_name)


def write_worldmap(rects, water):
    wm = WorldMapWriter()
    cover = box(config.COVER[0] * CELL, config.COVER[1] * CELL, (config.COVER[2] + 1) * CELL,
                (config.COVER[3] + 1) * CELL)
    for g in water.geoms:
        wm.add({"water": "river"}, g.intersection(cover))
    by_class = defaultdict(list)
    for r in rects:
        if r.code in WM_HIGHWAY:
            if isinstance(r, Diag):
                g = LineString(r.line).buffer(r.width / 2, cap_style="flat")
            else:
                g = box(r.x0, r.y0, r.x1, r.y1)
            by_class[WM_HIGHWAY[r.code]].append(g)
    for hw in ("trail", "tertiary", "primary"):
        merged = unary_union(by_class[hw]).difference(box(0, 0, config.RC_LINK_END_X + 1, 10 ** 6))
        for poly in raster.polygons(merged):
            wm.add({"highway": hw}, poly)
    wm.save(os.path.join(config.MAP_DIR, "worldmap.xml"))


def main():
    start = time.time()
    x0, y0, x1, y1 = config.COVER
    if len(sys.argv) == 5:
        x0, y0, x1, y1 = map(int, sys.argv[1:])
    clip = (config.COVER[0] * CELL, config.COVER[1] * CELL, (config.COVER[2] + 1) * CELL, (config.COVER[3] + 1) * CELL)
    data = osm.load(clip)  # water, land use and buildings; the roads come from the plan
    plan = roadplan.load()
    problems = roadplan.check(plan)
    if problems:
        raise SystemExit("road plan: " + "; ".join(problems[:50]))
    rects, lines_h, lines_v, end = build_network(plan)
    marks = {}
    connector(end, rects, marks)
    water = Water(data)
    biomes = Biomes(data, water)
    by_cell = bucket(rects)
    layer = LandmarkLayer(landmarks.build_all())
    print("network: %d rectangles, connector ends at %s (%.0f s)" % (len(rects), end, time.time() - start))

    cells = [(cx, cy) for cx in range(x0, x1 + 1) for cy in range(y0, y1 + 1)
             if config.COVER[0] <= cx <= config.COVER[2] and config.COVER[1] <= cy <= config.COVER[3]]
    vanilla = list(config.CONNECTOR_VANILLA_CELLS)
    clean_map_dir(cells + vanilla)
    plaza = config.project(*config.PLAZA_RIZAL)
    near_plaza, total = [], 0
    for i, (cx, cy) in enumerate(vanilla + cells):
        from_vanilla = (cx, cy) in vanilla
        cell, cd, core = build_cell(cx, cy, by_cell.get((cx, cy), []), water, lines_h, lines_v, marks, from_vanilla,
                                    None if from_vanilla else layer)
        cell.save(config.MAP_DIR)
        cd.save(os.path.join(config.MAP_DIR, "chunkdata_%d_%d.bin" % (cx, cy)))
        if not from_vanilla:
            values = biomes.cell(cx * CELL, cy * CELL)
            values[layer.claimed_mask(cx, cy)] = biome.TOWN
            biome.save(os.path.join(config.MAP_DIR, "maps", "biomemap_%d_%d.png" % (cx, cy)), values)
        total += int((core != NONE).sum())
        if abs(cx * CELL + 128 - plaza[0]) < 300 and abs(cy * CELL + 128 - plaza[1]) < 300:
            ys, xs = np.nonzero(np.isin(core, PAVED))
            near_plaza += [(cx * CELL + int(a), cy * CELL + int(b)) for a, b in zip(xs, ys)]
        if (i + 1) % 100 == 0:
            print("  %d / %d cells (%.0f s)" % (i + 1, len(vanilla) + len(cells), time.time() - start))
    write_worldmap(rects, water)
    n_streets, n_names = write_streets(plan)
    print("streets.xml: %d streets, %d names" % (n_streets, n_names))
    with open(os.path.join(config.MAP_DIR, "objects.lua"), "w", newline="\n") as f:
        f.write("objects = {\n}\n")
    spawn = write_spawn(near_plaza) if near_plaza else None
    size = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(config.MAP_DIR) for f in fs)
    print("done: %d cells, %d paved/water squares, spawn %s, map folder %.1f MB, %.0f s" % (
        len(vanilla) + len(cells), total, spawn, size / 1e6, time.time() - start))


if __name__ == "__main__":
    main()
