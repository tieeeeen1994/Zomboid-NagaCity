"""Floor-plan templates for buildkit.Building: classroom blocks, libraries, offices, halls, houses. Furniture
arrangements are copied from vanilla rooms (CLAUDE.md "Buildings"): the 39_49 school classroom, the 48_8 university
library and office, the 39_49 restroom.

Plans are built in local coordinates on a footprint mask (set of (x, y)); the long axis decides where the corridor
goes: along the south side of an east-west block, along the east side of a north-south one. Stairs always climb
north (bottom 24, top 26), so stair bays sit at the west end / north end where the climb fits."""
from buildkit import Building, RoomType, WallSet

INTERIOR = WallSet("walls_interior_house_02", 3, 0)      # cream
INTERIOR_TILE = WallSet("walls_interior_bathroom_01", 1, 0)
FLOOR_ROOM = "floors_interior_tilesandwood_01_46"
FLOOR_HALL = "floors_interior_tilesandwood_01_19"
FLOOR_BATH = "floors_interior_tilesandwood_01_11"
FLOOR_OFFICE = "floors_interior_tilesandwood_01_44"
FLOOR_GYM = "floors_interior_tilesandwood_01_17"
FLOOR_HOUSE = "floors_interior_tilesandwood_01_42"

ROOM = {
    "classroom": RoomType("classroom", FLOOR_ROOM, INTERIOR),
    "hall": RoomType("hall", FLOOR_HALL, INTERIOR),
    "bathroom": RoomType("bathroom", FLOOR_BATH, INTERIOR_TILE),
    "office": RoomType("office", FLOOR_OFFICE, INTERIOR),
    "universityoffice": RoomType("universityoffice", FLOOR_OFFICE, INTERIOR),
    "universitylibrary": RoomType("universitylibrary", FLOOR_ROOM, INTERIOR),
    "gym": RoomType("gym", FLOOR_GYM, INTERIOR),
    "church": RoomType("church", FLOOR_ROOM, INTERIOR),
    "bedroom": RoomType("bedroom", FLOOR_HOUSE, INTERIOR),
    "kitchen": RoomType("kitchen", FLOOR_BATH, INTERIOR),
    "livingroom": RoomType("livingroom", FLOOR_HOUSE, INTERIOR),
    "storage": RoomType("storage", "floors_interior_tilesandwood_01_17", INTERIOR),
    "security": RoomType("security", FLOOR_OFFICE, INTERIOR),
    "daycare": RoomType("daycare", FLOOR_ROOM, INTERIOR),
}

# Furniture, as vanilla lays it (see module docstring).
CHALKBOARD_W = ["location_business_office_generic_01_67", "location_business_office_generic_01_66",
                "location_business_office_generic_01_65", "location_business_office_generic_01_64"]  # north to south
DESK_N, DESK_S, DESK_CHAIR = "furniture_tables_high_01_33", "furniture_tables_high_01_32", "furniture_seating_indoor_01_52"
TEACHER = ["furniture_tables_high_01_34", "furniture_tables_high_01_35", "furniture_seating_indoor_01_50"]  # west to east
TOILET, STALL = "fixtures_bathroom_01_0", "fixtures_bathroom_01_57"
SINK_W = "fixtures_sinks_01_15"
SHELF_E, SHELF_W = "furniture_shelving_01_41", "furniture_shelving_01_42"
OFFICE_DESK = ["location_business_office_generic_01_96", "location_business_office_generic_01_97",
               "location_business_office_generic_01_98"]
OFFICE_CHAIR = "furniture_seating_indoor_02_47"
WALL_SHELF = "furniture_shelving_01_10"

KEYS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRTUVWXYZ0123456789"


class Plan:
    """Accumulates one footprint's rooms, then writes them as identical floors on a Building."""

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.grid = [["." for _ in range(w)] for _ in range(h)]
        self.legend = {}
        self.rooms = []   # (key, room name, x0, y0, x1, y1) inclusive
        self.doors = []   # (x, y, side)
        self._next = 0

    def room(self, name, x0, y0, x1, y1, mask=None):
        key = KEYS[self._next % len(KEYS)]
        self._next += 1
        self.legend[key] = ROOM[name]
        for y in range(max(y0, 0), min(y1, self.h - 1) + 1):
            for x in range(max(x0, 0), min(x1, self.w - 1) + 1):
                if mask is None or (x, y) in mask:
                    self.grid[y][x] = key
        self.rooms.append((key, name, x0, y0, x1, y1))
        return key

    def rows(self):
        return ["".join(r) for r in self.grid]


