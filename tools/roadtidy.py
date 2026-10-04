"""Remove the jagged bits from a road plan (the user, 2026-10-05: "I hate these jagged stuff. let's fix those.").

The straightener (roads.py) leaves short runs, up to JOG tiles, where its rules disagree:
- sidesteps: a road going one way, a short run across, then the same way again on a parallel line (Z);
- cut corners: a short run between two runs that turn (a 4-tile straight between a straight and a diagonal);
- short ends: a road that bends just before reaching its junction;
- stubs: dead-end roads of a few tiles.
A run is a stretch of a road going one way; junctions may sit inside it.

Every road is first written out as explicit straight / 45-degree pieces (route()'s bends become nodes). Then:
- shift: the run before the short one moves across by the short run's length (its far end sliding along the piece
  before it), so it arrives where the short run ended; or the run after it, the other way (a sidestep's two sides end
  up on one line; a road that stepped aside into a junction runs straight into it);
- meet: the lines on either side (at a road's end, the crossing road's line) are extended until they meet, the short
  run shrinking to that point (cut corners);
  whichever option moves least wins;
- dead-end roads of at most STUB tiles are dropped.
Moved nodes take other roads' pieces with them only when each such piece stays straight or 45 degrees and turns by at
most 45 degrees (moves that just lengthen a piece are preferred); any short run that leaves is fixed in a later round.
Hairpins (a short run between runs going opposite ways: loop roads) are left alone. Repeats until nothing changes.

Finally, roads of one class that carry straight on into each other at a junction (M. T. Villanueva Avenue into
Penafrancia Avenue) take the widest width and sidewalk among them: a width step a few squares past a junction looked
jagged."""
from collections import defaultdict
from fractions import Fraction

JOG = 16
STUB = 16
TURN_COST = 8  # cost of turning another road's piece, in tiles moved


def _dir(p, q):
    return ((q[0] > p[0]) - (q[0] < p[0]), (q[1] > p[1]) - (q[1] < p[1]))


def _len(p, q):
    return max(abs(q[0] - p[0]), abs(q[1] - p[1]))


def _octilinear(p, q):
    dx, dy = q[0] - p[0], q[1] - p[1]
    return (dx or dy) and (dx == 0 or dy == 0 or abs(dx) == abs(dy))


def _meet(p, d, q, e):
    """Integer intersection of the lines p + t d and q + s e, or None (parallel, or not on a square)."""
    den = d[0] * e[1] - d[1] * e[0]
    if den == 0:
        return None
    t = Fraction((q[0] - p[0]) * e[1] - (q[1] - p[1]) * e[0], den)
    x, y = p[0] + t * d[0], p[1] + t * d[1]
    if x.denominator != 1 or y.denominator != 1:
        return None
    return int(x), int(y)


