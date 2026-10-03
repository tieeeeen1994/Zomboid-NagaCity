"""Buildings from floor plans, the way vanilla builds them (see CLAUDE.md "Buildings").

A Building is a set of floors; each floor is a grid of room keys (one character per square, '.' = outside) in the
building's own coordinates (x east, y south), plus doors, stairs and furniture. `Canvas` collects every square's tiles,
the rooms and the chunk bits in absolute coordinates; generate.py merges it into the cells over the ground.

Vanilla's rules (checked on the 48_8 university, the 39_49 school and the 41_37 houses):
- Walls are edge sprites on a square's north or west edge. A wall between two squares goes on the southern / eastern
  one. On a square inside a room it is the room's interior set (+ baseboard `walls_interior_detailing_01`); on a
  square outside (the building's south and east faces) the exterior set.
- A wall set's rows of 16: colour A 0 W, 1 N, 2 NW corner, 3 SE post; colour B the same + 4; openings + 8: W window,
  N window, W door, N door (colour B + 12). Two walls meeting in a square's north-west corner are the corner piece; the
  post fills an outside corner (no wall on the square, a north wall west of it and a west wall north of it).
- Windows: the window frame piece + `fixtures_windows_01` (16 W / 17 N), placed per room like vanilla buildings: on
  each room's stretch of outside wall about one per 5 squares, spread evenly, not on the stretch's end squares,
  next to furniture or on a door; restrooms / storerooms / janitor rooms at most one, corridors and stairwells one
  per 8 (the first version put one on every other square: "why does every wall have a window?"). Doors: the door frame piece +
  `fixtures_doors_01` (0 W / 1 N).
- Stairs climb north: bottom 24, middle 25, top 26 (`fixtures_stairs_01`), two wide; the floor above them is left
  open and the square north of the top is where they arrive.
- Flat roof: `roofs_04_54` over every square of the floor above the top floor.
- Wall-hung furniture (clocks, certificates, whiteboards: sprites with `attachedN / W / E / S / NW / SE` in the tile
  definitions, pzmap/tiledefs.py) is kept only where its edge has a plain wall in this building; windows avoid the
  edges such items need. (Copied vanilla rooms of another size otherwise left certificates hanging in the air and a
  clock on a window, the user's catch 2026-10-04.)
- Nothing is placed on the squares either side of a door, on stairs, or at a stair's two ends (a vanilla kitchen
  put its stove in front of the kitchen door, the user's catch 2026-10-04)."""
from collections import defaultdict

from pzmap.chunkdata import ROOM, WALL_N, WALL_W
from pzmap.tiledefs import attached

W, N = "W", "N"


class WallSet:
    def __init__(self, family, row=0, colour=0):
        self.family, self.base = family, row * 16 + colour * 4

    def tile(self, piece):
        """piece: W, N, NW, SE, WWIN, NWIN, WDOOR, NDOOR"""
        k = {"W": 0, "N": 1, "NW": 2, "SE": 3, "WWIN": 8, "NWIN": 9, "WDOOR": 10, "NDOOR": 11}[piece]
        return "%s_%d" % (self.family, self.base + k)


# Wainscot / crown strip on interior walls; laid out like a wall set (row 2), so windows and doors get their own
# piece (vanilla: detailing_01_42 with a west door frame, _9 / _41 with north window frames).
DETAIL = WallSet("walls_interior_detailing_01", 2, 0)
WINDOW = {W: "fixtures_windows_01_16", N: "fixtures_windows_01_17"}
DOOR = {W: "fixtures_doors_01_0", N: "fixtures_doors_01_1"}
STAIRS = ("fixtures_stairs_01_26", "fixtures_stairs_01_25", "fixtures_stairs_01_24")  # top (north) to bottom
STAIRS_W = ("fixtures_stairs_01_18", "fixtures_stairs_01_17", "fixtures_stairs_01_16")  # top (west) to bottom
FLAT_ROOF = "roofs_04_54"


class RoomType:
    def __init__(self, name, floor, walls, outdoor=False):
        self.name = name        # vanilla room name: picks the loot (classroom, universitylibrary, office...)
        self.floor = floor      # floor tile
        self.walls = walls      # interior WallSet
        self.outdoor = outdoor  # verandas / corridors: no room def, railing instead of walls
        self.detail = True      # wainscot strip on its walls (off for rooms copied from vanilla, which bring their own)


