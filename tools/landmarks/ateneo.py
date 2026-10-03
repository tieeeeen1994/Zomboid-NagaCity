"""Ateneo de Naga University, the college campus on Ateneo Avenue (OSM way 222268858), hand-planned.

The campus grid runs about 24 degrees off north, so the whole plan is turned by -24 degrees about the campus centroid
(the Zomboid way: buildings straight north-south / east-west, places where they really are relative to each other).
Every OSM building inside it keeps its real footprint (turned and squared), name and storey count; its type picks the
template (classroom block, library, offices, gym, church, residence...). The grounds: lawn everywhere, OSM walks and
service roads as concrete, the soccer field, the tennis court, parking."""
import json
import math
from types import SimpleNamespace

from shapely import affinity
from shapely.geometry import LineString, Polygon

import config
import roads
import layout as L
import templates as T
from tiles import pick
from buildkit import Canvas, WallSet
from pzmap import raster

CAMPUS_WAY = 222268858
ANGLE = -24
EXTERIOR = WallSet("walls_commercial_03", 1, 0)

LAWN = ["blends_natural_01_16", "blends_natural_01_21", "blends_natural_01_22", "blends_natural_01_23"]
WALK = ["blends_street_01_48", "blends_street_01_53", "blends_street_01_54", "blends_street_01_55"]
DRIVE = ["blends_street_01_96", "blends_street_01_101", "blends_street_01_102", "blends_street_01_103"]
COURT = "floors_exterior_street_01_16"

# name -> (template, default levels); unnamed / unlisted buildings: by OSM building tag
KIND = {
    "Administration Building": ("offices", 2),
    "James O'Brien Library": ("library", 3),
    "University Gymnasium": ("gym", 1),
    "Christ the King Church": ("church", 1),
    "Jesuit Residence": ("house", 2),
    "Physical Plant Administration": ("storage", 1),
    "Madrigal Building": ("offices", 2),
    "Entrep Building": ("offices", 2),
    "Faber Center": ("offices", 2),
    "Ateneo Child Learning Center": ("daycare", 1),
    "Band Room": ("classroom_hall", 1),
    "Guard House": ("guard", 1),
}


