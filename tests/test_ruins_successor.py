"""A move whose unit the ruins replaced (GitLab #169).

Maya t5: order(unit, move) took Scout 24576 onto adjacent ruins at (22,21); the ruins made it Mayan Atlatlist 32770
there; the reply was {"ok": false, "err": "no such unit"} because the read-back found the old id gone. The next
digest's unit_upgraded row placed the Scout at its turn-start plot and said it "moved on automation"; assignment 8
stayed on the vanished id. Celts t22: a move to a Scout a standing move had already walked into ruins answered a
bare "no such unit" too.

Lua half (successors.lua): the successor is one of my units created this turn of a type the old one upgrades or
ruins-upgrades to, on the destination first; it is recorded, put on the logged unit_destroyed row, and found again
for an order to the old id. Python half: the move reply (success with `successor`, the notebook carried over, or
explicit uncertainty), the refusal of a retry, and the digest row.
"""
import unittest
from unittest import mock

import test_mcp_safety as support
import test_ongoing_units as tou
from harness.game_parts import units as units_mod
from tests.test_after_reads import _game
from tests.test_combat_narration import narrate

ATLATLIST = {"id": 32770, "type": "MAYAN_ATLATLIST", "x": 22, "y": 21, "moves": 0, "hp": 100}


class SuccessorLuaTests(unittest.TestCase):
    run_lua = support.LuaRuntimeTests.run_lua

    def setUp(self):
        support.LuaRuntimeTests.setUp(self)
        self.run_lua("Map = Map or {}")
        self.run_lua(tou.WORLD)
        self.run_lua(r"""
GameInfo.Units[1].GoodyHutUpgradeUnitClass = "UNITCLASS_ARCHER"
GameInfo.Units[6] = { Type = "UNIT_MAYAN_ATLATLIST", Class = "UNITCLASS_ARCHER" }
GameInfo.Units[7] = { Type = "UNIT_WORKER", Class = "UNITCLASS_WORKER" }
for _, row in pairs({ GameInfo.Units[1], GameInfo.Units[5], GameInfo.Units[6], GameInfo.Units[7] }) do GameInfo.Units[row.Type] = row end
function born(o)
  local u = make_unit(o)
  u.GetGameTurnCreated = function() return o.created or 0 end
  u.GetCurrHitPoints = function() return 100 end
  return u
end
-- the Scout is gone; this turn's new units: the Atlatlist on the ruins, a Worker trained elsewhere
Units = { born{ id = 32770, type = 6, x = 22, y = 21, moves = 0, created = 1 },
          born{ id = 40000, type = 7, x = 22, y = 22, moves = 120, created = 1 } }
""")

    def test_the_successor_on_the_destination_is_found_recorded_and_put_on_the_loss_row(self):
        self.run_lua(r"""
H.pending_moves[H.pm_key(24576, 0)] = { x = 22, y = 21, pid = 0, unit_id = 24576 }
H.record("unit_destroyed", { player = 0, unit = 24576, unit_type = "SCOUT", x = 23, y = 21, plot_from = "roster" })
local r = H.move_successor(24576, "SCOUT", 23, 21, 22, 21, 2, 0)
assert(r.successor and r.successor.id == 32770 and r.successor.type == "MAYAN_ATLATLIST", H.json(r))
assert(r.successor.x == 22 and r.successor.y == 21 and r.successor.how == "order", H.json(r))
assert(H.pending_moves[H.pm_key(24576, 0)] == nil, "the standing move died with the old unit")
local d = H.events[#H.events].data
assert(d.new_unit == 32770 and d.new_type == "MAYAN_ATLATLIST" and d.x == 22 and d.y == 21, H.json(d))
assert(d.plot_from == nil and d.moved_by == "order", H.json(d))
-- the destroy hook that runs after the read-back reads the record the same way
local late = { player = 0, unit = 24576, unit_type = "SCOUT", x = 23, y = 21, plot_from = "roster" }
H.attach_successor(late)
assert(late.new_unit == 32770 and late.x == 22 and late.plot_from == nil, H.json(late))
-- a retry to the old id names it
assert(H.successor_of(24576, 0).successor.id == 32770)
""")

    def test_nothing_or_two_candidates_is_said_never_guessed(self):
        self.run_lua(r"""
local r = H.move_successor(24576, "WARRIOR", 23, 21, 22, 21, 2, 0)
assert(r.successor == nil and #r.candidates == 0, "an Atlatlist is no Warrior's upgrade: " .. H.json(r))
Units[#Units + 1] = born{ id = 32771, type = 6, x = 22, y = 21, moves = 0, created = 1 }
r = H.move_successor(24576, "SCOUT", 23, 21, 22, 21, 2, 0)
assert(r.successor == nil and #r.candidates == 2, H.json(r))
assert(H.successor_of(24576, 0).successor == nil, "nothing was recorded")
""")

    def test_an_id_a_standing_move_took_into_the_ruins_is_found_from_the_roster(self):
        """Celts t22: the briefing still named the Scout; the move to it answered a bare "no such unit"."""
        self.run_lua(r"""
H.roster[0] = { [24576] = { unit = "SCOUT", x = 23, y = 21, moving = true } }
H.pending_moves[H.pm_key(24576, 0)] = { x = 22, y = 21, pid = 0, unit_id = 24576 }
local r = H.successor_of(24576, 0)
assert(r.successor and r.successor.id == 32770 and r.successor.how == "standing_move", H.json(r))
assert(H.successor_of(99, 0).successor == nil, "an id the roster never saw has no successor")
""")


