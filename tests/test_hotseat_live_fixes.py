"""Defects found on 2026-09-24 in the first two-human hotseat game (Alpha/Korea vs Bravo/Austria).

Every seat is the harness's own, so the situations a solo game only stumbles into could be built
on purpose: a war declared on a human, its leader screen, the World Congress founding during a
hand-off, a pillage ordered with no moves, and a relationship read of the other human.
"""
from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import test_mcp_safety as support  # noqa: E402


def _detached_game():
    from harness.game import Game
    g = Game.__new__(Game)
    g.seat = 0
    g._runtime_ok = True
    return g


class StalePopupRecordTests(unittest.TestCase):
    """H.popups keeps a record from PopupShown until PopupProcessed. The World Congress splash was
    queued during the hotseat hand-off and vanished without Processed: its context hidden, no popup
    on screen, and every action refused with "popup needs a decision" while generic_popup said
    nothing was open."""

    def _game(self, pending, hidden, popup_up, states=("InGame", "LeagueSplash")):
        g = _detached_game()
        dropped = []

        def q(code, timeout=None):
            if "H.popup_up(" in code:
                return popup_up
            if "H.drop_popup(" in code:
                dropped.append(code)
                return True
            raise AssertionError(code)

        g.q = q
        g.turn_state = lambda pid=None: {"pending_popups": pending}
        # v214: the screens' up/down come from one H.modal_flags read; a context that is not loaded is absent
        g._screens = lambda: {"screens": {"LeagueSplash": not hidden} if "LeagueSplash" in states else {}}
        return g, dropped

    def test_a_record_whose_screen_is_gone_is_dropped(self):
        pending = [{"name": "BUTTONPOPUP_LEAGUE_SPLASH", "type": -1522614506}]
        g, dropped = self._game(pending, hidden=True, popup_up=False)
        out = g._drop_stale_popup_records()
        self.assertEqual(len(dropped), 1)
        self.assertIn("H.drop_popup(-1522614506, ", dropped[0])
        self.assertEqual(out, ["BUTTONPOPUP_LEAGUE_SPLASH (stale record, screen already gone)"])

    def test_a_visible_screen_keeps_its_record(self):
        pending = [{"name": "BUTTONPOPUP_LEAGUE_SPLASH", "type": -1522614506}]
        g, dropped = self._game(pending, hidden=False, popup_up=True)
        self.assertEqual(g._drop_stale_popup_records(), [])
        self.assertEqual(dropped, [])

    def test_a_screen_queued_behind_another_popup_keeps_its_record(self):
        pending = [{"name": "BUTTONPOPUP_LEAGUE_SPLASH", "type": -1522614506}]
        g, dropped = self._game(pending, hidden=True, popup_up=True)
        self.assertEqual(g._drop_stale_popup_records(), [])
        self.assertEqual(dropped, [])

    def test_a_decision_popup_with_no_known_context_is_never_touched(self):
        pending = [{"name": "BUTTONPOPUP_CITY_CAPTURED", "type": 7}]
        g, dropped = self._game(pending, hidden=True, popup_up=False)
        self.assertEqual(g._drop_stale_popup_records(), [])
        self.assertEqual(dropped, [])


class PillageWithoutMovesTests(unittest.TestCase):
    """The engine takes a MISSION_PILLAGE from a unit with no moves and drops it: the quarry stayed
    whole, the unit went to HOLD, and the reply said ok with gold_gained 0 (live t219)."""

    def test_pillage_at_zero_moves_is_refused_up_front(self):
        g = _detached_game()
        pushed = []
        g.q = lambda code, timeout=None: {"moves": 0, "improvement": False, "route": False, "x": 32, "y": 10}
        g._unit_mission = lambda *a, **k: pushed.append(a) or {"ok": True}
        r = g.unit_mission(114698, "MISSION_PILLAGE", pid=0)
        self.assertFalse(r["ok"])
        self.assertIn("no moves left", r["err"])
        self.assertEqual((r["x"], r["y"]), (32, 10))
        self.assertEqual(pushed, [], "nothing was pushed to the engine")

    def test_a_pillage_reports_whether_the_plot_changed(self):
        g = _detached_game()
        state = {"pillaged": False}

        def q(code, timeout=None):
            if "H.pillage_plot_facts(" in code:
                return {"moves": 60, "improvement": False, "route": False, "x": 32, "y": 10}
            return {"improvement": state["pillaged"], "route": False}

        g.q = q
        g.summary = lambda pid=None: {"gold": 205}
        g._unit_mission = lambda *a, **k: state.update(pillaged=True) or {"ok": True}
        import harness.game as game_module
        with mock.patch.object(game_module.time, "sleep"):
            r = g.unit_mission(114698, "MISSION_PILLAGE", pid=0)
        self.assertTrue(r["ok"])
        self.assertTrue(r["effect"]["improvement_pillaged"])
        self.assertFalse(r["effect"]["route_pillaged"])
        self.assertNotIn("note", r["effect"])
        self.assertEqual(r["effect"]["gold_gained"], 0)


