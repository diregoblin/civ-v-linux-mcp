"""The unit-centred tactical view (#31): one bounded read of a unit's surroundings.

Lua half: H.tactical_view on a mocked 8 x 5 map that wraps east-west, laid out in Civ V's offset hexes (odd rows
half a plot to the right). Covered: the six neighbours come from the engine's PlotDirection, so the wrap seam and
the edge rows are its answer; `move` is move_unit's own refusal (H.move_refusal) and never a path cost; fogged
plots never read live occupants, owners or features (the live getters raise here); the combat previews are the
existing H.melee_targets / H.ranged_targets rows; radius bounds every list and the grid. The move_unit refactor
that shares its checks is covered by test_move_into_city and test_mcp_safety.
"""
import unittest

import test_mcp_safety as support
from harness.game import Game


WORLD = r"""
local function forbidden(name) return function() error('live ' .. name .. ' read under fog') end end
W, HT = 8, 5
GameDefines = { MOVE_DENOMINATOR = 60, MAX_HIT_POINTS = 100 }
DomainTypes = { DOMAIN_LAND = 0, DOMAIN_SEA = 1, DOMAIN_AIR = 2 }
MissionTypes = { MISSION_MOVE_TO = 1 }
GameInfoTypes = { MISSION_MOVE_TO = 1 }
Locale = { ConvertTextKey = function(k) return k end }
GameInfo = { Terrains = { [0] = { Type = 'TERRAIN_GRASS' }, [1] = { Type = 'TERRAIN_COAST' } },
             Features = { [0] = { Type = 'FEATURE_FOREST' } },
             Units = { [1] = { Type = 'UNIT_WARRIOR' }, [2] = { Type = 'UNIT_BRUTE' }, [3] = { Type = 'UNIT_ARCHER', Range = 2 },
                       [4] = { Type = 'UNIT_WORKER' } },
             Improvements = {}, Routes = {}, Resources = {} }

Players = {
  [0] = { GetTeam = function() return 0 end, IsBarbarian = function() return false end, IsMinorCiv = function() return false end,
          GetCivilizationShortDescription = function() return 'Venice' end,
          GetUnitByID = function(_, id) return UNITS[id] end },
  [3] = { GetTeam = function() return 3 end, IsBarbarian = function() return false end, IsMinorCiv = function() return false end,
          GetCivilizationShortDescription = function() return 'Persia' end },
  [63] = { GetTeam = function() return 63 end, IsBarbarian = function() return true end, IsMinorCiv = function() return false end },
}
Teams = { [0] = { IsAtWar = function(_, t) return t == 63 end, IsHasMet = function(_, t) return t == 3 end,
                  CanEmbark = function() return false end },
          [3] = { IsAllowsOpenBordersToTeam = function() return false end },
          [63] = {} }

-- hex geometry: odd-r offset, x wraps
local function wrapx(x) return x % W end
local function cube(x, y) local q = x - (y - (y % 2)) / 2; return q, y end
function hexdist(x1, y1, x2, y2)
  local best
  for _, s in ipairs({ -W, 0, W }) do
    local q1, r1 = cube(x1, y1); local q2, r2 = cube(x2 + s, y2)
    local dq, dr = q1 - q2, r1 - r2
    local d = math.max(math.abs(dq), math.abs(dr), math.abs(dq + dr))
    if not best or d < best then best = d end
  end
  return best
end
local EVEN = { {0, 1}, {1, 0}, {0, -1}, {-1, -1}, {-1, 0}, {-1, 1} }
local ODD  = { {1, 1}, {1, 0}, {1, -1}, {0, -1}, {-1, 0}, {0, 1} }

P = {}
function plot(x, y, o)
  o = o or {}
  local p = {
    o = o,
    GetX = function() return x end, GetY = function() return y end,
    IsRevealed = function() return o.revealed ~= false end,
    IsVisible = function() return o.revealed ~= false and o.fog ~= true end,
    GetTerrainType = function() return o.water and 1 or 0 end,
    IsHills = function() return o.hills == true end, IsMountain = function() return o.mountain == true end,
    IsImpassable = function() return false end,
    IsWater = function() return o.water == true end,
    IsRiver = function() return o.river == true end,
    IsWOfRiver = function() return o.w_of_river == true end,
    IsNWOfRiver = function() return o.nw_of_river == true end,
    IsNEOfRiver = function() return o.ne_of_river == true end,
    GetResourceType = function() return -1 end,
    GetRevealedImprovementType = function() return -1 end,
    GetRevealedRouteType = function() return -1 end,
    GetRevealedOwner = function() return o.rowner or -1 end,
    IsCity = function() return o.city ~= nil end,
    GetPlotCity = function() return o.city end,
    GetNumUnits = function() return #(o.units or {}) end,
    GetUnit = function(_, i) return (o.units or {})[i + 1] end,
  }
  if o.fog then
    p.GetFeatureType = forbidden('GetFeatureType'); p.GetImprovementType = forbidden('GetImprovementType')
    p.GetRouteType = forbidden('GetRouteType'); p.GetOwner = forbidden('GetOwner')
    p.GetUnit = forbidden('GetUnit')
  else
    p.GetFeatureType = function() return o.forest and 0 or -1 end
    p.GetImprovementType = function() return -1 end
    p.GetRouteType = function() return -1 end
    p.GetOwner = function() return o.owner or -1 end
  end
  P[x .. ',' .. y] = p
  return p
end
for y = 0, HT - 1 do for x = 0, W - 1 do plot(x, y) end end

Map = {
  GetGridSize = function() return W, HT end,
  IsWrapX = function() return true end,
  GetPlot = function(x, y) return P[x .. ',' .. y] end,
  PlotDistance = hexdist,
  PlotDirection = function(x, y, d)
    local off = ((y % 2 == 1) and ODD or EVEN)[d + 1]
    local ny = y + off[2]
    if ny < 0 or ny >= HT then return nil end
    return P[wrapx(x + off[1]) .. ',' .. ny]
  end,
  PlotXYWithRangeCheck = function(x, y, dx, dy, r)
    local ny = y + dy
    if ny < 0 or ny >= HT then return nil end
    local q = P[wrapx(x + dx) .. ',' .. ny]
    if hexdist(x, y, q:GetX(), ny) > r then return nil end
    return q
  end,
}

UNITS = {}
function unit(id, owner, typ, x, y, o)
  o = o or {}
  local u = {
    GetID = function() return id end, GetOwner = function() return owner end, GetTeam = function() return Players[owner]:GetTeam() end,
    GetX = function() return x end, GetY = function() return y end,
    GetPlot = function() return P[x .. ',' .. y] end,
    GetUnitType = function() return typ end,
    MovesLeft = function() return (o.moves or 2) * 60 end, MaxMoves = function() return 120 end,
    GetCurrHitPoints = function() return o.hp or 100 end, GetMaxHitPoints = function() return 100 end,
    GetDomainType = function() return 0 end, IsEmbarked = function() return false end,
    IsCombatUnit = function() return o.civilian ~= true end,
    GetBaseCombatStrength = function() return o.strength or 8 end,
    GetRangedCombatStrength = function() return o.ranged or 0 end,
    IsInvisible = function() return false end, IsDelayedDeath = function() return false end,
    IsHasPromotion = function() return false end,
    CanStartMission = function(_, m, tx, ty) return true end,
  }
  if owner == 0 then UNITS[id] = u end
  local here = P[x .. ',' .. y].o
  here.units = here.units or {}
  here.units[#here.units + 1] = u
  return u
end

-- the existing combat previews, canned: the view must hand these rows through, not compute its own
MELEE, RANGED = {}, {}
H.melee_targets = function(u, pid) return MELEE end
H.ranged_targets = function(u, pid) return RANGED end
H.seen_features = { [0] = {} }
"""


