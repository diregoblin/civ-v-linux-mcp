"""Conditional unit orders (#32).

Lua half: H.order_facts on the assignments test world (my unit's moves, activity and build in progress, every
visible hostile within the radius, a destination's refusal or enemy, what a build makes and whether its plot has
it) and H.resume_moves leaving the units an order owns to the order.
Python half: harness/orders.py (normalizing, the read's spec, decide), the notebook storage (one open order per
unit, replace, prune) and Game.give_order / run_orders / resume_order / cancel_order over a small simulated world
that answers H.order_facts and carries out move_unit / unit_mission: move-then-build and heal-then-move across
turns, cancellation, a blocked destination, a hostile coming into sight, damage, a step refused, no progress,
arrival without moves, a lost unit, a direct command taking the unit back, a restart after a step completed, a
harness that died mid-step, a loaded save, hotseat isolation, the turn-start window and its wake reasons, and
the MCP tools.
"""
import asyncio
import contextlib
import json
import os
import re
import tempfile
import unittest
from unittest import mock

import test_assignments as ta
import test_mcp_safety as support
from harness import orders as O
from harness.game import Game
from harness.notes import Notebook

WORLD = ta.WORLD + r"""
ActivityTypes = { ACTIVITY_AWAKE = 0, ACTIVITY_HEAL = 3, ACTIVITY_MISSION = 6 }
GameInfoTypes.IMPROVEMENT_FARM = 0; GameInfoTypes.ROUTE_ROAD = 0
GameInfo.Builds = { [0] = { ID = 0, Type = 'BUILD_FARM', ImprovementType = 'IMPROVEMENT_FARM' },
                    [1] = { ID = 1, Type = 'BUILD_ROAD', RouteType = 'ROUTE_ROAD' } }
GameInfo.Builds.BUILD_FARM = GameInfo.Builds[0]; GameInfo.Builds.BUILD_ROAD = GameInfo.Builds[1]
GameInfo.Builds[2] = { ID = 2, Type = 'BUILD_REMOVE_FOREST' }; GameInfo.Builds.BUILD_REMOVE_FOREST = GameInfo.Builds[2]
GameInfo.Builds[3] = { ID = 3, Type = 'BUILD_REMOVE_ROUTE' }; GameInfo.Builds.BUILD_REMOVE_ROUTE = GameInfo.Builds[3]
GameInfo.Features = { [0] = { ID = 0, Type = 'FEATURE_FOREST' }, [1] = { ID = 1, Type = 'FEATURE_MARSH' } }
GameInfo.BuildFeatures = setmetatable({}, { __call = function()
  local rows = { { BuildType = 'BUILD_REMOVE_FOREST', FeatureType = 'FEATURE_FOREST', Remove = true },
                 { BuildType = 'BUILD_FARM', FeatureType = 'FEATURE_MARSH', Remove = true } }
  local i = 0
  return function() i = i + 1; return rows[i] end
end })
Game.GetActivePlayer = function() return 0 end
local base_unit2 = unit
function unit(id, owner, typ, x, y, o)
  o = o or {}
  local u = base_unit2(id, owner, typ, x, y, o)
  u.GetActivityType = function() return o.activity or 0 end
  u.GetBuildType = function() return o.build or -1 end
  u.MaxMoves = function() return (o.max_moves or 2) * 60 end
  u.CanBuild = function(_, plot, b, extra)   -- the engine's binding takes (plot, build) only (live t43)
    if extra ~= nil then error("bad argument #3 to 'CanBuild' (number expected, got boolean)") end
    return o.can_build ~= false
  end
  return u
end
"""


class OrderFactsLuaTests(unittest.TestCase):
    run_lua = support.LuaRuntimeTests.run_lua

    def setUp(self):
        support.LuaRuntimeTests.setUp(self)
        self.run_lua(WORLD)

    def test_unit_detail_and_every_hostile_in_the_radius(self):
        self.run_lua("""
        unit(1, 0, 4, 2, 2, { created = 5, hp = 70, moves = 1, activity = 3, build = 0 })
        unit(40, 63, 2, 3, 2)                          -- a Brute next door
        unit(41, 63, 2, 4, 2)                          -- another, two plots away
        unit(42, 63, 2, 7, 2)                          -- out of the radius
        local f = H.order_facts(0, { units = { { id = 1, type = 'WORKER', created = 5, x = 2, y = 2 } }, radius = 2 })
        local u = f.units['1']
        assert(u.type == 'WORKER' and u.hp == 70 and u.moves == 1 and u.max_moves == 2, 'moves')
        assert(u.activity == 'HEAL' and u.build == 'BUILD_FARM', 'activity and build')
        assert(#u.hostiles == 2 and u.hostiles[1].id == 40 and u.hostiles[1].distance == 1 and u.hostiles[2].id == 41,
               'both hostiles, nearest first')
        assert(u.hostiles[1].owner_id == 63 and u.hostile == nil)
        """)

    def test_a_destination_answers_move_units_refusal_and_an_enemy(self):
        self.run_lua("""
        unit(1, 0, 1, 2, 2)
        unit(40, 63, 2, 4, 2)                          -- a Brute on the destination
        P['5,2'].o.mountain = true
        P['6,2'].o.revealed = false
        local f = H.order_facts(0, { units = { { id = 1 } }, dests = { { unit_id = 1, x = 4, y = 2 },
          { unit_id = 1, x = 5, y = 2 }, { unit_id = 1, x = 6, y = 2 }, { unit_id = 1, x = 3, y = 3 } } })
        assert(f.dests['1:4,2'].enemy == true and f.dests['1:4,2'].refusal == nil, 'enemy, never an attack')
        assert(f.dests['1:5,2'].refusal == 'destination plot is a mountain', tostring(f.dests['1:5,2'].refusal))
        assert(f.dests['1:6,2'].refusal ~= nil, 'unrevealed')
        assert(next(f.dests['1:3,3']) == nil, 'a plain plot: nothing to say')
        """)

    def test_a_build_says_what_it_makes_whether_it_is_there_and_whether_the_unit_can(self):
        self.run_lua("""
        unit(1, 0, 4, 2, 2)
        unit(2, 0, 4, 3, 3, { can_build = false })
        P['2,2'].GetImprovementType = function() return 0 end
        local f = H.order_facts(0, { units = { { id = 1 }, { id = 2 } }, builds = {
          { unit_id = 1, build = 'BUILD_FARM', x = 2, y = 2 }, { unit_id = 2, build = 'BUILD_FARM', x = 3, y = 3 },
          { unit_id = 1, build = 'BUILD_ROAD', x = 4, y = 4 }, { unit_id = 1, build = 'BUILD_CASTLE', x = 2, y = 2 } } })
        local a, b = f.builds['1:BUILD_FARM'], f.builds['2:BUILD_FARM']
        assert(a.known and a.improvement == 'IMPROVEMENT_FARM' and a.done == true and a.can_build == true)
        assert(b.done == false and b.can_build == false)
        local r = f.builds['1:BUILD_ROAD']
        assert(r.route == 'ROUTE_ROAD' and r.done == false and r.can_build == nil, 'not on the plot: not asked')
        assert(f.builds['1:BUILD_CASTLE'].known == false)
        """)

    def test_a_chop_is_done_when_the_forest_is_gone(self):
        """Live 2026-09-27 (Grok, t64): a REMOVE_FOREST step paused as "cannot start" the turn after the chop had
        paid out. A build that makes nothing is done when the feature it removes is gone from the plot."""
        self.run_lua("""
        unit(1, 0, 4, 2, 2)
        unit(2, 0, 4, 3, 3, { can_build = false })
        P['2,2'].GetFeatureType = function() return 0 end        -- forest still standing
        P['3,3'].GetFeatureType = function() return -1 end       -- chopped
        P['4,4'].GetRouteType = function() return -1 end
        local f = H.order_facts(0, { units = { { id = 1 }, { id = 2 } }, builds = {
          { unit_id = 1, build = 'BUILD_REMOVE_FOREST', x = 2, y = 2 }, { unit_id = 2, build = 'BUILD_REMOVE_FOREST', x = 3, y = 3 },
          { unit_id = 1, build = 'BUILD_REMOVE_ROUTE', x = 4, y = 4 } } })
        local a, b = f.builds['1:BUILD_REMOVE_FOREST'], f.builds['2:BUILD_REMOVE_FOREST']
        assert(a.known and a.done == false and a.removes[1] == 'FEATURE_FOREST' and a.can_build == true, H.json(a))
        assert(b.done == true and b.can_build == false, 'the chop is finished even though it cannot start again: ' .. H.json(b))
        assert(f.builds['1:BUILD_REMOVE_ROUTE'].done == true)
        """)

    def test_a_repair_is_done_when_nothing_on_the_plot_is_pillaged(self):
        """Live England t219-t221 (runtime v271): a Worker's "build REPAIR at (59,39)" fixed the pillaged farm in
        one turn and the step then paused as "cannot start REPAIR" because, like a chop before v2xx, nothing
        said it was finished. BUILD_REPAIR makes nothing: it is done when the plot's improvement and route are
        no longer pillaged."""
        self.run_lua("""
        GameInfo.Builds[4] = { ID = 4, Type = 'BUILD_REPAIR', Repair = 1 }; GameInfo.Builds.BUILD_REPAIR = GameInfo.Builds[4]
        unit(1, 0, 4, 2, 2)
        unit(2, 0, 4, 3, 3, { can_build = false })
        P['2,2'].IsImprovementPillaged = function() return true end        -- still broken
        P['3,3'].IsImprovementPillaged = function() return false end       -- repaired
        P['3,3'].IsRoutePillaged = function() return false end
        local f = H.order_facts(0, { units = { { id = 1 }, { id = 2 } }, builds = {
          { unit_id = 1, build = 'BUILD_REPAIR', x = 2, y = 2 }, { unit_id = 2, build = 'BUILD_REPAIR', x = 3, y = 3 } } })
        local a, b = f.builds['1:BUILD_REPAIR'], f.builds['2:BUILD_REPAIR']
        assert(a.known and a.repair == true and a.pillaged == true and a.done == false and a.can_build == true, H.json(a))
        assert(b.done == true and b.pillaged == false and b.can_build == false,
               'the repair is finished even though it cannot start again: ' .. H.json(b))
        P['2,2'].IsImprovementPillaged = function() return false end
        P['2,2'].IsRoutePillaged = function() return true end             -- the road is still broken
        f = H.order_facts(0, { units = { { id = 1 } }, builds = { { unit_id = 1, build = 'BUILD_REPAIR', x = 2, y = 2 } } })
        assert(f.builds['1:BUILD_REPAIR'].done == false, 'a pillaged route keeps the repair open: ' .. H.json(f.builds))
        """)

    def test_resume_moves_leaves_an_order_owned_unit_alone(self):
        self.run_lua("""
        unit(1, 0, 1, 2, 2); unit(2, 0, 1, 3, 3)
        H.pending_moves[H.pm_key(1, 0)] = { x = 5, y = 2, pid = 0, unit_id = 1 }
        H.pending_moves[H.pm_key(2, 0)] = { x = 5, y = 3, pid = 0, unit_id = 2 }
        local pushed = {}
        H.move_unit = function(id) pushed[#pushed + 1] = id; return { ok = true } end
        H.melee_defender = function() return nil end; H.enemy_city_at = function() return nil end
        H.peaceful_occupant = function() return nil end
        H.resume_moves(0, { 1 })
        assert(#pushed == 1 and pushed[1] == 2, 'only the unit no order owns')
        assert(H.pending_moves[H.pm_key(1, 0)] ~= nil, 'the order-owned record is kept for the order to judge')
        """)


