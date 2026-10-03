"""Which sprites hang on which wall, from the game's media/newtiledefinitions.tiles.txt (text copy of the tile
definitions): the `attachedN / W / E / S / NW / SE` properties (3,167 / 3,023 / 182 / 123 / 171 / 59 sprites in 42.20).
Cached in data/attached.json."""
import json
import os
import re

import config

SRC = os.path.join(config.GAME, "media", "newtiledefinitions.tiles.txt")
CACHE = os.path.join(config.DATA, "attached.json")
FLAGS = ("attachedN", "attachedW", "attachedE", "attachedS", "attachedNW", "attachedSE")
_attached = None


def attached():
    """{sprite name: "N" | "W" | "E" | "S" | "NW" | "SE"}"""
    global _attached
    if _attached is not None:
        return _attached
    if os.path.exists(CACHE) and os.path.getmtime(CACHE) >= os.path.getmtime(SRC):
        _attached = json.load(open(CACHE))
        return _attached
    out, name = {}, None
    comment = re.compile(r"^\s*//\s*(\S+)\s*$")
    for line in open(SRC, encoding="utf-8", errors="replace"):
        m = comment.match(line)
        if m:
            name = m.group(1)
            continue
        s = line.strip()
        for f in FLAGS:
            if name and (s == f + " =" or s.startswith(f + " =")):
                out[name] = f[len("attached"):]
    os.makedirs(config.DATA, exist_ok=True)
    json.dump(out, open(CACHE, "w"))
    _attached = out
    return out
