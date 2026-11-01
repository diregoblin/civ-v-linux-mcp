-- Shared by earlier fragments (load order: harness/runtime_source.py MANIFEST).
local L = H._ns.L

-- The social policy screen as the player sees it: adopted policies, policies adoptable right now,
-- branches with unlocked / can-unlock flags, and whether a policy is affordable this turn.
function H.available_policies(pid)
  local p = Players[pid]
  local out = { adopted = {}, adoptable = {}, branches = {}, culture = p:GetJONSCulture(),
                next_policy_cost = p:GetNextPolicyCost(), free_policies = p:GetNumFreePolicies(),
                free_tenets = p.GetNumFreeTenets and p:GetNumFreeTenets() or 0 }
  -- v260: the screen's tenet buttons light up for culture, a free policy OR a free tenet (socialpolicypopup.lua
  -- 575/608/645, the "Free Tenets" label beside them); the two tenets an ideology grants were invisible here
  -- (live t173, Mongolia: free_policies 0, can_adopt_now false, choose_policy said can_adopt_another false
  -- while the second tenet was still owed and ENDTURN_BLOCKING_FREE_POLICY stood). A free tenet buys only a
  -- tenet of the adopted ideology, never an ordinary policy: `tenets_only` says when that is all there is.
  local affordable = out.free_policies > 0 or out.culture >= out.next_policy_cost
  out.can_adopt_now = affordable or out.free_tenets > 0
  out.tenets_only = (not affordable and out.free_tenets > 0) or nil
  for b in GameInfo.PolicyBranchTypes() do
    local blocked = false
    if p.IsPolicyBranchBlocked then blocked = p:IsPolicyBranchBlocked(b.ID) end
    local finished = false
    if p.IsPolicyBranchFinished then finished = p:IsPolicyBranchFinished(b.ID) end
    -- The engine's CanUnlockPolicyBranch stays true for a branch already unlocked (live Doge t215);
    -- the screen shows no unlock button there, so the row says so too.
    local unlocked = p:IsPolicyBranchUnlocked(b.ID)
    out.branches[#out.branches + 1] = { branch = b.Type, unlocked = unlocked,
      can_unlock = (not unlocked) and p:CanUnlockPolicyBranch(b.ID) or false, blocked = blocked, finished = finished,
      era = b.EraPrereq, ideology = b.PurchaseByLevel or false }
  end
  local open = {}
  for _, b in ipairs(out.branches) do if b.unlocked and not b.finished then open[b.branch] = true end end
  out.locked = {}
  for pol in GameInfo.Policies() do
    local branch = pol.PolicyBranchType
    if p:HasPolicy(pol.ID) then
      out.adopted[#out.adopted + 1] = { policy = pol.Type, branch = branch }
    elseif p:CanAdoptPolicy(pol.ID, true) then  -- true: ignore the culture cost, list what the tree offers next
      out.adoptable[#out.adoptable + 1] = { policy = pol.Type, branch = branch, name = L(pol.Description) }
    elseif open[branch] and not (pol.Level and pol.Level > 0) then
      -- GitLab #123 (Siam t14, t21): the rest of an open branch was invisible, and the agent took its absence
      -- for a bug. The engine's tree: BNW's Legalism needs Oligarchy; Landed Elite and Monarchy need Legalism
      -- (Policy_PrereqPolicies). Each locked policy says what it still needs.
      local needs = {}
      pcall(function()
        for r in GameInfo.Policy_PrereqPolicies{ PolicyType = pol.Type } do
          if r.PolicyType == pol.Type and r.PrereqPolicy then
            local pre = GameInfo.Policies[r.PrereqPolicy]
            if not (pre and p:HasPolicy(pre.ID)) then needs[#needs + 1] = r.PrereqPolicy end
          end
        end
      end)
      out.locked[#out.locked + 1] = { policy = pol.Type, branch = branch, name = L(pol.Description), needs = needs }
    end
  end
  if #out.locked > 0 then
    out.locked_note = "the policies of an open branch not offered yet, with the policies they need first (the engine's tree)"
  else
    out.locked = nil
  end
  local oki, ideologies = pcall(H.ideologies, pid)
  if oki and ideologies then
    out.ideologies = ideologies.rows
    out.ideology = ideologies.mine
    out.ideology_choice_open = ideologies.choice_open or nil
    out.ideologies_note = ideologies.locked_note
  end
  return out
end

-- The ideology choice as chooseideologypopup.lua and the diplomacy overview show it (GitLab #145, Maya t217: the
-- policies read gave three flag rows for the biggest choice of the game). Per ideology: the met civs that follow
-- it (Player:GetLateGamePolicyTree is public; the opinion table says "You have both chosen to adopt ..."), each
-- marked friend / denounced / at_war as the overview does; the early-adopter free tenets the popup prints
-- (Game.GetNumFreePolicies(branch)); and, while the choice is still open, the tier-1 tenets with their text.
-- `mine` is the seat's own ideology; `choice_open` says the engine is asking for one now.
-- GitLab #179 (Celts t7, Ancient era): the tenets' text rode on every policy read of the game, a few thousand
-- characters, while the ideologies could not be taken. The engine asks for one once three Factories stand or the
-- Modern era begins (ENDTURN_BLOCKING_CHOOSE_IDEOLOGY), and every ideology branch names the era it opens in
-- (EraPrereq, ERA_INDUSTRIAL). Before that era, with the choice not asked, a row is the ideology's name, `era`,
-- `locked` and its followers; from that era on, while no ideology is mine, the early-adopter count and the tier-1
-- tenets to plan by.
local function era_reached(p, era_type)
  if not era_type then return true end
  local ok, reached = pcall(function() return p:GetCurrentEra() >= GameInfo.Eras[era_type].ID end)
  return ok and reached == true
end

function H.ideologies(pid)
  local p = Players[pid]
  if not (p and p.GetLateGamePolicyTree) then return nil end
  local branches = {}
  for b in GameInfo.PolicyBranchTypes() do
    if b.PurchaseByLevel then branches[#branches + 1] = b end
  end
  if #branches == 0 then return nil end
  local have = p:GetLateGamePolicyTree()
  local mine = (have and have >= 0) and GameInfo.PolicyBranchTypes[have].Type or nil
  local choice_open = false
  pcall(function()
    choice_open = (mine == nil) and H.blocking_name(p:GetEndTurnBlockingType()) == "ENDTURN_BLOCKING_CHOOSE_IDEOLOGY"
  end)
  -- Followers: every met, living major with an ideology, under its branch.
  local followers = {}
  pcall(function()
    local myTeam = Teams[p:GetTeam()]
    local last = (GameDefines.MAX_MAJOR_CIVS or 22) - 1
    for other = 0, last do
      local o = Players[other]
      if other ~= pid and o and o:IsAlive() and not (o.IsMinorCiv and o:IsMinorCiv()) and myTeam:IsHasMet(o:GetTeam()) then
        local tree = o.GetLateGamePolicyTree and o:GetLateGamePolicyTree() or -1
        if tree and tree >= 0 then
          local row = { player_id = other, civ = o:GetCivilizationShortDescription() }
          pcall(function() if p:IsDoF(other) then row.friend = true end end)
          pcall(function() if o:IsDenouncedPlayer(pid) then row.denounced_us = true end end)
          pcall(function() if p:IsDenouncedPlayer(other) then row.we_denounced = true end end)
          pcall(function() if myTeam:IsAtWar(o:GetTeam()) then row.at_war = true end end)
          followers[tree] = followers[tree] or {}
          table.insert(followers[tree], row)
        end
      end
    end
  end)
  local rows, locked = {}, false
  for _, b in ipairs(branches) do
    local row = { branch = b.Type, name = L(b.Description), followers = followers[b.ID] or {} }
    if mine == b.Type then row.mine = true end
    if mine == nil and not choice_open and not era_reached(p, b.EraPrereq) then
      row.era, row.locked, locked = b.EraPrereq, true, true
    else
      pcall(function() row.free_tenets_on_adopt = Game.GetNumFreePolicies(b.ID) end)
    end
    if mine == nil and not row.locked then
      local tenets = {}
      pcall(function()
        for pol in GameInfo.Policies{ PolicyBranchType = b.Type } do
          if pol.Level == 1 then tenets[#tenets + 1] = { policy = pol.Type, name = L(pol.Description), help = L(pol.Help) } end
        end
      end)
      if #tenets > 0 then row.tenets = tenets end
    end
    rows[#rows + 1] = row
  end
  return { rows = rows, mine = mine, choice_open = choice_open,
           locked_note = locked and "an ideology is chosen once 3 Factories stand or the Modern era begins; its tenets show from its era on" or nil }
end
