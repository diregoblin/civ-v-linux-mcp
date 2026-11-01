-- Shared by earlier fragments (load order: harness/runtime_source.py MANIFEST).
local L, short = H._ns.L, H._ns.short

function H.pending_popups(pid)
  local out = {}
  for kind, info in pairs(H.popups) do
    if info.player == pid then
      out[#out+1] = {type=kind, name=H.enum_name("popup", ButtonPopupTypes, kind), data1=info.data1, data2=info.data2, data3=info.data3}
    end
  end
  table.sort(out, function(a,b) return a.type < b.type end)
  return out
end

-- Why the turn would not end, in the engine's own terms. `UI.CanEndTurn()` is the flag the stock HUD
-- uses to grey out its End Turn button: when it is false, CONTROL_ENDTURN is discarded and nothing at
-- all happens. The harness used to answer that case with the guess "a unit or decision still blocks
-- it" alongside blocking_name NO_ENDTURN_BLOCKING_TYPE and an empty todo -- three statements that
-- together say nothing true. Live t189 (Shoshone vs the Inca): the seat sat on a turn that would not
-- end, with no blocker, no popup, no ready unit and no busy unit, and the harness could only repeat
-- itself. Report what the engine actually says so the next occurrence is diagnosable rather than
-- mysterious; every field is read through pcall because these getters vary by build.
function H.end_turn_diagnosis(pid)
  local p = Players[pid]
  local out = {}
  local function try(k, f) local ok, v = pcall(f); if ok then out[k] = v end end
  try("can_end_turn", function() return UI.CanEndTurn() end)
  try("has_ready_unit", function() return p:HasReadyUnit() end)
  try("has_busy_unit", function() return p:HasBusyUnit() end)
  try("blocking", function() return p:GetEndTurnBlockingType() end)
  try("turn_active", function() return p:IsTurnActive() end)
  try("processing", function() return Game.IsProcessingMessages() end)
  try("city_screen_up", function() return UI.IsCityScreenUp() end)
  try("interface_mode", function() return UI.GetInterfaceMode() end)
  try("leader_view_up", function() return H.leader_view_up() end)
  if out.can_end_turn == false then
    out.note = "the engine's own End Turn is disabled (UI.CanEndTurn() is false), so CONTROL_ENDTURN "
            .. "is discarded: this is not one of the todo blockers. Look at the game window -- a screen "
            .. "or popup the harness does not model may be open."
    if out.leader_view_up == false then
      out.note = out.note .. " It is not the leader view a previous exit to the main menu left open "
              .. "(GitLab #137): end_turn already asked the engine to leave that one (UI.RequestLeaveLeader())."
    end
  end
  return out
end

-- A leader on screen, whatever they want: a greeting, a demand, a deal or the "Anything else?" scene.
function H.leader_view_up()
  local f = H.modal_flags()
  return (f.leader_greeting_pending or f.discussion_pending) and true or false
end

-- GitLab #137 (live Maya t200, 2026-10-29): Events.ExitToMainMenu() with a leader on screen leaves the exe's
-- leader view "open" into the next game loaded -- no Lua context shows it, blocking is NO_ENDTURN_BLOCKING_TYPE,
-- no popup, yet UI.CanEndTurn() stays false and every CONTROL_ENDTURN is discarded. The leader screen's own
-- back button, UI.RequestLeaveLeader(), closes it at once. Called with End Turn disabled and nothing else to
-- blame (no blocker, no popup, no leader actually on screen): asks the engine to leave and says whether the
-- button came back. Anything else on screen is left alone, so a real leader is never walked out on.
function H.clear_stale_leader_view(pid)
  local p = Players[pid]
  local ok_c, can = pcall(function() return UI.CanEndTurn() end)
  if not ok_c or can ~= false then return { cleared = false, why = "End Turn is enabled" } end
  if p:GetEndTurnBlockingType() ~= -1 then return { cleared = false, why = "the engine names a blocker" } end
  if #H.pending_popups(pid) > 0 then return { cleared = false, why = "a popup is up" } end
  if H.leader_view_up() then return { cleared = false, why = "a leader is on screen" } end
  pcall(function() UI.RequestLeaveLeader() end)
  local ok2, can2 = pcall(function() return UI.CanEndTurn() end)
  local cleared = (ok2 and can2) and true or false
  -- The finish reply drops the send's own keys once the turn ends, so the digest carries what was done.
  if cleared then H.record("stale_leader_view_cleared", { turn = Game.GetGameTurn() }) end
  return { cleared = cleared, requested = true }
end

function H.todo(pid)
  local p = Players[pid]
  if not (Game.GetActivePlayer() == pid and p:IsTurnActive()) then return nil end
  local todo = { units = {}, promotions = {}, cities = {}, research_unset = p:GetCurrentResearch() == -1 }
  -- A religion to found or enhance (a Prophet spent, the beliefs not chosen), whatever blocker the engine
  -- names first (#109): "found" / "enhance".
  pcall(function() if H.religion_choice then todo.religion = H.religion_choice(pid) end end)
  -- GitLab #118 (Maya t177): a spy recruited at the new era sat Unassigned and only the digest said so.
  pcall(function()
    local s = H.idle_spies and H.idle_spies(pid) or {}
    if #s > 0 then
      todo.idle_spies = s
      todo.idle_spies_hint = "an unassigned spy earns nothing: state(what='options', view='spy_cities', id=<agent_id>) then order(to='spy', id, action='move', args={target_player_id, target_city_id})"
    end
  end)
  -- The World Congress wants this seat's proposal (a hard block on the turn's end), whatever blocker the engine
  -- names first (#117, live Maya t197: PRODUCTION masked it until finish refused).
  pcall(function()
    if Game.GetNumActiveLeagues() == 0 then return end
    local league = Game.GetActiveLeague()
    if league and not league:IsInSession() and league:CanPropose(pid) then
      todo.league_proposal = { remaining = league:GetRemainingProposalsForMember(pid),
                               hint = "state(what='league') lists proposable_enact / proposable_repeal; order(to='league', action='propose' / 'repeal') clears it; closing the popup does not" }
    end
  end)
  -- A deal another player proposed waits on the trade table until this seat answers it; a human
  -- opens it from the "X has offered you a deal" notice. Name it here so the seat does not have to
  -- read the notification log to know a peace treaty (live 2026-09-24 t226) or a trade is waiting.
  pcall(function()
    local d = H.incoming_deal(pid)
    local from
    if d and (d.n or 0) > 0 and d.from ~= nil and d.from ~= pid then from = d.from end
    -- The engine's own record of a waiting proposal outlives an empty table read (GitLab #161).
    if from == nil then from = H.pending_deal_from(pid) end
    if from ~= nil then
      todo.incoming_deal = { from = from, items = d and d.n or 0,
                             hint = "question() shows the items; answer(choice='accept') / answer(choice='refuse') answers it" }
    end
  end)
  -- A completed dig waits on its choice (#140, live Maya t221 / t234: ENDTURN_BLOCKING_PRODUCTION masked it until
  -- finish refused). The engine's own record is the next completed-dig plot.
  pcall(function()
    local plot = p.GetNextDigCompletePlot and p:GetNextDigCompletePlot() or nil
    if plot then
      todo.dig_choice = { x = plot:GetX(), y = plot:GetY(),
                          hint = "question() shows the find and the choices; answer(choice=<choice>) takes one" }
    end
  end)
  for u in p:Units() do
    if u:IsReadyToMove() and not u:IsAutomated() and not u:IsDelayedDeath() then
      local ut = GameInfo.Units[u:GetUnitType()]
      -- `hold`: the hold THIS unit can take (GitLab #85: the generic hint named MISSION_FORTIFY to a Hwacha, which
      -- cannot fortify -- siege, mounted, armoured, naval units and civilians sleep instead).
      local hold = "MISSION_SLEEP"
      pcall(function() if u:IsFortifyable() then hold = "MISSION_FORTIFY" end end)
      todo.units[#todo.units + 1] = { id = u:GetID(), type = ut and short(ut.Type) or u:GetUnitType(), x = u:GetX(), y = u:GetY(),
                                      moves = u:MovesLeft() / GameDefines.MOVE_DENOMINATOR, hold = hold }
    elseif not u:IsAutomated() and not u:IsDelayedDeath() and H.is_stalled_mission(u) then
      -- A partially spent move can also stall; report any remaining movement so end_turn cannot
      -- silently miss it.
      local ut = GameInfo.Units[u:GetUnitType()]
      todo.units[#todo.units + 1] = { id = u:GetID(), type = ut and short(ut.Type) or u:GetUnitType(), x = u:GetX(), y = u:GetY(),
                                      moves = u:MovesLeft() / GameDefines.MOVE_DENOMINATOR,
                                      stalled_mission = true, note = "queued move did not resume; re-issue order(to='unit', action='move')",
                                      going_to = H.going_to(u, pid) }
    elseif not u:IsDelayedDeath() and (u:IsAutomated() or H.going_to(u, pid)) then
      -- v218 (#37): a unit the game is already moving -- on automation, or walking a standing move_unit
      -- order that needs more turns -- is not a decision and does not block end_turn, but it is still my
      -- unit and it used to vanish from the turn (live 2026-09-26, Mongolia t42: the auto-explore scout
      -- drifting toward a camp near x=16 was nowhere on the status). List it under `ongoing` with where it
      -- is going; `attention` says when the seat should look (a visible camp or hostile beside it, a
      -- destination it can no longer reach) and is what wakes a quiet-turn run. Orders go out as manual
      -- missions (CvUnitMission::PushMission clears the automate type), so a new move_unit / unit_mission
      -- takes the unit back; no separate cancel is needed.
      local ut = GameInfo.Units[u:GetUnitType()]
      local going = H.going_to(u, pid)
      local row = { id = u:GetID(), type = ut and short(ut.Type) or u:GetUnitType(), x = u:GetX(), y = u:GetY(),
                    moves = u:MovesLeft() / GameDefines.MOVE_DENOMINATOR, hp = u:GetCurrHitPoints(),
                    automated = u:IsAutomated() or nil, going_to = going }
      pcall(function()
        local mission = u.GetMissionType and u:GetMissionType() or -1
        if mission and mission ~= -1 then
          local mn = H.enum_name("MissionTypes", MissionTypes, mission)
          if type(mn) == "string" then row.mission_name = mn end
        end
      end)
      row.attention = H.ongoing_attention(u, pid, going)
      row.note = row.automated and "on automation; a new order(to='unit', action='move' / 'mission') cancels it"
                 or "standing move; resumes each turn until it arrives (a new order replaces it)"
      todo.ongoing = todo.ongoing or {}
      todo.ongoing[#todo.ongoing + 1] = row
    end
    if u.IsPromotionReady and u:IsPromotionReady() then
      todo.promotions[#todo.promotions + 1] = u:GetID()
    end
  end
  -- ENDTURN_BLOCKING_STACKED_UNITS names no unit; a human sees the two icons on one tile. Live t245
  -- the hint alone ("move_unit one of them off it") sent the play loop at the wrong unit (a Caravan,
  -- which cannot be walked) for eleven attempts. List every tile holding two of my land or sea units
  -- of the same class -- combat with combat, civilian with civilian, the 1UPT rule -- with the unit
  -- ids, types and moves, so the caller can pick the one that can leave. Aircraft stack freely.
  pcall(function()
    local air = DomainTypes and DomainTypes.DOMAIN_AIR
    local by_plot = {}
    for u in p:Units() do
      if not u:IsDelayedDeath() and not (air and u:GetDomainType() == air) then
        local key = u:GetX() .. "," .. u:GetY()
        local e = by_plot[key] or { x = u:GetX(), y = u:GetY(), combat = {}, civilian = {} }
        by_plot[key] = e
        local ut = GameInfo.Units[u:GetUnitType()]
        local row = { id = u:GetID(), type = ut and short(ut.Type) or u:GetUnitType(),
                      moves = u:MovesLeft() / GameDefines.MOVE_DENOMINATOR }
        -- A trade unit never competes for a plot, on a route or idle: two caravans crossing the capital on
        -- their routes read as a civilian stack (Mongolia t117, 2026-09-27), and at Venice t153 the engine sold
        -- a Caravan into a city already holding a Worker and a caravan while it refused a second Worker there
        -- (the purchase runs the same one-per-tile check a move does). v254: idle trade units left out too.
        if not (u.IsTrade and u:IsTrade()) then
          local list = u:IsCombatUnit() and e.combat or e.civilian
          list[#list + 1] = row
        end
      end
    end
    for _, e in pairs(by_plot) do
      for _, class in ipairs({ "combat", "civilian" }) do
        if #e[class] > 1 then
          todo.stacked = todo.stacked or {}
          todo.stacked[#todo.stacked + 1] = { x = e.x, y = e.y, class = class, units = e[class] }
        end
      end
    end
  end)
  -- An empty queue in a city whose production is automated is not our decision to make: puppets are
  -- always automated (live t192: Machu/Tiwanaku/Cusco true, all five directly-run cities false), and so
  -- is any city a human put on production automation. The engine does not raise
  -- ENDTURN_BLOCKING_PRODUCTION for them either. Listing them told the LLM to follow the blocking hint
  -- into set_production on a puppet -- an order no human can give (see H.city_production_guard).
  for c in p:Cities() do
    if c:GetProductionNameKey() == "" and not H.production_is_automated(c) then
      todo.cities[#todo.cities + 1] = { id = c:GetID(), name = c:GetName() }
    end
  end
  -- GitLab #101 (Maya t24-t100): a starving city and a city that can fire were only notification text; the
  -- rows a human reads off the city banners. `starving`: cities losing food this turn; `city_strikes`: cities
  -- with a bombard they can fire now and a target in range (the strikes read's own test, only for those cities).
  pcall(function()
    for c in p:Cities() do
      local okf, food = pcall(function() return c:FoodDifference() end)
      if okf and type(food) == "number" and food < 0 then
        todo.starving = todo.starving or {}
        todo.starving[#todo.starving + 1] = { id = c:GetID(), name = c:GetName(), food_surplus = food,
          hint = "state(what='city', id, view='screen') shows the worked plots; order(to='city', action='governor', args={focus: 'food'}) or action='work_plot' ends it" }
      end
      local okn, now = pcall(function() return (c.CanRangeStrikeNow and c:CanRangeStrikeNow()) or false end)
      if okn and now then
        local oks, strikes = pcall(H.available_city_strikes, c:GetID(), pid)
        if oks and type(strikes) == "table" and strikes.can and #(strikes.targets or {}) > 0 then
          todo.city_strikes = todo.city_strikes or {}
          todo.city_strikes[#todo.city_strikes + 1] = { id = c:GetID(), name = c:GetName(), targets = #strikes.targets,
            hint = "state(what='city', id, view='strikes') lists the targets with the odds; order(to='city', action='strike', args={x, y}) fires (free: the city keeps nothing by not firing)" }
        end
      end
    end
  end)
  -- Spy-steal can be pending while another blocker is current (live t181: POLICY in front of
  -- STEAL_TECH). Surface it the same way empty cities / promotions are listed.
  local ok, steal = pcall(H.steal_tech_options, pid)
  if ok and type(steal) == "table" and (steal.n or 0) > 0 then
    todo.steal_tech = steal.victims
    todo.steal_tech_hint = "a spy finished stealing: question() then answer(choice=<tech>) (can sit behind another blocking_name)"
  end
  -- v251: a social policy that can be adopted is a decision a human sees (the glowing culture button and the
  -- "May adopt Policy" notice) whichever blocker the engine happens to report first (live t149, Mongolia:
  -- PRODUCTION first, the policy only surfaced when the turn end was refused).
  pcall(function()
    if p:IsAnarchy() then return end
    local free = p.GetNumFreePolicies and p:GetNumFreePolicies() or 0
    local tenets = p.GetNumFreeTenets and p:GetNumFreeTenets() or 0  -- v260: an ideology's free tenets too
    local culture, cost = p:GetJONSCulture(), p:GetNextPolicyCost()
    if free > 0 or tenets > 0 or (culture and cost and culture >= cost) then
      todo.policy = { culture = culture, cost = cost, free = free > 0 and free or nil,
                      free_tenets = tenets > 0 and tenets or nil }
    end
  end)
  return todo
end

-- What a player new to this harness should do about each end-turn blocker: the tool to call.
local BLOCKING_HINTS = {
  ENDTURN_BLOCKING_UNITS = "every unit in todo.units still has moves: order(to='unit', action='move') / order(to='unit', action='mission') each of them (MISSION_SKIP for this turn, the row's `hold` -- MISSION_FORTIFY, or MISSION_SLEEP for a unit that cannot fortify -- to hold, MISSION_BUILD for a worker)",
  ENDTURN_BLOCKING_STACKED_UNITS = "two of my units share a tile: order(to='unit', action='move') one of them off it (skip/fortify does NOT clear this)",
  ENDTURN_BLOCKING_UNIT_NEEDS_ORDERS = "a unit needs an order: see todo.units; order(to='unit', action='move' / 'mission')",
  ENDTURN_BLOCKING_UNIT_PROMOTION = "a unit earned a promotion: state(what='unit', id, view='actions').promotions then order(to='unit', action='promote') (todo.promotions lists the unit ids)",
  ENDTURN_BLOCKING_RESEARCH = "no research chosen: state(what='options', view='research') then order(to='empire', action='research')",
  ENDTURN_BLOCKING_PRODUCTION = "a city has nothing in production: todo.cities, then state(what='city', id, view='production') + order(to='city', action='produce')",
  ENDTURN_BLOCKING_POLICY = "a social policy can be adopted: state(what='options', view='policies') then order(to='empire', action='policy') with a policy or a branch",
  ENDTURN_BLOCKING_FREE_POLICY = "a free social policy is waiting: state(what='options', view='policies') then order(to='empire', action='policy')",
  ENDTURN_BLOCKING_FREE_TECH = "a free technology is waiting: state(what='options', view='research') then order(to='empire', action='research')",
  ENDTURN_BLOCKING_FOUND_PANTHEON = "enough faith for a pantheon: order(to='empire', action='pantheon')",
  ENDTURN_BLOCKING_FOUND_RELIGION = "a Great Prophet can found a religion: order(to='empire', action='religion')",
  ENDTURN_BLOCKING_ENHANCE_RELIGION = "a Great Prophet can enhance the religion: order(to='empire', action='enhance_religion')",
  ENDTURN_BLOCKING_STEAL_TECH = "a spy stole a tech and you must pick which: question() then answer(choice=<tech>)",
  ENDTURN_BLOCKING_LEAGUE_CALL_FOR_PROPOSALS = "World Congress wants a proposal (hard block): state(what='league') then order(to='league', action='propose' / 'repeal')",
  ENDTURN_BLOCKING_LEAGUE_CALL_FOR_VOTES = "World Congress session: state(what='league') then order(to='league', action='vote')",
  ENDTURN_BLOCKING_DIPLO_VOTE = "a diplomatic vote is pending: state(what='league') / order(to='league', action='vote')",
  ENDTURN_BLOCKING_FAITH_GREAT_PERSON = "a Great Person can be bought with faith: question() then answer(choice=<unit>)",
  ENDTURN_BLOCKING_FREE_ITEMS = "a free unit/building choice is pending: question() then answer(choice=<unit>)",
  ENDTURN_BLOCKING_CITY_RANGE_ATTACK = "a city can bombard an enemy: state(what='city', id, view='strikes') then order(to='city', action='strike') (or turn(action='finish') anyway once you have decided not to)",
  ENDTURN_BLOCKING_CHOOSE_IDEOLOGY = "state(what='options', view='policies').ideologies: per ideology the met civs that follow it (friends, denouncers), its early-adopter free tenets and its tier-1 tenets, each row with its order(to='empire', action='ideology', args={branch}) call",
  ENDTURN_BLOCKING_ADD_REFORMATION_BELIEF = "a reformation belief is pending: state(what='options', view='beliefs', kind='reformation') then order(to='empire', action='reformation')",
  ENDTURN_BLOCKING_CHOOSE_ARCHAEOLOGY = "use question() then answer(choice=<choice>) for the completed dig",
  ENDTURN_BLOCKING_MINOR_QUEST = "a city-state quest popup is pending: turn(action='wait') sweeps it",
  ENDTURN_BLOCKING_MAYA_LONG_COUNT = "use question() then answer(choice=<unit>) for the Long Count reward",
}
function H.blocking_hint(name)
  return BLOCKING_HINTS[name] or ("no dedicated action for " .. tostring(name) .. "; try turn(action='wait') (sweeps popups) and turn(action='status')")
end

-- The engine stops re-evaluating GetEndTurnBlockingType while a popup is up (UI.IsPopupUp()). So the
-- last ready unit's order, when it also raises an announcement (a city-state met on the way, a natural
-- wonder found, a golden age), leaves ENDTURN_BLOCKING_UNITS on the books with HasReadyUnit() false and
-- nothing in todo.units -- GitLab #23, reproduced live t215 (Persia, Infantry 32771 walked past a
-- natural wonder toward Melbourne: blocking UNITS, has_ready false, todo empty, popup_up true, for as
-- long as the popup stayed; closing it re-evaluated the blocker to -1 at once). The old hint ("every
-- unit in todo.units still has moves") pointed at an empty list. Returns the true hint when the reading
-- is stale, nil when a unit really does need orders (or the stalled-mission shape, which todo lists).
function H.stale_units_blocker(p, blocking, todo)
  if blocking == -1 or H.blocking_name(blocking) ~= "ENDTURN_BLOCKING_UNITS" then return nil end
  if not todo or #(todo.units or {}) > 0 then return nil end
  local ok, ready = pcall(function() return p:HasReadyUnit() end)
  if not ok or ready then return nil end
  local okp, up = pcall(function() return UI.IsPopupUp() end)
  return "no unit needs orders (HasReadyUnit is false, todo.units is empty): ENDTURN_BLOCKING_UNITS is a stale "
      .. "reading -- the engine does not re-evaluate its blocker while a popup is up"
      .. ((okp and up) and " (UI.IsPopupUp() is true now; see pending_popups)" or "")
      .. ". turn(action='finish') / turn(action='wait') sweep announcement popups; a decision popup is answered with question() / answer(choice=<button>)"
end

-- v254: the same frozen reading for the other todo-backed blockers. Live t153 (Mongolia): the Great Work
-- splash came up right after the artist's order; set_production then expired Karakorum's "ready for a new
-- construction project" notification (it read dismissed) while the engine, frozen behind the popup, kept
-- ENDTURN_BLOCKING_PRODUCTION pointing at it. end_turn refused on the blocker with todo.cities empty and
-- never reached its popup sweep; sweeping the popup by hand re-evaluated the blocker to -1 at once. Returns
-- the true hint when the blocker names something todo does not show, nil when the blocker is real.
function H.stale_blocker(p, blocking, todo)
  local units = H.stale_units_blocker(p, blocking, todo)
  if units then return units end
  if blocking == -1 or not todo then return nil end
  local name = H.blocking_name(blocking)
  local what
  if name == "ENDTURN_BLOCKING_PRODUCTION" and #(todo.cities or {}) == 0 then
    what = "no city has an empty production queue (todo.cities is empty): ENDTURN_BLOCKING_PRODUCTION is a stale reading"
  elseif name == "ENDTURN_BLOCKING_RESEARCH" and todo.research_unset == false then
    what = "research is set (todo.research_unset is false): ENDTURN_BLOCKING_RESEARCH is a stale reading"
  end
  if not what then return nil end
  local okp, up = pcall(function() return UI.IsPopupUp() end)
  return what .. " -- the engine re-evaluates its blocker on its next update, never while a popup is up"
      .. ((okp and up) and " (UI.IsPopupUp() is true now; see pending_popups)" or "")
      .. ". turn(action='finish') sweeps announcement popups and sends once more; a decision popup is answered with question() / answer(choice=<button>)"
end

-- Popup screens read from InGame in one query. Every popup is a LuaContext with a Lua state of its own,
-- so the harness used to ask the tuner about each one in turn: eight round-trips (~3 s) for one
-- turn_state, twenty-odd (~8 s) for one popup sweep, on every poll of a wait -- a profiled late turn
-- (S1 t270, 2026-09-25) spent 250 of its 278 trips this way. The engine's control tree is one tree,
-- and LookUpControl by full path reaches every context from here. Paths verified live 2026-09-25
-- (S1 t271): the BulkUI container is transparent to lookup (its children answer as /InGame/<ID>, and
-- any /InGame/BulkUI/<x> path answers with BulkUI itself, visible -- never use that form);
-- LeaderHeadRoot is mounted by the engine at the root, not under InGame; a context's ID can differ from
-- its file (GreatWorkPopup -> GreatWorkSplash, ChooseIdeologyPopup -> ChooseIdeology). Keys are the tuner
-- state names game.py execs into, so a screen found up here is closed in the same state as before.
H.CONTEXT_PATHS = {
  LeaderHeadRoot = "/LeaderHeadRoot",
  DiscussionDialog = "/LeaderHeadRoot/DiscussionDialog",
  DiploTrade = "/LeaderHeadRoot/DiploTrade",
  SimpleDiploTrade = "/InGame/WorldView/DiploCorner/SimpleDiplo",
  TechPopup = "/InGame/WorldView/InfoCorner/TechPanel/TechPopup",
  CityStateGreetingPopup = "/InGame/CityStateGreetingPopup",
  GreatPersonRewardPopup = "/InGame/GreatPersonRewardPopup",
  TechAwardPopup = "/InGame/TechAwardPopup",
  GreatWorkPopup = "/InGame/GreatWorkSplash",
  WhosWinningPopup = "/InGame/WhosWinningPopup",
  WonderPopup = "/InGame/WonderPopup",
  LeagueSplash = "/InGame/LeagueSplash",
  LeagueProjectPopup = "/InGame/LeagueProjectPopup",
  NewEraPopup = "/InGame/NewEraPopup",
  GoldenAgePopup = "/InGame/GoldenAgePopup",
  NaturalWonderPopup = "/InGame/NaturalWonderPopup",
  BarbarianCampPopup = "/InGame/BarbarianCampPopup",
  GoodyHutPopup = "/InGame/GoodyHutPopup",
  TextPopup = "/InGame/TextPopup",
  DeclareWarPopup = "/InGame/DeclareWarPopup",
  GenericPopup = "/InGame/GenericPopup",
  PlayerChange = "/InGame/PlayerChange",
  ChooseIdeologyPopup = "/InGame/ChooseIdeology",
  SocialPolicyPopup = "/InGame/SocialPolicyPopup",
  ProductionPopup = "/InGame/ProductionPopup",
  CityStateDiploPopup = "/InGame/CityStateDiploPopup",
  DiploVotePopup = "/InGame/DiploVotePopup",
  VoteResultsPopup = "/InGame/VoteResultsPopup",
}

-- Whether the context registered under tuner state `name` is drawn: true/false for a loaded context, nil
-- when it is unknown here or not loaded (nothing could draw it), never an error.
function H.screen_up(name)
  local path = H.CONTEXT_PATHS[name]
  if not path then return nil end
  local ok, c = pcall(function() return ContextPtr:LookUpControl(path) end)
  if not ok or c == nil then return nil end
  local okh, hidden = pcall(function() return c:IsHidden() end)
  if not okh then return nil end
  return not hidden
end

-- The screens that change what a turn read means, in one read. `screens` is every known context's
-- up/down (absent when not loaded); the named flags are what turn_state has always carried (game.py's
-- _modal_flags) under the same rules: discussion_pending is either trade table or the DiscussionDialog
-- (neither alone is reliable, see game.py's discussion_pending), leader_greeting_pending is the engine's
-- own flag or the leader scene left visible with no discussion on it (the "Anything else?" scene after a
-- proposal to a human seat). trade_state names the trade table that is up, the state its buttons live in.
function H.modal_flags()
  local screens = {}
  for name in pairs(H.CONTEXT_PATHS) do screens[name] = H.screen_up(name) end
  local trade = (screens.SimpleDiploTrade and "SimpleDiploTrade") or (screens.DiploTrade and "DiploTrade") or nil
  local discussion = (trade ~= nil) or (screens.DiscussionDialog == true)
  local okl, leader_up = pcall(function() return UI.GetLeaderHeadRootUp() end)
  leader_up = (okl and leader_up) and true or false
  return {
    hand_off_pending = H.hand_off_up(),
    leader_greeting_pending = leader_up or (screens.LeaderHeadRoot == true and not discussion) or false,
    city_state_greeting_pending = screens.CityStateGreetingPopup == true,
    great_person_reward_pending = screens.GreatPersonRewardPopup == true,
    tech_popup_pending = screens.TechPopup == true,
    discussion_pending = discussion and true or false,
    leader_head_root_up = leader_up,
    trade_state = trade,
    screens = screens,
  }
end
H.MODAL_FLAG_KEYS = { "leader_greeting_pending", "city_state_greeting_pending", "great_person_reward_pending",
                      "tech_popup_pending", "discussion_pending", "trade_state", "hand_off_pending" }

-- The hotseat hand-off screen ("<leader>'s turn -- Continue", PlayerChange.lua): the one screen that
-- H.screen_up cannot see. Live 2026-09-26 (Codex/Grok game, t24, seat 0 sitting on it): the PlayerChange
-- context answers IsHidden() == true while it is modal and its MainContainer is visible, so
-- screens.PlayerChange read false and turn_state carried nothing about it -- the reader saw
-- my_turn=true, paused=true, popup_up=true, an empty todo and no blocker, and had to guess. The rule below
-- is game.py's player_change_pending() (modal + visible container), asked from InGame in the same trip.
-- The game pauses itself while this is up (Game.SetPausePlayer in OnPlayerChange), so `paused` is its
-- shadow; this is the screen itself. Nothing acts until OnContinue(): wait_for_my_turn presses it.
function H.hand_off_up()
  local ok, up = pcall(function()
    local pc = ContextPtr:LookUpControl("/InGame/PlayerChange")
    if pc == nil then return false end
    local main = ContextPtr:LookUpControl("/InGame/PlayerChange/MainContainer")
    local modal = UIManager:IsModal(pc)
    if main ~= nil then return (modal and not main:IsHidden()) and true or false end
    return modal and true or false
  end)
  return (ok and up) and true or false
end

-- #38: deals and declarations of friendship about to lapse, on the status the seat reads every turn (the
-- city-state alliance warning already is). Mongolia t21-42: two embassy-for-gold deals lapsed and the seat
-- only learned it from the "expired" notification afterwards.
local function deal_item_summary(it)
  local s = (it.from_us and "we give " or "they give ") .. tostring(it.type)
  if it.resource then s = s .. " " .. tostring(it.resource) end
  if it.amount and it.amount ~= 0 then s = s .. " " .. tostring(it.amount) end
  return s
end

-- Deals with turns_left <= within. The rows come from current_deals, which loads each deal into the shared
-- scratch table and empties it afterwards; that is only done when the table holds nothing of this seat's and no
-- other seat's proposal is waiting (incoming_deal would load it), so an offer or a draft is never touched. nil
-- means "not read this time", {} means none.
function H.expiring_deals(pid, within)
  within = within or 3
  if not (UI and UI.GetScratchDeal and UI.GetNumCurrentDeals) then return nil end
  if H.pending_deal_from(pid) ~= nil then return nil end
  -- Occupied as this seat reads it: another pair's leftover table is not in the way (GitLab #172).
  if (H.incoming_deal(pid).n or 0) > 0 then return nil end
  local okn, n = pcall(function() return UI.GetNumCurrentDeals(pid) end)
  if not okn or type(n) ~= "number" then return nil end
  if n <= 0 then return {} end
  local r = H.current_deals(pid)
  if not (r and r.ok) then return nil end
  -- v258: a renewal accepted before the old deal ran out leaves both on the list until the turn ends (live
  -- t161 Venice: China's open-borders swap renewed at its own turn start, current_deals 161 and 186). The
  -- old row is then no warning: `renewed_until` names the new deal's end and nothing is to be re-offered.
  local function item_key(it)
    return tostring(it.type) .. "|" .. tostring(it.from_us) .. "|" .. tostring(it.resource) .. "|" .. tostring(it.amount)
  end
  local function renewed_until(d)
    local timed = {}
    for _, it in ipairs(d.items or {}) do
      if (tonumber(it.duration) or 0) > 0 then timed[#timed + 1] = item_key(it) end
    end
    if #timed == 0 or type(d.ends_on) ~= "number" then return nil end
    for _, d2 in ipairs(r.deals or {}) do
      if d2 ~= d and d2.other == d.other and type(d2.ends_on) == "number" and d2.ends_on > d.ends_on then
        local have = {}
        for _, it in ipairs(d2.items or {}) do have[item_key(it)] = true end
        local all = true
        for _, k in ipairs(timed) do if not have[k] then all = false break end end
        if all then return d2.ends_on end
      end
    end
    return nil
  end
  local out = {}
  for _, d in ipairs(r.deals or {}) do
    -- v250: permanent items (an embassy: duration 0) never expire; a deal made of them alone read as
    -- "ends this turn" the turn it was signed (live t145, Mongolia: Babylon's embassy swap, turns_left 0).
    local left
    if type(d.turns_left) == "number" and (tonumber(d.duration) or 0) > 0 then left = d.turns_left end
    for _, it in ipairs(d.items or {}) do
      if type(it.turns_left) == "number" and (tonumber(it.duration) or 0) > 0
         and (left == nil or it.turns_left < left) then left = it.turns_left end
    end
    if type(left) == "number" and left >= 0 and left <= within then
      local items = {}
      for _, it in ipairs(d.items or {}) do items[#items + 1] = deal_item_summary(it) end
      -- v256: open borders are committed too (live t159 Venice: the China swap two turns from its end was
      -- refused as "not legal", trade_catalog open_borders us/them both false), as are a research
      -- agreement and a defensive pact (one at a time); only gold per turn goes on a fresh table now.
      local until_ = renewed_until(d)
      if until_ then
        out[#out + 1] = { player_id = d.other, civ = d.civ, turns_left = left, ends_on = d.ends_on, items = items,
                          renewed = true, renewed_until = until_,
                          hint = "already renewed: the new deal runs to turn " .. tostring(until_) .. ", nothing to re-offer" }
      else
        local reoffer = type(d.ends_on) == "number" and (d.ends_on + 1) or nil
        out[#out + 1] = { player_id = d.other, civ = d.civ, turns_left = left, ends_on = d.ends_on, items = items,
                          reoffer_on = reoffer,
                          hint = "the AI usually offers the renewal itself at the turn the deal ends (a deal screen with renewal: true; "
                                 .. "answer(choice='accept')); if it does not, order(to='civ', action='propose_deal') on reoffer_on. "
                                 .. "A resource, open borders, a research agreement or a defensive pact it carries stays committed "
                                 .. "until then and is refused as not legal before; gold per turn can be re-offered now" }
      end
    end
  end
  return out
end

-- Declarations of friendship with met majors whose term (DOF_EXPIRATION_TIME - GetDoFCounter, the counter
-- war_consequences and relationship read) ends within `within` turns. Five by default: renewing is a
-- leader conversation, and IsDoFMessageTooSoon can grey that button out for a few turns.
function H.expiring_friendships(pid, within)
  within = within or 5
  local p = Players[pid]
  if not (p and p.IsDoF and p.GetDoFCounter and GameDefines and GameDefines.DOF_EXPIRATION_TIME) then return {} end
  local myTeam = Teams and Teams[p:GetTeam()]
  local out = {}
  for i = 0, (GameDefines.MAX_MAJOR_CIVS or 22) - 1 do
    local o = Players[i]
    if i ~= pid and o and o:IsAlive() and not (o.IsMinorCiv and o:IsMinorCiv()) then
      local okm, met = pcall(function() return myTeam:IsHasMet(o:GetTeam()) end)
      local okf, dof = pcall(function() return p:IsDoF(i) end)
      if okm and met and okf and dof then
        local okc, counter = pcall(function() return p:GetDoFCounter(i) end)
        local left = okc and type(counter) == "number" and (GameDefines.DOF_EXPIRATION_TIME - counter) or nil
        if left and left <= within then
          local e = { player_id = i, civ = o:GetCivilizationShortDescription(), turns_left = left,
                      hint = "the engine refuses a new declaration while this one runs (order(to='civ', action='friendship'): already friends): order(to='civ', action='friendship') the turn after it lapses, unless the AI asks first" }
          local okt, soon = pcall(function() return o:IsDoFMessageTooSoon(pid) end)
          if okt and soon then e.ask_too_soon = true end
          out[#out + 1] = e
        end
      end
    end
  end
  return out
end

function H.pause_player()
  local ok, v = pcall(function() return Game.GetPausePlayer() end)
  if ok and type(v) == "number" then return v end
  return -1
end

function H.turn_state(pid)
  local p = Players[pid]
  local net = Game.IsNetworkMultiPlayer()
  local sent = net and Network.HasSentNetTurnComplete() or false
  local mode = PreGame.IsHotSeatGame() and "hotseat" or (net and (PreGame.IsInternetGame() and "internet" or "lan")) or "single"
  local gs = Game.GetGameState()
  local blocking = p:GetEndTurnBlockingType()
  -- `todo`: everything that still needs a decision this turn, in one place, so a caller does not have
  -- to poll units()/cities()/overview() to find out why the turn will not end or what it is leaving
  -- idle: units awaiting orders (and which of them can take a promotion), cities with an empty
  -- production queue, and research unset. Computed only for the active seat on its own turn.
  local todo = H.todo(pid)
  local stale = H.stale_blocker(p, blocking, todo)
  local okp, popup_up = pcall(function() return UI.IsPopupUp() end)
  -- `a and b or nil` loses a false b: popup_up read as nil whenever no popup was up (v207-v213).
  if okp then popup_up = (popup_up == true) else popup_up = nil end
  -- v214: the popup screens in the same read (they used to be eight more round-trips from game.py).
  local flags = H.modal_flags()
  -- v217: the alerts (#39) and the bare happiness total ride on every status, for this seat only.
  local alerts, happiness, unhappy = H.status_alerts(pid)
  local t = {
    todo = todo,
    alerts = alerts, happiness = happiness, unhappy = unhappy,
    blocking_hint = stale or (blocking ~= -1 and H.blocking_hint(H.blocking_name(blocking)) or nil),
    blocking_stale = stale and true or nil,
    popup_up = popup_up,
    active_player = Game.GetActivePlayer(), my_turn = Game.GetActivePlayer() == pid and p:IsTurnActive() and not sent,
    turn = Game.GetGameTurn(), blocking = blocking, blocking_name = H.blocking_name(blocking),
    num_units_needing_moves = p.GetNumUnitsNeedingMoves and p:GetNumUnitsNeedingMoves() or nil,
    processing = Game.IsProcessingMessages(), paused = Game.IsPaused(), hotseat = PreGame.IsHotSeatGame(),
    mode = mode, turn_complete_sent = sent,
    -- v288 (#96): the Dawn of Man splash. loadscreen.lua's OnSequenceGameInitComplete pauses a single-player
    -- game with Game.SetPausePlayer(activePlayer) and waits for its button; nothing else pauses a single-player
    -- game, so paused-by-this-seat outside hotseat and multiplayer IS the splash. A hand-started game sat on it
    -- for every client (Claude Code, Grok, Codex) because only the harness's own load pressed the button.
    load_screen_pending = (mode == "single" and Game.IsPaused() and H.pause_player() == pid) or false,
    -- v246: whether the seat on screen still holds its turn. In hotseat the active player stays the last human
    -- while the AIs move after it ended its turn, so a waiting seat used to be told only "seat N is on screen"
    -- for the whole AI round (live t135: five minutes of it); false here means the AIs are moving.
    active_turn_active = (function()
      local ok, v = pcall(function() local a = Players[Game.GetActivePlayer()]; return a and a:IsTurnActive() or false end)
      return ok and v or nil
    end)(),
    simultaneous = net and Game.IsOption(GameOptionTypes.GAMEOPTION_SIMULTANEOUS_TURNS) or false,
    dynamic_turns = net and Game.IsOption(GameOptionTypes.GAMEOPTION_DYNAMIC_TURNS) or false,
    turn_timer = net and Game.IsOption(GameOptionTypes.GAMEOPTION_END_TURN_TIMER_ENABLED) or false,
    everyone_connected = net and Network.IsEveryoneConnected() or nil,
    game_state = gs, game_state_name = H.game_state_name(gs), game_over = gs == GameplayGameStateTypes.GAMESTATE_OVER,
    alive = p:IsAlive(), pending_popups = H.pending_popups(pid), pending_deal_from = H.pending_deal_from(pid),
    notifications = H.notification_counts(p),
  }
  for _, k in ipairs(H.MODAL_FLAG_KEYS) do t[k] = flags[k] end
  -- v219 (#38): only on this seat's own turn, like todo; empty lists stay off the status.
  if todo then
    local deals = H.expiring_deals(pid)
    if deals and #deals > 0 then t.expiring_deals = deals end
    local dofs = H.expiring_friendships(pid)
    if #dofs > 0 then t.expiring_friendships = dofs end
    -- v265: the wars this seat is in and whether peace can be asked for (the leader screen's Negotiate Peace gate).
    local ok, wars = pcall(H.wars, pid)
    if ok and wars then t.wars = wars end
  end
  if t.game_over then
    -- GitLab #92 (live Assyria t273, after the Science Victory): the status kept ENDTURN_BLOCKING_LEAGUE_CALL_FOR_
    -- PROPOSALS, its hint and a Crossbowman in todo.units beside the game_over gate. Nothing is pending in a
    -- finished game; the engine's stale blocker is not a chore.
    t.blocking, t.blocking_name, t.blocking_hint, t.blocking_stale = -1, "NO_ENDTURN_BLOCKING_TYPE", nil, nil
    t.todo = { units = {}, promotions = {}, cities = {}, research_unset = false }
    t.expiring_deals, t.expiring_friendships, t.wars, t.alerts = nil, nil, nil, nil
    t.num_units_needing_moves = 0
  end
  return t
end

-- The Notification Log (notificationlogpopup.lua): every entry the gamecore still holds, newest
-- first, dismissed ones included -- that is the whole point of the screen. `turn_digest` reports only
-- the undismissed ones, because those are what the panel is currently showing, so anything read once
-- and dismissed had nowhere to be read again (live t233: 3 live, 99 held).
function H.notification_log(pid, limit, include_dismissed)
  local p = Players[pid]
  if not p or not p.GetNumNotifications then return { ok = false, err = "no notification list" } end
  local ok, n = pcall(function() return p:GetNumNotifications() end)
  if not ok or type(n) ~= "number" then return { ok = false, err = "no notification list" } end
  if include_dismissed == nil then include_dismissed = true end
  limit = (type(limit) == "number" and limit > 0) and limit or 40
  -- The engine's list gives text alone; the digest's hook saw each notice with its type and data words. Join by
  -- notification id (GetNotificationIndex(i) is the hook's id: live t238, 862/863) for what the hook located, and
  -- re-read a Great Person notice now: the person it announced may have been spent since (live t238: two notices,
  -- no unit behind either).
  local located = {}
  for _, ev in ipairs(H.events or {}) do
    local d = type(ev) == "table" and ev.kind == "notification" and type(ev.data) == "table" and ev.data or nil
    if d and d.player == pid and d.id ~= nil then located[d.id] = d end
  end
  local great_person = NotificationTypes and NotificationTypes.NOTIFICATION_GREAT_PERSON_ACTIVE_PLAYER or nil
  local out, skipped = {}, 0
  for i = n - 1, 0, -1 do
    if #out >= limit then break end
    local dismissed = false
    pcall(function() dismissed = p:GetNotificationDismissed(i) and true or false end)
    if dismissed and not include_dismissed then
      skipped = skipped + 1
    else
      local e = { i = i, dismissed = dismissed }
      pcall(function() e.turn = p:GetNotificationTurn(i) end)
      pcall(function() e.summary = p:GetNotificationSummaryStr(i) end)
      pcall(function() e.text = p:GetNotificationStr(i) end)
      if e.summary == e.text then e.summary = nil end
      pcall(function()
        local d = located[p:GetNotificationIndex(i)]
        if not d then return end
        for _, k in ipairs({ "unit", "unit_id", "x", "y", "city_id", "sites" }) do if d[k] ~= nil then e[k] = d[k] end end
        if great_person ~= nil and d.ntype == great_person then
          local g = H.great_person_facts(p, d.d1, e.turn)
          if g then
            e.unit = g.unit
            if g.unit_id then
              e.unit_id, e.x, e.y = g.unit_id, g.x, g.y
            else
              e.of_type_now = g.of_type_now
              if d.unit_id then e.unit_gone = true end  -- the hook saw it born; it is not among my units now
            end
          end
        end
      end)
      out[#out + 1] = e
    end
  end
  return { ok = true, held = n, shown = #out, dismissed_skipped = skipped > 0 and skipped or nil,
           notifications = out }
end

-- The notification panel's load, for crash correlation: the gamecore keeps a ~100-entry history ring
-- and dismisses entries by itself after about a turn (live t315: 99 held, 10 live), so `live` is what
-- the panel is actually showing.
function H.notification_counts(p)
  if not p.GetNumNotifications then return nil end
  local ok, n = pcall(function() return p:GetNumNotifications() end)
  if not ok or type(n) ~= "number" then return nil end
  local live = 0
  for i = 0, n - 1 do
    local okd, d = pcall(function() return p:GetNotificationDismissed(i) end)
    if okd and d == false then live = live + 1 end
  end
  return { held = n, live = live }
end

-- Human players in a network game: who is connected / has ended their turn (for "waiting on" digests).
-- The in-game player list (mplist.lua) names every human seat but shows the civ only once met.
function H.net_players(pid)
  local out = {}
  local me = Players[pid or Game.GetActivePlayer()]
  local myTeam = me and Teams[me:GetTeam()]
  for i = 0, GameDefines.MAX_MAJOR_CIVS - 1 do
    local p = Players[i]
    if p and p:IsEverAlive() and p:IsHuman() then
      local met = myTeam == nil or p:GetTeam() == me:GetTeam() or myTeam:IsHasMet(p:GetTeam())
      local nick = p:GetNickName()
      if (nick == nil or nick == "") and met then nick = p:GetName() end  -- GetName falls back to the leader: civ-revealing
      out[#out+1] = { id = i, name = nick, met = met,
                      civ = met and L(p:GetCivilizationShortDescriptionKey()) or nil, alive = p:IsAlive(),
                      turn_active = p:IsTurnActive(), connected = Network.IsPlayerConnected(i),
                      ended_turn = p.HasReceivedNetTurnComplete and p:HasReceivedNetTurnComplete() or nil }
    end
  end
  return out
end

-- What the screen shows anyone: the turn, whether the game is over, whose turn it is (seat-free).
function H.game_facts()
  local over = false
  pcall(function() over = Game.GetGameState() == GameplayGameStateTypes.GAMESTATE_OVER end)
  return { turn = Game.GetGameTurn(), over = over, active_player = Game.GetActivePlayer() }
end

-- The popup records the screens dismissed by hand (a chooser closed with OnClose only dequeues the popup).
function H.drop_popups_matching(pattern, pid)
  for k in pairs(H.popups) do
    local n = H.enum_name("popup", ButtonPopupTypes, k) or ""
    if n:find(pattern, 1, true) then H.popups[k] = nil end
  end
  return true
end

function H.drop_popup(key, pid)
  local k = key
  if type(key) == "string" then k = ButtonPopupTypes[key] end
  if k ~= nil then H.popups[k] = nil end
  return true
end

function H.popup_processed(popup_type, pid)
  -- exactly what a screen's close handler does: Processed for the type (citystategreetingpopup.lua and siblings)
  Events.SerialEventGameMessagePopupProcessed.CallImmediate(popup_type, 0)
  return true
end

function H.popup_up(pid) return UI.IsPopupUp() and true or false end

function H.current_research(pid) return Players[pid]:GetCurrentResearch() end

-- The stock end-turn button's path to a chooser the engine will not raise by itself (archaeology: the
-- archaeologist id is published only when the completed-dig notification is activated).
function H.activate_blocking_notification(blocking_name, pid)
  local p = Players[pid]
  if Game.GetActivePlayer() == pid and p:GetEndTurnBlockingType() == EndTurnBlockingTypes[blocking_name] then
    UI.ActivateNotification(p:GetEndTurnBlockingNotificationIndex()); return true
  end
  return false
end

function H.turn_started_this_turn(pid)
  local seq = (H.cursors and H.cursors[pid]) or 0
  local t = Game.GetGameTurn()
  for _, e in ipairs(H.events_since(seq, pid)) do
    if e.kind == "turn_start" and e.turn == t and e.data and e.data.player == pid then return true end
  end
  return false
end

-- The end-turn order (harness/game_parts/turn.py _end_turn_send): the engine's own gates, then the harness's.
function H.end_turn_send(autosave, pid)
  if Game.GetActivePlayer() ~= pid then return { ok = false, err = "this seat is not active" } end
  local p = Players[pid]
  if Game.IsPaused() then return { ok = false, err = "game is paused" } end
  if not p:IsTurnActive() then return { ok = false, err = "turn not active" } end
  if Game.IsProcessingMessages() then return { ok = false, err = "game is processing messages; retry" } end
  if Game.IsNetworkMultiPlayer() and Network.HasSentNetTurnComplete() then
    return { ok = false, err = "turn-complete already sent; waiting for the other players" }
  end
  local blocking = p:GetEndTurnBlockingType()
  local todo = H.todo(pid)
  -- GitLab #23: ENDTURN_BLOCKING_UNITS with no ready unit is a reading the engine froze while a popup was up,
  -- not a unit that needs orders. Refusing on it named an empty todo; the popup (swept by end_turn() before
  -- this call, or waiting for an answer) is the real blocker. v254: the same for PRODUCTION with no empty
  -- city and RESEARCH with research set (live t153, Mongolia).
  local stale = H.stale_blocker(p, blocking, todo)
  if blocking ~= -1 and not stale then
    local name = H.blocking_name(blocking)
    return { ok = false, err = "turn has unresolved decisions: " .. H.blocking_hint(name), blocking = name, todo = todo }
  end
  local popups = H.pending_popups(pid)
  if #popups > 0 then
    return { ok = false, err = "popup needs attention" .. (stale and (" (" .. H.blocking_name(blocking) .. " is a stale reading the engine re-evaluates once the popup is processed)") or ""),
             pending_popups = popups, blocking = stale and H.blocking_name(blocking) or nil, blocking_stale = stale and true or nil }
  end
  -- GitLab #137: End Turn disabled with nothing on screen is the leader view a previous exit left open.
  local stale_view = H.clear_stale_leader_view(pid)
  if autosave and not Game.IsNetworkMultiPlayer() then UI.QuickSave() end
  Game.DoControl(GameInfoTypes.CONTROL_ENDTURN)
  return { ok = true, blocking_before = blocking, blocking_stale = stale and true or nil,
           stale_leader_view_cleared = stale_view.cleared or nil,
           turn_complete_sent = Game.IsNetworkMultiPlayer() and Network.HasSentNetTurnComplete() or false }
end

-- The in-game Quick Save button / F5 (gamemenu.lua OnQuickSave): the active seat's save slot.
function H.quick_save(pid)
  if Game.GetActivePlayer() ~= pid then return { ok = false, err = "this seat is not active" } end
  UI.QuickSave()
  return { ok = true, turn = Game.GetGameTurn() }
end

function H.note_reconnected(pid)
  H.record("reconnected", { turn = Game.GetGameTurn() })
  return true
end

-- Major civs the engine considers human-controlled, lowest id first (seat detection in a solo game).
function H.human_seats()
  local n = (GameDefines and GameDefines.MAX_MAJOR_CIVS) or 22
  local ids = {}
  for i = 0, n - 1 do
    local p = Players[i]
    if p and p:IsAlive() and p:IsHuman() then ids[#ids + 1] = i end
  end
  return ids
end

-- GitLab #137: a leader left on screen here is still "open" to the exe in the next game loaded, with its End
-- Turn disabled and no blocker named; leave the view first (what the screen's back button does).
function H.exit_to_main_menu(pid)
  if Game.GetActivePlayer() ~= pid then return { ok = false, err = "this seat is not active" } end
  local left = false
  if H.leader_view_up() then
    pcall(function() UI.RequestLeaveLeader() end)
    left = true
  end
  Events.ExitToMainMenu()
  return { ok = true, left_leader_view = left or nil }
end