class LeaderScreenGuardTests(unittest.TestCase):
    """A leader screen (here Bravo's war-declared echo) freezes the engine's update loop; orders pushed
    under it half-apply. Two Artillery set up beneath it stayed "busy" and could not fire until the
    screen was closed. Actions are refused while it is up; reads and the closers still work."""

    TS = {"active_player": 0, "paused": False, "processing": False, "my_turn": True, "turn": 218,
          "leader_greeting_pending": True, "pending_popups": [], "blocking_name": "ENDTURN_BLOCKING_UNITS"}

    def setUp(self):
        from harness import mcp_server
        self.mcp_server = mcp_server
        self._saved = mcp_server._game
        calls = self.calls = []

        class FakeGame:
            seat = 0

            def turn_state(self, pid=None):
                return dict(LeaderScreenGuardTests.TS)

            def discussion_pending(self):
                return False

            def has_state(self, name):
                return True

            def unit_mission(self, *a, **k):
                calls.append(("unit_mission", a, k))
                return {"ok": True}

            def discussion(self, *a, **k):
                calls.append(("discussion",))
                return {"pending": True}

        mcp_server._game = FakeGame()

    def tearDown(self):
        self.mcp_server._game = self._saved

    def _call(self, tool, args):
        result = asyncio.run(self.mcp_server.mcp.call_tool(tool, args))
        text = result[0].text if isinstance(result, (list, tuple)) else result.content[0].text
        return json.loads(text)

    def test_an_order_under_a_leader_screen_is_refused_with_the_way_out(self):
        r = self._call("unit_mission", {"unit_id": 131084, "mission": "MISSION_RANGE_ATTACK", "x": 30, "y": 12})
        self.assertFalse(r["ok"])
        self.assertIn("leader screen", r["err"])
        self.assertIn("answer(choice='leave')", r["err"])
        self.assertEqual([c[0] for c in self.calls], [])

    def test_the_reads_that_show_the_screen_still_answer(self):
        r = self._call("discussion", {})
        self.assertTrue(r.get("pending"))


class RelationshipWithAHumanTests(unittest.TestCase):
    """The stock diplomacy list blanks the status tooltip for a human seat and never asks the engine
    for an approach or opinion table; the engine still answers for a human, and the harness relayed
    "They have some early concerns about your warmongering" about the other human."""
    run_lua = support.LuaRuntimeTests.run_lua

    def setUp(self):
        support.LuaRuntimeTests.setUp(self)

    WORLD = """
    local p={GetTeam=function() return 0 end,
      GetApproachTowardsUsGuess=function() error('the AI approach guess must not be asked of a human') end,
      IsDoF=function() return false end, IsDenouncedPlayer=function() return false end,
      GetNumWarsFought=function() return 0 end,
      GetNegativeReligiousConversionPoints=function() return 0 end,
      GetNegativeArchaeologyPoints=function() return 0 end,
      HasRecentIntrigueAbout=function() return false end}
    local o={IsAlive=function() return true end, IsMinorCiv=function() return false end, IsHuman=function() return HUMAN end,
      GetCivilizationShortDescription=function() return 'Austria' end, GetName=function() return 'Bravo' end,
      GetTeam=function() return 1 end, IsDenouncedPlayer=function() return false end,
      GetOpinionTable=function() if HUMAN then error('the opinion table must not be asked of a human') end return {'They like you'} end,
      GetEspionageSpies=function() return {} end,
      IsAskedToStopConverting=function() return false end, IsStopSpyingMessageTooSoon=function() return true end,
      IsDontSettleMessageTooSoon=function() return false end, IsAskedToStopDigging=function() return false end,
      IsDoFMessageTooSoon=function() return false end, IsDoF=function() return false end}
    Players={[0]=p,[1]=o}
    Teams={[0]={IsHasMet=function() return true end, IsAtWar=function() return true end,
      GetNumTurnsLockedIntoWar=function() return 0 end,
      HasEmbassyAtTeam=function() return false end, IsAllowsOpenBordersToTeam=function() return false end,
      IsHasResearchAgreement=function() return false end, IsHasDefensivePact=function() return false end},
      [1]={HasEmbassyAtTeam=function() return false end, IsAllowsOpenBordersToTeam=function() return false end,
        IsAtWar=function() return true end, IsHasMet=function() return true end}}
    GameDefines={MAX_CIV_PLAYERS=2, MAX_MAJOR_CIVS=2}
    H.approach_name=function() return 'HOSTILE' end
    """

    def test_a_human_seat_has_no_approach_or_opinion(self):
        self.run_lua("HUMAN=true\n" + self.WORLD + """
        local r=H.relationship(0,1)
        assert(r.ok and r.human==true and r.at_war==true)
        assert(r.approach_guess==nil, 'no approach for a human')
        assert(#r.opinion==0, 'no opinion lines for a human')
        """)

    def test_an_ai_seat_keeps_both(self):
        self.run_lua("HUMAN=false\n" + self.WORLD + """
        local r=H.relationship(0,1)
        assert(r.ok and r.human==false)
        assert(r.approach_guess=='HOSTILE', tostring(r.approach_guess))
        assert(r.opinion[1]=='They like you')
        """)


