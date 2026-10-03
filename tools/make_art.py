"""Poster (512), icon (128) and Workshop preview (512): Naga's streets and rivers drawn from data/naga.json."""
import json
import os

from PIL import Image, ImageDraw, ImageFont

import config

ROOT = os.path.join(config.TOOLS, "..")
MOD = os.path.join(ROOT, "Contents", "mods", config.MOD_ID, "42")

BG = (24, 27, 31)
WATER = (64, 120, 190)
ROAD = {"trunk": ((232, 92, 60), 4), "primary": ((232, 140, 60), 3.5), "secondary": ((226, 190, 90), 3),
        "tertiary": ((200, 200, 200), 2)}
MINOR = ((120, 124, 130), 1)
BUILDING = (70, 74, 80)

# Downtown and the river, in projected metres around Plaza Rizal (before the PZ offset).
VIEW = (-1700, -2900, 2900, 1700)


def local(g):
    x, y = config.project(g["lat"], g["lon"])
    return x - config.OFFSET_X, y - config.OFFSET_Y


def render(size, view, minor=True, buildings=True, scale=4):
    big = size * scale
    x0, y0, x1, y1 = view
    k = big / max(x1 - x0, y1 - y0)
    im = Image.new("RGB", (big, big), BG)
    d = ImageDraw.Draw(im)
    elements = json.load(open(config.OSM_FILE, encoding="utf-8"))["elements"]

    def pts(e):
        return [((x - x0) * k, (y - y0) * k) for x, y in (local(g) for g in e["geometry"])]

    ways = [e for e in elements if e["type"] == "way" and "geometry" in e]
    for e in ways:
        t = e.get("tags", {})
        if buildings and "building" in t and len(e["geometry"]) > 2:
            d.polygon(pts(e), fill=BUILDING)
    for e in ways:
        t = e.get("tags", {})
        if t.get("natural") == "water" or t.get("water") or t.get("waterway") == "riverbank":
            if len(e["geometry"]) > 2:
                d.polygon(pts(e), fill=WATER)
        elif t.get("waterway") in ("river", "stream", "canal"):
            d.line(pts(e), fill=WATER, width=int(3 * scale))
    order = ["minor", "tertiary", "secondary", "primary", "trunk"]
    for cls in order:
        for e in ways:
            h = e.get("tags", {}).get("highway", "").replace("_link", "")
            if cls == "minor":
                if not minor or h not in ("residential", "unclassified", "service", "living_street"):
                    continue
                color, w = MINOR
            elif h != cls:
                continue
            else:
                color, w = ROAD[cls]
            d.line(pts(e), fill=color, width=max(1, int(w * scale * size / 512)))
    return im.resize((size, size), Image.LANCZOS)


def title(im, text, sub):
    d = ImageDraw.Draw(im)
    try:
        f1 = ImageFont.truetype("arialbd.ttf", 54)
        f2 = ImageFont.truetype("arial.ttf", 24)
    except OSError:
        f1 = f2 = ImageFont.load_default()
    h = 104
    band = Image.new("RGBA", (im.width, h), (0, 0, 0, 170))
    im.paste(band, (0, im.height - h), band)
    d.text((20, im.height - h + 10), text, font=f1, fill=(245, 245, 240))
    d.text((22, im.height - h + 70), sub, font=f2, fill=(200, 200, 195))
    return im


def main():
    poster = title(render(512, VIEW), "NAGA CITY", "Camarines Sur, Philippines")
    poster.save(os.path.join(MOD, "poster.png"))
    poster.save(os.path.join(ROOT, "preview.png"))
    render(128, (-1100, -1500, 1100, 700), minor=False, buildings=False, scale=6).save(os.path.join(MOD, "icon.png"))
    print("poster.png, icon.png, preview.png written")


if __name__ == "__main__":
    main()
