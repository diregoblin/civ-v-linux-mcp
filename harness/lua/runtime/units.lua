-- Shared by earlier fragments (load order: harness/runtime_source.py MANIFEST).
local L, info_type, short = H._ns.L, H._ns.info_type, H._ns.short

-- militaryoverview.lua UpdateScreen / toppanel.lua UnitSupplyString: how many units the empire
-- can support. Over the cap is extra gold (CalculateUnitSupply, already in gold_breakdown) and a
-- city-production penalty (GetUnitProductionMaintenanceMod). A human opens Military Overview for
-- the handicap/cities/population split; the top bar only appears once already over.
function H.unit_supply(pid)
  local p = Players[pid]
  if not p then return nil end
  local function n(fn)
    local ok, v = pcall(fn)
    if ok then return v end
  end
  local cap = n(function() return p:GetNumUnitsSupplied() end)
  local used = n(function() return p:GetNumUnits() end)
  if cap == nil and used == nil then return nil end
  local out = {
    cap = cap, used = used,
    from_handicap = n(function() return p:GetNumUnitsSuppliedByHandicap() end),
    from_cities = n(function() return p:GetNumUnitsSuppliedByCities() end),
    from_population = n(function() return p:GetNumUnitsSuppliedByPopulation() end),
  }
  local deficit = n(function() return p:GetNumUnitsOutOfSupply() end)
  if deficit and deficit > 0 then
    out.deficit = deficit
    local pen = n(function() return p:GetUnitProductionMaintenanceMod() end)
    if pen and pen ~= 0 then out.production_penalty = pen end
  elseif cap and used then
    out.remaining = cap - used
  end
  return out
end

