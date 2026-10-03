"""OSM road network -> Zomboid-style roads (see CLAUDE.md "Roads").

Highways (trunk, primary, secondary) first, as long straight legs: place accuracy, not curvature (the user,
2026-10-03: "treat highways as completely straight; the zomboid map just needs to follow place accuracy but not
highway curvatures").
1. Highway ways of the same name, class and width are stitched into routes.
2. Each route is simplified with HW_SIMPLIFY (Douglas-Peucker), keeping its ends and every node it shares with another
   highway route (so crossings stay crossings).
3. A leg within HW_AXIS_DEG of an axis is made exactly east-west / north-south: its two ends share a coordinate
   (weighted mean, no cap); any other leg keeps both ends and is drawn straight / 45 degrees / straight.
4. Every other node on a route (a side street's junction) is pinned onto the straightened route at the same fraction
   of the leg's length.

Then the other roads, around the pinned junctions:
5. Split at junctions and ends, simplified (Douglas-Peucker, 6 m).
6. Segments within AXIS_DEG of an axis share x or y with their neighbours (union-find, longest and most important
   first, a group's original spread capped at CAP); a group holding a pinned node takes the pinned coordinate.
   Segments still off by at most SNAP are merged anyway, coordinates are snapped to GRID.
7. Anything still off both axes is straight / 45 degrees / straight; a diagonal shorter than MIN_DIAG, or with a
   45-degree part shorter than MIN_DIAG_PART, is a square corner (short diagonals and small offsets made "horrible
   formations", the user's second look).

The result is a list of Piece: straight (H / V) or 45-degree (D) centre lines in integer tile coordinates."""
import math
from collections import Counter, defaultdict

HIGHWAY_RANK = 5
HW_SIMPLIFY = 40
HW_AXIS_DEG = 15
AXIS_DEG = 35
CAP = 20
SNAP = 16
GRID = 4
MIN_DIAG = 40
MIN_DIAG_PART = 8
PIN_WEIGHT = 1e12
RANK = {"trunk": 7, "primary": 6, "secondary": 5, "tertiary": 4, "residential": 3, "unclassified": 3,
        "living_street": 3, "road": 3, "service": 2, "track": 1, "pedestrian": 1}
SIMPLIFY = {4: 8}  # Douglas-Peucker tolerance by rank for the other roads, default 6


class Piece:
    __slots__ = ("x0", "y0", "x1", "y1", "road", "a", "b")

    def __init__(self, a, b, road):
        (self.x0, self.x1), (self.y0, self.y1) = sorted((a[0], b[0])), sorted((a[1], b[1]))
        self.road, self.a, self.b = road, a, b

    @property
    def horizontal(self):
        return self.y0 == self.y1 and self.x0 != self.x1

    @property
    def diagonal(self):
        return self.x0 != self.x1 and self.y0 != self.y1

    @property
    def falling(self):
        """Diagonal running north-west to south-east (x and y grow together): its edges are lines x - y = const."""
        return (self.b[0] - self.a[0]) * (self.b[1] - self.a[1]) > 0

    def rect(self, half):
        """Squares covered by a straight piece at half-width `half`: x in [x0, x1), y in [y0, y1). Square caps, so
        pieces meeting at a corner overlap cleanly."""
        return self.x0 - half, self.y0 - half, self.x1 + half, self.y1 + half


def _douglas_peucker(ids, pos, tol):
    if len(ids) <= 2:
        return list(ids)
    (ax, ay), (bx, by) = pos[ids[0]], pos[ids[-1]]
    dx, dy = bx - ax, by - ay
    length = math.hypot(dx, dy)
    best, index = -1.0, 0
    for i in range(1, len(ids) - 1):
        px, py = pos[ids[i]]
        d = abs(dy * (px - ax) - dx * (py - ay)) / length if length > 0 else math.hypot(px - ax, py - ay)
        if d > best:
            best, index = d, i
    if best <= tol:
        return [ids[0], ids[-1]]
    left = _douglas_peucker(ids[:index + 1], pos, tol)
    return left[:-1] + _douglas_peucker(ids[index:], pos, tol)


def _simplify_keeping(ids, pos, tol, forced):
    """Douglas-Peucker, but every node in `forced` is kept (the route is split there first)."""
    out, start = [ids[0]], 0
    for i in range(1, len(ids)):
        if ids[i] in forced or i == len(ids) - 1:
            out += _douglas_peucker(ids[start:i + 1], pos, tol)[1:]
            start = i
    return out


class _Groups:
    """Union-find over node ids for one coordinate, with a cap on the spread of the original coordinates."""

    def __init__(self, coord):
        self.coord = coord
        self.parent, self.lo, self.hi = {}, {}, {}

    def _add(self, n):
        if n not in self.parent:
            c = self.coord[n]
            self.parent[n], self.lo[n], self.hi[n] = n, c, c

    def find(self, n):
        self._add(n)
        root = n
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[n] != root:
            self.parent[n], n = root, self.parent[n]
        return root

    def union(self, a, b, cap):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return True
        lo, hi = min(self.lo[ra], self.lo[rb]), max(self.hi[ra], self.hi[rb])
        if hi - lo > cap:
            return False
        self.parent[rb] = ra
        self.lo[ra], self.hi[ra] = lo, hi
        return True