class Canvas:
    """Everything the landmarks place, in absolute coordinates."""

    def __init__(self):
        self.squares = {}                # (x, y, z) -> [tiles], floor first
        self.room_of = {}                # (x, y, z) -> global room index
        self.rooms = []                  # [name, level, set of (x, y)]
        self.buildings = []              # [[room index]]
        self.bits = defaultdict(int)     # (x, y) -> chunkdata bits (level 0)
        self.claimed = set()             # (x, y) of the ground the landmarks own (no generic roads / buildings)
        self.ground_only = set()         # level-0 squares holding only a ground tile (a building floor replaces it)

    def add(self, x, y, z, tiles):
        self.squares.setdefault((x, y, z), []).extend(tiles)

    def floor(self, x, y, z, tile):
        """A building's floor: replaces a ground tile, else goes first."""
        key = (x, y, z)
        if key in self.ground_only:
            self.ground_only.discard(key)
            self.squares[key][0] = tile
        elif key in self.squares:
            self.squares[key].insert(0, tile)
        else:
            self.squares[key] = [tile]

    def ground(self, x, y, tiles):
        """Lay a level-0 ground tile (paving, lawn); a building floor laid later replaces it."""
        key = (x, y, 0)
        if key in self.squares and key not in self.ground_only:
            return
        self.squares[key] = list(tiles)
        self.ground_only.add(key)
        self.claimed.add((x, y))


