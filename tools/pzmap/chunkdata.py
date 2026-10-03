"""chunkdata_X_Y.bin, as zombie/pot/POTChunkData (42.20) writes it: big-endian (DataOutputStream), short version 1,
then per chunk (y outer, x inner) a type byte, plus 64 bytes (x + y * 8) for a regular chunk.
Beyond POT: bit 32 = the square has no level-0 lot data (worldgen fills it) and chunk type 5 = every square is that;
vanilla and Raven Creek files use both, read only by native code (MapCollisionData.n_initMetaCell)."""
import struct

SOLID, WALL_N, WALL_W, WATER, ROOM, NO_LOT = 1, 2, 4, 8, 16, 32
EMPTY_CHUNK, SOLID_CHUNK, REGULAR_CHUNK, WATER_CHUNK, ROOM_CHUNK, NO_LOT_CHUNK = 0, 1, 2, 3, 4, 5
UNIFORM = {0: EMPTY_CHUNK, SOLID: SOLID_CHUNK, WATER: WATER_CHUNK, ROOM: ROOM_CHUNK, NO_LOT: NO_LOT_CHUNK}
UNIFORM_BITS = {v: k for k, v in UNIFORM.items()}


class ChunkData:
    def __init__(self):
        self.bits = bytearray(256 * 256)  # cell-local x + y * 256

    def set(self, x, y, bits):
        self.bits[x + y * 256] = bits

    def get(self, x, y):
        return self.bits[x + y * 256]

    def to_bytes(self):
        out = bytearray(struct.pack(">h", 1))
        for cy in range(32):
            for cx in range(32):
                block = bytes(self.bits[cx * 8 + x + (cy * 8 + y) * 256] for y in range(8) for x in range(8))
                first = block[0]
                if first in UNIFORM and block.count(first) == 64:
                    out.append(UNIFORM[first])
                else:
                    out.append(REGULAR_CHUNK)
                    out += block
        return bytes(out)

    @classmethod
    def from_bytes(cls, b):
        cd = cls()
        assert struct.unpack_from(">h", b, 0)[0] == 1
        p = 2
        for cy in range(32):
            for cx in range(32):
                t = b[p]
                p += 1
                if t == REGULAR_CHUNK:
                    block = b[p:p + 64]
                    p += 64
                else:
                    block = bytes([UNIFORM_BITS[t]]) * 64
                for i, v in enumerate(block):
                    cd.bits[cx * 8 + i % 8 + (cy * 8 + i // 8) * 256] = v
        return cd

    def save(self, path):
        with open(path, "wb") as f:
            f.write(self.to_bytes())