def _resolve(groups, coord, weights, snap=True):
    """Each node takes its group's weighted mean; groups holding a pinned node keep its exact value (no snapping)."""
    total, wsum = defaultdict(float), defaultdict(float)
    for n in coord:
        if weights[n] > 0:
            r = groups.find(n)
            total[r] += coord[n] * weights[n]
            wsum[r] += weights[n]
    out = {}
    for n in coord:
        r = groups.find(n) if n in groups.parent else None
        v = total[r] / wsum[r] if r is not None and wsum[r] > 0 else coord[n]
        pinned = r is not None and wsum[r] >= PIN_WEIGHT
        out[n] = int(round(v)) if pinned or not snap else int(round(v / GRID)) * GRID
    return out


def _kind(a, b, axis_deg):
    dx, dy = b[0] - a[0], b[1] - a[1]
    tan = math.tan(math.radians(axis_deg))
    return "H" if abs(dy) <= abs(dx) * tan else "V" if abs(dx) <= abs(dy) * tan else "D"


def _stitch(roads, indices):
    """Highway ways -> routes: ways of the same name, class and width joined end to end. [(node ids, road index)]"""
    def key(i):
        r = roads[i]
        return (r.tags.get("name") or r.tags.get("ref") or "#%d" % r.osm_id, r.cls, r.width)

    groups = defaultdict(list)
    for i in indices:
        groups[key(i)].append(i)
    routes = []
    for members in groups.values():
        ends = defaultdict(list)
        for i in members:
            ends[roads[i].nodes[0]].append(i)
            ends[roads[i].nodes[-1]].append(i)
        used = set()
        for i in members:
            if i in used:
                continue
            used.add(i)
            chain = list(roads[i].nodes)
            for forward in (True, False):
                while True:
                    tip = chain[-1] if forward else chain[0]
                    nxt = [j for j in ends[tip] if j not in used] if len(ends[tip]) == 2 else []
                    if not nxt or chain[0] == chain[-1]:
                        break
                    j = nxt[0]
                    used.add(j)
                    seq = list(roads[j].nodes)
                    if forward:
                        chain += (seq if seq[0] == tip else seq[::-1])[1:]
                    else:
                        chain = (seq if seq[-1] == tip else seq[::-1])[:-1] + chain
            routes.append((chain, i))
    return routes


def _point_along(path, frac):
    """The integer point at `frac` of the length of a polyline of straight / 45-degree pieces, on its centre line."""
    lengths = [max(abs(q[0] - p[0]), abs(q[1] - p[1])) for p, q in path]  # steps along the piece
    total = sum(lengths)
    if total == 0:
        return path[0][0]
    target = round(frac * total)
    for (p, q), n in zip(path, lengths):
        if target <= n:
            sx = (q[0] > p[0]) - (q[0] < p[0])
            sy = (q[1] > p[1]) - (q[1] < p[1])
            return p[0] + sx * target, p[1] + sy * target
        target -= n
    return path[-1][1]


