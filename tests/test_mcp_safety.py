"""Regression tests for privacy and invalid actions, using the real Lua runtime."""
import ctypes
import ctypes.util
import json
from pathlib import Path
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest import mock
from harness import runtime_source
from harness.client import Civ5
from harness.action_lock import action_lock


class LuaRuntimeTests(unittest.TestCase):
    def setUp(self):
        library = ctypes.util.find_library("lua5.4")
        if not library:
            self.skipTest("liblua5.4 is needed for runtime regression tests")
        self.lua = ctypes.CDLL(library)
        self.lua.luaL_newstate.restype = ctypes.c_void_p
        self.lua.luaL_openlibs.argtypes = [ctypes.c_void_p]
        self.lua.luaL_loadstring.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        self.lua.lua_pcallk.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_longlong, ctypes.c_void_p]
        self.lua.lua_tolstring.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        self.lua.lua_tolstring.restype = ctypes.c_char_p
        self.lua.lua_pushlstring.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t]
        self.lua.lua_pushlstring.restype = ctypes.c_char_p
        self.lua.lua_setglobal.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        self.lua.lua_close.argtypes = [ctypes.c_void_p]
        self.state = self.lua.luaL_newstate()
        self.lua.luaL_openlibs(self.state)
        self.addCleanup(self.lua.lua_close, self.state)
        self.run_lua("Events={}; Game={GetActivePlayer=function() return 0 end, GetGameTurn=function() return 1 end}")
        LuaRuntimeTests.load_runtime(self)   # explicit: some suites borrow setUp/run_lua without subclassing

    def load_runtime(self):
        """Install the runtime on this state the way Game.ensure_runtime does: the assembled text goes into a
        global and the installer runs each fragment as its own chunk. A repeat is a reload that carries the
        accumulated state (the installer forces `H.version = -1` first)."""
        src = runtime_source.snapshot()
        text = src.text.encode("utf-8")
        self.lua.lua_pushlstring(self.state, text, len(text))
        self.lua.lua_setglobal(self.state, b"__H_SRC")
        self.run_lua(src.install_lua("__H_SRC"))

    def run_lua(self, source):
        result = self.lua.luaL_loadstring(self.state, source.encode())
        if result == 0:
            result = self.lua.lua_pcallk(self.state, 0, 0, 0, 0, None)
        if result:
            self.fail(self.lua.lua_tolstring(self.state, -1, None).decode())

    def test_unmet_civilizations_are_not_returned(self):
        self.run_lua("""
        Players={[0]={GetTeam=function() return 0 end}, [1]={
          IsAlive=function() return true end, IsEverAlive=function() return true end,
          GetTeam=function() return 1 end, GetName=function() error('private identity read') end}}
        Teams={[0]={IsHasMet=function() return false end}}; GameDefines={MAX_MAJOR_CIVS=2}
        assert(#H.diplomacy(0)==0)
        """)

    def test_fogged_plots_do_not_read_dynamic_state(self):
        self.run_lua("""
        local function no() return false end
        local p={IsRevealed=function() return true end, IsVisible=no,
          GetX=function() return 2 end, GetY=function() return 3 end,
          GetTerrainType=function() return 0 end, IsHills=no, IsMountain=no, IsRiver=no,
          -- last-seen values a human still sees under fog; the live GetImprovementType/GetOwner/GetFeatureType stay forbidden
          GetRevealedImprovementType=function(self, team) assert(team==7); return 0 end,
          GetRevealedRouteType=function(self, team) assert(team==7); return -1 end,
          GetRevealedOwner=function(self, team) assert(team==7); return -1 end,
          GetResourceType=function(self, team) assert(team==7); return -1 end}
        setmetatable(p,{__index=function(_,key) error('private state read: '..key) end})
        Map={PlotXYWithRangeCheck=function() return p end}
        GameInfo={Terrains={[0]={Type='TERRAIN_GRASS'}}, Improvements={[0]={Type='IMPROVEMENT_GOODY_HUT'}}}
        Players={[5]={GetTeam=function() return 7 end}}
        local result=H.plots_around(2,3,0,5)
        assert(#result==1 and result[1].vis==false)
        assert(result[1].improvement=='GOODY_HUT')
        assert(result[1].owner==nil and result[1].city==nil and result[1].units==nil and result[1].feature==nil)
        """)

    def test_revealed_plots_omit_unrevealed_and_do_not_cheat_fog(self):
        self.run_lua("""
        local function no() return false end
        local function yes() return true end
        local function plot(revealed, visible, extra)
          local p={IsRevealed=function() return revealed end, IsVisible=function() return visible end,
            GetX=function() return extra.x end, GetY=function() return extra.y end,
            GetTerrainType=function() return 0 end, IsHills=no, IsMountain=no, IsRiver=no,
            GetResourceType=function() return -1 end}
          if visible then
            p.GetFeatureType=function() return -1 end
            p.GetImprovementType=function() return -1 end
            p.GetRouteType=function() return -1 end
            p.GetOwner=function() return extra.owner end
            p.IsCity=no
            p.GetNumUnits=function() return extra.units or 0 end
            p.GetUnit=function() return extra.unit end
          else
            p.GetRevealedImprovementType=function() return -1 end
            p.GetRevealedRouteType=function() return -1 end
            p.GetRevealedOwner=function() return -1 end
            setmetatable(p,{__index=function(_,key) error('fog cheat: '..key) end})
          end
          return p
        end
        local hidden=plot(false, false, {x=0,y=0})
        local fog=plot(true, false, {x=1,y=1})
        local seen=plot(true, true, {x=2,y=2, owner=3, units=1, unit={
          IsInvisible=no, GetOwner=function() return 3 end, GetID=function() return 9 end,
          GetUnitType=function() return 0 end, GetCurrHitPoints=function() return 100 end}})
        Map={GetNumPlots=function() return 3 end, GetPlotByIndex=function(i)
          return ({[0]=hidden,[1]=fog,[2]=seen})[i]
        end}
        GameInfo={Terrains={[0]={Type='TERRAIN_GRASS'}}, Units={[0]={Type='UNIT_WARRIOR'}}}
        local result=H.revealed_plots(7)
        assert(#result==2)
        assert(result[1].x==1 and result[1].vis==false and result[1].units==nil and result[1].owner==nil)
        assert(result[2].x==2 and result[2].vis==true and result[2].owner==3)
        assert(#result[2].units==1 and result[2].units[1].id==9)
        """)

    def test_explore_frontier_reads_only_revealed_flag_of_fog(self):
        # A 3x1 strip: x=0 revealed water, x=1 revealed water, x=2 unrevealed. Only (1,0) borders the fog.
        # Touching anything but IsRevealed on the unrevealed plot is a fog cheat.
        self.run_lua("""
        local function no() return false end
        local function yes() return true end
        local plots = {}
        local function water(x)
          return {IsRevealed=yes, IsImpassable=no, IsMountain=no, IsWater=yes, GetX=function() return x end, GetY=function() return 0 end,
                  GetTerrainType=function() return 0 end}
        end
        plots[0]=water(0); plots[1]=water(1)
        plots[2]=setmetatable({IsRevealed=no, GetX=function() return 2 end, GetY=function() return 0 end},
          {__index=function(_,key) error('fog cheat: '..key) end})
        Map={GetNumPlots=function() return 3 end, GetPlotByIndex=function(i) return plots[i] end,
             GetGridSize=function() return 3, 1 end, GetPlot=function(x, y) return plots[x] end,
             PlotXYWithRangeCheck=function(x, y, dx, dy, r) if dy ~= 0 then return nil end return plots[x+dx] end,
             PlotDistance=function(ax, ay, bx, by) return math.abs(ax-bx) end}
        DomainTypes={DOMAIN_SEA=1, DOMAIN_LAND=0}
        GameInfo={Terrains={[0]={Type='TERRAIN_COAST'}}}
        local ship={GetDomainType=function() return 1 end, IsEmbarked=no, GetX=function() return 0 end, GetY=function() return 0 end}
        Players={[0]={GetUnitByID=function(_, id) if id==5 then return ship end end, GetTeam=function() return 0 end}}
        local r=H.explore_frontier(5, 0, 12)
        assert(r.ok, 'ok')
        assert(r.unrevealed_plots==1, 'one fogged plot')
        assert(#r.frontier==1 and r.frontier[1].x==1 and r.frontier[1].unrevealed_neighbors==1 and r.frontier[1].distance==1, 'frontier is (1,0)')
        assert(r.frontier[1].t=='COAST' and r.frontier[1].map_edge==true)  -- a 1-row map is all edge
        assert(r.frontier[1].reachable==true, 'adjacent known water is reachable')
        assert(r.unit.domain=='SEA' and r.map.width==3)
        assert(r.note==nil)
        -- a land unit sees no frontier here (all water) and gets a note instead of nothing
        local land={GetDomainType=function() return 0 end, IsEmbarked=no, GetX=function() return 0 end, GetY=function() return 0 end}
        Players[0].GetUnitByID=function(_, id) return land end
        local r2=H.explore_frontier(5, 0, 12)
        assert(#r2.frontier==0 and r2.note ~= nil and r2.frontier_total==0)
        assert(not H.explore_frontier(99, 0, 12).ok or true)
        """)

    def test_explore_frontier_marks_plots_behind_land_unreachable(self):
        # 6x1 strip for a ship at x=0: water, water, LAND, water, water, fog. (4,0) borders the fog but the
        # only known route crosses land, so reachable=false; it must still be listed, sorted last.
        self.run_lua("""
        local function no() return false end
        local function yes() return true end
        local plots = {}
        local function plot(x, water)
          return {IsRevealed=yes, IsImpassable=no, IsMountain=no, IsWater=function() return water end, GetX=function() return x end,
                  GetY=function() return 0 end, GetTerrainType=function() return 0 end}
        end
        plots[0]=plot(0,true); plots[1]=plot(1,true); plots[2]=plot(2,false); plots[3]=plot(3,true); plots[4]=plot(4,true)
        plots[5]=setmetatable({IsRevealed=no, GetX=function() return 5 end, GetY=function() return 0 end},
          {__index=function(_,key) error('fog cheat: '..key) end})
        Map={GetNumPlots=function() return 6 end, GetPlotByIndex=function(i) return plots[i] end,
             GetGridSize=function() return 6, 1 end, GetPlot=function(x, y) return plots[x] end,
             PlotXYWithRangeCheck=function(x, y, dx, dy, r) if dy ~= 0 then return nil end return plots[x+dx] end,
             PlotDistance=function(ax, ay, bx, by) return math.abs(ax-bx) end}
        DomainTypes={DOMAIN_SEA=1, DOMAIN_LAND=0}
        GameInfo={Terrains={[0]={Type='TERRAIN_COAST'}}}
        local ship={GetDomainType=function() return 1 end, IsEmbarked=no, GetX=function() return 0 end, GetY=function() return 0 end}
        Players={[0]={GetUnitByID=function(_, id) return ship end, GetTeam=function() return 0 end}}
        local r=H.explore_frontier(5, 0, 12)
        assert(r.ok and #r.frontier==1 and r.frontier[1].x==4, 'only (4,0) borders fog')
        assert(r.frontier[1].reachable==false, 'behind land: unreachable through the known map')
        -- an embarked land unit may cross the land plot, so for it the same plot is reachable
        local emb={GetDomainType=function() return 0 end, IsEmbarked=yes, GetX=function() return 0 end, GetY=function() return 0 end}
        Players[0].GetUnitByID=function() return emb end
        local r2=H.explore_frontier(5, 0, 12)
        assert(#r2.frontier==1 and r2.frontier[1].reachable==true, 'embarked unit crosses land')
        -- (3,0) belongs to player 7 (team 7) who gives us no open borders: the fill stops there, and the
        -- frontier plot (4,0) becomes unreachable; (4,0) itself owned by 7 is flagged closed_border
        plots[3].GetRevealedOwner=function() return 7 end
        plots[4].GetRevealedOwner=function() return 7 end
        Players[7]={GetTeam=function() return 7 end}
        Teams={[0]={IsAtWar=function() return false end}, [7]={IsAllowsOpenBordersToTeam=function() return false end}}
        local r3=H.explore_frontier(5, 0, 12)
        assert(#r3.frontier==1 and r3.frontier[1].reachable==false and r3.frontier[1].closed_border==7, 'closed border blocks')
        Teams[7].IsAllowsOpenBordersToTeam=function() return true end
        local r4=H.explore_frontier(5, 0, 12)
        assert(r4.frontier[1].reachable==true and r4.frontier[1].closed_border==nil, 'open borders pass')
        Teams[7].IsAllowsOpenBordersToTeam=function() return false end
        Teams[0].IsAtWar=function() return true end
        assert(H.explore_frontier(5, 0, 12).frontier[1].reachable==true, 'war lets units in')
        """)

    def test_unmet_city_states_are_not_returned(self):
        self.run_lua("""
        Players={[0]={GetTeam=function() return 0 end}, [22]={
          IsAlive=function() return true end, IsEverAlive=function() return true end,
          IsMinorCiv=function() return true end, GetTeam=function() return 22 end,
          GetName=function() error('private minor identity read') end}}
        Teams={[0]={IsHasMet=function() return false end}}
        GameDefines={MAX_CIV_PLAYERS=23, MAX_MAJOR_CIVS=2}
        assert(#H.diplomacy(0)==0)
        """)

    def test_non_trade_unit_never_reaches_native_route_api(self):
        self.run_lua("""
        Players={[0]={GetUnitByID=function() return {IsTrade=function() return false end} end,
          GetPotentialInternationalTradeRouteDestinations=function() error('unsafe native call') end}}
        assert(#H.available_trade_routes(1,0)==0)
        local result=H.establish_trade_route(1,2,3,0,0)
        assert(result.ok==false and result.err=='unit is not a caravan or cargo ship')
        """)

    def test_events_are_filtered_at_capture_and_consumed_per_seat(self):
        self.run_lua("""
        H.record('city_created', {player=1,city=123})
        H.record('city_created', {player=0,city=456})
        Game.GetActivePlayer=function() return 1 end
        H.record('city_created', {player=1,city=789})
        local zero=H.take_events(0); local one=H.take_events(1)
        assert(#zero==1 and zero[1].data.city==456)
        assert(#one==1 and one[1].data.city==789)
        assert(#H.take_events(0)==0)
        """)

    def test_available_research_uses_can_research_not_raw_table(self):
        self.run_lua("""
        local seen={}
        GameInfo={Technologies=function()
          local rows={{ID=1,Type='TECH_POTTERY'},{ID=2,Type='TECH_FUTURE_TECH'}}
          local i=0
          return function() i=i+1; return rows[i] end
        end}
        Players={[0]={
          GetCurrentResearch=function() return 1 end,
          CanResearch=function(self,id) seen[#seen+1]=id; return id==1 end,
          GetResearchTurnsLeft=function() return 3 end,
          GetResearchCost=function() return 35 end,
        }}
        local out=H.available_research(0)
        assert(#out==1 and out[1].tech=='TECH_POTTERY' and out[1].current==true)
        assert(#seen==2)
        """)

    def test_tech_tree_have_prereqs_and_embassy_rivals(self):
        self.run_lua("""
        local function rows_iter(rows)
          local i=0; return function() i=i+1; return rows[i] end
        end
        local techs={
          {ID=0,Type='TECH_AGRICULTURE',Era='ERA_ANCIENT'},
          {ID=1,Type='TECH_POTTERY',Era='ERA_ANCIENT'},
          {ID=2,Type='TECH_WRITING',Era='ERA_ANCIENT'},
          {ID=3,Type='TECH_EDUCATION',Era='ERA_MEDIEVAL'},
        }
        local by={TECH_AGRICULTURE=techs[1],TECH_POTTERY=techs[2],TECH_WRITING=techs[3],TECH_EDUCATION=techs[4],
                  [0]=techs[1],[1]=techs[2],[2]=techs[3],[3]=techs[4]}
        GameInfo={
          Technologies=setmetatable(by,{__call=function() return rows_iter(techs) end}),
          Technology_PrereqTechs=function()
            return rows_iter({
              {TechType='TECH_POTTERY',PrereqTech='TECH_AGRICULTURE'},
              {TechType='TECH_WRITING',PrereqTech='TECH_POTTERY'},
              {TechType='TECH_EDUCATION',PrereqTech='TECH_WRITING'},
            })
          end,
        }
        GameDefines={MAX_MAJOR_CIVS=3}
        local known={[0]=true}
        Players={
          [0]={GetTeam=function() return 0 end, GetCurrentResearch=function() return 1 end,
               CanResearch=function(self,id) return id==1 end, CanEverResearch=function() return true end,
               GetResearchTurnsLeft=function() return 4 end, GetResearchCost=function(self,id) return 10+id end,
               GetResearchProgress=function() return 12 end, GetQueuePosition=function() return -1 end},
          [1]={IsAlive=function() return true end, IsMinorCiv=function() return false end, GetTeam=function() return 1 end,
               GetCivilizationShortDescription=function() return 'Ethiopia' end},
          [2]={IsAlive=function() return true end, IsMinorCiv=function() return false end, GetTeam=function() return 2 end,
               GetCivilizationShortDescription=function() error('unmet civ leaked') end},
        }
        Teams={
          [0]={IsHasTech=function(self,id) return id==0 end, IsHasMet=function(self,t) return t==1 end,
               HasEmbassyAtTeam=function(self,t) return t==1 end, GetTeam=function() return 0 end},
          [1]={IsHasTech=function(self,id) return id==0 or id==1 or id==2 end, GetTeam=function() return 1 end},
          [2]={IsHasTech=function() error('unmet HasTech') end},
        }
        local r=H.tech_tree(0)
        assert(r.ok and r.current=='POTTERY')
        assert(#r.have==1 and r.have[1]=='AGRICULTURE')
        local by_status={}
        for _,t in ipairs(r.techs) do by_status[t.tech]=t end
        assert(by_status.TECH_POTTERY.status=='current' and by_status.TECH_POTTERY.current==true)
        assert(by_status.TECH_WRITING.status=='unavailable' and by_status.TECH_WRITING.missing[1]=='TECH_POTTERY')
        assert(by_status.TECH_EDUCATION.status=='unavailable')
        assert(by_status.TECH_AGRICULTURE==nil, 'researched techs belong in have, not techs')
        -- GitLab #1: an embassy is not a tech list. Ethiopia (met, embassy, two techs ahead) must not
        -- appear anywhere in the answer, and no rival team's IsHasTech may be consulted.
        assert(r.rivals==nil, 'no per-rival technology column')
        local dumped=H.json(r)
        assert(not dumped:find('Ethiopia', 1, true), 'embassy rival leaked into tech_tree')
        assert(not dumped:find('ahead', 1, true), 'ahead list leaked into tech_tree')
        """)

    def test_stored_beakers_show_on_every_unfinished_tech(self):
        """GitLab #18: techhelpinclude.lua prints GetResearchProgress for any unfinished tech with
        some, so switching research must not hide what the previous tech banked."""
        self.run_lua("""
        local rows={{ID=1,Type='TECH_POTTERY',Era='ERA_ANCIENT'},{ID=2,Type='TECH_MINING',Era='ERA_ANCIENT'},
                    {ID=3,Type='TECH_WRITING',Era='ERA_ANCIENT'},{ID=4,Type='TECH_MASONRY',Era='ERA_ANCIENT'}}
        local by_id={}
        for _,r in ipairs(rows) do by_id[r.ID]=r; by_id[r.Type]=r end
        GameInfo={Technologies=setmetatable(by_id,{__call=function() local i=0; return function() i=i+1; return rows[i] end end}),
                  Technology_PrereqTechs=function() local i=0; return function() i=i+1; return nil end end}
        GameDefines={MAX_MAJOR_CIVS=1}
        local progress={[1]=0,[2]=37,[3]=12,[4]=0}
        Players={[0]={GetTeam=function() return 0 end, GetCurrentResearch=function() return 1 end,
                      CanResearch=function(self,id) return id~=3 end, CanEverResearch=function() return true end,
                      GetResearchTurnsLeft=function() return 2 end, GetResearchCost=function() return 35 end,
                      GetResearchProgress=function(self,id) return progress[id] end,
                      GetQueuePosition=function() return -1 end}}
        Teams={[0]={IsHasTech=function() return false end}}
        local by={}
        for _,t in ipairs(H.tech_tree(0).techs) do by[t.tech]=t end
        assert(by.TECH_POTTERY.status=='current' and by.TECH_POTTERY.progress==0, 'the current tech always carries progress')
        assert(by.TECH_MINING.status=='available' and by.TECH_MINING.progress==37)
        assert(by.TECH_WRITING.status=='unavailable' and by.TECH_WRITING.progress==12, 'stored beakers show even when it cannot be researched yet')
        assert(by.TECH_MASONRY.status=='available' and by.TECH_MASONRY.progress==nil, 'zero stored is not printed')
        local av={}
        for _,t in ipairs(H.available_research(0)) do av[t.tech]=t end
        assert(av.TECH_POTTERY.progress==0 and av.TECH_MINING.progress==37 and av.TECH_MASONRY.progress==nil)
        assert(av.TECH_WRITING==nil)
        """)

    def test_tech_tree_never_reads_a_rival_teams_techs(self):
        """Even with an embassy, a rival team's IsHasTech is not consulted (GitLab #1)."""
        self.run_lua("""
        GameInfo={Technologies=function()
          local rows={{ID=1,Type='TECH_POTTERY',Era='ERA_ANCIENT'}}
          local i=0; return function() i=i+1; return rows[i] end
        end, Technology_PrereqTechs=function() local i=0; return function() i=i+1; return nil end end}
        GameDefines={MAX_MAJOR_CIVS=2}
        Players={[0]={GetTeam=function() return 0 end, GetCurrentResearch=function() return -1 end,
                      CanResearch=function() return true end, CanEverResearch=function() return true end,
                      GetResearchTurnsLeft=function() return 2 end, GetResearchCost=function() return 35 end,
                      GetQueuePosition=function() return -1 end},
                 [1]={IsAlive=function() return true end, IsMinorCiv=function() return false end,
                      GetTeam=function() return 1 end,
                      GetCivilizationShortDescription=function() error('rival identity read') end}}
        Teams={[0]={IsHasTech=function() return false end, IsHasMet=function() return true end,
                    HasEmbassyAtTeam=function() return true end},
               [1]={IsHasTech=function() error('rival tech read behind an embassy') end}}
        local r=H.tech_tree(0)
        assert(r.ok and r.rivals==nil)
        """)

    def test_tech_tree_omits_never_researchable(self):
        self.run_lua("""
        GameInfo={Technologies=function()
          local rows={{ID=1,Type='TECH_POTTERY',Era='ERA_ANCIENT'},{ID=2,Type='TECH_UNIQUE',Era='ERA_ANCIENT'}}
          local i=0; return function() i=i+1; return rows[i] end
        end, Technology_PrereqTechs=function() local i=0; return function() i=i+1; return nil end end}
        GameDefines={MAX_MAJOR_CIVS=1}
        Players={[0]={GetTeam=function() return 0 end, GetCurrentResearch=function() return -1 end,
                      CanResearch=function(self,id) return id==1 end,
                      CanEverResearch=function(self,id) return id==1 end,
                      GetResearchTurnsLeft=function() return 2 end, GetResearchCost=function() return 35 end,
                      GetQueuePosition=function() return -1 end}}
        Teams={[0]={IsHasTech=function() return false end}}
        local r=H.tech_tree(0)
        assert(#r.techs==1 and r.techs[1].tech=='TECH_POTTERY' and r.techs[1].status=='available')
        """)

    def test_available_production_missing_city_does_not_scan(self):
        self.run_lua("""
        GameInfo={Units=function() error('scanned units') end,
                  Buildings=function() error('scanned buildings') end,
                  Projects=function() error('scanned projects') end,
                  Processes=function() error('scanned processes') end}
        Players={[0]={GetCityByID=function() return nil end}}
        local r=H.available_production(99,0)
        assert(r.ok==false and r.err=='no such city')
        """)

    def test_available_unit_actions_do_not_select_or_consult_panel(self):
        self.run_lua("""
        Game.CanHandleAction=function() error('CanHandleAction without selection') end
        UI={SelectUnit=function() error('SelectUnit flips camera') end,
            GetHeadSelectedUnit=function() return nil end}
        GameDefines={MOVE_DENOMINATOR=60}
        GameInfoActions={[0]={Type='MISSION_FORTIFY', MissionType=7, CommandType=-1, AutomateType=-1, MissionData=-1}}
        local unit={
          CanStartMission=function(self, mid, d1, d2, vis) assert(mid==7); return true end,
          GetX=function() return 1 end, GetY=function() return 2 end,
          MovesLeft=function() return 120 end,
          IsCombatUnit=function() return false end,
        }
        Players={[0]={GetUnitByID=function() return unit end}}
        local r=H.available_unit_actions(1,0)
        assert(r.ok==true and #r.actions==1 and r.actions[1].type=='MISSION_FORTIFY')
        assert(#r.attack_targets==0)
        """)

    def test_available_unit_actions_omit_global_ui_controls(self):
        self.run_lua("""
        local unit={}
        Game.CanHandleAction=function() error('CanHandleAction must not be used') end
        GameDefines={MOVE_DENOMINATOR=60}
        GameInfoActions={
          [0]={Type='MISSION_FORTIFY', MissionType=7, CommandType=-1, AutomateType=-1, MissionData=-1},
          [1]={Type='CONTROL_QUICK_SAVE', MissionType=-1, CommandType=-1, AutomateType=-1, MissionData=-1},
          [2]={Type='AUTOMATE_EXPLORE', MissionType=-1, CommandType=2, AutomateType=1, MissionData=-1},
          [3]={Type='COMMAND_HOTKEY', MissionType=-1, CommandType=-1, AutomateType=-1, MissionData=-1},
          [4]={Type='INTERFACEMODE_MOVE_TO', MissionType=-1, CommandType=-1, AutomateType=-1, MissionData=-1},
        }
        Players={[0]={GetUnitByID=function() return unit end}}
        unit.CanStartMission=function(self, mid, d1, d2, vis) return mid==7 end
        unit.CanAutomate=function(self, at) return at==1 end
        unit.CanDoCommand=function() return true end
        unit.GetX=function() return 1 end; unit.GetY=function() return 2 end
        unit.MovesLeft=function() return 120 end
        unit.IsCombatUnit=function() return false end
        local r=H.available_unit_actions(1,0)
        assert(r.ok==true and #r.actions==2)
        assert(r.actions[1].type=='MISSION_FORTIFY' and r.actions[2].type=='AUTOMATE_EXPLORE')
        """)

    def test_available_unit_actions_omit_the_promotion_catalogue(self):
        """Live 2026-09-27 (Grok, t62): a wounded Spearman's actions carried every PROMOTION_* row of
        GameInfoActions, 200 of them, because CanDoCommand(COMMAND_PROMOTION) without the promotion says yes to
        all once the unit can promote. The chooser's rows are `promotions`; COMMAND_PROMOTION itself stays."""
        self.run_lua("""
        local unit={}
        GameDefines={MOVE_DENOMINATOR=60}
        GameInfoActions={
          [0]={Type='COMMAND_PROMOTION', MissionType=-1, CommandType=5, AutomateType=-1, MissionData=-1},
          [1]={Type='PROMOTION_SHOCK_1', MissionType=-1, CommandType=5, CommandData=11, AutomateType=-1, MissionData=-1},
          [2]={Type='PROMOTION_AIR_SIEGE_3', MissionType=-1, CommandType=5, CommandData=12, AutomateType=-1, MissionData=-1},
          [3]={Type='MISSION_FORTIFY', MissionType=7, CommandType=-1, AutomateType=-1, MissionData=-1},
        }
        Players={[0]={GetUnitByID=function() return unit end}}
        unit.CanStartMission=function(self, mid) return mid==7 end
        unit.CanDoCommand=function() return true end
        unit.GetX=function() return 1 end; unit.GetY=function() return 2 end
        unit.MovesLeft=function() return 120 end
        unit.IsCombatUnit=function() return false end
        local r=H.available_unit_actions(1,0)
        local types={}
        for _,a in ipairs(r.actions) do types[#types+1]=a.type end
        assert(#r.actions==2, table.concat(types, ','))
        assert(types[1]=='COMMAND_PROMOTION' and types[2]=='MISSION_FORTIFY', table.concat(types, ','))
        """)

    def test_available_unit_actions_never_list_the_swap_mission(self):
        """GitLab #71 (live Assyria t239-t273): MISSION_SWAP_UNITS sat in every unit's actions and in
        `routine_actions`. The engine's CanStartMission says yes to it for every unit, the order does nothing in
        this build (England t225) and the swap net message crashed the game: a row nobody may run is not offered.
        unit_mission still refuses it with the two-move recipe."""
        self.run_lua("""
        local unit={}
        GameDefines={MOVE_DENOMINATOR=60}
        GameInfoActions={
          [0]={Type='MISSION_SWAP_UNITS', MissionType=3, CommandType=-1, AutomateType=-1, MissionData=-1},
          [1]={Type='MISSION_FORTIFY', MissionType=7, CommandType=-1, AutomateType=-1, MissionData=-1},
        }
        Players={[0]={GetUnitByID=function() return unit end}}
        unit.CanStartMission=function(self, mid) return true end
        unit.GetX=function() return 1 end; unit.GetY=function() return 2 end
        unit.MovesLeft=function() return 120 end
        unit.IsCombatUnit=function() return false end
        local r=H.available_unit_actions(1,0)
        assert(r.ok==true and #r.actions==1 and r.actions[1].type=='MISSION_FORTIFY', H.json(r.actions))
        """)
        from harness.game_parts.support import ROUTINE_ACTIONS
        from harness.game_parts.units import KNOWN_MISSIONS
        self.assertNotIn("MISSION_SWAP_UNITS", ROUTINE_ACTIONS)
        self.assertNotIn("MISSION_SWAP_UNITS", KNOWN_MISSIONS)   # never a did_you_mean suggestion either

    def test_turn_state_names_the_dawn_of_man_splash_in_a_solo_game(self):
        """GitLab #96: loadscreen.lua pauses a single-player game with SetPausePlayer(activePlayer) until its
        button is pressed, and nothing else pauses a solo game. `load_screen_pending` is that state; in hotseat
        the same pause is the hand-off screen and the flag stays false."""
        self.run_lua("""
        local stub = { __index = function() return function() return nil end end }
        Players = { [0] = setmetatable({ GetEndTurnBlockingType = function() return -1 end }, stub) }
        Teams = { [0] = setmetatable({}, stub) }
        local paused, pauser, hotseat = true, 0, false
        Game.IsNetworkMultiPlayer = function() return false end
        Game.GetGameState = function() return 0 end
        Game.IsProcessingMessages = function() return false end
        Game.IsPaused = function() return paused end
        Game.GetPausePlayer = function() return pauser end
        Game.GetActivePlayer = function() return 0 end
        Game.GetGameTurn = function() return 0 end
        GameplayGameStateTypes = { GAMESTATE_OVER = 2 }
        PreGame = { IsHotSeatGame = function() return hotseat end }
        UI = { IsPopupUp = function() return false end }
        H.modal_flags = function() return {} end
        H.status_alerts = function() return {} end
        H.pending_popups = function() return {} end
        H.pending_deal_from = function() return nil end
        H.todo = function() return { units = {} } end
        H.stale_blocker = function() return nil end
        local t = H.turn_state(0)
        assert(t.mode == 'single' and t.paused == true and t.load_screen_pending == true, H.json(t))
        pauser = -1; paused = false
        t = H.turn_state(0)
        assert(t.load_screen_pending == false, 'pressed: ' .. H.json(t))
        paused = true; pauser = 1
        assert(H.turn_state(0).load_screen_pending == false, 'another seat pauses: not our splash')
        pauser = 0; hotseat = true
        assert(H.turn_state(0).load_screen_pending == false, 'hotseat: the hand-off screen, not the splash')
        Game.GetPausePlayer = nil
        hotseat = false
        assert(H.turn_state(0).load_screen_pending == false, 'no GetPausePlayer: no guess')
        """)

    def test_game_key_facts_hide_the_script_of_a_random_map(self):
        """GitLab #119: with map type Random the engine still answers the real script; the key says random."""
        self.run_lua("""
        local random = false
        PreGame = { GetMapScript = function() return "Assets/Maps/Fractal.lua" end,
                    IsRandomMapScript = function() return random end, GetGameName = function() return "" end }
        Game.GetStartTurn = function() return 0 end
        Players = { [0] = { GetLeaderType = function() return 31 end, GetCivilizationType = function() return 33 end,
                            GetCapitalCity = function() return nil end, GetStartingPlot = function() return nil end } }
        assert(H.game_key_facts(0).map == 'Fractal', H.json(H.game_key_facts(0)))
        assert(H.game_key_facts(0).identity == '', 'no starting plot: no identity (#168)')
        random = true
        assert(H.game_key_facts(0).map == 'random', H.json(H.game_key_facts(0)))
        PreGame.IsRandomMapScript = nil
        assert(H.game_key_facts(0).map == 'Fractal', 'no IsRandomMapScript: the script as before')
        """)

    def test_an_attack_ordered_at_zero_moves_is_refused_not_queued(self):
        """GitLab #110 (Maya t119): a move onto a barbarian at 0 moves answered queued; the engine held a mission
        it never ran and the unit sat on HOLD at full moves the next turn, in no list."""
        self.run_lua("""
        local sent={}
        UI={SelectUnit=function() end, GetHeadSelectedUnit=function() return nil end}
        Game={GetActivePlayer=function() return 0 end,
              SelectionListGameNetMessage=function(...) sent[#sent+1]={...} end}
        GameMessageTypes={GAMEMESSAGE_PUSH_MISSION=41}
        GameDefines={MOVE_DENOMINATOR=60}
        MissionTypes={MISSION_MOVE_TO=1}
        GameInfoTypes=MissionTypes
        local moves=0
        local unit={
          GetID=function() return 1 end, GetOwner=function() return 0 end,
          GetX=function() return 10 end, GetY=function() return 20 end,
          MovesLeft=function() return moves end, IsCombatUnit=function() return true end,
          CanStartMission=function() return true end,
        }
        Players={[0]={GetUnitByID=function() return unit end, GetTeam=function() return 7 end}}
        Map={GetPlot=function(x,y) return {IsRevealed=function() return true end, IsVisible=function() return true end,
                                           IsImpassable=function() return false end, IsMountain=function() return false end,
                                           GetX=function() return x end, GetY=function() return y end} end}
        H.melee_defender=function() return { unit='HAND_AXE', owner='Barbarians' } end
        H.enemy_city_at=function() return false end
        local r=H.move_unit(1, 11, 20, 0)
        assert(r.ok==false and r.err:find('no moves left this turn to attack', 1, true) and r.moves==0, H.json(r))
        assert(#sent==0, 'nothing was pushed')
        """)

    def test_a_mission_that_acts_is_refused_at_zero_moves_and_a_hold_mission_is_not(self):
        """GitLab #83 (Assyria t254): MISSION_SPACESHIP at 0 moves answered ok, the engine held it on HOLD, the
        Booster count stayed 0/3 and the part left todo. Fortify at 0 moves still works, as the stock button does."""
        self.run_lua("""
        local pushed={}
        local selected=nil
        UI={SelectUnit=function(u) selected=u end, GetHeadSelectedUnit=function() return selected end}
        Game={GetActivePlayer=function() return 0 end,
              SelectionListGameNetMessage=function(msg, m, d1, d2) pushed[#pushed+1]={m=m} end}
        GameMessageTypes={GAMEMESSAGE_PUSH_MISSION=41, GAMEMESSAGE_DO_COMMAND=42}
        GameDefines={MOVE_DENOMINATOR=60}
        MissionTypes={MISSION_SPACESHIP=30, MISSION_FORTIFY=7, MISSION_HURRY=22}
        GameInfoTypes=MissionTypes
        local moves=0
        local unit={
          GetID=function() return 1 end, GetOwner=function() return 0 end,
          GetX=function() return 16 end, GetY=function() return 27 end, MovesLeft=function() return moves end,
          IsCombatUnit=function() return false end, CanStartMission=function() return true end,
          GetBuildType=function() return -1 end, GetLengthMissionQueue=function() return 0 end,
          GetActivityType=function() return 1 end,
        }
        Players={[0]={GetUnitByID=function() return unit end, GetTeam=function() return 0 end}}
        local r=H.unit_mission(1, 'MISSION_SPACESHIP', -1, -1, nil, 0)
        assert(r.ok==false and r.err:find('would hold MISSION_SPACESHIP', 1, true) and r.moves==0, H.json(r))
        r=H.unit_mission(1, 'MISSION_HURRY', -1, -1, nil, 0)
        assert(r.ok==false and r.err:find('no moves left', 1, true), H.json(r))
        assert(#pushed==0, 'nothing was pushed at 0 moves')
        r=H.unit_mission(1, 'MISSION_FORTIFY', -1, -1, nil, 0)
        assert(r.ok==true and #pushed==1 and pushed[1].m==7, 'a hold mission works at 0 moves: ' .. H.json(r))
        moves=120
        r=H.unit_mission(1, 'MISSION_SPACESHIP', -1, -1, nil, 0)
        assert(r.ok==true and #pushed==2 and pushed[2].m==30, H.json(r))
        """)

    def test_a_finished_games_status_carries_no_chores(self):
        """GitLab #92 (Assyria t273 after the win): blocking_hint still asked for a World Congress proposal and
        todo.units held a Crossbowman beside the game_over gate."""
        self.run_lua("""
        local stub = { __index = function() return function() return nil end end }
        Players = { [0] = setmetatable({ GetEndTurnBlockingType = function() return 12 end,
                                         GetNumUnitsNeedingMoves = function() return 1 end }, stub) }
        Teams = { [0] = setmetatable({}, stub) }
        Game.IsNetworkMultiPlayer = function() return false end
        Game.GetGameState = function() return 2 end
        Game.IsProcessingMessages = function() return false end
        Game.IsPaused = function() return false end
        Game.GetPausePlayer = function() return -1 end
        Game.GetActivePlayer = function() return 0 end
        Game.GetGameTurn = function() return 273 end
        GameplayGameStateTypes = { GAMESTATE_OVER = 2 }
        PreGame = { IsHotSeatGame = function() return false end }
        UI = { IsPopupUp = function() return false end }
        H.modal_flags = function() return {} end
        H.status_alerts = function() return { { kind = 'x' } }, 5, nil end
        H.pending_popups = function() return {} end
        H.pending_deal_from = function() return nil end
        H.blocking_name = function() return 'ENDTURN_BLOCKING_LEAGUE_CALL_FOR_PROPOSALS' end
        H.todo = function() return { units = { { id = 7 } }, cities = {}, promotions = {}, research_unset = false } end
        H.stale_blocker = function() return nil end
        H.expiring_deals = function() return { { x = 1 } } end
        H.expiring_friendships = function() return {} end
        local t = H.turn_state(0)
        assert(t.game_over == true, H.json(t))
        assert(t.blocking_name == 'NO_ENDTURN_BLOCKING_TYPE' and t.blocking_hint == nil and t.blocking == -1, H.json(t))
        assert(#t.todo.units == 0 and t.expiring_deals == nil and t.alerts == nil and t.num_units_needing_moves == 0, H.json(t))
        """)

    def test_move_unit_goes_through_selection_net_message(self):
        # v86: orders must be GAMEMESSAGE_PUSH_MISSION on the selected unit (the game's own UI path), never
        # Unit:PushMission -- that mutates only the local gamecore and desyncs a LAN client (2026-09-17).
        self.run_lua("""
        local sent={}
        local selected=nil
        local unit
        UI={SelectUnit=function(u) selected=u end,
            LookAt=function() error('LookAt flips camera') end,
            GetHeadSelectedUnit=function() return selected end}
        Game={GetActivePlayer=function() return 0 end,
              SelectionListMove=function() error('use SelectionListGameNetMessage') end,
              SelectionListGameNetMessage=function(msg, d2, d3, d4, flags, alt, shift)
                assert(selected==unit, 'net message must target the selected unit')
                sent[#sent+1]={msg=msg,d2=d2,d3=d3,d4=d4,flags=flags,alt=alt,shift=shift}
              end,
              CanHandleAction=function() error('CanHandleAction needs selection') end}
        GameMessageTypes={GAMEMESSAGE_PUSH_MISSION=41, GAMEMESSAGE_DO_COMMAND=42}
        GameDefines={MOVE_DENOMINATOR=60}
        MissionTypes={MISSION_MOVE_TO=1}
        GameInfoTypes=MissionTypes
        unit={
          GetID=function() return 1 end, GetOwner=function() return 0 end,
          GetX=function() return 10 end, GetY=function() return 20 end,
          MovesLeft=function() return 120 end, IsCombatUnit=function() return false end,
          CanStartMission=function(self, m, x, y, vis)
            assert(m==1 and x==11 and y==20 and vis==false); return true
          end,
          PushMission=function() error('Unit:PushMission is local-only; must not be used') end,
        }
        Players={[0]={GetUnitByID=function() return unit end, GetTeam=function() return 7 end}}
        Map={GetPlot=function(x,y)
          return {IsRevealed=function(self, team) assert(team==7); return true end,
                  IsImpassable=function() return false end, IsMountain=function() return false end,
                  -- melee_defender: nothing to attack on a plot we cannot see
                  IsVisible=function(self, team) assert(team==7); return false end}
        end}
        local r=H.move_unit(1, 11, 20, 0)
        assert(r.ok==true and r.x==10 and r.y==20 and r.moves==2)
        assert(#sent==1 and sent[1].msg==41 and sent[1].d2==1 and sent[1].d3==11 and sent[1].d4==20)
        assert(sent[1].flags==0 and sent[1].alt==false and sent[1].shift==false)
        -- selection that lands a frame late: the first call reports select_pending, the retry sends
        selected=nil
        local late=nil
        UI.SelectUnit=function(u) late=u end
        r=H.move_unit(1, 11, 20, 0)
        assert(r.ok==false and r.select_pending==true and #sent==1 and late==unit)
        selected=late
        r=H.move_unit(1, 11, 20, 0)
        assert(r.ok==true and #sent==2)
        """)

    def test_move_unit_rejects_unrevealed_and_illegal(self):
        self.run_lua("""
        UI={SelectUnit=function() error('SelectUnit flips camera') end}
        Game={GetActivePlayer=function() return 0 end}
        GameDefines={MOVE_DENOMINATOR=60}
        MissionTypes={MISSION_MOVE_TO=1}; GameInfoTypes=MissionTypes
        local pushed=false
        local unit={
          GetX=function() return 1 end, GetY=function() return 1 end, MovesLeft=function() return 60 end,
          CanStartMission=function() return true end,
          PushMission=function() pushed=true end,
        }
        Players={[0]={GetUnitByID=function() return unit end, GetTeam=function() return 0 end}}
        Map={GetPlot=function() return {IsRevealed=function() return false end} end}
        local r=H.move_unit(1, 4, 5, 0)
        assert(r.ok==false and r.err=='plot is not revealed' and pushed==false)
        Map={GetPlot=function() return {IsRevealed=function() return true end} end}
        unit.CanStartMission=function() return false end
        r=H.move_unit(1, 4, 5, 0)
        assert(r.ok==false and r.err=='move is not currently legal' and pushed==false)
        """)

    def test_unit_mission_build_slot_via_selection_net_message(self):
        self.run_lua("""
        local selected=nil
        UI={SelectUnit=function(u) selected=u end,
            GetHeadSelectedUnit=function() return selected end}
        local pushed={}
        Game={GetActivePlayer=function() return 0 end,
              CanHandleAction=function() error('CanHandleAction needs selection') end,
              SelectionListGameNetMessage=function(msg, m, d1, d2, flags, alt, shift)
                assert(msg==41 and selected~=nil); pushed[#pushed+1]={m=m,d1=d1,d2=d2}
              end}
        GameMessageTypes={GAMEMESSAGE_PUSH_MISSION=41, GAMEMESSAGE_DO_COMMAND=42}
        GameDefines={MOVE_DENOMINATOR=60}
        GameInfoTypes={MISSION_FORTIFY=7, MISSION_BUILD=5, BUILD_FARM=9, MISSION_MOVE_TO=1}
        MissionTypes=GameInfoTypes
        GameInfo={Builds={[9]={Type='BUILD_FARM'}}}
        local plot={GetX=function() return 0 end, GetY=function() return 0 end,
                    GetBuildTurnsLeft=function(self, b) return b==9 and 5 or -1 end,
                    GetImprovementType=function() return -1 end, IsImprovementPillaged=function() return false end,
                    GetRouteType=function() return -1 end, IsRoutePillaged=function() return false end,
                    GetFeatureType=function() return -1 end}
        local unit={
          GetID=function() return 1 end, GetOwner=function() return 0 end,
          GetX=function() return 0 end, GetY=function() return 0 end, MovesLeft=function() return 60 end,
          CanStartMission=function(self, m, d1, d2, vis) return m==7 and d1==-1 and d2==-1 end,
          CanBuild=function(self, plot, b) return b==9 end,  -- Unit:CanBuild(plot, build)
          GetBuildType=function() return -1 end,
          -- MISSION_BUILD snapshots the unit's own plot so build_check can recognise instant completion
          GetPlot=function() return plot end,
          PushMission=function() error('Unit:PushMission is local-only; must not be used') end,
        }
        Players={[0]={GetUnitByID=function() return unit end, GetTeam=function() return 0 end}}
        Map={GetPlot=function() return plot end}
        local r=H.unit_mission(1, 'MISSION_FORTIFY', -1, -1, nil, 0)
        assert(r.ok==true and #pushed==1 and pushed[1].m==7 and pushed[1].d1==-1)
        r=H.unit_mission(1, 'MISSION_BUILD', -1, -1, 'BUILD_FARM', 0)
        assert(r.ok==true and r.pending==true and r.build_id==9 and r.before.imp==-1)
        assert(#pushed==2 and pushed[2].m==5 and pushed[2].d1==9 and pushed[2].d2==-1)
        -- the order lands later: build_check reports started once GetBuildType shows it, completed
        -- when the plot already changed (instant repair/chop)
        local c=H.build_check(1, 0, 0, r.before, 0)
        assert(c.ok and c.started==false and c.completed==false)
        unit.GetBuildType=function() return 9 end
        c=H.build_check(1, 0, 0, r.before, 0)
        -- turns_left is the unit panel's number, GetBuildTurnsLeft + 1, the same the unit row prints (GitLab #165)
        assert(c.started==true and c.buildtype==9 and c.build=='BUILD_FARM' and c.turns_left==6)
        unit.GetBuildType=function() return -1 end
        plot.GetImprovementType=function() return 3 end
        c=H.build_check(1, 0, 0, r.before, 0)
        assert(c.started==false and c.completed==true)
        -- a skip on a unit still following an engine path is refused rather than cancelling the path
        unit.GetLengthMissionQueue=function() return 1 end
        r=H.unit_mission(1, 'MISSION_SKIP', -1, -1, nil, 0)
        assert(r.ok==false and r.err:find('multi%-turn move') and #pushed==2)
        unit.GetLengthMissionQueue=function() return 0 end
        H.pending_moves[H.pm_key(1,0)]={x=5,y=5,pid=0,unit_id=1}
        r=H.unit_mission(1, 'MISSION_SKIP', -1, -1, nil, 0)
        assert(r.ok==false and H.pending_moves[H.pm_key(1,0)]~=nil, 'standing order survives the refused skip')
        H.pending_moves[H.pm_key(1,0)]=nil
        unit.CanStartMission=function() return false end
        r=H.unit_mission(1, 'MISSION_FORTIFY', -1, -1, nil, 0)
        assert(r.ok==false and r.err=='action is not currently legal')
        -- a swap is accepted by the engine and never happens (live England t225): refused, not "ok"
        unit.IsCombatUnit=function() return true end
        r=H.unit_mission(1, 'MISSION_SWAP_UNITS', 1, 0, nil, 0)
        assert(r.ok==false and r.err:find('does nothing') and r.hint:find('garrison swap') and #pushed==2, H.json(r))
        unit.IsCombatUnit=function() return false end
        r=H.unit_mission(1, 'MISSION_SWAP_UNITS', 1, 0, nil, 0)
        assert(r.ok==false and r.hint:find("order(to='unit', action='move') onto the other civilian", 1, true), H.json(r))
        local seen
        unit.CanStartMission=function(self, m, a, b) seen={a,b}; return false end
        r=H.unit_mission(1, 'MISSION_MOVE_TO', 0, 0, nil, 0)
        -- x=0 must not be treated as missing (Lua 0 is falsy)
        assert(seen[1]==0 and seen[2]==0)
        assert(r.ok==false and r.err=='action is not currently legal')
        """)

    def test_popup_lifecycle_keeps_decisions_until_processed(self):
        self.run_lua("""
        local handlers={}
        Events=setmetatable({}, {__index=function(_,name)
          return {Add=function(fn) handlers[name]=fn end, Remove=function() end}
        end})
        ButtonPopupTypes={BUTTONPOPUP_CHOOSETECH=4}
        H.install_hooks()
        handlers.SerialEventGameMessagePopupShown({Type=4,Data1=8})
        assert(#H.pending_popups(0)==1 and #H.pending_popups(1)==0)
        handlers.SerialEventGameMessagePopupProcessed(4)
        assert(#H.pending_popups(0)==0)
        """)

    def test_incoming_deal_reads_without_mutating(self):
        self.run_lua("""
        local i=0
        local deal={
          GetFromPlayer=function() return 1 end, GetToPlayer=function() return 0 end,
          ResetIterator=function() i=0 end,
          GetNextItem=function()
            i=i+1
            if i==1 then return 1, 30, 0, 50, 0, 0, 0, 1 end
            if i==2 then return 2, 30, 0, 3, 1, 0, 0, 0 end
          end,
          AddGoldTrade=function() error('must not Add*') end,
          ClearItems=function() error('must not ClearItems') end,
        }
        UI={GetScratchDeal=function() return deal end,
            DoProposeDeal=function() error('must not propose') end,
            DoFinalizePlayerDeal=function() error('must not finalize on read') end}
        TradeableItems={TRADE_ITEM_GOLD=1, TRADE_ITEM_RESOURCES=2}
        GameInfo={Resources={[3]={Type='RESOURCE_IVORY', ResourceClassType='RESOURCECLASS_LUXURY'}}}
        Players={[0]={GetNumResourceTotal=function() return 1 end, GetNumResourceAvailable=function() return 1 end,
                      GetResourceImport=function() return 0 end, GetResourceExport=function() return 1 end}}
        local r=H.incoming_deal(0)
        assert(r.ok==true and r.n==2 and r.from==1 and r.to==0)
        assert(r.items[1].type=='GOLD' and r.items[1].amount==50 and r.items[1].from_us==false)
        assert(r.items[2].type=='RESOURCES' and r.items[2].resource=='IVORY' and r.items[2].amount==1)
        assert(r.items[2].from_us==true)
        -- the resource we would give carries its empire numbers and a last-copy warning
        -- total 1 net of the 1 export = 2 owned: a renewal of that export is not our last copy
        assert(r.items[2].us_total==1 and r.items[2].us_exported==1 and r.items[2].us_owned==2 and r.items[2].last_copy==nil)
        assert(r.items[1].us_total==nil, 'only our own resource items are annotated')
        Players[0].GetResourceExport=function() return 0 end
        r=H.incoming_deal(0)
        assert(r.items[2].us_owned==1 and r.items[2].last_copy==true, 'one copy, nothing exported: last copy')
        Players[0].GetNumResourceTotal=function() return 2 end
        Players[0].GetNumResourceAvailable=function() return 0 end
        r=H.incoming_deal(0)
        assert(r.items[2].last_copy==nil and r.items[2].note:find('no spare copy'), 'two copies but none spare')
        """)

    def test_incoming_deal_empty_when_no_scratch(self):
        self.run_lua("""
        UI={GetScratchDeal=function() return nil end}
        local r=H.incoming_deal(0)
        assert(r.ok==true and r.n==0 and #r.items==0)
        r=H.accept_deal(0)
        assert(r.ok==false and r.err=='no incoming deal')
        r=H.refuse_deal(0)
        assert(r.ok==false and r.err=='no incoming deal')
        """)

    def test_current_deals_refuses_when_scratch_occupied(self):
        self.run_lua("""
        local i=0
        local deal={
          GetFromPlayer=function() return 1 end, GetToPlayer=function() return 0 end,
          ResetIterator=function() i=0 end,
          GetNextItem=function()
            i=i+1
            if i==1 then return 1, 30, 0, 50, 0, 0, 0, 1 end
          end,
          ClearItems=function() error('must not ClearItems when scratch occupied') end,
        }
        UI={GetScratchDeal=function() return deal end,
            GetNumCurrentDeals=function() error('must not count') end,
            LoadCurrentDeal=function() error('must not LoadCurrentDeal') end}
        TradeableItems={TRADE_ITEM_GOLD=1}
        local r=H.current_deals(0)
        assert(r.ok==false and r.err:find('occupied') and r.n==0)
        """)

    def test_current_deals_loads_and_clears(self):
        self.run_lua("""
        local loaded, cleared, i, filled = {}, 0, 0, false
        local deal={
          GetFromPlayer=function() return 0 end, GetToPlayer=function() return 2 end,
          GetOtherPlayer=function(self,pid) return 2 end,
          GetStartTurn=function() return 143 end, GetDuration=function() return 30 end,
          ResetIterator=function() i=0 end,
          GetNextItem=function()
            if not filled then return nil end
            i=i+1
            if i==1 then return 2, 30, 173, 3, 1, 0, 0, 0 end
          end,
          ClearItems=function() cleared=cleared+1; filled=false end,
        }
        UI={GetScratchDeal=function() return deal end,
            GetNumCurrentDeals=function(pid) assert(pid==0); return 1 end,
            LoadCurrentDeal=function(pid, idx) loaded[#loaded+1]={pid, idx}; filled=true; i=0 end}
        TradeableItems={TRADE_ITEM_RESOURCES=2}
        GameInfo={Resources={[3]={Type='RESOURCE_SILK', ResourceClassType='RESOURCECLASS_LUXURY'}}}
        Game.GetGameTurn=function() return 173 end
        Players={[0]={GetTeam=function() return 0 end,
                      GetNumResourceTotal=function() return 1 end, GetNumResourceAvailable=function() return 1 end,
                      GetResourceImport=function() return 0 end, GetResourceExport=function() return 1 end},
                 [2]={GetTeam=function() return 2 end, GetCivilizationShortDescription=function() return 'The Inca' end}}
        Teams={[0]={IsHasMet=function() return true end}}
        local r=H.current_deals(0)
        assert(r.ok==true and r.n==1)
        assert(#loaded==1 and loaded[1][2]==0)
        assert(cleared==1, 'scratch must be emptied after snapshot')
        local d=r.deals[1]
        assert(d.other==2 and d.civ=='The Inca' and d.ends_on==173 and d.turns_left==0)
        assert(d.items[1].type=='RESOURCES' and d.items[1].resource=='SILK' and d.items[1].final_turn==173)
        """)

    def test_accept_deal_finalizes_existing_only(self):
        self.run_lua("""
        local finalized={}
        local i=0
        local deal={
          GetFromPlayer=function() return 1 end, GetToPlayer=function() return 0 end,
          ResetIterator=function() i=0 end,
          GetNextItem=function()
            i=i+1
            if i==1 then return 1, 30, 0, 10, nil, nil, nil, 1 end
          end,
          AddGoldTrade=function() error('must not Add*') end,
        }
        UI={GetScratchDeal=function() return deal end,
            DoFinalizePlayerDeal=function(them, us, yes)
              finalized[#finalized+1]={them=them,us=us,yes=yes}
            end}
        TradeableItems={TRADE_ITEM_GOLD=1}
        local r=H.accept_deal(0)
        assert(r.ok==true and r.other==1)
        assert(#finalized==1 and finalized[1].them==1 and finalized[1].us==0 and finalized[1].yes==true)
        i=0
        r=H.refuse_deal(0)
        assert(r.ok==true and finalized[2].yes==false)
        """)

    def test_trade_catalog_never_adds(self):
        self.run_lua("""
        local deal={
          SetFromPlayer=function(self,a) self.from=a end,
          SetToPlayer=function(self,a) self.to=a end,
          IsPossibleToTradeItem=function(self, from, to, typ, a, b)
            return typ==1 and a==1
          end,
          AddGoldTrade=function() error('must not Add*') end,
          ClearItems=function() error('must not ClearItems') end,
          DoProposeDeal=function() error('must not propose') end,
        }
        UI={GetScratchDeal=function() return deal end, DoProposeDeal=function() error('no') end}
        TradeableItems={TRADE_ITEM_GOLD=1, TRADE_ITEM_GOLD_PER_TURN=2, TRADE_ITEM_OPEN_BORDERS=3,
                        TRADE_ITEM_ALLOW_EMBASSY=4, TRADE_ITEM_RESEARCH_AGREEMENT=5, TRADE_ITEM_DEFENSIVE_PACT=6,
                        TRADE_ITEM_RESOURCES=7}
        Game.GetDealDuration=function() return 25 end
        Game.GetActivePlayer=function() return 0 end
        Teams={[0]={IsHasMet=function() return true end, IsAtWar=function() return false end}}
        Players={[0]={GetTeam=function() return 0 end},
                 [1]={IsAlive=function() return true end, IsMinorCiv=function() return false end, GetTeam=function() return 1 end}}
        local r=H.trade_catalog(1,0)
        assert(r.ok==true and r.gold.us==true and r.gold.them==true)
        assert(r.gold_per_turn.us==false)
        r=H.trade_catalog(1,0)
        Players[1].IsMinorCiv=function() return true end
        r=H.trade_catalog(1,0)
        assert(r.ok==false)
        """)

    def test_trade_catalog_lists_tradeable_cities_and_availability_without_adding(self):
        self.run_lua("""
        local deal={
          SetFromPlayer=function(self,a) self.from=a end,
          SetToPlayer=function(self,a) self.to=a end,
          IsPossibleToTradeItem=function(self, from, to, typ, a, b)
            if typ==8 then return from==0 and a==5 and b==6 end   -- only our city at (5,6) is tradeable
            return typ==1 and a==1
          end,
          GetGoldAvailable=function(self, p, i) return p==0 and 321 or 77 end,
          AddCityTrade=function() error('must not AddCityTrade') end,
          AddGoldTrade=function() error('must not Add*') end,
        }
        UI={GetScratchDeal=function() return deal end}
        TradeableItems={TRADE_ITEM_GOLD=1, TRADE_ITEM_GOLD_PER_TURN=2, TRADE_ITEM_OPEN_BORDERS=3,
                        TRADE_ITEM_ALLOW_EMBASSY=4, TRADE_ITEM_RESEARCH_AGREEMENT=5, TRADE_ITEM_DEFENSIVE_PACT=6,
                        TRADE_ITEM_RESOURCES=7, TRADE_ITEM_CITIES=8}
        Game.GetDealDuration=function() return 25 end
        Game.GetActivePlayer=function() return 0 end
        Teams={[0]={IsHasMet=function() return true end, IsAtWar=function() return false end}}
        local function city(id,name,x,y) return {GetID=function() return id end, GetName=function() return name end,
                                                 GetX=function() return x end, GetY=function() return y end,
                                                 Plot=function() return {IsRevealed=function() return true end} end} end
        local function cities(list) return function() local i=0; return function() i=i+1; return list[i] end end end
        Players={[0]={GetTeam=function() return 0 end, CalculateGoldRate=function() return 12 end,
                      Cities=cities({city(11,'Cap',1,2), city(12,'Spare',5,6)})},
                 [1]={IsAlive=function() return true end, IsMinorCiv=function() return false end, GetTeam=function() return 1 end,
                      CalculateGoldRate=function() return -3 end, Cities=cities({city(21,'Theirs',9,9)})}}
        local r=H.trade_catalog(1,0)
        assert(r.ok==true, tostring(r.err))
        assert(#r.cities.us==1 and r.cities.us[1].id==12 and r.cities.us[1].x==5 and r.cities.us[1].y==6, 'us cities')
        assert(#r.cities.them==0, 'them cities')
        assert(r.gold.us_available==321 and r.gold.them_available==77, 'gold avail')
        assert(r.gold_per_turn.us_available==12 and r.gold_per_turn.them_available==-3, 'gpt avail')
        """)

    def test_trade_catalog_flags_last_luxury_copy(self):
        self.run_lua("""
        local deal={
          SetFromPlayer=function(self,a) self.from=a end,
          SetToPlayer=function(self,a) self.to=a end,
          IsPossibleToTradeItem=function(self, from, to, typ, a, b)
            if typ==7 then return from==0 end  -- we can export every resource, they export none
            return false
          end,
        }
        UI={GetScratchDeal=function() return deal end}
        TradeableItems={TRADE_ITEM_GOLD=1, TRADE_ITEM_GOLD_PER_TURN=2, TRADE_ITEM_OPEN_BORDERS=3,
                        TRADE_ITEM_ALLOW_EMBASSY=4, TRADE_ITEM_RESEARCH_AGREEMENT=5, TRADE_ITEM_DEFENSIVE_PACT=6,
                        TRADE_ITEM_RESOURCES=7}
        local rows={{ID=10,Type='RESOURCE_GEMS',ResourceClassType='RESOURCECLASS_LUXURY'},
                    {ID=11,Type='RESOURCE_DYE',ResourceClassType='RESOURCECLASS_LUXURY'},
                    {ID=12,Type='RESOURCE_IRON',ResourceClassType='RESOURCECLASS_RUSH'}}
        GameInfo={Resources=function() local i=0 return function() i=i+1 return rows[i] end end}
        Game.GetDealDuration=function() return 30 end
        Game.GetActivePlayer=function() return 0 end
        Teams={[0]={IsHasMet=function() return true end, IsAtWar=function() return false end}}
        local mine={[10]=1,[11]=3,[12]=1}
        Players={[0]={GetTeam=function() return 0 end, GetNumResourceAvailable=function(self,id,inc) return mine[id] end},
                 [1]={IsAlive=function() return true end, IsMinorCiv=function() return false end, GetTeam=function() return 1 end,
                      GetNumResourceAvailable=function() return 0 end}}
        local r=H.trade_catalog(1,0)
        assert(r.ok==true and #r.resources==3)
        local by={} for _,e in ipairs(r.resources) do by[e.resource]=e end
        assert(by.RESOURCE_GEMS.last_copy==true and by.RESOURCE_GEMS.us_available==1 and by.RESOURCE_GEMS.note)
        assert(by.RESOURCE_DYE.last_copy==nil and by.RESOURCE_DYE.us_available==3)
        assert(by.RESOURCE_IRON.last_copy==nil and by.RESOURCE_IRON.class=='RESOURCECLASS_RUSH')
        -- they cannot trade any resource to us: the trade screen shows no count for them, so none is returned
        assert(by.RESOURCE_GEMS.them_available==nil)
        """)

    def test_strategic_resources_only_revealed_rush_and_modern(self):
        self.run_lua("""
        local rows={{ID=1,Type='RESOURCE_IRON',ResourceClassType='RESOURCECLASS_RUSH',TechReveal='TECH_BRONZE_WORKING'},
                    {ID=2,Type='RESOURCE_COAL',ResourceClassType='RESOURCECLASS_RUSH',TechReveal='TECH_SCIENTIFIC_THEORY'},
                    {ID=3,Type='RESOURCE_URANIUM',ResourceClassType='RESOURCECLASS_MODERN'},
                    {ID=4,Type='RESOURCE_GEMS',ResourceClassType='RESOURCECLASS_LUXURY',TechReveal='TECH_MINING'},
                    {ID=5,Type='RESOURCE_HIDDEN_ARTIFACTS',ResourceClassType='RESOURCECLASS_RUSH'}}
        GameInfo={Resources=function() local i=0 return function() i=i+1 return rows[i] end end}
        GameInfoTypes={TECH_BRONZE_WORKING=10, TECH_SCIENTIFIC_THEORY=11, TECH_MINING=12}
        local known={[10]=true,[11]=false,[12]=true}
        local techs={HasTech=function(self,id) return known[id] end}
        Teams={[0]={GetTeamTechs=function() return techs end}}
        local avail={[1]=-2,[3]=0,[4]=1}
        local total={[1]=4,[3]=0,[4]=1}
        Players={[0]={GetTeam=function() return 0 end,
                      GetNumResourceAvailable=function(self,id,inc) return avail[id] end,
                      GetNumResourceTotal=function(self,id,inc) return total[id] end}}
        local r=H.strategic_resources(0)
        assert(r.IRON and r.IRON.available==-2 and r.IRON.total==4)
        assert(r.COAL==nil, 'unrevealed coal must not leak')
        assert(r.URANIUM and r.URANIUM.available==0)
        assert(r.GEMS==nil, 'luxuries are not strategic')
        assert(r.HIDDEN_ARTIFACTS==nil, 'archaeology marker is not a stockpile')
        """)

    def test_disband_unit_uses_command_delete_and_measures(self):
        self.run_lua("""
        GameInfo={Units={[3]={Type='UNIT_SWORDSMAN'}}, Resources=function() return function() return nil end end}
        CommandTypes={COMMAND_DELETE=9, COMMAND_UPGRADE=8}
        GameMessageTypes={GAMEMESSAGE_PUSH_MISSION=41, GAMEMESSAGE_DO_COMMAND=42}
        local alive=true
        local selected=nil
        UI={SelectUnit=function(u) selected=u end, GetHeadSelectedUnit=function() return selected end}
        Game={GetActivePlayer=function() return 0 end,
              SelectionListGameNetMessage=function(msg, cmd, d1, d2)
                assert(msg==42 and cmd==9 and selected~=nil, 'must send DO_COMMAND(COMMAND_DELETE) on the selected unit')
                alive=false
              end}
        local unit={GetID=function() return 7 end, GetOwner=function() return 0 end,
                    GetUnitType=function() return 3 end,
                    CanDoCommand=function(self,cmd) return cmd==9 end,
                    DoCommand=function() error('Unit:DoCommand is local-only; must not be used') end}
        Teams={[0]={GetTeamTechs=function() return {HasTech=function() return true end} end}}
        Players={[0]={GetTeam=function() return 0 end,
                      GetUnitByID=function(self,id) if id==7 and alive then return unit end return nil end,
                      GetNumUnits=function() return alive and 5 or 4 end}}
        local r=H.disband_unit(7,0)
        assert(r.ok==true and r.pending==true and r.type=='UNIT_SWORDSMAN', 'disband should be sent')
        assert(r.before.units==5)
        local c=H.disband_unit_check(7,0)
        assert(c.gone==true and c.units==4)
        local r2=H.disband_unit(7,0)
        assert(r2.ok==false and r2.err=='no such unit')
        """)

    def test_found_check_reports_moves_can_found_and_city(self):
        self.run_lua("""
        GameDefines={MOVE_DENOMINATOR=60}
        local plot={IsCity=function() return false end}
        local unit={GetX=function() return 43 end, GetY=function() return 12 end, MovesLeft=function() return 0 end,
                    GetPlot=function() return plot end, GetID=function() return 1 end, GetUnitType=function() return 7 end,
                    CanFound=function(self, pl, vis) assert(vis==nil, 'CanFound arg 2 must be omitted') return true end}
        GameInfo=GameInfo or {}; GameInfo.Units={[7]={ID=7, Type='UNIT_SETTLER'}}
        Map={GetPlot=function(x, y) return plot end}
        Players={[0]={GetUnitByID=function(self, id) if id==1 then return unit end return nil end}}
        H.roster=nil
        local r=H.found_check(1, -1, -1, 0)
        assert(r.ok and r.unit_exists and r.moves==0 and r.can_found==true and r.city==nil and r.x==43)
        -- the pre-check notes the settler so the destroy hook can name it once it is gone (live Assyria t0:
        -- the founding Settler reached the digest as a bare id, the roster being empty before the first turn start)
        assert(H.roster[0][1] and H.roster[0][1].unit=='SETTLER' and H.roster[0][1].x==43, H.json(H.roster))
        -- after founding: unit gone, city on the remembered plot
        plot.IsCity=function() return true end
        Players[0].GetUnitByID=function() return nil end
        plot.GetPlotCity=function() return {GetID=function() return 5 end, GetName=function() return 'Xian' end, GetOwner=function() return 0 end} end
        local r2=H.found_check(1, 43, 12, 0)
        assert(r2.ok and r2.unit_exists==false and r2.city and r2.city.name=='Xian' and r2.city.x==43)
        -- a settler that cannot found (CanFound errors or returns false) says so, and why: the nearest city within
        -- MIN_CITY_RANGE (named when its plot is revealed to me), water, foreign land
        plot.IsCity=function() return false end
        plot.IsWater=function() return false end
        plot.GetOwner=function() return 2 end
        plot.IsRevealed=function() return true end
        Players[0].GetUnitByID=function() return unit end
        Players[0].GetTeam=function() return 0 end
        Players[0].IsAlive=function() return true end
        Players[0].Cities=function() local done=false; return function() if done then return nil end; done=true
          return {GetX=function() return 41 end, GetY=function() return 12 end, GetName=function() return 'Assur' end, Plot=function() return plot end} end end
        -- a City has Plot(), never GetPlot() (live Assyria t60: the read of Malacca's plot raised inside the pcall
        -- and the refusal lost every reason); these fakes have only what the engine has
        Players[2]={IsAlive=function() return true end, GetTeam=function() return 2 end,
                    Cities=function() local done=false; return function() if done then return nil end; done=true
          return {GetX=function() return 43 end, GetY=function() return 14 end, GetName=function() return 'Hidden' end,
                  Plot=function() return {IsRevealed=function() return false end} end} end end}
        Players[3]={IsAlive=function() return true end, GetTeam=function() return 3 end,
                    Cities=function() local done=false; return function() if done then return nil end; done=true
          return {GetX=function() return 46 end, GetY=function() return 12 end, GetName=function() return 'Malacca' end,
                  Plot=function() return {IsRevealed=function() return true end} end} end end}
        Teams={[0]={}}
        GameDefines.MIN_CITY_RANGE=3; GameDefines.MAX_CIV_PLAYERS=4
        Map.PlotDistance=function(x1,y1,x2,y2) return math.max(math.abs(x1-x2), math.abs(y1-y2)) end
        H.owner_label=function(i, pid) return i==pid and 'you' or 'Persia' end
        unit.CanFound=function() error('no') end
        local r3=H.found_check(1, -1, -1, 0)
        assert(r3.can_found==false)
        assert(r3.min_distance==4 and r3.nearest_city and r3.nearest_city.distance==2 and r3.nearest_city.name=='Assur', H.json(r3))
        assert(r3.foreign_owner=='Persia' and r3.water==nil, H.json(r3))
        -- the fogged foreign city is the nearest: counted, not named
        Players[0].Cities=function() return function() return nil end end
        r3=H.found_check(1, -1, -1, 0)
        assert(r3.nearest_city.distance==2 and r3.nearest_city.name==nil, H.json(r3))
        -- a revealed city-state three plots away is named with its owner (live Assyria t60: Malacca from (19,23))
        Players[2].IsAlive=function() return false end
        r3=H.found_check(1, -1, -1, 0)
        assert(r3.nearest_city.distance==3 and r3.nearest_city.name=='Malacca' and r3.nearest_city.owner=='Persia', H.json(r3))
        """)

    def test_generic_popup_shim_replays_button_handlers(self):
        # the shim runs in the GenericPopup state: fake that state's globals, install the shim twice
        # (idempotent), let a layout add buttons, answer one, and check the handler ran and the window closed
        self.run_lua("""
        local hidden = false
        local btns = {}
        for i = 1, 4 do btns[i] = { hidden = true } end
        Controls = { PopupText = { GetText = function() return 'Return it?' end } }
        for i = 1, 4 do
          Controls['Button' .. i] = { IsHidden = function() return btns[i].hidden end }
        end
        ContextPtr = { IsHidden = function() return hidden end }
        local cleared = 0
        function AddButton(text, fn) for i = 1, 4 do if btns[i].hidden then btns[i].hidden = false; break end end end
        function ClearButtons() cleared = cleared + 1; for i = 1, 4 do btns[i].hidden = true end end
        function HideWindow() hidden = true; ClearButtons() end
        """ + Path("harness/lua/generic_popup_shim.lua").read_text() + """
        local first_add = AddButton
        """ + Path("harness/lua/generic_popup_shim.lua").read_text() + """
        assert(AddButton == first_add, 'shim installed twice')
        local pressed = nil
        AddButton('Return the Unit', function() pressed = 'return' end)
        AddButton('Take It', function() pressed = 'take' end)
        local st = __H_popup_state()
        assert(st.open and #st.buttons == 2 and st.buttons[2].text == 'Take It' and st.buttons_shown == 2)
        local r = __H_answer_popup(3)
        assert(r.ok == false and r.buttons == 2)
        r = __H_answer_popup(1)
        assert(r.ok and r.clicked == 'Return the Unit' and r.closed and pressed == 'return' and cleared == 1)
        assert(#__H_BTN == 0)
        r = __H_answer_popup(1)
        assert(r.ok == false and r.err == 'no generic popup is open')
        """)

    def test_pending_popups_carry_data3(self):
        self.run_lua("""
        H.popups = { [52] = { type = 52, player = 0, data1 = 0, data2 = 2, data3 = 745484 } }
        H.enum_name = function() return 'BUTTONPOPUP_RETURN_CIVILIAN' end
        local p = H.pending_popups(0)
        assert(#p == 1 and p[1].data3 == 745484 and p[1].name == 'BUTTONPOPUP_RETURN_CIVILIAN')
        assert(#H.pending_popups(1) == 0)
        """)

    def test_a_puppet_is_never_offered_production_choices(self):
        """Live t192: a Worker pushed into freshly-captured Cusco stuck across the turn boundary and
        displaced the puppet AI's own pick permanently. The stock city screen has no production
        picker for a puppet at all, so both the offer and the order must be refused."""
        self.run_lua("""
        local city = { IsPuppet=function() return true end,
                       GetProductionNameKey=function() return 'TXT_KEY_UNIT_WORKER' end }
        Players={[0]={GetCityByID=function() return city end}}
        local r = H.available_production(1, 0)
        assert(r.ok == false and r.puppet == true and r.items == nil, 'a puppet lists no choices')
        assert(r.err:find('annex'), 'the refusal names the way out: ' .. tostring(r.err))
        assert(r.producing == 'TXT_KEY_UNIT_WORKER', 'what it is building stays readable')
        assert(H.city_production_guard(city) ~= nil)
        """)

    def test_a_directly_run_city_is_still_offered_production(self):
        self.run_lua("""
        local city = { IsPuppet=function() return false end }
        assert(H.city_production_guard(city) == nil)
        """)

    def test_production_automation_decides_what_todo_lists(self):
        """Puppets are always production-automated and the engine never raises
        ENDTURN_BLOCKING_PRODUCTION for them, so an empty queue there is not our decision."""
        self.run_lua("""
        local puppet = { IsPuppet=function() return true end, IsProductionAutomated=function() return true end }
        local mine = { IsPuppet=function() return false end, IsProductionAutomated=function() return false end }
        local old = { IsPuppet=function() return true end }   -- a build without IsProductionAutomated
        assert(H.production_is_automated(puppet) == true)
        assert(H.production_is_automated(mine) == false)
        assert(H.production_is_automated(old) == true, 'falls back to IsPuppet')
        """)

    def test_available_production_lists_faith_purchases(self):
        self.run_lua("""
        YieldTypes={YIELD_GOLD=2, YIELD_FAITH=5}
        local units={ {ID=1, Type='UNIT_WORKER'}, {ID=2, Type='UNIT_MISSIONARY'}, {ID=3, Type='UNIT_GREAT_SCIENTIST'} }
        local blds={ {ID=7, Type='BUILDING_MONASTERY'} }
        GameInfo={Units=function() local i=0 return function() i=i+1 return units[i] end end,
                  Buildings=function() local i=0 return function() i=i+1 return blds[i] end end}
        local city={
          CanTrain=function(_, id) return id==1 end, CanConstruct=function() return false end,
          GetUnitProductionTurnsLeft=function() return 5 end,
          GetUnitPurchaseCost=function() return 310 end, GetBuildingPurchaseCost=function() return -1 end,
          IsCanPurchase=function(_, a, b, uid, bid, c, yield)
            if yield==2 then return uid==1 end
            if a==true and uid==3 then return false end  -- the Great Scientist is not affordable yet
            return uid==2 or uid==3 or bid==7
          end,
          GetUnitFaithPurchaseCost=function(_, id) return ({[2]=200, [3]=1500})[id] end,
          GetBuildingFaithPurchaseCost=function(_, id) return 250 end,
        }
        Players={[0]={GetCityByID=function() return city end}}
        local r=H.available_production(1, 0)
        local by={} for _, it in ipairs(r.items) do by[it.item]=it end
        assert(by.UNIT_WORKER.gold==310 and by.UNIT_WORKER.can_buy==true and by.UNIT_WORKER.faith==nil)
        assert(by.UNIT_MISSIONARY.faith==200 and by.UNIT_MISSIONARY.faith_only==true and by.UNIT_MISSIONARY.turns==nil)
        assert(by.UNIT_GREAT_SCIENTIST.faith==1500 and by.UNIT_GREAT_SCIENTIST.faith_can_buy==false and by.UNIT_MISSIONARY.faith_can_buy==true and by.BUILDING_MONASTERY.faith==250 and by.BUILDING_MONASTERY.kind=='building')
        """)

    def test_choose_ideology_sends_network_choice_only_for_ideologies(self):
        self.run_lua("""
        local sent={}
        Network={SendIdeologyChoice=function(pid, id) sent[#sent+1]={pid,id} end}
        GameInfo={PolicyBranchTypes={POLICY_BRANCH_ORDER={ID=10, Type='POLICY_BRANCH_ORDER', PurchaseByLevel=true},
                                     POLICY_BRANCH_TRADITION={ID=0, Type='POLICY_BRANCH_TRADITION', PurchaseByLevel=false},
                                     [10]={ID=10, Type='POLICY_BRANCH_ORDER', PurchaseByLevel=true}}}
        local tree=-1
        Players={[0]={GetLateGamePolicyTree=function() return tree end, GetNumFreeTenets=function() return 2 end}}
        local r=H.choose_ideology('POLICY_BRANCH_TRADITION', 0)
        assert(r.ok==false and #sent==0)
        r=H.choose_ideology('POLICY_BRANCH_NOPE', 0)
        assert(r.ok==false)
        r=H.choose_ideology('POLICY_BRANCH_ORDER', 0)
        assert(r.ok==true and r.pending==true and sent[1][1]==0 and sent[1][2]==10)
        assert(H.ideology_state(0).ideology==nil)
        tree=10
        local st=H.ideology_state(0)
        assert(st.ideology=='POLICY_BRANCH_ORDER' and st.free_tenets==2)
        r=H.choose_ideology('POLICY_BRANCH_ORDER', 0)
        assert(r.ok==false and r.ideology=='POLICY_BRANCH_ORDER' and #sent==1, 'no second send once chosen')
        """)

    def test_minor_gold_gift_rejects_wrong_amount_and_poverty(self):
        self.run_lua("""
        GameDefines={MINOR_GOLD_GIFT_SMALL=250, MINOR_GOLD_GIFT_MEDIUM=500, MINOR_GOLD_GIFT_LARGE=1000, MAX_MAJOR_CIVS=3}
        Game.GetActivePlayer=function() return 0 end
        Game.DoMinorGoldGift=function() error('must not gift') end
        Teams={[0]={IsHasMet=function(_, t) return t ~= 2 end, IsAtWar=function() return false end}}
        Players={[0]={GetTeam=function() return 0 end, GetGold=function() return 61 end},
                 [1]={IsAlive=function() return true end, GetTeam=function() return 1 end},
                 [2]={IsAlive=function() return true end, GetTeam=function() return 2 end, GetName=function() error('unmet rival read') end},
                 [26]={IsMinorCiv=function() return true end, GetTeam=function() return 26 end,
                       GetFriendshipFromGoldGift=function() return 30 end,
                       GetMinorCivFriendshipWithMajor=function(_, who) return ({[0]=0, [1]=55, [2]=90})[who] end,
                       IsFriends=function() return false end, IsAllies=function(_, who) return who==2 end,
                       GetAlly=function() return 2 end}}
        local r=H.city_state_gifts(26,0)
        assert(r.ok==true and r.small.amount==250 and r.small.affordable==false)
        -- what the ally tooltip shows: an unmet ally stays anonymous, only the influence gap to pass it;
        -- the met non-ally's 55 is shown nowhere and is not returned
        assert(r.rivals==nil and r.ally.met==false and r.ally.player==nil and r.ally.civ==nil and r.ally.to_become_ally==91)
        r=H.minor_gold_gift(26, 250, 0)
        assert(r.ok==false and r.err=='not enough gold')
        r=H.minor_gold_gift(26, 15, 0)
        assert(r.ok==false)
        r=H.city_state_gifts(0,0)
        assert(r.ok==false)
        """)

    def test_city_ranged_attack_does_not_select(self):
        self.run_lua("""
        UI={SelectCity=function() error('SelectCity') end}
        Game={SelectedCitiesGameNetMessage=function() error('needs selection') end}
        local sent={}
        Network={SendDoTask=function(...) sent={...} end}
        TaskTypes={TASK_RANGED_ATTACK=7}
        local city={
          CanRangeStrike=function() return true end,
          CanRangeStrikeAt=function(self,x,y,a,b) assert(x==11 and y==12); return true end,
          GetID=function() return 8192 end, GetX=function() return 10 end, GetY=function() return 12 end,
          GetName=function() return 'Assur' end,
        }
        Map={PlotDistance=function(x1,y1,x2,y2) return math.max(math.abs(x1-x2), math.abs(y1-y2)) end}
        GameDefines={CITY_ATTACK_RANGE=2}
        Players={[0]={GetCityByID=function() return city end}}
        local r=H.city_ranged_attack(8192, 11, 12, 0)
        assert(r.ok==true)
        assert(sent[1]==8192 and sent[2]==7 and sent[3]==11 and sent[4]==12)
        -- out of range is said as such, before the engine's "cannot strike now" (live Assyria t51: the Spearman
        -- three plots from Assur read "city cannot range strike this turn")
        sent={}
        local r2=H.city_ranged_attack(8192, 13, 12, 0)
        assert(r2.ok==false and r2.err:find("3 plots from Assur") and r2.err:find("range is 2") and r2.distance==3, H.json(r2))
        assert(sent[1]==nil, 'nothing sent')
        city.CanRangeStrikeNow=function() return false end
        local r3=H.city_ranged_attack(8192, 11, 12, 0)
        assert(r3.ok==false and r3.err:find("state(what='city', view='strikes')", 1, true), H.json(r3))
        """)

    def test_available_city_strikes_no_select_and_filters(self):
        self.run_lua("""
        UI={SelectCity=function() error('SelectCity') end}
        GameDefines={MAX_CITY_ATTACK_RANGE=1}
        local city={
          GetX=function() return 5 end, GetY=function() return 5 end,
          CanRangeStrike=function() return true end,
          CanRangeStrikeAt=function(self,x,y) return x==6 and y==5 end,
          GetID=function() return 1 end,
        }
        Players={[0]={GetCityByID=function() return city end, GetTeam=function() return 0 end}}
        Map={PlotXYWithRangeCheck=function(x,y,dx,dy,r)
          if dx==1 and dy==0 then
            return {GetX=function() return 6 end, GetY=function() return 5 end,
                    IsVisible=function() return true end, GetNumUnits=function() return 0 end,
                    IsCity=function() return false end}
          end
          return {GetX=function() return x+dx end, GetY=function() return y+dy end,
                  IsVisible=function() return false end}
        end}
        local r=H.available_city_strikes(1, 0)
        assert(r.ok==true and r.can==true and #r.targets==1)
        assert(r.targets[1].x==6 and r.targets[1].y==5)
        city.CanRangeStrike=function() return false end
        r=H.available_city_strikes(1, 0)
        assert(r.ok==true and r.can==false and #r.targets==0)
        city.CanRangeStrike=function() return true end
        city.CanRangeStrikeNow=function() return false end
        r=H.available_city_strikes(1, 0)
        assert(r.ok==true and r.can==false and #r.targets==0)
        """)

    def test_visible_plot_yields_and_city_banner(self):
        self.run_lua("""
        local function no() return false end
        local function yes() return true end
        local p={IsRevealed=yes, IsVisible=yes, GetX=function() return 4 end, GetY=function() return 5 end,
          GetTerrainType=function() return 0 end, IsHills=yes, IsMountain=no, IsRiver=yes,
          GetResourceType=function() return 1 end, GetNumResource=function() return 2 end,
          GetFeatureType=function() return -1 end, GetImprovementType=function() return -1 end,
          GetRouteType=function() return -1 end, GetOwner=function() return 0 end,
          CalculateYield=function(self, i) return ({[0]=2,[1]=1,[2]=0,[3]=0,[4]=0,[5]=0})[i] end,
          IsFreshWater=yes, IsBeingWorked=yes, IsCity=yes, GetNumUnits=function() return 0 end,
          GetPlotCity=function() return {
            GetName=function() return 'Cusco' end, GetOwner=function() return 2 end,
            GetPopulation=function() return 6 end, GetMaxHitPoints=function() return 200 end,
            GetDamage=function() return 20 end, GetStrengthValue=function() return 2149 end,
            GetGarrisonedUnit=function() return {} end, IsPuppet=yes, IsRazing=no,
            GetReligiousMajority=function() return 1 end} end}
        GameInfo={Terrains={[0]={Type='TERRAIN_GRASS'}}, Resources={[1]={Type='RESOURCE_SALT'}}}
        Game={GetReligionName=function() return 'Tengriism' end}
        H.L=function(s) return s end
        local e=H.describe_plot(p, 0)
        assert(e.vis==true and e.yields.food==2 and e.yields.production==1 and e.fresh_water==true)
        assert(e.worked==true and e.resource=='SALT' and e.resource_qty==2)
        assert(e.city.name=='Cusco' and e.city.strength==21.49 and e.city.puppet==true)
        assert(e.city.garrisoned==true and e.city.religion=='Tengriism')
        """)

    def test_city_screen_lists_buildings_queue_and_focus(self):
        self.run_lua("""
        local function no() return false end
        local plots={
          [0]={GetX=function() return 10 end, GetY=function() return 10 end, IsVisible=function() return true end},
          [1]={GetX=function() return 11 end, GetY=function() return 10 end, IsVisible=no,
            CalculateYield=function() error('fogged city-radius yield leak') end},
        }
        local city={
          GetID=function() return 7 end, GetName=function() return 'Agaidika' end,
          GetX=function() return 10 end, GetY=function() return 10 end, GetPopulation=function() return 4 end,
          IsCapital=no, IsPuppet=no, IsOccupied=no, IsRazing=no, IsResistance=no,
          GetFocusType=function() return 1 end, IsForcedAvoidGrowth=no, IsNoAutoAssignSpecialists=no,
          GetNumRealBuilding=function(self,id) return id==3 and 1 or 0 end,
          GetNumFreeBuilding=function() return 0 end,
          IsBuildingSellable=function(self,id) return id==3 end,
          GetSellBuildingRefund=function() return 18 end,
          GetNumSpecialistsInBuilding=function() return 0 end, GetNumSpecialistsAllowedByBuilding=function() return 0 end,
          GetSpecialistCount=function() return 0 end, GetSpecialistGreatPersonProgress=function() return 0 end,
          GetOrderQueueLength=function() return 1 end,
          GetOrderFromQueue=function() return 1, 9 end,
          GetNumCityPlots=function() return 2 end, GetCityIndexPlot=function(self,i) return plots[i] end,
          IsWorkingPlot=function(self,p) return p:GetX()==10 end, IsForcedWorkingPlot=no, CanWork=function() return true end,
          CanBuyPlotAt=no, GetProductionNameKey=function() return 'TXT_KEY_BUILDING_LIBRARY' end,
          GetProductionTurnsLeft=function() return 7 end, FoodDifference=function() return 0 end,
          GetResourceDemanded=function() return -1 end, CanRaze=function() return false end,
        }
        CityAIFocusTypes={CITY_AI_FOCUS_TYPE_FOOD=1, NO_CITY_AI_FOCUS_TYPE=0}
        OrderTypes={ORDER_TRAIN=0, ORDER_CONSTRUCT=1, ORDER_CREATE=2, ORDER_MAINTAIN=3}
        local function rows_iter(rows)
          local i=0; return function() i=i+1; return rows[i] end
        end
        GameInfo={
          Buildings=setmetatable({[9]={Type='BUILDING_LIBRARY'}},
            {__call=function() return rows_iter({{ID=3,Type='BUILDING_LIBRARY',GoldMaintenance=1}}) end}),
          Specialists=function() return function() return nil end end,
          Units={}, Projects={}, Processes={},
        }
        Game.GetActivePlayer=function() return 0 end
        Players={[0]={GetTeam=function() return 0 end, GetCityByID=function(self,id) return id==7 and city or nil end, MayNotAnnex=no, CanRaze=no}}
        H.L=function(s) return 'Library' end
        local r=H.city_screen(7,0)
        assert(r.ok and r.name=='Agaidika' and r.focus=='food' and r.queue[1]=='BUILDING_LIBRARY')
        assert(#r.buildings==1 and r.buildings[1].building=='BUILDING_LIBRARY')
        assert(r.buildings[1].can_sell and r.buildings[1].sell_gold==18 and r.buildings[1].gold_maintenance==1)
        assert(r.plots[1].worked==true and r.plots[2].can_work==true)
        assert(r.meters == nil)
        local miss=H.city_screen(99,0)
        assert(miss.ok==false)
        """)

    def test_luxuries_omit_zero_and_mark_last_copy(self):
        self.run_lua("""
        local function iter()
          local rows={{ID=1,Type='RESOURCE_GEMS',ResourceClassType='RESOURCECLASS_LUXURY'},
                      {ID=2,Type='RESOURCE_SALT',ResourceClassType='RESOURCECLASS_LUXURY'},
                      {ID=3,Type='RESOURCE_IRON',ResourceClassType='RESOURCECLASS_RUSH'}}
          local i=0; return function() i=i+1; return rows[i] end
        end
        GameInfo={Resources=iter}
        Teams={[0]={GetTeamTechs=function() return {HasTech=function() return true end} end}}
        Players={[0]={GetTeam=function() return 0 end,
          GetNumResourceAvailable=function(self,id) return ({[1]=1,[2]=0,[3]=2})[id] end,
          GetNumResourceTotal=function(self,id) return ({[1]=1,[2]=0,[3]=2})[id] end,
          GetResourceImport=function() return 0 end, GetResourceExport=function() return 0 end}}
        local lux=H.luxuries(0)
        assert(lux.GEMS.available==1 and lux.GEMS.last_copy==true)
        assert(lux.SALT==nil)
        assert(lux.IRON==nil)
        """)

    def test_bonus_resources_match_the_resource_list(self):
        self.run_lua("""
        local rows = {
          {ID=1, Type='RESOURCE_WHEAT', ResourceClassType='RESOURCECLASS_BONUS'},
          {ID=2, Type='RESOURCE_DEER', ResourceClassType='RESOURCECLASS_BONUS'},
          {ID=3, Type='RESOURCE_COW', ResourceClassType='RESOURCECLASS_BONUS', TechReveal='TECH_TRAPPING'},
          {ID=4, Type='RESOURCE_SILK', ResourceClassType='RESOURCECLASS_LUXURY'},
          {ID=5, Type='RESOURCE_IRON', ResourceClassType='RESOURCECLASS_RUSH'},
          {ID=6, Type='RESOURCE_CRAB', ResourceClassType='RESOURCECLASS_BONUS'},
        }
        GameInfo = { Resources = function()
          local i = 0
          return function() i = i + 1; return rows[i] end
        end }
        GameInfoTypes = { TECH_TRAPPING = 40 }
        Teams = {[0] = { GetTeamTechs = function() return { HasTech = function(_, id) return id ~= 40 end } end }}
        local total = {[1]=4, [2]=0, [3]=3, [4]=2, [5]=1, [6]=0}
        local avail = {[1]=4, [2]=0, [3]=3, [4]=2, [5]=1, [6]=0}
        local exported = {[6]=2}
        Players = {[0] = {
          GetTeam = function() return 0 end,
          GetNumResourceAvailable = function(_, id) return avail[id] or 0 end,
          GetNumResourceTotal = function(_, id) return total[id] or 0 end,
          GetResourceImport = function() return 0 end,
          GetResourceExport = function(_, id) return exported[id] or 0 end,
          GetNumResourceUsed = function() return 0 end,
        }}
        local b = H.bonus_resources(0)
        assert(b.WHEAT.available == 4 and b.WHEAT.total == 4 and b.WHEAT.used == nil)
        assert(b.DEER == nil, 'a bonus the empire does not have is not on the list')
        assert(b.COW == nil, 'an unrevealed bonus must not leak')
        assert(b.SILK == nil and b.IRON == nil)
        assert(b.CRAB.total == 0 and b.CRAB.exported == 2 and b.CRAB.available == 0)
        """)

    def test_strategic_row_carries_used_when_the_list_would_print_it(self):
        self.run_lua("""
        local rows = {
          {ID=1, Type='RESOURCE_IRON', ResourceClassType='RESOURCECLASS_RUSH'},
          {ID=2, Type='RESOURCE_COAL', ResourceClassType='RESOURCECLASS_RUSH', TechReveal='TECH_SCIENTIFIC_THEORY'},
          {ID=3, Type='RESOURCE_URANIUM', ResourceClassType='RESOURCECLASS_MODERN'},
          {ID=4, Type='RESOURCE_HORSE', ResourceClassType='RESOURCECLASS_RUSH'},
        }
        GameInfo = { Resources = function()
          local i = 0
          return function() i = i + 1; return rows[i] end
        end }
        GameInfoTypes = { TECH_SCIENTIFIC_THEORY = 11 }
        Teams = {[0] = { GetTeamTechs = function() return { HasTech = function() return false end } end }}
        local avail = {[1]=-2, [3]=0, [4]=2}
        local total = {[1]=4, [3]=0, [4]=4}
        local used = {[1]=6, [4]=0}
        local imported = {[1]=1}
        Players = {[0] = {
          GetTeam = function() return 0 end,
          GetNumResourceAvailable = function(_, id) return avail[id] or 0 end,
          GetNumResourceTotal = function(_, id) return total[id] or 0 end,
          GetResourceImport = function(_, id) return imported[id] or 0 end,
          GetResourceExport = function() return 0 end,
          GetNumResourceUsed = function(_, id) return used[id] or 0 end,
        }}
        local r = H.strategic_resources(0)
        assert(r.IRON.available == -2 and r.IRON.total == 4 and r.IRON.used == 6 and r.IRON.imported == 1)
        assert(r.COAL == nil, 'unrevealed coal must not leak')
        assert(r.URANIUM.available == 0 and r.URANIUM.used == nil)
        assert(r.HORSE.available == 2 and r.HORSE.used == nil and r.HORSE.imported == nil)
        """)

    def test_resource_hover_is_static_text_even_under_fog(self):
        self.run_lua("""
        Locale = { ConvertTextKey = function(k)
          if k == 'TXT_KEY_RESOURCE_SALT_HELP' then
            return '[COLOR_POSITIVE_TEXT]Salt.[ENDCOLOR] A luxury.'
          end
          return k
        end }
        local changes = {
          { ResourceType = 'RESOURCE_SALT', YieldType = 'YIELD_GOLD', Yield = 1 },
          { ResourceType = 'RESOURCE_SALT', YieldType = 'YIELD_FOOD', Yield = 1 },
          { ResourceType = 'RESOURCE_IRON', YieldType = 'YIELD_PRODUCTION', Yield = 1 },
          { ResourceType = 'RESOURCE_WHEAT', YieldType = 'YIELD_FOOD', Yield = 0 },
        }
        GameInfo = {
          Terrains = {[0] = { Type = 'TERRAIN_GRASS' }},
          Resources = {
            [1] = { Type = 'RESOURCE_SALT', Happiness = 4, Help = 'TXT_KEY_RESOURCE_SALT_HELP' },
            [2] = { Type = 'RESOURCE_WHEAT', Happiness = 0 },
          },
          Resource_YieldChanges = function()
            local i = 0
            return function() i = i + 1; return changes[i] end
          end,
        }
        local function no() return false end
        local function base(visible, res)
          return {
            IsRevealed = function() return true end,
            IsVisible = function() return visible end,
            GetX = function() return 4 end, GetY = function() return 5 end,
            GetTerrainType = function() return 0 end,
            IsHills = no, IsMountain = no, IsRiver = no,
            GetResourceType = function() return res end,
            GetNumResource = function() return 1 end,
            GetRevealedImprovementType = function() return -1 end,
            GetRevealedRouteType = function() return -1 end,
            GetRevealedOwner = function() return -1 end,
          }
        end
        local fog = base(false, 1)
        setmetatable(fog, { __index = function(_, key) error('fogged live read: ' .. key) end })
        local e = H.describe_plot(fog, 0)
        assert(e.vis == false and e.resource == 'SALT')
        -- v216: the hover (happiness, improved yields, blurb) is printed once in reference("resources"),
        -- never on the plot -- it is the same text on every Salt tile.
        assert(e.resource_happiness == nil and e.resource_improved_yields == nil and e.resource_help == nil)
        assert(e.yields == nil and e.feature == nil and e.units == nil)
        local ref = H.reference('resources')
        assert(ref.ok and ref.section == 'resources' and #ref.rows == 2, tostring(#ref.rows))
        local salt = ref.rows[1].type == 'RESOURCE_SALT' and ref.rows[1] or ref.rows[2]
        assert(salt.happiness == 4 and salt.help == 'Salt. A luxury.', tostring(salt.help))
        assert(salt.improved_yields.gold == 1 and salt.improved_yields.food == 1 and salt.improved_yields.production == nil)
        local vis = base(true, 2)
        vis.GetFeatureType = function() return -1 end
        vis.GetImprovementType = function() return -1 end
        vis.GetRouteType = function() return -1 end
        vis.GetOwner = function() return -1 end
        vis.IsCity = function() return false end
        vis.GetNumUnits = function() return 0 end
        vis.CalculateYield = function() return 2 end
        vis.IsFreshWater = no
        vis.IsBeingWorked = no
        local w = H.describe_plot(vis, 0)
        assert(w.vis == true and w.resource == 'WHEAT')
        assert(w.resource_happiness == nil and w.resource_improved_yields == nil and w.resource_help == nil)
        assert(w.yields.food == 2)
        """)