class DealsBetweenHumansTests(unittest.TestCase):
    """Peace between two humans (live t226): make_peace opened the trade table with the treaty on it,
    accept_deal proposed it, and the other seat found it as incoming_deal on its turn. After it accepted,
    the items lingered on the scratch table as a fresh "incoming deal" and current_deals refused."""
    run_lua = support.LuaRuntimeTests.run_lua

    def setUp(self):
        support.LuaRuntimeTests.setUp(self)

    DEAL = """
    local i=0
    cleared=0
    deal={
      GetFromPlayer=function() return 0 end, GetToPlayer=function() return 1 end,
      GetNumItems=function() return 1 end,
      ResetIterator=function() i=0 end,
      GetNextItem=function()
        i=i+1
        if i==1 then return 1, 30, 0, 10, nil, nil, nil, 1 end
      end,
      ClearItems=function() cleared=cleared+1; i=99 end,
      AddGoldTrade=function() error('must not Add*') end,
    }
    finalized={}
    UI={GetScratchDeal=function() return deal end,
        DoFinalizePlayerDeal=function(them, us, yes) finalized[#finalized+1]={them=them,us=us,yes=yes} end}
    TradeableItems={TRADE_ITEM_GOLD=1}
    """

    def test_accepting_or_refusing_empties_the_scratch_table(self):
        self.run_lua(self.DEAL + """
        local r=H.accept_deal(1)
        assert(r.ok==true and r.other==0, 'accepted from the other seat')
        assert(finalized[1].them==0 and finalized[1].us==1 and finalized[1].yes==true)
        assert(cleared==1, 'the scratch table is emptied after finalizing, as the stock screen does on hide')
        i=0
        r=H.refuse_deal(1)
        assert(r.ok==true and finalized[2].yes==false and cleared==2)
        """)

    def test_the_todo_names_a_waiting_proposal(self):
        self.run_lua(self.DEAL + """
        Players={[1]={IsTurnActive=function() return true end,GetCurrentResearch=function() return 1 end,
          Cities=function() return function() end end,Units=function() return function() end end}}
        Game={GetActivePlayer=function() return 1 end}
        GameInfo={Units={}};GameDefines={MOVE_DENOMINATOR=60}
        local r=H.todo(1)
        assert(r.incoming_deal and r.incoming_deal.from==0 and r.incoming_deal.items==1, 'the offer is in the todo')
        assert(r.incoming_deal.hint:find("answer(choice='accept')", 1, true), 'and says how to answer it')
        -- our own outgoing proposal is not a decision for us
        deal.GetFromPlayer=function() return 1 end
        r=H.todo(1)
        assert(r.incoming_deal==nil)
        -- GitLab #161: the engine's record of a waiting proposal outlives an empty table read
        UI.ProposedDealExists=function(a, b) return a==0 and b==1 end
        UI.LoadProposedDeal=function() end
        deal.GetNumItems=function() return 0 end
        deal.GetNextItem=function() return nil end
        GameDefines.MAX_MAJOR_CIVS=2; Players[0]={}
        r=H.todo(1)
        assert(r.incoming_deal and r.incoming_deal.from==0 and r.incoming_deal.items==0, H.json(r.incoming_deal))
        """)

    def test_the_todo_skips_a_table_between_two_other_seats(self):
        """GitLab #172: seat 0's proposal to seat 2 stayed on the shared scratch and seat 1's todo named it."""
        self.run_lua(self.DEAL + """
        Players={[1]={IsTurnActive=function() return true end,GetCurrentResearch=function() return 1 end,
          Cities=function() return function() end end,Units=function() return function() end end}}
        Game={GetActivePlayer=function() return 1 end}
        GameInfo={Units={}};GameDefines={MOVE_DENOMINATOR=60}
        deal.GetToPlayer=function() return 2 end
        local r=H.todo(1)
        assert(r.incoming_deal==nil, 'not seat 1\\'s offer: ' .. H.json(r.incoming_deal))
        """)


if __name__ == "__main__":
    unittest.main()
