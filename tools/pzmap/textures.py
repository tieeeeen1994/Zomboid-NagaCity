"""Tile sprites from the game's texture packs, for previews and for picking tiles by eye.

A .pack is a run of int32-length-prefixed entry names, each followed by eight int32s (x, y, w, h, offsetX, offsetY,
originalW, originalH), then once per page a plain PNG of the sheet; an entry belongs to the first PNG that starts after
it (same reader as TienActionableHotbar/scripts/make_art.py). Floor tiles are in Tiles2x.floor.pack, everything else in
Tiles2x.pack. A 2x tile is 128 x 256, its floor diamond the bottom 128 x 64."""
import io
import os
import re
import struct

from PIL import Image

import config

PACK_DIR = os.path.join(config.GAME, "media", "texturepacks")
PACKS = ["Tiles2x.floor.pack", "Tiles2x.pack"]
_packs = {}


def _index(name):
    if name in _packs:
        return _packs[name]
    blob = open(os.path.join(PACK_DIR, name), "rb").read()
    pages = list(zip([m.start() for m in re.finditer(rb"\x89PNG\r\n\x1a\n", blob)],
                     [m.start() + 12 for m in re.finditer(rb"IEND\xaeB`\x82", blob)]))
    starts = [p[0] for p in pages]
    index = {}
    for match in re.finditer(rb"[A-Za-z0-9_]{3,80}", blob):
        at, run = match.start(), match.group()
        if at < 4:
            continue
        length = struct.unpack_from("<i", blob, at - 4)[0]
        if not 3 <= length <= len(run):
            continue
        try:
            rect = struct.unpack_from("<8i", blob, at + length)
        except struct.error:
            continue
        import bisect
        page = bisect.bisect_right(starts, at)
        if page < len(pages):
            index[run[:length].decode()] = (page,) + rect
    _packs[name] = {"blob": blob, "pages": pages, "sheets": {}, "index": index}
    return _packs[name]


def sprite(name):
    """RGBA image of a tile at 2x (originalW x originalH, normally 128 x 256), or None."""
    for pack_name in PACKS:
        pack = _index(pack_name)
        entry = pack["index"].get(name)
        if entry is None:
            continue
        page, x, y, w, h, ox, oy, ow, oh = entry
        if page not in pack["sheets"]:
            start, end = pack["pages"][page]
            pack["sheets"][page] = Image.open(io.BytesIO(pack["blob"][start:end])).convert("RGBA")
        img = Image.new("RGBA", (ow, oh), (0, 0, 0, 0))
        img.paste(pack["sheets"][page].crop((x, y, x + w, y + h)), (ox, oy))
        return img
    return None


def names(prefix):
    out = set()
    for pack_name in PACKS:
        out.update(n for n in _index(pack_name)["index"] if n.startswith(prefix))
    return sorted(out, key=lambda n: (n.rsplit("_", 1)[0], int(n.rsplit("_", 1)[1]) if n.rsplit("_", 1)[1].isdigit() else 0))


def contact_sheet(tile_names, columns=16, scale=0.5):
    from PIL import ImageDraw
    w, h = int(128 * scale), int(256 * scale)
    rows = (len(tile_names) + columns - 1) // columns
    sheet = Image.new("RGBA", (columns * w, rows * (h + 12)), (40, 40, 40, 255))
    d = ImageDraw.Draw(sheet)
    for i, n in enumerate(tile_names):
        s = sprite(n)
        x, y = (i % columns) * w, (i // columns) * (h + 12)
        if s is not None:
            s = s.resize((w, h))
            sheet.alpha_composite(s, (x, y))
        d.text((x + 2, y + h), n.rsplit("_", 1)[1], fill=(255, 255, 0, 255))
    return sheet