class ModalFlagsAndSelectTests(unittest.TestCase):
    def _detached_game(self):
        from harness.game import Game
        g = Game.__new__(Game)
        g.seat = 0
        g._runtime_ok = True
        return g

    def test_move_unit_python_does_not_select(self):
        calls = []
        g = self._detached_game()
        g.q = lambda code, timeout=None: calls.append(code) or {"ok": True, "x": 13, "y": 25, "moves": 2}
        g.move_unit(24576, 12, 25, settle_timeout=0)
        # a selection-free attack_before read (is the destination a melee target?), then the order; a
        # "did not move" result may add a read-only units() lookup for the blocker hint
        self.assertGreaterEqual(len(calls), 2)
        self.assertIn("H.attack_before", calls[0])
        self.assertIn("H.move_unit", calls[1])
        for code in calls:
            self.assertNotIn("SelectUnit", code)
            self.assertNotIn("SelectionListMove", code)

    def test_move_unit_reports_a_swap(self):
        """Live t252: a Worker ordered into Goshute traded places with the Worker standing there.
        The order carries who stood on the destination; once the mover has arrived, the one of
        them now on the mover's old plot is reported as swapped_with."""
        calls = []
        g = self._detached_game()

        def q(code, timeout=None):
            calls.append(code)
            if "H.attack_before" in code:
                return {"ok": True}
            if "H.move_unit" in code:
                return {"ok": True, "x": 45, "y": 29, "moves": 2,
                        "swap_candidates": [{"id": 819222, "type": "WORKER"}]}
            if "H.unit_pos" in code:
                return {"ok": True, "x": 46, "y": 29, "moves": 1, "activity": 0}
            if "H.swapped_unit" in code:
                self.assertIn("{819222}", code)
                self.assertIn(", 45, 29,", code)
                return {"ok": True, "unit": {"id": 819222, "type": "WORKER", "x": 45, "y": 29, "moves": 0}}
            return {"ok": True}

        g.q = q
        r = g.move_unit(778244, 46, 29, settle_timeout=0.5)
        self.assertTrue(r.get("arrived"))
        self.assertEqual(r["swapped_with"]["id"], 819222)
        self.assertIn("swapped places with WORKER 819222", r["note"])
        self.assertIn("(45,29)", r["note"])

    def test_move_unit_without_candidates_asks_no_swap_question(self):
        calls = []
        g = self._detached_game()
        g.q = lambda code, timeout=None: calls.append(code) or (
            {"ok": True, "x": 46, "y": 29, "moves": 1, "activity": 0} if "H.unit_pos" in code
            else {"ok": True, "x": 45, "y": 29, "moves": 2})
        r = g.move_unit(778244, 46, 29, settle_timeout=0.5)
        self.assertTrue(r.get("arrived"))
        self.assertNotIn("swapped_with", r)
        self.assertFalse([c for c in calls if "H.swapped_unit" in c])

    def test_unit_mission_python_does_not_select(self):
        calls = []
        g = self._detached_game()
        g.q = lambda code, timeout=None: calls.append(code) or {"ok": True}
        g.unit_mission(16385, "MISSION_FORTIFY")
        # the mission push plus a selection-free after-state read (unit_pos); never a UI select
        self.assertGreaterEqual(len(calls), 1)
        self.assertIn("H.unit_mission", calls[0])
        for code in calls:
            self.assertNotIn("SelectUnit", code)
            self.assertNotIn("CanHandleAction", code)
            self.assertNotIn("SelectionListGameNetMessage", code)

    def test_answer_popup_uses_generic_popup_state_only(self):
        g = self._detached_game()
        g._popup_shim_ok = True
        calls = []
        g.c = type("C", (), {"query": lambda self, state, body, timeout=None: calls.append((state, body)) or {"ok": True, "clicked": "Take It", "closed": True}})()
        g.discussion_pending = lambda: False
        g.turn_state = lambda: {"pending_popups": []}
        r = g.answer_popup(2)
        self.assertTrue(r["ok"])
        self.assertEqual(calls, [("GenericPopup", "return __H_answer_popup(2)")])
        self.assertFalse(r["discussion_pending"])

    def test_generic_popup_flags_pre_shim_popup(self):
        g = self._detached_game()
        g._popup_shim_ok = True
        g.c = type("C", (), {"query": lambda self, state, body, timeout=None: {"open": True, "text": "?", "buttons": [], "buttons_shown": 2}})()
        g.q = lambda code, timeout=None: []
        r = g.generic_popup()
        self.assertTrue(r["open"])
        self.assertIn("before the shim", r["note"])

    def test_diff_snapshot_tolerates_empty_lua_resources_table(self):
        from harness.game import Game
        before = {"gold": 551, "gold_per_turn": 55, "happiness": 16, "deals": 3, "resources": []}
        after = {"gold": 308, "gold_per_turn": 55, "happiness": 16, "deals": 4, "resources": []}
        eff = Game._diff_snapshot(before, after)
        self.assertEqual(eff, {"gold": {"before": 551, "after": 308}, "deals": {"before": 3, "after": 4}})

    def test_respond_discussion_reports_the_next_queued_question(self):
        g = self._detached_game()
        first = {"pending": True, "screen": "discussion", "leader": "A", "speech": "war?", "buttons": [{"id": 1, "text": "no", "disabled": False}]}
        second = {"pending": True, "screen": "trade", "leader": "B", "speech": "renew?", "buttons": [], "how_to_answer": "accept_deal"}
        seq = iter([first, second])
        g.discussion = lambda pid=None: next(seq)
        g.discussion_pending = lambda: True
        g.incoming_deal = lambda pid=None: {"items": [{"type": "OPEN_BORDERS"}]}
        g._settle_leader_remark = lambda wait=1.5, player=None: {"remark": "ok"}
        calls = []
        g.c = type("C", (), {"exec": lambda self, *a, **k: calls.append(a) or [],
                             "wait_state": lambda self, name, t: name})()
        r = g.respond_discussion(1)
        self.assertEqual(calls, [("DiscussionDialog", "OnButton1()")])
        self.assertTrue(r["still_pending"])
        self.assertEqual(r["next"]["leader"], "B")
        self.assertEqual(r["next"]["deal"], [{"type": "OPEN_BORDERS"}])

    def test_establish_trade_route_by_city_name(self):
        g = self._detached_game()
        rows = [{"city_name": "Antwerp", "kind": "international", "x": 28, "y": 17, "trade_connection_type": 0},
                {"city_name": "Beijing", "kind": "food", "x": 24, "y": 23, "trade_connection_type": 1},
                {"city_name": "Beijing", "kind": "production", "x": 24, "y": 23, "trade_connection_type": 2}]
        g.available_trade_routes = lambda unit_id, pid=None: rows
        g.trade_routes = lambda pid=None: []
        calls = []
        g.q = lambda code, timeout=None: calls.append(code) or {"ok": False, "err": "stub"}
        r = g.establish_trade_route(5, city_name="antwerp")
        self.assertEqual(r, {"ok": False, "err": "stub"})
        self.assertIn("H.establish_trade_route(5, 28, 17, 0", calls[-1])
        r = g.establish_trade_route(5, city_name="Beijing")
        self.assertFalse(r["ok"]); self.assertIn("kind=", r["err"])
        g.establish_trade_route(5, city_name="Beijing", kind="production")
        self.assertIn("H.establish_trade_route(5, 24, 23, 2", calls[-1])
        r = g.establish_trade_route(5, city_name="Ur")
        self.assertFalse(r["ok"]); self.assertEqual(len(r["available"]), 3)
        r = g.establish_trade_route(5)
        self.assertFalse(r["ok"])
        # the destination alone (Codex t64: dest_x/dest_y and kind, no trade_type, was refused)
        g.establish_trade_route(5, dest_x=28, dest_y=17)
        self.assertIn("H.establish_trade_route(5, 28, 17, 0", calls[-1])
        r = g.establish_trade_route(5, dest_x=24, dest_y=23)
        self.assertFalse(r["ok"]); self.assertIn("kind=", r["err"])
        g.establish_trade_route(5, dest_x=24, dest_y=23, kind="food")
        self.assertIn("H.establish_trade_route(5, 24, 23, 1", calls[-1])
        r = g.establish_trade_route(5, dest_x=1, dest_y=1)
        self.assertFalse(r["ok"]); self.assertEqual(len(r["available"]), 3)

    def test_establish_trade_route_names_the_caravans_new_id(self):
        # Codex c41 (2026-09-27): the reply's route.unit.id differed from the id passed, and the agent read it
        # as "a different unit was substituted and mine consumed". Same caravan, re-created for the route.
        g = self._detached_game()
        g.available_trade_routes = lambda unit_id, pid=None: [
            {"city_name": "Antwerp", "kind": "international", "x": 28, "y": 17, "trade_connection_type": 0}]
        reads = []
        g.trade_routes = lambda pid=None: reads.append(1) or ({"outgoing": []} if len(reads) == 1 else
            {"outgoing": [{"from_city": "Rome", "to_city": "Antwerp", "turns_left": 30, "unit": {"id": 99}}]})
        g._order = lambda code: {"ok": True}
        r = g.establish_trade_route(5, city_name="Antwerp")
        self.assertTrue(r["established"])
        self.assertEqual(r["unit_id_now"], 99)
        self.assertIn("re-created by the engine under id 99", r["note"])
        self.assertIn("nothing was substituted", r["note"])

    def test_accept_deal_clicks_open_diplotrade(self):
        g = self._detached_game()
        execs = []
        g.states = lambda: {2: "DiploTrade"}
        g._screens = lambda: {"trade_state": "DiploTrade", "discussion_pending": True, "screens": {"DiploTrade": True}}
        g.c = type("C", (), {"exec": staticmethod(lambda state, lua, check=True: execs.append((state, lua)) or [])})()
        def q(code, timeout=None):
            if "H.accept_deal" in code:
                raise AssertionError("should not fall back")
            return {"ok": True, "items": [], "deals": 1}  # incoming_deal / _deal_snapshot reads around the click
        g.q = q
        g._settle_leader_remark = lambda wait=1.5: {}
        with mock.patch("time.sleep"):
            r = g.accept_deal()
        self.assertTrue(r["ok"])
        self.assertEqual(execs[0][0], "DiploTrade")
        self.assertIn("OnPropose", execs[0][1])
        execs.clear()
        with mock.patch("time.sleep"):
            r = g.refuse_deal()
        self.assertIn("OnBack", execs[0][1])

    def test_turn_state_reports_modal_flags_without_querying_missing_states(self):
        g = self._detached_game()
        g.q = lambda code, timeout=None: {"active_player": 0, "pending_popups": []}
        g.c = type("C", (), {
            "states": staticmethod(lambda: {1: "InGame"}),
            "query": staticmethod(lambda state, lua, timeout=None: (_ for _ in ()).throw(
                AssertionError(f"queried missing popup {state}"))),
        })()
        ts = g.turn_state()
        for flag in (
            "leader_greeting_pending", "city_state_greeting_pending",
            "great_person_reward_pending", "tech_popup_pending", "discussion_pending",
        ):
            self.assertIn(flag, ts)
            self.assertFalse(ts[flag])

    def test_wait_for_my_turn_returns_early_when_tech_choice_is_unset(self):
        g = self._detached_game()
        calls = {"n": 0}

        def q(code, timeout=None):
            calls["n"] += 1
            if "H.current_research(" in code:
                return -1
            return {
                "active_player": 0, "my_turn": False, "processing": False,
                "hotseat": False, "tech_popup_pending": True,
            }

        g.q = q
        g.c = type("C", (), {
            "ping": staticmethod(lambda: {"connected": True}),
            "states": staticmethod(lambda: {1: "InGame", 2: "TechPopup"}),
            "query": staticmethod(lambda state, lua, timeout=None: state == "TechPopup"),
        })()
        g.dismiss_pending_popups = lambda ts=None: []
        ts = g.wait_for_my_turn(timeout=2, poll=0.01)
        self.assertTrue(ts["tech_popup_pending"])

    def test_turn_state_sets_discussion_if_either_dialog_is_up(self):
        g = self._detached_game()
        # v214: H.modal_flags is the one read; the DiscussionDialog alone (no trade table) counts
        g.q = lambda code, timeout=None: ({"discussion_pending": True, "screens": {"DiscussionDialog": True}}
                                          if "modal_flags" in code else {"pending_popups": []})
        ts = g.turn_state()
        self.assertTrue(ts["discussion_pending"])
        self.assertFalse(ts["leader_greeting_pending"])
        self.assertFalse(ts["tech_popup_pending"])
        self.assertIn("leader_screen_note", ts)

    def _greeting_game(self, up):
        g = self._detached_game()

        def q(code, timeout=None):
            if "modal_flags" in code:
                return {"leader_greeting_pending": up["v"], "leader_head_root_up": up["v"],
                        "screens": {"LeaderHeadRoot": up["v"]}}
            return {"pending_popups": []}
        g.q = q
        execs = []

        def exec_(state, lua, check=True):
            execs.append((state, lua))
            if "DequeuePopup" in lua:
                up["v"] = False
                return []
            return ["2\tTemujin of Mongolia\tNeutral\tfalse", "Greetings. I am Temujin."]

        g.c = type("C", (), {
            "states": staticmethod(lambda: {1: "InGame", 2: "LeaderHeadRoot", 3: "DiscussionDialog"}),
            "wait_state": staticmethod(lambda name, timeout: name),
            "exec": staticmethod(exec_),
        })()
        g.relationship = lambda other, pid=None: {"ok": False}
        return g, execs

    def test_greeting_is_readable_and_flags_the_frozen_blocker(self):
        g, _ = self._greeting_game({"v": True})
        ts = g.turn_state()
        self.assertTrue(ts["leader_greeting_pending"])
        self.assertIn("answer(choice='leave')", ts["leader_screen_note"])
        d = g.discussion()
        self.assertEqual((d["pending"], d["screen"], d["player"]), (True, "greeting", 2))
        self.assertEqual(d["speech"], "Greetings. I am Temujin.")
        self.assertEqual(d["buttons"], [])
        # GitLab #154: the greeting read is the greeting; the standing (approach guess, discuss flags, opinion) is
        # state(what='civ', view='summary') afterwards, as the overview is for a human once the screen closes
        self.assertNotIn("relationship", d)
        self.assertIn("view='summary'", d["how_to_answer"])

    def test_dismiss_discussion_cancels_a_bare_trade_table(self):
        """Live hotseat t38 (2026-10-30): a DiploTrade from seat 0 to seat 1 with nothing on it and no
        DiscussionDialog; Back on the hidden dialog closed nothing and every order was refused on the gate. The
        table's own Cancel (tradelogic.lua OnBack) closes it; a PvP table takes CANCEL_TYPE (0)."""
        for state, back in (("DiploTrade", "OnBack()"), ("SimpleDiploTrade", "OnBack(0)")):
            g, execs = self._bare_trade_table_game(state)
            with mock.patch("harness.game_parts.diplomacy.time.sleep"):
                r = g.dismiss_discussion()
            self.assertEqual(r, {"ok": True, "closed": "trade_table", "via": f"{state}.OnBack"})
            self.assertEqual(execs, [(state, back)])

    def _bare_trade_table_game(self, state):
        """A game with only the trade table `state` up (no DiscussionDialog); any exec closes it."""
        g = self._detached_game()
        up = {"v": True}
        g.q = lambda code, timeout=None: ({"leader_greeting_pending": False, "discussion_pending": up["v"],
                                           "trade_state": state if up["v"] else None,
                                           "screens": {"DiscussionDialog": False, state: up["v"]}}
                                          if "modal_flags" in code else {"pending_popups": []})
        execs = []

        def exec_(st, lua, check=True):
            execs.append((st, lua))
            up["v"] = False
            return []
        g.c = type("C", (), {"states": staticmethod(lambda: {1: "InGame", 2: state}),
                             "wait_state": staticmethod(lambda name, timeout: name), "exec": staticmethod(exec_)})()
        return g, execs

    def test_dismiss_discussion_closes_a_plain_greeting(self):
        up = {"v": True}
        g, execs = self._greeting_game(up)
        self.assertEqual(g.dismiss_discussion(), {"ok": True, "closed": "greeting", "closed_count": 1})
        self.assertEqual([s for s, _ in execs], ["LeaderHeadRoot"])
        self.assertNotIn("leader_screen_note", g.turn_state())


