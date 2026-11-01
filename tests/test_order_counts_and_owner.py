"""The standing orders' counts and their one-owner rule (GitLab #181, #182).

#181 (three-seat hotseat, Maya seat 0, t26): the finish that ended t25 returned
status.orders {open: 1, paused: 0, rows: [{id 7, status "completed", closed_turn 26}]}: the turn-start window
counted the open orders before running them, so the quarry that completed in that very run still read as open
and no `closed` count came back (#113 had fixed the briefing's count only).

#182 (three-seat hotseat, Celts seat 1, t18): order(to="unit", action="mission", MISSION_BUILD BUILD_FARM at
(8,23)) from (7,24) created walk-then-build order 1, walked the Worker there, and the same reply paused order 1
("given a direct order (unit_mission); that command owns it now"), its note still placing the unit at (7,24).
"""
import asyncio
import contextlib
import json
import os
import tempfile
import unittest
from unittest import mock

import test_orders as to
from harness import orders as O


class RemoteBuildSim(to.SimGame):
    """SimGame with Game.unit_mission's remote-build branch: a MISSION_BUILD naming another plot becomes a
    walk-then-build order (Game._remote_build), read from the unit's position as H.unit_pos gives it."""

    def q(self, code, *a, **k):
        if getattr(code, "fn", None) == "unit_pos":
            u = self.units.get(int(code.args[0]))
            return {"ok": True, "x": u["x"], "y": u["y"], "moves": u["moves"]} if u else {"ok": False}
        return super().q(code, *a, **k)

    def unit_mission(self, unit_id, mission, x=-1, y=-1, data2=0, build=None, pid=None):
        if mission == "MISSION_BUILD" and build and x >= 0 and y >= 0:
            remote = self._remote_build(unit_id, build, x, y, pid)
            if remote is not None:
                return remote
        return super().unit_mission(unit_id, mission, x, y, data2, build, pid)


class _NotesDir(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = mock.patch.dict(os.environ, {"CIV5_NOTES_DIR": self.tmp.name, "CIV5_SEAT": "0"})
        p.start()
        self.addCleanup(p.stop)


class TurnStartCountsTests(_NotesDir):
    """#181: the counts are read from each row's status after the orders have run."""

    def test_an_order_completed_in_this_run_is_closed_not_open(self):
        g = to.SimGame()
        g.build_turns = 1
        self.assertTrue(g.give_order(7, [{"kind": "build", "build": "BUILD_FARM"}])["ok"])
        g.end_turn()                                       # the farm is finished at the turn change
        out = g._turn_start_orders(g.turn_state())
        self.assertEqual(out["rows"][0]["status"], "completed", out)
        self.assertEqual((out["open"], out.get("closed"), out["paused"]), (0, 1, 0), out)
        # the briefing over the same notebook agrees: nothing open
        self.assertEqual(O.briefing_section(g.notebook().orders("open"), 5)["open"], 0)

    def test_a_failed_order_is_closed_and_paused_and_active_ones_are_open(self):
        g = to.SimGame()
        g.units[8] = {**g.units[7], "x": 5, "y": 5}
        g.units[9] = {**g.units[7], "x": 9, "y": 9}
        g.give_order(7, [{"kind": "move", "x": 2, "y": 8}])   # walking: stays active
        g.give_order(8, [{"kind": "move", "x": 5, "y": 9}])
        g.note_manual_order(8, "move_unit")                   # paused, waits for an answer
        g.give_order(9, [{"kind": "move", "x": 9, "y": 3}])
        del g.units[9]                                        # lost: the order fails at the turn start
        g.end_turn()
        out = g._turn_start_orders(g.turn_state())
        by_id = {r["unit"]["id"]: r["status"] for r in out["rows"]}
        self.assertEqual(by_id, {7: "active", 8: "paused", 9: "failed"}, out)
        self.assertEqual((out["open"], out.get("closed"), out["paused"]), (2, 1, 1), out)
        self.assertEqual({k: out[k] for k in ("open", "closed", "paused")}, O.counts(out["rows"]))

    def test_no_closed_count_when_nothing_closed(self):
        self.assertEqual(O.counts([{"status": "active"}, {"status": "paused"}]), {"open": 2, "paused": 1})
        self.assertEqual(O.counts([{"status": "replaced"}, {"status": "cancelled"}]), {"open": 0, "closed": 2, "paused": 0})


class DirectCommandOwnerTests(_NotesDir):
    """#182: a direct command takes the unit from the order that held it before the command, never from the order
    the command itself creates."""

    def setUp(self):
        super().setUp()
        from harness import mcp_server
        self.m = mcp_server
        self.addCleanup(setattr, mcp_server, "_game", mcp_server._game)
        g = RemoteBuildSim()
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

    def _remote_farm(self, x, y):
        return self._call("order", {"to": "unit", "action": "mission", "id": 7,
                                    "args": {"mission": "MISSION_BUILD", "build": "BUILD_FARM", "x": x, "y": y}})

    def test_the_remote_build_keeps_the_order_it_created_and_says_where_the_unit_got(self):
        self.g.units[7]["moves"] = 1                          # Celts t18: one step, then no moves left
        r = self._remote_farm(3, 2)
        self.assertTrue(r["ok"], r)
        self.assertNotIn("order_paused", r)
        self.assertEqual(r["order"]["status"], "active", r)
        self.assertEqual(r["at"], {"x": 3, "y": 2})
        self.assertIn("walked to (3,2)", r["note"])
        self.assertNotIn("(2,2)", r["note"])
        self.assertEqual([o["status"] for o in self.g.notebook().orders("all")], ["active"])
        self.g.end_turn()                                     # the next turn start issues the build
        rows = self.g._turn_start_orders(self.g.turn_state())["rows"]
        self.assertEqual(rows[0].get("did"), ["build FARM at (3,2): issued"], rows)

    def test_a_remote_build_still_on_its_way_names_the_tile_reached(self):
        self.g.units[7]["moves"] = 1
        r = self._remote_farm(2, 5)                           # three plots away: one step this turn
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["order"]["status"], "active", r)
        self.assertIn("the unit is at (2,3)", r["note"])

    def test_a_remote_build_replaces_the_order_that_held_the_unit(self):
        self.assertTrue(self.g.give_order(7, [{"kind": "move", "x": 2, "y": 8}])["ok"])
        r = self._remote_farm(3, 2)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r.get("replaced"), 1, r)
        self.assertNotIn("order_paused", r)
        self.assertEqual({o["id"]: o["status"] for o in self.g.notebook().orders("all")}, {1: "replaced", 2: "active"})

    def test_a_plain_direct_command_still_takes_the_unit_from_its_order(self):
        self.assertTrue(self.g.give_order(7, [{"kind": "move", "x": 2, "y": 8}])["ok"])
        r = self._call("order", {"to": "unit", "action": "mission", "id": 7, "args": {"mission": "MISSION_FORTIFY"}})
        self.assertEqual(r["order_paused"]["id"], 1, r)
        self.assertEqual(self.g.notebook().orders("open")[0]["status"], "paused")


if __name__ == "__main__":
    unittest.main()