def build(canvas=None):
    canvas = canvas or Canvas()
    data = json.load(open(config.OSM_FILE, encoding="utf-8"))
    ways = {e["id"]: e for e in data["elements"] if e["type"] == "way" and "geometry" in e}

    def poly(e):
        return Polygon([config.project(g["lat"], g["lon"]) for g in e["geometry"]])

    campus = poly(ways[CAMPUS_WAY])
    origin = campus.centroid

    def turn(g):
        return affinity.rotate(g, ANGLE, origin=origin)

    area = turn(campus)
    minx, miny, maxx, maxy = (int(math.floor(v)) for v in area.bounds)
    w, h = maxx - minx + 2, maxy - miny + 2
    # the turned outline still has slanted sides: square it off into large rectangles (no jagged edges)
    outline = raster.mask([area], minx, miny, w, h)
    inside = outline & False
    for x, y, rw, rh in wings_of(outline, min_side=16, keep=0.97) or []:
        inside[y:y + rh, x:x + rw] = True

    def squares(g):
        m = raster.mask([g], minx, miny, w, h) & inside
        ys, xs = m.nonzero()
        return {(minx + int(x), miny + int(y)) for x, y in zip(xs, ys)}

    # grounds, lowest layer first: lawn, then parking / courts as rectangles, then walks and drives straightened
    # like the streets (roads.schematize, square corners only) and laid as straight strips
    ground = {}
    ys, xs = inside.nonzero()
    for x, y in zip(xs.tolist(), ys.tolist()):
        ground[(minx + x, miny + y)] = pick(LAWN, minx + x, miny + y)

    def fill(x0, y0, x1, y1, tiles):
        for y in range(y0, y1):
            for x in range(x0, x1):
                if 0 <= x - minx < w and 0 <= y - miny < h and inside[y - miny, x - minx]:
                    ground[(x, y)] = pick(tiles, x, y)

    paths = []
    for e in ways.values():
        t = e.get("tags", {})
        if t.get("amenity") == "parking" or (t.get("leisure") == "pitch" and t.get("sport") == "tennis"):
            if len(e["geometry"]) < 4:
                continue
            g = turn(poly(e))
            if g.intersects(area):
                bx0, by0, bx1, by1 = (int(round(v)) for v in g.bounds)
                fill(bx0, by0, bx1, by1, DRIVE if t.get("amenity") == "parking" else [COURT])
        elif t.get("highway") in ("service", "footway", "pedestrian", "path") and len(e.get("nodes", [])) >= 2:
            line = turn(LineString([config.project(p["lat"], p["lon"]) for p in e["geometry"]]))
            if line.intersects(area):
                paths.append(SimpleNamespace(line=line, nodes=e["nodes"], cls=t["highway"], tags=t, osm_id=e["id"],
                                             width=6 if t["highway"] == "service" else 2))
    saved = roads.MIN_DIAG
    roads.MIN_DIAG = float("inf")  # campus paths: square corners only
    try:
        pieces, _ = roads.schematize(paths)
    finally:
        roads.MIN_DIAG = saved
    for p in sorted(pieces, key=lambda p: paths[p.road].width):
        r = paths[p.road]
        fill(*p.rect(r.width // 2), DRIVE if r.cls == "service" else WALK)
    for (x, y), tile in ground.items():
        canvas.ground(x, y, [tile])

    # buildings
    placed = []
    for e in ways.values():
        t = e.get("tags", {})
        if "building" not in t or len(e["geometry"]) < 4:
            continue
        p = poly(e)
        if not p.is_valid or p.intersection(campus).area < 0.5 * p.area:
            continue
        name = t.get("name", "")
        kind, default_levels = KIND.get(name, ("school", 2) if t.get("building") == "school" else
                                        ("roof", 1) if t.get("building") == "roof" else ("offices", 1))
        levels = int(t.get("building:levels", default_levels) or default_levels)
        r = turn(p)
        bx0, by0, bx1, by1 = (int(round(v)) for v in r.bounds)
        bw, bh = bx1 - bx0, by1 - by0
        if bw < 4 or bh < 4:
            continue
        placed.append((name or "#%d" % e["id"], kind, levels, bx0, by0, bw, bh, r))

    # Buildings sized to vanilla rooms (layout.py), centred on the real ones; L / U footprints become separate
    # wings; a building that would overlap one already placed is shrunk (90 %, 80 %, 70 %) or left out.
    taken, jobs = [], []
    for name, kind, levels, x, y, bw, bh, shape in placed:
        if kind == "roof":
            covered_court(canvas, x, y, bw, bh)
            taken.append((x, y, x + bw - 1, y + bh - 1))
            continue
        local = raster.mask([shape], x, y, bw, bh)
        parts = wings_of(local) if local.mean() < 0.8 and kind in ("school", "offices") else None
        for wx, wy, ww, wh in parts or [(0, 0, bw, bh)]:
            jobs.append((name, kind, levels, x + wx, y + wy, ww, wh))

    def free(r):
        return all(r[2] + 2 < t[0] or t[2] + 2 < r[0] or r[3] + 2 < t[1] or t[3] + 2 < r[1] for t in taken)

    for k, (name, kind, levels, x, y, bw, bh) in enumerate(sorted(jobs, key=lambda j: -j[5] * j[6])):
        cx, cy = x + bw / 2, y + bh / 2
        horizontal = bw >= bh
        long_side, short_side = max(bw, bh), min(bw, bh)
        seed = sum(map(ord, name)) + k
        placed_ok = False
        for scale in (1.0, 0.9, 0.8, 0.7):
            res = vanilla_layout(kind, round(long_side * scale), round(short_side * scale), horizontal, levels, seed)
            if res is None:
                break
            lay, entries = res
            ox, oy = int(round(cx - lay.w / 2)), int(round(cy - lay.h / 2))
            rect = (ox, oy, ox + lay.w - 1, oy + lay.h - 1)
            if free(rect):
                lay.building(name, ox, oy, EXTERIOR, levels, entries).draw(canvas)
                taken.append(rect)
                placed_ok = True
                break
        if not placed_ok:
            print("ateneo: no room for %s (%s, %dx%d)" % (name, kind, bw, bh))
    return canvas


def vanilla_layout(kind, long_side, short_side, horizontal, levels, seed):
    if kind in ("church", "gym"):
        return L.hall_building(kind, long_side, short_side, horizontal, seed)
    if kind in ("security", "guard", "classroom_hall") or short_side < 8:
        return L.single_room({"classroom_hall": "classroom", "guard": "security"}.get(kind, kind), long_side,
                             short_side, horizontal, seed)
    mix = {"school": "school", "offices": "offices", "library": "library", "house": "house", "daycare": "daycare",
           "storage": "storage"}.get(kind, "offices")
    return L.corridor_building(mix, long_side, short_side, horizontal, levels, seed)


def wings_of(mask, min_side=8, keep=0.85):
    """An L / U / T footprint (bool [y, x]) as rectangles (x, y, w, h), largest first, until `keep` of it is covered
    or no rectangle with both sides >= min_side is left."""
    m = mask.copy()
    total, wings = m.sum(), []
    while m.sum() > (1 - keep) * total:
        best = _largest_rect(m)
        if best is None or min(best[2], best[3]) < min_side:
            break
        x, y, w, h = best
        m[y:y + h, x:x + w] = False
        wings.append(best)
    return wings or None


def _largest_rect(m):
    """Largest all-True axis-aligned rectangle (histogram method)."""
    h, w = m.shape
    heights = [0] * w
    best, area = None, 0
    for y in range(h):
        for x in range(w):
            heights[x] = heights[x] + 1 if m[y, x] else 0
        stack = []
        for x in range(w + 1):
            cur = heights[x] if x < w else 0
            start = x
            while stack and stack[-1][1] >= cur:
                start, hh = stack.pop()
                if hh * (x - start) > area:
                    area, best = hh * (x - start), (start, y - hh + 1, x - start, hh)
            stack.append((start, cur))
    return best


def covered_court(canvas, x0, y0, w, h):
    """The big open-sided roof by the soccer field: a court floor, posts, a roof one level up."""
    for y in range(y0, y0 + h):
        for x in range(x0, x0 + w):
            canvas.squares[(x, y, 0)] = [COURT]
            canvas.claimed.add((x, y))
            canvas.add(x, y, 1, ["roofs_04_54"])
