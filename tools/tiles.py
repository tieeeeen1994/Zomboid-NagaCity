"""Tile choices, the way vanilla lays its streets (see CLAUDE.md "Tiles"). Variation is a hash of the square, so a rerun
writes the same tiles."""

ASPHALT_MAJOR = ["blends_street_01_80", "blends_street_01_85", "blends_street_01_86", "blends_street_01_87"]
ASPHALT_MINOR = ["blends_street_01_96", "blends_street_01_101", "blends_street_01_102", "blends_street_01_103"]
SIDEWALK = ["blends_street_01_48", "blends_street_01_53", "blends_street_01_54", "blends_street_01_55"]
DIRT_ROAD = ["blends_street_01_16", "blends_street_01_21"]
WATER = ["blends_natural_02_0", "blends_natural_02_5", "blends_natural_02_6", "blends_natural_02_7"]
# Plain green grass, under half tiles: vanilla's half tiles (street and water family base + 1..4) are transparent on
# their other half.
GRASS = ["blends_natural_01_16", "blends_natural_01_21", "blends_natural_01_22", "blends_natural_01_23"]

# street_trafficlines_01: white 0 W, 2 N, 4 E, 6 S edge; yellow = white + 16 (odd numbers are corners).
WHITE = {"W": "street_trafficlines_01_0", "N": "street_trafficlines_01_2", "E": "street_trafficlines_01_4",
         "S": "street_trafficlines_01_6"}
YELLOW = {"W": "street_trafficlines_01_16", "N": "street_trafficlines_01_18", "E": "street_trafficlines_01_20",
          "S": "street_trafficlines_01_22"}

# Curbs sit on a square's south or east edge: a sidewalk square with road south of it gets 8, a road square with
# sidewalk south of it 10; east: 9 on the sidewalk square, 11 on the road square (vanilla town streets).
CURB_SIDEWALK_S, CURB_ROAD_S = "street_curbs_01_8", "street_curbs_01_10"
CURB_SIDEWALK_E, CURB_ROAD_E = "street_curbs_01_9", "street_curbs_01_11"

# Green grass edge drawn over a street square on the side where grass is (blends_natural_01, two variants each).
GRASS_EDGE = {"N": ["blends_natural_01_24", "blends_natural_01_28"], "W": ["blends_natural_01_25", "blends_natural_01_29"],
              "E": ["blends_natural_01_26", "blends_natural_01_30"], "S": ["blends_natural_01_27", "blends_natural_01_31"]}
# Raven Creek's road edge rows (north row, south row) use these.
EDGE_N = ["blends_natural_01_24", "blends_natural_01_28", "blends_natural_01_40", "blends_natural_01_44"]
EDGE_S = ["blends_natural_01_27", "blends_natural_01_31", "blends_natural_01_43", "blends_natural_01_47"]


def pick(options, x, y, salt=0):
    h = (x * 73856093) ^ (y * 19349663) ^ (salt * 83492791)
    return options[(h & 0x7FFFFFFF) % len(options)]


def dash_on(along):
    """Raven Creek's lane dashes: 2 on, 2 off, on where the coordinate mod 4 is 0 or 1."""
    return along % 4 in (0, 1)