class QueueTests(unittest.TestCase):
    def test_parallel_client_calls_cannot_swap_replies(self):
        class Wire:
            def write(self, data): self.request=json.loads(data)
            def flush(self): time.sleep(0.001)
            def readline(self): return json.dumps(self.request).encode()
        client=Civ5.__new__(Civ5)
        client.f=Wire(); client._lock=threading.RLock()
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(lambda n: client.call(number=n)['number'], range(50)))
        self.assertEqual(results,list(range(50)))

    def test_competing_operation_times_out_without_running(self):
        with action_lock('test-safety-socket'):
            with ThreadPoolExecutor(max_workers=1) as pool:
                def competing():
                    with action_lock('test-safety-socket', timeout=0.03):
                        self.fail('overlapping operation entered')
                with self.assertRaises(TimeoutError): pool.submit(competing).result()
        with action_lock('test-safety-socket', timeout=0.03):
            pass  # The queue is usable after the refused operation.




class McpArgumentTests(unittest.TestCase):
    def test_unknown_tool_argument_is_rejected(self):
        """The MCP SDK's argument models ignore unknown keys by default, so a misspelled parameter
        (timeout vs timeout_seconds) silently ran with the default. The server forbids extras."""
        import asyncio
        from harness import mcp_server
        with self.assertRaises(Exception) as cm:
            asyncio.run(mcp_server.mcp.call_tool("turn_status", {"bogus": 1}))
        self.assertIn("bogus", str(cm.exception))


