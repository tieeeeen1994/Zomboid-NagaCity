"""Generate Naga City's map files into Contents/mods/NagaCity/common/media/maps/Naga City, PH/.

Ground only so far: roads straightened to north-south / east-west pieces (roads.py) and laid with vanilla's street
recipe (asphalt, sidewalks, curbs, grass edges, centre lines), rivers, biome maps, the connector from Raven Creek, the
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
M = 1  # margin squares around a cell, so edges and curbs see their neighbours

WM_HIGHWAY = {S_MAJOR: "primary", S_MINOR: "tertiary", S_DIRT: "trail"}

# Coverage of a square as four triangles (centre to edge): N 1, E 2, S 4, W 8. A 45-degree road edge cuts a square
# along a diagonal, leaving half of it: N+E (right half on screen), W+S (left), N+W (upper), E+S (lower). Vanilla's
# half tiles are the family base + 1 (upper), + 2 (lower), + 3 (left), + 4 (right), the other half grass.
FULL = 15
HALF_OFFSET = {9: 1, 6: 2, 12: 3, 3: 4}
FAMILY = {S_MAJOR: 80, S_MINOR: 96, S_SIDEWALK: 48, S_DIRT: 16}


class Rect:
    __slots__ = ("x0", "y0", "x1", "y1", "code", "horizontal")

    def __init__(self, r, code, horizontal):
        self.x0, self.y0, self.x1, self.y1 = r
        self.code, self.horizontal = code, horizontal

    def paint(self, surf, mask, gx, gy, hmask, vmask, dmask):
        size = surf.shape[0]
        x0, x1 = max(self.x0 - gx, 0), min(self.x1 - gx, size)
        y0, y1 = max(self.y0 - gy, 0), min(self.y1 - gy, size)
        if x0 >= x1 or y0 >= y1:
            return
        region = surf[y0:y1, x0:x1]
        np.maximum(region, self.code, out=region)
        mask[y0:y1, x0:x1] = FULL
        if self.code in PAVED:
            (hmask if self.horizontal else vmask)[y0:y1, x0:x1] = True


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

    def paint(self, surf, mask, gx, gy, hmask, vmask, dmask):
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
        hit = cover > 0
        region, mregion = surf[y0:y1, x0:x1], mask[y0:y1, x0:x1]
        region[hit] = np.maximum(region[hit], self.code)
        mregion[hit] |= cover[hit]
        dmask[y0:y1, x0:x1] |= hit


def road_code(road):
    if road.surface == "dirt":
        return S_DIRT
    if road.surface == "sidewalk":
        return S_SIDEWALK
    return S_MAJOR if roadnet.RANK.get(road.cls, 3) >= MAJOR_RANK else S_MINOR


def build_network(data):
    line_roads = [r for r in data["roads"] if r.nodes]
    pieces, final = roadnet.schematize(line_roads)
    rects, lines_h, lines_v = [], {}, {}
    for p in pieces:
        r = line_roads[p.road]
        half = r.width // 2
        code = road_code(r)
        if p.diagonal:
            rects.append(Diag(p, r.width, code))
            continue
        rects.append(Rect(p.rect(half), code, p.horizontal))
        if r.sidewalk and code != S_SIDEWALK and max(p.x1 - p.x0, p.y1 - p.y0) >= SIDEWALK_MIN:
            x0, y0, x1, y1 = p.rect(half)  # widened across the road only: no sidewalk past the road's end
            s = r.sidewalk
            box_ = (x0, y0 - s, x1, y1 + s) if p.horizontal else (x0 - s, y0, x1 + s, y1)
            rects.append(Rect(box_, S_SIDEWALK, p.horizontal))
        if r.center_line:
            if p.horizontal:
                for x in range(p.x0 + half + 2, p.x1 - half - 2):
                    lines_h.setdefault((x, p.y0 - 1), []).append(tiles.YELLOW["S"])
                    lines_h.setdefault((x, p.y0), []).append(tiles.YELLOW["N"])
            else:
                for y in range(p.y0 + half + 2, p.y1 - half - 2):
                    lines_v.setdefault((p.x0 - 1, y), []).append(tiles.YELLOW["E"])
                    lines_v.setdefault((p.x0, y), []).append(tiles.YELLOW["W"])
    calabanga = next(r for r in line_roads if r.osm_id == config.CALABANGA_WAY)
    end = final[calabanga.nodes[0]]
    return rects, lines_h, lines_v, end


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
    hmask = np.zeros((size, size), dtype=bool)
    vmask = np.zeros((size, size), dtype=bool)
    dmask = np.zeros((size, size), dtype=bool)
    for r in sorted(cell_rects, key=lambda r: r.code):
        r.paint(surf, mask, gx, gy, hmask, vmask, dmask)
    mask[(mask != 0) & ~np.isin(mask, list(HALF_OFFSET))] = FULL
    # No sidewalk touching a 45-degree road: its half tiles have no sidewalk version, so the corner would notch.
    near = dmask.copy()
    near[1:, :] |= dmask[:-1, :]
    near[:-1, :] |= dmask[1:, :]
    near[:, 1:] |= near[:, :-1].copy()
    near[:, :-1] |= near[:, 1:].copy()
    drop = near & (surf == S_SIDEWALK)
    surf[drop] = NONE
    mask[drop] = 0
    smooth_shore(surf, mask)
    return surf, mask, hmask, vmask


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


def square_tiles(surf, mask, hmask, vmask, lx, ly, x, y, lines_h, lines_v, marks):
    """lx, ly index the margin grid; x, y are absolute."""
    s = int(surf[ly, lx])
    m = int(mask[ly, lx])
    if s == S_WATER:
        if m != FULL:
            return [tiles.pick(tiles.GRASS, x, y), "blends_natural_02_%d" % HALF_OFFSET[m]]
        return [tiles.pick(tiles.WATER, x, y)]
    if m != FULL:
        return [tiles.pick(tiles.GRASS, x, y), "blends_street_01_%d" % (FAMILY[s] + HALF_OFFSET[m])]
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
    surf, mask, hmask, vmask = surfaces(rects, water, ox, oy)
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
                                                marks))
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
    data = osm.load(clip)
    rects, lines_h, lines_v, end = build_network(data)
    marks = {}
    connector(end, rects, marks)
    for r in data["roads"]:  # pedestrian areas (plazas) as drawn in OSM
        if not r.nodes and r.surface == "sidewalk":
            minx, miny, maxx, maxy = (int(round(v)) for v in r.line.bounds)
            rects.append(Rect((minx, miny, maxx, maxy), S_SIDEWALK, True))
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
    with open(os.path.join(config.MAP_DIR, "objects.lua"), "w", newline="\n") as f:
        f.write("objects = {\n}\n")
    spawn = write_spawn(near_plaza) if near_plaza else None
    size = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(config.MAP_DIR) for f in fs)
    print("done: %d cells, %d paved/water squares, spawn %s, map folder %.1f MB, %.0f s" % (
        len(vanilla) + len(cells), total, spawn, size / 1e6, time.time() - start))


if __name__ == "__main__":
    main()
