-- Shared by earlier fragments (load order: harness/runtime_source.py MANIFEST).
local info_type, plain_text, short = H._ns.info_type, H._ns.plain_text, H._ns.short

-- Deals go through the real trade screen from Python (Game.propose_deal drives LeaderHeadRoot.OnTrade,
-- tradelogic.lua's pocket handlers and OnPropose). There is no headless path here any more: the one that
-- built a scratch deal with the per-item Add* calls and UI.DoProposeDeal() crashed the game natively eight
-- times (2026-09-16, docs/NOTES.md "Phase 3a") and was retired 2026-09-17; its body stayed in this file as a
-- reference until 2026-10-08 (runtime v264) and is in git history. What it taught, so nobody rediscovers it:
--   * every Add* must be gated by the same deal:IsPossibleToTradeItem(from, to, TRADE_ITEM_*, ...) call
--     tradelogic.lua makes before showing a pocket button; H.trade_catalog below makes exactly those calls;
--   * IsPossibleToTradeItem for TRADE_ITEM_DECLARATION_OF_FRIENDSHIP against an AI recipient crashes natively
--     (tradelogic.lua only handles it when g_bPVPTrade; an AI's friendship is a diplo_event, not a deal item);
--   * deal:AddPeaceTreaty crashes natively even as the real UI's paired (us, them) call; peace is made
--     through the trade screen, which seeds the treaty on both sides itself (Game.make_peace), never a built deal.

-- One deal object's items (scratch or a LoadCurrentDeal snapshot). Read-only: no Add*/ClearItems.
-- GetNextItem's third value is the turn the timed item ends (diplocurrentdeals.lua "ENDS ON").
function H.deal_items(deal, pid)
  local items = {}
  if not (deal and deal.ResetIterator and deal.GetNextItem) then return items end
  -- v259: an item's own from-player can name a third civ (live t162 Mongolia: Catherine's renewal offer, deal
  -- from 1 to 7, carried England's id 2 on her open borders and gold per turn). The trade screen places an item
  -- by "ours or not", so the giver of anything not ours is the deal's other player; the raw id rides along as
  -- `from_engine` only when it differs.
  local other
  pcall(function() other = deal.GetOtherPlayer and deal:GetOtherPlayer(pid) or nil end)
  if type(other) ~= "number" or other < 0 then other = nil end
  deal:ResetIterator()
  local itemType, duration, finalTurn, data1, data2, data3, flag1, fromPlayer = deal:GetNextItem()
  local turn = Game and Game.GetGameTurn and Game.GetGameTurn() or nil
  while itemType ~= nil do
    local name = H.enum_name("TradeableItems", TradeableItems, itemType)
    if type(name) == "string" then name = name:gsub("^TRADE_ITEM_", "") end
    local e = { type = name, from = fromPlayer, from_us = fromPlayer == pid, duration = duration }
    if not e.from_us and other and fromPlayer ~= other then e.from, e.from_engine = other, fromPlayer end
    if type(finalTurn) == "number" and finalTurn > 0 then
      e.final_turn = finalTurn
      if type(turn) == "number" then e.turns_left = finalTurn - turn end
    end
    if name == "GOLD" or name == "GOLD_PER_TURN" then
      e.amount = data1
    elseif name == "RESOURCES" then
      e.resource = GameInfo and short(info_type(GameInfo.Resources, data1)) or data1
      e.amount = data2
      -- what giving it costs us (renewal offers name a resource trade_catalog no longer lists because
      -- it is still under the expiring deal; live t292 America's Dye renewal). Same numbers the
      -- top bar / trade screen show a human.
      if e.from_us and Players and Players[pid] then
        local pl, info = Players[pid], GameInfo and GameInfo.Resources and GameInfo.Resources[data1] or nil
        local function num(f) local okc, v = pcall(function() return pl[f](pl, data1, true) end) if okc and type(v) == "number" then return v end return nil end
        local function num1(f) local okc, v = pcall(function() return pl[f](pl, data1) end) if okc and type(v) == "number" then return v end return nil end
        e.class = info and info.ResourceClassType or nil
        e.us_total, e.us_available = num("GetNumResourceTotal"), num("GetNumResourceAvailable")
        e.us_imported, e.us_exported = num1("GetResourceImport"), num1("GetResourceExport")
        -- GetNumResourceTotal is already net of exports (live t292: Copper total 1, exported 2,
        -- available 1 = three copies owned, two under deals). us_owned undoes that so a renewal of an
        -- existing export is not mistaken for selling our only copy.
        if e.us_total then e.us_owned = e.us_total - (e.us_imported or 0) + (e.us_exported or 0) end
        if e.class == "RESOURCECLASS_LUXURY" and e.us_owned and e.us_owned <= (e.amount or 1) then
          e.last_copy = true
          e.note = "our only copy: exporting it removes its happiness from the empire"
        elseif e.us_available and e.us_available < (e.amount or 1) then
          e.note = "no spare copy: either this renews an export already counted in us_exported (no change), or it takes a copy we use"
        end
      elseif Players and Players[pid] then
        -- what receiving it gives us: a luxury we already have adds no happiness (live t444: Venice offered
        -- Spices for Copper and nothing said whether Spices was new). Our own count, as the top bar shows.
        local pl, info = Players[pid], GameInfo and GameInfo.Resources and GameInfo.Resources[data1] or nil
        e.class = info and info.ResourceClassType or nil
        local okc, have = pcall(function() return pl:GetNumResourceAvailable(data1, true) end)
        local oki, imp = pcall(function() return pl:GetResourceImport(data1) end)
        if okc and type(have) == "number" then
          e.us_have = have
          if oki and type(imp) == "number" then e.us_imported = imp end
          if e.class == "RESOURCECLASS_LUXURY" then
            -- v280: a renewal offer of the very import that gives us our only copy read "we already have this
            -- luxury: no extra happiness" (live Assyria t172, Portugal's Truffles for our Salt): the copy we have IS
            -- this deal's, and letting it lapse loses the happiness.
            local own = have - ((oki and type(imp) == "number") and imp or 0)
            if have <= 0 then
              e.note = "new luxury for us: adds its happiness"
            elseif own > 0 then
              e.note = "we already have this luxury: no extra happiness"
            else
              e.note = "our only copy of this luxury is an import: renewing the deal that brings it keeps its happiness, a second import adds none"
            end
          end
        end
      end
    elseif name == "CITIES" then
      -- The deal screen (tradelogic.lua DisplayDeal) names the city and shows its population, never
      -- its coordinates. data1/data2 are the plot; they are the item's identity for us, but they only
      -- reach the row once the plot is revealed to this seat -- the same gate trade_catalog applies.
      -- Until v191 they were copied unconditionally, so a deal could place a city we had never seen
      -- (GitLab #2).
      local owner = Players and Players[fromPlayer]
      if owner and owner.Cities then
        for c in owner:Cities() do
          if c:GetX() == data1 and c:GetY() == data2 then
            e.name, e.city_id = c:GetName(), c:GetID()
            local okp, pop = pcall(function() return c:GetPopulation() end)
            if okp and type(pop) == "number" then e.pop = pop end
            break
          end
        end
      end
      local revealed = false
      if Map and Map.GetPlot and Players and Players[pid] then
        pcall(function()
          local plot = Map.GetPlot(data1, data2)
          revealed = plot and plot:IsRevealed(Players[pid]:GetTeam(), false) or false
        end)
      end
      if revealed then e.x, e.y = data1, data2 end
    elseif name == "THIRD_PARTY_PEACE" or name == "THIRD_PARTY_WAR" then
      -- tradelogic.lua LeaderSelected: AddThirdPartyWar/Peace(who, otherTEAM); DisplayOtherPlayerItem then
      -- shows that team's leader button. data1 is the team; `other` is the player the screen names
      -- (until v199 the raw team id was reported as `other`, which is a player id only by luck; GitLab #6).
      e.team = data1
      if H.third_party_player then
        local okp, who = pcall(H.third_party_player, data1)
        if okp and type(who) == "table" then for k, v in pairs(who) do e[k] = v end end
      end
    elseif name == "VOTE_COMMITMENT" then
      -- tradelogic.lua DisplayDeal: data1 resolution id, data2 the voter choice, data3 the votes
      -- committed, flag1 repeal (GetLeagueVoteIndexFromData). Until v198 all four were dropped, so an
      -- incoming commitment was a bare type name (GitLab #7). The screen labels it with the resolution's
      -- name and the choice text; the same words go on the row when the league still lists the proposal.
      local repeal = (flag1 == true or flag1 == 1)
      e.resolution_id, e.choice_id, e.votes, e.repeal = data1, data2, data3, repeal
      if H.describe_vote_commitment then
        local okv, d = pcall(H.describe_vote_commitment, data1, data2, repeal)
        if okv and type(d) == "table" then for k, v in pairs(d) do e[k] = v end end
      end
    end
    items[#items + 1] = e
    itemType, duration, finalTurn, data1, data2, data3, flag1, fromPlayer = deal:GetNextItem()
  end
  return items
end

-- Read the current scratch deal WITHOUT Add*/ClearItems/DoProposeDeal.
-- tradelogic.lua DisplayDeal() iterates with ResetIterator + GetNextItem; that is a
-- read of whatever is already on the table (empty, our draft, or an AI offer).
-- The seat that has a deal proposal waiting for us (UI.ProposedDealExists(them, us)), or nil. The
-- stock game announces it with a notification whose click opens the PvP deal screen; turn_status
-- names the proposer so the seat knows to read incoming_deal (GitLab #4).
function H.pending_deal_from(pid)
  if not (UI and UI.ProposedDealExists) then return nil end
  local max = (GameDefines and GameDefines.MAX_MAJOR_CIVS) or 22
  for i = 0, max - 1 do
    local okp, exists = pcall(function() return i ~= pid and Players[i] and UI.ProposedDealExists(i, pid) end)
    if okp and exists then return i end
  end
  return nil
end

-- Whether the scratch deal is a table this seat has no part in. Every seat of a hotseat game shares one scratch
-- deal, and a proposal one human seat sends another stays on it after the screen closes (tradelogic.lua OnPropose:
-- DoProposeDeal, then SetHide with no ClearItems; the stock screen clears or reloads the table in
-- OnOpenPlayerDealScreen before a seat sees it). GitLab #172 / #174: seat 0's proposal to seat 2 read on seat 1's
-- turn as an offer from seat 0 -- a seat 1 had not even met -- that question() could not show, and the blind
-- refuse finalized a 0 -> 1 deal that never was ("Your offer ... is no longer valid" on both seats). Foreign: a
-- table between two other players, or a human's table to this seat whose proposal the engine no longer holds.
function H.foreign_table(deal, pid)
  local okf, from = pcall(function() return deal:GetFromPlayer() end)
  local okt, to = pcall(function() return deal:GetToPlayer() end)
  if not (okf and okt) or type(from) ~= "number" or type(to) ~= "number" or from < 0 or to < 0 then return false end
  if from ~= pid and to ~= pid then return true end
  if from == pid or not UI.ProposedDealExists then return false end
  local okh, human = pcall(function() return Players[from]:IsHuman() end)
  if not (okh and human) then return false end
  local okp, held = pcall(function() return UI.ProposedDealExists(from, pid) end)
  return okp and not held
end

function H.incoming_deal(pid)
  if not UI or not UI.GetScratchDeal then
    return { ok = true, items = {}, n = 0 }
  end
  local ok, deal = pcall(function() return UI.GetScratchDeal() end)
  if not ok or deal == nil then return { ok = true, items = {}, n = 0 } end
  -- Another pair's table reads as an empty one: nothing on it is this seat's, and its parties are not named.
  local items = H.foreign_table(deal, pid) and {} or H.deal_items(deal, pid)
  local proposed_by
  if #items == 0 and UI.ProposedDealExists and UI.LoadProposedDeal then
    -- A proposal from another human seat is not on the scratch table until the deal screen loads it
    -- (tradelogic.lua OnOpenPlayerDealScreen: ProposedDealExists(them, us) -> LoadProposedDeal). Do
    -- the same so the receiving seat can read it, then accept_deal / refuse_deal (GitLab #4).
    local max = (GameDefines and GameDefines.MAX_MAJOR_CIVS) or 22
    for i = 0, max - 1 do
      local okp, exists = pcall(function() return i ~= pid and Players[i] and UI.ProposedDealExists(i, pid) end)
      if okp and exists then
        pcall(function() UI.LoadProposedDeal(i, pid) end)
        items = H.deal_items(deal, pid)
        proposed_by = i
        break
      end
    end
  end
  -- The parties are those of the items read, or of the proposal that loaded none (#161); an empty table's
  -- leftover counterpart is nobody's offer.
  local from, to
  if #items > 0 then
    from = deal.GetFromPlayer and deal:GetFromPlayer() or nil
    to = deal.GetToPlayer and deal:GetToPlayer() or nil
  elseif proposed_by ~= nil then
    from, to = proposed_by, pid
  end
  -- The engine may already have loaded another seat's proposal into the scratch (live t227: Bravo's
  -- table held Alpha's three items before anything asked for them); it is still their pending offer.
  if proposed_by == nil and #items > 0 and type(from) == "number" and from ~= pid and UI.ProposedDealExists then
    local okp, exists = pcall(function() return UI.ProposedDealExists(from, pid) end)
    if okp and exists then proposed_by = from end
  end
  local ours_pending
  if type(from) == "number" and from == pid and UI.HasMadeProposal then
    local okh, made = pcall(function() return UI.HasMadeProposal(pid) end)
    if okh and made == to then ours_pending = true end
  end
  return { ok = true, items = items, n = #items, from = from, to = to, proposed_by = proposed_by,
           pending = proposed_by ~= nil or nil, ours_pending = ours_pending }
end

-- Diplomacy Overview "Current Deals" tab (diplocurrentdeals.lua PopulateDealChooser).
-- Stock loads each row into the scratch deal via UI.LoadCurrentDeal. That is the same object
-- propose_deal / incoming_deal use, so this refuses when the table already has items and
-- ClearItems afterwards so a leftover current-deal does not look like an incoming offer.
-- Never Add* / DoProposeDeal.
function H.current_deals(pid)
  if not UI or not UI.GetNumCurrentDeals or not UI.LoadCurrentDeal then
    return { ok = false, err = "current-deals UI unavailable", deals = {}, n = 0 }
  end
  local scratch = H.incoming_deal(pid)
  if (scratch.n or 0) > 0 then
    return { ok = false, err = "trade table is occupied; answer the incoming deal first (question(), then answer(choice='accept' / 'refuse'))", deals = {}, n = 0 }
  end
  local okn, n = pcall(function() return UI.GetNumCurrentDeals(pid) end)
  if not okn or type(n) ~= "number" or n <= 0 then
    return { ok = true, deals = {}, n = 0 }
  end
  local okd, deal = pcall(function() return UI.GetScratchDeal() end)
  if not okd or deal == nil then
    return { ok = false, err = "no scratch deal to snapshot current deals into", deals = {}, n = 0 }
  end
  local turn = Game and Game.GetGameTurn and Game.GetGameTurn() or 0
  local out = {}
  for i = 0, n - 1 do
    local okl = pcall(function() UI.LoadCurrentDeal(pid, i) end)
    if okl then
      local items = H.deal_items(deal, pid)
      local other
      pcall(function() other = deal:GetOtherPlayer(pid) end)
      local start_turn, duration
      pcall(function() start_turn = deal:GetStartTurn() end)
      pcall(function() duration = deal:GetDuration() end)
      local ends_on
      if type(start_turn) == "number" and type(duration) == "number" then
        ends_on = start_turn + duration
      end
      local civ
      if other and Players and Players[other] and Players[other].GetCivilizationShortDescription then
        local met = true
        if Teams and Players[pid] then
          pcall(function() met = Teams[Players[pid]:GetTeam()]:IsHasMet(Players[other]:GetTeam()) end)
        end
        if met then civ = Players[other]:GetCivilizationShortDescription() end
      end
      local e = { other = other, civ = civ, items = items, n = #items,
                  start_turn = start_turn, duration = duration, ends_on = ends_on }
      if ends_on then e.turns_left = ends_on - turn end
      out[#out + 1] = e
    end
  end
  if deal.ClearItems then pcall(function() deal:ClearItems() end) end
  return { ok = true, deals = out, n = #out }
end

-- Finalize an EXISTING scratch deal (AI/human offer already on the table).
-- Never Add* — that path crashed the process. Stock UI: tradelogic.lua
-- UI.DoFinalizePlayerDeal(them, us, true/false) for PvP accept/refuse.
function H.accept_deal(pid)
  local d = H.incoming_deal(pid)
  if not d.ok or (d.n or 0) == 0 then return { ok = false, err = "no incoming deal" } end
  local them = d.from
  if them == pid then them = d.to end
  if them == nil or them == pid then return { ok = false, err = "deal has no other player" } end
  if not UI or not UI.DoFinalizePlayerDeal then
    return { ok = false, err = "DoFinalizePlayerDeal unavailable" }
  end
  UI.DoFinalizePlayerDeal(them, pid, true)
  -- The stock screen hides itself after finalizing and its hide handler empties the scratch table;
  -- without that the accepted items lingered as a fresh "incoming deal" and current_deals refused
  -- with "trade table is occupied" (live 2026-09-24 t226, peace between two humans).
  H.clear_scratch_deal()
  -- The reply names what was signed and with whom, as the trade screen's accept does (GitLab #174).
  return { ok = true, other = them, accepted_items = d.items }
end

function H.clear_scratch_deal()
  pcall(function()
    local deal = UI and UI.GetScratchDeal and UI.GetScratchDeal()
    if deal and deal.ClearItems then deal:ClearItems() end
  end)
end

function H.refuse_deal(pid)
  local d = H.incoming_deal(pid)
  if not d.ok then return { ok = false, err = "no incoming deal" } end
  -- A proposal the engine holds (ProposedDealExists) is refusable even when its items did not load into
  -- the scratch (GitLab #161): the stock screen's refuse is DoFinalizePlayerDeal(them, us, false) all the same.
  if (d.n or 0) == 0 and d.proposed_by == nil then return { ok = false, err = "no incoming deal" } end
  local them = d.proposed_by or d.from
  if them == pid then them = d.to end
  if them == nil or them == pid then return { ok = false, err = "deal has no other player" } end
  if not UI or not UI.DoFinalizePlayerDeal then
    return { ok = false, err = "DoFinalizePlayerDeal unavailable" }
  end
  UI.DoFinalizePlayerDeal(them, pid, false)
  H.clear_scratch_deal()
  -- What was declined and from whom (GitLab #174: {ok, other} alone, after a refuse nobody could read).
  local r = { ok = true, other = them, refused_items = d.items }
  if (d.n or 0) == 0 then
    r.unread = true
    r.note = "player " .. tostring(them) .. "'s proposal was declined unseen: its items did not load onto the table"
  end
  return r
end

-- What can currently go on a deal with `other`, using only IsPossibleToTradeItem.
-- Never Add*/ClearItems/DoProposeDeal. SetFromPlayer/SetToPlayer is required for
-- some item types to report correctly (live: lump GOLD stayed false until from/to
-- were set; GPT was already true). Skips DECLARATION_OF_FRIENDSHIP vs AI (native
-- crash) and PEACE_TREATY (AddPeaceTreaty crashed even when valid).
-- Peace on the trade table (GitLab #5). Neither stock screen has a Peace Treaty pocket button: tradelogic.lua
-- OnOpenPlayerDealScreen seeds TRADE_ITEM_PEACE_TREATY on BOTH sides itself when two humans at war open a table,
-- and after HUMAN_NEGOTIATE_PEACE the engine opens the AI's table with the same pair already on it (the "Deal can
-- already have items in it if, say, we're at war" comment in tradelogic.lua OnShowHide). What a human sees before
-- that is the leader screen's Negotiate Peace button (leaderheadroot.lua OnShowHide): hidden when CanChangeWarPeace
-- is false, greyed with TXT_KEY_DIPLO_NEGOTIATE_PEACE_BLOCKED_TT while GetNumTurnsLockedIntoWar > 0. `us`/`them`
-- are the engine's own IsPossibleToTradeItem(PEACE_TREATY) answers; `ok`/`note` is the whole gate, as the screen
-- shows it. Read-only; the headless AddPeaceTreaty crashed the game and is never called here.
function H.peace_catalog(deal, pid, other)
  if not (Players and Teams and TradeableItems) then return nil end
  local T = TradeableItems
  if not T.TRADE_ITEM_PEACE_TREATY then return nil end
  local usTeam, themTeam = Players[pid]:GetTeam(), Players[other]:GetTeam()
  local function try(f) local ok, v = pcall(f); if ok then return v end return nil end
  local at_war = try(function() return Teams[usTeam]:IsAtWar(themTeam) end) or false
  local length = try(function() return GameDefines.PEACE_TREATY_LENGTH end)
  local out = { at_war = at_war, duration = try(function() return Game.GetPeaceDuration() end) or length }
  if not at_war then
    out.ok, out.note = false, "not at war"
    return out
  end
  out.can_change_war_peace = try(function() return Teams[usTeam]:CanChangeWarPeace(themTeam) end)
  out.locked_turns = try(function() return Teams[usTeam]:GetNumTurnsLockedIntoWar(themTeam) end)
  out.us = try(function() return deal:IsPossibleToTradeItem(pid, other, T.TRADE_ITEM_PEACE_TREATY, length) end) and true or false
  out.them = try(function() return deal:IsPossibleToTradeItem(other, pid, T.TRADE_ITEM_PEACE_TREATY, length) end) and true or false
  local fixed = try(function()
    return Game.IsOption(GameOptionTypes.GAMEOPTION_ALWAYS_WAR) or Game.IsOption(GameOptionTypes.GAMEOPTION_NO_CHANGING_WAR_PEACE)
  end)
  if fixed then
    out.ok, out.note = false, "the game options do not allow changing war and peace"
  elseif out.can_change_war_peace == false then
    out.ok, out.note = false, "war and peace cannot be changed with this player"
  elseif (out.locked_turns or 0) > 0 then
    out.ok = false
    out.note = try(function() return Locale.ConvertTextKey("TXT_KEY_DIPLO_NEGOTIATE_PEACE_BLOCKED_TT", out.locked_turns) end)
               or ("locked into war for " .. out.locked_turns .. " more turns")
  elseif not (out.us and out.them) then
    out.ok, out.note = false, "the engine does not allow a peace treaty between these players right now"
  else
    out.ok = true
  end
  return out
end

-- Every war this seat is in, with the peace gate a human sees on the leader screen's Negotiate Peace button
-- (H.peace_catalog's CanChangeWarPeace / GetNumTurnsLockedIntoWar half; the deal's own IsPossibleToTradeItem
-- answer needs the scratch deal and is read by trade_catalog). Live 2026-10-08: Grok's England sat twenty turns
-- in a siege it could not win while every one of its three enemies took a white peace on the first ask -- nothing
-- in the turn's reads said peace was there to be asked for. Majors under `majors`, city-states under `minors`
-- (their peace is city_state_action make_peace). Nil when not at war with anyone.
function H.wars(pid)
  local p = Players[pid]
  if not (p and Teams) then return nil end
  local usTeam = p:GetTeam()
  local team = Teams[usTeam]
  if not team then return nil end
  local function try(f) local ok, v = pcall(f); if ok then return v end return nil end
  local fixed = try(function()
    return Game.IsOption(GameOptionTypes.GAMEOPTION_ALWAYS_WAR) or Game.IsOption(GameOptionTypes.GAMEOPTION_NO_CHANGING_WAR_PEACE)
  end)
  local majors, minors = {}, {}
  for i = 0, GameDefines.MAX_CIV_PLAYERS - 1 do
    local o = Players[i]
    if o and i ~= pid and o:IsAlive() and o:GetTeam() ~= usTeam and team:IsHasMet(o:GetTeam()) and team:IsAtWar(o:GetTeam()) then
      local row = { player_id = i, civ = Locale.Lookup(o:GetCivilizationShortDescriptionKey()) }
      if o:IsMinorCiv() then
        minors[#minors + 1] = row
      else
        row.leader = o:GetName()
        local locked = try(function() return team:GetNumTurnsLockedIntoWar(o:GetTeam()) end) or 0
        local can = try(function() return team:CanChangeWarPeace(o:GetTeam()) end)
        local peace = { locked_turns = locked }
        if fixed then
          peace.ok, peace.note = false, "the game options do not allow changing war and peace"
        elseif can == false then
          peace.ok, peace.note = false, "war and peace cannot be changed with this player"
        elseif locked > 0 then
          peace.ok = false
          peace.note = try(function() return Locale.ConvertTextKey("TXT_KEY_DIPLO_NEGOTIATE_PEACE_BLOCKED_TT", locked) end)
                       or ("locked into war for " .. locked .. " more turns")
        else
          peace.ok = true
        end
        row.peace = peace
        majors[#majors + 1] = row
      end
    end
  end
  if #majors == 0 and #minors == 0 then return nil end
  return { majors = majors, minors = minors }
end

function H.trade_catalog(other, pid)
  if Game.GetActivePlayer() ~= pid then return { ok = false, err = "this seat is not active" } end
  local o = Players[other]
  if not o or not o:IsAlive() then return { ok = false, err = "no such player" } end
  if o.IsMinorCiv and o:IsMinorCiv() then
    return { ok = false, err = "city-states are not trade-table deals; use state(what='city_state', view='full')" }
  end
  local myTeam = Teams[Players[pid]:GetTeam()]
  if not myTeam:IsHasMet(o:GetTeam()) then return { ok = false, err = "have not met this player yet" } end
  if not UI or not UI.GetScratchDeal then return { ok = false, err = "scratch deal unavailable" } end
  local deal = UI.GetScratchDeal()
  if not deal then return { ok = false, err = "scratch deal unavailable" } end
  deal:SetFromPlayer(pid)
  deal:SetToPlayer(other)
  local duration = Game.GetDealDuration()
  local T = TradeableItems
  local function possible(from, to, typ, a, b)
    local ok, v = pcall(function()
      if b ~= nil then return deal:IsPossibleToTradeItem(from, to, typ, a, b) end
      if a ~= nil then return deal:IsPossibleToTradeItem(from, to, typ, a) end
      return deal:IsPossibleToTradeItem(from, to, typ)
    end)
    return ok and v and true or false
  end
  local function pair(typ, a, b)
    return {
      us = possible(pid, other, typ, a, b),
      them = possible(other, pid, typ, a, b),
    }
  end
  local resources = {}
  if GameInfo and GameInfo.Resources then
    for res in GameInfo.Resources() do
      if res and res.ID then
        local us = possible(pid, other, T.TRADE_ITEM_RESOURCES, res.ID, 1)
        local them = possible(other, pid, T.TRADE_ITEM_RESOURCES, res.ID, 1)
        if us or them then
          -- copies each side holds (the trade screen shows these numbers to a human), and a warning when
          -- the requested export is our only copy of a luxury: selling it costs the empire its happiness.
          -- The trade screen shows their count only for what they can trade us, and without imports
          -- (diplorelationships.lua:374-377 passes false); ours keeps imports for the last-copy check.
          local function avail(pl, withImports)
            local okc, v = pcall(function() return pl:GetNumResourceAvailable(res.ID, withImports) end)
            if okc and type(v) == "number" then return v end
            return nil
          end
          local entry = { resource = res.Type, us = us, them = them, class = res.ResourceClassType,
                          us_available = avail(Players[pid], true), them_available = them and avail(o, false) or nil }
          if us and res.ResourceClassType == "RESOURCECLASS_LUXURY" and entry.us_available == 1 then
            entry.last_copy = true
            entry.note = "our only copy: exporting it removes its happiness from the empire"
          end
          resources[#resources + 1] = entry
        end
      end
    end
  end
  -- Cities the deal would accept from each side: the exact IsPossibleToTradeItem(..., x, y) gate the
  -- trade screen's Pocket Cities list is built from. tradelogic's OnChooseCity -> deal:AddCityTrade is
  -- unconditional, so a city id that fails this gate must never reach it (v85).
  local function tradeable_cities(from, to)
    local out = {}
    local pl = Players[from]
    if pl and pl.Cities then
      for c in pl:Cities() do
        if c and possible(from, to, T.TRADE_ITEM_CITIES, c:GetX(), c:GetY()) then
          -- the trade screen lists the name; where the city is shows only once its plot is revealed to us
          -- the Pocket Cities list (tradelogic.lua) prints "name (pop)" for every entry, ours and theirs
          local seen = c:Plot():IsRevealed(Players[pid]:GetTeam(), false)
          local okp, pop = pcall(function() return c:GetPopulation() end)
          -- City ids are per player: Nineveh 16385 and Umgungundlovu 16385 are different cities (GitLab #70). Each
          -- row says whose it is; state(what="city", id) reads my own cities only.
          out[#out + 1] = { id = c:GetID(), player = from, name = c:GetName(), pop = okp and type(pop) == "number" and pop or nil,
                            x = seen and c:GetX() or nil, y = seen and c:GetY() or nil }
        end
      end
    end
    return out
  end
  local function num(f)
    local okn, v = pcall(f)
    if okn and type(v) == "number" then return v end
    return nil
  end
  local gold = pair(T.TRADE_ITEM_GOLD, 1)
  gold.us_available = num(function() return deal:GetGoldAvailable(pid, -1) end)
  gold.them_available = num(function() return deal:GetGoldAvailable(other, -1) end)
  -- Brave New World: a lump sum ("flat fee") is tradeable only under a Declaration of Friendship; gold
  -- per turn is not gated. The stock pocket just hides the Gold row (tradelogic.lua 1057 asks the same
  -- IsPossibleToTradeItem(..., TRADE_ITEM_GOLD, 1)); say why, since the rule is the game's own (engine-
  -- checked 2026-09-25: only the one friend among four met civs traded lump gold either way).
  if not (gold.us or gold.them) then
    local dof = false
    pcall(function() dof = Players[pid]:IsDoF(other) end)
    gold.declaration_of_friendship = dof and true or false
    if not dof then
      gold.note = "lump-sum gold needs a Declaration of Friendship with this civ (Brave New World rule); gold per turn does not"
    end
  end
  local gpt = pair(T.TRADE_ITEM_GOLD_PER_TURN, 1, duration)
  gpt.us_available = num(function() return Players[pid]:CalculateGoldRate() end)
  gpt.them_available = num(function() return o:CalculateGoldRate() end)
  -- Brave New World: open borders need embassies. Live England t222-t223 (v272): Rome's row read not legal
  -- both ways the turn after its deal ended while the Ottomans' (embassies both ways) went on the table the
  -- turn after theirs; Rome and England held no embassy with each other (Rome's counter-offer asked for one).
  -- The stock pocket just hides the row; say which embassy is missing, since the rule is the game's own.
  local open_borders = pair(T.TRADE_ITEM_OPEN_BORDERS, duration)
  if not (open_borders.us or open_borders.them) and not myTeam:IsAtWar(o:GetTeam()) then
    -- A row is also illegal while borders are already open that way (the deal in force; v273 -- at t214 Rome's
    -- Wine deal carried open borders both ways and no embassy existed, so the embassy note would have been wrong).
    local we_give, they_give = nil, nil
    pcall(function() we_give = myTeam:IsAllowsOpenBordersToTeam(o:GetTeam()) and true or false end)
    pcall(function() they_give = Teams[o:GetTeam()]:IsAllowsOpenBordersToTeam(Players[pid]:GetTeam()) and true or false end)
    if we_give or they_give then
      open_borders.in_force = { we_give = we_give, they_give = they_give }
      open_borders.note = "already in force: " .. ((we_give and they_give) and "open borders both ways"
        or (we_give and "we give open borders" or "they give open borders"))
        .. " (state(what='screen', view='deals') has the end turn; a renewal goes on the table the turn after)"
    else
      local ours, theirs = nil, nil
      -- HasEmbassyAtTeam(t): this team's embassy stands in t's capital (GitLab #136: the two were swapped)
      pcall(function() ours = myTeam:HasEmbassyAtTeam(o:GetTeam()) and true or false end)
      pcall(function() theirs = Teams[o:GetTeam()]:HasEmbassyAtTeam(Players[pid]:GetTeam()) and true or false end)
      open_borders.our_embassy_with_them, open_borders.their_embassy_with_us = ours, theirs
      if ours == false or theirs == false then
        local missing = {}
        if ours == false then missing[#missing + 1] = "we have no embassy with them" end
        if theirs == false then missing[#missing + 1] = "they have none with us" end
        open_borders.note = "open borders need an embassy (Brave New World rule): " .. table.concat(missing, "; ")
          .. "; the embassy row says whether one can be exchanged now"
      end
    end
  end
  return {
    ok = true, other = other, duration = duration,
    gold = gold,
    gold_per_turn = gpt,
    cities = { us = tradeable_cities(pid, other), them = tradeable_cities(other, pid) },
    open_borders = open_borders,
    embassy = pair(T.TRADE_ITEM_ALLOW_EMBASSY, duration),
    research_agreement = pair(T.TRADE_ITEM_RESEARCH_AGREEMENT, duration),
    defensive_pact = pair(T.TRADE_ITEM_DEFENSIVE_PACT, duration),
    -- the PvP-only pocket row (GitLab #175); against an AI it only points at the leader screen
    declaration_of_friendship = H.friendship_catalog and H.friendship_catalog(deal, pid, other) or nil,
    at_war = myTeam:IsAtWar(o:GetTeam()) or false,
    -- the Negotiate Peace gate; the treaty itself is seeded on both sides of any table by the screens (GitLab #5)
    peace = H.peace_catalog and H.peace_catalog(deal, pid, other) or nil,
    resources = resources,
    -- the Other Players pocket (tradelogic.lua ShowOtherPlayerChooser), GitLab #6
    third_party = H.third_party_catalog and H.third_party_catalog(deal, pid, other) or nil,
    -- the Pocket Votes list (tradelogic.lua RefreshPocketVotes), GitLab #7
    vote_commitments = H.vote_commitment_catalog and H.vote_commitment_catalog(deal, pid, other) or {},
    -- the Votes pocket header: enabled by Player:CanCommitVote(other), tooltip GetCommitVoteDetails(other)
    -- (why not: no World Congress, not a member, in session, no proposals yet, no Spy as a Diplomat in
    -- the other capital, delegates already traded this session). Both directions, as the screen shows.
    votes = H.vote_gate and H.vote_gate(Players[pid], o) or nil,
  }
end

-- Third-party war / peace on the trade table (GitLab #6). The deal item names a TEAM; the screen's
-- Other Players pocket shows one leader button per met, living player of it. Same lookup here.
function H.third_party_player(team)
  if not (Players and GameDefines) then return nil end
  local max = GameDefines.MAX_CIV_PLAYERS or 63
  for p = 0, max - 1 do
    local pl = Players[p]
    if pl and pl:IsAlive() and pl:GetTeam() == team then
      local minor = pl.IsMinorCiv and pl:IsMinorCiv() or false
      local okn, name = pcall(function() return pl:GetName() end)
      return { other = p, other_name = okn and name or nil, minor = minor }
    end
  end
  return nil
end

-- tradelogic.lua ShowOtherPlayerChooser: every living player both sides have met (not us, not them)
-- is a button; IsPossibleToTradeItem(from, to, type, team) enables it, otherwise it is greyed with the
-- reason the screen puts in its tooltip. `ok` rows are what propose_deal will accept.
function H.third_party_catalog(deal, pid, other)
  if not (Players and Teams and GameDefines and TradeableItems) then return nil end
  local T = TradeableItems
  if not (T.TRADE_ITEM_THIRD_PARTY_WAR and T.TRADE_ITEM_THIRD_PARTY_PEACE) then return nil end
  local usTeam, themTeam = Players[pid]:GetTeam(), Players[other]:GetTeam()
  local function reason(from, loop, loopTeam, war)
    local fromTeam = Players[from]:GetTeam()
    local r
    pcall(function()
      if not war then
        if not Teams[loopTeam]:IsAtWar(fromTeam) then r = "TXT_KEY_DIPLO_NOT_AT_WAR"
        elseif loop:IsMinorCiv() then
          local ally = loop:GetAlly()
          if loop:IsMinorPermanentWar(from) then r = "TXT_KEY_DIPLO_MINOR_PERMANENT_WAR"
          elseif ally ~= -1 and Teams[Players[ally]:GetTeam()]:IsAtWar(fromTeam) then r = "TXT_KEY_DIPLO_MINOR_ALLY_AT_WAR" end
        else
          if not Players[from]:IsWillAcceptPeaceWithPlayer(loop:GetID()) then r = "TXT_KEY_DIPLO_MINOR_THIS_GUY_WANTS_WAR"
          elseif not loop:IsWillAcceptPeaceWithPlayer(from) then r = "TXT_KEY_DIPLO_MINOR_OTHER_GUY_WANTS_WAR" end
        end
      else
        if Teams[loopTeam]:IsAtWar(fromTeam) then r = "TXT_KEY_DIPLO_ALREADY_AT_WAR"
        elseif Teams[fromTeam]:IsForcePeace(loopTeam) then r = "TXT_KEY_DIPLO_FORCE_PEACE"
        elseif loop:IsMinorCiv() and loop:GetAlly() == from then r = "TXT_KEY_DIPLO_NO_WAR_ALLIES" end
      end
    end)
    if r and Locale and Locale.ConvertTextKey then
      local okl, txt = pcall(Locale.ConvertTextKey, r)
      if okl and type(txt) == "string" then return plain_text(txt) end
    end
    return r
  end
  local out = { war = { us = {}, them = {} }, peace = { us = {}, them = {} } }
  -- GitLab #148: third_party.peace listed every met civ for us and for them, 40 rows reading "These players are
  -- not at war." (~5 KB) -- a peace is tradeable only between parties at war; those rows are counted, not listed.
  local not_at_war = { us = 0, them = 0 }
  local max = GameDefines.MAX_CIV_PLAYERS or 63
  for p = 0, max - 1 do
    local pl = Players[p]
    if pl and p ~= pid and p ~= other and pl:IsAlive() then
      local t = pl:GetTeam()
      if t ~= usTeam and t ~= themTeam and Teams[usTeam]:IsHasMet(t) and Teams[themTeam]:IsHasMet(t) then
        local okn, name = pcall(function() return pl:GetName() end)
        local minor = pl.IsMinorCiv and pl:IsMinorCiv() or false
        for _, kind in ipairs({ { "war", T.TRADE_ITEM_THIRD_PARTY_WAR, true }, { "peace", T.TRADE_ITEM_THIRD_PARTY_PEACE, false } }) do
          for _, side in ipairs({ { "us", pid, other }, { "them", other, pid } }) do
            local okq, possible = pcall(function() return deal:IsPossibleToTradeItem(side[2], side[3], kind[2], t) end)
            possible = okq and possible and true or false
            local row = { player = p, team = t, name = okn and name or nil, minor = minor, ok = possible,
                          at_war_with_them = Teams[t]:IsAtWar(Players[side[2]]:GetTeam()) or false }
            if not possible then row.note = reason(side[2], pl, t, kind[3]) end
            if kind[1] == "peace" and not possible and not row.at_war_with_them then
              not_at_war[side[1]] = not_at_war[side[1]] + 1
            else
              local list = out[kind[1]][side[1]]
              list[#list + 1] = row
            end
          end
        end
      end
    end
  end
  for _, side in ipairs({ "us", "them" }) do
    if not_at_war[side] > 0 then out.peace[side .. "_not_at_war_omitted"] = not_at_war[side] end
  end
  return out
end

function H.vote_gate(us, them)
  if not (us and them and us.CanCommitVote) then return nil end
  local function side(a, b)
    local okc, can = pcall(function() return a:CanCommitVote(b:GetID()) end)
    local okd, det = pcall(function() return a:GetCommitVoteDetails(b:GetID()) end)
    local r = { can = okc and can and true or false }
    if okd and type(det) == "string" and det ~= "" then r.note = plain_text(det) end
    return r
  end
  local u, t = side(us, them), side(them, us)
  return { us = u.can, us_note = u.note, them = t.can, them_note = t.note }
end

---------------------------------------------------------------- the trade flow's own reads (v285)
-- Composed in harness/game_parts/deals.py until stage 3 of the seat binding moved them here.
function H.set_harness_diplo(on, pid)
  -- leader chatter from here until the screens close is provoked by us (turn_digest hides it)
  H.harness_diplo = on and true or nil
  return true
end

function H.begin_diplo_with(other, pid)
  if Game.GetActivePlayer() ~= pid then return { ok = false, err = "this seat is not active" } end
  local o = Players[other]
  if not o then return { ok = false, err = "no such player" } end
  H.harness_diplo = true
  UI.SetRepeatActionPlayer(other); UI.ChangeStartDiploRepeatCount(1); o:DoBeginDiploWithHuman()
  return { ok = true }
end

function H.deal_snapshot(resources, pid)
  local p = Players[pid]
  local out = { gold = p:GetGold(), gold_per_turn = p:CalculateGoldRate(), happiness = p:GetExcessHappiness(),
                deals = UI.GetNumCurrentDeals(pid), resources = {} }
  for _, r in ipairs(resources or {}) do
    local id = GameInfoTypes[r]
    if id then out.resources[r] = { available = p:GetNumResourceAvailable(id, true),
                                    imported = p:GetResourceImport(id), exported = p:GetResourceExport(id) } end
  end
  return out
end

-- tradelogic.lua keeps g_bPVPTrade / g_iThem as file locals, so the counterpart is read off the scratch deal
-- the screen just set up (SetFromPlayer(us) / SetToPlayer(them), or the pending proposal it loaded).
function H.scratch_deal_ends(pid)
  if Game.GetActivePlayer() ~= pid then return { ok = false, err = "this seat is not active" } end
  local d = UI.GetScratchDeal()
  return { from_p = d:GetFromPlayer(), to_p = d:GetToPlayer(), n = d:GetNumItems() }
end

function H.deal_partner_check(other, pid)
  local o = Players[other]
  if not o or not o:IsAlive() then return { ok = false, err = "no such player" } end
  if o:IsMinorCiv() then return { ok = false, err = "city-states are not trade-table deals; use order(to='city_state', action='gift_gold')" } end
  if not Teams[Players[pid]:GetTeam()]:IsHasMet(o:GetTeam()) then return { ok = false, err = "have not met this player" } end
  local pending = UI.HasMadeProposal(pid)
  if pending ~= -1 and pending ~= other then
    return { ok = false, err = "a proposal to another player is already outstanding", pending_to = pending }
  end
  return { ok = true, human = o:IsHuman() and true or false }
end

function H.at_war_with(other, pid)
  local o = Players[other]
  if not o then return false end
  return Teams[Players[pid]:GetTeam()]:IsAtWar(o:GetTeam()) and true or false
end

function H.player_is_human(other, pid)
  local o = Players[other]
  return (o and o:IsHuman()) and true or false
end

function H.has_made_proposal(pid) return UI.HasMadeProposal(pid) end
