"""Shapely geometry -> per-square masks. A square (x, y) is covered when its centre (x + 0.5, y + 0.5) is inside."""
import numpy as np
from PIL import Image, ImageDraw
from shapely.geometry import MultiPolygon, Polygon


def polygons(geom):
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return list(geom.geoms)
    return [p for g in getattr(geom, "geoms", []) for p in polygons(g)]


def mask(geoms, ox, oy, w=256, h=256):
    """[y, x] bool array for the w x h squares starting at (ox, oy)."""
    img = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(img)
    for g in geoms:
        for poly in polygons(g):
            ext = [(x - ox - 0.5, y - oy - 0.5) for x, y in poly.exterior.coords]
            if len(ext) >= 3:
                d.polygon(ext, fill=1)
            for ring in poly.interiors:
                hole = [(x - ox - 0.5, y - oy - 0.5) for x, y in ring.coords]
                if len(hole) >= 3:
                    d.polygon(hole, fill=0)
    return np.asarray(img, dtype=bool)