class _Net:
    def __init__(self, plan, route):
        self.pos = {k: tuple(v) for k, v in plan["nodes"].items()}
        self.next_bend = 1 + max([int(k[1:]) for k in self.pos if k[:1] == "b" and k[1:].isdigit()] or [0])
        self.roads = []
        for r in plan["roads"]:
            pts = [r["points"][0]]
            for a, b in zip(r["points"], r["points"][1:]):
                for p, q in route(self.pos[a], self.pos[b])[:-1]:
                    pts.append(self._bend(q))
                pts.append(b)
            self.roads.append(self._dedupe(pts))
        self.dead = set()
        self.at = defaultdict(set)
        for i, r in enumerate(self.roads):
            for n in r:
                self.at[n].add(i)

    def _bend(self, pt):
        nid = "b%d" % self.next_bend
        self.next_bend += 1
        self.pos[nid] = pt
        return nid

    @staticmethod
    def _dedupe(pts):
        out = []
        for n in pts:
            if not out or out[-1] != n:
                out.append(n)
        return out

    def straighten(self, i):
        """Drop vertices in the middle of a straight run that nothing else needs."""
        r = self.roads[i]
        k = 1
        while k < len(r) - 1:
            a, b, c = self.pos[r[k - 1]], self.pos[r[k]], self.pos[r[k + 1]]
            if a != b and b != c and _dir(a, b) == _dir(b, c) and len(self.at[r[k]]) == 1 and r.count(r[k]) == 1:
                self.at[r[k]].discard(i)
                del r[k]
            else:
                k += 1

    def runs(self, i):
        """[(first vertex index, last vertex index)] of road i's straight runs."""
        r, out, a = self.roads[i], [], 0
        for k in range(1, len(r)):
            if k == len(r) - 1 or _dir(self.pos[r[k - 1]], self.pos[r[k]]) != _dir(self.pos[r[k]], self.pos[r[k + 1]]):
                out.append((a, k))
                a = k
        return out

    def pieces_at(self, n):
        """(road, index of the piece's first vertex, other end) for every piece touching node n."""
        out = []
        for i in self.at[n]:
            r = self.roads[i]
            for k, m in enumerate(r):
                if m == n:
                    if k > 0:
                        out.append((i, k - 1, r[k - 1]))
                    if k < len(r) - 1:
                        out.append((i, k, r[k + 1]))
        return out

    def cost(self, moves, exempt):
        """Cost of moving nodes (moves: id -> new point), or None if a piece outside `exempt` ((road, k) pairs)
        would stop being straight / 45 degrees, vanish, or turn by more than 45 degrees."""
        total = sum(_len(self.pos[n], p) for n, p in moves.items())
        for n in moves:
            for i, k, other in self.pieces_at(n):
                if (i, k) in exempt:
                    continue
                a, b = self.pos[n], self.pos[other]
                na, nb = moves.get(n, a), moves.get(other, b)
                if not _octilinear(na, nb):
                    return None
                old, new = _dir(a, b), _dir(na, nb)
                if old[0] * new[0] + old[1] * new[1] <= 0:
                    return None
                if old != new:
                    total += TURN_COST
        return total

    def apply_moves_only(self, moves):
        for n, p in moves.items():
            self.pos[n] = p

    def apply(self, moves):
        touched = set(range(len(self.roads))) if not moves else set()
        for n, p in moves.items():
            self.pos[n] = p
            touched |= self.at[n]
        for i in touched:  # nodes that now coincide along a road become one node
            r = self.roads[i]
            k = 0
            while k < len(r) - 1:
                if r[k] != r[k + 1] and self.pos[r[k]] == self.pos[r[k + 1]]:
                    self.merge(r[k + 1], r[k])
                    r = self.roads[i]
                else:
                    k += 1
        for i in touched:
            self.straighten(i)

    def merge(self, a, b):
        """Node a becomes node b everywhere."""
        for i in list(self.at[a]):
            self.roads[i] = self._dedupe([b if n == a else n for n in self.roads[i]])
            self.at[b].add(i)
        self.at.pop(a, None)


