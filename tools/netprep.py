"""OSM road network simplified before straightening (roadplan.draft), so the plan starts without the knots the
straightener makes of them (the user, 2026-10-05: "I hate these jagged stuff"):
- slip roads (`*_link`) are dropped;
- roundabouts (junction = roundabout / circular, the Naga Rotonda among them) become one plain junction at their
  centre: the ring is dropped and every road that touched it runs to the centre;
- split carriageways (two one-way ways of the same name and class running side by side in opposite directions,
  Mabolo Road / Roxas Avenue / Maharlika Highway in places) become one two-way road: the eastbound / southbound side
  is kept (as the wider of the two, with a centre line), the other dropped, and the side streets that joined the
  dropped side are moved onto the kept one at the nearest point.
- junction clusters (several junctions within CLUSTER m of each other along the roads: wide intersections, offset
  T-junctions) become one junction at their centre; the short road bits between them go.
Works on osm.Road objects (line roads with node ids); returns a new list."""
import math
from collections import defaultdict

from shapely.geometry import LineString, Point

import osm

TWIN_DIST = 30      # m between the two carriageways' centre lines, at most (unnamed pairs: TWIN_DIST_UNNAMED)
TWIN_DIST_UNNAMED = 20
TWIN_SHARE = 0.6    # share of a way's length that must run beside its twin
TWIN_CLASSES = {"trunk", "primary", "secondary", "tertiary"}
CLUSTER = 14        # m along the roads between junctions that become one


def _copy(r, line, nodes, **kw):
    out = osm.Road(line, r.cls, r.width, r.sidewalk, r.center_line, r.surface, dict(r.tags), r.osm_id, nodes)
    for k, v in kw.items():
        setattr(out, k, v)
    return out


def _rebuild(r, pairs):
    """Road with the given (node id, point) sequence, consecutive repeats removed; None when under two nodes."""
    seq = []
    for n, p in pairs:
        if not seq or seq[-1][0] != n:
            seq.append((n, p))
    if len(seq) < 2:
        return None
    return _copy(r, LineString([p for _, p in seq]), [n for n, _ in seq])


def drop_links(roads):
    return [r for r in roads if not r.tags.get("highway", "").endswith("_link")]


def collapse_roundabouts(roads):
    ring = [r for r in roads if r.tags.get("junction") in ("roundabout", "circular")]
    if not ring:
        return roads, 0
    parent = {}

    def find(n):
        while parent.setdefault(n, n) != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n

    for r in ring:
        for a in r.nodes[1:]:
            parent[find(a)] = find(r.nodes[0])
    groups = defaultdict(list)
    for r in ring:
        groups[find(r.nodes[0])].append(r)
    centre, where = {}, {}
    for g, (root, members) in enumerate(groups.items()):
        pts = [p for r in members for p in r.line.coords]
        cid = -(g + 1)  # new node id
        centre[cid] = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
        for r in members:
            for n in r.nodes:
                where[n] = cid
    ring_ids = {id(r) for r in ring}
    out = []
    for r in roads:
        if id(r) in ring_ids:
            continue
        pairs = [(where.get(n, n), centre[where[n]] if n in where else p) for n, p in zip(r.nodes, r.line.coords)]
        nr = _rebuild(r, pairs)
        if nr is not None:
            out.append(nr)
    return out, len(groups)


def _forward(r):
    """The way's points in its driving direction."""
    pts = list(r.line.coords)
    return pts[::-1] if r.tags.get("oneway") == "-1" else pts


