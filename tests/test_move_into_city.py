"""A move onto another player's city plot must be refused, not silently dropped.

`CanStartMission(MISSION_MOVE_TO)` says yes for a foreign city plot; the engine then drops the
mission without a word and the unit sits at full moves blocking the turn. Live t213: a Missionary
bought to answer Lhasa's "spread Tengriism here" quest was ordered onto Lhasa's own plot (49,5),
reported `queued: true`, moved nowhere for two turns, and only worked once retargeted to an adjacent
plot. `resume_moves` already carried a note about the same shape from t266.

At war the same move is an attack and stays legal.
"""
import unittest

import test_mcp_safety as support


WORLD = """
UI = {SelectUnit = function() end, GetHeadSelectedUnit = function() return unit end}
Game = {GetActivePlayer = function() return 0 end,
        SelectionListGameNetMessage = function() pushed = true end}
GameMessageTypes = {GAMEMESSAGE_PUSH_MISSION = 41}
GameDefines = {MOVE_DENOMINATOR = 60}
MissionTypes = {MISSION_MOVE_TO = 1}
GameInfoTypes = MissionTypes
DomainTypes = {DOMAIN_LAND = 0, DOMAIN_SEA = 1}

pushed = false
unit = {
  GetID = function() return 1 end, GetOwner = function() return 0 end,
  GetX = function() return 47 end, GetY = function() return 10 end,
  MovesLeft = function() return 60 end, MaxMoves = function() return 60 end,
  GetTeam = function() return 0 end,
  CanStartMission = function() return true end,
  IsCombatUnit = function() return false end,
  GetDomainType = function() return 0 end,
  IsHasPromotion = function() return true end,
  PushMission = function() pushed = true end,
}

-- The destination: a revealed plot holding someone else's city.
function city_plot(o)
  return {
    GetX = function() return 49 end, GetY = function() return 5 end,
    IsRevealed = function() return o.revealed ~= false end,
    IsVisible = function() return false end,
    GetPlotIndex = function() return 4905 end,
    IsCity = function() return true end,
    IsImpassable = function() return false end,
    IsMountain = function() return false end,
    IsWater = function() return false end,
    GetOwner = function() return o.owner end,
    GetNumUnits = function() return 0 end,
    GetPlotCity = function()
      return {GetName = function() return 'Lhasa' end,
              GetOwner = function() return o.owner end,
              GetTeam = function() return o.team end}
    end,
  }
end

function aim_at(owner, team, revealed)
  Map = {GetPlot = function() return city_plot{owner = owner, team = team, revealed = revealed} end}
  pushed = false
end

Players = {[0] = {GetUnitByID = function() return unit end, GetTeam = function() return 0 end,
                  IsMinorCiv = function() return false end},
           [22] = {GetTeam = function() return 22 end, IsMinorCiv = function() return true end,
                   GetCivilizationShortDescription = function() return 'Lhasa' end}}
Teams = {[0] = {IsAtWar = function() return AT_WAR end, CanEmbark = function() return true end},
         [22] = {IsAllowsOpenBordersToTeam = function() return true end}}
AT_WAR = false
"""