def _shift(net, i, runs, j):
    """Short run j of road i disappears by shifting a neighbouring run across: options (cost, moves)."""
    r, pos = net.roads[i], net.pos
    a, b = runs[j]
    v = (pos[r[b]][0] - pos[r[a]][0], pos[r[b]][1] - pos[r[a]][1])
    out = []
    # Side 0: the run before shifts by v so it ends where the short run ended; side 1: the run after shifts by -v so
    # it starts where the short run started. The shifted run's far end slides along the piece beyond it.
    for side in (0, 1):
        if side == 0 and j == 0 or side == 1 and j + 1 >= len(runs):
            continue
        nb = runs[j - 1] if side == 0 else runs[j + 1]
        d = _dir(pos[r[nb[0]]], pos[r[nb[1]]])
        if d in (_dir(pos[r[a]], pos[r[b]]), _dir(pos[r[b]], pos[r[a]])):
            continue
        if side == 0:
            s0, s1 = runs[j - 1]
            end, step = s0, v
            onto, anchor = pos[r[b]], s0 - 1
            shifted = range(s0 + 1, b)
            exempt = {(i, k) for k in range(s0, b)}
        else:
            s0, s1 = runs[j + 1]
            end, step = s1, (-v[0], -v[1])
            onto, anchor = pos[r[a]], s1 + 1
            shifted = range(a + 1, s1)
            exempt = {(i, k) for k in range(a, s1)}
        e = pos[r[end]]
        if 0 <= anchor < len(r):  # the run's far end slides along the piece beyond it onto the kept line
            to = _meet(pos[r[anchor]], _dir(pos[r[anchor]], e), onto, d)
        else:
            to = (e[0] + step[0], e[1] + step[1])
        if to is None:
            continue
        moves = {r[end]: to}
        for k in shifted:
            n = r[k]
            if a <= k <= b:
                moves[n] = pos[r[b]] if side == 0 else pos[r[a]]
            else:
                moves[n] = (pos[n][0] + step[0], pos[n][1] + step[1])
        if side == 0 and _dir(to, pos[r[b]]) != d or side == 1 and _dir(pos[r[a]], to) != d:
            continue
        c = net.cost(moves, exempt)
        if c is not None:
            out.append((c, moves))
    return out


def _corner(net, i, runs, j):
    """Run j of road i is short and turns (or ends the road): the lines on either side meet. Options."""
    r, pos = net.roads[i], net.pos
    a, b = runs[j]
    s = _dir(pos[r[a]], pos[r[b]])
    exempt = {(i, k) for k in range(a, b)}

    def lines(k):
        """{direction: [(road, piece index, far end)]} of the pieces at vertex k outside the run."""
        out = defaultdict(list)
        for jj, kk, o in net.pieces_at(r[k]):
            if (jj, kk) not in exempt:
                out[_dir(pos[r[k]], pos[o])].append((jj, kk, o))
        return out

    def between(p, x, q):
        return x != p and _dir(p, x) == _dir(p, q) and _len(p, x) < _len(p, q)

    out = []
    at_p, at_q = lines(a), lines(b)
    for dp, p_pieces in at_p.items():
        for dq, q_pieces in at_q.items():
            if dp in (s, (-s[0], -s[1])) or dq in (s, (-s[0], -s[1])):
                continue
            X = _meet(pos[r[a]], dp, pos[r[b]], dq)
            if X is None:
                continue
            moves = {r[k]: X for k in range(a, b + 1)}
            c = net.cost(moves, exempt)
            if c is not None:
                out.append((c, moves))
            # The road ends here: it may leave the junction and join the crossing road where the lines meet.
            for end, pieces_there, keep in ((b, q_pieces, range(a, b)), (a, p_pieces, range(a + 1, b + 1))):
                if end != (len(r) - 1 if end == b else 0):
                    continue
                for jj, kk, o in pieces_there:
                    if jj == i or not between(pos[r[end]], X, pos[o]):
                        continue
                    moves = {r[k]: X for k in keep}
                    c = net.cost(moves, exempt)
                    if c is not None:
                        out.append((c + 1, ("attach", i, end, moves, jj, r[end], o)))
    return out


def _attach(net, i, end, moves, jj, junction, other):
    """Road i lets go of `junction` (its end vertex `end`) and joins road jj between junction and other, at the point
    its run was moved to."""
    net.apply_moves_only(moves)
    r = net.roads[i]
    node = r[end - 1] if end == len(r) - 1 else r[end + 1]
    del r[end]
    net.at[junction].discard(i)
    rj = net.roads[jj]
    for k in range(len(rj) - 1):
        if {rj[k], rj[k + 1]} == {junction, other}:
            rj.insert(k + 1, node)
            break
    net.at[node].add(jj)
    net.apply({})
    for x in (i, jj):
        net.straighten(x)