-- trade_routes_used counts trade UNITS, not routes: a caravan sleeping in a city fills a slot while earning
-- nothing (live t324: "6 of 6 used", two caravans idle in Nanjing, four real routes). A unit on a route is
-- automated; one that is not is idle and can take a route (establish_trade_route).
-- The engine's gate for training another caravan / cargo ship (CvPlayer::canTrain ->
-- CvPlayerTrade::GetNumTradeRoutesRemaining(false)): routes possible minus trade units alive minus
-- trade-unit orders queued in any of this player's cities (CvCity::getNumTrainUnitAI(UNITAI_TRADE_UNIT);
-- puppets' queues count too). Player:GetNumInternationalTradeRoutesUsed is the alive half only, so a
-- queued Caravan takes a slot the overview never shows as taken (live t139: Venice "4 of 8" with
-- CanTrain false and no rule named; t154: Mongolia 5 alive of 5 refused, Venice 4 of 8 with nothing
-- queued allowed). Lua has no accessor for the remaining count (GetNumAvailableTradeUnits(domain) is
-- the top bar's count of idle units), so the queues are read the way the engine reads them.
function H.trade_unit_count(p)
  local out = { alive = 0, queued = 0 }
  pcall(function() for u in p:Units() do if u:IsTrade() then out.alive = out.alive + 1 end end end)
  pcall(function()
    local train = OrderTypes and OrderTypes.ORDER_TRAIN or 0
    for c in p:Cities() do
      for i = 0, c:GetOrderQueueLength() - 1 do
        local kind, data = c:GetOrderFromQueue(i)
        if kind == train and data ~= nil then
          local u = GameInfo.Units[data]
          if u and (u.Trade == true or u.Trade == 1 or u.DefaultUnitAI == "UNITAI_TRADE_UNIT") then
            out.queued = out.queued + 1
          end
        end
      end
    end
  end)
  local okp, possible = pcall(function() return p:GetNumInternationalTradeRoutesAvailable() end)
  if okp and type(possible) == "number" then
    out.possible = possible
    out.remaining = possible - out.alive - out.queued
  end
  return out
end

-- A production tooltip as one sentence: [NEWLINE]s and the other [TAGS] gone, spaces collapsed.
function H.tooltip_text(t)
  if type(t) ~= "string" then return "" end
  local s = t:gsub("%[NEWLINE%]", " ")
  s = s:gsub("%[[^%]]*%]", "")
  s = s:gsub("%s+", " ")
  s = s:gsub("^%s+", "")
  s = s:gsub("%s+$", "")
  return s
end

-- Past the slot count the engine has a second gate per domain (CvCity::canTrain -> CvPlayerTrade::
-- CanCreateTradeRoute(domain)): a trade unit is trainable only while some city of mine could start a new route
-- of its kind right now. Player:GetTradeRoutesAvailable() is not that test: live t152 it listed 5 rows for
-- Venice (4 of 8 slots free, nothing queued) while CanTrain was false for Caravan and Cargo Ship in every city
-- with "You cannot construct this trade unit because there are no available land/sea trade routes" -- the
-- rule behind the t139 refusal. So the gate is asked directly, city by city, and its own sentences kept
-- (CanTrainTooltip; the limit sentence is the slot rule, anything else is this one or a plain prerequisite).
function H.trade_unit_gate(p)
  local out = { trainable = {}, engine_reason = {} }
  for _, kind in ipairs({ { "caravan", "UNIT_CARAVAN" }, { "cargo_ship", "UNIT_CARGO_SHIP" } }) do
    local key, utype = kind[1], kind[2]
    local info = GameInfo.Units[utype]
    if info and info.ID then
      local can, tips, seen = false, {}, {}
      pcall(function()
        for c in p:Cities() do
          if c:CanTrain(info.ID, 0) then can = true; return end
          if c.CanTrainTooltip then
            local t = H.tooltip_text(c:CanTrainTooltip(info.ID))
            if t ~= "" and not seen[t] then seen[t] = true; tips[#tips + 1] = t end
          end
        end
      end)
      out.trainable[key] = can
      if not can and #tips > 0 then out.engine_reason[key] = table.concat(tips, " / ") end
    end
  end
  return out
end

function H.idle_trade_units(p, pid)
  local out = {}
  for u in p:Units() do
    if u:IsTrade() and not u:IsAutomated() then
      local e = { unit_id = u:GetID(), type = short(GameInfo.Units[u:GetUnitType()].Type),
                  x = u:GetX(), y = u:GetY() }
      -- "Idle" is not always "ready": a caravan walking back to a city cannot be given a route
      -- from where it stands, and the overview used to make all three look equally available.
      local plot = u:GetPlot()
      local city = plot and plot:IsCity() and plot:GetPlotCity()
      if city and city:GetOwner() == (pid or p:GetID()) then e.in_city = city:GetName()
      else
        e.in_city = false
        pcall(function()
          local why = H.no_trade_route_reason(u, p, pid or p:GetID())
          e.hint = why.hint
          if why.nearest_city then e.nearest_city = why.nearest_city end
        end)
      end
      out[#out + 1] = e
    end
  end
  return out
end

-- A spy sitting unassigned earns nothing and nothing else says so: no end-turn blocker, no
-- notification after the one that announced it. Same shape (and same hazard) as an idle caravan.
-- Live t212: a Special Agent had been Unassigned for an unknown number of turns while the empire
-- was behind in science with a tech-steal available.
function H.idle_spies(pid)
  local out = {}
  for _, s in ipairs(H.spies(pid) or {}) do
    if s.state_key == "TXT_KEY_SPY_STATE_UNASSIGNED" then
      out[#out + 1] = { agent_id = s.agent_id, name = s.name, rank = s.rank }
    end
  end
  return out
end

-- The promotion chooser as a human reads it: the name on the button and the effect text under it,
-- not just the enum. "PROMOTION_DOGFIGHTING_1" beside "PROMOTION_INTERCEPTION_1" is not a choice
-- anyone can make -- the panel says "+33% Combat Strength when intercepting" against "+33% chance
-- to intercept". Same shape as available_policies.adoptable and available_research help.
-- Found live t184 (Shoshone vs the Inca): a Fighter earned a promotion and the three options came
-- back as bare type strings.
function H.promotion_options(u)
  local out = {}
  if not (u and u.CanPromote and GameInfo and GameInfo.UnitPromotions) then return out end
  for promo in GameInfo.UnitPromotions() do
    if promo and promo.ID and u:CanPromote(promo.ID) then
      -- The name and the effect line under it (v216 dropped the line for reference("promotions"); GitLab #132 put it back).
      out[#out + 1] = {
        promotion = promo.Type,
        -- GitLab #132 (Siam t27): the numbers were a 20 KB reference read away (and that read was cut short)
        effect = promo.Help and H.L(promo.Help) or nil,
        name = promo.Description and L(promo.Description) or nil,
      }
    end
  end
  return out
end

-- Promotions currently on a unit (the unit panel list). Compact short names.
function H.unit_promotions(u)
  local out = {}
  if not (u and u.IsHasPromotion and GameInfo and GameInfo.UnitPromotions) then return out end
  for promo in GameInfo.UnitPromotions() do
    if promo and promo.ID and u:IsHasPromotion(promo.ID) then
      out[#out + 1] = short(promo.Type)
    end
  end
  return out
end

-- v248: whose land a unit stands on, when it is not the seat's own. The map shows every border and the
-- notification ("Trespassing in Kiev!") names the city-state but not the unit; a human sees the unit inside
-- the border. nil on the seat's own or unowned land; the owner is labelled as the map would (unmet: "Unknown").
function H.plot_territory(plot, pid)
  local ok, out = pcall(function()
    local o = plot and plot:GetOwner() or -1
    if o == nil or o < 0 or o == pid then return nil end
    local t = { player_id = o, owner = H.owner_label(o, pid) }
    local po = Players[o]
    if po and po.IsMinorCiv and po:IsMinorCiv() then t.city_state = true end
    return t
  end)
  return ok and out or nil
end

local HOLD_ACTIVITIES = { ACTIVITY_HOLD = true, ACTIVITY_SLEEP = true, ACTIVITY_HEAL = true, ACTIVITY_SENTRY = true,
                          ACTIVITY_INTERCEPT = true }
function H.unit_activity(u)
  local ok, name = pcall(function()
    local a = u:GetActivityType()
    local n = H.enum_name and H.enum_name("ActivityTypes", ActivityTypes, a)
    return type(n) == "string" and n or nil
  end)
  if ok and name then return (name:gsub("^ACTIVITY_", "")) end
  return nil
end
function H.unit_holding(u)
  local ok, v = pcall(function()
    if u:GetFortifyTurns() > 0 then return true end
    local n = H.enum_name and H.enum_name("ActivityTypes", ActivityTypes, u:GetActivityType())
    return HOLD_ACTIVITIES[n] == true
  end)
  return ok and v == true or false
end
-- GitLab #176 (Celts t7): MISSION_FORTIFY on a Warrior that had moved answered SLEEP_OR_FORTIFY with its move left,
-- and units() read activity SLEEP, fortified false. The engine's fortify IS ACTIVITY_SLEEP plus a fortify count
-- (GetFortifyTurns) that grows by one at each of the unit's turn starts up to MAX_FORTIFY_TURNS, worth
-- FORTIFY_MODIFIER_PER_TURN percent each (the unit list and the flag say "Fortified" once it is above 0;
-- militaryoverview.lua / unitlist.lua). A unit that can fortify is never put to plain sleep (its Sleep button is
-- Fortify), so asleep with a count of 0 is a fortify that starts counting next turn. The moves are not spent, and
-- a unit in any hold is not IsReadyToMove: todo.units (turn.lua) no longer lists it. The order's reply and the
-- unit list read these same facts, so they say the same thing.
function H.unit_fortifying(u)
  local ok, v = pcall(function()
    return u:GetFortifyTurns() == 0 and u:IsEverFortifyable() and H.unit_activity(u) == "SLEEP"
  end)
  return ok and v == true or false
end
function H.unit_hold_state(u)
  local out = { activity = H.unit_activity(u) }
  pcall(function() out.fortify_turns = u:GetFortifyTurns() end)
  pcall(function() out.fortifyable = u:IsEverFortifyable() end)
  pcall(function() out.needs_orders = u:IsReadyToMove() and not u:IsAutomated() and not u:IsDelayedDeath() end)
  pcall(function() out.fortify_max, out.fortify_pct = GameDefines.MAX_FORTIFY_TURNS, GameDefines.FORTIFY_MODIFIER_PER_TURN end)
  return out
end

function H.units(pid)
  local p = Players[pid]
  local out = {}
  for u in p:Units() do
    local plot = u:GetPlot()
    local mission = u.GetMissionType and u:GetMissionType() or -1
    local e = {
      id = u:GetID(), type = short(info_type(GameInfo.Units, u:GetUnitType())), name = u:GetName(),
      x = u:GetX(), y = u:GetY(), moves = u:MovesLeft() / GameDefines.MOVE_DENOMINATOR, max_moves = u:MaxMoves() / GameDefines.MOVE_DENOMINATOR,
      hp = u:GetCurrHitPoints(), max_hp = u:GetMaxHitPoints(), strength = u:GetBaseCombatStrength(),
      ranged = H.ranged_strength(u), range = (u.Range and u:Range() or 0),
      embarked = u:IsEmbarked(), fortified = u:GetFortifyTurns() > 0, automated = u:IsAutomated(), ready = u:IsReadyToMove(),
      -- GitLab #128 (Siam t24): a sleeping Scout read fortified false while MISSION_FORTIFY was refused as "already
      -- holding" -- a scout cannot fortify, it sleeps. `activity` is the engine's word; `holding` is true for any hold.
      activity = H.unit_activity(u), holding = H.unit_holding(u),
      fortifying = H.unit_fortifying(u) or nil,   -- #176: fortify ordered, the bonus counts from its next turn start
      garrisoned = (u.IsGarrisoned and u:IsGarrisoned()) or false,
      mission = mission, domain = short(info_type(GameInfo.Domains, u:GetDomainType())),
      level = u.GetLevel and u:GetLevel() or nil, xp = u.GetExperience and u:GetExperience() or nil,
      can_found = (u.CanFound and plot and u:CanFound(plot)) or false,
      in_city = plot and plot:IsCity() or false,
      going_to = H.going_to(u, pid),   -- v218 (#37): the standing move_unit destination, when one is stored
      territory = H.plot_territory(plot, pid),   -- v248: another player's land under the unit, if any
    }
    -- Unit panel worker-progress line: "Trading Post (6)" from GetBuildType + GetBuildTurnsLeft (+1).
    if mission and mission ~= -1 then
      local okm, mn = pcall(function() return H.enum_name("MissionTypes", MissionTypes, mission) end)
      if okm and type(mn) == "string" then e.mission_name = mn end
    end
    pcall(function()
      local b = H.unit_build(u, pid)   -- builds.lua: the unit's own build type, or the dig on its plot (#140)
      if not b then return end
      e.build = b.build
      e.build_turns_left = b.turns_left
    end)
    -- The unit flag and panel name a religious unit by its faith ("Missionary (Tengriism)"), and the
    -- religion it carries is the one it spreads -- not necessarily ours. Live t205: a Missionary
    -- carrying Catholicism sat in a puppet and nothing in units/available_unit_actions said which
    -- religion it would spread, so the charge went into re-converting a city to a rival's faith.
    pcall(function()
      local rel = u.GetReligion and u:GetReligion() or -1
      if not rel or rel < 0 then return end
      e.religion = Game.GetReligionName and H.L(Game.GetReligionName(rel)) or rel
      e.religion_id = rel
      if u.GetSpreadsLeft then e.spreads_left = u:GetSpreadsLeft() end
    end)
    local promos = H.unit_promotions(u)
    if #promos > 0 then e.promotions = promos end
    if u.ExperienceNeeded and e.xp then
      local ok, need = pcall(function() return u:ExperienceNeeded() end)
      if ok and need then e.xp_needed = need end
    end
    if u.GetUpgradeUnitType then
      local ok, ut = pcall(function() return u:GetUpgradeUnitType() end)
      if ok and ut and ut >= 0 and GameInfo.Units[ut] then
        e.upgrade_to = GameInfo.Units[ut].Type
        local okp, price = pcall(function() return u:UpgradePrice(ut) end)
        if okp then e.upgrade_gold = price end
        local okc, can = pcall(function() return u:CanUpgradeRightNow() end)
        if okc then e.can_upgrade = can end
        if okc and not can then
          local okb, blocked = pcall(H.upgrade_blocked, u, pid, price, ut)
          if okb and blocked and #blocked > 0 then e.upgrade_blocked = blocked end
        end
      end
    end
    out[#out + 1] = e
  end
  return out
end

-- v254: why the unit panel's Upgrade button is greyed (unitpanel.lua COMMAND_UPGRADE, the red
-- strDisabledString): outside my territory, an air unit outside a city, not enough gold, a strategic
-- resource short (each one, with how many), or a second unit of the same kind on the plot. Live t153
-- Venice: three Warriors read `can_upgrade false` with 2500 gold in the bank and nothing said why
-- (no Iron). The panel's own sentences ride in `text`; the structured fields are the facts behind
-- them. A unit that has already moved this turn gets `moved` -- the engine's gate the panel never
-- spells out, since its button is simply absent then.
function H.upgrade_blocked(u, pid, price, ut)
  local p = Players[pid]
  local plot = u:GetPlot()
  local out = {}
  -- The panel shows no Upgrade button at all while the target cannot be trained yet (live t153: a
  -- Crossbowman's Gatling Gun before Industrialization): the engine's CanTrain as the panel's visibility
  -- test asks it (bTestVisible: the tech counts, a missing resource does not -- that is the red line
  -- below), cost and the upgrade chain ignored; the target's own prerequisite tech is named when the
  -- team lacks it. Live: with bTestVisible false the Warrior's Swordsman read "cannot be trained yet"
  -- in place of "You need 1 Iron".
  if type(ut) == "number" and p and p.CanTrain and GameInfo and GameInfo.Units and GameInfo.Units[ut] then
    local okc, can = pcall(function() return p:CanTrain(ut, false, true, true, true) end)
    if okc and can == false then
      local row_u = GameInfo.Units[ut]
      local e = { reason = "unavailable", unit = row_u.Type,
                  text = (row_u.Description and L(row_u.Description) or row_u.Type) .. " cannot be trained yet" }
      pcall(function()
        local tech = row_u.PrereqTech
        if tech and GameInfoTypes and GameInfoTypes[tech] ~= nil then
          local team = Teams[p:GetTeam()]
          if team and team.GetTeamTechs and not team:GetTeamTechs():HasTech(GameInfoTypes[tech]) then
            e.prereq_tech = tech
            e.text = e.text .. " (needs " .. (GameInfo.Technologies and GameInfo.Technologies[tech] and
              L(GameInfo.Technologies[tech].Description) or tech) .. ")"
          end
        end
      end)
      out[#out + 1] = e
      return out
    end
  end
  local function row(reason, key, extra, ...)
    local e = { reason = reason }
    if key and Locale and Locale.ConvertTextKey then
      -- The panel's own call, arguments included (the resources line takes the "1 Iron" list).
      local okt, text = pcall(Locale.ConvertTextKey, key, ...)
      if okt and type(text) == "string" and text ~= "" and text ~= key then e.text = text end
    end
    if extra then for k, v in pairs(extra) do e[k] = v end end
    out[#out + 1] = e
  end
  if plot and plot:GetOwner() ~= u:GetOwner() then
    row("territory", "TXT_KEY_UPGRADE_HELP_DISABLED_TERRITORY", { owner = plot:GetOwner() })
  end
  if plot and DomainTypes and u:GetDomainType() == DomainTypes.DOMAIN_AIR and not plot:IsCity() then
    row("city", "TXT_KEY_UPGRADE_HELP_DISABLED_CITY")
  end
  local gold = p and p.GetGold and p:GetGold() or nil
  if type(price) == "number" and type(gold) == "number" and price > gold then
    row("gold", "TXT_KEY_UPGRADE_HELP_DISABLED_GOLD", { price = price, gold = gold })
  end
  if GameInfo and GameInfo.Resources and u.GetNumResourceNeededToUpgrade then
    local short_list, names = {}, {}
    for res in GameInfo.Resources() do
      local okn, need = pcall(function() return u:GetNumResourceNeededToUpgrade(res.ID) end)
      if okn and type(need) == "number" and need > 0 then
        local have = p:GetNumResourceAvailable(res.ID)
        if need > have then
          short_list[#short_list + 1] = { resource = short(res.Type), needed = need, available = have }
          names[#names + 1] = need .. " " .. (res.Description and L(res.Description) or short(res.Type))
        end
      end
    end
    if #short_list > 0 then
      row("resources", "TXT_KEY_UPGRADE_HELP_DISABLED_RESOURCES", { resources = short_list }, table.concat(names, ", "))
    end
  end
  if plot and plot.GetNumFriendlyUnitsOfType then
    local oks, n = pcall(function() return plot:GetNumFriendlyUnitsOfType(u) end)
    if oks and type(n) == "number" and n > 1 then
      row("stacking", "TXT_KEY_UPGRADE_HELP_DISABLED_STACKING", { units_on_plot = n })
    end
  end
  if #out == 0 and u.HasMoved and u:HasMoved() then
    row("moved", nil, { text = "the unit has already moved this turn: an upgrade needs its full moves" })
  end
  return out
end

-- The ids of my units, and a brief row per unit: read either side of a purchase to name the new unit.
function H.unit_ids(pid)
  local out = {}
  for u in Players[pid]:Units() do out[#out + 1] = u:GetID() end
  return out
end

function H.unit_brief_list(pid)
  local out = {}
  for u in Players[pid]:Units() do
    out[#out + 1] = { id = u:GetID(), x = u:GetX(), y = u:GetY(),
                      type = (GameInfo.Units[u:GetUnitType()] or {}).Type or u:GetUnitType() }
  end
  return out
end
