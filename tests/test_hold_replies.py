"""What a hold order reports (GitLab #176).

Celts t7: order(unit, mission, MISSION_FORTIFY) on a Warrior that had moved answered activity_name SLEEP_OR_FORTIFY
and moves 1; units() read activity SLEEP, fortified false; todo.units no longer named it; the actions list offered
COMMAND_WAKE with no `call`. The engine's fortify is ACTIVITY_SLEEP plus a fortify count that starts at the unit's
next turn start when it moved this turn, no hold spends moves, and a holding unit is not IsReadyToMove (the end-turn
list). The reply's `hold` block says that from the same facts the unit list and todo.units read.

Lua half: H.unit_hold_state / H.unit_fortifying on the ongoing-units test world, and unit_pos carrying them.
Python half: harness/unit_hold.describe, and a unit_mission reply built from a read-back.
"""
import unittest
from unittest import mock

import test_mcp_safety as support
import test_ongoing_units as tou
from harness import unit_hold as UH
from harness.game_parts import units as units_mod
from tests.test_after_reads import _game


class HoldStateLuaTests(unittest.TestCase):
    run_lua = support.LuaRuntimeTests.run_lua

    def setUp(self):
        support.LuaRuntimeTests.setUp(self)
        self.run_lua("Map = Map or {}")
        self.run_lua(tou.WORLD)
        self.run_lua(r"""
ActivityTypes.ACTIVITY_SLEEP = 2; ActivityTypes.ACTIVITY_HOLD = 0
GameDefines.MAX_FORTIFY_TURNS = 2; GameDefines.FORTIFY_MODIFIER_PER_TURN = 20
function hold_unit(o)
  local u = make_unit(o)
  u.IsEverFortifyable = function() return o.ever ~= false end
  u.GetFortifyTurns = function() return o.turns or 0 end
  return u
end
""")

    def test_a_fortify_after_a_move_is_fortifying_and_off_the_end_turn_list(self):
        self.run_lua(r"""
local w = hold_unit{ id = 16385, type = 5, x = 4, y = 4, moves = 60, activity = 2, turns = 0, ready = false, strength = 8 }
local s = H.unit_hold_state(w)
assert(s.activity == "SLEEP" and s.fortify_turns == 0 and s.fortifyable == true, H.json(s))
assert(s.needs_orders == false and s.fortify_max == 2 and s.fortify_pct == 20, H.json(s))
assert(H.unit_fortifying(w) == true)
local done = hold_unit{ id = 2, type = 5, x = 4, y = 4, moves = 120, activity = 2, turns = 1 }
assert(H.unit_fortifying(done) == false, "a count above 0 is fortified, not fortifying")
local scout = hold_unit{ id = 3, type = 1, x = 4, y = 4, moves = 60, activity = 2, ever = false }
assert(H.unit_fortifying(scout) == false, "a unit that cannot fortify only sleeps")
Units[#Units + 1] = w
local p = H.unit_pos(16385, 0)
assert(p.activity_name == "SLEEP" and p.hold.activity == "SLEEP" and p.hold.needs_orders == false, H.json(p))
local row
for _, r in ipairs(H.units(0)) do if r.id == 16385 then row = r end end
assert(row.activity == "SLEEP" and row.fortified == false and row.fortifying == true and row.holding == true, H.json(row))
""")


class DescribeTests(unittest.TestCase):
    @staticmethod
    def after(moves=1, **hold):
        facts = {"activity": "SLEEP", "fortifyable": True, "fortify_turns": 0, "needs_orders": False,
                 "fortify_max": 2, "fortify_pct": 20}
        facts.update(hold)
        return {"ok": True, "x": 4, "y": 4, "moves": moves, "hold": facts}

    def test_fortifying_says_when_the_bonus_comes_and_what_the_move_left_means(self):
        h = UH.describe("MISSION_FORTIFY", self.after())
        self.assertEqual((h["state"], h["fortified"], h["fortify_turns"], h["full_in"], h["needs_orders"]),
                         ("fortifying", False, 0, 2, False))
        self.assertIn("bonus starts at its next turn start (+20%), full strength (+40%) in 2 turns", h["summary"])
        self.assertIn("off the end-turn list", h["summary"])
        self.assertIn("1 move left: a hold spends none", h["moves"])
        self.assertIn("fortify starts over", h["moves"])

    def test_fortified_now(self):
        h = UH.describe("MISSION_FORTIFY", self.after(moves=2, fortify_turns=1))
        self.assertEqual((h["state"], h["fortified"]), ("fortified", True))
        self.assertIn("fortified (+20% defence); full strength (+40%) in 1 turn", h["summary"])
        h = UH.describe("MISSION_FORTIFY", self.after(moves=0, fortify_turns=2))
        self.assertIn("at full strength", h["summary"])
        self.assertNotIn("moves", h, "no moves left: nothing to explain")

    def test_sleep_alert_skip_and_wake(self):
        self.assertEqual(UH.describe("MISSION_SLEEP", self.after(fortifyable=False))["state"], "asleep")
        self.assertEqual(UH.describe("MISSION_ALERT", self.after(activity="SENTRY"))["state"], "alert")
        skip = UH.describe("MISSION_SKIP", self.after(moves=2, activity="HOLD"))
        # t12: MISSION_SKIP answered moves 2 and HOLD while todo dropped the unit; the reply now says why
        self.assertEqual((skip["state"], skip["needs_orders"]), ("skipping", False))
        self.assertIn("back on the end-turn list next turn", skip["summary"])
        self.assertIn("2 moves left", skip["moves"])
        wake = UH.describe("COMMAND_WAKE", self.after(moves=2, activity="AWAKE", needs_orders=True))
        self.assertEqual(wake["state"], "awake")
        self.assertIn("still names it", wake["summary"])
        self.assertNotIn("moves", wake)

    def test_not_a_hold_or_an_older_runtime_adds_nothing(self):
        self.assertIsNone(UH.describe("MISSION_BUILD", self.after()))
        self.assertIsNone(UH.describe("MISSION_FORTIFY", {"ok": True, "moves": 1, "activity_name": "SLEEP"}))


class MissionReplyTests(unittest.TestCase):
    def setUp(self):
        units_mod.defer_after_reads(False)

    def test_the_fortify_reply_carries_the_hold_block(self):
        hold = {"activity": "SLEEP", "fortifyable": True, "fortify_turns": 0, "needs_orders": False,
                "fortify_max": 2, "fortify_pct": 20}
        g = _game([("H.unit_mission", {"ok": True}),
                   ("H.unit_pos", {"ok": True, "x": 7, "y": 26, "moves": 1, "activity": 2, "activity_name": "SLEEP",
                                   "hold": hold})])
        with mock.patch("harness.game_parts.units.time.sleep"):
            r = g.unit_mission(16385, "MISSION_FORTIFY")
        self.assertTrue(r["ok"], r)
        self.assertEqual((r["activity_name"], r["moves"]), ("SLEEP", 1))
        self.assertEqual((r["hold"]["state"], r["hold"]["needs_orders"]), ("fortifying", False))


if __name__ == "__main__":
    unittest.main()