class RawLuaGateTests(unittest.TestCase):
    """The raw `lua` escape hatch is opt-in: absent from the tool list and refused in-body unless CIV5_ALLOW_LUA is set."""

    def setUp(self):
        import os
        self._saved = os.environ.pop("CIV5_ALLOW_LUA", None)

    def tearDown(self):
        import os
        if self._saved is not None:
            os.environ["CIV5_ALLOW_LUA"] = self._saved
        else:
            os.environ.pop("CIV5_ALLOW_LUA", None)

    def test_lua_absent_and_refused_by_default(self):
        import os
        from harness import mcp_server
        names = {t.name for t in mcp_server.mcp._tool_manager.list_tools()}
        self.assertNotIn("lua", names)
        self.assertFalse(mcp_server.register_lua_if_allowed())
        self.assertNotIn("lua", {t.name for t in mcp_server.mcp._tool_manager.list_tools()})
        self.assertFalse(mcp_server.lua_allowed())
        for v in ("", "0", "false", "no"):
            os.environ["CIV5_ALLOW_LUA"] = v
            self.assertFalse(mcp_server.lua_allowed(), v)

    def test_lua_registered_only_with_opt_in(self):
        import os
        from harness import mcp_server
        os.environ["CIV5_ALLOW_LUA"] = "1"
        self.assertTrue(mcp_server.lua_allowed())
        try:
            self.assertTrue(mcp_server.register_lua_if_allowed())
            self.assertIn("lua", {t.name for t in mcp_server.mcp._tool_manager.list_tools()})
            self.assertFalse(mcp_server.register_lua_if_allowed())  # idempotent
        finally:
            mcp_server.mcp._tool_manager._tools.pop("lua", None)