class TacticalViewLuaTests(unittest.TestCase):
    run_lua = support.LuaRuntimeTests.run_lua

    def setUp(self):
        support.LuaRuntimeTests.setUp(self)
        self.run_lua(WORLD)

    def test_neighbours_across_the_wrap_seam_are_the_engines_and_all_adjacent(self):
        self.run_lua("""
        unit(1, 0, 1, 0, 2)
        local v = H.tactical_view(1, 0, 2, 'summary')
        assert(v.ok and v.unit.x == 0 and v.unit.y == 2, 'the unit')
        local want = { NE = {0, 3}, E = {1, 2}, SE = {0, 1}, SW = {7, 1}, W = {7, 2}, NW = {7, 3} }
        assert(#v.neighbors == 6)
        for _, n in ipairs(v.neighbors) do
          local w = want[n.dir]
          assert(w and n.x == w[1] and n.y == w[2], n.dir .. ' is ' .. tostring(n.x) .. ',' .. tostring(n.y))
          assert(hexdist(0, 2, n.x, n.y) == 1, n.dir .. ' is adjacent')
          assert(n.move == 'open', n.dir .. ' ' .. tostring(n.move) .. ' ' .. tostring(n.why))
        end
        assert(v.map.wrap_x == true)
        assert(v.grid.cols[1] == 6 and v.grid.cols[2] == 7 and v.grid.cols[3] == 0, 'wrapped column xs')
        """)

    def test_edge_rows_are_off_the_map_not_invented(self):
        self.run_lua("""
        unit(1, 0, 1, 2, 0)
        local v = H.tactical_view(1, 0, 2, 'summary')
        local off = {}
        for _, n in ipairs(v.neighbors) do if n.off_map then off[n.dir] = n end end
        assert(off.SE and off.SW and not off.NE and not off.E, 'the south row is the edge')
        assert(off.SE.move == 'refused' and off.SE.x == nil, 'nothing is made up beyond it')
        assert(#v.grid.rows == 3, 'rows y=2..0 only: ' .. #v.grid.rows)
        assert(v.grid.rows[1]:sub(1, 3) == '  2' and v.grid.rows[3]:sub(1, 3) == '  0', v.grid.rows[1])
        """)

    def test_move_is_move_units_own_refusal(self):
        self.run_lua("""
        unit(1, 0, 1, 2, 2)
        unit(2, 0, 1, 3, 2)                             -- E: our own warrior (one combat unit per plot)
        P['1,3'].o.mountain = true                      -- NE of (2,2) on an even row is (2,3); NW is (1,3)
        P['2,3'].o.revealed = false                     -- NE unrevealed
        P['2,1'].o.fog = true; P['2,1'].o.rowner = 3    -- SE fogged, last seen inside Persia (no open borders)
        P['1,1'].o.water = true                         -- SW water, no embarkation
        local v = H.tactical_view(1, 0, 2, 'summary')
        local by = {}; for _, n in ipairs(v.neighbors) do by[n.dir] = n end
        assert(by.E.move == 'refused' and by.E.why:find('one per tile', 1, true), tostring(by.E.why))
        assert(by.NW.move == 'refused' and by.NW.why:find('mountain', 1, true), tostring(by.NW.why))
        assert(by.NE.move == 'refused' and by.NE.vis == 'unrevealed' and by.NE.t == nil, 'unrevealed shows nothing')
        assert(by.SE.move == 'refused' and by.SE.why:find('Persia', 1, true), 'closed border from the last-seen owner: ' .. tostring(by.SE.why))
        assert(by.SE.vis == 'fogged' and by.SE.owner == 3 and v.players['3'] == 'Persia')
        assert(by.SW.move == 'refused' and by.SW.why:find('cannot embark', 1, true), tostring(by.SW.why))
        assert(by.W.move == 'open' and by.W.why == nil)
        """)

    def test_the_engines_no_is_reported_and_spent_moves_are_said(self):
        self.run_lua("""
        local u = unit(1, 0, 1, 2, 2)
        u.CanStartMission = function() return false end
        local v = H.tactical_view(1, 0, 1, 'summary')
        assert(v.neighbors[2].move == 'refused' and v.neighbors[2].why == 'move is not currently legal')
        u.MovesLeft = function() return 0 end
        v = H.tactical_view(1, 0, 1, 'summary')
        assert(v.note and v.note:find('no moves left', 1, true))
        assert(v.unit.moves == 0)
        """)

    def test_fog_never_gains_live_units_owners_or_cities(self):
        self.run_lua("""
        unit(1, 0, 1, 2, 2)
        P['3,3'].o.fog = true                           -- a fogged plot next door (NE on an even row is (2,3); E is (3,2))
        P['3,2'].o.fog = true
        unit(9, 63, 2, 3, 2)                            -- a Brute under that fog: never seen, never read (GetUnit raises)
        P['1,3'].o.fog = true
        P['1,3'].o.city = { GetName = function() return 'Hidden' end, GetOwner = function() return 3 end,
                            IsRevealed = function() return false end, GetTeam = function() return 3 end }
        P['2,0'].o.fog = true
        P['2,0'].o.city = { GetName = function() return 'Pasargadae' end, GetOwner = function() return 3 end,
                            IsRevealed = function() return true end, GetTeam = function() return 3 end }
        local v = H.tactical_view(1, 0, 2, 'summary')
        assert(#v.occupants == 0, 'the fogged Brute is not an occupant')
        local e; for _, n in ipairs(v.neighbors) do if n.dir == 'E' then e = n end end
        assert(e.vis == 'fogged' and e.units == nil and e.move == 'open', 'fog: last seen, no occupant')
        assert(#v.cities == 1 and v.cities[1].name == 'Pasargadae' and v.cities[1].last_seen and v.cities[1].hp == nil,
               'only the city whose banner we have, without live hp')
        assert(v.fog.fogged == 4 and v.fog.unseen_within_2 == 4, 'fog counted: ' .. v.fog.fogged)
        for _, r in ipairs(v.grid.rows) do assert(not r:find('X', 1, true), 'no hostile mark in fog: ' .. r) end
        """)

    def test_visible_occupants_hostile_first_and_bounded_by_radius(self):
        self.run_lua("""
        unit(1, 0, 1, 2, 2)
        unit(5, 0, 4, 1, 2, { civilian = true })        -- our worker, W
        unit(7, 63, 3, 4, 2, { ranged = 7 })            -- a barbarian archer two plots east
        unit(8, 3, 1, 5, 2)                             -- a Persian warrior three plots east: outside radius 2
        local v = H.tactical_view(1, 0, 2, 'summary')
        assert(#v.occupants == 2, 'radius bounds the list: ' .. #v.occupants)
        assert(v.occupants[1].id == 7 and v.occupants[1].hostile and v.occupants[1].distance == 2, 'hostile first')
        assert(v.occupants[1].ranged_strength == 7 and v.occupants[1].range == 2, 'visible evidence of its reach')
        assert(v.occupants[2].id == 5 and v.occupants[2].civilian and not v.occupants[2].hostile)
        assert(v.players['63'] == 'Barbarians' and v.players['0'] == 'you')
        local row = v.grid.rows[3]                      -- y = 2
        assert(row:find('@', 1, true) and row:find('X', 1, true) and row:find('u', 1, true), row)
        v = H.tactical_view(1, 0, 3, 'summary')
        assert(#v.occupants == 3 and #v.grid.rows == 5, 'radius 3 reaches the Persian; rows clip at the map')
        """)

    def test_grid_corners_beyond_the_radius_are_blank(self):
        self.run_lua("""
        unit(1, 0, 1, 2, 2)
        unit(7, 63, 3, 4, 3)                            -- the box's NE corner at radius 2, three hex steps away
        assert(hexdist(2, 2, 4, 3) == 3)
        local v = H.tactical_view(1, 0, 2, 'summary')
        assert(#v.occupants == 0, 'beyond the radius: no occupant row')
        local row = v.grid.rows[2]                      -- y = 3, odd: one pad space after the label
        assert(row:sub(-2) == '  ', 'the corner is blank, not drawn: [' .. row .. ']')
        for _, r in ipairs(v.grid.rows) do assert(not r:find('X', 1, true), 'no hostile drawn: ' .. r) end
        """)

    def test_a_city_stays_drawn_under_the_unit_standing_in_it(self):
        """GitLab #177 (Celts t4): a Scout standing on Edinburgh read ".@" -- the unit mark replaced the city's -- while
        cities[] still had Edinburgh at distance 0. A city is the cell's ground, its units the occupant."""
        self.run_lua("""
        local function city(name, owner)
          return { GetName = function() return name end, GetOwner = function() return owner end,
                   GetPopulation = function() return 1 end, GetMaxHitPoints = function() return 200 end,
                   GetDamage = function() return 0 end, IsRevealed = function() return true end }
        end
        unit(1, 0, 1, 2, 2)
        P['2,2'].o.city = city('Edinburgh', 0)           -- the Scout's own plot
        P['0,2'].o.city = city('Dunedin', 0)             -- our city with our worker in it
        unit(5, 0, 4, 0, 2, { civilian = true })
        P['4,2'].o.city = city('Susa', 3)                -- Persia's, at peace, empty
        local v = H.tactical_view(1, 0, 2, 'summary')
        assert(v.grid.rows[3] == '  2 Cu. C@. C ', '[' .. v.grid.rows[3] .. ']')
        assert(v.cities[1].name == 'Edinburgh' and v.cities[1].distance == 0)
        Teams[0].IsAtWar = function(_, t) return t == 63 or t == 3 end
        v = H.tactical_view(1, 0, 2, 'summary')
        assert(v.grid.rows[3] == '  2 Cu. C@. CX', 'an enemy city: [' .. v.grid.rows[3] .. ']')
        P['4,2'].o.fog = true                            -- a fogged city: remembered terrain, never a live read
        v = H.tactical_view(1, 0, 2, 'summary')
        assert(v.grid.rows[3] == '  2 Cu. C@. .?', 'fog: [' .. v.grid.rows[3] .. ']')
        """)

    def test_targets_are_the_existing_previews_and_mark_the_neighbour(self):
        self.run_lua("""
        unit(1, 0, 1, 2, 2)
        unit(7, 63, 2, 3, 2)                            -- a Brute on E
        MELEE = { { x = 3, y = 2, unit = 'BRUTE', owner = 'Barbarians', how = 'move_unit onto this plot attacks',
                    preview = { expected_damage_dealt = 30, expected_damage_taken = 12, modifiers = { { text = 'flank' } } } } }
        local v = H.tactical_view(1, 0, 2, 'summary')
        local e; for _, n in ipairs(v.neighbors) do if n.dir == 'E' then e = n end end
        assert(e.move == 'attack', tostring(e.move))
        assert(#v.targets == 1 and v.targets[1].kind == 'melee' and v.targets[1].preview.expected_damage_dealt == 30)
        assert(v.targets[1].preview.modifiers == nil, 'summary drops the modifier rows')
        assert(v.targets[1].preview.modifiers_brief == nil, 'rows without a side: nothing to brief')
        MELEE[1].preview.modifiers = { mine = { { text = 'Fortified', value = 20, percent = true }, { text = 'vs Barbarians', value = 33, percent = true } },
                                       theirs = { { text = 'Hills', value = 25, percent = true } } }
        v = H.tactical_view(1, 0, 2, 'summary')
        assert(v.targets[1].preview.modifiers == nil and v.targets[1].preview.modifiers_brief.mine == 'Fortified +20%; vs Barbarians +33%'
               and v.targets[1].preview.modifiers_brief.theirs == 'Hills +25%', H.json(v.targets[1].preview))   -- #121: one line a side
        MELEE[1].preview.modifiers = { { text = 'flank' } }
        v = H.tactical_view(1, 0, 2, 'full')
        assert(v.targets[1].preview.modifiers[1].text == 'flank', 'full keeps them')
        assert(v.plots and #v.plots == 19, 'full adds every revealed plot in radius: ' .. tostring(v.plots and #v.plots))
        """)

    def test_a_ranged_unit_beside_an_enemy_sees_enemy_not_open(self):
        self.run_lua("""
        unit(1, 0, 3, 2, 2, { ranged = 7 })
        unit(7, 63, 2, 3, 2)
        RANGED = { { x = 3, y = 2, how = 'unit_mission MISSION_RANGE_ATTACK with x, y', preview = { expected_damage_dealt = 20 } } }
        local v = H.tactical_view(1, 0, 2, 'summary')
        local e; for _, n in ipairs(v.neighbors) do if n.dir == 'E' then e = n end end
        assert(e.move == 'enemy' and e.why:find('ranged unit shoots', 1, true), tostring(e.why))
        assert(v.targets[1].kind == 'ranged' and v.unit.range == 2)
        """)

    def test_a_melee_unit_with_spent_moves_is_told_so(self):
        """Live t42: a Warrior with no moves beside a Barbarian read "no melee attack"; melee_targets is empty only
        because its moves are spent."""
        self.run_lua("""
        unit(1, 0, 1, 2, 2, { moves = 0 })
        unit(7, 63, 2, 3, 2)
        local v = H.tactical_view(1, 0, 1, 'summary')
        local e; for _, n in ipairs(v.neighbors) do if n.dir == 'E' then e = n end end
        assert(e.move == 'enemy' and e.why:find('no moves left', 1, true), tostring(e.why))
        """)

    def test_a_land_unit_beside_a_ship_at_sea_is_told_it_cannot_attack_there(self):
        """Live t60 (Codex): a Warrior beside a barbarian Galley on the coast read "attack" and move_unit refused the
        plot as occupied. The domain rule lives in H.melee_domain_refusal, which melee_defender applies."""
        self.run_lua("""
        plot(3, 2, { water = true })
        unit(1, 0, 1, 2, 2)
        unit(7, 63, 2, 3, 2)
        assert(H.melee_defender(UNITS[1], Map.GetPlot(3, 2), 0) == nil, 'no melee defender at sea for a land unit')
        local v = H.tactical_view(1, 0, 1, 'summary')
        local e; for _, n in ipairs(v.neighbors) do if n.dir == 'E' then e = n end end
        assert(e.move == 'enemy' and e.why:find('cannot attack a unit at sea', 1, true), tostring(e.why))
        -- the same fight on land is the melee_defender's to name
        plot(3, 2, {})
        unit(8, 63, 2, 3, 2)
        assert(H.melee_defender(UNITS[1], Map.GetPlot(3, 2), 0) ~= nil, 'a land enemy is a melee defender')
        -- a ship beside a land unit
        local ship = unit(2, 0, 1, 4, 2)
        ship.GetDomainType = function() return DomainTypes.DOMAIN_SEA end
        assert(H.melee_domain_refusal(ship, Map.GetPlot(3, 2)):find('ship cannot attack', 1, true))
        -- an embarked land unit fights nowhere
        local emb = unit(3, 0, 1, 5, 2)
        emb.IsEmbarked = function() return true end
        assert(H.melee_domain_refusal(emb, Map.GetPlot(3, 2)):find('embarked', 1, true))
        """)

    def test_river_crossings_read_the_edge_owner(self):
        self.run_lua("""
        unit(1, 0, 1, 2, 2)
        P['2,2'].o.w_of_river = true                    -- river on (2,2)'s east edge
        P['1,2'].o.w_of_river = true                    -- river on the west neighbour's east edge = our west edge
        P['1,3'].o.nw_of_river = true                   -- NW neighbour's south-east edge = our north-west edge
        P['2,2'].o.ne_of_river = true                   -- our south-west edge
        local v = H.tactical_view(1, 0, 1, 'summary')
        local by = {}; for _, n in ipairs(v.neighbors) do by[n.dir] = n.river_crossing or false end
        assert(by.E and by.W and by.NW and by.SW, 'crossings')
        assert(not by.NE and not by.SE, 'no crossing')
        """)


    # v261: the view sized to the unit's own sight (the engine's canSeePlot stands in here as a distance rule).
    def test_without_a_radius_the_view_reaches_as_far_as_the_unit_sees(self):
        self.run_lua("""
        unit(1, 0, 3, 3, 2, { ranged = 5 })               -- an archer (range 2) on a hill
        P['3,2'].o.hills = true
        UNITS[1].VisibilityRange = function() return 2 end
        UNITS[1].IsRangeAttackIgnoreLOS = function() return false end
        for _, q in pairs(P) do q.CanSeePlot = function(self, other, team, range) return hexdist(self:GetX(), self:GetY(), other:GetX(), other:GetY()) <= range + 1 end end
        local open = P['3,2'].CanSeePlot                   -- the test is asked of the viewer's plot, as the engine's is
        P['3,2'].CanSeePlot = function(self, other, team, range) if other:GetX() == 6 and other:GetY() == 2 then return false end return open(self, other, team, range) end  -- three plots east, behind something
        unit(8, 3, 1, 0, 2)                                -- a Persian warrior three plots west: in sight
        unit(9, 3, 1, 6, 2)                                -- a Persian warrior three plots east: seen by the team, not by this unit
        P['3,2'].o.city = { GetName = function() return 'Sukhothai' end, GetOwner = function() return 0 end,
                            GetMaxHitPoints = function() return 200 end, GetDamage = function() return 0 end,
                            GetStrengthValue = function() return 1200 end, IsRevealed = function() return true end }   -- the archer's own city (#131)
        local v = H.tactical_view(1, 0, nil, 'summary')
        local own = nil; for _, c in ipairs(v.cities or {}) do if c.distance == 0 then own = c end end
        assert(own and own.in_sight == true and own.in_fire_los == false, 'the unit sees the city it stands in; it cannot fire at its own plot: ' .. H.json(v.cities))
        assert(v.radius == 3 and v.radius_from == 'sight', tostring(v.radius) .. ' ' .. tostring(v.radius_from))
        assert(v.unit.sight.on_hills == true and v.unit.sight.range == 2, 'sight range')
        assert(v.unit.sight.reach == 3 and v.unit.sight.plots == 27, 'ring three on a five-row map minus one blocked: ' .. v.unit.sight.plots)
        assert(v.unit.fire_los.range == 2 and v.unit.fire_los.reach == 3 and v.unit.fire_los.plots == 27, 'fire LOS')
        assert(v.unit.fire_los.ignores_los == nil)
        assert(#v.grid.rows == 5, 'the grid covers the sight radius')
        local by = {}; for _, o in ipairs(v.occupants) do by[o.id] = o end
        assert(by[8] and by[8].in_sight == true and by[8].in_fire_los == true, 'west warrior in the sight of this unit')
        assert(by[9] and by[9].in_sight == false and by[9].in_fire_los == false, 'east warrior listed (team sees it) but not in the sight of this unit')
        """)

    def test_a_given_radius_is_kept_and_flat_ground_keeps_the_default(self):
        self.run_lua("""
        unit(1, 0, 1, 3, 2)                                -- a warrior on flat ground
        UNITS[1].VisibilityRange = function() return 2 end
        for _, q in pairs(P) do q.CanSeePlot = function(self, other, team, range) return hexdist(self:GetX(), self:GetY(), other:GetX(), other:GetY()) <= range end end
        local v = H.tactical_view(1, 0, nil, 'summary')
        assert(v.radius == 2 and v.radius_from == 'default', tostring(v.radius) .. ' ' .. tostring(v.radius_from))
        assert(v.unit.sight.plots == 18 and v.unit.sight.reach == 2 and v.unit.sight.on_hills == false, v.unit.sight.plots)
        assert(v.unit.fire_los == nil, 'a melee unit has no fire LOS')
        UNITS[1].VisibilityRange = function() return 4 end
        v = H.tactical_view(1, 0, 2, 'summary')
        assert(v.radius == 2 and v.radius_from == 'given', 'a given radius stands')
        v = H.tactical_view(1, 0, nil, 'summary')
        assert(v.radius == 4 and v.radius_from == 'sight', 'a far-seeing unit widens the default: ' .. v.radius)
        """)

    def test_indirect_fire_covers_its_range_without_line_of_sight(self):
        self.run_lua("""
        unit(1, 0, 3, 3, 2, { ranged = 5 })
        UNITS[1].VisibilityRange = function() return 2 end
        UNITS[1].IsRangeAttackIgnoreLOS = function() return true end
        for _, q in pairs(P) do q.CanSeePlot = function() return false end end
        local v = H.tactical_view(1, 0, nil, 'summary')
        assert(v.unit.sight.plots == 0, 'nothing in sight by the plot rule')
        assert(v.unit.fire_los.ignores_los == true and v.unit.fire_los.plots == 18 and v.unit.fire_los.reach == 2, 'range alone: ' .. v.unit.fire_los.plots)
        assert(v.radius == 2 and v.radius_from == 'default')
        """)

    def test_an_engine_without_canseeplot_keeps_the_old_view(self):
        self.run_lua("""
        unit(1, 0, 1, 3, 2)
        local v = H.tactical_view(1, 0, nil, 'summary')
        assert(v.radius == 2 and v.radius_from == 'default')
        assert(v.unit.sight.plots == 0 and v.unit.sight.range == 0, 'no VisibilityRange, no CanSeePlot: empty, not an error')
        for _, o in ipairs(v.occupants) do assert(o.in_sight == nil) end
        """)

    # v262: the engine has no Unit:GetRangedCombatStrength; the base figure is GetBaseRangedCombatStrength.
    def test_a_ranged_unit_is_known_by_the_engines_own_getter(self):
        self.run_lua("""
        unit(1, 0, 3, 3, 2)                                -- an archer, the test double's old getter removed
        UNITS[1].GetRangedCombatStrength = nil
        UNITS[1].GetBaseRangedCombatStrength = function() return 18 end
        UNITS[1].Range = function() return 3 end           -- a promotion's extra range counts
        UNITS[1].VisibilityRange = function() return 2 end
        for _, q in pairs(P) do q.CanSeePlot = function(self, other, team, range) return hexdist(self:GetX(), self:GetY(), other:GetX(), other:GetY()) <= range end end
        unit(8, 3, 1, 6, 2)                                -- a Persian warrior three plots east
        local v = H.tactical_view(1, 0, nil, 'summary')
        assert(v.unit.ranged_strength == 18 and v.unit.range == 3, 'ranged by GetBaseRangedCombatStrength, range by Range()')
        assert(v.unit.fire_los and v.unit.fire_los.range == 3 and v.unit.fire_los.reach == 3, 'fire LOS from Range()')
        assert(v.radius == 3 and v.radius_from == 'sight', 'the view reaches the shot: ' .. tostring(v.radius))
        local by = {}; for _, o in ipairs(v.occupants) do by[o.id] = o end
        assert(by[8].in_fire_los == true and by[8].in_sight == false, 'in the fire LOS at three, past the sight of two')
        assert(H.ranged_strength({}) == 0, 'a unit with neither getter is not ranged')
        assert(H.ranged_strength({ GetRangedCombatStrength = function() return 7 end }) == 7, 'the old name still answers for test doubles')
        """)

