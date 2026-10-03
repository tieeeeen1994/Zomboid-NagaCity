"""Vanilla interiors stamped into Naga's rooms (data/vanilla_rooms.json, from build_room_library.py).

For a room of a given name and size, the vanilla rooms of that name that fit are ranked by how much space they
leave; one of the best few is picked by the room's position (so neighbouring classrooms differ) and copied with its
north-west square on the room's. The north and west walls line up, so things hung on them stay on walls. A room
much bigger than the stamp gets more copies of the stamp's inner part (without its first row and column, where wall
items live), except rooms whose furniture must stay single (an altar, a kitchen). Corridors stay empty: vanilla
`hall` rooms are house hallways (washers, sinks). Squares next to doors and stairs are kept clear."""
import json
import os

import config

FALLBACK = {"universityoffice": "office", "security": "office", "church": "church", "daycare": "daycare",
            "universitylibrary": "library", "hall": None}
NO_FURNITURE = {"hall"}
NO_REPEAT = {"church", "gym", "kitchen", "livingroom", "bedroom", "bathroom", "daycare", "security"}
_lib = None


def library():
    global _lib
    if _lib is None:
        path = os.path.join(config.DATA, "vanilla_rooms.json")
        _lib = json.load(open(path)) if os.path.exists(path) else {}
    return _lib


def furnish(name, x0, y0, x1, y1, clear=frozenset()):
    """[(x, y, [tiles])] for the room's rect (inclusive), or [] when vanilla has nothing for it."""
    if name in NO_FURNITURE:
        return []
    lib = library()
    cands = lib.get(name) or (lib.get(FALLBACK[name]) if FALLBACK.get(name) else None) or []
    w, h = x1 - x0 + 1, y1 - y0 + 1
    fits = [c for c in cands if c["w"] <= w and c["h"] <= h and len(c["items"]) >= 2]
    if not fits:
        return []
    fits.sort(key=lambda c: ((w - c["w"]) + (h - c["h"]), -len(c["items"])))
    best = fits[:6]
    stamp = best[(x0 * 7 + y0 * 13) % len(best)]
    out = [(x0 + dx, y0 + dy, tiles) for dx, dy, tiles in stamp["items"]]
    sw, sh = stamp["w"], stamp["h"]
    if (w >= 2 * sw or h >= 2 * sh) and name not in NO_REPEAT:
        inner = [(dx, dy, t) for dx, dy, t in stamp["items"] if dx >= 1 and dy >= 1]
        for oy in range(0, h - sh + 1, sh):
            for ox in range(0, w - sw + 1, sw):
                if ox == 0 and oy == 0:
                    continue
                out += [(x0 + ox + dx, y0 + oy + dy, t) for dx, dy, t in inner]
    return [(x, y, t) for x, y, t in out if (x, y) not in clear and x <= x1 and y <= y1]