class DealItemLegalityTests(unittest.TestCase):
    """_check_deal_items refuses, before any screen opens, everything tradelogic.lua's own clamps and pocket
    gates would never let a human put on the table: bad amounts, over-limit amounts, and city ids that fail
    IsPossibleToTradeItem (OnChooseCity -> AddCityTrade is unconditional in the game's UI code)."""

    CATALOG = {"ok": True, "gold": {"us": True, "them": True, "us_available": 500, "them_available": 40},
               "gold_per_turn": {"us": True, "them": True, "us_available": 20, "them_available": 3},
               "open_borders": {"us": True, "them": False}, "embassy": {"us": True, "them": True},
               "resources": [{"resource": "RESOURCE_DYE", "us": True, "them": False, "us_available": 2, "them_available": 0}],
               "cities": {"us": [{"id": 12, "name": "Spare", "x": 5, "y": 6}], "them": []}}

    def game(self):
        from harness.game import Game
        g = Game.__new__(Game)          # no socket: __post_init__ skipped on purpose
        g.seat = 0
        g.trade_catalog = lambda other, pid=None: dict(self.CATALOG)
        return g

    def check(self, *items):
        return self.game()._check_deal_items(1, list(items), 0)

    def test_valid_items_pass(self):
        self.assertTrue(self.check({"type": "GOLD", "from_us": True, "amount": 500})["ok"])
        self.assertTrue(self.check({"type": "GOLD_PER_TURN", "from_us": False, "amount": 3})["ok"])
        self.assertTrue(self.check({"type": "RESOURCES", "resource": "DYE", "from_us": True, "amount": 2})["ok"])
        self.assertTrue(self.check({"type": "CITIES", "from_us": True, "city_id": 12})["ok"])
        self.assertTrue(self.check({"type": "OPEN_BORDERS", "from_us": True})["ok"])

    def test_amounts_must_be_positive_integers(self):
        for bad in (0, -5, 1.5, "10", True, None):
            r = self.check({"type": "GOLD", "from_us": True, "amount": bad})
            if bad is None:
                self.assertTrue(r["ok"])       # amount omitted = the pocket default, fine
            else:
                self.assertFalse(r["ok"], repr(bad))
                self.assertIn("positive whole number", r["err"])

    def test_amounts_over_what_the_side_has_are_refused(self):
        r = self.check({"type": "GOLD", "from_us": True, "amount": 501})
        self.assertFalse(r["ok"]); self.assertEqual(r["available"], 500)
        r = self.check({"type": "GOLD", "from_us": False, "amount": 41})
        self.assertFalse(r["ok"]); self.assertEqual(r["available"], 40)
        r = self.check({"type": "GOLD_PER_TURN", "from_us": False, "amount": 4})
        self.assertFalse(r["ok"]); self.assertEqual(r["available"], 3)
        r = self.check({"type": "RESOURCES", "resource": "RESOURCE_DYE", "from_us": True, "amount": 3})
        self.assertFalse(r["ok"]); self.assertEqual(r["available"], 2)

    def test_city_must_pass_the_ui_gate(self):
        r = self.check({"type": "CITIES", "from_us": True, "city_id": 11})     # our capital, not tradeable
        self.assertFalse(r["ok"]); self.assertEqual(r["tradeable_cities"], self.CATALOG["cities"]["us"])
        r = self.check({"type": "CITIES", "from_us": False, "city_id": 21})    # theirs: nothing tradeable
        self.assertFalse(r["ok"]); self.assertEqual(r["tradeable_cities"], [])
        r = self.check({"type": "CITIES", "from_us": True})                    # no id at all
        self.assertFalse(r["ok"]); self.assertIn("city_id", r["err"])
        r = self.check({"type": "CITIES", "from_us": True, "city_id": "12"})
        self.assertFalse(r["ok"])

    def test_non_object_items_and_unknown_types_are_refused(self):
        self.assertFalse(self.check("GOLD")["ok"])
        self.assertFalse(self.check({"type": "DECLARATION_OF_FRIENDSHIP", "from_us": True})["ok"])
        self.assertFalse(self.check({"type": "PEACE_TREATY", "from_us": True})["ok"])