# ------------------------------------------------------------------ pure logic
def order(steps, **kw):
    o = {"id": 1, "unit": {"id": 7, "type": "WORKER", "created": 3}, "steps": O.normalize_steps(steps), "step": 0,
         "interrupt": O.normalize_interrupt(kw.pop("interrupt", None)), "status": "active", "updated_turn": 10}
    o.update(kw)
    return o


def facts(turn=10, **u):
    row = {"id": 7, "type": "WORKER", "created": 3, "x": 2, "y": 2, "hp": 100, "max_hp": 100, "moves": 2,
           "max_moves": 2}
    dests = u.pop("dests", {})
    builds = u.pop("builds", {})
    row.update(u)
    return {"turn": turn, "units": {"7": row}, "dests": dests, "builds": builds}


class NormalizeTests(unittest.TestCase):
    def test_steps(self):
        s = O.normalize_steps([{"kind": "move", "x": 5, "y": 2}, {"kind": "build", "build": "farm"},
                               "heal", {"kind": "hold", "mission": "MISSION_SLEEP"}])
        self.assertEqual(s[1], {"kind": "build", "build": "BUILD_FARM", "x": 5, "y": 2}, "builds where the move ends")
        self.assertEqual(s[2], {"kind": "heal", "hp": 100})
        self.assertEqual(s[3], {"kind": "hold", "mission": "sleep"})
        for bad, msg in (([], "non-empty"), ([{"kind": "attack"}], "never attacks"), ([{"kind": "move", "x": 1}], "x and y"),
                         (["hold", "heal"], "nothing can follow"), ([{"kind": "hold", "mission": "pillage"}], "mission"),
                         ([{"kind": "move", "x": 1, "y": 1}] * 7, "at most")):
            with self.assertRaises(O.OrderError) as e:
                O.normalize_steps(bad)
            self.assertIn(msg, str(e.exception))
        self.assertNotIn("x", O.normalize_steps([{"kind": "build", "build": "ROAD"}])[0], "filled in by the caller")

    def test_interrupt(self):
        self.assertEqual(O.normalize_interrupt(None), {"hostile_within": 2, "damaged": True})
        self.assertEqual(O.normalize_interrupt({"hostile_within": 0, "hp_below": 150, "damaged": False}),
                         {"hostile_within": 0, "hp_below": 100, "damaged": False})
        with self.assertRaises(O.OrderError):
            O.normalize_interrupt({"war": True})
        with self.assertRaises(O.OrderError):
            O.normalize_interrupt({"damaged": "yes"})

    def test_spec_reads_only_the_current_step(self):
        o = order([{"kind": "move", "x": 5, "y": 2}, {"kind": "build", "build": "FARM"}])
        self.assertEqual(O.spec([o]), {"units": [{"id": 7, "type": "WORKER", "created": 3}],
                                       "dests": [{"unit_id": 7, "x": 5, "y": 2}], "radius": 2})
        o["step"] = 1
        self.assertEqual(O.spec([o])["builds"], [{"unit_id": 7, "build": "BUILD_FARM", "x": 5, "y": 2}])


