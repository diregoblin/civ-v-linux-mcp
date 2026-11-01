"""The ideology choice is explained in one read (GitLab #145): per ideology its followers among the met civs, the
early-adopter free tenets and the tier-1 tenets, each row with its adopt call while the engine asks; civs rows carry
`ideology`. Maya t217: the policies read gave three flag rows -- no followers, no tenets -- for the biggest single
choice of the game."""
import unittest

import test_mcp_safety as support
from harness.affordances import policy_rows


WORLD = r"""
local function iter(rows, filter)
  local i, key, want = 0, nil, nil
  if type(filter) == 'table' then for k, v in pairs(filter) do key, want = k, v end end
  return function()
    while true do
      i = i + 1
      local r = rows[i]
      if r == nil then return nil end
      if key == nil or r[key] == want then return r end
    end
  end
end
BRANCHES = {
  { ID = 1, Type = 'POLICY_BRANCH_TRADITION', Description = 'TXT_TRADITION' },
  { ID = 9, Type = 'POLICY_BRANCH_FREEDOM', Description = 'TXT_FREEDOM', PurchaseByLevel = true, EraPrereq = 'ERA_INDUSTRIAL' },
  { ID = 10, Type = 'POLICY_BRANCH_ORDER', Description = 'TXT_ORDER', PurchaseByLevel = true, EraPrereq = 'ERA_INDUSTRIAL' },
  { ID = 11, Type = 'POLICY_BRANCH_AUTOCRACY', Description = 'TXT_AUTOCRACY', PurchaseByLevel = true, EraPrereq = 'ERA_INDUSTRIAL' },
}
POLICIES = {
  { ID = 1, Type = 'POLICY_ARISTOCRACY', PolicyBranchType = 'POLICY_BRANCH_TRADITION', Description = 'TXT_ARISTO', Help = 'TXT_ARISTO_H' },
  { ID = 50, Type = 'POLICY_OPEN_SOCIETY', PolicyBranchType = 'POLICY_BRANCH_FREEDOM', Level = 1, Description = 'TXT_AVANT', Help = 'TXT_AVANT_H' },
  { ID = 51, Type = 'POLICY_CIVIL_SOCIETY', PolicyBranchType = 'POLICY_BRANCH_FREEDOM', Level = 2, Description = 'TXT_CIVIL', Help = 'TXT_CIVIL_H' },
  { ID = 60, Type = 'POLICY_HERO_OF_THE_PEOPLE', PolicyBranchType = 'POLICY_BRANCH_ORDER', Level = 1, Description = 'TXT_HERO', Help = 'TXT_HERO_H' },
  { ID = 70, Type = 'POLICY_ELITE_FORCES', PolicyBranchType = 'POLICY_BRANCH_AUTOCRACY', Level = 1, Description = 'TXT_ELITE', Help = 'TXT_ELITE_H' },
}
GameInfo = {
  PolicyBranchTypes = setmetatable({ [1] = BRANCHES[1], [9] = BRANCHES[2], [10] = BRANCHES[3], [11] = BRANCHES[4] },
                                   { __call = function(_, f) return iter(BRANCHES, f) end }),
  Policies = setmetatable({}, { __call = function(_, f) return iter(POLICIES, f) end }),
}
Locale = { ConvertTextKey = function(k) return 'txt:' .. tostring(k) end }
GameDefines = { MAX_MAJOR_CIVS = 4 }
FREE = { [9] = 2, [10] = 1, [11] = 0 }
Game.GetNumFreePolicies = function(id) return FREE[id] end
EndTurnBlockingTypes = { ENDTURN_BLOCKING_CHOOSE_IDEOLOGY = 7, NO_ENDTURN_BLOCKING_TYPE = -1 }
BLOCKER = 7
local function player(id, tree, opts)
  opts = opts or {}
  return {
    GetTeam = function() return id end, IsAlive = function() return opts.alive ~= false end, IsMinorCiv = function() return opts.minor == true end,
    GetCivilizationShortDescription = function() return opts.civ or ('Civ' .. id) end,
    GetLateGamePolicyTree = function() return tree end,
    IsDoF = function(_, other) return opts.dof == other end,
    IsDenouncedPlayer = function(_, other) return opts.denounced == other end,
    GetEndTurnBlockingType = function() return BLOCKER end,
    -- what available_policies itself reads
    GetJONSCulture = function() return 500 end, GetNextPolicyCost = function() return 900 end,
    GetNumFreePolicies = function() return 0 end, GetNumFreeTenets = function() return 0 end,
    IsPolicyBranchUnlocked = function() return false end, CanUnlockPolicyBranch = function() return false end,
    HasPolicy = function() return false end, CanAdoptPolicy = function() return false end,
  }
end
MET = { [1] = true, [2] = true, [3] = false }
Teams = { [0] = { IsHasMet = function(_, t) return MET[t] == true end, IsAtWar = function(_, t) return t == 2 end } }
Players = {
  [0] = player(0, -1, { dof = 1, denounced = 2 }),
  [1] = player(1, 10, { civ = 'Assyria' }),     -- Order, our friend
  [2] = player(2, 10, { civ = 'Venice', denounced = 0 }),  -- Order, denounced us, at war
  [3] = player(3, 11, { civ = 'Byzantium' }),   -- Autocracy, never met: not listed
}
"""


