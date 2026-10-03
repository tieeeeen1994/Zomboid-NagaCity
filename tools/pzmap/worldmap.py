"""worldmap.xml (the in-game map) reader and writer.

Cells in this file are 300 tiles even in B42 (vanilla and Raven Creek): absolute = cell * 300 + point. The game loads
`worldmap.xml.bin` when it exists, else parses the XML (`WorldMapDataAssetManager`). Every vanilla feature the style
draws is a Polygon; extra `<coordinates>` blocks are holes. Properties the style knows (ISMapDefinitions.lua):
natural=forest, water=river, highway=trail|tertiary|secondary|primary, railway=*, building=yes|Residential|
CommunityServices|Hospitality|Industrial|Medical|RestaurantsAndEntertainment|RetailAndCommercial; buildings may also
carry RoomTone."""
import math
import xml.etree.ElementTree as ET
from xml.sax.saxutils import quoteattr

from shapely.geometry import MultiPolygon, Polygon, box
from shapely.geometry.polygon import orient

WM_CELL = 300


def read_features(path):
    """[(properties dict, [rings of absolute (x, y)])]"""
    out = []
    for _, cell in ET.iterparse(path):
        if cell.tag != "cell":
            continue
        cx, cy = int(cell.get("x")), int(cell.get("y"))
        for feature in cell.findall("feature"):
            props = {p.get("name"): p.get("value") for p in feature.iter("property")}
            rings = [[(cx * WM_CELL + int(pt.get("x")), cy * WM_CELL + int(pt.get("y"))) for pt in co.findall("point")]
                     for co in feature.iter("coordinates")]
            out.append((props, rings))
        cell.clear()
    return out


class WorldMapWriter:
    def __init__(self):
        self.cells = {}  # (cx, cy) -> [(props, polygon in cell-local coords)]

    def add(self, props, geometry):
        """geometry: shapely Polygon / MultiPolygon in absolute tile coordinates; clipped into 300-tile cells."""
        if geometry.is_empty:
            return
        x0, y0, x1, y1 = geometry.bounds
        for cx in range(math.floor(x0 / WM_CELL), math.floor(x1 / WM_CELL) + 1):
            for cy in range(math.floor(y0 / WM_CELL), math.floor(y1 / WM_CELL) + 1):
                ox, oy = cx * WM_CELL, cy * WM_CELL
                part = geometry.intersection(box(ox, oy, ox + WM_CELL, oy + WM_CELL))
                for poly in _polygons(part):
                    local = Polygon([(x - ox, y - oy) for x, y in poly.exterior.coords],
                                    [[(x - ox, y - oy) for x, y in r.coords] for r in poly.interiors])
                    self.cells.setdefault((cx, cy), []).append((props, local))

    def to_xml(self):
        lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<world version="1.0">']
        for (cx, cy) in sorted(self.cells):
            lines.append(' <cell x="%d" y="%d">' % (cx, cy))
            for props, poly in self.cells[(cx, cy)]:
                rings = [_ring(poly.exterior.coords)] + [_ring(r.coords) for r in poly.interiors]
                rings = [r for r in rings if len(r) >= 3]
                if not rings:
                    continue
                lines.append('  <feature>')
                lines.append('   <geometry type="Polygon">')
                for ring in rings:
                    lines.append('    <coordinates>')
                    lines.extend('     <point x="%d" y="%d"/>' % p for p in ring)
                    lines.append('    </coordinates>')
                lines.append('   </geometry>')
                lines.append('   <properties>')
                for k, v in props.items():
                    lines.append('    <property name=%s value=%s/>' % (quoteattr(k), quoteattr(v)))
                lines.append('   </properties>')
                lines.append('  </feature>')
            lines.append(' </cell>')
        lines.append('</world>')
        return "\n".join(lines) + "\n"

    def save(self, path):
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(self.to_xml())


def _polygons(geom):
    if geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [orient(geom)]
    if isinstance(geom, MultiPolygon):
        return [orient(g) for g in geom.geoms]
    return [g for sub in getattr(geom, "geoms", []) for g in _polygons(sub)]


def _ring(coords):
    """Integer points, closing point dropped, consecutive duplicates removed (vanilla rings are not closed)."""
    out = []
    for x, y in list(coords)[:-1]:
        p = (int(round(x)), int(round(y)))
        if not out or out[-1] != p:
            out.append(p)
    if len(out) > 1 and out[0] == out[-1]:
        out.pop()
    return out
