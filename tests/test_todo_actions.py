"""todo_actions: legal actions for many units in one read.

Step 4 of the loop asked `available_unit_actions` once per unit. On the late S1 map (38 units) that was 38
tuner round-trips a turn, most of the ~15 minutes `scripts/play_loop.py` spent on one turn. One query now
answers for every unit that still needs an order (plus the promotion-ready ones), or for the ids given.
"""
import json
import os
import unittest
from unittest import mock

import anyio

import test_mcp_safety as support
from test_set_seat import session
from harness import mcp_server as m
from harness.surface import classes
from harness.game import Game


WORLD = """
GameDefines={MOVE_DENOMINATOR=60}
Locale={ConvertTextKey=function(key) return ({TXT_KEY_FORTIFY_HELP='Fortify: +50% defence'})[key] or key end}
GameInfo={Units={[3]={Type='UNIT_WARRIOR'}, [5]={Type='UNIT_WORKER'}}}
GameInfoActions={
  [0]={Type='MISSION_FORTIFY', MissionType=7, CommandType=-1, AutomateType=-1, MissionData=-1, Help='TXT_KEY_FORTIFY_HELP'},
  [1]={Type='MISSION_SKIP', MissionType=8, CommandType=-1, AutomateType=-1, MissionData=-1},
}
local function mk(id, utype, ready, promo, x)
  return {
    GetID=function() return id end, GetUnitType=function() return utype end,
    GetX=function() return x end, GetY=function() return 1 end,
    MovesLeft=function() return ready and 120 or 0 end,
    IsReadyToMove=function() return ready end, IsAutomated=function() return false end,
    IsDelayedDeath=function() return false end, IsPromotionReady=function() return promo end,
    IsCombatUnit=function() return false end,
    CanStartMission=function(self, mid) return mid==7 or (ready and mid==8) end,
  }
end
UNITS={ [11]=mk(11, 3, true, false, 1), [22]=mk(22, 5, false, true, 2), [33]=mk(33, 3, false, false, 3) }
UNITS[11].GetDamage=function() return 35 end
UNITS[11].GetCurrHitPoints=function() return 65 end
UNITS[11].GetMaxHitPoints=function() return 100 end
UNITS[22].GetDamage=function() return 0 end
ACTIVE=0
Game.GetActivePlayer=function() return ACTIVE end
Players={[0]={
  GetUnitByID=function(_, id) return UNITS[id] end,
  Units=function() local ids={11,22,33}; local i=0; return function() i=i+1; return UNITS[ids[i]] end end,
  IsTurnActive=function() return true end, GetCurrentResearch=function() return 4 end,
  Cities=function() return function() return nil end end,
  GetTeam=function() return 0 end,
}}
"""


