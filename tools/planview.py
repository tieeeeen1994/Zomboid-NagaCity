"""Top-down drawing of the road plan (no map files needed): carriageways to scale, coloured by class, short runs (the
jagged bits roadtidy.py could not remove) outlined in red.

    tools/.venv/Scripts/python.exe tools/planview.py x0 y0 x1 y1 [px per tile] [out.png]"""
import os
import sys

from PIL import Image, ImageDraw

import config
import roadplan
import roadtidy

COLOR = {"trunk": (40, 40, 48), "primary": (55, 55, 62), "secondary": (70, 70, 78), "tertiary": (105, 105, 110),
         "residential": (140, 140, 140), "unclassified": (140, 140, 140), "living_street": (140, 140, 140),
         "road": (140, 140, 140), "service": (170, 165, 155), "track": (150, 110, 70), "pedestrian": (200, 190, 160)}


def render(x0, y0, x1, y1, scale=3, plan=None):
    plan = plan or roadplan.load()
    img = Image.new("RGB", ((x1 - x0) * scale, (y1 - y0) * scale), (96, 112, 72))
    draw = ImageDraw.Draw(img)
    pieces, roads = roadplan.pieces(plan)
    T = lambda p: ((p[0] - x0) * scale, (p[1] - y0) * scale)
    short = []
    for p in sorted(pieces, key=lambda p: roads[p.road].width):
        r = roads[p.road]
        if max(p.x1, p.x0) < x0 - 20 or min(p.x0, p.x1) > x1 + 20 or max(p.y0, p.y1) < y0 - 20 or min(p.y0, p.y1) > y1 + 20:
            continue
        draw.line([T(p.a), T(p.b)], fill=COLOR.get(r.cls, (140, 140, 140)), width=max(1, r.width * scale))
        if roadtidy._len(p.a, p.b) <= roadtidy.JOG:
            short.append(p)
    for p in short:
        draw.line([T(p.a), T(p.b)], fill=(230, 40, 40), width=max(1, scale))
    for n, (x, y) in plan["nodes"].items():
        if x0 <= x < x1 and y0 <= y < y1 and not n.startswith("b"):
            cx, cy = T((x, y))
            draw.rectangle([cx - 1, cy - 1, cx + 1, cy + 1], fill=(250, 220, 60))
    return img


def main():
    x0, y0, x1, y1 = map(int, sys.argv[1:5])
    scale = int(sys.argv[5]) if len(sys.argv) > 5 else 3
    out = sys.argv[6] if len(sys.argv) > 6 else os.path.join(config.OUT, "plan_%d_%d.png" % (x0, y0))
    render(x0, y0, x1, y1, scale).save(out)
    print(out)


if __name__ == "__main__":
    main()