def _move_game(move_reply, extra):
    answers = [("H.attack_before(", {"attack": False, "seq": 10}),
               ("H.events_since(", [{"kind": "alert", "data": {"text": "Your Unit equips itself with advanced weapons found in the ruins!"}}]),
               ("H.move_unit(", move_reply),
               ("H.unit_pos(", {"ok": False, "err": "no such unit"})] + extra
    return _game(answers)


class MoveReplyTests(unittest.TestCase):
    SENT = {"ok": True, "x": 23, "y": 21, "moves": 1, "type": "SCOUT", "max_moves": 2}

    def setUp(self):
        units_mod.defer_after_reads(False)
        patcher = mock.patch("harness.game_parts.units.time.sleep")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_move_into_upgrading_ruins_succeeds_names_the_successor_and_carries_the_notebook(self):
        g = _move_game(self.SENT, [("H.move_successor(", {"ok": True, "successor": dict(ATLATLIST, turn=5, how="order")})])
        g.carry_unit_over = mock.Mock(return_value={"assignments": [{"id": 8, "role": "explore"}]})
        r = g.move_unit(24576, 22, 21)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["successor"], ATLATLIST)
        self.assertEqual((r["unit_id"], r["moved_from"], r["arrived"], r["unit_gone"]), (24576, {"x": 23, "y": 21}, True, True))
        self.assertIn("replaced it with MAYAN_ATLATLIST 32770", r["note"])
        g.carry_unit_over.assert_called_once_with(24576, 32770, why="upgraded in the ruins")
        self.assertEqual(r["carried_over"]["assignments"][0]["id"], 8)
        self.assertEqual(r["actions"][0]["args"], {"what": "unit", "id": 32770, "view": "tactical"})
        self.assertEqual(r["happened"][0]["kind"], "alert")
        q = next(q for q in g.queries if "H.move_successor(" in q)
        self.assertIn('24576, "SCOUT", 23, 21, 22, 21, 2', q)
        self.assertIn(24576, g._spent_by_order, "the digest reads the loss as spent by my order")

    def test_a_vanished_mover_with_no_single_successor_is_uncertain_not_refused(self):
        g = _move_game(self.SENT, [("H.move_successor(", {"ok": True, "candidates": []})])
        g.carry_unit_over = mock.Mock()
        r = g.move_unit(24576, 22, 21)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["identity"], "unknown")
        self.assertIn("do not repeat the move", r["note"])
        self.assertEqual(r["actions"][0]["args"], {"what": "units"})
        g.carry_unit_over.assert_not_called()

    def test_a_hold_after_the_move_is_left_to_the_successor(self):
        g = _move_game(self.SENT, [("H.move_successor(", {"ok": True, "successor": dict(ATLATLIST, turn=5)})])
        g.carry_unit_over = mock.Mock(return_value={})
        r = g.move_unit(24576, 22, 21, then="fortify")
        self.assertTrue(r["ok"])
        self.assertFalse(r["then"]["ok"])
        self.assertIn("32770", r["then"]["err"])
        self.assertFalse(any("H.unit_mission(" in q for q in g.queries), "nothing sent to the vanished id")

    def test_a_retry_is_refused_naming_the_successor(self):
        g = _move_game({"ok": False, "err": "no such unit"},
                       [("H.successor_of(", {"ok": True, "successor": dict(ATLATLIST, turn=5, how="order")})])
        r = g.move_unit(24576, 22, 21)
        self.assertFalse(r["ok"])
        self.assertIn("MAYAN_ATLATLIST 32770 (turn 5); nothing was sent", r["err"])
        self.assertEqual(r["successor"]["id"], 32770)
        self.assertEqual(r["actions"][0]["args"]["id"], 32770)
        # an id with no known successor keeps the plain refusal
        g = _move_game({"ok": False, "err": "no such unit"}, [("H.successor_of(", {"ok": True})])
        self.assertEqual(g.move_unit(24576, 22, 21), {"ok": False, "err": "no such unit"})

    def test_a_mission_retry_is_refused_naming_the_successor_too(self):
        # live 2026-11-05 t28: MISSION_SKIP to the Scout the ruins had just replaced answered a bare "no such unit";
        # the naming was on the move path only
        g = _game([("H.unit_mission(", {"ok": False, "err": "no such unit"}),
                   ("H.successor_of(", {"ok": True, "successor": dict(ATLATLIST, turn=5, how="order")})])
        r = g.unit_mission(24576, "MISSION_SKIP")
        self.assertFalse(r["ok"])
        self.assertIn("MAYAN_ATLATLIST 32770 (turn 5); nothing was sent", r["err"])
        self.assertEqual(r["successor"]["id"], 32770)
        self.assertEqual(r["actions"][0]["args"]["id"], 32770)


