"""Deals between two human seats (GitLab #4): the receiving seat's view.

tradelogic.lua OnOpenPlayerDealScreen loads a proposal that exists between the two seats
(UI.ProposedDealExists -> UI.LoadProposedDeal) before showing it. incoming_deal does the same so the
seat can read it without the screen, and turn_status names the proposer.
"""
import unittest

import test_mcp_safety as support

WORLD = r"""
GameDefines = { MAX_MAJOR_CIVS = 4 }
TradeableItems = { TRADE_ITEM_GOLD_PER_TURN = 2, TRADE_ITEM_RESOURCES = 4 }
Players = { [0] = { GetTeam = function() return 0 end }, [1] = { GetTeam = function() return 1 end }, [2] = { GetTeam = function() return 2 end } }
PROPOSED = {}          -- "from:to" -> true
MADE = -1              -- UI.HasMadeProposal(us)
local scratch = { items = {}, from = -1, to = -1 }
SCRATCH = scratch
function scratch:ResetIterator() self.i = 0 end
function scratch:GetNextItem()
  self.i = self.i + 1
  local it = self.items[self.i]
  if not it then return nil end
  return it.type, 0, 0, it.data1, it.data2 or 0, 0, 0, it.from
end
function scratch:GetFromPlayer() return self.from end
function scratch:GetToPlayer() return self.to end
LOADED = {}
UI = {
  GetScratchDeal = function() return scratch end,
  ProposedDealExists = function(a, b) return PROPOSED[a .. ':' .. b] == true end,
  LoadProposedDeal = function(a, b)
    LOADED[#LOADED + 1] = { a, b }
    scratch.from, scratch.to = a, b
    scratch.items = { { type = 2, data1 = 5, from = a } }
  end,
  HasMadeProposal = function(us) return MADE end,
}
H.enum_name = function(_, _, v) return v == 2 and 'TRADE_ITEM_GOLD_PER_TURN' or 'TRADE_ITEM_RESOURCES' end
"""


class PvpDealReadTests(unittest.TestCase):
    run_lua = support.LuaRuntimeTests.run_lua

    def setUp(self):
        support.LuaRuntimeTests.setUp(self)
        self.run_lua(WORLD)

    def test_turn_status_names_the_proposer(self):
        self.run_lua("""
        assert(H.pending_deal_from(1) == nil)
        PROPOSED['0:1'] = true
        assert(H.pending_deal_from(1) == 0)
        assert(H.pending_deal_from(0) == nil, 'the proposer has nothing pending for itself')
        assert(H.pending_deal_from(2) == nil)
        """)

    def test_incoming_deal_loads_the_pending_proposal_into_the_scratch(self):
        self.run_lua("""
        PROPOSED['0:1'] = true
        local r = H.incoming_deal(1)
        assert(#LOADED == 1 and LOADED[1][1] == 0 and LOADED[1][2] == 1, 'LoadProposedDeal(them, us)')
        assert(r.n == 1 and r.items[1].type == 'GOLD_PER_TURN' and r.items[1].amount == 5 and r.items[1].from_us == false, H.json(r))
        assert(r.pending == true and r.proposed_by == 0 and r.from == 0 and r.to == 1)
        """)

    def test_a_proposal_the_engine_already_loaded_is_still_flagged_pending(self):
        self.run_lua("""
        PROPOSED['0:1'] = true
        SCRATCH.from, SCRATCH.to = 0, 1
        SCRATCH.items = { { type = 2, data1 = 5, from = 0 } }
        local r = H.incoming_deal(1)
        assert(#LOADED == 0, 'nothing reloaded')
        assert(r.pending == true and r.proposed_by == 0, H.json(r))
        """)

    def test_our_own_sent_proposal_reads_as_ours_pending(self):
        self.run_lua("""
        MADE = 1
        SCRATCH.from, SCRATCH.to = 0, 1
        SCRATCH.items = { { type = 2, data1 = 5, from = 0 } }
        local r = H.incoming_deal(0)
        assert(r.ours_pending == true and r.pending == nil and r.proposed_by == nil, H.json(r))
        """)

    def test_a_proposal_that_loads_nothing_is_still_pending_and_refusable(self):
        """GitLab #161: status kept pending_deal_from:1 while the table read came back empty."""
        self.run_lua("""
        PROPOSED['0:1'] = true
        UI.LoadProposedDeal = function(a, b) LOADED[#LOADED + 1] = { a, b } end   -- loads nothing
        finalized = {}
        UI.DoFinalizePlayerDeal = function(them, us, yes) finalized[#finalized + 1] = { them, us, yes } end
        local r = H.incoming_deal(1)
        assert(r.n == 0 and r.pending == true and r.proposed_by == 0, H.json(r))
        local a = H.accept_deal(1)
        assert(a.ok == false, 'nothing readable is never accepted: ' .. H.json(a))
        local d = H.refuse_deal(1)
        assert(d.ok == true and d.other == 0, H.json(d))
        assert(#finalized == 1 and finalized[1][1] == 0 and finalized[1][2] == 1 and finalized[1][3] == false, 'DoFinalizePlayerDeal(them, us, false)')
        -- GitLab #174: a refuse that saw nothing says so and names the sender
        assert(d.unread == true and #d.refused_items == 0 and d.note:find('player 0', 1, true), H.json(d))
        """)

    def test_an_empty_table_with_no_proposal_stays_empty(self):
        self.run_lua("""
        local r = H.incoming_deal(1)
        assert(r.n == 0 and r.pending == nil and r.proposed_by == nil and #LOADED == 0)
        """)


