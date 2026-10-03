"""Download Naga City's OpenStreetMap data (inside the city boundary) to data/naga.json via Overpass."""
import json
import os
import time
import urllib.parse
import urllib.request

import config

QUERY = """[out:json][timeout:600][maxsize:1073741824];
area(id:%d)->.a;
(
  rel(%d);
  way["building"](area.a);
  rel["building"](area.a);
  way["highway"](area.a);
  way["waterway"](area.a);
  way["natural"](area.a);
  rel["natural"](area.a);
  way["landuse"](area.a);
  rel["landuse"](area.a);
  way["leisure"](area.a);
  way["amenity"](area.a);
  way["railway"](area.a);
  way["bridge"](area.a);
  node["amenity"](area.a);
  node["shop"](area.a);
);
out geom;""" % (3600000000 + config.OSM_RELATION, config.OSM_RELATION)

SERVERS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]


def main():
    os.makedirs(config.DATA, exist_ok=True)
    body = urllib.parse.urlencode({"data": QUERY}).encode()
    for url in SERVERS:
        try:
            start = time.time()
            req = urllib.request.Request(url, data=body, headers={"User-Agent": "pz-naga-mapgen/0.1"})
            raw = urllib.request.urlopen(req, timeout=700).read()
            data = json.loads(raw)
            if data.get("remark"):
                print("overpass remark:", data["remark"])
            with open(config.OSM_FILE, "wb") as f:
                f.write(raw)
            print("%s: %d bytes, %d elements, %.0f s" % (url, len(raw), len(data["elements"]), time.time() - start))
            return
        except Exception as e:
            print(url, repr(e))
    raise SystemExit("every Overpass server failed")


if __name__ == "__main__":
    main()
