"""What a step costs, on the tactical view's neighbours (GitLab #180).

Celts t11 (three-seat hotseat): the view showed a plains neighbour as `move: open` and nothing else; the Warrior had 2
moves and arrived with 0 -- a barbarian stood next to both plots, and zone of control ends a move from one plot next to
an enemy to another plot next to the same enemy. A Scout stepping out of a barbarian's reach on t16 did the same. The
engine's Plot:MovementCost crashed the game (t183), so step_cost.lua reads BNW's CvUnitMovement::MovementCost off the
engine's own getters and tables; these tests pin each rule on the tactical view's mocked 8 x 5 map
(tests/test_tactical_view.py WORLD), unit at (2,2): NE (2,3), E (3,2), SE (2,1), SW (1,1), W (1,2), NW (1,3).
"""
import unittest

import test_mcp_safety as support
from test_tactical_view import WORLD


COSTS = r"""
GameInfo.Terrains[0].Movement = 1; GameInfo.Terrains[1].Movement = 1
GameInfo.Features[0].Movement = 2
GameInfo.Routes = { [0] = { Type = 'ROUTE_ROAD', Movement = 30, FlatMovement = 30 } }
function by_dir(v) local by = {}; for _, n in ipairs(v.neighbors) do by[n.dir] = n end; return by end
function road(x, y) P[x .. ',' .. y].GetRouteType = function() return 0 end end
function city(name, owner)
  return { GetName = function() return name end, GetOwner = function() return owner end, GetPopulation = function() return 1 end,
           GetMaxHitPoints = function() return 200 end, GetDamage = function() return 0 end, IsRevealed = function() return true end }
end
"""