class TodoActionsLuaTests(unittest.TestCase):
    run_lua = support.LuaRuntimeTests.run_lua

    def setUp(self):
        support.LuaRuntimeTests.setUp(self)
        self.run_lua(WORLD)

    def test_default_covers_todo_units_and_promotion_ready_ones_without_help(self):
        self.run_lua("""
        local r = H.todo_actions(0, nil, false)
        assert(r.ok == true and r.source == 'todo' and r.n == 2, tostring(r.n))
        -- 11 is ready to move (todo.units); 22 is not ready but has a promotion waiting; 33 is neither.
        assert(r.units[1].id == 11 and r.units[1].type == 'WARRIOR' and r.units[1].promotion_ready == nil)
        assert(r.units[2].id == 22 and r.units[2].type == 'WORKER' and r.units[2].promotion_ready == true)
        assert(#r.units[1].actions == 2 and r.units[1].actions[1].type == 'MISSION_FORTIFY')
        for _, u in ipairs(r.units) do for _, a in ipairs(u.actions) do assert(a.help == nil, 'help kept') end end
        assert(r.units[1].moves == 2 and r.units[1].x == 1)
        """)

    def test_full_keeps_only_the_computed_button_line(self):
        """v216: the standing sentence under a button is static and lives in reference("actions"); even
        `full` does not repeat it. Only the per-unit computed lines (upgrade price, scrap gold) remain."""
        self.run_lua("""
        local r = H.todo_actions(0, nil, true)
        assert(r.units[1].actions[1].type == 'MISSION_FORTIFY' and r.units[1].actions[1].help == nil,
               tostring(r.units[1].actions[1].help))
        local ref = H.reference('actions')
        assert(ref.ok and #ref.rows == 1 and ref.rows[1].type == 'MISSION_FORTIFY', tostring(#ref.rows))
        assert(ref.rows[1].help == 'Fortify: +50% defence' and ref.rows[1].kind == 'mission', tostring(ref.rows[1].help))
        """)

    def test_explicit_ids_keep_their_order_and_name_a_missing_unit(self):
        self.run_lua("""
        local r = H.todo_actions(0, {33, 99, 11}, false)
        assert(r.ok == true and r.source == 'ids' and r.n == 3)
        assert(r.units[1].id == 33 and r.units[1].ok == true and #r.units[1].actions == 1)
        assert(r.units[2].id == 99 and r.units[2].ok == false and r.units[2].err == 'no such unit')
        assert(r.units[3].id == 11 and r.units[3].ok == true)
        """)

    def test_a_damaged_unit_carries_hp_and_a_healthy_one_does_not(self):
        """v220 (#35): hp is the one piece of unit state the summary level needs that the row lacked."""
        self.run_lua("""
        local r = H.todo_actions(0, nil, false)
        assert(r.units[1].id == 11 and r.units[1].hp == 65 and r.units[1].max_hp == 100, tostring(r.units[1].hp))
        assert(r.units[2].id == 22 and r.units[2].hp == nil and r.units[2].max_hp == nil)
        """)

    def test_inactive_seat_is_refused_unless_ids_are_given(self):
        self.run_lua("""
        ACTIVE=1
        local r = H.todo_actions(0, nil, false)
        assert(r.ok == false and r.err:find('unit_ids'), tostring(r.err))
        local r2 = H.todo_actions(0, {11}, false)
        assert(r2.ok == true and r2.n == 1)
        """)


class TodoActionsQueryTests(unittest.TestCase):
    def test_game_formats_ids_as_a_lua_list_and_nil_when_empty(self):
        g = Game.__new__(Game)
        g.seat = 0
        seen = []
        g.q = lambda code, timeout=None: seen.append((code, timeout)) or {"ok": True}
        g.todo_actions()
        g.todo_actions([5, 7], full=True)
        self.assertEqual(seen[0][0], "return H.todo_actions(0, nil, false)")
        self.assertEqual(seen[1][0], "return H.todo_actions(0, {5, 7}, true)")
        self.assertGreaterEqual(seen[0][1], 120, "a whole turn's units in one query needs a long timeout")