class DigestRowTests(unittest.TestCase):
    START = {"kind": "turn_start", "turn": 5, "data": {"player": 0}}
    RUINS = {"kind": "alert", "turn": 5, "data": {"text": "Your Unit equips itself with advanced weapons found in the ruins!"}}

    def test_the_row_names_the_successor_the_ruins_plot_and_who_moved_it(self):
        gone = {"kind": "unit_destroyed", "turn": 5, "data": {"player": 0, "unit": 24576, "unit_type": "SCOUT", "x": 22,
                                                              "y": 21, "new_unit": 32770, "new_type": "MAYAN_ATLATLIST",
                                                              "moved_by": "order"}}
        out = narrate([self.START, gone, self.RUINS])
        self.assertEqual(out[1]["kind"], "unit_upgraded")
        self.assertEqual(out[1]["data"]["summary"], "your SCOUT found advanced weapons in the ruins at (22,21) (your move "
                                                    "took it there) and became a MAYAN_ATLATLIST (new id 32770)")

    def test_the_roster_fallback_names_automation_only_when_the_roster_saw_it(self):
        row = lambda **kw: {"kind": "unit_destroyed", "turn": 5,
                            "data": {"player": 0, "unit": 24576, "unit_type": "SCOUT", "x": 23, "y": 21, "plot_from": "roster", **kw}}
        manual = narrate([self.START, row(), self.RUINS])[1]["data"]["summary"]
        self.assertNotIn("automat", manual)
        self.assertIn("last recorded at (23,21); it moved since", manual)
        auto = narrate([self.START, row(moving=True), self.RUINS])[1]["data"]["summary"]
        self.assertIn("moving on its own (automated or a standing move)", auto)


if __name__ == "__main__":
    unittest.main()