def classroom_furniture(x0, y0, x1, y1, door_side):
    """Board on the west wall, teacher's desk in front, desks in rows facing west. Leaves the door row free."""
    out = []
    ym = (y0 + y1) // 2
    if y1 - y0 >= 5:
        for i, t in enumerate(CHALKBOARD_W):
            out.append((x0, ym - 2 + i, [t]))
    for i, t in enumerate(TEACHER):
        if x0 + 1 + i <= x1:
            out.append((x0 + 1 + i, y0, [t]))
    last = y1 - 2 if door_side == "S" else y1
    for x in range(x0 + 4, x1 - 1, 3):
        for y in range(y0 + 2, last, 3):
            out += [(x, y, [DESK_N]), (x, y + 1, [DESK_S]), (x + 1, y, [DESK_CHAIR]), (x + 1, y + 1, [DESK_CHAIR])]
    return out


def bathroom_furniture(x0, y0, x1, y1):
    out = [(x, y0, [STALL, TOILET]) for x in range(x0 + 1, x1, 2)]
    out += [(x0, y, [SINK_W]) for y in range(y0 + 2, y1)]
    return out


def library_furniture(x0, y0, x1, y1):
    out = []
    for x in range(x0 + 1, x1 - 1, 3):
        for y in range(y0 + 1, min(y1 - 2, y0 + 1 + 6)):
            out += [(x, y, [SHELF_E]), (x + 2, y, [SHELF_W])]
    return out


def office_furniture(x0, y0, x1, y1):
    out = []
    for y in range(y0 + 1, y1 - 1, 4):
        for x in range(x0 + 1, x1 - 3, 5):
            out += [(x + i, y, [t]) for i, t in enumerate(OFFICE_DESK)]
            out.append((x + 1, y + 1, [OFFICE_CHAIR]))
    out += [(x0, y, [WALL_SHELF]) for y in range(y0 + 1, y1, 3)]
    return out