# A normal-level reply as H.todo_actions gives it (shapes from live S1 t266 and the Lua above).
NORMAL = {"ok": True, "source": "ids", "n": 3, "units": [
    {"ok": True, "id": 475136, "type": "PARATROOPER", "x": 46, "y": 10, "moves": 2, "promotions": [],
     "attack_targets": [], "ranged_targets": [],
     "actions": [{"type": "MISSION_SKIP", "kind": "mission", "mission": "MISSION_SKIP"},
                 {"type": "COMMAND_WAKE", "kind": "command"},
                 {"type": "MISSION_MOVE_TO", "kind": "mission", "mission": "MISSION_MOVE_TO"},
                 {"type": "INTERFACEMODE_PARADROP", "kind": "interface", "mission": "MISSION_PARADROP",
                  "target_view": "targets"}]},
    {"ok": True, "id": 737288, "type": "WORKER", "x": 42, "y": 23, "moves": 2, "promotions": [],
     "actions": [{"type": "AUTOMATE_BUILD", "kind": "other"}, {"type": "BUILD_REMOVE_ROUTE", "kind": "build"}],
     "nearby_builds": [{"x": 41, "y": 22, "builds": ["BUILD_REMOVE_JUNGLE"], "routes": ["BUILD_ROAD"],
                        "resource": "ARTIFACTS", "t": "PLAINS", "owned": False,
                        "build_info": [{"build": "BUILD_REMOVE_JUNGLE", "turns": 5}]}]},
    {"ok": True, "id": 11, "type": "WARRIOR", "x": 3, "y": 4, "moves": 1, "hp": 65, "max_hp": 100,
     "promotion_ready": True, "promotions": [{"promotion": "PROMOTION_SHOCK_1", "name": "Shock I"}],
     "actions": [{"type": "MISSION_FORTIFY", "kind": "mission", "mission": "MISSION_FORTIFY"},
                 {"type": "MISSION_HEAL", "kind": "mission", "mission": "MISSION_HEAL"}],
     "attack_targets": [{"x": 4, "y": 4, "unit": "BRUTE", "owner": "Barbarians", "hp": 40, "max_hp": 100,
                         "how": "move_unit onto this plot attacks", "preview": {"odds": 0.9}}]},
]}


def game_answering(reply):
    g = Game.__new__(Game)
    g.seat = 0
    g.q = lambda code, timeout=None: json.loads(json.dumps(reply))
    return g


