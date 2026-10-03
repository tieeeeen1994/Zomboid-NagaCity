"""Checks for the writers that cannot be byte-identical: worldmap.xml (re-emitted from Raven Creek's, compared by area per
property) and biome PNGs (values must survive a save and load)."""
import collections
import os
import tempfile

import numpy as np
from shapely.geometry import Polygon
from shapely.validation import make_valid

import config
from pzmap import biome
from pzmap.worldmap import WorldMapWriter, read_features


def areas(features):
    out = collections.Counter()
    for props, rings in features:
        if not rings or len(rings[0]) < 3:
            continue
        poly = make_valid(Polygon(rings[0], [r for r in rings[1:] if len(r) >= 3]))
        out[tuple(sorted(props.items()))] += poly.area
    return out


def test_worldmap():
    src = os.path.join(config.RAVEN_CREEK_MAP, "worldmap.xml")
    features = read_features(src)
    writer = WorldMapWriter()
    for props, rings in features:
        if rings and len(rings[0]) >= 3:
            writer.add(props, make_valid(Polygon(rings[0], [r for r in rings[1:] if len(r) >= 3])))
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "worldmap.xml")
        writer.save(out)
        again = read_features(out)
    a, b = areas(features), areas(again)
    worst = max(abs(a[k] - b[k]) / max(a[k], 1) for k in a)
    print("worldmap: %d features in, %d out, %d property sets, worst area difference %.4f%%" % (
        len(features), len(again), len(a), worst * 100))
    assert set(a) == set(b) and worst < 0.01


def test_biome():
    folder = os.path.join(config.RAVEN_CREEK_MAP, "maps")
    names = sorted(f for f in os.listdir(folder) if f.startswith("biomemap_"))[:20]
    with tempfile.TemporaryDirectory() as tmp:
        for n in names:
            values = biome.load(os.path.join(folder, n))
            biome.save(os.path.join(tmp, n), values)
            assert np.array_equal(values, biome.load(os.path.join(tmp, n))), n
    vanilla = biome.load(os.path.join(config.VANILLA_MAP, "maps", "biomemap_30_62.png"))
    print("biome: %d Raven Creek maps round-trip; vanilla palette 30_62 decodes to %s" % (
        len(names), sorted(collections.Counter(vanilla.ravel().tolist()).items())))


if __name__ == "__main__":
    test_worldmap()
    test_biome()
