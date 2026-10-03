--[[
    Naga City -- server, the road from Raven Creek

    Raven Creek's road south-east of its first gas station ends at x 6599 (rows 15396..15411), but Raven Creek's
    cell 25 runs on to x 6655: its lot is empty there and its biome map says deep forest, so B42 worldgen grows trees
    across the road. Naga's connector starts at x 6656 (cell 26). This paves the 56 x 16 strip in between as Raven
    Creek's road continued (same tiles and markings as tools/generate.py connector_markings), whenever one of its
    squares loads and is not paved yet. Runs on the server and in single player; clients get the result from the
    server. See CLAUDE.md "Placement".
--]]

if isClient() then return end

local X0, X1 = 6600, 6655
local Y0, Y1 = 15396, 15411
local CENTER = 15404

local ASPHALT = { "blends_street_01_80", "blends_street_01_85", "blends_street_01_86", "blends_street_01_87" }
local EDGE_N = { "blends_natural_01_24", "blends_natural_01_28", "blends_natural_01_40", "blends_natural_01_44" }
local EDGE_S = { "blends_natural_01_27", "blends_natural_01_31", "blends_natural_01_43", "blends_natural_01_47" }
local YELLOW_N, YELLOW_S = "street_trafficlines_01_18", "street_trafficlines_01_22"
local WHITE_N, WHITE_S = "street_trafficlines_01_2", "street_trafficlines_01_6"

local function pick(list, x, y)
    return list[(x * 7 + y * 13) % #list + 1]
end

local function overlaysAt(x, y)
    local out = {}
    if y == Y0 then table.insert(out, pick(EDGE_N, x, y)) end
    if y == Y1 then table.insert(out, pick(EDGE_S, x, y)) end
    if y == CENTER - 1 then table.insert(out, YELLOW_S) end
    if y == CENTER then table.insert(out, YELLOW_N) end
    if x % 4 <= 1 then
        if y == CENTER - 4 then table.insert(out, WHITE_N) end
        if y == CENTER + 3 then table.insert(out, WHITE_S) end
    end
    return out
end

local function isPaved(square)
    local floor = square:getFloor()
    local sprite = floor and floor:getSprite()
    local name = sprite and sprite:getName()
    return name ~= nil and string.sub(name, 1, 17) == "blends_street_01_"
end

local function pave(square)
    local x, y = square:getX(), square:getY()
    local objects = square:getObjects()
    local floor = square:getFloor()
    for i = objects:size() - 1, 0, -1 do
        local object = objects:get(i)
        if object ~= floor then
            square:transmitRemoveItemFromSquare(object)
        end
    end
    square:addFloor(pick(ASPHALT, x, y))
    for _, name in ipairs(overlaysAt(x, y)) do
        square:transmitAddObjectToSquare(IsoObject.new(square, name), -1)
    end
end

local function onLoadGridsquare(square)
    local x, y = square:getX(), square:getY()
    if x < X0 or x > X1 or y < Y0 or y > Y1 or square:getZ() ~= 0 then return end
    if isPaved(square) then return end
    pave(square)
end

Events.LoadGridsquare.Add(onLoadGridsquare)