def merge_twins(roads):
    oneway = [r for r in roads if r.cls in TWIN_CLASSES and r.tags.get("oneway") in ("yes", "-1")]
    by_key = defaultdict(list)
    for r in oneway:
        by_key[(r.tags.get("name", ""), r.cls)].append(r)
    drop, twin_of = set(), {}
    for (name, cls), group in by_key.items():
        limit = TWIN_DIST if name else TWIN_DIST_UNNAMED
        for a in group:
            fa = _forward(a)
            da = (fa[-1][0] - fa[0][0], fa[-1][1] - fa[0][1])
            if da[0] + 0.001 * da[1] >= 0:
                continue  # only westbound / northbound ways are dropped (each pair is looked at from that side)
            best = None
            for b in group:
                if b is a:
                    continue
                fb = _forward(b)
                db = (fb[-1][0] - fb[0][0], fb[-1][1] - fb[0][1])
                if da[0] * db[0] + da[1] * db[1] >= 0:
                    continue  # same direction: not a twin
                samples = [a.line.interpolate(t, normalized=True) for t in (i / 10 for i in range(11))]
                near = sum(1 for s in samples if b.line.distance(s) <= limit) / len(samples)
                if near >= TWIN_SHARE and (best is None or near > best[0]):
                    best = (near, b)
            if best:
                drop.add(id(a))
                twin_of[id(a)] = [b for b in group if id(b) != id(a) and b.line.distance(a.line) <= limit]
    if not drop:
        return roads, 0
    kept = [r for r in roads if id(r) not in drop]
    dropped = [r for r in roads if id(r) in drop]
    used_by_kept = defaultdict(int)
    for r in kept:
        for n in set(r.nodes):
            used_by_kept[n] += 1
    # Every node of a dropped way that another (kept) road uses moves onto the nearest kept twin.
    inserts = defaultdict(list)  # id(kept twin) -> [(distance along, node, point)]
    moved = {}
    for r in dropped:
        twins = [t for t in twin_of[id(r)] if id(t) not in drop]
        if not twins:
            continue
        for n, p in zip(r.nodes, r.line.coords):
            if used_by_kept[n] == 0 or n in moved:
                continue
            if any(n in t.nodes for t in twins):
                continue
            t = min(twins, key=lambda t: t.line.distance(Point(p)))
            along = t.line.project(Point(p))
            q = t.line.interpolate(along)
            moved[n] = (q.x, q.y)
            inserts[id(t)].append((along, n, (q.x, q.y)))
    out = []
    for r in kept:
        pairs = [(n, moved.get(n, p)) for n, p in zip(r.nodes, r.line.coords)]
        if id(r) in inserts:
            cum = [0.0]
            for (_, p), (_, q) in zip(pairs, pairs[1:]):
                cum.append(cum[-1] + math.dist(p, q))
            extra = sorted(inserts[id(r)])
            merged, k = [], 0
            for (n, p), c in zip(pairs, cum):
                while k < len(extra) and extra[k][0] < c:
                    merged.append((extra[k][1], extra[k][2]))
                    k += 1
                merged.append((n, p))
            merged += [(n, p) for _, n, p in extra[k:]]
            pairs = merged
        nr = _rebuild(r, pairs)
        if nr is None:
            continue
        if r.cls in TWIN_CLASSES and r.tags.get("oneway") in ("yes", "-1") and any(
                id(r) in map(id, twin_of.get(id(d), [])) for d in dropped):
            nr.tags.pop("oneway", None)
            nr.center_line = r.cls in osm.CENTER_LINE and nr.width >= 8
        out.append(nr)
    return out, len(dropped)


def merge_clusters(roads):
    import heapq
    pos, adj, ways_at = {}, defaultdict(list), defaultdict(set)
    for w, r in enumerate(roads):
        for n, p in zip(r.nodes, r.line.coords):
            pos[n] = p
            ways_at[n].add(w)
        for a, b in zip(r.nodes, r.nodes[1:]):
            if a != b:
                d = math.dist(pos[a], pos[b])
                adj[a].append((b, d))
                adj[b].append((a, d))
    junction = {n for n, ws in ways_at.items() if len(ws) >= 2 or len({m for m, _ in adj[n]}) >= 3}
    parent = {}

    def find(n):
        while parent.setdefault(n, n) != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n

    for j in junction:
        dist, heap = {j: 0.0}, [(0.0, j)]
        while heap:
            d, n = heapq.heappop(heap)
            if d > dist.get(n, 1e18):
                continue
            if n != j and n in junction:
                parent[find(n)] = find(j)
            for m, w in adj[n]:
                nd = d + w
                if nd <= CLUSTER and nd < dist.get(m, 1e18):
                    dist[m] = nd
                    heapq.heappush(heap, (nd, m))
    groups = defaultdict(list)
    for j in junction:
        groups[find(j)].append(j)
    where, centre = {}, {}
    k = 0
    for root, members in groups.items():
        if len(members) < 2:
            continue
        k += 1
        cid = -(100000 + k)
        centre[cid] = (sum(pos[m][0] for m in members) / len(members), sum(pos[m][1] for m in members) / len(members))
        for m in members:
            where[m] = cid
    if not k:
        return roads, 0
    out = []
    for r in roads:
        seq = [(where.get(n, n), centre[where[n]] if n in where else p) for n, p in zip(r.nodes, r.line.coords)]
        # A road leaving a cluster and coming back to it within the cluster's reach: cut the bit in between.
        i = 0
        while i < len(seq):
            n = seq[i][0]
            if n in centre:
                last = max(j for j in range(i, len(seq)) if seq[j][0] == n)
                if last > i + 1 and sum(math.dist(seq[t][1], seq[t + 1][1]) for t in range(i, last)) <= 2 * CLUSTER:
                    del seq[i + 1:last + 1]
            i += 1
        nr = _rebuild(r, seq)
        if nr is not None and nr.line.length > 0:
            out.append(nr)
    return out, k


def prepare(roads, log=print):
    n0 = len(roads)
    roads = drop_links(roads)
    links = n0 - len(roads)
    roads, rings = collapse_roundabouts(roads)
    roads, twins = merge_twins(roads)
    roads, clusters = merge_clusters(roads)
    log("network: %d slip roads dropped, %d roundabouts made junctions, %d split-carriageway ways merged, "
        "%d junction clusters merged" % (links, rings, twins, clusters))
    return roads
