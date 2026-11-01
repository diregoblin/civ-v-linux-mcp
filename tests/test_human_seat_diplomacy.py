"""A human seat has no leader screen (GitLab #175).

Three-seat hotseat, 2026-10-30 t6: seat 1 (Celts) called order(to="civ", id=2, action="friendship") on seat 2
(Indonesia, human). propose_friendship fired FROM_UI_DIPLO_EVENT_HUMAN_DISCUSSION_WORK_WITH_US at seat 2, whose
dormant diplomacy AI answered on the spot: {"accepted": false, "reply": "Making such a declaration at this point in
our relationship would be premature. Maybe another time."}, and the civ summary kept the line under history.

Every stock Game.DoFromUIDiploEvent call names an AI (leaderheadroot.lua / discussiondialog.lua open for AI leaders
only; diplolist.lua opens the PvP trade table for a human). So for a human seat: a Declaration of Friendship is the
PvP table's DoF pocket (tradelogic.lua PocketDoFHandler, both sides in one press), war is diplolist.lua's War button
(Network.SendChangeWar), and every other event is refused with what to do instead.
"""
import unittest
from unittest import mock

import test_mcp_safety as support

from harness.game import Game
from harness.game_parts import deal_items

WORLD = r"""
SENT, WARS = {}, {}
FromUIDiploEventTypes = { FROM_UI_DIPLO_EVENT_HUMAN_DECLARES_WAR = 0, FROM_UI_DIPLO_EVENT_HUMAN_NEGOTIATE_PEACE = 1,
  FROM_UI_DIPLO_EVENT_DENOUNCE = 20, FROM_UI_DIPLO_EVENT_HUMAN_DISCUSSION_WORK_WITH_US = 30,
  FROM_UI_DIPLO_EVENT_WORK_WITH_US_RESPONSE = 31, FROM_UI_DIPLO_EVENT_AI_REQUEST_DENOUNCE_RESPONSE = 32 }
Game.DoFromUIDiploEvent = function(id, other, a, b) SENT[#SENT + 1] = { id, other } end
Game.IsOption = function() return false end
Game.GetDealDuration = function() return 50 end
GameOptionTypes = { GAMEOPTION_ALWAYS_WAR = 1, GAMEOPTION_ALWAYS_PEACE = 2, GAMEOPTION_NO_CHANGING_WAR_PEACE = 3 }
Network = { SendChangeWar = function(team, war) WARS[#WARS + 1] = { team, war } end }
AT_WAR, DOF = false, false
local team = { IsHasMet = function() return true end, CanChangeWarPeace = function() return true end,
               IsAtWar = function() return AT_WAR end, IsForcePeace = function() return false end,
               CanDeclareWar = function() return true end, GetNumTurnsLockedIntoWar = function() return 0 end }
Teams = { [0] = team, [1] = team, [2] = team }
local function player(id, human)
  return { GetTeam = function() return id end, IsHuman = function() return human end, IsAlive = function() return true end,
           IsMinorCiv = function() return false end, IsDoF = function() return DOF end,
           IsDoFMessageTooSoon = function() error('the too-soon memory is an AI leader screen read') end }
end
Players = { [0] = player(0, true), [1] = player(1, false), [2] = player(2, true) }
TradeableItems = { TRADE_ITEM_DECLARATION_OF_FRIENDSHIP = 9 }
ASKED = {}
DEAL = { IsPossibleToTradeItem = function(self, from, to, typ, dur)
  ASKED[#ASKED + 1] = { from, to, typ, dur }
  return not AT_WAR and not DOF
end }
"""


class HumanSeatEventTests(unittest.TestCase):
    run_lua = support.LuaRuntimeTests.run_lua

    def setUp(self):
        support.LuaRuntimeTests.setUp(self)
        self.run_lua(WORLD)

    def test_the_leader_screen_events_never_reach_a_human_seat(self):
        self.run_lua("""
        local cases = { HUMAN_DISCUSSION_WORK_WITH_US = "action='friendship'", WORK_WITH_US_RESPONSE = "choice='accept'",
                        HUMAN_NEGOTIATE_PEACE = "action='peace'", DENOUNCE = 'no denouncement between human players',
                        AI_REQUEST_DENOUNCE_RESPONSE = 'no leader screen' }
        for event, says in pairs(cases) do
          local r = H.diplo_event(0, event, 2, 0, 0)
          assert(r.ok == false and r.human == true, event .. ': ' .. H.json(r))
          assert(r.err:find(says, 1, true), event .. ': ' .. r.err)
        end
        assert(#SENT == 0, 'nothing was sent to a dormant diplomacy AI: ' .. H.json(SENT))
        """)

    def test_war_on_a_human_seat_is_the_diplomacy_lists_war_button(self):
        self.run_lua("""
        local r = H.diplo_event(0, 'HUMAN_DECLARES_WAR', 2, 0, 0)
        assert(r.ok == true and r.human == true, H.json(r))
        assert(#WARS == 1 and WARS[1][1] == 2 and WARS[1][2] == true, 'Network.SendChangeWar(team, true): ' .. H.json(WARS))
        assert(#SENT == 0, 'no leader answers it')
        AT_WAR = true
        assert(H.diplo_event(0, 'HUMAN_DECLARES_WAR', 2, 0, 0).ok == false and #WARS == 1, 'the war gates still apply')
        AT_WAR = false
        Game.IsOption = function(o) return o == GameOptionTypes.GAMEOPTION_ALWAYS_PEACE end
        r = H.diplo_event(0, 'HUMAN_DECLARES_WAR', 2, 0, 0)
        assert(r.ok == false and r.err:find('game options') and #WARS == 1, H.json(r))
        """)

    def test_an_ai_leader_still_gets_the_event(self):
        self.run_lua("""
        assert(H.diplo_event(0, 'DENOUNCE', 1, 0, 0).ok == true)
        assert(H.diplo_event(0, 'HUMAN_DECLARES_WAR', 1, 0, 0).ok == true)
        assert(#SENT == 2 and SENT[1][2] == 1 and #WARS == 0, H.json(SENT))
        """)

    def test_friendship_check_sends_a_human_seat_to_the_table(self):
        self.run_lua("""
        local r = H.friendship_check(2, 0)
        assert(r.ok == true and r.human == true, H.json(r))
        DOF = true
        assert(H.friendship_check(2, 0).ok == false, 'already friends is still refused')
        DOF = false
        Players[1].IsDoFMessageTooSoon = function() return true end
        r = H.friendship_check(1, 0)
        assert(r.ok == false and r.err:find('too recently'), 'an AI keeps its leader screen gate: ' .. H.json(r))
        """)

    def test_the_trade_catalog_row_is_asked_of_a_human_seat_only(self):
        self.run_lua("""
        local r = H.friendship_catalog(DEAL, 0, 2)
        assert(r.us == true and r.them == true and r.note == nil, H.json(r))
        assert(#ASKED == 1 and ASKED[1][1] == 0 and ASKED[1][2] == 2 and ASKED[1][3] == 9 and ASKED[1][4] == 50, H.json(ASKED))
        r = H.friendship_catalog(DEAL, 0, 1)
        assert(r.ai == true and r.us == false and r.note:find("action='friendship'", 1, true), H.json(r))
        assert(#ASKED == 1, 'the DoF legality query against an AI crashed the game; it is never made')
        AT_WAR = true
        r = H.friendship_catalog(DEAL, 0, 2)
        assert(r.us == false and r.note == 'not while at war', H.json(r))
        AT_WAR, DOF = false, true
        assert(H.friendship_catalog(DEAL, 0, 2).note:find('already in force'))
        """)