class UnknownToolHintTest(unittest.TestCase):
    def test_alias_and_close_matches(self):
        from harness.mcp_server import unknown_tool_hint
        known = ["overview", "map_window", "turn_status", "units", "unit_mission"]
        self.assertIn("Did you mean: overview", unknown_tool_hint("summary", known))
        self.assertIn("map_window", unknown_tool_hint("plots_around", known))
        self.assertIn("units", unknown_tool_hint("unit", known))
        self.assertIn("tools/list", unknown_tool_hint("xyzzy", known))


class PlainTextTest(unittest.TestCase):
    def test_markup_removed_nested(self):
        from harness.game import plain_text
        v = {"a": ["[COLOR_POSITIVE_TEXT]Free Thought[ENDCOLOR][NEWLINE]+1 [ICON_RESEARCH] Science"],
             "b": "x.[NEWLINE][NEWLINE][COLOR_POSITIVE_TEXT]RIGHT-CLICK[ENDCOLOR] to dismiss.", "c": 3, "d": "[x]", "e": "[SPACE]Work has now begun on a Research Lab."}
        self.assertEqual(plain_text(v), {"a": ["Free Thought\n+1 Science"], "b": "x.", "c": 3, "d": "[x]", "e": "Work has now begun on a Research Lab."})

    def test_civilopedia_link_keeps_its_word(self):
        from harness.game import plain_text
        # the build descriptions on the tech tree (live t160 Mongolia: Refrigeration's Offshore Platform row)
        self.assertEqual(plain_text({"name": "Create [LINK=IMPROVEMENT_OFFSHORE_PLATFORM]Offshore Platform[\\LINK]",
                                     "road": "Construct a [LINK=CONCEPT_MOVEMENT]Road[\\LINK]"}),
                         {"name": "Create Offshore Platform", "road": "Construct a Road"})