class CivilianStackingTests(unittest.TestCase):
    """Grok (Venice/Mongolia 2026-09-27): tactical_view called a Worker's move onto another Worker's plot "open",
    and move_unit then answered "unit did not move: your WORKER already holds it". The view's `refused` is
    H.move_refusal, so the one-civilian-per-tile rule lives there now, beside the combat one."""
    run_lua = support.LuaRuntimeTests.run_lua

    def setUp(self):
        support.LuaRuntimeTests.setUp(self)
        self.run_lua(WORLD)

    def refusal(self, setup):
        self.run_lua(setup)
        self.run_lua("""
        local r = H.move_refusal(UNITS[1], P['3,2'], 0, true)
        OUT = r and r.err or 'open'
        """)
        try:
            self.run_lua("error(OUT, 0)")
        except AssertionError as e:
            return str(e)
        return ""

    def test_a_worker_is_refused_onto_another_workers_plot_by_name(self):
        out = self.refusal("unit(1, 0, 4, 2, 2, { civilian = true }); unit(2, 0, 4, 3, 2, { civilian = true })")
        self.assertIn("already holds your WORKER 2", out)
        self.assertIn("one civilian per tile", out)

    def test_a_worker_may_join_a_warrior_and_pass_a_caravan_on_its_route(self):
        out = self.refusal("unit(1, 0, 4, 2, 2, { civilian = true }); unit(2, 0, 1, 3, 2)")
        self.assertIn("open", out, "a combat unit does not fill the civilian slot")
        out = self.refusal("""
        unit(1, 0, 4, 2, 2, { civilian = true })
        local c = unit(2, 0, 4, 3, 2, { civilian = true })
        c.IsAutomated = function() return true end; c.IsTrade = function() return true end
        """)
        self.assertIn("open", out, "a caravan walking its route passes through")

    def test_an_automated_worker_still_holds_its_plot(self):
        """Live Assyria t135: a Great Prophet ordered onto an automated Worker's plot was dropped by the engine
        with "no path"; automation is not a trade route, the plot is taken."""
        out = self.refusal("""
        unit(1, 0, 4, 2, 2, { civilian = true })
        local c = unit(2, 0, 4, 3, 2, { civilian = true }); c.IsAutomated = function() return true end
        """)
        self.assertIn("already holds your WORKER 2 (automated; it still holds the plot)", out)

    def test_the_combat_rule_is_unchanged(self):
        out = self.refusal("unit(1, 0, 1, 2, 2); unit(2, 0, 1, 3, 2)")
        self.assertIn("one of your combat units", out)


