"""Read real cells (vanilla and Raven Creek), write them back with pzmap, and require byte-identical files."""
import os
import random
import re
import sys
import time

import config
from pzmap.chunkdata import ChunkData
from pzmap.lotfiles import Cell


def cells_in(folder):
    out = []
    for f in os.listdir(folder):
        m = re.match(r"(\d+)_(\d+)\.lotheader$", f)
        if m:
            out.append((int(m[1]), int(m[2])))
    return sorted(out)


def check(folder, cx, cy):
    name = "%d_%d" % (cx, cy)
    problems = []
    cell = Cell.load(folder, cx, cy)
    rng = cell.file_level_range
    if cell.header_bytes(rng) != open(os.path.join(folder, name + ".lotheader"), "rb").read():
        problems.append("lotheader")
    if cell.pack_bytes(rng) != open(os.path.join(folder, "world_" + name + ".lotpack"), "rb").read():
        problems.append("lotpack")
    if rng != cell.level_range() and cell.squares:
        problems.append("levels %s vs used %s" % (rng, cell.level_range()))
    path = os.path.join(folder, "chunkdata_" + name + ".bin")
    if os.path.exists(path):
        raw = open(path, "rb").read()
        if ChunkData.from_bytes(raw).to_bytes() != raw:
            problems.append("chunkdata")
    return cell, problems


def main():
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    random.seed(42)
    for folder in (config.VANILLA_MAP, config.RAVEN_CREEK_MAP):
        cells = cells_in(folder)
        biggest = sorted(cells, key=lambda c: -os.path.getsize(os.path.join(folder, "%d_%d.lotheader" % c)))[:3]
        sample = sorted(set(biggest + random.sample(cells, min(count, len(cells)))))
        bad = 0
        start = time.time()
        for cx, cy in sample:
            cell, problems = check(folder, cx, cy)
            if problems:
                bad += 1
            print("  %d_%d rooms %d squares %d room ids %s %s" % (
                cx, cy, len(cell.rooms), len(cell.squares), sorted(cell.room_ids_seen)[:3], problems or "ok"))
        print("%s: %d cells, %d with differences, %.1f s" % (os.path.basename(folder), len(sample), bad,
                                                           time.time() - start))


if __name__ == "__main__":
    main()