class Building:
    def __init__(self, name, ox, oy, exterior):
        self.name, self.ox, self.oy = name, ox, oy
        self.exterior = exterior   # WallSet for the outside faces
        self.floors = {}           # z -> list of strings
        self.legend = {}           # key -> RoomType
        self.doors = set()         # (z, x, y, W|N) local
        self.no_window = set()     # (z, x, y, W|N) local edges kept blank
        self.stairs = []           # (z, x, y_top) north-climbing, or (z, x_top, y, "W") west-climbing; two wide
        self.edge_walls = {}       # (z, x, y, W|N) -> WallSet replacing the usual set on that edge (shopfronts)
        self.door_tiles = {}       # (z, x, y, W|N) -> door object replacing the plain door (glass shop doors)
        self.fixed_windows = None  # set of (z, x, y, W|N): hand-placed windows instead of the per-room plan
        self.furniture = []        # (z, x, y, [tiles]) local
        self.furnished = set()     # (z, x, y) local squares with furniture: no window cut into their walls
        self._windows = {}         # z -> planned window edges

    def floor(self, z, rows, legend):
        self.floors[z] = rows
        self.legend.update(legend)

    def key(self, z, x, y):
        rows = self.floors.get(z)
        if rows is None or y < 0 or y >= len(rows) or x < 0 or x >= len(rows[y]):
            return None
        k = rows[y][x]
        return None if k == "." else k

    def _hung_edges(self, z, x, y, tile):
        """The wall edges (buildkit form) a wall-hung tile on local square (x, y) needs, or [] for free-standing."""
        a = attached().get(tile)
        if not a:
            return []
        out = []
        if "N" in a:
            out.append((x, y, N))
        if "W" in a:
            out.append((x, y, W))
        if "S" in a:
            out.append((x, y + 1, N))
        if "E" in a:
            out.append((x + 1, y, W))
        return out

    def draw(self, canvas):
        self._hung = {(z,) + e for z, x, y, tiles in self.furniture for t in tiles for e in self._hung_edges(z, x, y, t)}
        room_index = {}
        first_room = len(canvas.rooms)
        top = max(self.floors)
        stair_holes = set()
        for st in self.stairs:
            z, x, y = st[:3]
            if len(st) > 3 and st[3] == "W":
                stair_holes |= {(z + 1, self.ox + x + dx, self.oy + y + dy) for dx in (0, 1, 2) for dy in (0, 1)}
            else:
                stair_holes |= {(z + 1, self.ox + x + dx, self.oy + y + dy) for dx in (0, 1) for dy in (0, 1, 2)}
        for z, rows in sorted(self.floors.items()):
            h, w = len(rows), max(len(r) for r in rows)
            # rooms: one room def per connected key region would be nicer; one per key and level is what vanilla's
            # simple buildings do (rects may be many).
            for y in range(h):
                for x in range(w):
                    k = self.key(z, x, y)
                    if k is None:
                        continue
                    rt = self.legend[k]
                    ax, ay = self.ox + x, self.oy + y
                    if (z, ax, ay) not in stair_holes:
                        canvas.floor(ax, ay, z, rt.floor)
                    if not rt.outdoor:
                        ri = room_index.get((k, z))
                        if ri is None:
                            ri = room_index[(k, z)] = len(canvas.rooms)
                            canvas.rooms.append([rt.name, z, set()])
                        canvas.rooms[ri][2].add((ax, ay))
                        canvas.room_of[(ax, ay, z)] = ri
                        if z == 0:
                            canvas.bits[(ax, ay)] |= ROOM
                    if z == 0:
                        canvas.claimed.add((ax, ay))
            # walls on every square of the grid plus one row / column beyond (the south and east faces)
            for y in range(h + 1):
                for x in range(w + 1):
                    self._walls(canvas, z, x, y)
            if z == top:
                for y in range(h):
                    for x in range(w):
                        if self.key(z, x, y) is not None:
                            canvas.add(self.ox + x, self.oy + y, z + 1, [FLAT_ROOF])
        for st in self.stairs:
            z, x, y = st[:3]
            if len(st) > 3 and st[3] == "W":
                for dy in (0, 1):
                    for dx, tile in enumerate(STAIRS_W):
                        canvas.add(self.ox + x + dx, self.oy + y + dy, z, [tile])
            else:
                for dx in (0, 1):
                    for dy, tile in enumerate(STAIRS):
                        canvas.add(self.ox + x + dx, self.oy + y + dy, z, [tile])
        blocked = set()  # squares either side of every door, and stairs with their two ends: nothing stands there
        for z, x, y, side in self.doors:
            blocked |= {(z, x, y), (z, x, y - 1) if side == N else (z, x - 1, y)}
        for st in self.stairs:
            z, x, y = st[:3]
            if len(st) > 3 and st[3] == "W":
                blocked |= {(z, x + dx, y + dy) for dx in (-1, 0, 1, 2, 3) for dy in (0, 1)}
                blocked |= {(z + 1, x - 1, y + dy) for dy in (0, 1)}
            else:
                blocked |= {(z, x + dx, y + dy) for dx in (0, 1) for dy in (-1, 0, 1, 2, 3)}
                blocked |= {(z + 1, x + dx, y - 1) for dx in (0, 1)}
        for z, x, y, tiles in self.furniture:
            if (z, x, y) in blocked:
                continue
            keep = []
            for t in tiles:
                edges = self._hung_edges(z, x, y, t)
                if all(self._plain_wall(z, ex, ey, side) for ex, ey, side in edges):
                    keep.append(t)
            if keep:
                canvas.add(self.ox + x, self.oy + y, z, keep)
        canvas.buildings.append(list(range(first_room, len(canvas.rooms))))

    def _edge(self, z, x, y, side):
        """What the wall on the north (side N) or west (side W) edge of local square (x, y) is, or None."""
        here = self.key(z, x, y)
        there = self.key(z, x, y - 1) if side == N else self.key(z, x - 1, y)
        if here == there:
            return None
        rt_here = self.legend.get(here) if here else None
        rt_there = self.legend.get(there) if there else None
        if (rt_here is None or rt_here.outdoor) and (rt_there is None or rt_there.outdoor):
            return None  # outside / veranda boundaries get railings, not walls
        if (z, x, y, side) in self.doors:
            kind = "DOOR"
        elif self._window_here(z, x, y, side, rt_here, rt_there):
            kind = "WIN"
        else:
            kind = ""
        inside = rt_here is not None and not rt_here.outdoor
        return kind, inside, rt_here if inside else None

    def _plain_wall(self, z, x, y, side):
        e = self._edge(z, x, y, side)
        return e is not None and e[0] == ""

    def _window_here(self, z, x, y, side, rt_here, rt_there):
        if self.fixed_windows is not None:
            return (z, x, y, side) in self.fixed_windows
        if z not in self._windows:
            self._windows[z] = self._plan_windows(z)
        return (x, y, side) in self._windows[z] and (z, x, y, side) not in self.no_window

    def _inside(self, k):
        rt = self.legend.get(k) if k else None
        return rt is not None and not rt.outdoor

    def _plan_windows(self, z):
        """{(x, y, side)} of the window edges on level z (see the module docstring)."""
        rows = self.floors[z]
        h, w = len(rows), max(len(r) for r in rows)
        lines = []
        for y in range(h + 1):  # north edges of row y: the room is below (row y) or above (row y - 1)
            edges = []
            for x in range(w):
                a, b = self.key(z, x, y), self.key(z, x, y - 1)
                edges.append((a, "in") if self._inside(a) and not self._inside(b) else
                             (b, "out") if self._inside(b) and not self._inside(a) else None)
            lines.append((N, y, edges))
        for x in range(w + 1):  # west edges of column x: the room is right (column x) or left (column x - 1)
            edges = []
            for y in range(h):
                a, b = self.key(z, x, y), self.key(z, x - 1, y)
                edges.append((a, "in") if self._inside(a) and not self._inside(b) else
                             (b, "out") if self._inside(b) and not self._inside(a) else None)
            lines.append((W, x, edges))
        few = {"bathroom", "storage", "janitor", "schoolstorage", "lockerroom", "security"}
        out = set()
        for side, line, edges in lines:
            runs, cur, last = [], [], None
            for pos, e in enumerate(edges + [None]):
                if e != last and cur:
                    runs.append((last, cur))
                    cur = []
                if e is not None:
                    cur.append(pos)
                last = e
            for (k, where), group in runs:
                usable = group[1:-1]
                if not usable:
                    continue
                name = self.legend[k].name
                if name == "hall":
                    count = len(group) // 8
                elif name in few:
                    count = 1 if len(group) >= 4 else 0
                else:
                    count = max(1, round(len(group) / 5))
                for i in range(count):
                    pos = usable[min(len(usable) - 1, int((i + 0.5) * len(usable) / count))]
                    for p in (pos, pos + 1, pos - 1):
                        if p not in usable:
                            continue
                        x, y = (p, line) if side == N else (line, p)
                        room = (x, y) if where == "in" else ((x, y - 1) if side == N else (x - 1, y))
                        if (z, x, y, side) in self.doors or (z, x, y, side) in getattr(self, "_hung", ()):
                            continue
                        out.add((x, y, side))
                        break
        return out

    def _walls(self, canvas, z, x, y):
        n, w = self._edge(z, x, y, N), self._edge(z, x, y, W)
        ax, ay = self.ox + x, self.oy + y
        tiles = []
        same_set = self.edge_walls.get((z, x, y, N)) is self.edge_walls.get((z, x, y, W))
        if n and w and not n[0] and not w[0] and n[1] == w[1] and same_set:
            ws = self.edge_walls.get((z, x, y, N)) or (n[2].walls if n[1] else self.exterior)
            tiles.append(ws.tile("NW"))
            if n[1] and n[2].detail:
                tiles.append(DETAIL.tile("NW"))
        else:
            for side, e in ((W, w), (N, n)):
                if not e:
                    continue
                kind, inside, rt = e
                override = self.edge_walls.get((z, x, y, side))
                ws = override or (rt.walls if inside else self.exterior)
                piece = side + kind
                tiles.append(ws.tile(piece))
                if inside and rt.detail and not override:
                    tiles.append(DETAIL.tile(piece))
                if kind == "DOOR":
                    tiles.append(self.door_tiles.get((z, x, y, side), DOOR[side]))
                elif kind == "WIN":
                    tiles.append(WINDOW[side])
        if not n and not w:
            west_n = self._edge(z, x - 1, y, N)
            north_w = self._edge(z, x, y - 1, W)
            if west_n and north_w:
                tiles.append(self.exterior.tile("SE"))
        if not tiles:
            return
        if (ax, ay, z) not in canvas.squares and z == 0:
            canvas.ground(ax, ay, ["blends_natural_01_16"])
        canvas.add(ax, ay, z, tiles)
        if z == 0:
            if n:
                canvas.bits[(ax, ay)] |= WALL_N
            if w:
                canvas.bits[(ax, ay)] |= WALL_W