class TodoActionsDetailTests(unittest.TestCase):
    """#35: summary / normal / full from the same one read, with counts and a way back to every omission."""

    def test_normal_is_the_default_and_unchanged_apart_from_the_counts(self):
        r = game_answering(NORMAL).todo_actions([1, 2, 3])
        self.assertEqual(r["detail"], "normal")
        self.assertEqual((r["n"], r["returned"]), (3, 3))
        def bare(rows):   # #47: every action, target and promotion carries `call` (and `read`); the rest is unchanged
            return json.loads(json.dumps(rows, default=str).replace('"call"', '"_"').replace('"read"', '"_"'))
        stripped = [{k: ([{kk: vv for kk, vv in x.items() if kk not in ("call", "read", "calls")} if isinstance(x, dict) else x   # calls: #102
                          for x in v] if isinstance(v, list) else v) for k, v in u.items()} for u in r["units"]]
        self.assertEqual(stripped, NORMAL["units"])
        self.assertTrue(all("call" in a for u in r["units"] for a in u["actions"]))
        # GitLab #176: Wake is a complete order too, not a row the seat has to guess the call for
        self.assertEqual(r["units"][0]["actions"][1]["call"],
                         {"tool": "order", "args": {"to": "unit", "action": "mission", "id": 475136, "args": {"mission": "COMMAND_WAKE"}}})
        self.assertEqual(r["units"][2]["attack_targets"][0]["call"], {"tool": "order", "args": {"to": "unit", "action": "move", "id": 11, "args": {"x": 4, "y": 4}}})
        self.assertEqual(r["units"][2]["promotions"][0]["call"]["args"], {"to": "unit", "action": "promote", "id": 11, "args": {"promotion": "PROMOTION_SHOCK_1"}})
        self.assertEqual(r["units"][0]["actions"][3]["read"]["args"]["view"], "targets")
        del bare
        self.assertNotIn("omitted", r)

    def test_summary_rows_keep_ids_state_and_non_routine_actions(self):
        r = game_answering(NORMAL).todo_actions([1, 2, 3], detail="summary")
        para, worker, warrior = r["units"]
        self.assertEqual(para, {"id": 475136, "type": "PARATROOPER", "x": 46, "y": 10, "moves": 2,
                                "actions": [{"tool": "state", "args": {"what": "unit", "view": "targets", "mission": "MISSION_PARADROP", "id": 475136}},
                                            {"tool": "order", "args": {"to": "unit", "action": "mission", "id": 475136, "args": {"mission": "MISSION_PARADROP"}},
                                             "choose": ["x", "y"]}],
                                "routine": 3})
        self.assertEqual(worker["actions"], [{"tool": "order", "args": {"to": "unit", "action": "mission", "id": 737288, "args": {"mission": "AUTOMATE_BUILD"}}}])
        self.assertEqual(worker["build_plots"], [{"x": 41, "y": 22, "builds": ["BUILD_REMOVE_JUNGLE"], "resource": "ARTIFACTS",
                                                  "calls": [{"tool": "order", "args": {"to": "unit", "action": "mission", "id": 737288,
                                                                                       "args": {"mission": "MISSION_BUILD", "build": "BUILD_REMOVE_JUNGLE", "x": 41, "y": 22}}}]}],
                         "the build plot carries its order (#102)")
        self.assertEqual((warrior["hp"], warrior["max_hp"], warrior["promotion_ready"]), (65, 100, True))
        self.assertEqual(warrior["promotions"], ["PROMOTION_SHOCK_1"])
        self.assertEqual([a["args"].get("args", {}).get("mission") for a in warrior["actions"]],
                         ["MISSION_HEAL", None, None], "heal is a decision, fortify is routine")
        self.assertEqual(warrior["actions"][1], {"tool": "order", "args": {"to": "unit", "action": "move", "id": 11, "args": {"x": 4, "y": 4}}},
                         "the melee target is a move row (#45)")
        self.assertEqual(warrior["actions"][2]["args"]["args"]["promotion"], "PROMOTION_SHOCK_1")
        self.assertEqual(warrior["attack"], [{"x": 4, "y": 4, "unit": "BRUTE", "owner": "Barbarians", "hp": 40}])
        self.assertIn("MISSION_FORTIFY", r["routine_actions"])
        self.assertEqual(r["drill_down"]["args"], {"what": "units", "view": "actions", "id": [475136, 737288, 11], "detail": "normal"})

    def test_summary_agrees_with_normal_on_every_action(self):
        from harness.affordances import COMMAND_TOOLS
        from harness.surface import retirement as R
        own_action = {R.RETIRED[tool].fixed["action"]: k for k, (tool, _choose) in COMMAND_TOOLS.items()}
        g = game_answering(NORMAL)
        s, n = g.todo_actions(detail="summary"), g.todo_actions()
        for a, b in zip(s["units"], n["units"]):
            types = [x["type"] for x in b["actions"]]
            decided = [t for t in types if t not in s["routine_actions"]]
            self.assertEqual(a["id"], b["id"])
            # every non-routine action is among the rows: by its mission / build name, or by its own tool
            named = {(r["args"].get("args") or {}).get("build") or (r["args"].get("args") or {}).get("mission")
                     or own_action.get(r["args"].get("action")) for r in a["actions"]}
            self.assertFalse({t for t in decided if not t.startswith("INTERFACEMODE_")} - named, (decided, named))
            for t in decided:
                if t.startswith("INTERFACEMODE_"):
                    self.assertIn(next(x["mission"] for x in b["actions"] if x["type"] == t), named)
            self.assertEqual(a["routine"], len(types) - len(decided))

    def test_summary_is_deterministic_and_smaller_on_a_live_shaped_reply(self):
        """The rows cost more than the bare type strings they replace (#45), so the saving is measured on a reply
        shaped like the live one (S1 t266: 38 units, the normal rows carrying `help` and the previews)."""
        def with_help(u):
            u = json.loads(json.dumps(u))
            for a in u["actions"]:
                a["help"] = "Fortify: +50% defence; the unit holds until woken"
            return u
        live = {**NORMAL, "units": [with_help(u) for u in NORMAL["units"]] * 13, "n": 39}
        g = game_answering(live)
        one, two = json.dumps(g.todo_actions(detail="summary")), json.dumps(g.todo_actions(detail="summary"))
        self.assertEqual(one, two)
        self.assertLess(len(one), 0.7 * len(json.dumps(g.todo_actions())))

    def test_limit_lists_every_omitted_unit_with_the_args_that_fetch_it(self):
        r = game_answering(NORMAL).todo_actions(detail="summary", limit=1)
        self.assertEqual((r["n"], r["returned"]), (3, 1))
        self.assertEqual(r["omitted"], {"count": 2, "ids": [737288, 11],
                                        "args": {"unit_ids": [737288, 11], "detail": "summary"}})
        self.assertEqual(r["drill_down"]["args"]["id"], [475136])

    def test_full_flag_is_detail_full_and_bad_levels_are_refused(self):
        seen = []
        g = game_answering(NORMAL)
        g.q = lambda code, timeout=None: seen.append(code) or json.loads(json.dumps(NORMAL))
        self.assertEqual(g.todo_actions(full=True)["detail"], "full")
        self.assertEqual(g.todo_actions(detail="full")["detail"], "full")
        self.assertTrue(all(c.endswith("true)") for c in seen), seen)
        self.assertFalse(g.todo_actions(detail="brief")["ok"])
        self.assertFalse(g.todo_actions(full=True, detail="summary")["ok"])
        self.assertFalse(g.todo_actions(limit=0)["ok"])
        self.assertEqual(len(seen), 2, "a refused argument never reaches the game")

    def test_a_refusal_and_a_missing_unit_pass_through(self):
        refused = {"ok": False, "err": "this seat is not active"}
        self.assertEqual(game_answering(refused).todo_actions(detail="summary"), refused)
        r = game_answering({"ok": True, "source": "ids", "n": 1, "units": [{"ok": False, "id": 99,
                                                                           "err": "no such unit"}]})
        self.assertEqual(r.todo_actions([99], detail="summary")["units"],
                         [{"id": 99, "ok": False, "err": "no such unit"}])


