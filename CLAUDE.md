# Naga City, Philippines

Project Zomboid B42 map mod: Naga City, Camarines Sur, generated from OpenStreetMap at 1 tile = 1 m and added to Knox
Country south-east of Raven Creek. The shipped mod is `Contents/mods/NagaCity/`: mod.info, art and Lua in `42/`, the
map folder in `common/media/maps/Naga City, PH/` (it must be under `common`, see Placement). The generator that writes
the map files is `tools/` (Python, not uploaded). General engine findings go in
`~/Zomboid/Workshop/ZomboidFixesB42/CLAUDE.md`; this file holds the reasoning behind this mod and the map formats.

## Where we are (2026-10-04) — read this first

**Direction (the user's, in order of how they arrived):**
1. Roads the Zomboid way: cardinal / 45-degree, highways completely straight, nothing jagged anywhere (walks, drives,
   outlines too). Done in `roads.py` / `generate.py`.
2. Interiors: vanilla-style, full, fun; accuracy only outside; outsides may be resized to fit the interiors.
3. **The real goal: street-level nostalgia.** "What we need is for a Naga citizen to go down a named road and feel
   actual Naga City in isometric view, even if the road is curved and straightened." Building *positions* along named
   roads (which road, which side, order, setback) matter most; overall map accuracy does not.
4. **Buildings are hand-drawn by Claude** ("you draw them") as designs that suit Zomboid tiles, reviewed by the user
   from renders. Procedural exteriors (Ateneo v1/v2) looked generic/ugly — do not go back to rule-based facades.
5. Pilot street: **Panganiban Drive**, end to end, before anything else. Generic vanilla signs / shop interiors are OK
   for now (no custom brand art yet).

**Pilot status:** OSM inventory done (`tools/out/panganiban_strip.png`, data in `out/panganiban_items.json`):
Panganiban Drive = OSM ways named exactly "Panganiban Drive" (not J. Panganiban Street), main run 1,678 m from Elias
Angeles St (8194,19493) east to Juan Miranda Ave (9855,19729); 251 OSM buildings within 35 m, 66 named places.
Cross streets (m from Elias Angeles): Dinaga / Peñafrancia Ave 81, Riverside 168, Blumentritt 260, Lerma /
Misericordia 317, Ninoy and Cory Ave 506, Palomares 516, SM City Naga Road 689, Isarog 761, Ramon Felipe Jr. 836,
Caceres 917, Seton Rd 977, Mayon Ave 1044, Sampaguita 1176, Hospital Loop Rd 1376, Evangelical 1441, Juan Miranda
1527. Named places west to east: Mercury Drug, Southstar, Naga Optical, Naga Garden, RCBC, Chinabank, Maybank,
Watsons, Security Bank, jeepney station (to Concepcion / Del Rosario) ~91 m south side, PSBank, Worldtech, 7-Eleven,
Beanbag Coffee, PBCOM, Petron ~291, CheckOut, Spring Star Siopao, Shell ~381, Motortrade, Julie's Bakeshop,
Jollibee ~525 (2 floors), St. John Hospital ~573, LDS church, DBP, Petron ~866, BDO, PNB, Amanse Children's Clinic,
NIA Regional Office ~1156, BPI, Producers Bank, Metro Gaisano / Super Metro ~1457 (6,500 m2), UnionBank, Landbank,
Naga City Police Station 2 at the east end. The user has not corrected the list yet (may later).

**Done for the pilot:** the design system (`tools/designs.py`, `tools/design_preview.py`) and design 1,
`SHOPHOUSE_8` (2-floor shophouse, 8 x 14: glass shopfront + glass door, shop, back stair hall + storeroom; upstairs
kitchen, bathroom, bedroom, front living room). The user: "this is honestly better", but flagged a clock on a window
and certificates hanging in the air → fixed with wall-hung item filtering (below); re-render not yet reviewed.

**Next:** re-check the shophouse renders; ask about look (side walls, flat roof, paler paint, full glass front vs
roll-up door). Then designs for: 3-floor bank / office with glass ground floor, gas station (canopy + pumps),
fast-food restaurant (Jollibee), hospital, NIA office, mall (Metro Gaisano), police station, jeepney station.
Then a street-anchored placer: each OSM building along the road → its along-distance, side and setback mapped onto
the straightened in-game Panganiban Drive (fraction of length along the schematized path; sidewalk then setback),
design chosen by OSM tags / size, front facing the road, 1-tile gaps between neighbours (adjacent buildings would put
two walls on one edge). Then generate and show renders of the first 250 m.

**Open issues:** the same render's bathroom has a shower head but no glass panes: multi-part fixtures lose pieces
when a vanilla room is copied — parts on squares outside the room rect are never collected (`build_room_library.py`
keeps only the rect), and pane-like pieces may be dropped by the hung-item filter (it demands a plain wall where the
pane *is* the wall). Fix before more copying: collect a room's S / E boundary squares too, never filter wall-like
fixtures, or keep whole fixtures together. the user found (2026-10-04, shophouse upstairs render) a room with a blank window and a door with
no frame — not yet diagnosed: every room's wall set has all eight pieces (checked), so check the wall-set numbering
per family (render `walls_interior_bathroom_01` / `walls_interior_house_03` pieces large) and the iso renderer's draw
order before trusting renders; the user is losing confidence ("I don't think we can do this. it might be too complex
for you") — verify every render square by square before sending. whiteboards / chalkboards (`location_business_office_generic_01_64..67`) carry no `attached*` flag,
so they are not filtered (check their `Facing` property instead); a copied vanilla room smaller than the drawn room
leaves space; branded signs need custom art (later); Ateneo still uses the procedural layout (`layout.py`) and should
be redrawn with designs later; the NagaCity repo has **no commits yet** (offer one).

## Prefabs: copying whole vanilla buildings (2026-10-04, current approach)

After the hand-drawn designs kept breaking vanilla pieces (blank window frames, a door with no frame, a shower head
without its glass panes, an oven in front of a door), the user chose: **copy whole vanilla buildings with small
alterations** ("I like the idea of copying vanilla buildings with small alterations"). `tools/prefabs.py`:
`extract((cx, cy), building index, margin)` copies every square of a building's rooms on every level plus a border
(border squares keep objects, not ground; other buildings' room squares skipped); `entrances(p)` = sides with outside
doors (buildings cannot be turned: sprites face fixed ways, so pick one whose front faces the street);
`paste(p, canvas, ox, oy)`. Small safe alterations planned: exterior paint swap, room names (loot), signs, a few
furniture pieces. No structural edits.
Proof (`tools/out/proof_*.png`, original left, copy right): pharmacy 46_26 #32 (Pharmahug) and bank 41_37 #45 copy
identically; the gas station 46_26 #36 (border 14) comes with its whole forecourt (asphalt, pumps, lines, cones, fence).
How the border is kept: its ground comes along (the user asked "why is it on top of grass?" when it did not), except
squares inside a vanilla **road polygon** of Knox County's worldmap.xml (`vanilla_road_squares`, cached
`data/vanilla_roads.pickle`), where asphalt / lines / curbs / trees are dropped — lots and roads use the same asphalt,
only the world map tells them apart. Squares of other buildings' rooms are skipped, and squares within one square of
them (and their roofs above) too, **except** on our own one-square rim (else the bank lost its south / east walls,
which sit on squares outside its rooms). A neighbour's yard room can still cut off planting next to ours (the bank's
flower bed). Waiting for the user's look and an in-game test, then: fill the first
250 m of Panganiban Drive with matched vanilla buildings (type by OSM tags, size, entrance facing the street).

## Status

Phases 1-3 done, phase 3 waiting for the user's in-game test. The lot writers rewrite 124 sampled vanilla and Raven
Creek cells byte-identical (`test_roundtrip.py`); the worldmap and biome writers pass `test_writers.py`.
`generate.py` writes the ground of the whole coverage (743 cells incl. 7 connector cells, ~4 M paved/water squares,
82.5 MB, 34 s): roads, sidewalks, centre lines, rivers, biome maps, worldmap.xml, a test spawn at Plaza Rizal. No
buildings, zones, zombies (density 0) or car spawns yet. Nothing has been run in game.

Run the tools with the venv: `tools/.venv/Scripts/python.exe` (create it with `python -m venv tools/.venv` and
`pip install -r tools/requirements.txt`: numpy, Pillow, shapely).

## Decisions (the user's, do not re-ask)

- **Coverage: the whole urban area** (not a downtown pilot): Naga-local cells x -7..24, y -13..9 = PZ cells 26..57 x
  63..85 (`config.COVER`), from the Bicol River west of downtown out along Roxas Avenue / Maharlika Highway to
  Concepcion, Triangulo, Carolina, and Pacol to the north. OSM reaches further (roads into the hills, scattered
  buildings east to local cell 55 and north to row -19, i.e. Panicuason / Mt Isarog): clipped. The user never chose
  between this and a smaller box; this one stands until they say otherwise.
- **Placement: added to Knox Country** (`lots=Muldraugh, KY`), not a standalone world.
- **Buildings: generated from OSM footprints, plus hand-built landmarks.** A landmark replaces the generated building
  on its OSM footprint (matched by OSM way id) and keeps its real position. Candidates: Naga Metropolitan Cathedral,
  Basilica of Our Lady of Peñafrancia, Plaza Rizal and Plaza Quezon, Porta Mariae, Naga City Hall, Ateneo de Naga,
  University of Nueva Caceres, SM City Naga, Naga City public market, Bicol Medical Center. List not settled.
- **Entry: from Raven Creek.** Its long entry highway leaves the vanilla road near cell 25,57, runs south to its first
  gas station (cell 25,59, room `gasstorage` at 6549,15313) and turns west into town. The road **south-east of that
  station** (16 tiles wide, y 15396..15411) runs east and stops at x 6599. Naga's network joins there.
- Build in phases (below); the test slice is checked in game by the user before the full run.
- **Interiors full and real, not accurate; outsides may be resized to fit them** (user, 2026-10-04: "Make it look
  like the real thing EVEN WITHOUT BEING ACCURATE ... accuracy is only needed for the outside ones", "we can also
  resize the exterior so that the interior can match"). `tools/layout.py`: corridor buildings are strips of
  [vanilla room band | corridor 3 | vanilla room band] plus a 6-wide stairwell / lobby, every band filled with whole
  vanilla rooms of exactly its depth (widths found by a reachable-sums search so both bands of a strip end level,
  main type required in the north / west band, e.g. 15 library rooms in the library); halls = best vanilla hall +
  a band of side rooms; small buildings = one vanilla room. Rooms bring their vanilla floor and wall set
  (`build_room_library.py` stores both). Buildings are centred on the real ones and shrunk if they would overlap.
  Open: the church (vanilla churches are at most 30 x 28) came out 11 x 40 instead of 23 x 44.
- **Interiors: the normal Zomboid way** (user, 2026-10-03, about Ateneo: "for the interiors, you can use the normal
  zomboid format"): rooms need not match the real buildings; they are furnished with vanilla rooms of the same name
  (`rooms.furnish`, library from `build_room_library.py`).
- **Roads the Zomboid way** (user, after the first in-game look, 2026-10-03: "why use these tiles? do it the zomboid
  way ... use cardinal directions mostly ... we can approximate"): streets straight north-south / east-west where
  they are within 30 degrees of it, real diagonals as clean **45-degree** roads (chosen over staircases), vanilla's
  street recipe (no custom-looking tiles). Never follow OSM's exact angles: a 1-tile staircase at an arbitrary angle
  is what the user rejected. Second look (screenshot of two 45-degree roads crossing with sidewalk stubs and 1-2 tile
  notches): "horrible formations ... we can further straighten these", then "**treat highways as completely
  straight**. the zomboid map just needs to follow place accuracy but not highway curvatures." So: few long straight
  legs, junctions near their real places, no short diagonals or small jogs.

## Placement

- Vanilla 42 lots fill cells x 0..77, y 0..62 (4065 lot cells; the north-west 0..57 x 0..17 is biome-only wilderness).
  Installed map mods (Raven Creek x 16..25 y 56..69, Camden County, Constown, DawnTown, HavenFall, Nellis AFB) replace
  cells inside that or extend south (Raven Creek to row 69). Nothing installed uses x >= 26, y >= 63.
- Naga goes south of the vanilla edge: Naga-local cell (-7, -13) = PZ cell (26, 63), so Plaza Rizal (local 0,0) =
  PZ 8448,19456 (`config.OFFSET_X/Y`, tentative until coverage is settled; map.info `zoomX/Y` follow it).
- Connector (`generate.connector_line`): from x 6600 along Raven Creek's centre y 15404, east to x 7688, a 64-tile
  curve, then south on x 7752 to the north end of Calabanga Road (OSM way 733429690, secondary, at 7752,16341). 16 wide
  like Raven Creek's road; on the straight parts Raven Creek's exact marking profile (edge grass blends, double yellow
  on the centre boundary, white dashes 4 tiles out, 2 on / 2 off where the coordinate mod 4 is 0 or 1), turned 90
  degrees on the south leg. It clips the edge of a small vanilla pond near the curve (causeway). The vanilla world's
  lot data ends partway through cell row 62 (y ~15900); south of that vanilla has only biome data. Those vanilla cells hold no buildings,
  only `blends_natural_01` ground and vegetation (26_60: every square one natural tile, 64 tile names), so the connector
  cells are vanilla's cells copied with the road laid over them. A mod cell replaces the vanilla cell whole.
- **The gap x 6600..6655**: inside Raven Creek's cell 25 (its 300-grid edge is x 6600), empty in its lotpack. Raven Creek's
  `biomemap_25_59/60.png` is 255 there (`primary_forest` / DeepForest), and B42 worldgen fills every level-0 square that
  has no objects (`IsoChunk.LoadBrandNew` -> `WorldGenChunk.generateChunks` for the 2x2 chunk block), so trees grow in
  the road's way. `media/lua/server/NagaCity_RavenCreekLink.lua` paves the 56 x 16 strip on `LoadGridsquare` (fired in
  `IsoChunk.doLoadGridsquare` after worldgen, server and SP) when its floor is not `blends_street_01_*`: removes every
  other object with `transmitRemoveItemFromSquare`, `addFloor` (removes floors / ground vegetation / grass overlays,
  adds and transmits the new floor), then the markings with `transmitAddObjectToSquare(IsoObject.new(square, name), -1)`
  (-1 appends). Same profile as the connector. Independent of map order, and also repaves an existing save's strip. Shipping our own copy of Raven Creek's cell 25 files would also work but
  redistributes its data and depends on load order.
- **The map folder must be under `common/media/maps/`.** `MapGroups.createGroups` (42.20) scans a mod's
  `getVersionDir()/media/maps/` only inside the `if` for `getCommonDir()/media/maps/` existing, so a map that lives only
  in `42/media/maps/` is never found: the mod loads, its Lua runs, but the world has no Naga (first in-game test,
  2026-10-03: the save's world map stopped at the vanilla edge). Raven Creek ships its map under `common/`.
- Map order (`MapGroups.MapGroup.setPriority`): mod map folders come before vanilla and each map before the maps in
  its `lots=`, so Naga's copies of vanilla cells win over Muldraugh's. `checkMapConflicts` will list those 7 connector
  cells as conflicts with Muldraugh (expected).
- `mod.info` has `require=\RavenCreekB42` (Raven Creek's mod id). Naga does not overlap Raven Creek, so this only exists
  because the way in is through it; drop it if Naga should also be usable alone.

## B42 map formats (42.20, from `zombie/pot/POT*.java`, the game's own B41 -> B42 converter)

Phase 2 checked all of this by rewriting real files (see Status); where WorldEd's real files differ from POT, the
writers follow the real files.

Map folder `media/maps/<name>/`: `X_Y.lotheader`, `world_X_Y.lotpack`, `chunkdata_X_Y.bin` per cell (cell 256 tiles,
chunk 8, 32 x 32 chunks), `maps/biomemap_X_Y.png`, `map.info`, `objects.lua`, `spawnpoints.lua`, `worldmap.xml`
(+ `.bin`), optional `worldmap-forest.xml`, `spawnSelectImagePyramid.zip`, `roomtones.lua`, `thumb.png`.

- **lotheader** (little-endian ints): `LOTH`, version 1, tile count, tile names each ending in `\n`, width 8, height 8,
  minLevel, maxLevel (the non-empty range), room count; per room: name`\n`, level, rect count, rects (x, y, w, h,
  cell-relative), object count, objects (type, x, y); building count; per building: room count, room indexes; then
  32 x 32 zombie density bytes written x-outer (`density[x + y * 32]` for x, for y).
- **lotpack**: `LOTP`, version 1, then 1024 (POT writes the chunk dim 8 here; real files have the chunk count and the
  reader skips it), then a table of 32 x 32 8-byte offsets (index `chunkX * 32 + chunkY`; readers read only the low
  int), then per chunk, z from minLevel to maxLevel, x 0..7, y 0..7: either `-1, n` (skip n empty squares, runs cross
  levels but not chunks) or `count, roomId, tile indexes (count - 1)`. `IsoLot` reads roomId and ignores it: rooms
  come only from the header's room rects. WorldEd writes the square's room index (POT writes -1); the writer keeps it
  (`Cell.square_rooms`). Tile order in a square is draw order (floor first).
- **chunkdata** (big-endian, `DataOutputStream`): short version 1, then per chunk (y outer, x inner) a type byte:
  0 empty, 1 all solid, 3 all water, 4 all room, 5 all "no lot", 2 regular followed by 64 bytes (`x + y * 8`) of bits
  1 solid, 2 wall N, 4 wall W, 8 water, 16 room, 32 no lot. Type 5 and bit 32 are not in POT but are in vanilla (165,716
  type-5 chunks) and Raven Creek; bit 32 is set exactly on the squares with no level-0 lot data (checked square by
  square on 25 Raven Creek cells), i.e. the ones worldgen fills. Read only by native code
  (`MapCollisionData.n_initMetaCell`, the zombie population / collision library), so the other bits' exact meaning is
  inferred from POT.
- **biome map**: 256 x 256 PNG; band 0 = biome, band 1 = zone (`BiomeMap.Type`), looked up in
  `media/lua/server/metazones/BiomeMapConfig.lua` (0 Water, 64 ForagingNav, 96 DeepForest random, 102 TrailerPark,
  115 TownZone/townhouse, 128 Farm, 141 FarmLand, 153..243 forest kinds, 254 dirt (spawns nothing), 255 primary forest).
  `BiomeMap.getRaster` takes the first map in the world's map list that has the file, so a cell's biome comes from
  whichever map folder is listed first. `BiomeRaster` decodes to RGBA (red = biome, green = zone), so vanilla's palette
  PNGs and Raven Creek's RGB (R = G = B) both work; vanilla 30_62 decodes to 153 and 255. The writer uses RGB.
- **worldmap.xml** cells are 300 tiles even in B42 (vanilla and Raven Creek): absolute = cell * 300 + point. The game
  loads `worldmap.xml.bin` when it exists, else parses the XML (`WorldMapDataAssetManager`), so XML alone works; Lua
  (`ISMapDefinitions`, `ISMiniMap`) adds `worldmap-forest.xml` then `worldmap.xml` of every map folder. Vanilla: 13,742
  Polygon, 24 LineString, 4 Point features; extra `<coordinates>` blocks are holes; rings are not closed; 112 points lie
  slightly outside 0..300. The style (`MapUtils.initDefaultStyleV1`) draws only polygons with natural=forest,
  water=river, highway=trail|tertiary|secondary|primary, railway=*, building=yes|Residential|CommunityServices|
  Hospitality|Industrial|Medical|RestaurantsAndEntertainment|RetailAndCommercial. Buildings also carry `RoomTone`
  (HouseSuburb, HouseSmall, HouseGarage, Shed, ... the building's ambient sound).
- Squares the lot leaves empty at level 0 are generated by worldgen from the biome map, so the generator only writes
  what OSM knows (roads, water, buildings, paved areas); trees and grass come from biome maps.

## Tiles (phase 3, from vanilla and Raven Creek lots; `tools/tiles.py`)

- Tile families come in 16s; the plain fill tiles are base +0, +5, +6, +7, the rest are edge blends.
  `blends_street_01`: 80 dark asphalt (vanilla's main roads, Raven Creek's road), 96 light concrete, 48 beige,
  16 dirt road (16, 21), 32 / 64 / 0 other greys. `blends_natural_02` 0/5/6/7 water. `blends_natural_01` 0-15 sand,
  16-31 green grass, 32-47 dry grass. `floors_exterior_street_01_0..14` concrete slabs.
- Vanilla town street cross-section (cells 42_39, 41_37, 44_26, 46_26, 31_45): grass | sidewalk `blends_street_01`
  48/53/54/55 (1-2 rows) | asphalt 80 family (main roads) or 96 family (town streets) | sidewalk | grass. The outer
  street row carries a grass-edge overlay on its grass side; curbs are overlays on the sidewalk / road boundary.
  `floors_exterior_tilesandstone_01_3` (first attempt's sidewalk, the big light slabs in the user's screenshot) is
  not a sidewalk.
- Edge sprites (checked by rendering over asphalt): grass edge `blends_natural_01` 24 N, 25 W, 26 E, 27 S, 28-31 the
  same again, 40-47 dry grass. Curbs sit on a south or east edge: sidewalk square with road south of it 8, road
  square with sidewalk south 10; east: 9 on the sidewalk, 11 on the road. `street_trafficlines_01`: white 0 W, 2 N,
  4 E, 6 S, odd = corners; yellow = +16. On a tile the "/" upper-left edge is west, "\" upper-right is north.
- Half tiles: in every 16-family base + 1 = upper half (N+W triangles), + 2 lower (E+S), + 3 left (W+S), + 4 right
  (N+E), cut along the square's diagonals; **the other half is transparent**, so a grass tile goes underneath
  (`tiles.GRASS`). Same for water (`blends_natural_02_1..4`).
- Roads (`roads.py` docstring has the steps, `generate.py` draws them). Highways (trunk / primary / secondary) are
  stitched into routes by name, simplified at 40 m keeping ends and highway crossings, each leg made exactly H / V
  within 15 degrees of an axis (no cap) or straight / 45 / straight otherwise; side streets' junctions on a route are
  pinned onto the straightened route at the same fraction of the leg. Other roads: split at junctions, Douglas-Peucker
  (8 m tertiary, 6 m else), H / V within 35 degrees by union-find (pinned nodes win, spread cap 20, then offsets up
  to 16 merged anyway), coordinates snapped to multiples of 4, the rest octilinear; a diagonal under 40 m or with a
  45-degree part under 8 becomes a square corner; no sidewalk on pieces under 12 or next to a diagonal, and sidewalks
  never run past their road's end. Straight pieces are rectangles with square caps; 45-degree pieces are bands
  between lines x - y = c (or x + y = c) with half tiles on the bounds. Carriageway (even, so edges fall on square lines) trunk 14, primary 12, secondary 10, tertiary 8,
  residential 6, service 4, track 4 (dirt), links 6, `lanes` * 3 + 2 when tagged; 2-row sidewalks on trunk /
  primary / secondary straight pieces; double yellow on two-way trunk / primary / secondary straight pieces, cut at
  crossings of the other orientation. Diagonals get no sidewalk, curb or line yet (no clean half pieces for them).
  Priority water < sidewalk < dirt < minor < major, so roads cross water as causeways (no bridges yet).
- Water: OSM areas plus waterways buffered (river 20, canal 6, stream 4, drain/ditch 2, or `width`), organic
  outline; a bare square with water on exactly two adjacent sides becomes half water (`smooth_shore`), so the
  shoreline is no sawtooth on screen.
- Biome (`generate.Biomes`): FarmLand 141 by default, forest 192, farm 141, town 115 (town landuse and 25 m around every
  building), water 0.

## Buildings (`tools/buildkit.py`, `tools/templates.py`), learned from vanilla

From the 48_8 university (rooms classroom / universitylibrary / universityoffice), the 39_49 school and 41_37 houses.
- Walls are edge sprites on a square's north or west edge; a wall between two squares goes on the southern / eastern
  one. On a square inside a room: the interior set + the detailing strip (`walls_interior_detailing_01`, row 2, same
  piece); on a square outside (the building's south and east faces): the exterior set. That is the face the camera
  sees; vanilla's north / west outer walls are interior tiles on the room's own squares.
- Every wall set (exterior, interior, detailing) uses rows of 16: colour A 0 W, 1 N, 2 NW corner, 3 SE post, colour B
  + 4; openings + 8: W window, N window, W door, N door (colour B + 12). NW corner where two walls meet in a square,
  SE post on the outside corner square. Window = frame piece + `fixtures_windows_01_16` (W) / `_17` (N); door =
  frame + `fixtures_doors_01_0` (W) / `_1` (N). Stairs: north-climbing `fixtures_stairs_01_24` (bottom) 25, 26 (top),
  two wide, no floor above them, arrival north of the top; west-climbing 16 (bottom, east) 17, 18. Flat roof
  `roofs_04_54` / `_55` over the top floor (z + 1).
- Interiors: `tools/build_room_library.py` collects every one-rect vanilla room (3..64 squares a side) with its
  furniture (everything but floors, walls, doors, windows, overlays, stairs, railings, vegetation) into
  `data/vanilla_rooms.json` (25,022 rooms, 442 names, 81 s). `rooms.furnish(name, rect, clear)` copies one of the six
  best-fitting rooms of that name onto the room's north-west corner (walls line up, so wall items stay on walls),
  repeats its inner part in rooms twice its size (not churches, gyms, homes, restrooms), keeps door and stair squares
  clear, and gives corridors nothing (vanilla `hall` rooms are house hallways with washers). The hand layouts below
  are the fallback when vanilla has no room of that name that fits.
- Hand furniture copied from vanilla rooms: classroom = whiteboard on the west wall `location_business_office_generic_01_67..64`
  (north to south), teacher's desk `furniture_tables_high_01_34`, `_35` + chair `furniture_seating_indoor_01_50`,
  student desks `tables_high_01_33` over `_32` with chairs `seating_indoor_01_52` east of them; library shelves
  `furniture_shelving_01_41` / `_42` in facing rows; restroom toilets `fixtures_bathroom_01_0` (+ stall `_57`), wall sinks
  `fixtures_sinks_01_15`; office desk `location_business_office_generic_01_96..98` + chair `seating_indoor_02_47`.
- Templates: `school_block` (rooms along the long side, a 3-wide corridor on the south / east, a 6-wide stair bay at
  the west / north end with stairs alternating between two spots per level, restrooms at the other end, entrances on
  the corridor's outer wall), `hall_block` (one big room), `house_block`. Room defs: one per key per level, rects from
  `landmarks/merge.rects_of`; a building's defs go in the header of the cell holding its first room, rects may run
  past 256 (vanilla does it).
- `buildkit.Canvas` holds landmark squares in absolute coordinates; `landmarks/merge.LandmarkLayer` writes them into
  the cells over the ground, and the claimed squares get no generic roads, town biome and their own chunk bits
  (ROOM, WALL_N, WALL_W).

## Designs (`tools/designs.py`) — hand-drawn buildings

- A `Design` = name, notes, `rooms` (letter -> vanilla room name, `"{use}"` = the business: pharmacy, bank...),
  `shop` letter, and one dict per floor: `rows` (text grid, north row first, street front at the **bottom / south**),
  `doors` [(x, y, edge N|S|E|W, optional "glass")], `windows` [(x, y, edge)], `stairs` [(x, y, climb dir)] = top
  square (west of the two columns) as drawn. Walls go wherever letters differ.
- `place(design, ox, oy, facing, use, exterior=None, seed)` turns it: S as drawn, N mirrored, E / W rotated; edges
  convert to buildkit's N/W form (S edge = N edge of the square below, E = W edge of the square right). Stairs that
  would climb S / E after turning are laid N / W in the same footprint (stair bays must be open at both ends). Each
  (letter, floor) gets its own one-character room key. The ground floor's south edges in the shop room become the
  glass shopfront `walls_commercial_01` row 80 (80 W, 81 N, 82 corner, 83 post, 90 / 91 door frames) with glass door
  `fixtures_doors_01_48` (W) / `_49` (N); other vanilla shop doors: `_52/53/56/57`, double `fixtures_doors_02_40/41/44/45`.
  Upper floors: a random `PAINT` exterior set. `fixed_windows` = only the drawn windows.
- Rooms get the best-fitting vanilla room of their name (top 5, seeded) and its floor and wall set; corridors /
  stair halls (`hall`) get no furniture.
- buildkit additions: `edge_walls` (per-edge WallSet override), `door_tiles` (per-edge door object), `fixed_windows`,
  west-climbing stairs `(z, x_top, y, "W")` = `fixtures_stairs_01_18` (top, west) 17, 16, two rows deep; stair holes
  are now in absolute coordinates (they were local before, so floors were laid over stairwells).
- Wall-hung items: `pzmap/tiledefs.py` reads `attachedN/W/E/S/NW/SE` from `media/newtiledefinitions.tiles.txt`
  (6,681 sprites; cached `data/attached.json`). `Building.draw` keeps a hung tile only if every edge it needs is a
  plain wall (no window, door or open air); the per-room window plan skips edges that hung items need.
- `Building.draw` also drops furniture on the squares either side of every door, on stairs and at a stair's two ends
  (a vanilla kitchen put its stove in front of the kitchen door: "you put an oven in front of the door").
- `design_preview.py NAME [use] [--z=N] [--facing=SNEW]` renders one design on grass with a road in front
  (`render_canvas` draws a Canvas directly, no map files).

## Landmarks

- **Ateneo de Naga University**, the college campus on Ateneo Avenue (OSM way 222268858; the user asked for it
  2026-10-03 and said "the college campus", not the Junior High campus far east). `tools/landmarks/ateneo.py`: the
  campus turned -24 degrees about its centroid (its grid's angle) so every building is straight; each OSM building
  keeps its turned bounding box, name, storey count (`building:levels`) and a template by name / type (KIND map:
  Administration, Madrigal, Entrep, Faber = offices; Library = universitylibrary hall; Gymnasium; Christ the King
  Church; Jesuit Residence = house; the 4,500 m2 `building=roof` by the soccer field = covered court with a roof one
  level up; the rest of `building=school` = classroom blocks). Grounds (nothing jagged, the user's rule, again 2026-10-04 on
  the first campus walk): the turned outline squared into rectangles (`wings_of`, sides >= 16, 97 %), lawn inside,
  parking and the tennis court as their turned bounding rectangles, OSM walks (2 wide) and service roads (6 wide)
  straightened by `roads.schematize` with `MIN_DIAG` = inf (square corners only) and laid as straight strips. 28 buildings, 379 rooms (187 classrooms).
- Ateneo v2 (current): buildings from `layout.py` (vanilla-sized rooms, see Decisions), windows per room
  (`buildkit._plan_windows`: ~1 per 5 squares of a room's outside wall, at most 1 for restrooms / storage / janitor,
  corridors 1 per 8; the first rule put one on every other square — "why does every wall have a window?"). The user
  then found the result still generic ("it looks like this will be tough for you") → hand-drawn designs instead.
  Labelled map: `tools/out/ateneo_labels.png`. Xavier Hall = (8212, 18727) 32 x 28, offices (OSM has no use for it).
- Footprints filling less than 80 % of their box (Administration U, Arrupe L, Physical Plant) are split into
  rectangular wings (`wings_of`, largest rectangle first, sides >= 8, until 85 % is covered); wings share one plan,
  touching corridors get a door, the first wing has the stair bay.
- To do there: campus fence and gates; overlap check after squaring; the church (23 x 44) is about twice any vanilla
  church, so its back half is empty.

## OSM data and projection

- `tools/fetch_osm.py` -> `tools/data/naga.json` (gitignored, ~19 MB): everything inside relation 3084673 (Naga City,
  admin level 6): 22,402 building ways, 4,183 highways (2,759 residential, 622 service, 198 tertiary, 116 secondary, 22
  primary, 44 trunk: Maharlika Highway, Almeda Highway, Roxas Avenue, Mabolo Road, Naga Rotonda), 58 waterways, 643
  landuse ways + 43 relations, 16 railway ways (PNR), 419 amenity and 242 shop nodes.
- The boundary cuts the west side at the Bicol River; across it (Camaligan) is not downloaded.
- `config.project(lat, lon)`: equirectangular around Plaza Rizal (13.6236, 123.1875), 1 m = 1 tile, +y south.
- Licence: ODbL. Credit "Map data (c) OpenStreetMap contributors, ODbL" in mod.info, map.info, workshop.txt, README.

## Files

- `tools/config.py`: paths, projection, placement offsets, Raven Creek link coordinates.
- `tools/fetch_osm.py`: the Overpass query.
- `tools/pzmap/lotfiles.py`: `Cell` (tile table, squares, square room indexes, rooms, buildings, density) with
  `load`, `save`, `header_bytes`, `pack_bytes`; `set_square(x, y, z, names, room)` in cell-local coordinates.
- `tools/pzmap/chunkdata.py`: `ChunkData` (bits per square, cell-local) with `from_bytes` / `to_bytes` / `save`.
- `tools/pzmap/biome.py`: biome PNG `save` / `load` and the BiomeMapConfig pixel values.
- `tools/pzmap/worldmap.py`: worldmap.xml reader; `WorldMapWriter.add(props, shapely polygon)` clips into 300-tile
  cells.
- `tools/test_roundtrip.py [n]`: n random cells (+ the 3 biggest) of vanilla and Raven Creek must rewrite byte-identical.
- `tools/test_writers.py`: Raven Creek's worldmap re-emitted (area per property within 0.01%), biome PNG round trip.
- `tools/make_art.py`: poster/icon/preview from OSM (placeholders until there are in-game screenshots).
- `tools/osm.py`: OSM JSON -> projected shapely roads (`Road`), water, waterways, landuse, buildings, boundary.
- `tools/tiles.py`: tile choices and the deterministic `pick(options, x, y)`.
- `tools/pzmap/raster.py`: geometry -> per-square mask (square centres).
- `tools/pzmap/textures.py`: sprites from Tiles2x(.floor).pack, `contact_sheet` for picking tiles by eye.
- `tools/generate.py [x0 y0 x1 y1]`: writes the map folder (lots, chunkdata, biome maps, worldmap.xml, objects.lua,
  spawnpoints.lua, spawnregions.lua). Deletes only the files of the cells it writes.
- `tools/preview.py x0 y0 x1 y1`: top-down PNG read back from the written files (vanilla where we have no cell),
  empty squares in their biome colour.
- `tools/roads.py`: the road straightener (see Tiles / Roads).
- `tools/buildkit.py`, `tools/templates.py`, `tools/landmarks/` (`ateneo.py`, `merge.py`): buildings and landmarks.
- `tools/iso_preview.py x y size [out] [--z=N]`: isometric render (levels up to N) with the game's sprites (empty squares as plain grass), the
  closest thing to an in-game look without the game. Check new tile work here before asking the user to test.
- `media/lua/server/NagaCity_RavenCreekLink.lua`: paves the gap (see Placement).
- Decompiling: classes come from `projectzomboid.jar` in the game folder (the loose `zombie/` folder there is
  PZ_Optimization's overrides); the bundled JRE is `jre64/bin/java.exe`; Vineflower as in the ZomboidFixesB42 notes.

- `tools/build_room_library.py` -> `data/vanilla_rooms.json` (vanilla rooms with furniture, floor, wall set);
  `tools/rooms.py` (`furnish`, `NO_FURNITURE`, `NO_REPEAT`); `tools/layout.py` (vanilla-sized corridor / hall /
  single-room buildings, used by Ateneo v2); `tools/designs.py` + `tools/design_preview.py` (hand-drawn designs);
  `tools/pzmap/tiledefs.py` (wall-hung sprites); `tools/landmarks/` (`ateneo.py`, `merge.py`, `__init__.build_all`).
- Renders for the user live in `tools/out/` (sent with SendUserFile; VS Code links also work).

## Phases

1. Skeleton (done).
2. Writers: lotheader, lotpack, chunkdata, biome PNG, worldmap.xml (done).
3. Ground for the whole coverage, the connector, the Raven Creek gap Lua, test spawn (done; in-game test pending).
4. Buildings: footprints -> walls (N/W edge sprites), doors, windows, floors, roofs, levels and stairs, rooms named for
   loot, basic furniture/containers. Tile choices learned from vanilla lots, not guessed.
5. Zones and the rest: objects.lua (TownZone, Farm, ParkingStall, Nav...), spawnpoints.lua, biome maps from land use,
   zombie density from building density, worldmap.xml, map.info zoom.
6. Landmarks: hand-built buildings stamped over their OSM footprints (format: BuildingEd `.tbx` and/or a
   tile-by-tile spec in `tools/landmarks/`, not decided), with their own rooms, furniture and loot.
7. Full run over the whole coverage; size check (each full lotpack ~1 MB; cells with nothing to write get no files).

## To verify

- Phase 3 in game: the strip at x 6600..6655 paved (no trees), the connector drivable, worldgen ground beside roads,
  water tiles render, the in-game map shows Naga, the spawn region appears, no errors in console.txt.
- Empty lot cells (written with level range 0, 0 and no squares; POT would write 1000, -1000) load fine.

- Whether a cell with only `biomemap_X_Y.png` (no lotheader) beyond the vanilla edge is generated like vanilla's
  biome-only north-west, or is outside the world.
- What the native chunkdata reader does with each bit (zombie population and collision), and whether wrong bits break
  anything visible.
- Bridges: B42 vanilla bridge construction over the river (tile names, levels).