class DecideTests(unittest.TestCase):
    MOVE_BUILD = [{"kind": "move", "x": 5, "y": 2}, {"kind": "build", "build": "FARM"}]

    def test_move_issue_wait_and_arrive(self):
        o = order(self.MOVE_BUILD)
        d = O.decide(o, facts(), 10)
        self.assertEqual((d["do"], d["tool"], d["args"]), ("issue", "move_unit", {"unit_id": 7, "x": 5, "y": 2}))
        o["issued"] = {"turn": 10, "step": 0, "x": 2, "y": 2}
        d = O.decide(o, facts(x=3, moves=0, going_to={"x": 5, "y": 2}), 10)
        self.assertEqual((d["do"], d["state"]), ("wait", "moving"), "never twice in one turn")
        self.assertEqual(O.decide(o, facts(x=5), 11)["do"], "next")

    def test_no_moves_is_an_explicit_wait_not_a_retry(self):
        d = O.decide(order(self.MOVE_BUILD), facts(moves=0), 10)
        self.assertEqual((d["do"], d["state"]), ("wait", "no_moves"))

    def test_no_progress_for_a_turn_pauses(self):
        o = order(self.MOVE_BUILD, issued={"turn": 9, "step": 0, "x": 2, "y": 2})
        d = O.decide(o, facts(), 10)
        self.assertEqual((d["do"], d["kind"]), ("pause", "no_progress"))

    def test_the_destination_is_checked_before_every_move(self):
        o = order(self.MOVE_BUILD)
        d = O.decide(o, facts(dests={"7:5,2": {"enemy": True}}), 10)
        self.assertEqual((d["do"], d["kind"]), ("pause", "enemy_on_destination"))
        self.assertIn("never attacks", d["reason"])
        d = O.decide(o, facts(dests={"7:5,2": {"refusal": "destination plot is a mountain"}}), 10)
        self.assertEqual((d["do"], d["kind"]), ("pause", "destination"))

    def test_hostiles_pause_unless_acknowledged_and_only_within_the_radius(self):
        h = {"id": 40, "owner_id": 63, "owner": "Barbarians", "unit": "BRUTE", "x": 3, "y": 2, "distance": 1}
        o = order(self.MOVE_BUILD)
        d = O.decide(o, facts(hostiles=[h]), 10)
        self.assertEqual((d["do"], d["kind"]), ("pause", "hostile"))
        self.assertEqual(d["hostiles"], [h])
        o["acked"] = ["63:40"]
        self.assertEqual(O.decide(o, facts(hostiles=[h]), 10)["do"], "issue")
        o = order(self.MOVE_BUILD, interrupt={"hostile_within": 0})
        self.assertEqual(O.decide(o, facts(hostiles=[h]), 10)["do"], "issue", "turned off")

    def test_damage_and_low_hp(self):
        o = order(self.MOVE_BUILD, seen={"hp": 100})
        self.assertEqual(O.decide(o, facts(hp=80), 10)["kind"], "damaged")
        o = order(self.MOVE_BUILD, interrupt={"damaged": False, "hp_below": 50}, seen={"hp": 40})
        self.assertEqual(O.decide(o, facts(hp=40), 10)["kind"], "low_hp")
        o = order([{"kind": "heal", "hp": 90}], interrupt={"hp_below": 50}, seen={"hp": 40})
        self.assertEqual(O.decide(o, facts(hp=40), 10)["do"], "issue", "low hp is what a heal step is for")

    def test_build_steps(self):
        o = order(self.MOVE_BUILD, step=1)
        d = O.decide(o, facts(), 10)
        # off the build plot (walked away by a direct order, live Assyria t53): the order walks it back, as its
        # move step would, instead of pausing "not on (5,2)"
        self.assertEqual((d["do"], d["tool"], d["args"]), ("issue", "move_unit", {"unit_id": 7, "x": 5, "y": 2}))
        self.assertEqual(d["what"], "walk to (5,2) for FARM")
        o2 = order(self.MOVE_BUILD, step=1, issued={"turn": 10, "step": 1, "x": 2, "y": 2})
        self.assertEqual(O.decide(o2, facts(moves=0), 10)["state"], "moving", "issued this turn: on its way")
        self.assertEqual(O.decide(o2, facts(), 11)["kind"], "no_progress", "still where it was issued from a turn later")
        o3 = order([{"kind": "build", "build": "FARM"}], step=0)
        self.assertEqual(O.decide(o3, facts(), 10)["kind"], "prerequisite", "a build with no plot of its own")
        f = facts(x=5, builds={"7:BUILD_FARM": {"known": True, "done": False, "can_build": True}})
        d = O.decide(o, f, 10)
        self.assertEqual((d["tool"], d["args"]["build"]), ("unit_mission", "BUILD_FARM"))
        f["units"]["7"]["build"] = "BUILD_REMOVE_FOREST"
        d = O.decide(o, f, 10)
        self.assertEqual(d["state"], "building")
        self.assertIn("first", d["note"])
        f["units"]["7"]["build"] = None
        f["builds"]["7:BUILD_FARM"]["done"] = True
        self.assertEqual(O.decide(o, f, 10)["do"], "next")
        f["builds"]["7:BUILD_FARM"] = {"known": True, "done": False, "can_build": False}
        self.assertEqual(O.decide(o, f, 10)["kind"], "prerequisite")

    def test_prophet_that_spread_cannot_build_a_holy_site(self):
        # live Assyria t189-t190: the Prophet spread Judaism into Belgrade (4 -> 3 charges), then its Holy Site
        # order paused with the generic plot sentence; the engine's rule is that a spent charge ends the build.
        o = order([{"kind": "build", "build": "BUILD_HOLY_SITE", "x": 15, "y": 21}])
        f = facts(x=15, y=21, builds={"7:BUILD_HOLY_SITE": {"known": True, "done": False, "can_build": False,
                                                           "why": "spent_spread", "spreads_left": 3, "spreads_max": 4}})
        d = O.decide(o, f, 10)
        self.assertEqual(d["kind"], "prerequisite")
        self.assertIn("spread its religion can no longer build a HOLY_SITE (1 of 4 spread charges used)", d["reason"])
        self.assertIn("MISSION_SPREAD_RELIGION", d["reason"])
        self.assertNotIn("a tech, the terrain", d["reason"])

    def test_heal_and_hold(self):
        o = order([{"kind": "heal", "hp": 80}, "hold"])
        d = O.decide(o, facts(hp=50), 10)
        self.assertEqual(d["args"]["mission"], "MISSION_HEAL")
        self.assertEqual(O.decide(o, facts(hp=60, activity="HEAL"), 10)["state"], "healing")
        self.assertEqual(O.decide(o, facts(hp=80), 10)["do"], "next")
        o["step"] = 1
        self.assertEqual(O.decide(o, facts(), 10)["args"]["mission"], "MISSION_FORTIFY")

    def test_a_hold_after_a_rest_wakes_the_unit_first_and_a_held_unit_is_done(self):
        """GitLab #176 note (Celts t24): "heal to 90, then fortify" healed to 90 and its fortify was refused as not
        legal -- the Warrior was still in ACTIVITY_HEAL, and the engine takes no new hold from a waiting unit."""
        o = order([{"kind": "heal", "hp": 80}, "hold"], step=1)
        d = O.decide(o, facts(hp=90, activity="HEAL"), 10)
        self.assertEqual(d["args"], {"unit_id": 7, "mission": "MISSION_FORTIFY", "wake_first": True})
        self.assertNotIn("wake_first", O.decide(o, facts(activity="AWAKE"), 10)["args"])
        d = O.decide(o, facts(activity="SLEEP"), 10)     # already fortified (or fortifying): nothing to send
        self.assertEqual(d["do"], "next")
        self.assertIn("already holding", d["note"])

    def test_a_lost_or_reused_unit_fails_and_an_upgrade_is_named(self):
        o = order(self.MOVE_BUILD)
        f = {"turn": 10, "units": {"7": {"id": 7, "missing": True,
                                         "on_last_plot": [{"id": 9, "type": "SWORDSMAN", "upgrade_of": "WORKER"}]}}}
        d = O.decide(o, f, 10)
        self.assertEqual((d["do"], d["kind"]), ("fail", "unit_gone"))
        self.assertIn("SWORDSMAN (9)", d["reason"])
        self.assertEqual(O.decide(o, facts(type="SETTLER"), 10)["do"], "fail")

    def test_an_unanswered_step_and_a_loaded_save_pause(self):
        o = order(self.MOVE_BUILD, inflight={"turn": 10, "step": 0, "what": "move to (5,2)"})
        self.assertEqual(O.decide(o, facts(), 10)["kind"], "uncertain")
        self.assertEqual(O.decide(o, facts(x=5), 10)["do"], "next", "the board shows it happened")
        o = order(self.MOVE_BUILD, updated_turn=12)
        self.assertEqual(O.decide(o, facts(), 10)["kind"], "turn_went_back")


class OwnUnitOnDestinationTests(unittest.TestCase):
    """Live Assyria t55: the Settler walking north stood for one turn on the plot the Worker's order was walking to,
    and the order paused with "replace the order with a reachable plot". My own unit passing through is waited
    out; one that stays pauses the order after OWN_UNIT_BLOCK_TURNS turns. A stranger's refusal pauses at once."""
    MOVE = [{"kind": "move", "x": 5, "y": 2}]
    MINE = "destination already holds one of your civilian units (one per tile); pick an adjacent plot or move that unit first"

    def test_my_own_unit_on_the_plot_is_waited_out(self):
        o = order(self.MOVE)
        d = O.decide(o, facts(dests={"7:5,2": {"refusal": self.MINE}}), 10)
        self.assertEqual((d["do"], d["state"]), ("wait", "blocked"))
        self.assertEqual(d["blocked"], {"x": 5, "y": 2, "turn": 10})
        self.assertIn("tries again next turn", d["note"])
        o["blocked"] = d["blocked"]
        d = O.decide(o, facts(dests={"7:5,2": {"refusal": self.MINE}}), 11)
        self.assertEqual((d["do"], d["blocked"]["turn"]), ("wait", 10), "the first turn is kept")
        d = O.decide(o, facts(dests={"7:5,2": {"refusal": self.MINE}}), 12)
        self.assertEqual((d["do"], d["kind"]), ("pause", "destination"))
        self.assertIn("since turn 10", d["reason"])
        self.assertIn("move that unit off the plot", d["hint"])
        # another destination's block starts its own count
        o["blocked"] = {"x": 9, "y": 9, "turn": 3}
        self.assertEqual(O.decide(o, facts(dests={"7:5,2": {"refusal": self.MINE}}), 12)["do"], "wait")
        # the plot free again: the move is issued and the count forgotten by the runner
        self.assertEqual(O.decide(o, facts(), 12)["do"], "issue")

    def test_a_strangers_refusal_pauses_at_once(self):
        d = O.decide(order(self.MOVE), facts(dests={"7:5,2": {"refusal": "destination is inside Persia's borders"}}), 10)
        self.assertEqual((d["do"], d["kind"]), ("pause", "destination"))
        self.assertNotIn("blocked", d)

class NotebookOrderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = mock.patch.dict(os.environ, {"CIV5_NOTES_DIR": self.tmp.name})
        p.start()
        self.addCleanup(p.stop)

    def test_one_open_order_per_unit_and_replace(self):
        nb = Notebook("g", 0)
        rec = {"unit": {"id": 7}, "steps": [{"kind": "heal", "hp": 100}]}
        a = nb.add_order(rec, 5)["order"]["id"]
        r = nb.add_order(rec, 5)
        self.assertFalse(r["ok"])
        self.assertIn("replace_id=1", r["err"])
        r = nb.add_order(rec, 6, replace_id=a)
        self.assertTrue(r["ok"], r)
        self.assertEqual([o["status"] for o in nb.orders("all")], ["replaced", "active"])
        self.assertFalse(nb.add_order(rec, 6, replace_id=a)["ok"], "a replaced order is closed")
        self.assertEqual(Notebook("g", 1).orders("all"), [], "per seat")

    def test_closed_ones_are_pruned(self):
        nb = Notebook("g", 0)
        for i in range(O.MAX_CLOSED + 5):
            o = nb.add_order({"unit": {"id": i}, "steps": []}, 1)["order"]
            o["status"] = "completed"
            nb.put_order(o)
        self.assertEqual(len(nb.orders("closed")), O.MAX_CLOSED)


# ------------------------------------------------------------------ Game over a simulated world
class SimGame(Game):
    """Answers H.order_facts from `world` and carries out move_unit / unit_mission on it. A move walks up to
    `moves` plots in a straight line (x first, then y); a build takes `build_turns` turns; heal adds 20 hp a
    turn while HEAL. `end_turn()` advances the world one turn the way the engine would."""

    def __init__(self, seat=0, key="sim"):
        self.seat = seat
        self._game_key = key
        self.turn = 10
        self.claim = None
        self.units = {7: {"type": "WORKER", "created": 3, "x": 2, "y": 2, "hp": 100, "max_hp": 100, "moves": 2,
                          "max_moves": 2}}
        self.hostiles = []          # {id, owner_id, owner, unit, x, y}
        self.blocked = {}           # (x, y) -> refusal
        self.enemy_on = set()
        self.improved = {}          # (x, y) -> BUILD_*
        self.cant_build = set()
        self.pending = {}           # unit id -> (x, y): the standing move
        self.calls = []             # (tool, args) the orders issued
        self.refuse = None          # make the next action refuse with this err
        self.build_turns = 2
        self.lua = []

    # -- the read
    def q(self, code, *a, **k):
        if code.startswith(f"return H.order_facts({self.seat}, "):
            return self._facts(code)
        if code.startswith("return H.drop_pending_move_at("):
            self.lua.append(code)
            uid, x, y, _seat = (int(v) for v in re.findall(r"-?\d+", code))
            if uid in self.pending and self.pending[uid] == (x, y):
                del self.pending[uid]
                return True
            return False
        if code.startswith("return H.resume_moves"):
            self.lua.append(code)
            return []
        if code.startswith("return H.turn_started_this_turn("):
            return getattr(self, "unseen", False)
        if code.startswith("return H.unit_is_automated("):
            uid = int(re.search(r"\((\d+),", code).group(1))
            return bool(self.units.get(uid, {}).get("automated"))
        raise AssertionError(code)

    def _facts(self, code):
        ids = [int(i) for i in re.findall(r'\["id"\]=(\d+)', code.split('["units"]=')[1].split("}}")[0] + "}")]
        radius = int((re.search(r'\["radius"\]=(\d+)', code) or [0, 0])[1])
        units = {}
        for i in ids:
            u = self.units.get(i)
            if u is None:
                units[str(i)] = {"id": i, "missing": True}
                continue
            row = {"id": i, **{k: v for k, v in u.items() if k not in ("heal_turns",)}}
            if i in self.pending:
                row["going_to"] = {"x": self.pending[i][0], "y": self.pending[i][1]}
            near = []
            for h in self.hostiles:
                d = max(abs(h["x"] - u["x"]), abs(h["y"] - u["y"]))
                if d <= radius:
                    near.append({**h, "distance": d})
            if near:
                row["hostiles"] = sorted(near, key=lambda h: h["distance"])
            units[str(i)] = row
        dests = {}
        for uid, x, y in re.findall(r'\["unit_id"\]=(\d+), \["x"\]=(-?\d+), \["y"\]=(-?\d+)\}', code):
            key, xy = f"{uid}:{x},{y}", (int(x), int(y))
            dests[key] = {**({"refusal": self.blocked[xy]} if xy in self.blocked else {}),
                          **({"enemy": True} if xy in self.enemy_on else {})}
        builds = {}
        for uid, b, x, y in re.findall(r'\["unit_id"\]=(\d+), \["build"\]="(\w+)", \["x"\]=(-?\d+), \["y"\]=(-?\d+)', code):
            u = self.units.get(int(uid))
            xy = (int(x), int(y)) if int(x) >= 0 or not u else (u["x"], u["y"])
            row = {"known": b in ("BUILD_FARM", "BUILD_ROAD")}
            if row["known"]:
                row["done"] = self.improved.get(xy) == b
                if u and (u["x"], u["y"]) == xy:
                    row["can_build"] = xy not in self.cant_build
            builds[f"{uid}:{b}"] = row
        return {"turn": self.turn, "units": units, "dests": dests, "builds": builds}

    def turn_state(self, pid=None):
        return {"turn": self.turn, "active_player": self.seat, "my_turn": True, "todo": {"units": []}}

    # -- the actions, as the game would carry them out
    def _step(self, u, x, y):
        while u["moves"] > 0 and (u["x"], u["y"]) != (x, y):
            if u["x"] != x:
                u["x"] += 1 if x > u["x"] else -1
            else:
                u["y"] += 1 if y > u["y"] else -1
            u["moves"] -= 1

    def move_unit(self, unit_id, x, y, pid=None, settle_timeout=1.0):
        self.calls.append(("move_unit", unit_id, x, y))
        if self.refuse:
            err, self.refuse = self.refuse, None
            return {"ok": False, "err": err}
        u = self.units[unit_id]
        u["activity"] = "MISSION"
        u.pop("build", None)
        u.pop("automated", None)
        self._step(u, x, y)
        if (u["x"], u["y"]) == (x, y):
            self.pending.pop(unit_id, None)
            u["activity"] = "AWAKE"
            return {"ok": True, "x": x, "y": y, "arrived": True, "moves": u["moves"]}
        self.pending[unit_id] = (x, y)
        return {"ok": True, "x": u["x"], "y": u["y"], "queued": True, "going_to": {"x": x, "y": y}}

    def unit_mission(self, unit_id, mission, x=-1, y=-1, data2=0, build=None, pid=None):
        self.calls.append(("unit_mission", unit_id, mission, build))
        if self.refuse:
            err, self.refuse = self.refuse, None
            return {"ok": False, "err": err}
        u = self.units[unit_id]
        self.pending.pop(unit_id, None)
        u.pop("automated", None)   # CvUnitMission::PushMission clears the automate type; so does the stop command
        if mission == "COMMAND_STOP_AUTOMATION":
            return {"ok": True, "command": mission}
        if mission == "MISSION_BUILD":
            u["build"], u["build_left"] = build, self.build_turns
            return {"ok": True, "build": build, "turns_left": self.build_turns}
        if mission == "COMMAND_WAKE":
            u["activity"] = "AWAKE"
            return {"ok": True, "command_pending": mission}
        if mission in O.HOLD_MISSIONS.values() and u.get("activity") in O.WAITING:
            # CvUnit::isWaiting: a resting unit takes no new hold until it is woken
            return {"ok": False, "err": "action is not currently legal", "legal_missions": ["COMMAND_WAKE"]}
        if mission == "MISSION_HEAL":
            u["activity"] = "HEAL"
        else:
            u["activity"] = "SLEEP"
        return {"ok": True}

    def expiring_city_states(self, pid=None):
        return []   # no city-states in this world: the turn's arrival reads this

    def turn_digest(self):
        self.calls.append(("turn_digest",))
        return {"events": [{"kind": "turn_start", "turn": self.turn, "data": {}}], "notifications": []}

    def end_turn(self):
        """The AIs move, then my next turn begins."""
        self.turn += 1
        for u in self.units.values():
            if u.get("build"):
                u["build_left"] -= 1
                if u["build_left"] <= 0:
                    self.improved[(u["x"], u["y"])] = u.pop("build")
            if u.get("activity") == "HEAL":
                u["hp"] = min(u["max_hp"], u["hp"] + 20)
                if u["hp"] == u["max_hp"]:
                    u["activity"] = "AWAKE"
            u["moves"] = u["max_moves"]


class GameOrderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = mock.patch.dict(os.environ, {"CIV5_NOTES_DIR": self.tmp.name})
        p.start()
        self.addCleanup(p.stop)

    def arrive(self, g):
        """The turn-start window as _arrive runs it (without the rest of the hand-off)."""
        g.end_turn()
        return g._turn_start_orders(g.turn_state())

    def test_arrive_if_due_runs_the_orders_once_per_turn(self):
        # live t225 (Mongolia): the turn opened under China's deal screen, wait_for_my_turn returned at that gate
        # before the arrival hook, and the Great Musician's order never ran that turn. The tool that answers the
        # leader now runs the arrival once the table is free -- once per turn, never under a screen.
        g = SimGame()
        g.expiring_city_states = list
        g.give_order(7, [{"kind": "move", "x": 9, "y": 2}], purpose="walk east")
        g.end_turn()
        out = g.arrive_if_due()
        self.assertEqual(out["orders"]["rows"][0]["did"], ["move to (9,2): issued"])
        self.assertEqual((g.units[7]["x"], g.units[7]["y"]), (6, 2))
        self.assertIsNone(g.arrive_if_due(), "already arrived this turn")
        g.end_turn()
        real = g.turn_state
        g.turn_state = lambda pid=None: {**real(), "discussion_pending": True}
        self.assertIsNone(g.arrive_if_due(), "a leader screen is still up: nothing runs under it")
        self.assertEqual((g.units[7]["x"], g.units[7]["y"]), (6, 2))
        g.turn_state = real
        self.assertEqual(g.arrive_if_due()["orders"]["rows"][0]["did"], ["move to (9,2): issued"])
        self.assertEqual((g.units[7]["x"], g.units[7]["y"]), (8, 2))

    def test_move_then_build_across_turns(self):
        g = SimGame()
        r = g.give_order(7, [{"kind": "move", "x": 5, "y": 2}, {"kind": "build", "build": "FARM"}],
                         purpose="farm the river plot")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["did"], ["move to (5,2): issued"])
        self.assertEqual((r["order"]["state"], r["order"]["now"]), ("moving", "move to (5,2)"))
        self.assertEqual(g.pending, {7: (5, 2)}, "the order's standing move")
        out = self.arrive(g)
        row = out["rows"][0]
        self.assertEqual(row["did"], ["move to (5,2): issued", "move to (5,2): done", "build FARM at (5,2): issued"],
                         "arrived with a move left: the build starts the same turn")
        self.assertEqual(row["state"], "building")
        self.arrive(g)
        out = self.arrive(g)
        self.assertEqual(out["rows"][0]["status"], "completed")
        self.assertEqual(g.improved, {(5, 2): "BUILD_FARM"})
        self.assertEqual(len(g.calls), 3, "three calls made for me over four turns")
        self.assertEqual(g.orders("closed")["orders"][0]["issued_count"], 3)
        self.assertIsNone(self.arrive(g), "nothing open: no read at all")

    def test_heal_then_move(self):
        g = SimGame()
        g.units[7]["hp"] = 40
        r = g.give_order(7, [{"kind": "heal", "hp": 80}, {"kind": "move", "x": 3, "y": 2}, "hold"])
        self.assertEqual(r["order"]["state"], "healing")
        self.arrive(g)                                   # 60
        out = self.arrive(g)                             # 80: moves on and holds, same turn
        self.assertEqual(out["rows"][0]["status"], "completed", out)
        self.assertEqual([c[0:3] for c in g.calls][-2:], [("move_unit", 7, 3), ("unit_mission", 7, "MISSION_FORTIFY")])

    def test_heal_then_hold_wakes_the_healed_unit_before_the_fortify(self):
        g = SimGame()
        g.units[7]["hp"] = 60
        r = g.give_order(7, [{"kind": "heal", "hp": 80}, "hold"])
        self.assertEqual(r["order"]["state"], "healing")
        out = self.arrive(g)                             # 80 of 100: still resting in HEAL, the hold step runs
        self.assertEqual(out["rows"][0]["status"], "completed", out)
        self.assertEqual([c[2] for c in g.calls if c[0] == "unit_mission"][-2:], ["COMMAND_WAKE", "MISSION_FORTIFY"])
        self.assertEqual(g.units[7]["activity"], "SLEEP")

    def test_a_hold_uses_whichever_of_fortify_and_sleep_the_unit_is_offered(self):
        g = SimGame()
        real = g.unit_mission

        def only_fortify(unit_id, mission, *a, **k):
            if mission == "MISSION_SLEEP":
                g.calls.append(("unit_mission", unit_id, mission, None))
                return {"ok": False, "err": "action is not currently legal",
                        "legal_missions": ["MISSION_FORTIFY", "MISSION_HEAL"]}
            return real(unit_id, mission, *a, **k)
        g.unit_mission = only_fortify
        r = g.give_order(7, [{"kind": "hold", "mission": "sleep"}])
        self.assertEqual(r["order"]["status"], "completed", r)
        self.assertEqual([c[2] for c in g.calls], ["MISSION_SLEEP", "MISSION_FORTIFY"])
        self.assertIn("holds it instead", r["order"]["last"]["note"])

    def test_a_first_step_that_cannot_run_is_refused_and_nothing_stored(self):
        g = SimGame()
        g.blocked[(6, 2)] = "destination plot is a mountain"
        r = g.give_order(7, [{"kind": "move", "x": 6, "y": 2}])
        self.assertFalse(r["ok"])
        self.assertIn("mountain", r["err"])
        g.cant_build.add((2, 2))
        self.assertFalse(g.give_order(7, [{"kind": "build", "build": "FARM"}])["ok"])
        self.assertIn("not a build", g.give_order(7, [{"kind": "build", "build": "CASTLE"}])["err"])
        self.assertIn("not mine", g.give_order(99, ["heal"])["err"])
        self.assertEqual(g.orders("all")["count"], 0)
        self.assertEqual(g.calls, [])

    def test_a_later_move_onto_a_mountain_is_refused_up_front(self):
        """Live Assyria t16: "heal, move to (13,28), hold" healed first and paused a turn later on the mountain."""
        g = SimGame()
        g.blocked[(6, 2)] = "destination plot is a mountain"
        r = g.give_order(7, ["heal", {"kind": "move", "x": 6, "y": 2}, {"kind": "hold", "mission": "alert"}])
        self.assertFalse(r["ok"])
        self.assertIn("step 2 (move to (6,2)) can never run: destination plot is a mountain", r["err"])
        self.assertEqual(g.orders("all")["count"], 0)
        # what can change by then (borders, occupants, the fog) is left to the step's own turn
        g.blocked[(6, 2)] = "destination is inside Persia's borders and you have no open-borders agreement"
        self.assertTrue(g.give_order(7, ["heal", {"kind": "move", "x": 6, "y": 2}])["ok"])

    def test_a_blocked_destination_mid_order_pauses_and_releases_the_move(self):
        g = SimGame()
        g.give_order(7, [{"kind": "move", "x": 6, "y": 2}])
        g.blocked[(6, 2)] = "destination is inside Persia's borders and you have no open-borders agreement"
        row = self.arrive(g)["rows"][0]
        self.assertEqual((row["status"], row["pause"]["kind"]), ("paused", "destination"))
        self.assertEqual(g.pending, {}, "the unit stops: the order's standing move is dropped")
        # GitLab #143: the pause skips the unit for the turn (it never blocks the end turn) and says so
        self.assertEqual(g.calls[1:], [("unit_mission", 7, "MISSION_SKIP", None)], "the skip, and no step after the pause")
        self.assertEqual(row["pause"]["skipped_turn"], g.turn)
        self.assertIn("tries the destination again", row["pause"]["hint"])

    def test_a_destination_pause_retries_at_the_next_turn_start(self):
        """GitLab #143 (Maya t216): the Worker's order paused on a Cannon's plot and waited for a manual resume
        while the plot freed; a destination pause now tries again at every turn start by itself."""
        g = SimGame()
        g.give_order(7, [{"kind": "move", "x": 6, "y": 2}])
        g.blocked[(6, 2)] = "holds a Cannon of Korea (not at war): units cannot share its plot"
        self.assertEqual(self.arrive(g)["rows"][0]["status"], "paused")
        out = self.arrive(g)   # still taken: retried, paused again, skipped again
        row = out["rows"][0]
        self.assertEqual((row["status"], row["pause"]["kind"], row["pause"]["skipped_turn"]), ("paused", "destination", g.turn))
        self.assertEqual(g.calls[-1], ("unit_mission", 7, "MISSION_SKIP", None))
        self.assertIn("retried at turn start after destination", [h["what"] for h in g.notebook().orders("open")[0]["history"]])
        del g.blocked[(6, 2)]
        row = self.arrive(g)["rows"][0]   # the plot is free: the order walks on (and arrives: two plots left)
        self.assertEqual((row["status"], (g.units[7]["x"], g.units[7]["y"])), ("completed", (6, 2)))
        self.assertEqual(g.calls[-1], ("move_unit", 7, 6, 2))
        # a hostile pause is the agent's to resume, not the order's
        g2 = SimGame()
        g2.give_order(7, [{"kind": "move", "x": 8, "y": 2}])
        g2.hostiles.append({"id": 40, "owner_id": 63, "owner": "Barbarians", "unit": "BRUTE", "x": 6, "y": 3})
        self.assertEqual(self.arrive(g2)["rows"][0]["pause"]["kind"], "hostile")
        calls = len(g2.calls)
        self.assertEqual(self.arrive(g2)["rows"][0]["status"], "paused")
        self.assertEqual(len(g2.calls), calls, "nothing issued, nothing skipped")

    def test_a_hostile_in_sight_pauses_before_any_step_and_resume_acknowledges_it(self):
        g = SimGame()
        g.give_order(7, [{"kind": "move", "x": 8, "y": 2}, {"kind": "build", "build": "FARM"}])
        g.hostiles.append({"id": 40, "owner_id": 63, "owner": "Barbarians", "unit": "BRUTE", "x": 6, "y": 3})
        calls = len(g.calls)
        out = self.arrive(g)
        row = out["rows"][0]
        self.assertEqual((row["status"], row["pause"]["kind"]), ("paused", "hostile"))
        self.assertEqual(len(g.calls), calls, "the interrupted sequence took no other step")
        self.assertEqual(g._wake_reasons({"orders": out}, {}), ["order:1:paused"])
        self.assertIsNone(self.arrive(g)["rows"][0].get("did"), "a paused order does not run")
        r = g.resume_order(1)
        self.assertEqual(r["did"], ["move to (8,2): issued"])
        self.assertEqual(r["order"]["status"], "active")
        g.hostiles.append({"id": 41, "owner_id": 63, "owner": "Barbarians", "unit": "ARCHER", "x": 8, "y": 3})
        self.assertEqual(self.arrive(g)["rows"][0]["pause"]["hostiles"][0]["id"], 41, "only a new one pauses it")

    def test_existing_hostiles_are_acknowledged_when_the_order_is_given(self):
        g = SimGame()
        g.hostiles.append({"id": 40, "owner_id": 63, "owner": "Barbarians", "unit": "BRUTE", "x": 3, "y": 3})
        r = g.give_order(7, [{"kind": "move", "x": 8, "y": 2}])
        self.assertEqual(r["acknowledged_hostiles"][0]["id"], 40)
        self.assertEqual(r["order"]["status"], "active")

    def test_damage_pauses(self):
        g = SimGame()
        g.give_order(7, [{"kind": "move", "x": 8, "y": 2}])
        g.units[7]["hp"] = 70
        self.assertEqual(self.arrive(g)["rows"][0]["pause"]["kind"], "damaged")

    def test_a_refused_step_pauses_with_the_refusal(self):
        g = SimGame()
        g.refuse = "unit did not move: the engine found no path"
        r = g.give_order(7, [{"kind": "move", "x": 8, "y": 2}])
        self.assertEqual(r["order"]["status"], "paused")
        self.assertIn("no path", r["order"]["pause"]["reason"])
        self.assertFalse(r["order"]["last"]["ok"])

    def test_no_progress_pauses_instead_of_retrying_forever(self):
        g = SimGame()
        g.give_order(7, [{"kind": "move", "x": 8, "y": 2}])
        g.units[7].update({"x": 2, "y": 2})          # the engine dropped the path: back where it was issued
        g.pending.clear()
        g.units[7]["x"] = 2
        o = g.notebook().orders("open")[0]
        o["issued"]["x"], o["issued"]["y"] = 2, 2
        g.notebook().put_order(o)
        self.assertEqual(self.arrive(g)["rows"][0]["pause"]["kind"], "no_progress")

    def test_arrival_without_moves_waits_explicitly(self):
        g = SimGame()
        g.units[7]["moves"] = 0
        r = g.give_order(7, [{"kind": "move", "x": 3, "y": 2}])
        self.assertEqual((r["order"]["state"], g.calls), ("no_moves", []))
        self.assertEqual(self.arrive(g)["rows"][0]["status"], "completed")

    def test_a_lost_unit_fails_the_order(self):
        g = SimGame()
        g.give_order(7, [{"kind": "move", "x": 8, "y": 2}])
        del g.units[7]
        row = self.arrive(g)["rows"][0]
        self.assertEqual((row["status"], row["pause"]["kind"]), ("failed", "unit_gone"))

    def test_cancel_and_replace(self):
        g = SimGame()
        g.give_order(7, [{"kind": "move", "x": 8, "y": 2}])
        self.assertFalse(g.give_order(7, ["heal"])["ok"], "one owner per unit")
        r = g.cancel_order(1, note="plans changed")
        self.assertEqual(r["standing_move_dropped"], {"x": 8, "y": 2})
        self.assertEqual(g.pending, {})
        self.assertFalse(g.cancel_order(1)["ok"])
        g.give_order(7, [{"kind": "move", "x": 8, "y": 2}])
        r = g.give_order(7, [{"kind": "move", "x": 2, "y": 4}], replace_id=2)
        self.assertEqual(r["replaced"], 2)
        self.assertEqual([o["status"] for o in g.notebook().orders("all")], ["cancelled", "replaced", "active"])

    def test_a_direct_command_takes_the_unit_back(self):
        g = SimGame()
        g.give_order(7, [{"kind": "move", "x": 8, "y": 2}])
        p = g.note_manual_order(7, "unit_mission")
        self.assertEqual((p["id"], p["status"]), (1, "paused"))
        self.assertIsNone(g.note_manual_order(8, "move_unit"), "no order on that unit")
        calls = len(g.calls)
        self.arrive(g)
        self.assertEqual(len(g.calls), calls, "the order never fights the command")
        # GitLab #143 (Maya t234): a direct order to a unit whose order is already paused replaces the order
        r = g.note_manual_order(7, "move_unit")
        self.assertEqual((r["id"], r["status"]), (1, "replaced"))
        self.assertIn("is closed", r["reason"])
        self.assertEqual(g.notebook().orders("open"), [])
        self.assertEqual(g.notebook().orders("all")[0]["status"], "replaced")
        self.assertIsNone(g.note_manual_order(7, "move_unit"), "nothing open any more")

    def test_an_unseen_turns_arrival_carries_the_digest(self):
        """GitLab #147 (Maya t213-t214): an order sent while the AIs moved ran on arrival with `arrival` (orders only)
        and the finish beside it carried no digest; the first call to meet a turn hands back what happened."""
        g = SimGame()
        g.expiring_city_states = list
        g.give_order(7, [{"kind": "move", "x": 9, "y": 2}])
        g.end_turn()
        g.unseen = True
        out = g.arrive_if_due(g.turn_state())
        self.assertEqual(out["digest"]["events"][0]["kind"], "turn_start")
        self.assertIn("orders", out)
        self.assertIsNone(g.arrive_if_due(g.turn_state()), "once per turn")
        g.end_turn()
        g.unseen = False
        self.assertNotIn("digest", g.arrive_if_due(g.turn_state()), "a turn a wait of ours opened had its digest there")

    def test_a_restart_after_a_step_completed_does_not_replay_it(self):
        g = SimGame()
        g.give_order(7, [{"kind": "move", "x": 6, "y": 2}, {"kind": "build", "build": "FARM"}])
        self.assertEqual((g.units[7]["x"], g.pending), (4, {7: (6, 2)}), "on its way")
        g.units[7]["x"] = 6                           # the engine carried the standing move to its end
        g.pending.clear()
        g2 = SimGame()                                # a new session: same game, same seat, same notebook
        g2.units, g2.turn, g2.pending = g.units, g.turn, g.pending
        out = self.arrive(g2)
        self.assertEqual(out["rows"][0]["did"], ["move to (6,2): done", "build FARM at (6,2): issued"])
        self.assertEqual([c[0] for c in g2.calls], ["unit_mission"], "the move is not issued again")

    def test_a_harness_that_died_mid_step_pauses_instead_of_replaying(self):
        g = SimGame()
        g.give_order(7, [{"kind": "move", "x": 8, "y": 2}], start=False)
        nb = g.notebook()
        o = nb.orders("open")[0]
        o["inflight"] = {"turn": 10, "step": 0, "what": "move to (8,2)"}
        nb.put_order(o)
        row = self.arrive(g)["rows"][0]
        self.assertEqual(row["pause"]["kind"], "uncertain")
        self.assertEqual(g.calls, [])
        self.assertEqual(g.resume_order(1)["did"], ["move to (8,2): issued"])

    def test_a_loaded_save_pauses(self):
        g = SimGame()
        g.give_order(7, [{"kind": "move", "x": 8, "y": 2}])
        g.turn = 5
        self.assertEqual(g.run_orders()[0]["pause"]["kind"], "turn_went_back")
        self.assertEqual(g.resume_order(1)["order"]["status"], "active")

    def test_hotseat_isolation(self):
        a, b = SimGame(seat=0), SimGame(seat=1)
        a.give_order(7, [{"kind": "move", "x": 8, "y": 2}])
        self.assertEqual(b.orders()["count"], 0)
        self.assertIsNone(self.arrive(b), "seat 1's turn start runs nothing of seat 0's")
        self.assertIsNone(b.note_manual_order(7, "move_unit"), "the same unit id on seat 1 is another unit")
        self.assertEqual(a.orders()["orders"][0]["status"], "active")

    def test_the_turn_claim_gates_the_window(self):
        from harness.turn_claim import ClaimRefused
        g = SimGame()
        g.give_order(7, [{"kind": "move", "x": 8, "y": 2}])

        def held(turn, tool, force=False):
            raise ClaimRefused("another client holds the turn", {"pid": 1})
        g.claim = held
        calls = len(g.calls)
        out = self.arrive(g)
        self.assertIn("not_run", out)
        self.assertEqual(len(g.calls), calls)
        self.assertIn("orders_not_run", g._wake_reasons({"orders": out}, {}))

    def test_arrive_skips_owned_units_in_resume_moves_and_tags_todo(self):
        g = SimGame()
        g.give_order(7, [{"kind": "move", "x": 8, "y": 2}])
        g.enemy_on.add((8, 2))
        g.end_turn()
        g.expiring_city_states = list
        g.turn_state = lambda pid=None: {"turn": g.turn, "active_player": 0, "my_turn": True,
                                         "todo": {"units": [{"id": 7, "type": "WORKER"}]}}
        ts = g._arrive(g.turn_state())
        self.assertIn("return H.resume_moves(0, {7})", g.lua)
        self.assertEqual(ts["orders"]["paused"], 1)
        self.assertEqual(ts["todo"]["units"][0]["order"]["id"], 1)
        self.assertIn("never attacks", ts["todo"]["units"][0]["order"]["reason"])


    def test_a_paused_orders_unit_is_resumed_like_any_other(self):
        """Live Assyria t20: a direct move_unit given to the Scout under its paused order sat at the turn start as
        "queued move did not resume": H.resume_moves skipped every unit with an open order, paused ones included."""
        g = SimGame()
        g.give_order(7, [{"kind": "move", "x": 8, "y": 2}])
        g.hostiles.append({"id": 40, "owner_id": 63, "owner": "Barbarians", "unit": "BRUTE", "x": 6, "y": 3})
        self.assertEqual(self.arrive(g)["rows"][0]["status"], "paused")
        g.end_turn()
        g.expiring_city_states = list
        g.turn_state = lambda pid=None: {"turn": g.turn, "active_player": 0, "my_turn": True, "todo": {"units": []}}
        g._arrive(g.turn_state())
        self.assertIn("return H.resume_moves(0)", g.lua, "no unit is held back by a paused order")


