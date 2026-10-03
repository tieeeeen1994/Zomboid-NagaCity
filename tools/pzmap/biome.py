"""maps/biomemap_X_Y.png: 256 x 256, one pixel per square. The game decodes it to RGBA (`BiomeRaster`) and reads
band 0 (red) as the biome and band 1 (green) as the zone, both looked up in BiomeMapConfig.lua. Raven Creek writes
RGB with R = G = B; vanilla uses palette PNGs (decoded to the same colours)."""
import numpy as np
from PIL import Image

WATER = 0
FORAGING_NAV = 64
DEEP_FOREST_RANDOM = 96
TRAILER_PARK = 102
TOWN = 115
FARM = 128
FARMLAND = 141
PH_FOREST = 153
PR_FOREST = 179
FARM_MIX_FOREST = 192
FARM_FOREST = 204
BIRCH_FOREST = 217
BIRCH_MIX_FOREST = 230
ORGANIC_FOREST = 243
DIRT = 254  # spawns nothing
PRIMARY_FOREST = 255


def save(path, values):
    """values: 256 x 256 uint8 array indexed [y, x]."""
    a = np.asarray(values, dtype=np.uint8)
    assert a.shape == (256, 256)
    Image.fromarray(np.dstack([a, a, a]), "RGB").save(path, optimize=True)


def load(path):
    """[y, x] array of band 0 (biome)."""
    return np.asarray(Image.open(path).convert("RGB"))[:, :, 0].copy()
