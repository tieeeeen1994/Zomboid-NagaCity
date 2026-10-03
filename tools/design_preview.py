"""Render a hand-drawn design on its own (no map files): the design placed facing each street direction on a patch of
grass with a road in front, drawn with the game's sprites.

    tools/.venv/Scripts/python.exe tools/design_preview.py DESIGN_NAME [use] [--z=N] [--facing=SNEW]"""
import sys

from PIL import Image

import designs
from buildkit import Canvas
from pzmap import textures

ROAD = "blends_street_01_80"
GRASS = "blends_natural_01_16"


def render_canvas(canvas, x0, y0, size, zmax, scale=0.5):
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
                names = canvas.squares.get((x0 + dx, y0 + dy, z)) or ([GRASS] if z == 0 else [])
                sx, sy = (dx - dy) * 64 + w // 2 - 64, (dx + dy) * 32 + lift * (zmax - z)
                for n in names:
                    if n not in cache:
                        cache[n] = textures.sprite(n)
                    if cache[n] is not None:
                        img.alpha_composite(cache[n], (sx, sy))
    return img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)


def preview(design, use, facing="S", zmax=1, seed=1):
    c = Canvas()
    pad = 4
    b = designs.place(design, pad, pad, facing, use, seed=seed)
    bw = max(len(r) for r in b.floors[0])
    bh = len(b.floors[0])
    size = max(bw, bh) + 2 * pad + 4
    for y in range(size):
        for x in range(size):
            road = {"S": y >= pad + bh + 1, "N": y < pad - 1, "E": x >= pad + bw + 1, "W": x < pad - 1}[facing]
            c.ground(x, y, [ROAD if road else GRASS])
    b.draw(c)
    return render_canvas(c, 0, 0, size, zmax)


def main():
    name = sys.argv[1]
    use = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else "generalstore"
    zmax = int(next((a[4:] for a in sys.argv if a.startswith("--z=")), 1))
    facings = next((a[9:] for a in sys.argv if a.startswith("--facing=")), "S")
    design = getattr(designs, name)
    for f in facings:
        out = "out/design_%s_%s_z%d.png" % (name, f, zmax)
        preview(design, use, f, zmax).save(out)
        print(out)


if __name__ == "__main__":
    main()
