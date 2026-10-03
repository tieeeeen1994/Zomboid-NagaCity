"""Top-down preview of generated cells, read back from the map folder: one pixel per square, coloured by its tiles.
Squares with no lot data (filled by worldgen in game) show their biome colour, darkened.

    tools/.venv/Scripts/python.exe tools/preview.py x0 y0 x1 y1 [out.png] [--scale N]   (PZ cells, inclusive)"""
import os
import sys

import numpy as np
from PIL import Image

import config
from pzmap import biome
from pzmap.lotfiles import CELL, Cell

STREET_FAMILY = {80: (60, 60, 64), 96: (105, 105, 105), 48: (200, 190, 160), 16: (140, 110, 70)}
COLORS = [
    ("street_trafficlines_01_1", (240, 200, 40)), ("street_trafficlines_01_2", (240, 200, 40)),
    ("street_trafficlines_01_", (235, 235, 235)), ("street_curbs_01_", (225, 220, 205)),
    ("floors_exterior_tilesandstone", (190, 185, 170)), ("floors_exterior_street", (170, 170, 165)),
    ("blends_natural_02_", (60, 120, 190)), ("vegetation", (60, 100, 40)), ("e_", (50, 90, 40)),
]
BIOME = {biome.TOWN: (150, 150, 130), biome.FARMLAND: (170, 165, 100), biome.FARM_MIX_FOREST: (70, 110, 60),
         biome.WATER: (60, 110, 170), biome.PRIMARY_FOREST: (40, 80, 40)}


def color(names):
    for name in reversed(names[1:]):  # markings and curbs over the base tile; grass edges are ignored
        for prefix, c in COLORS:
            if name.startswith(prefix):
                return c
    base = names[0]
    if base.startswith("blends_street_01_"):
        return STREET_FAMILY.get(int(base.rsplit("_", 1)[1]) // 16 * 16, (200, 60, 200))
    if base.startswith("blends_natural_01_"):
        return (110, 140, 70)
    for prefix, c in COLORS:
        if base.startswith(prefix):
            return c
    return (200, 60, 200)


def render(x0, y0, x1, y1, scale=1):
    w, h = (x1 - x0 + 1) * CELL, (y1 - y0 + 1) * CELL
    img = np.zeros((h, w, 3), dtype=np.uint8)
    for cx in range(x0, x1 + 1):
        for cy in range(y0, y1 + 1):
            ox, oy = (cx - x0) * CELL, (cy - y0) * CELL
            bpath = os.path.join(config.MAP_DIR, "maps", "biomemap_%d_%d.png" % (cx, cy))
            if os.path.exists(bpath):
                b = biome.load(bpath)
                for value, c in BIOME.items():
                    img[oy:oy + CELL, ox:ox + CELL][b == value] = [v * 0.7 for v in c]
            mine = os.path.exists(os.path.join(config.MAP_DIR, "%d_%d.lotheader" % (cx, cy)))
            folder = config.MAP_DIR if mine else config.VANILLA_MAP
            if not os.path.exists(os.path.join(folder, "%d_%d.lotheader" % (cx, cy))):
                continue
            cell = Cell.load(folder, cx, cy)
            for (x, y, z), ids in cell.squares.items():
                if z == 0:
                    img[oy + y, ox + x] = color([cell.tiles[i] for i in ids])
    out = Image.fromarray(img)
    if scale != 1:
        out = out.resize((w * scale, h * scale), Image.NEAREST)
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    scale = int(sys.argv[sys.argv.index("--scale") + 1]) if "--scale" in sys.argv else 1
    if "--scale" in sys.argv:
        args.remove(str(scale))
    x0, y0, x1, y1 = map(int, args[:4])
    path = args[4] if len(args) > 4 else os.path.join(config.OUT, "preview_%d_%d_%d_%d.png" % (x0, y0, x1, y1))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    render(x0, y0, x1, y1, scale).save(path)
    print(path)


if __name__ == "__main__":
    main()