class AutomationTests(unittest.TestCase):
    """Grok's wish (Venice/Mongolia 2026-09-27): a Worker on AUTOMATE_BUILD given an order with no moves left
    issued nothing that turn, and the game's automation walked it away at the next turn start before the
    harness ran the order. A stored order takes the unit off automation at once."""
    setUp = GameOrderTests.setUp

    def test_an_order_that_issues_nothing_stops_the_units_automation(self):
        g = SimGame()
        g.units[7].update({"automated": True, "moves": 0})
        r = g.give_order(7, [{"kind": "build", "build": "FARM"}])
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["order"]["state"], "no_moves")
        self.assertTrue(r.get("automation_stopped"))
        self.assertIn(("unit_mission", 7, "COMMAND_STOP_AUTOMATION", None), g.calls)
        self.assertNotIn("automated", g.units[7])

    def test_a_stored_but_unstarted_order_stops_it_too(self):
        g = SimGame()
        g.units[7]["automated"] = True
        r = g.give_order(7, [{"kind": "move", "x": 4, "y": 2}], start=False)
        self.assertTrue(r["ok"] and r.get("automation_stopped"), r)
        self.assertEqual(g.calls, [("unit_mission", 7, "COMMAND_STOP_AUTOMATION", None)])

    def test_a_step_issued_now_needs_no_stop_command(self):
        g = SimGame()
        g.units[7]["automated"] = True
        r = g.give_order(7, [{"kind": "move", "x": 4, "y": 2}])
        self.assertTrue(r["ok"], r)
        self.assertNotIn("automation_stopped", r)
        self.assertEqual([c[0] for c in g.calls], ["move_unit"], "the move itself cancels automation")

    def test_a_unit_not_automated_gets_no_command(self):
        g = SimGame()
        g.units[7]["moves"] = 0
        r = g.give_order(7, [{"kind": "build", "build": "FARM"}])
        self.assertTrue(r["ok"], r)
        self.assertNotIn("automation_stopped", r)
        self.assertEqual(g.calls, [])


