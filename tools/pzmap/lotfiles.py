"""B42 lot files (.lotheader / .lotpack), byte for byte as zombie/pot/POTLotHeader and POTLotPack (42.20) write them.

A Cell holds one 256 x 256 cell: the tile table, every square's tile list, rooms, buildings and zombie density.
Coordinates inside a Cell are cell-local (0..255); levels are -32..31."""
import struct

CELL = 256
CHUNK = 8
CHUNKS = 32
LOTHEADER_MAGIC = b"LOTH"
LOTPACK_MAGIC = b"LOTP"


class Room:
    __slots__ = ("name", "level", "rects", "objects")

    def __init__(self, name, level, rects=None, objects=None):
        self.name = name
        self.level = level
        self.rects = rects if rects is not None else []  # (x, y, w, h), cell-local
        self.objects = objects if objects is not None else []  # (type, x, y)


class Cell:
    def __init__(self, cell_x, cell_y):
        self.cell_x = cell_x
        self.cell_y = cell_y
        self.tiles = []
        self.tile_index = {}
        self.squares = {}  # (x, y, z) -> [tile index]
        self.square_rooms = {}  # (x, y, z) -> room index; WorldEd writes it, the game reads and ignores it
        self.rooms = []
        self.buildings = []  # [[room index]]
        self.density = bytearray(CHUNKS * CHUNKS)  # density[x + y * 32] per chunk
        self.version = 1

    # building

    def tile(self, name):
        i = self.tile_index.get(name)
        if i is None:
            i = len(self.tiles)
            self.tiles.append(name)
            self.tile_index[name] = i
        return i

    def set_square(self, x, y, z, names, room=-1):
        if names:
            self.squares[(x, y, z)] = [self.tile(n) for n in names]
            if room >= 0:
                self.square_rooms[(x, y, z)] = room
            else:
                self.square_rooms.pop((x, y, z), None)
        else:
            self.squares.pop((x, y, z), None)
            self.square_rooms.pop((x, y, z), None)

    def get_square(self, x, y, z):
        ids = self.squares.get((x, y, z))
        return [self.tiles[i] for i in ids] if ids else None

    def add_building(self, rooms):
        start = len(self.rooms)
        self.rooms.extend(rooms)
        self.buildings.append(list(range(start, start + len(rooms))))

    def level_range(self):
        if not self.squares:
            return 0, 0  # POT would write 1000, -1000; a reader sizing arrays by maxLevel - minLevel + 1 breaks on that
        zs = [k[2] for k in self.squares]
        return min(zs), max(zs)

    # writing

    def header_bytes(self, level_range=None):
        min_z, max_z = level_range or self.level_range()
        out = bytearray(LOTHEADER_MAGIC)
        out += struct.pack("<ii", 1, len(self.tiles))
        for t in self.tiles:
            out += t.encode("utf-8") + b"\n"
        out += struct.pack("<iiiii", CHUNK, CHUNK, min_z, max_z, len(self.rooms))
        for r in self.rooms:
            out += r.name.encode("utf-8") + b"\n"
            out += struct.pack("<ii", r.level, len(r.rects))
            for rect in r.rects:
                out += struct.pack("<iiii", *rect)
            out += struct.pack("<i", len(r.objects))
            for o in r.objects:
                out += struct.pack("<iii", *o)
        out += struct.pack("<i", len(self.buildings))
        for b in self.buildings:
            out += struct.pack("<i", len(b))
            out += struct.pack("<%di" % len(b), *b)
        for x in range(CHUNKS):
            for y in range(CHUNKS):
                out.append(self.density[x + y * CHUNKS])
        return bytes(out)

    def pack_bytes(self, level_range=None):
        min_z, max_z = level_range or self.level_range()
        levels = max(0, max_z - min_z + 1)
        per_chunk = levels * CHUNK * CHUNK
        by_chunk = {}
        for (x, y, z), ids in self.squares.items():
            if not ids:
                continue
            key = (x // CHUNK) * CHUNKS + y // CHUNK
            linear = (z - min_z) * 64 + (x % CHUNK) * CHUNK + y % CHUNK
            by_chunk.setdefault(key, []).append((linear, self.square_rooms.get((x, y, z), -1), ids))
        table_start = 12
        out = bytearray(LOTPACK_MAGIC)
        out += struct.pack("<ii", 1, CHUNKS * CHUNKS)  # POT writes 8 here; WorldEd's files (and the reader's seek) use 1024
        out += bytes(CHUNKS * CHUNKS * 8)
        for index in range(CHUNKS * CHUNKS):
            struct.pack_into("<q", out, table_start + index * 8, len(out))
            pos = 0
            for linear, room, ids in sorted(by_chunk.get(index, ())):
                if linear > pos:
                    out += struct.pack("<ii", -1, linear - pos)
                out += struct.pack("<ii", len(ids) + 1, room)
                out += struct.pack("<%di" % len(ids), *ids)
                pos = linear + 1
            if per_chunk > pos:
                out += struct.pack("<ii", -1, per_chunk - pos)
        return bytes(out)

    def save(self, folder):
        import os
        rng = self.level_range()
        name = "%d_%d" % (self.cell_x, self.cell_y)
        with open(os.path.join(folder, name + ".lotheader"), "wb") as f:
            f.write(self.header_bytes(rng))
        with open(os.path.join(folder, "world_" + name + ".lotpack"), "wb") as f:
            f.write(self.pack_bytes(rng))

    # reading

    @classmethod
    def load(cls, folder, cell_x, cell_y):
        import os
        name = "%d_%d" % (cell_x, cell_y)
        cell = cls(cell_x, cell_y)
        header = cell._read_header(os.path.join(folder, name + ".lotheader"))
        cell._read_pack(os.path.join(folder, "world_" + name + ".lotpack"), header)
        return cell

    def _read_header(self, path):
        b = open(path, "rb").read()
        p = 0

        def i32():
            nonlocal p
            v = struct.unpack_from("<i", b, p)[0]
            p += 4
            return v

        def s():
            nonlocal p
            e = b.index(b"\n", p)
            v = b[p:e].decode("utf-8")
            p = e + 1
            return v

        if b[:4] == LOTHEADER_MAGIC:
            p = 4
        self.version = i32()
        for _ in range(i32()):
            self.tile(s().strip())
        if self.version == 0:
            p += 1
        i32(), i32()
        if self.version == 0:
            min_level, max_level = 0, i32()
        else:
            min_level, max_level = i32(), i32()
        for _ in range(i32()):
            name = s()
            level = i32()
            rects = [(i32(), i32(), i32(), i32()) for _ in range(i32())]
            objects = [(i32(), i32(), i32()) for _ in range(i32())]
            self.rooms.append(Room(name, level, rects, objects))
        self.buildings = [[i32() for _ in range(i32())] for _ in range(i32())]
        for x in range(CHUNKS):
            for y in range(CHUNKS):
                self.density[x + y * CHUNKS] = b[p]
                p += 1
        self.file_level_range = (min_level, max_level)
        return dict(min_level=min_level, max_level=max_level)

    def _read_pack(self, path, header):
        b = open(path, "rb").read()
        off = 8 if b[:4] == LOTPACK_MAGIC else 0
        version = struct.unpack_from("<i", b, 4)[0] if off else 0
        min_z = max(header["min_level"], -32)
        max_z = min(header["max_level"], 31) - (1 if version == 0 else 0)
        self.room_ids_seen = set()
        for cx in range(CHUNKS):
            for cy in range(CHUNKS):
                p = struct.unpack_from("<i", b, off + 4 + (cx * CHUNKS + cy) * 8)[0]
                skip = 0
                for z in range(min_z, max_z + 1):
                    for x in range(CHUNK):
                        for y in range(CHUNK):
                            if skip > 0:
                                skip -= 1
                                continue
                            count = struct.unpack_from("<i", b, p)[0]
                            p += 4
                            if count == -1:
                                skip = struct.unpack_from("<i", b, p)[0]
                                p += 4
                                if skip > 0:
                                    skip -= 1
                                    continue
                            if count > 1:
                                room = struct.unpack_from("<i", b, p)[0]
                                self.room_ids_seen.add(room)
                                p += 4
                                ids = list(struct.unpack_from("<%di" % (count - 1), b, p))
                                p += 4 * (count - 1)
                                key = (cx * CHUNK + x, cy * CHUNK + y, z)
                                self.squares[key] = ids
                                if room >= 0:
                                    self.square_rooms[key] = room


def read_header(path):
    """Header only, as a dict (tiles, rooms as tuples, buildings, levels)."""
    c = Cell(0, 0)
    h = c._read_header(path)
    return dict(version=c.version, tiles=c.tiles, min_level=h["min_level"], max_level=h["max_level"],
                rooms=[(r.name, r.level, r.rects, r.objects) for r in c.rooms], buildings=c.buildings,
                density=bytes(c.density))


def read_pack(path, header, cell_x, cell_y):
    """{(x, y, z): [tile names]} in absolute coordinates."""
    c = Cell(cell_x, cell_y)
    c.tiles = header["tiles"]
    c._read_pack(path, header)
    return {(cell_x * CELL + x, cell_y * CELL + y, z): [c.tiles[i] for i in ids] for (x, y, z), ids in c.squares.items()}
