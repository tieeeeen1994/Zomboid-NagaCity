"""Shared constants for the Naga City generator. See CLAUDE.md for why each value is what it is."""
import math
import os

TOOLS = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(TOOLS, "data")
OUT = os.path.join(TOOLS, "out")

MOD_ID = "NagaCity"
MAP_NAME = "Naga City, PH"
MOD_MEDIA = os.path.join(TOOLS, "..", "Contents", "mods", MOD_ID, "common", "media")  # maps must be under common/ (MapGroups)
MAP_DIR = os.path.join(MOD_MEDIA, "maps", MAP_NAME)

GAME = r"C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid"
VANILLA_MAP = os.path.join(GAME, "media", "maps", "Muldraugh, KY")
WORKSHOP = r"C:\Program Files (x86)\Steam\steamapps\workshop\content\108600"
RAVEN_CREEK_MAP = os.path.join(WORKSHOP, "3484263516", "mods", "Raven Creek B42", "common", "media", "maps", "Raven Creek B42")

OSM_RELATION = 3084673
OSM_FILE = os.path.join(DATA, "naga.json")

CELL = 256
CHUNK = 8
CHUNKS_PER_CELL = 32

# Projection: local equirectangular around Plaza Rizal, 1 tile = 1 m, +x = east, +y = south (PZ north is -y).
LAT0, LON0 = 13.6236, 123.1875
KX = math.cos(math.radians(LAT0)) * 111320.0
KY = 110574.0

# Placement (tentative until the coverage is settled): Naga cell (-7, -13) lands on PZ cell (26, 63),
# east of Raven Creek and south of the vanilla edge (vanilla lots stop at cell row 62).
OFFSET_X = (26 - -7) * CELL
OFFSET_Y = (63 - -13) * CELL

# Naga's cells (PZ cell coordinates, inclusive): Naga-local cells -7..24 x -13..9, the city from the Bicol River to
# Carolina and Pacol. OSM data reaches further (roads into the hills, Panicuason); it is clipped to this box.
COVER = (26, 63, 57, 85)

# Raven Creek road south-east of its first gas station: ends at x 6599, rows 15396..15411 (16 wide, 4 lanes, double
# yellow on the boundary y = 15404, dashed white on y = 15400 and y = 15408).
# x 6600..6655 is inside Raven Creek's cell 25 but empty in its lotpack (biome 255, deep forest): paved by
# media/lua/server/NagaCity_RavenCreekLink.lua.
RC_LINK_END_X = 6599
RC_LINK_Y0, RC_LINK_Y1 = 15396, 15411
RC_LINK_CENTER = 15404

# Connector: east along Raven Creek's road (y = RC_LINK_CENTER), a square corner, then south to the north end of
# Calabanga Road (OSM way 733429690, secondary; about 7752,16341 before straightening, generate.py uses the
# straightened node). Vanilla cells it crosses are copied and the road laid over them.
CALABANGA_WAY = 733429690
CONNECTOR_WIDTH = 16
CONNECTOR_VANILLA_CELLS = [(26, 60), (27, 60), (28, 60), (29, 60), (30, 60), (30, 61), (30, 62)]

# Test spawn: the road square nearest Plaza Rizal.
PLAZA_RIZAL = (13.6236, 123.1875)


def project(lat, lon):
    """OSM lat/lon -> PZ absolute tile coordinates (floats)."""
    return ((lon - LON0) * KX + OFFSET_X, (LAT0 - lat) * KY + OFFSET_Y)
