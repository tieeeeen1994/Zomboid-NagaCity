"""Buildings sized to vanilla rooms, so every room is a whole vanilla interior (the user, 2026-10-04: interiors must
look full and real, accuracy only outside, and "we can also resize the exterior so that the interior can match").

A corridor building is one or more strips across its depth, each [room band | corridor 3 | room band], plus a 6-wide
stairwell / lobby across the strips at its west (or north) end. Every room band is filled with vanilla rooms whose
depth is exactly the band's (data/vanilla_rooms.json), side by side; the bands of a strip have the same length,
found by a reachable-sums search over the rooms' widths, as close as possible to the real building. Halls (church,
gym) are the best-fitting vanilla hall plus a band of side rooms; small buildings are one vanilla room.

Stamps keep their orientation (sprites face a way), so a stamp's width runs along a horizontal band and its height
along a vertical one. Rooms bring their own floor and interior wall set from the vanilla room."""
import random

import rooms as vanilla
import templates as T
from buildkit import Building, RoomType, WallSet

CORRIDOR = 3
STAIRWELL = 6
HALL = RoomType("hall", T.FLOOR_HALL, T.INTERIOR)
HALL.detail = False

# Room mixes by building kind: band types cycle through these.
MIX = {
    "school": ["classroom", "classroom", "office", "classroom", "classroom", "storage", "classroom", "bathroom",
               "classroom", "janitor", "classroom", "breakroom", "classroom", "medical"],
    "offices": ["office", "office", "breakroom", "office", "bathroom", "office", "storage", "office", "janitor",
                "universityoffice"],
    "library": ["library", "universitylibrary", "office", "library", "storage", "library", "bathroom"],
    "house": ["bedroom", "livingroom", "bathroom", "bedroom", "kitchen", "bedroom", "storage"],
    "daycare": ["daycare", "classroom", "bathroom", "storage"],
    "storage": ["storage", "janitor", "storage", "office"],
    "security": ["security"],
}
HALLS = {"church": ["office", "storage", "bathroom", "janitor"], "gym": ["lockerroom", "storage", "bathroom", "office"]}
MIN_AREA = {"classroom": 30, "library": 24, "universitylibrary": 24, "church": 120, "gym": 120, "daycare": 20}


def _pool(types, across, horizontal):
    """(name, stamp) of the given types whose size across the band is exactly `across`."""
    out = []
    lib = vanilla.library()
    for name in dict.fromkeys(types):
        for st in lib.get(name, []):
            a, b = (st["h"], st["w"]) if horizontal else (st["w"], st["h"])
            if a == across and b >= 3 and len(st["items"]) >= 2 and st["w"] * st["h"] >= MIN_AREA.get(name, 0):
                out.append((name, st))
    return out


def _along(st, horizontal):
    return st["w"] if horizontal else st["h"]


def _reachable(widths, limit):
    ok = [False] * (limit + 1)
    ok[0] = True
    for n in range(1, limit + 1):
        ok[n] = any(w <= n and ok[n - w] for w in widths)
    return ok


def _sequence(widths, ok, total, rng, preferred=()):
    """Widths summing to total; widths in `preferred` (where the building's main room type exists) first."""
    seq, n = [], total
    while n > 0:
        opts = [w for w in widths if w <= n and ok[n - w]]
        main = [w for w in opts if w in preferred]
        w = rng.choice(sorted(main or opts)[-3:])  # prefer bigger rooms, some variety
        seq.append(w)
        n -= w
    rng.shuffle(seq)
    return seq


