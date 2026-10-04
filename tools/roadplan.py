"""The road plan: Naga's finished roads, the fixed base every later phase builds on (the user, 2026-10-05: "if we
create a final product of the roads, that becomes the template we can always go back to when we generate buildings").

plan/roads.json (tracked in git) is the only source of the roads once drafted:
- `nodes`: id -> [x, y], integer PZ tile coordinates of every road point. OSM node ids where the point came from one
  (junctions, road ends), "b<n>" for bends the straightener made. A node shared by roads is a junction: moving it moves
  every road through it.
- `roads`: one per highway route / other OSM way: `id`, `name`, `class` (OSM highway class), `width` (carriageway
  tiles, even), `sidewalk` (tiles per side), `center_line`, `surface` (asphalt / dirt / sidewalk), `osm` (way id), and
  `points`, the node ids in order. Consecutive points are joined straight, 45 degrees or, when they are neither (a point
  moved by hand), straight / 45 degrees / straight, or a square corner when that diagonal would be short (`route`).
- `areas`: paved rectangles (plazas from OSM pedestrian areas): `name`, `surface`, `rect` [x0, y0, x1, y1].
- `connector_end`: the node where the road from Raven Creek arrives (north end of Calabanga Road).

Only `draft` reads OSM (simplified by netprep.py, straightened by roads.py, cleaned by roadtidy.py); it refuses to replace an existing plan
without --force. `tidy` cleans the saved plan again (after hand edits). Generating the map (generate.py) and every later
phase read the plan.

    tools/.venv/Scripts/python.exe tools/roadplan.py draft [--force]
    tools/.venv/Scripts/python.exe tools/roadplan.py tidy
    tools/.venv/Scripts/python.exe tools/roadplan.py check"""
import json
import math
import os
import sys

import config
import osm
import roads as roadnet
import netprep
import roadtidy

PLAN = os.path.join(config.PLAN_DIR, "roads.json")
SURFACES = ("asphalt", "dirt", "sidewalk")


class PlanRoad:
    """A plan road with the attribute names generate.py reads from osm.Road."""
    __slots__ = ("id", "name", "cls", "width", "sidewalk", "center_line", "surface", "osm_id", "points")

    def __init__(self, d):
        self.id, self.name, self.cls = d["id"], d.get("name", ""), d["class"]
        self.width, self.sidewalk = int(d["width"]), int(d.get("sidewalk", 0))
        self.center_line, self.surface = bool(d.get("center_line")), d.get("surface", "asphalt")
        self.osm_id, self.points = d.get("osm"), list(d["points"])


def _road_dict(rid, r):
    return {"id": rid, "name": r.tags.get("name") or r.tags.get("ref") or "", "class": r.cls, "width": r.width,
            "sidewalk": r.sidewalk, "center_line": r.center_line, "surface": r.surface, "osm": r.osm_id}


def draft():
    """The straightened OSM network as a plan."""
    clip = (config.COVER[0] * config.CELL, config.COVER[1] * config.CELL, (config.COVER[2] + 1) * config.CELL,
            (config.COVER[3] + 1) * config.CELL)
    data = osm.load(clip)
    line_roads = netprep.prepare([r for r in data["roads"] if r.nodes])
    _, final, lines, alias = roadnet.schematize(line_roads, lines=True)
    nodes, bend_no, roads = {}, 0, []
    for k, (i, line) in enumerate(lines):
        pts = []
        for n, pt in line:
            if n is None:
                bend_no += 1
                nid = "b%d" % bend_no
            else:
                nid = str(alias.get(n, n))
            old = nodes.setdefault(nid, [int(pt[0]), int(pt[1])])
            if old != [int(pt[0]), int(pt[1])]:
                raise ValueError("node %s placed twice: %s and %s" % (nid, old, pt))
            if not pts or pts[-1] != nid:
                pts.append(nid)
        if len(pts) >= 2:
            d = _road_dict("r%d" % (k + 1), line_roads[i])
            d["points"] = pts
            roads.append(d)
    areas = []
    for r in data["roads"]:
        if not r.nodes and r.surface == "sidewalk":
            minx, miny, maxx, maxy = (int(round(v)) for v in r.line.bounds)
            areas.append({"name": r.tags.get("name", ""), "surface": "sidewalk", "rect": [minx, miny, maxx, maxy],
                          "osm": r.osm_id})
    calabanga = next(r for r in line_roads if r.osm_id == config.CALABANGA_WAY)
    end = str(alias.get(calabanga.nodes[0], calabanga.nodes[0]))
    if end not in nodes:
        raise ValueError("Calabanga Road's north end %s is not a plan node" % end)
    plan = {"version": 1, "connector_end": end, "nodes": nodes, "roads": roads, "areas": areas}
    return roadtidy.tidy(plan, route)