class ConsumedBuilderTests(unittest.TestCase):
    """Grok's wish (Venice/Mongolia 2026-09-27): a Great Merchant's Customs House build answered ok:true, the
    unit was consumed by it, and the next turn start marked the order failed ("not among my units"). The
    improvement standing on the plot with its builder gone is the order completed."""
    setUp = GameOrderTests.setUp

    def test_a_build_that_consumed_its_unit_completes_the_order(self):
        g = SimGame()
        g.units[7]["type"] = "MERCHANT"
        g.build_turns = 1
        r = g.give_order(7, [{"kind": "build", "build": "FARM"}])   # SimGame's stand-in for a Customs House
        self.assertTrue(r["ok"], r)
        g.end_turn()                                                  # the build pays out...
        del g.units[7]                                                # ...and takes the merchant with it
        rows = g._turn_start_orders(g.turn_state())
        row = rows["rows"][0]
        self.assertEqual(row["status"], "completed", row)
        self.assertIn("consumed", row.get("note", ""))
        self.assertTrue(any("consumed" in d for d in row.get("did", [])), row.get("did"))

    def test_a_unit_gone_before_its_build_stands_still_fails(self):
        g = SimGame()
        r = g.give_order(7, [{"kind": "build", "build": "FARM"}])
        self.assertTrue(r["ok"], r)
        del g.units[7]                                                # killed mid-build: nothing on the plot
        row = g._turn_start_orders(g.turn_state())["rows"][0]
        self.assertEqual(row["status"], "failed")
        self.assertIn("not among my units", row["pause"]["reason"])

    def test_a_paused_order_whose_unit_is_gone_closes_at_the_turn_start(self):
        # live t83 (Portugal): a settler's move order paused on a hostile, the settler founded Braga by hand, and
        # the order stayed listed as paused for six turns -- the turn-start pass ran active orders only.
        g = SimGame()
        g.give_order(7, [{"kind": "move", "x": 8, "y": 2}])
        self.assertEqual(g.note_manual_order(7, "unit_mission")["status"], "paused")
        del g.units[7]                                                # founded a city / killed / upgraded
        row = g._turn_start_orders(g.turn_state())["rows"][0]
        self.assertEqual(row["status"], "failed", row)
        self.assertIn("not among my units", row["pause"]["reason"])
        self.assertEqual(g.notebook().orders("open"), [])

    def test_a_paused_order_whose_unit_is_still_there_is_left_alone(self):
        g = SimGame()
        g.give_order(7, [{"kind": "move", "x": 8, "y": 2}])
        g.note_manual_order(7, "unit_mission")
        calls = len(g.calls)
        g.end_turn()
        out = g._turn_start_orders(g.turn_state())
        self.assertEqual([r["status"] for r in out["rows"]], ["paused"])
        self.assertNotIn("did", out["rows"][0], "nothing was issued or closed")
        self.assertEqual(len(g.calls), calls)
        self.assertEqual(g.notebook().orders("paused")[0]["status"], "paused")