def _roomtype(name, stamp):
    rt = RoomType(name, stamp.get("floor") or T.FLOOR_ROOM, T.INTERIOR)
    walls = stamp.get("walls")
    if walls:
        rt.walls = WallSet(walls[0], walls[1] // 16, (walls[1] % 16) // 4)
    rt.detail = False
    return rt


class Layout:
    """Rooms in local coordinates, then written onto a buildkit.Building."""

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.cells = {}            # (x, y) -> key
        self.legend = {}
        self.doors = []            # (x, y, side)
        self.furniture = []        # (x, y, tiles)
        self.stairs = []           # (z, x, y_top)
        self._n = 0

    def room(self, rt, x0, y0, x1, y1, stamp=None):
        key = T.KEYS[self._n % len(T.KEYS)]
        self._n += 1
        self.legend[key] = rt
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                self.cells[(x, y)] = key
        if stamp:
            self.furniture += [(x0 + dx, y0 + dy, t) for dx, dy, t in stamp["items"]]
        return key

    def building(self, name, ox, oy, exterior, levels, entries):
        b = Building(name, ox, oy, exterior)
        rows = ["".join(self.cells.get((x, y), ".") for x in range(self.w)) for y in range(self.h)]
        clear = set()
        for x, y, side in self.doors + entries:
            clear |= {(x, y), (x, y - 1)} if side == "N" else {(x, y), (x - 1, y)}
        for _, sx, sy in self.stairs:
            clear |= {(sx + dx, sy + dy) for dx in (0, 1) for dy in (-1, 0, 1, 2, 3)}
        for z in range(levels):
            b.floor(z, rows, self.legend)
            for x, y, side in self.doors:
                b.doors.add((z, x, y, side))
            for x, y, tiles in self.furniture:
                if (x, y) not in clear:
                    b.furniture.append((z, x, y, tiles))
                    b.furnished.add((z, x, y))
        for x, y, side in entries:
            b.doors.add((0, x, y, side))
        b.stairs = [s for s in self.stairs if s[0] < levels - 1]
        return b


def corridor_building(kind, length, depth, horizontal, levels, seed):
    """Returns (Layout, entries) or None when vanilla has no rooms that fit."""
    rng = random.Random(seed)
    types = MIX.get(kind, MIX["offices"])
    best = None
    for ra in range(4, 13):
        pa = _pool(types, ra, horizontal)
        primary_a = sum(1 for p in pa if p[0] == types[0])
        if len(pa) < 2 or not primary_a:
            continue
        for rb in [0] + list(range(3, 13)):
            pb = _pool(types, rb, horizontal) if rb else []
            if rb and len(pb) < 2:
                continue
            strip = ra + CORRIDOR + rb
            for n in range(1, 5):
                total = n * strip
                score = abs(total - depth) + (0 if rb else 1.5) + 0.3 * n - min(primary_a, 6) * 0.4
                if best is None or score < best[0]:
                    best = (score, ra, rb, n, pa, pb)
    if best is None:
        return None
    _, ra, rb, n, pa, pb = best
    target = max(8, length - STAIRWELL)
    limit = int(target * 1.4) + 12
    wa = sorted({_along(st, horizontal) for _, st in pa})
    wb = sorted({_along(st, horizontal) for _, st in pb})
    oka = _reachable(wa, limit)
    okb = _reachable(wb, limit) if rb else [True] * (limit + 1)
    common = [L for L in range(6, limit + 1) if oka[L] and okb[L]]
    if not common:
        return None
    run = min(common, key=lambda L: (abs(L - target), -L))
    strip = ra + CORRIDOR + rb
    across, along = n * strip, STAIRWELL + run
    w, h = (along, across) if horizontal else (across, along)
    lay = Layout(w, h)

    def rect(a0, c0, a1, c1):
        """along / across -> x, y"""
        return (a0, c0, a1, c1) if horizontal else (c0, a0, c1, a1)

    for s in range(n):
        c = s * strip
        # stairwell / lobby across the whole strip at the start
        sx0, sy0, sx1, sy1 = rect(0, c, STAIRWELL - 1, c + strip - 1)
        lay.room(HALL, sx0, sy0, sx1, sy1)
        if levels > 1 and strip >= 5:
            for z in range(levels - 1):
                off = 1 if z % 2 == 0 else 3
                lay.stairs.append((z, sx0 + off, sy0 + 1) if horizontal else (z, sx0 + off, sy0 + 1))
        # corridor
        cx0, cy0, cx1, cy1 = rect(STAIRWELL, c + ra, along - 1, c + ra + CORRIDOR - 1)
        lay.room(HALL, cx0, cy0, cx1, cy1)
        lay.doors.append((STAIRWELL, c + ra + 1, "W") if horizontal else (c + ra + 1, STAIRWELL, "N"))
        for band, depth_b, pool, ok, ws, c0 in ((0, ra, pa, oka, wa, c), (1, rb, pb, okb, wb, c + ra + CORRIDOR)):
            if not depth_b:
                continue
            pos = STAIRWELL
            primary_widths = {_along(st, horizontal) for nm, st in pool if nm == types[0]}
            for i, wd in enumerate(_sequence(ws, ok, run, rng, primary_widths)):
                want = types[0] if band == 0 and i % 3 != 2 else types[(seed + s * 7 + band * 3 + i) % len(types)]
                choices = [p for p in pool if _along(p[1], horizontal) == wd]
                pref = [p for p in choices if p[0] == want] or choices
                name, st = rng.choice(pref)
                x0, y0, x1, y1 = rect(pos, c0, pos + wd - 1, c0 + depth_b - 1)
                lay.room(_roomtype(name, st), x0, y0, x1, y1, st)
                mid = pos + wd // 2
                if band == 0:
                    lay.doors.append((mid, c0 + depth_b, "N") if horizontal else (c0 + depth_b, mid, "W"))
                else:
                    lay.doors.append((mid, c0, "N") if horizontal else (c0, mid, "W"))
                pos += wd
    first = ra + 1
    entries = ([(0, first, "W"), (along, first, "W")] if horizontal else [(first, 0, "N"), (first, along, "N")])
    return lay, entries


def hall_building(kind, length, depth, horizontal, seed):
    """The best-fitting vanilla hall, plus a band of side rooms along its long side when the real building is
    deeper. Returns (Layout, entries) or None."""
    rng = random.Random(seed)
    lib = vanilla.library()
    halls = [st for st in lib.get(kind, []) if st["w"] * st["h"] >= MIN_AREA.get(kind, 0) and len(st["items"]) >= 4]
    if not halls:
        return None
    W, H = (length, depth) if horizontal else (depth, length)

    def score(st):
        return abs(st["w"] - W) + abs(st["h"] - H) + (8 if st["w"] > W * 1.2 or st["h"] > H * 1.2 else 0)

    main = min(halls, key=score)
    mw, mh = main["w"], main["h"]
    lay_h = mh
    side = None
    if H - mh >= 4:
        types = HALLS.get(kind, ["storage", "office"])
        for d in range(min(12, H - mh), 2, -1):
            pool = _pool(types, d, True)
            ws = sorted({p[1]["w"] for p in pool})
            ok = _reachable(ws, mw)
            if pool and ok[mw]:
                side = (d, pool, ws, ok)
                lay_h = mh + d
                break
    lay = Layout(mw, lay_h)
    lay.room(_roomtype(kind, main), 0, 0, mw - 1, mh - 1, main)
    if side:
        d, pool, ws, ok = side
        pos = 0
        for wd in _sequence(ws, ok, mw, rng):
            name, st = rng.choice([p for p in pool if p[1]["w"] == wd])
            lay.room(_roomtype(name, st), pos, mh, pos + wd - 1, mh + d - 1, st)
            lay.doors.append((pos + wd // 2, mh, "N"))
            pos += wd
    entries = [(0, mh // 2, "W"), (mw // 2, lay_h, "N")]
    return lay, entries


def single_room(kind, length, depth, horizontal, seed):
    """One vanilla room of that kind, the closest in size (guard houses, band room, small annexes)."""
    rng = random.Random(seed)
    lib = vanilla.library()
    names = MIX.get(kind, [kind])
    cands = [(n, st) for n in names for st in lib.get(n, []) if len(st["items"]) >= 2]
    if not cands:
        return None
    W, H = (length, depth) if horizontal else (depth, length)
    cands.sort(key=lambda p: abs(p[1]["w"] - W) + abs(p[1]["h"] - H))
    name, st = rng.choice(cands[:4])
    lay = Layout(st["w"], st["h"])
    lay.room(_roomtype(name, st), 0, 0, st["w"] - 1, st["h"] - 1, st)
    return lay, [(st["w"] // 2, st["h"], "N")]