def save(plan, path=PLAN):
    """One node / road / area per line, so git diffs show what moved."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    dump = lambda v: json.dumps(v, ensure_ascii=False, separators=(",", ":"))
    out = ['{"version":%d,' % plan["version"], '"connector_end":%s,' % dump(plan["connector_end"]), '"nodes":{']
    def order(k):  # OSM nodes by number, then bends by number, then anything else
        if k.isdigit():
            return 0, int(k), ""
        if k[:1] == "b" and k[1:].isdigit():
            return 1, int(k[1:]), ""
        return 2, 0, k
    keys = sorted(plan["nodes"], key=order)
    out += ["%s:%s%s" % (dump(k), dump(plan["nodes"][k]), "," if j < len(keys) - 1 else "") for j, k in enumerate(keys)]
    out.append('},"roads":[')
    out += [dump(r) + ("," if j < len(plan["roads"]) - 1 else "") for j, r in enumerate(plan["roads"])]
    out.append('],"areas":[')
    out += [dump(a) + ("," if j < len(plan["areas"]) - 1 else "") for j, a in enumerate(plan["areas"])]
    out.append("]}")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")


def load(path=PLAN):
    if not os.path.exists(path):
        raise SystemExit("No road plan at %s: run `roadplan.py draft` first." % path)
    return json.load(open(path, encoding="utf-8"))


def check(plan):
    """Problems that would break generation, as strings."""
    out = []
    nodes = plan["nodes"]
    for k, v in nodes.items():
        if not (isinstance(v, list) and len(v) == 2 and all(isinstance(c, int) for c in v)):
            out.append("node %s: not two integers: %r" % (k, v))
    ids = set()
    for r in plan["roads"]:
        rid = r.get("id")
        if rid in ids:
            out.append("road %s: id used twice" % rid)
        ids.add(rid)
        if r.get("class") not in roadnet.RANK:
            out.append("road %s: unknown class %r" % (rid, r.get("class")))
        if not isinstance(r.get("width"), int) or r["width"] < 2 or r["width"] % 2:
            out.append("road %s: width must be an even number >= 2, got %r" % (rid, r.get("width")))
        if r.get("surface") not in SURFACES:
            out.append("road %s: surface must be one of %s" % (rid, ", ".join(SURFACES)))
        pts = r.get("points", [])
        if len(pts) < 2:
            out.append("road %s: fewer than two points" % rid)
        for n in pts:
            if n not in nodes:
                out.append("road %s: unknown node %s" % (rid, n))
    if plan.get("connector_end") not in nodes:
        out.append("connector_end %r is not a node" % plan.get("connector_end"))
    for a in plan["areas"]:
        x0, y0, x1, y1 = a["rect"]
        if not (x0 < x1 and y0 < y1):
            out.append("area %r: empty rect" % a.get("name"))
    return out


def route(a, b):
    """The straight / 45-degree pieces joining two points: as is when they already line up (same x, same y, or a
    pure diagonal), else roads.py's straight / 45 degrees / straight or square corner."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    if dx == 0 or dy == 0 or abs(dx) == abs(dy):
        return [(a, b)] if a != b else []
    return [(p, q) for p, q in roadnet._path(a, b, None) if p != q]


def polyline(plan, road):
    """A plan road (dict) as its drawn points: every bend route() adds included."""
    nodes = plan["nodes"]
    pts = [tuple(nodes[road["points"][0]])]
    for a, b in zip(road["points"], road["points"][1:]):
        pts += [q for _, q in route(tuple(nodes[a]), tuple(nodes[b]))]
    return pts


def _direction(p, q):
    return ((q[0] > p[0]) - (q[0] < p[0]), (q[1] > p[1]) - (q[1] < p[1]))


def pieces(plan):
    """(roads.Piece list whose .road indexes the returned PlanRoad list, PlanRoad list). Consecutive pieces of a road
    going the same way are merged (a junction in the middle of a straight run does not break its sidewalk or centre
    line)."""
    nodes = {k: tuple(v) for k, v in plan["nodes"].items()}
    roads, out = [PlanRoad(d) for d in plan["roads"]], []
    for i, r in enumerate(roads):
        run = []
        for a, b in zip(r.points, r.points[1:]):
            run += route(nodes[a], nodes[b])
        merged = []
        for p, q in run:
            if merged and merged[-1][1] == p and _direction(*merged[-1]) == _direction(p, q):
                merged[-1] = (merged[-1][0], q)
            else:
                merged.append((p, q))
        out += [roadnet.Piece(p, q, i) for p, q in merged]
    return out, roads


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "draft":
        if os.path.exists(PLAN) and "--force" not in sys.argv:
            raise SystemExit("%s exists; it is the finished road plan. Use --force to replace it with a new draft."
                             % PLAN)
        plan = draft()
        problems = check(plan)
        if problems:
            raise SystemExit("\n".join(problems[:50]))
        save(plan)
        length = sum(math.dist(plan["nodes"][a], plan["nodes"][b])
                     for r in plan["roads"] for a, b in zip(r["points"], r["points"][1:]))
        print("%s: %d roads, %d nodes, %d areas, %.0f km of centre line" % (
            PLAN, len(plan["roads"]), len(plan["nodes"]), len(plan["areas"]), length / 1000))
    elif cmd == "tidy":
        plan = roadtidy.tidy(load(), route)
        problems = check(plan)
        if problems:
            raise SystemExit("\n".join(problems[:50]))
        save(plan)
        print("%s: %d roads, %d nodes" %(PLAN, len(plan["roads"]), len(plan["nodes"])))
    elif cmd == "check":
        problems = check(load())
        print("\n".join(problems) if problems else "plan OK")
        if problems:
            raise SystemExit(1)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