def tidy(plan, route, log=print):
    """Rewrites plan["nodes"] and plan["roads"] in place."""
    net = _Net(plan, route)
    for i in range(len(net.roads)):
        net.straighten(i)
    counts = defaultdict(int)
    for _ in range(30):
        changed = 0
        for i in range(len(net.roads)):
            j = 0
            while True:
                r = net.roads[i]
                runs = net.runs(i) if len(r) >= 2 else []
                if j >= len(runs):
                    break
                a, b = runs[j]
                if _len(net.pos[r[a]], net.pos[r[b]]) > JOG:
                    j += 1
                    continue
                before = _dir(net.pos[r[runs[j - 1][0]]], net.pos[r[a]]) if j > 0 else None
                after = _dir(net.pos[r[b]], net.pos[r[runs[j + 1][1]]]) if j + 1 < len(runs) else None
                if before and after and before == (-after[0], -after[1]):
                    j += 1  # hairpin
                    continue
                if before and before == after:
                    kind, options = "sidesteps", _shift(net, i, runs, j)
                else:
                    kind, options = "corners and short ends", _corner(net, i, runs, j) + _shift(net, i, runs, j)
                if options:
                    act = min(options, key=lambda o: o[0])[1]
                    if isinstance(act, tuple):
                        _attach(net, *act[1:])
                    else:
                        net.apply(act)
                    counts[kind] += 1
                    changed += 1
                    j = 0
                else:
                    j += 1
        if not changed:
            break
    for i, r in enumerate(net.roads):  # dead-end stubs
        if len(r) < 2:
            continue
        length = sum(_len(net.pos[a], net.pos[b]) for a, b in zip(r, r[1:]))
        if length <= STUB and (len(net.at[r[0]]) == 1 or len(net.at[r[-1]]) == 1):
            net.dead.add(i)
            counts["stubs"] += 1
    roads = []
    for i, d in enumerate(plan["roads"]):
        if i in net.dead or len(net.roads[i]) < 2:
            continue
        d = dict(d)
        d["points"] = net.roads[i]
        roads.append(d)
    used = {n for d in roads for n in d["points"]} | {plan["connector_end"]}
    plan["roads"] = roads
    plan["nodes"] = {n: list(net.pos[n]) for n in used}
    counts["roads widened to match the road they continue"] = harmonize_widths(plan)
    log("tidy: " + ", ".join("%d %s" % (v, k) for k, v in sorted(counts.items())))
    return plan


def harmonize_widths(plan):
    """Same-class roads continuing straight through a junction share the widest width / sidewalk. Returns how many
    roads changed."""
    pos = {k: tuple(v) for k, v in plan["nodes"].items()}
    roads = plan["roads"]
    arms = defaultdict(list)  # node -> [(road index, direction away from the node)]
    for i, r in enumerate(roads):
        pts = r["points"]
        for k, n in enumerate(pts):
            for m in ((pts[k - 1],) if k > 0 else ()) + ((pts[k + 1],) if k + 1 < len(pts) else ()):
                if pos[m] != pos[n]:
                    arms[n].append((i, _dir(pos[n], pos[m])))
    parent = list(range(len(roads)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for n, here in arms.items():
        for x, (i, d) in enumerate(here):
            for j, e in here[x + 1:]:
                if i != j and e == (-d[0], -d[1]) and roads[i]["class"] == roads[j]["class"]:
                    parent[find(j)] = find(i)
    groups = defaultdict(list)
    for i in range(len(roads)):
        groups[find(i)].append(i)
    changed = 0
    for members in groups.values():
        if len(members) < 2:
            continue
        width = max(roads[i]["width"] for i in members)
        side = max(roads[i].get("sidewalk", 0) for i in members)
        for i in members:
            if roads[i]["width"] != width or roads[i].get("sidewalk", 0) != side:
                roads[i]["width"], roads[i]["sidewalk"] = width, side
                changed += 1
    return changed
