"""Isometric preview with the game's own sprites, read back from the generated map folder: what a square looks like
in game, minus lighting. Squares with no lot data get plain grass (worldgen fills them in game).

    tools/.venv/Scripts/python.exe tools/iso_preview.py x y size [out.png] [--z=N]   (top corner; levels up to N)"""
import os
import sys

from PIL import Image

import config
from pzmap import textures
from pzmap.lotfiles import CELL, Cell

GRASS = "blends_natural_01_16"


def render(x0, y0, size, scale=0.5, zmax=0, ground_grass=True, folder=None):
    """zmax: highest level drawn (cut away above it, like the game's cutaway)."""
    cells = {}

    def square(x, y, z):
        key = (x // CELL, y // CELL)
        if key not in cells:
            src = folder or config.MAP_DIR
            path = os.path.join(src, "%d_%d.lotheader" % key)
            cells[key] = Cell.load(src, *key) if os.path.exists(path) else None
        c = cells[key]
        return c.get_square(x - key[0] * CELL, y - key[1] * CELL, z) if c else None

    lift = 192
    w, h = size * 128, size * 64 + 256 + lift * zmax
    img = Image.new("RGBA", (w, h), (30, 30, 30, 255))
    cache = {}
    for z in range(zmax + 1):
        for s in range(2 * size - 1):
            for dx in range(size):
                dy = s - dx
                if not 0 <= dy < size:
                    continue
                names = square(x0 + dx, y0 + dy, z) or ([GRASS] if z == 0 and ground_grass else [])
                sx = (dx - dy) * 64 + w // 2 - 64
                sy = (dx + dy) * 32 + lift * (zmax - z)
                for n in names:
                    if n not in cache:
                        cache[n] = textures.sprite(n)
                    if cache[n] is not None:
                        img.alpha_composite(cache[n], (sx, sy))
    return img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--z=")]
    zmax = int(next((a[4:] for a in sys.argv[1:] if a.startswith("--z=")), 0))
    x, y, size = map(int, args[:3])
    out = args[3] if len(args) > 3 else os.path.join(config.OUT, "iso_%d_%d_%d_z%d.png" % (x, y, size, zmax))
    render(x, y, size, zmax=zmax).save(out)
    print(out)


if __name__ == "__main__":
    main()