class FakeGame:
    seat = 0

    def has_state(self, name):
        return True

    def mode(self):
        return "single"

    def turn_state(self, pid=None):
        return {"turn": 270, "active_player": 0, "my_turn": True, "processing": False, "paused": False,
                "hotseat": False, "mode": "single", "blocking_name": "ENDTURN_BLOCKING_UNITS", "todo": {},
                "pending_popups": []}

    def discussion_pending(self):
        return False

    def todo_actions(self, unit_ids=None, full=False, detail=None, limit=None):
        self.args = (unit_ids, full)
        self.kw = (detail, limit)
        return {"ok": True, "source": "ids" if unit_ids else "todo", "n": 1, "units": [{"id": 11, "ok": True}]}


class TodoActionsToolTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeGame()
        self.patches = [mock.patch.object(m, "game", lambda: self.fake),
                        mock.patch.dict(os.environ, {"CIV5_TUNERD_SOCK": "/tmp/civ5-test-todo.sock", "CIV5_SEAT": "0"}),
                        mock.patch.object(m, "_seat_rechecked", True),
                        mock.patch.dict(m._RECENT, {}, clear=True)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_tool_passes_ids_and_full_through_and_runs_inside_do(self):
        out, batch = anyio.run(session, [("todo_actions", {"unit_ids": [11], "full": True}),
                                         ("do", {"actions": [{"tool": "todo_actions", "args": {}}]})])
        self.assertTrue(out["ok"])
        self.assertEqual(out["units"][0]["id"], 11)
        self.assertEqual(batch["results"][0]["result"]["source"], "todo")
        self.assertNotIn(classes.of_call("todo_actions"), classes.BATCH_EXCLUDED)

    def test_detail_and_limit_pass_through(self):
        anyio.run(session, [("todo_actions", {"detail": "summary", "limit": 5})])
        self.assertEqual(self.fake.kw, ("summary", 5))
        anyio.run(session, [("todo_actions", {})])
        self.assertEqual(self.fake.kw, (None, None), "no detail given means the Game default")

    def test_empty_list_means_the_todo_list(self):
        (out,) = anyio.run(session, [("todo_actions", {"unit_ids": []})])
        self.assertEqual(self.fake.args, (None, False))
        self.assertEqual(out["source"], "todo")
