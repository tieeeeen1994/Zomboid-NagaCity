"""data/naga.json -> projected shapely geometry (PZ absolute tile coordinates)."""
import json

from shapely.geometry import LineString, Polygon, box
from shapely.ops import polygonize, unary_union
from shapely.validation import make_valid

import config

# Carriageway width in tiles (1 tile = 1 m) and sidewalk width per side.
ROAD_WIDTH = {"trunk": 14, "primary": 12, "secondary": 10, "tertiary": 8, "residential": 6, "unclassified": 6,
              "living_street": 6, "service": 4, "road": 6, "track": 4, "pedestrian": 4}  # even: edges on square lines
LINK_WIDTH = 6
SIDEWALK = {"trunk": 2, "primary": 2, "secondary": 2, "tertiary": 2}
CENTER_LINE = {"trunk", "primary", "secondary"}
DIRT = {"track"}
PAVED_FOOT = {"pedestrian"}

WATERWAY_WIDTH = {"river": 20, "canal": 6, "stream": 4, "drain": 2, "ditch": 2}

TOWN_LANDUSE = {"residential", "commercial", "retail", "industrial", "institutional", "education", "religious",
                "construction", "garages", "railway", "military"}
FARM_LANDUSE = {"farmland", "meadow", "grass", "farmyard", "orchard", "plant_nursery", "village_green", "allotments",
                "greenfield", "aquaculture"}
FOREST = {"forest"}
FOREST_NATURAL = {"wood", "scrub"}


class Road:
    __slots__ = ("line", "cls", "width", "sidewalk", "center_line", "surface", "tags", "osm_id", "nodes")

    def __init__(self, line, cls, width, sidewalk, center_line, surface, tags, osm_id, nodes=None):
        self.line, self.cls, self.width, self.sidewalk = line, cls, width, sidewalk
        self.center_line, self.surface, self.tags, self.osm_id = center_line, surface, tags, osm_id
        self.nodes = nodes  # OSM node ids, one per point of line (None for area roads)


def _pts(geometry):
    return [config.project(g["lat"], g["lon"]) for g in geometry if g is not None]


def _closed_polygon(pts):
    if len(pts) >= 4 and pts[0] == pts[-1]:
        return make_valid(Polygon(pts))
    return None


def _relation_polygon(rel):
    outer, inner = [], []
    for m in rel.get("members", []):
        if m.get("type") != "way" or "geometry" not in m:
            continue
        pts = _pts(m["geometry"])
        if len(pts) >= 2:
            (inner if m.get("role") == "inner" else outer).append(LineString(pts))
    shell = unary_union(list(polygonize(unary_union(outer)))) if outer else None
    if shell is None or shell.is_empty:
        return None
    if inner:
        holes = unary_union(list(polygonize(unary_union(inner))))
        shell = shell.difference(holes)
    return make_valid(shell)


def load(clip=None):
    """clip: (x0, y0, x1, y1) in PZ tiles; geometry outside is dropped (roads are kept whole if they touch it)."""
    data = json.load(open(config.OSM_FILE, encoding="utf-8"))
    area = box(*clip) if clip else None
    out = {"roads": [], "water": [], "waterways": [], "town": [], "farm": [], "forest": [], "buildings": [],
           "boundary": None}

    def keep(g):
        return g is not None and not g.is_empty and (area is None or g.intersects(area))

    for e in data["elements"]:
        tags = e.get("tags", {})
        if e["type"] == "relation":
            if e["id"] == config.OSM_RELATION:
                out["boundary"] = _relation_polygon(e)
                continue
            if tags.get("type") != "multipolygon":
                continue
            poly = _relation_polygon(e)
            if not keep(poly):
                continue
            if tags.get("natural") == "water" or tags.get("water"):
                out["water"].append(poly)
            elif tags.get("landuse") in TOWN_LANDUSE:
                out["town"].append(poly)
            elif tags.get("landuse") in FARM_LANDUSE:
                out["farm"].append(poly)
            elif tags.get("landuse") in FOREST or tags.get("natural") in FOREST_NATURAL:
                out["forest"].append(poly)
            elif "building" in tags:
                out["buildings"].append((poly, tags, e["id"]))
            continue
        if e["type"] != "way" or "geometry" not in e:
            continue
        pts = _pts(e["geometry"])
        if len(pts) < 2:
            continue
        hw = tags.get("highway")
        if hw:
            cls = hw.replace("_link", "")
            if tags.get("area") == "yes":
                poly = _closed_polygon(pts)
                if keep(poly) and cls in PAVED_FOOT | {"service", "residential", "unclassified"}:
                    out["roads"].append(Road(poly, cls, 0, 0, False, "sidewalk" if cls in PAVED_FOOT else "asphalt",
                                             tags, e["id"]))
                continue
            if cls not in ROAD_WIDTH or tags.get("access") == "no" and cls == "service":
                continue
            pairs = [(n, config.project(g["lat"], g["lon"])) for n, g in zip(e.get("nodes", []), e["geometry"])
                     if g is not None]
            if len(pairs) < 2:
                continue
            line = LineString([p for _, p in pairs])
            if not keep(line):
                continue
            width = LINK_WIDTH if hw.endswith("_link") else ROAD_WIDTH[cls]
            lanes = tags.get("lanes", "")
            if lanes.isdigit() and not hw.endswith("_link"):
                width = max(width, min(int(lanes) * 3 + 2, 18) // 2 * 2)
            surface = "dirt" if cls in DIRT or tags.get("surface") in ("dirt", "ground", "gravel", "unpaved", "earth") \
                else "sidewalk" if cls in PAVED_FOOT else "asphalt"
            center = cls in CENTER_LINE and tags.get("oneway") not in ("yes", "-1") and width >= 8
            out["roads"].append(Road(line, cls, width, SIDEWALK.get(cls, 0), center, surface, tags, e["id"],
                                     [n for n, _ in pairs]))
            continue
        if "building" in tags:
            poly = _closed_polygon(pts)
            if keep(poly):
                out["buildings"].append((poly, tags, e["id"]))
            continue
        ww = tags.get("waterway")
        if tags.get("natural") == "water" or ww == "riverbank" or tags.get("landuse") in ("reservoir", "basin"):
            poly = _closed_polygon(pts)
            if keep(poly):
                out["water"].append(poly)
            continue
        if ww in WATERWAY_WIDTH and tags.get("tunnel") not in ("yes", "culvert"):
            line = LineString(pts)
            if keep(line):
                w = tags.get("width", "")
                try:
                    width = float(w)
                except ValueError:
                    width = WATERWAY_WIDTH[ww]
                out["waterways"].append((line, width, tags, e["id"]))
            continue
        lu, nat = tags.get("landuse"), tags.get("natural")
        poly = _closed_polygon(pts) if (lu or nat) else None
        if not keep(poly):
            continue
        if lu in TOWN_LANDUSE:
            out["town"].append(poly)
        elif lu in FARM_LANDUSE:
            out["farm"].append(poly)
        elif lu in FOREST or nat in FOREST_NATURAL:
            out["forest"].append(poly)
    return out
