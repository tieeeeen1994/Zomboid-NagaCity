"""Collect vanilla interiors: every rectangular room (one rect) in Knox County, its name, size and furniture, into
data/vanilla_rooms.json. rooms.furnish() stamps them into Naga's rooms ("for the interiors, you can use the normal
zomboid format", the user, 2026-10-03).

Kept per room: every tile on its squares except floors, walls, doors, windows and overlays (decals, grime), relative
to the room's north-west square; its most common floor tile; and its interior wall set (family and the base of its
16-tile row block, read from the plain W / N wall pieces on its own squares), so a copied room keeps its look. Furniture hung on the room's own south / east walls sits on squares outside the
rect and is not kept.

    tools/.venv/Scripts/python.exe tools/build_room_library.py"""
import json
import os
import re
import time
from collections import Counter

import config
from pzmap.lotfiles import Cell, read_header

SKIP = ("floors_", "blends_", "walls_", "fixtures_doors", "fixtures_windows", "overlay_", "d_", "carpentry_02",
        "street_", "roofs_", "fixtures_stairs", "fixtures_railings", "lighting_outdoor", "vegetation_", "e_", "f_",
        "trash_", "papernotices", "location_restaurant_spiffos_01_7")
MIN_SIDE, MAX_SIDE = 3, 64
WALL = re.compile(r"(walls_interior_[a-z]+_\d+)_(\d+)$")
OUT = os.path.join(config.DATA, "vanilla_rooms.json")


def main():
    start = time.time()
    lib = {}
    files = sorted(f for f in os.listdir(config.VANILLA_MAP) if f.endswith(".lotheader"))
    for k, f in enumerate(files):
        h = read_header(os.path.join(config.VANILLA_MAP, f))
        if len(h["rooms"]) < 3:
            continue
        cx, cy = map(int, re.match(r"(\d+)_(\d+)", f).groups())
        cell = Cell.load(config.VANILLA_MAP, cx, cy)
        for r in cell.rooms:
            if len(r.rects) != 1:
                continue
            x, y, w, hh = r.rects[0]
            if not (MIN_SIDE <= w <= MAX_SIDE and MIN_SIDE <= hh <= MAX_SIDE):
                continue
            if x < 0 or y < 0 or x + w > 256 or y + hh > 256:
                continue
            items, floors, walls = [], Counter(), Counter()
            for yy in range(y, y + hh):
                for xx in range(x, x + w):
                    t = cell.get_square(xx, yy, r.level)
                    if not t:
                        continue
                    floors[t[0]] += 1
                    for n in t[1:]:
                        m = WALL.match(n)
                        if m and int(m[2]) % 16 in (0, 1, 4, 5):
                            k = int(m[2])
                            walls[(m[1], k - k % 16 + (4 if k % 16 >= 4 else 0))] += 1
                    keep = [n for n in t[1:] if not n.startswith(SKIP)]
                    if keep:
                        items.append([xx - x, yy - y, keep])
            if items:
                entry = {"w": w, "h": hh, "items": items, "src": "%d_%d %d,%d z%d" % (cx, cy, x, y, r.level)}
                if floors:
                    entry["floor"] = floors.most_common(1)[0][0]
                if walls:
                    entry["walls"] = list(walls.most_common(1)[0][0])
                lib.setdefault(r.name.strip(), []).append(entry)
        if (k + 1) % 400 == 0:
            print("  %d / %d cells, %d room names (%.0f s)" % (k + 1, len(files), len(lib), time.time() - start))
    os.makedirs(config.DATA, exist_ok=True)
    with open(OUT, "w") as fh:
        json.dump(lib, fh)
    print("%d room names, %d rooms, %.1f MB, %.0f s" % (len(lib), sum(len(v) for v in lib.values()),
                                                       os.path.getsize(OUT) / 1e6, time.time() - start))
    for name in ("classroom", "church", "gym", "bedroom", "kitchen", "livingroom", "bathroom", "office",
                 "universitylibrary", "universityoffice", "daycare", "storage", "security", "hall"):
        print("  %-18s %d" % (name, len(lib.get(name, []))))


if __name__ == "__main__":
    main()