class McpOrderTests(unittest.TestCase):
    def setUp(self):
        from harness import mcp_server
        self.m = mcp_server
        self._saved = mcp_server._game
        self.addCleanup(setattr, mcp_server, "_game", self._saved)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = mock.patch.dict(os.environ, {"CIV5_NOTES_DIR": self.tmp.name, "CIV5_SEAT": "0"})
        p.start()
        self.addCleanup(p.stop)
        g = SimGame()
        g.ts = {"turn": 10, "active_player": 0, "my_turn": True, "paused": False, "processing": False}
        g.turn_state = lambda pid=None: dict(g.ts)
        g.has_state = lambda name: True
        g.discussion_pending = lambda: False
        g.lock = contextlib.nullcontext
        self.g = g
        mcp_server._game = g

    def _call(self, tool, args):
        result = asyncio.run(self.m.mcp.call_tool(tool, args))
        text = result[0].text if isinstance(result, (list, tuple)) else result.content[0].text
        return json.loads(text)

    def test_the_tools_and_a_direct_command(self):
        r = self._call("give_order", {"unit_id": 7, "steps": [{"kind": "move", "x": 8, "y": 2}, "hold"]})
        self.assertTrue(r["ok"], r)
        self.assertEqual(self._call("orders", {})["orders"][0]["now"], "move to (8,2)")
        r = self._call("move_unit", {"unit_id": 7, "x": 3, "y": 3})
        self.assertEqual(r["order_paused"]["id"], 1)
        r = self._call("resume_order", {"order_id": 1})
        self.assertEqual(r["order"]["status"], "active", r)
        self.g.ts = {**self.g.ts, "active_player": 1, "my_turn": False}
        self.assertFalse(self._call("resume_order", {"order_id": 1})["ok"], "runs only on my turn")
        self.assertTrue(self._call("orders", {"status": "all"})["ok"], "the stored orders: any time")
        self.assertTrue(self._call("cancel_order", {"order_id": 1})["ok"], "cancelling: any time")

    def test_a_turn_no_wait_opened_gets_its_arrival_before_the_first_order(self):
        # live t95 (Portugal): accept_deal answered a leader at the end of t94 while the AI round still ran, the
        # round went on by itself, and t95 opened with no wait of ours in flight -- no arrival, so a worker's
        # standing move stalled and a finished quarry's order stayed open. The first mutating call of a turn
        # that has not arrived runs the arrival first (end_turn does the same before sending).
        self.g.expiring_city_states = list
        self.g.units[8] = {**self.g.units[7], "x": 3, "y": 2}   # another unit, with no order of its own
        r = self._call("give_order", {"unit_id": 7, "steps": [{"kind": "move", "x": 9, "y": 2}]})
        self.assertTrue(r["ok"], r)
        x0 = self.g.units[7]["x"]
        self.g.end_turn()                                   # the AIs moved; nothing of ours waited on it
        self.g.ts = {**self.g.ts, "turn": self.g.turn}
        self.assertNotEqual(self.g._arrived_at, (self.g.turn, 0))
        r = self._call("move_unit", {"unit_id": 8, "x": 3, "y": 3})   # any first order of the new turn
        self.assertEqual(self.g._arrived_at, (self.g.turn, 0), "the arrival ran")
        self.assertGreater(self.g.units[7]["x"], x0, "the open order walked on before the order ran")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["arrival"]["orders"]["rows"][0]["did"], ["move to (9,2): issued"],
                         "the order's reply says what the arrival did, as the wait would have")
        calls = len(self.g.calls)
        r = self._call("move_unit", {"unit_id": 8, "x": 4, "y": 3})
        self.assertEqual(len(self.g.calls), calls + 1, "once per turn: the second order ran alone")
        self.assertNotIn("arrival", r)

    def test_end_turn_gives_a_cold_turn_its_arrival_and_reports_it(self):
        # The same cold turn, and the next call is end_turn (live t95: nothing on the todo, so the model ended
        # the turn at once): the standing orders walk before the turn ends, and the reply says so.
        self.g.expiring_city_states = list
        self.assertTrue(self._call("give_order", {"unit_id": 7, "steps": [{"kind": "move", "x": 9, "y": 2}]})["ok"])
        x0 = self.g.units[7]["x"]
        self.g.end_turn()
        self.g.ts = {**self.g.ts, "turn": self.g.turn}
        sends = []
        self.g._end_turn_send = lambda lua: sends.append(lua) or {"ok": True, "turn_complete_sent": True}
        self.g.dismiss_pending_popups = lambda ts=None: False
        r = Game.end_turn(self.g)   # the real one (the sim's own end_turn is the world's clock)
        self.assertEqual(len(sends), 1)
        self.assertGreater(self.g.units[7]["x"], x0)
        self.assertEqual(r["arrival"]["orders"]["rows"][0]["did"], ["move to (9,2): issued"])


if __name__ == "__main__":
    unittest.main()


class HeldUnitRowTests(unittest.TestCase):
    """Live Assyria t13: the Warrior's garrison order paused on a Brute two plots away; its todo row said
    "queued move did not resume; re-issue move_unit" beside order.status paused."""

    def test_a_paused_order_explains_the_stalled_row(self):
        from harness.game_parts.turn import note_held_units
        units = [{"id": 16385, "type": "WARRIOR", "stalled_mission": True, "note": "queued move did not resume; re-issue move_unit"},
                 {"id": 24576, "type": "SCOUT", "moves": 2}]
        rows = [{"id": 1, "unit": {"id": 16385}, "status": "paused", "pause": {"reason": "a hostile BARBARIAN_WARRIOR is in sight"}},
                {"id": 2, "unit": {"id": 24576}, "status": "active"}]
        note_held_units(units, rows)
        self.assertEqual(units[0]["order"], {"id": 1, "status": "paused", "reason": "a hostile BARBARIAN_WARRIOR is in sight"})
        self.assertIn("resume_order", units[0]["note"])
        self.assertNotIn("re-issue", units[0]["note"])
        self.assertNotIn("order", units[1], "an active order is not a held unit")
        units = [{"id": 7, "stalled_mission": True, "note": "queued move did not resume; re-issue move_unit"}]
        note_held_units(units, [{"id": 3, "unit": {"id": 7}, "status": "failed"}])
        self.assertEqual(units[0]["order"], {"id": 3, "status": "failed"})
        self.assertIn("failed", units[0]["note"])