class SharedScratchTableTests(unittest.TestCase):
    """GitLab #172 / #174 (three-seat hotseat, 2026-10-30, t8 and t25): seat 0 proposed to seat 2 only, and the
    proposal stayed on the one scratch deal every seat shares (tradelogic.lua OnPropose: DoProposeDeal, then hide,
    no ClearItems). On seat 1's turn the todo read it as incoming_deal {from: 0, items: 2}, question() had nothing
    to show (no proposal to seat 1 existed), the deals screen said the table was occupied, and the blind refuse
    finalized a 0 -> 1 deal that never was -- "Your offer ... is no longer valid" on seats 0 and 1."""
    run_lua = PvpDealReadTests.run_lua

    def setUp(self):
        support.LuaRuntimeTests.setUp(self)
        self.run_lua(WORLD + """
        for i = 0, 2 do Players[i].IsHuman = function() return true end end
        finalized = {}
        UI.DoFinalizePlayerDeal = function(them, us, yes) finalized[#finalized + 1] = { them, us, yes } end
        UI.GetNumCurrentDeals = function() return 0 end
        UI.LoadCurrentDeal = function() error('nothing to load') end
        -- seat 0's proposal to seat 2, as the closed screen left it
        PROPOSED['0:2'] = true
        SCRATCH.from, SCRATCH.to = 0, 2
        SCRATCH.items = { { type = 2, data1 = 1, from = 0 }, { type = 2, data1 = 1, from = 2 } }
        """)

    def test_another_pairs_table_is_nothing_on_this_seats(self):
        self.run_lua("""
        local r = H.incoming_deal(1)
        assert(r.n == 0 and r.pending == nil and r.proposed_by == nil, H.json(r))
        assert(r.from == nil and r.to == nil, 'the other pair is not named: ' .. H.json(r))
        assert(H.pending_deal_from(1) == nil)
        local d = H.refuse_deal(1)
        assert(d.ok == false and #finalized == 0, 'no deal is finalized for a proposal seat 1 never had: ' .. H.json(d))
        assert(H.accept_deal(1).ok == false and #finalized == 0)
        assert(#SCRATCH.items == 2, 'the copy is left alone by the reads')
        assert(H.current_deals(1).ok == true, 'the deals screen is not blocked by another pair\\'s table')
        """)

    def test_the_recipient_still_reads_and_answers_it(self):
        self.run_lua("""
        local r = H.incoming_deal(2)
        assert(r.n == 2 and r.pending == true and r.proposed_by == 0 and r.from == 0 and r.to == 2, H.json(r))
        local a = H.accept_deal(2)
        assert(a.ok == true and a.other == 0 and #a.accepted_items == 2, 'the accept echoes the items: ' .. H.json(a))
        assert(#finalized == 1 and finalized[1][1] == 0 and finalized[1][2] == 2 and finalized[1][3] == true)
        """)

    def test_the_sender_still_sees_its_own_proposal(self):
        self.run_lua("""
        MADE = 2
        local r = H.incoming_deal(0)
        assert(r.n == 2 and r.ours_pending == true and r.pending == nil, H.json(r))
        """)

    def test_a_proposal_to_this_seat_is_loaded_over_another_pairs_table(self):
        self.run_lua("""
        PROPOSED['2:1'] = true
        local r = H.incoming_deal(1)
        assert(#LOADED == 1 and LOADED[1][1] == 2 and LOADED[1][2] == 1, 'LoadProposedDeal(2, 1): ' .. H.json(LOADED))
        assert(r.n == 1 and r.pending == true and r.proposed_by == 2 and r.from == 2 and r.to == 1, H.json(r))
        local d = H.refuse_deal(1)
        assert(d.ok == true and d.other == 2 and #d.refused_items == 1 and d.unread == nil, 'the refuse echoes the items: ' .. H.json(d))
        assert(finalized[1][1] == 2 and finalized[1][2] == 1 and finalized[1][3] == false)
        """)

    def test_a_human_table_whose_proposal_is_gone_is_not_an_offer(self):
        self.run_lua("""
        PROPOSED['0:2'] = nil
        SCRATCH.to = 1   -- a copy of seat 0's table to seat 1, but the engine holds no such proposal
        local r = H.incoming_deal(1)
        assert(r.n == 0 and r.pending == nil, H.json(r))
        assert(H.refuse_deal(1).ok == false and #finalized == 0)
        -- an AI's offer is on the table without a proposal record (its screen carries it)
        Players[0].IsHuman = function() return false end
        r = H.incoming_deal(1)
        assert(r.n == 2 and r.from == 0, H.json(r))
        """)


if __name__ == "__main__":
    unittest.main()