class StepCostTests(unittest.TestCase):
    run_lua = support.LuaRuntimeTests.run_lua

    def setUp(self):
        support.LuaRuntimeTests.setUp(self)
        self.run_lua(WORLD)
        self.run_lua(COSTS)

    def test_zone_of_control_ends_the_move_and_names_the_enemy(self):
        """The #180 shape: an open plains step next to the barbarian that also stands next to the unit."""
        self.run_lua("""
        unit(1, 0, 1, 2, 2)                              -- a Warrior with 2 moves
        unit(7, 63, 2, 3, 2)                             -- a barbarian Brute on E, next to NE (2,3) and SE (2,1)
        local by = by_dir(H.tactical_view(1, 0, 1, 'summary'))
        for _, d in ipairs({ 'NE', 'SE' }) do
          local n = by[d]
          assert(n.move == 'open', d .. ' is still a legal move: ' .. tostring(n.move))
          assert(n.cost == 2 and n.left == 0, d .. ' spends every move: ' .. H.json(n))
          assert(n.zoc and n.zoc.id == 7 and n.zoc.unit == 'BRUTE' and n.zoc.x == 3 and n.zoc.y == 2 and n.zoc.owner == 63, H.json(n.zoc))
        end
        assert(by.W.cost == 1 and by.W.left == 1 and by.W.zoc == nil, 'W is out of the Brute\\'s reach: ' .. H.json(by.W))
        assert(by.E.cost == nil, 'no cost on a plot that is not an open step')
        """)

    def test_only_a_visible_enemy_combat_unit_on_land_exerts_it(self):
        self.run_lua("""
        unit(1, 0, 1, 2, 2)
        GameInfo.Units[4].Description = 'Worker'
        local worker = unit(7, 63, 4, 3, 2, { civilian = true })   -- a captured worker: no zone of control
        local by = by_dir(H.tactical_view(1, 0, 1, 'summary'))
        assert(by.NE.zoc == nil and by.NE.cost == 1, 'a civilian: ' .. H.json(by.NE))
        worker.IsCombatUnit = function() return true end
        worker.GetOwner = function() return 3 end                 -- Persia, met and at peace
        by = by_dir(H.tactical_view(1, 0, 1, 'summary'))
        assert(by.NE.zoc == nil, 'a unit we are at peace with: ' .. H.json(by.NE))
        worker.GetOwner = function() return 63 end
        worker.IsEmbarked = function() return true end
        by = by_dir(H.tactical_view(1, 0, 1, 'summary'))
        assert(by.NE.zoc == nil, 'an embarked enemy exerts none on a land unit')
        worker.IsEmbarked = function() return false end
        worker.IsInvisible = function() return true end
        by = by_dir(H.tactical_view(1, 0, 1, 'summary'))
        assert(by.NE.zoc == nil, 'an enemy we cannot see')
        worker.IsInvisible = function() return false end
        by = by_dir(H.tactical_view(1, 0, 1, 'summary'))
        assert(by.NE.zoc and by.NE.zoc.id == 7 and by.NE.left == 0, 'now it does: ' .. H.json(by.NE))
        """)

    def test_an_enemy_city_exerts_it_and_an_ignore_zoc_promotion_lifts_it(self):
        self.run_lua("""
        Teams[0].IsAtWar = function(_, t) return t == 63 or t == 3 end
        unit(1, 0, 1, 2, 2)
        P['3,2'].o.city = city('Susa', 3)
        local by = by_dir(H.tactical_view(1, 0, 1, 'summary'))
        assert(by.NE.zoc and by.NE.zoc.city == 'Susa' and by.NE.zoc.id == nil and by.NE.left == 0, H.json(by.NE))
        local rows = { { ID = 5, IgnoreZOC = false }, { ID = 9, IgnoreZOC = true } }
        GameInfo.UnitPromotions = function() local i = 0; return function() i = i + 1; return rows[i] end end
        UNITS[1].IsHasPromotion = function(_, id) return id == 9 end
        by = by_dir(H.tactical_view(1, 0, 1, 'summary'))
        assert(by.NE.zoc == nil and by.NE.cost == 1 and by.NE.left == 1, 'IgnoreZOC: ' .. H.json(by.NE))
        """)

    def test_terrain_hills_and_a_city_on_hills(self):
        self.run_lua("""
        local u = unit(1, 0, 1, 2, 2, { moves = 3 })
        u.MaxMoves = function() return 180 end
        P['2,3'].o.forest = true                         -- NE forest
        P['3,2'].o.hills = true                          -- E hills
        P['1,2'].o.hills = true; P['1,2'].o.forest = true   -- W forested hills
        P['2,1'].o.hills = true                          -- SE hills under our own city: flat land
        P['2,1'].o.city = city('Dun Edin', 0)
        local by = by_dir(H.tactical_view(1, 0, 1, 'summary'))
        assert(by.NE.cost == 2 and by.NE.left == 1, 'forest: ' .. H.json(by.NE))
        assert(by.E.cost == 2 and by.E.left == 1, 'hills: ' .. H.json(by.E))
        assert(by.W.cost == 3 and by.W.left == 0, 'forest on hills: ' .. H.json(by.W))
        assert(by.SE.cost == 1 and by.SE.left == 2, 'a city counts as flat: ' .. H.json(by.SE))
        assert(by.NW.cost == 1 and by.NW.left == 2, 'open ground: ' .. H.json(by.NW))
        u.IsFeatureDoubleMove = function(_, f) return f == 0 end
        u.IsHillsDoubleMove = function() return true end
        by = by_dir(H.tactical_view(1, 0, 1, 'summary'))
        assert(by.NE.cost == 1 and by.E.cost == 1 and by.W.cost == 1.5, 'double-move promotions halve: ' .. H.json(by))
        """)

    def test_a_step_never_spends_more_than_the_unit_has_and_no_moves_prices_next_turn(self):
        self.run_lua("""
        local u = unit(1, 0, 1, 2, 2, { moves = 1 })
        P['2,3'].o.forest = true
        local by = by_dir(H.tactical_view(1, 0, 1, 'summary'))
        assert(by.NE.cost == 1 and by.NE.left == 0, 'one move left enters the forest and stops: ' .. H.json(by.NE))
        u.MovesLeft = function() return 20 end           -- a third of a move
        by = by_dir(H.tactical_view(1, 0, 1, 'summary'))
        assert(by.W.cost == 0.33 and by.W.left == 0, H.json(by.W))
        u.MovesLeft = function() return 0 end
        by = by_dir(H.tactical_view(1, 0, 1, 'summary'))
        assert(by.NE.cost == 2 and by.NE.left == 0 and by.W.cost == 1 and by.W.left == 1, 'next turn, from full moves: ' .. H.json(by))
        """)

    def test_rivers_end_the_move_unless_bridged_or_amphibious(self):
        self.run_lua("""
        local u = unit(1, 0, 1, 2, 2)
        P['2,2'].o.w_of_river = true                     -- a river on our east edge
        local by = by_dir(H.tactical_view(1, 0, 1, 'summary'))
        assert(by.E.river_crossing and by.E.cost == 2 and by.E.left == 0, 'all moves across: ' .. H.json(by.E))
        road(2, 2); road(3, 2)
        by = by_dir(H.tactical_view(1, 0, 1, 'summary'))
        assert(by.E.cost == 2 and by.E.left == 0, 'a road does not bridge the river before the tech: ' .. H.json(by.E))
        Teams[0].IsBridgeBuilding = function() return true end
        by = by_dir(H.tactical_view(1, 0, 1, 'summary'))
        assert(by.E.cost == 0.5 and by.E.left == 1.5, 'bridged road: ' .. H.json(by.E))
        Teams[0].IsBridgeBuilding = nil
        P['3,2'].GetRouteType = function() return -1 end
        u.IsRiverCrossingNoPenalty = function() return true end
        by = by_dir(H.tactical_view(1, 0, 1, 'summary'))
        assert(by.E.cost == 1 and by.E.left == 1, 'amphibious: the terrain alone: ' .. H.json(by.E))
        """)

    def test_roads_and_the_team_route_change(self):
        self.run_lua("""
        unit(1, 0, 1, 2, 2)
        road(2, 2); road(1, 2)
        P['1,2'].o.forest = true
        local by = by_dir(H.tactical_view(1, 0, 1, 'summary'))
        assert(by.W.cost == 0.5 and by.W.left == 1.5, 'a road on both plots: ' .. H.json(by.W))
        assert(by.NW.cost == 1, 'no road on the far plot: ' .. H.json(by.NW))
        Teams[0].GetRouteChange = function(_, r) return r == 0 and -10 or 0 end   -- Machinery
        by = by_dir(H.tactical_view(1, 0, 1, 'summary'))
        assert(by.W.cost == 0.33 and by.W.left == 1.67, H.json(by.W))
        Players[3].GetTeam = function() return 3 end
        P['1,2'].o.owner = 3
        Teams[0].IsAtWar = function(_, t) return t == 63 or t == 3 end
        Teams[0].IsHasMet = function() return true end
        by = by_dir(H.tactical_view(1, 0, 1, 'summary'))
        assert(by.W.move == 'open' and by.W.cost == 2 and by.W.left == 0, 'an enemy road is not ours to use: ' .. H.json(by.W))
        """)

    def test_embarking_spends_every_move(self):
        self.run_lua("""
        Teams[0].CanEmbark = function() return true end
        unit(1, 0, 1, 2, 2)
        P['1,1'].o.water = true                          -- SW coast
        local by = by_dir(H.tactical_view(1, 0, 1, 'summary'))
        assert(by.SW.move == 'open' and by.SW.cost == 2 and by.SW.left == 0, 'embarking: ' .. H.json(by.SW))
        """)

    def test_a_fogged_step_is_priced_as_last_seen(self):
        """The fogged plot's live feature, route and owner getters raise in WORLD: the cost reads what was seen."""
        self.run_lua("""
        unit(1, 0, 1, 2, 2)
        P['1,2'].o.fog = true
        P['1,2'].o.forest = true
        H.seen_features[0][1 * 4096 + 2] = 0             -- a forest when last seen
        local by = by_dir(H.tactical_view(1, 0, 1, 'summary'))
        assert(by.W.vis == 'fogged' and by.W.move == 'open', H.json(by.W))
        assert(by.W.cost == 2 and by.W.left == 0, 'the remembered forest: ' .. H.json(by.W))
        """)


if __name__ == "__main__":
    unittest.main()