class IdeologyChoiceLuaTests(unittest.TestCase):
    run_lua = support.LuaRuntimeTests.run_lua
    load_runtime = support.LuaRuntimeTests.load_runtime

    def setUp(self):
        support.LuaRuntimeTests.setUp(self)

    def test_the_policies_read_explains_the_choice(self):
        self.run_lua(WORLD)
        self.run_lua(r"""
local r = H.available_policies(0)
assert(r.ideology == nil and r.ideology_choice_open == true, H.json(r))
assert(#r.ideologies == 3, 'the three ideologies, not Tradition: ' .. H.json(r.ideologies))
local by = {}
for _, row in ipairs(r.ideologies) do by[row.branch] = row end
local order = by.POLICY_BRANCH_ORDER
assert(order.name == 'txt:TXT_ORDER' and order.free_tenets_on_adopt == 1, H.json(order))
assert(#order.followers == 2, 'two met followers: ' .. H.json(order.followers))
assert(order.followers[1].civ == 'Assyria' and order.followers[1].friend == true and order.followers[1].denounced_us == nil)
assert(order.followers[2].civ == 'Venice' and order.followers[2].denounced_us == true and order.followers[2].we_denounced == true
       and order.followers[2].at_war == true, H.json(order.followers[2]))
assert(#by.POLICY_BRANCH_AUTOCRACY.followers == 0, 'an unmet follower is not listed (the overview does not show it)')
assert(by.POLICY_BRANCH_FREEDOM.free_tenets_on_adopt == 2 and by.POLICY_BRANCH_AUTOCRACY.free_tenets_on_adopt == 0)
assert(#by.POLICY_BRANCH_FREEDOM.tenets == 1 and by.POLICY_BRANCH_FREEDOM.tenets[1].policy == 'POLICY_OPEN_SOCIETY'
       and by.POLICY_BRANCH_FREEDOM.tenets[1].help == 'txt:TXT_AVANT_H', 'tier 1 only, with its text: ' .. H.json(by.POLICY_BRANCH_FREEDOM.tenets))
""")

    def test_after_the_choice_the_rows_shrink_to_followers(self):
        self.run_lua(WORLD)
        self.run_lua(r"""
Players[0].GetLateGamePolicyTree = function() return 10 end
BLOCKER = -1
local r = H.available_policies(0)
assert(r.ideology == 'POLICY_BRANCH_ORDER' and r.ideology_choice_open == nil, H.json(r))
local by = {}
for _, row in ipairs(r.ideologies) do by[row.branch] = row end
assert(by.POLICY_BRANCH_ORDER.mine == true and by.POLICY_BRANCH_FREEDOM.mine == nil)
assert(by.POLICY_BRANCH_FREEDOM.tenets == nil, 'the tenets are the adoptable / locked rows once chosen')
assert(#by.POLICY_BRANCH_ORDER.followers == 2, 'followers stay: the pressure the others put on me')
""")

    def test_before_the_ideology_era_the_rows_are_names_only(self):
        """GitLab #179 (Celts t7, Ancient era): every tier-1 tenet's text rode on the policy read, a few thousand
        characters, while the ideologies were locked to ERA_INDUSTRIAL and only Tradition could be taken."""
        self.run_lua(WORLD)
        self.run_lua(r"""
BLOCKER = -1
ERA = 0
GameInfo.Eras = { ERA_ANCIENT = { ID = 0 }, ERA_INDUSTRIAL = { ID = 4 } }
Players[0].GetCurrentEra = function() return ERA end
Players[1].GetLateGamePolicyTree = function() return -1 end
Players[2].GetLateGamePolicyTree = function() return -1 end
local r = H.available_policies(0)
assert(r.ideology_choice_open == nil and #r.ideologies == 3, H.json(r))
for _, row in ipairs(r.ideologies) do
  assert(row.tenets == nil and row.free_tenets_on_adopt == nil, 'no tenet text before the era: ' .. H.json(row))
  assert(row.locked == true and row.era == 'ERA_INDUSTRIAL' and row.name and #row.followers == 0, H.json(row))
end
assert(r.ideologies_note:find('3 Factories', 1, true), H.json(r))
assert(#H.json(r.ideologies) < 400, 'three short rows: ' .. #H.json(r.ideologies))
-- the Industrial era reached, the choice not asked yet (fewer than three Factories): the tenets to plan by
ERA = 4
r = H.available_policies(0)
assert(r.ideologies_note == nil and r.ideology_choice_open == nil, H.json(r))
for _, row in ipairs(r.ideologies) do
  assert(row.locked == nil and row.era == nil and row.tenets and row.free_tenets_on_adopt, H.json(row))
end
""")

    def test_the_choice_asked_shows_the_tenets_whatever_the_era_reads(self):
        """The engine's own question wins: ENDTURN_BLOCKING_CHOOSE_IDEOLOGY up means the choice is now (#145)."""
        self.run_lua(WORLD)
        self.run_lua(r"""
GameInfo.Eras = { ERA_INDUSTRIAL = { ID = 4 } }
Players[0].GetCurrentEra = function() return 0 end
local r = H.available_policies(0)
assert(r.ideology_choice_open == true and r.ideologies_note == nil, H.json(r))
for _, row in ipairs(r.ideologies) do assert(row.tenets and not row.locked, H.json(row)) end
""")

    def test_a_blocker_that_is_not_the_choice_leaves_the_choice_closed(self):
        self.run_lua(WORLD)
        self.run_lua(r"""
BLOCKER = -1
assert(H.available_policies(0).ideology_choice_open == nil)
""")

    def test_civs_rows_carry_the_ideology(self):
        self.run_lua(WORLD)
        self.run_lua(r"""
Players[1].IsEverAlive = function() return true end; Players[1].IsHuman = function() return false end
Players[1].GetName = function() return 'Ashurbanipal' end; Players[1].GetScore = function() return 300 end
Players[1].GetCapitalCity = function() return nil end
Players[2].IsEverAlive = function() return true end; Players[2].IsHuman = function() return false end
Players[2].GetName = function() return 'Dandolo' end; Players[2].GetScore = function() return 200 end
Players[2].GetLateGamePolicyTree = function() return -1 end
Players[2].GetCapitalCity = function() return nil end
Players[3].IsEverAlive = function() return true end
GameDefines.MAX_CIV_PLAYERS = 4
local rows = H.diplomacy(0)
assert(#rows == 2, H.json(rows))
assert(rows[1].civ == 'Assyria' and rows[1].ideology == 'POLICY_BRANCH_ORDER', H.json(rows[1]))
assert(rows[2].civ == 'Venice' and rows[2].ideology == nil, 'no ideology yet, no field')
""")

    def test_an_engine_without_ideologies_keeps_the_old_read(self):
        """The available_policies mocks of the older tests (no PurchaseByLevel branch, no Teams) still answer."""
        self.run_lua(r"""
GameInfo = { PolicyBranchTypes = function() return function() end end, Policies = function() return function() end end }
Players = { [0] = { GetJONSCulture = function() return 200 end, GetNextPolicyCost = function() return 1005 end,
  GetNumFreePolicies = function() return 0 end, IsPolicyBranchUnlocked = function() return false end,
  CanUnlockPolicyBranch = function() return false end } }
local r = H.available_policies(0)
assert(r.ideologies == nil and r.ideology == nil and r.ideology_choice_open == nil, H.json(r))
""")


class IdeologyRowsTests(unittest.TestCase):
    def test_each_ideology_carries_its_adopt_call_while_the_engine_asks(self):
        reply = {"ok": True, "adoptable": [], "branches": [], "ideology_choice_open": True,
                 "ideologies": [{"branch": "POLICY_BRANCH_FREEDOM", "followers": []}, {"branch": "POLICY_BRANCH_ORDER", "followers": []}]}
        out = policy_rows(reply)
        self.assertEqual(out["ideologies"][1]["call"],
                         {"tool": "order", "args": {"to": "empire", "action": "ideology", "args": {"branch": "POLICY_BRANCH_ORDER"}}})

    def test_no_call_once_chosen_or_before_the_engine_asks(self):
        reply = {"ok": True, "adoptable": [], "branches": [], "ideology": "POLICY_BRANCH_ORDER",
                 "ideologies": [{"branch": "POLICY_BRANCH_ORDER", "mine": True, "followers": []}]}
        self.assertNotIn("call", policy_rows(reply)["ideologies"][0])


if __name__ == "__main__":
    unittest.main()