def schematize(roads):
    """roads: osm.Road list (line roads with node ids). Returns (pieces, final node positions {id: (x, y)})."""
    pos, use = {}, Counter()
    for r in roads:
        for n, p in zip(r.nodes, r.line.coords):
            pos[n] = p
        use.update(set(r.nodes))
    xs = {n: p[0] for n, p in pos.items()}
    ys = {n: p[1] for n, p in pos.items()}

    # Highways.
    hw = [i for i, r in enumerate(roads) if RANK.get(r.cls, 3) >= HIGHWAY_RANK]
    routes = _stitch(roads, hw)
    on_routes = Counter(n for chain, _ in routes for n in set(chain))
    forced = {n for n, c in on_routes.items() if c >= 2}
    legs = []  # (a, b, road index, route nodes from a to b)
    for chain, i in routes:
        chain = [n for k, n in enumerate(chain) if k == 0 or n != chain[k - 1]]
        if len(chain) < 2:
            continue
        kept = _simplify_keeping(chain, pos, HW_SIMPLIFY, forced)
        at = 0
        for a, b in zip(kept, kept[1:]):
            start = chain.index(a, at)
            end = chain.index(b, start + 1) if b in chain[start + 1:] else start
            legs.append((a, b, i, chain[start:end + 1]))
            at = end
    hx, hy = _Groups(xs), _Groups(ys)
    hwx, hwy = defaultdict(float), defaultdict(float)
    leg_kind = []
    for a, b, i, _ in legs:
        k = _kind(pos[a], pos[b], HW_AXIS_DEG)
        leg_kind.append(k)
        w = math.dist(pos[a], pos[b]) * roads[i].width
        if k == "H":
            hy.union(a, b, float("inf"))
            hwy[a] += w
            hwy[b] += w
        elif k == "V":
            hx.union(a, b, float("inf"))
            hwx[a] += w
            hwx[b] += w
    fx, fy = _resolve(hx, xs, hwx), _resolve(hy, ys, hwy)
    pinned, pieces = {}, []
    for (a, b, i, nodes), k in zip(legs, leg_kind):
        A, B = (fx[a], fy[a]), (fx[b], fy[b])
        pinned[a], pinned[b] = A, B
        path = [(p, q) for p, q in _path(A, B, k) if p != q]
        pieces += [Piece(p, q, i) for p, q in path]
        if len(nodes) > 2 and path:
            cum = [0.0]
            for p, q in zip(nodes, nodes[1:]):
                cum.append(cum[-1] + math.dist(pos[p], pos[q]))
            for n, c in zip(nodes[1:-1], cum[1:-1]):
                if use[n] >= 2 and n not in pinned:
                    pinned[n] = _point_along(path, c / cum[-1] if cum[-1] else 0)

    # The other roads, around the pinned junctions.
    others = [i for i, r in enumerate(roads) if RANK.get(r.cls, 3) < HIGHWAY_RANK]
    key = {n for n, c in use.items() if c >= 2} | set(pinned)
    for i in others:
        key.update((roads[i].nodes[0], roads[i].nodes[-1]))
    segments = []
    for i in others:
        r = roads[i]
        tol = SIMPLIFY.get(RANK.get(r.cls, 3), 6)
        chain = [r.nodes[0]]
        for n in r.nodes[1:]:
            if n == chain[-1]:
                continue
            chain.append(n)
            if n in key:
                kept = _douglas_peucker(chain, pos, tol)
                segments += [(a, b, i) for a, b in zip(kept, kept[1:]) if a != b]
                chain = [n]
    kind = [_kind(pos[a], pos[b], AXIS_DEG) for a, b, _ in segments]
    px, py = dict(xs), dict(ys)
    wx, wy = defaultdict(float), defaultdict(float)
    for n, (x, y) in pinned.items():
        px[n], py[n] = x, y
        wx[n] += PIN_WEIGHT
        wy[n] += PIN_WEIGHT
    gx, gy = _Groups(px), _Groups(py)
    order = sorted(range(len(segments)), key=lambda s: (-RANK.get(roads[segments[s][2]].cls, 3),
                                                        -math.dist(pos[segments[s][0]], pos[segments[s][1]])))
    for s in order:
        a, b, i = segments[s]
        weight = math.dist(pos[a], pos[b]) * roads[i].width
        if kind[s] == "H" and gy.union(a, b, CAP):
            wy[a] += weight
            wy[b] += weight
        elif kind[s] == "V" and gx.union(a, b, CAP):
            wx[a] += weight
            wx[b] += weight
    fx, fy = _resolve(gx, px, wx), _resolve(gy, py, wy)
    for _ in range(4):
        merged = 0
        for s in order:
            a, b, i = segments[s]
            weight = math.dist(pos[a], pos[b]) * roads[i].width
            if kind[s] == "H" and 0 < abs(fy[a] - fy[b]) <= SNAP and gy.find(a) != gy.find(b):
                gy.union(a, b, float("inf"))
                wy[a] += weight
                wy[b] += weight
                merged += 1
            elif kind[s] == "V" and 0 < abs(fx[a] - fx[b]) <= SNAP and gx.find(a) != gx.find(b):
                gx.union(a, b, float("inf"))
                wx[a] += weight
                wx[b] += weight
                merged += 1
        if not merged:
            break
        fx, fy = _resolve(gx, px, wx), _resolve(gy, py, wy)
    final = {n: (fx[n], fy[n]) for n in pos}
    final.update(pinned)
    for s, (a, b, i) in enumerate(segments):
        pieces += [Piece(p, q, i) for p, q in _path(final[a], final[b], kind[s]) if p != q]
    return pieces, final


def _path(a, b, k):
    """Straight when the ends share x or y, else straight / 45 degrees / straight (the straight part split in two), or
    a square corner when the diagonal would be short."""
    (ax, ay), (bx, by) = a, b
    dx, dy = bx - ax, by - ay
    if dx == 0 or dy == 0:
        return [(a, b)]
    sx, sy = (1 if dx > 0 else -1), (1 if dy > 0 else -1)
    d = min(abs(dx), abs(dy))
    if math.hypot(dx, dy) < MIN_DIAG or d < MIN_DIAG_PART:
        corner = (bx, ay) if abs(dx) >= abs(dy) else (ax, by)
        return [(a, corner), (corner, b)]
    rest = max(abs(dx), abs(dy)) - d
    first = rest // 2 // GRID * GRID
    p1 = (ax + sx * first, ay) if abs(dx) >= abs(dy) else (ax, ay + sy * first)
    p2 = (p1[0] + sx * d, p1[1] + sy * d)
    return [(a, p1), (p1, p2), (p2, b)]