def school_wing(p, x0, y0, w, h, levels, kind="classroom", stairs=True):
    """One rectangular wing of rooms in plan p at (x0, y0): rooms along the long side, a corridor (3 wide, 2 when the
    wing is narrow) on the south / east, a 6-wide stair bay at the west / north end (stairs alternate between two
    spots per level), restrooms at the other end. Returns (furniture, stairs, entries, corridor rect)."""
    furniture, stair_list = [], []
    corridor = 3 if min(w, h) >= 10 else 2
    if w >= h:
        rooms_h = h - corridor
        hall = (x0, y0 + rooms_h, x0 + w - 1, y0 + h - 1)
        p.room("hall", *hall)
        bay = 6 if stairs and levels > 1 and rooms_h >= 5 and w >= 16 else 0
        if bay:
            p.room("hall", x0, y0, x0 + bay - 1, y0 + rooms_h - 1)
            p.doors.append((x0 + 2, y0 + rooms_h, "N"))
        bath = 5 if w - bay >= 18 else 0
        start, end = x0 + bay, x0 + w - bath
        n = max(1, round((end - start) / 9))
        cuts = [start + round(i * (end - start) / n) for i in range(n + 1)]
        for a, b in zip(cuts, cuts[1:]):
            p.room(kind, a, y0, b - 1, y0 + rooms_h - 1)
            p.doors.append(((a + b) // 2, y0 + rooms_h, "N"))
        if bath:
            p.room("bathroom", end, y0, x0 + w - 1, y0 + rooms_h - 1)
            p.doors.append((end + 2, y0 + rooms_h, "N"))
        entry = [(x0 + w // 3, y0 + h, "N"), (x0 + 2 * w // 3, y0 + h, "N"), (x0, y0 + rooms_h + 1, "W")]
    else:
        rooms_w = w - corridor
        hall = (x0 + rooms_w, y0, x0 + w - 1, y0 + h - 1)
        p.room("hall", *hall)
        bay = 6 if stairs and levels > 1 and rooms_w >= 6 and h >= 16 else 0
        if bay:
            p.room("hall", x0, y0, x0 + rooms_w - 1, y0 + bay - 1)
            p.doors.append((x0 + rooms_w, y0 + 4, "W"))
        bath = 5 if h - bay >= 18 else 0
        start, end = y0 + bay, y0 + h - bath
        n = max(1, round((end - start) / 9))
        cuts = [start + round(i * (end - start) / n) for i in range(n + 1)]
        for a, b in zip(cuts, cuts[1:]):
            p.room(kind, x0, a, x0 + rooms_w - 1, b - 1)
            p.doors.append((x0 + rooms_w, (a + b) // 2, "W"))
        if bath:
            p.room("bathroom", x0, end, x0 + rooms_w - 1, y0 + h - 1)
            p.doors.append((x0 + rooms_w, end + 2, "W"))
        entry = [(x0 + w, y0 + h // 3, "W"), (x0 + w, y0 + 2 * h // 3, "W"), (x0 + rooms_w + 1, y0 + h, "N")]
    if levels > 1 and bay:
        for z in range(levels - 1):
            stair_list.append((z, x0 + (1 if z % 2 == 0 else 3), y0 + 1))
    return furniture, stair_list, entry, hall


def school_block(w, h, levels, kind="classroom", stairs=True, wings=None):
    """A whole footprint: one wing, or several rectangles (x, y, w, h) of an L / U shaped footprint, the first with
    the stair bay; corridors of touching wings get a door between them."""
    p = Plan(w, h)
    wings = wings or [(0, 0, w, h)]
    furniture, stair_list, entry, halls = [], [], [], []
    for i, (x, y, ww, hh) in enumerate(wings):
        f, s, e, hall = school_wing(p, x, y, ww, hh, levels, kind, stairs and i == 0)
        furniture += f
        stair_list += s
        entry += e
        halls.append(hall)
    for i, a in enumerate(halls):
        for b in halls[i + 1:]:
            door = _touching_door(a, b)
            if door:
                p.doors.append(door)
    return p, furniture, stair_list, entry


def _touching_door(a, b):
    """A door on the shared edge of two corridor rects (x0, y0, x1, y1 inclusive), if they touch."""
    for r, q in ((a, b), (b, a)):
        if q[1] == r[3] + 1:  # q just south of r
            lo, hi = max(r[0], q[0]), min(r[2], q[2])
            if lo <= hi:
                return ((lo + hi) // 2, q[1], "N")
        if q[0] == r[2] + 1:  # q just east of r
            lo, hi = max(r[1], q[1]), min(r[3], q[3])
            if lo <= hi:
                return (q[0], (lo + hi) // 2, "W")
    return None


def hall_block(w, h, name, furniture_fn=None, levels=1):
    p = Plan(w, h)
    p.room(name, 0, 0, w - 1, h - 1)
    furniture = []
    entry = [(w // 2, h, "N"), (0, h // 2, "W")]
    stair_list = [(z, 1 + 2 * (z % 2), 1) for z in range(levels - 1)] if levels > 1 and h >= 6 and w >= 6 else []
    return p, furniture, stair_list, entry


def house_block(w, h):
    p = Plan(w, h)
    mid = w // 2
    p.room("livingroom", 0, 0, mid - 1, h // 2 - 1)
    p.room("kitchen", mid, 0, w - 1, h // 2 - 1)
    p.room("bedroom", 0, h // 2, mid - 1, h - 1)
    p.room("bedroom", mid, h // 2, w - 1 - 4, h - 1)
    p.room("bathroom", w - 4, h // 2, w - 1, h - 1)
    p.doors += [(mid, h // 4, "W"), (mid // 2, h // 2, "N"), (mid + 2, h // 2, "N"), (w - 4, h // 2 + 2, "W")]
    furniture = []
    entry = [(mid // 2, h, "N"), (0, h // 4, "W")]
    return p, furniture, [], entry


def make_building(name, ox, oy, exterior, plan, furniture, stair_list, entry, levels):
    """Furniture: vanilla interiors stamped per room (rooms.furnish), the hand layouts above where vanilla has no
    room of that name and size."""
    import rooms as vanilla
    b = Building(name, ox, oy, exterior)
    rows = plan.rows()
    doors = list(plan.doors) + list(entry)
    clear = set()
    for x, y, side in doors:
        clear |= {(x, y), (x, y - 1)} if side == "N" else {(x, y), (x - 1, y)}
    for sz, sx, sy in stair_list:
        clear |= {(sx + dx, sy + dy) for dx in (0, 1) for dy in (-1, 0, 1, 2, 3)}
    per_room = []
    for key, rname, x0, y0, x1, y1 in plan.rooms:
        items = vanilla.furnish(rname, x0, y0, x1, y1, clear)
        if not items and rname not in vanilla.NO_FURNITURE:
            items = [(x, y, t) for x, y, t in _hand_furniture(rname, x0, y0, x1, y1) if (x, y) not in clear]
        per_room += items
    for z in range(levels):
        b.floor(z, rows, plan.legend)
        for x, y, side in plan.doors:
            b.doors.add((z, x, y, side))
        for x, y, tiles in per_room + furniture:
            if not any(x in (sx, sx + 1) and sy - 1 <= y <= sy + 3 and sz in (z, z - 1) for sz, sx, sy in stair_list):
                b.furniture.append((z, x, y, tiles))
    for x, y, side in entry:
        b.doors.add((0, x, y, side))
    b.stairs = stair_list
    return b


def _hand_furniture(name, x0, y0, x1, y1):
    if name == "classroom":
        return classroom_furniture(x0, y0, x1, y1, "S")
    if name == "bathroom":
        return bathroom_furniture(x0, y0, x1, y1)
    if name in ("universitylibrary", "library"):
        return library_furniture(x0, y0, x1, y1)
    if name in ("office", "universityoffice"):
        return office_furniture(x0, y0, x1, y1)
    return []