class FriendshipItemTests(unittest.TestCase):
    HUMAN = {"us": True, "them": True}

    def check(self, row, **item):
        return deal_items.check_items({"ok": True, "declaration_of_friendship": row}, [{"type": "DECLARATION_OF_FRIENDSHIP", **item}])

    def test_a_legal_row_passes_from_either_side(self):
        self.assertTrue(self.check(self.HUMAN)["ok"])
        self.assertTrue(self.check(self.HUMAN, from_us=False)["ok"])

    def test_an_ai_or_a_missing_row_points_at_the_leader_screen(self):
        for row in ({"us": False, "them": False, "ai": True}, None):
            r = self.check(row)
            self.assertFalse(r["ok"])
            self.assertIn("action='friendship'", r["err"])

    def test_a_greyed_row_says_why(self):
        r = self.check({"us": False, "them": False, "note": "not while at war"})
        self.assertFalse(r["ok"])
        self.assertIn("not while at war", r["err"])

    def test_the_pocket_is_pressed_once_for_both_sides(self):
        g = Game.__new__(Game)
        g.seat, g._trade_state = 0, "SimpleDiploTrade"
        g.c = mock.Mock()
        g.incoming_deal = lambda pid=None: {"ok": True, "items": [{"type": "DECLARATION_OF_FRIENDSHIP", "from_us": True},
                                                                   {"type": "DECLARATION_OF_FRIENDSHIP", "from_us": False}]}
        with mock.patch("harness.game_parts.deals.time.sleep"):
            r = g._add_deal_items(2, [{"type": "DECLARATION_OF_FRIENDSHIP"}, {"type": "DECLARATION_OF_FRIENDSHIP", "from_us": False}], 0)
        self.assertEqual([c.args[1] for c in g.c.exec.call_args_list], ["PocketDoFHandler(1)"])
        self.assertTrue(r["ok"], r)


class ProposeFriendshipTests(unittest.TestCase):
    def game(self, check):
        g = Game.__new__(Game)
        g.seat = 1
        g.calls = []
        g.q = lambda code, *a, **k: check
        g._harness_diplo = lambda on: None
        g.diplo_event = lambda *a: g.calls.append(("diplo_event", a)) or {"ok": True}
        g.propose_deal = lambda other, items, ask_counter=False, pid=None, demand=False: (
            g.calls.append(("propose_deal", other, items, pid))
            or {"ok": True, "pvp": True, "accepted": None, "pending": True, "pending_to": other, "note": "sent"})
        return g

    def test_a_human_seat_gets_the_declaration_as_a_deal(self):
        g = self.game({"ok": True, "human": True})
        r = g.propose_friendship(2)
        self.assertEqual(g.calls, [("propose_deal", 2, [{"type": "DECLARATION_OF_FRIENDSHIP"}], 1)])
        self.assertTrue(r["friendship"] and r["pvp"] and r["pending"])
        self.assertEqual(r["pending_to"], 2)
        self.assertIsNone(r["accepted"])
        self.assertNotIn("reply", r, "no leader spoke")
        self.assertIn("answer(choice='accept'", r["note"])

    def test_a_refused_check_proposes_nothing(self):
        g = self.game({"ok": False, "err": "already friends (declaration still running)"})
        self.assertFalse(g.propose_friendship(2)["ok"])
        self.assertEqual(g.calls, [])

    def test_an_ai_is_still_asked_on_its_leader_screen(self):
        g = self.game({"ok": True})
        g._friendship_result = lambda other, me, pid: {"ok": True, "accepted": True}
        with mock.patch("harness.game_parts.friendship.time.sleep"):
            g.propose_friendship(4)
        self.assertEqual(g.calls, [("diplo_event", ("HUMAN_DISCUSSION_WORK_WITH_US", 4, 0, 0))])


if __name__ == "__main__":
    unittest.main()