class TacticalViewQueryTests(unittest.TestCase):
    def test_game_bounds_radius_and_detail(self):
        g = Game.__new__(Game)
        g.seat = 0
        seen = []
        g.q = lambda code, timeout=None: seen.append(code) or {"ok": True}
        g.tactical_view(12)
        g.tactical_view(12, radius=4, detail="full")
        self.assertEqual(seen, ['return H.tactical_view(12, 0, nil, "summary")', 'return H.tactical_view(12, 0, 4, "full")'])
        for bad in ({"radius": 0}, {"radius": 6}, {"detail": "normal"}):
            with self.assertRaises(ValueError):
                g.tactical_view(12, **bad)

    def test_the_legend_is_said_once_per_process_then_a_key(self):
        """GitLab #152: the legend rode on every tactical read (about 2 KB a time); it is the reply reference, sent
        once, and a one-line `key` after that names the section that holds it."""
        from harness import legend
        g = Game.__new__(Game)
        g.seat = 0
        g.q = lambda code, timeout=None: {"ok": True, "neighbors": [{"dir": "E", "x": 3, "y": 2, "move": "open"}]}
        first = g.tactical_view(12)
        self.assertIn("odd rows sit half a cell to the right", first["legend"], "the first reply carries the whole legend")
        self.assertIn("never reported safe", first["legend"])
        self.assertNotIn("key", first)
        self.assertFalse(first["legend"].startswith("##"), "the heading is not part of the legend")
        second = g.tactical_view(12, radius=3)
        self.assertNotIn("legend", second)
        self.assertEqual(second["key"], legend.KEY)
        self.assertIn(legend.TOPIC, second["key"], "the key names the reference section")
        self.assertLess(len(legend.KEY), 320)
        self.assertEqual(second["neighbors"][0]["call"], {"tool": "order", "args": {"to": "unit", "action": "move", "id": 12, "args": {"x": 3, "y": 2}}})
        other = Game.__new__(Game)
        other.seat = 1
        other.q = g.q
        self.assertIn("legend", other.tactical_view(12), "another process starts over")

    def test_the_legend_is_the_reply_reference(self):
        from harness import guide, legend
        self.assertIn(legend.TOPIC, guide.reply_topics(), "docs/TOOL_REPLIES.md holds the view's legend")
        self.assertIn("## " + legend.TOPIC, guide.how_to_play(legend.TOPIC), "reference(book='playbook', section=...) serves it")
        self.assertEqual(legend.text(), guide.reply_topic(legend.TOPIC).strip().split("\n", 1)[1].strip())

    def test_the_tool_is_a_read(self):
        from harness import mcp_server
        from harness.surface import classes
        self.assertIn(classes.of_handler("tactical_view"), classes.READ)
        self.assertIn(classes.of_handler("explore_frontier"), classes.READ)
        self.assertTrue(callable(mcp_server.tactical_view))


if __name__ == "__main__":
    unittest.main()