class ToolSignatureTest(unittest.TestCase):
    def test_signature_lists_params_and_defaults(self):
        from harness.mcp_server import tool_signature
        sig = tool_signature({"properties": {"unit_id": {"type": "integer"}, "dest_x": {"type": "integer", "default": -1}},
                              "required": ["unit_id"]})
        self.assertEqual(sig, "(unit_id: integer, dest_x: integer = -1)")


class RespondDiscussionExpectTest(unittest.TestCase):
    def test_mismatch_presses_nothing(self):
        from harness.game import Game
        g = Game.__new__(Game)
        g.discussion = lambda pid=None: {"pending": True, "screen": "discussion", "buttons": [
            {"id": 1, "disabled": False, "text": "Sorry, we have no interest in this arrangement."},
            {"id": 4, "disabled": False, "text": "Yes, let's get this started. (Declares War)"}]}
        pressed = []
        g.c = type("C", (), {"wait_state": lambda self, *a: pressed.append("wait") or 1,
                             "exec": lambda self, *a, **k: pressed.append(a)})()
        r = g.respond_discussion(4, expect="no interest")
        self.assertFalse(r["ok"])
        self.assertIn("Declares War", r["err"])
        self.assertEqual(pressed, [])


if __name__=='__main__': unittest.main()


class TestAliasArguments:
    def test_renames_to_obvious_parameter(self):
        from harness.mcp_server import alias_arguments
        schema = {"properties": {"unit_id": {}, "dest_x": {}, "dest_y": {}, "button_id": {}}}
        assert alias_arguments({"unit_id": 1, "x": 2, "y": 3}, schema) == {"unit_id": 1, "dest_x": 2, "dest_y": 3}
        assert alias_arguments({"button": 1}, schema) == {"button_id": 1}

    def test_leaves_known_or_already_given_keys(self):
        from harness.mcp_server import alias_arguments
        schema = {"properties": {"x": {}, "button_id": {}}}
        assert alias_arguments({"x": 2, "button": 1, "button_id": 3}, schema) == {"x": 2, "button": 1, "button_id": 3}


class TestBlockerHint:
    me = {"id": 1, "type": "SS_BOOSTER", "strength": 0, "domain": "LAND"}

    def test_idle_caravan_is_named(self):
        from harness.game import Game
        mine = [{"id": 2, "type": "CARAVAN", "x": 24, "y": 23, "strength": 0, "domain": "LAND", "automated": False}]
        hint = Game._blocker_hint(self.me, 24, 23, mine)
        assert hint and "CARAVAN" in hint and "trade route" in hint

    def test_caravan_on_route_is_not(self):
        from harness.game import Game
        mine = [{"id": 2, "type": "CARAVAN", "x": 24, "y": 23, "strength": 0, "domain": "LAND", "automated": True}]
        assert Game._blocker_hint(self.me, 24, 23, mine) is None