class MoveIntoCityTests(unittest.TestCase):
    run_lua = support.LuaRuntimeTests.run_lua

    def setUp(self):
        support.LuaRuntimeTests.setUp(self)
        self.run_lua(WORLD)

    def test_a_foreign_city_plot_is_refused_by_name(self):
        self.run_lua("""
        aim_at(22, 22, true)
        local r = H.move_unit(1, 49, 5, 0)
        assert(r.ok == false, 'a move the engine will drop must not report success')
        assert(r.err:find('Lhasa', 1, true), 'the refusal names the city: ' .. tostring(r.err))
        assert(r.err:find('next to it', 1, true), 'and says what to do instead: ' .. tostring(r.err))
        assert(r.city.name == 'Lhasa' and r.city.x == 49 and r.city.y == 5)
        assert(pushed == false, 'nothing may be sent to the engine for an order it will drop')
        """)

    def test_at_war_the_same_move_is_an_attack_and_goes_through(self):
        self.run_lua("""
        AT_WAR = true
        aim_at(22, 22, true)
        local r = H.move_unit(1, 49, 5, 0)
        assert(r.ok == true, 'attacking a city is a legal order: ' .. tostring(r.err))
        assert(pushed == true)
        """)

    def test_an_unrevealed_plot_is_left_to_the_existing_check(self):
        """We only refuse where a human sees the city banner; otherwise the old check decides."""
        self.run_lua("""
        aim_at(22, 22, false)
        local r = H.move_unit(1, 49, 5, 0)
        assert(r.ok == false and r.err == 'plot is not revealed', tostring(r.err))
        """)

    def test_closed_borders_refuse_an_ordinary_civilian_but_not_a_rival_territory_unit(self):
        """Live Assyria t141: a Missionary bound for the Zulu capital was refused "no open-borders agreement"
        while the engine's own Unit:IsRivalTerritory() said it may enter; the guard honours that flag."""
        self.run_lua("""
        Players[3] = {GetTeam = function() return 3 end, IsMinorCiv = function() return false end,
                      GetCivilizationShortDescription = function() return 'The Zulus' end}
        Teams[3] = {IsAllowsOpenBordersToTeam = function() return false end}
        Map = {GetPlot = function() return {
          GetX = function() return 33 end, GetY = function() return 21 end,
          IsRevealed = function() return true end, IsVisible = function() return true end,
          GetPlotIndex = function() return 3321 end, IsCity = function() return false end,
          IsImpassable = function() return false end, IsMountain = function() return false end,
          IsWater = function() return false end, GetOwner = function() return 3 end,
          GetNumUnits = function() return 0 end, GetPlotCity = function() return nil end,
          GetUnit = function() return nil end} end}
        pushed = false
        local r = H.move_unit(1, 33, 21, 0)
        assert(r.ok == false and r.err:find('open%-borders'), 'a Worker is kept out: ' .. tostring(r.err))
        assert(r.owner_player_id == 3)
        unit.IsRivalTerritory = function() return true end
        r = H.move_unit(1, 33, 21, 0)
        assert(r.ok == true, 'a Missionary enters by the engine rule: ' .. tostring(r.err))
        assert(pushed == true)
        """)

    def test_our_own_city_is_still_enterable(self):
        self.run_lua("""
        aim_at(0, 0, true)
        local r = H.move_unit(1, 49, 5, 0)
        assert(r.ok == true, 'garrisoning our own city is an ordinary move: ' .. tostring(r.err))
        assert(pushed == true)
        """)

    def test_teammate_territory_and_cities_need_no_open_borders_agreement(self):
        """Player ids differ in team hotseat; both orders and tactical checks must allow the same team."""
        for combat in (False, True):
            for city in (False, True):
                for fog_safe in (False, True):
                    with self.subTest(combat=combat, city=city, fog_safe=fog_safe):
                        self.run_lua(f"""
                        unit.IsCombatUnit = function() return {str(combat).lower()} end
                        Players[3] = {{GetTeam = function() return 0 end,
                          IsMinorCiv = function() return false end,
                          GetCivilizationShortDescription = function() return 'China' end}}
                        Teams[0].IsAllowsOpenBordersToTeam = function() return false end
                        aim_at(3, 0, true)
                        local dest = Map.GetPlot()
                        dest.IsCity = function() return {str(city).lower()} end
                        dest.IsVisible = function() return {str(not fog_safe).lower()} end
                        dest.GetRevealedOwner = function() return 3 end
                        Map.GetPlot = function() return dest end
                        local refusal = H.move_refusal(unit, dest, 0, {str(fog_safe).lower()})
                        assert(refusal == nil, 'a teammate needs no border deal: ' ..
                          tostring(refusal and refusal.err))
                        pushed = false
                        local r = H.move_unit(1, 49, 5, 0)
                        assert(r.ok == true, 'the move must reach the engine: ' .. tostring(r.err))
                        assert(pushed == true)
                        """)

    def test_foreign_team_still_needs_open_borders_or_war(self):
        for at_war, open_borders in ((False, False), (False, True), (True, False)):
            for fog_safe in (False, True):
                with self.subTest(at_war=at_war, open_borders=open_borders, fog_safe=fog_safe):
                    self.run_lua(f"""
                    AT_WAR = {str(at_war).lower()}
                    Players[3] = {{GetTeam = function() return 3 end,
                      IsMinorCiv = function() return false end,
                      GetCivilizationShortDescription = function() return 'China' end}}
                    Teams[3] = {{IsAllowsOpenBordersToTeam = function() return {str(open_borders).lower()} end}}
                    aim_at(3, 3, true)
                    local dest = Map.GetPlot()
                    dest.IsCity = function() return false end
                    dest.IsVisible = function() return {str(not fog_safe).lower()} end
                    dest.GetRevealedOwner = function() return 3 end
                    Map.GetPlot = function() return dest end
                    local refusal = H.move_refusal(unit, dest, 0, {str(fog_safe).lower()})
                    pushed = false
                    local r = H.move_unit(1, 49, 5, 0)
                    if {str(at_war or open_borders).lower()} then
                      assert(refusal == nil and r.ok == true and pushed == true, tostring(r.err))
                    else
                      assert(refusal and refusal.owner_player_id == 3)
                      assert(r.ok == false and r.err:find('open%-borders'), tostring(r.err))
                      assert(pushed == false, 'closed foreign borders must still block the order')
                    end
                    """)


if __name__ == "__main__":
    unittest.main()
