-- Shared by earlier fragments (load order: harness/runtime_source.py MANIFEST).
local L, info_type, short = H._ns.L, H._ns.info_type, H._ns.short

---------------------------------------------------------------- snapshots
-- Strategic resources as the top bar shows them to a human: only those the team has revealed, with the
-- spare count (negative = deficit: units/buildings consume more than we own; they fight/produce worse).
local function resource_revealed(res, team)
  -- Team:IsResourceRevealed does not exist in this build; the top bar's rule is "the team knows the
  -- resource's TechReveal tech" (resources without one are always shown).
  if not res.TechReveal then return true end
  local ok, revealed = pcall(function() return team:GetTeamTechs():HasTech(GameInfoTypes[res.TechReveal]) end)
  return ok and revealed
end

-- resourcelist.lua reads these five. A missing getter stays 0 so a partial mock still answers.
local function resource_amounts(p, id)
  local function num(fn)
    local ok, v = pcall(fn)
    if ok and type(v) == "number" then return v end
    return 0
  end
  return {
    available = num(function() return p:GetNumResourceAvailable(id, true) end),
    total = num(function() return p:GetNumResourceTotal(id, true) end),
    imported = num(function() return p:GetResourceImport(id) end),
    exported = num(function() return p:GetResourceExport(id) end),
    used = num(function() return p:GetNumResourceUsed(id) end),
  }
end

local function resource_entry(a, opts)
  opts = opts or {}
  local e = { available = a.available, total = a.total }
  if a.imported ~= 0 then e.imported = a.imported end
  if a.exported ~= 0 then e.exported = a.exported end
  -- The resource list prints "used" on a strategic row only. A zero is left off, as the screen does.
  if opts.used and a.used > 0 then e.used = a.used end
  if opts.last_copy and a.available == 1 then e.last_copy = true end
  return e
end

function H.strategic_resources(pid)
  local p = Players[pid]
  local team = Teams[p:GetTeam()]
  local out = {}
  if not (GameInfo and GameInfo.Resources) then return out end
  for res in GameInfo.Resources() do
    if res and res.ID and (res.ResourceClassType == "RESOURCECLASS_RUSH" or res.ResourceClassType == "RESOURCECLASS_MODERN")
       and not res.Type:find("ARTIFACTS") then  -- RESOURCE_HIDDEN_ARTIFACTS is an archaeology marker, not a stockpile
      if resource_revealed(res, team) then
        -- Top bar still lists a revealed strategic at zero. `used` is the resource-list column.
        out[short(res.Type)] = resource_entry(resource_amounts(p, res.ID), { used = true })
      end
    end
  end
  return out
end

-- The empire's unhappy tier as the top bar colours it: unhappy / very_unhappy / super_unhappy, nil when
-- content. happiness_breakdown and turn_state read the same three getters.
function H.unhappy_tier(p)
  local function is(name)
    local fn = p[name]
    if not fn then return false end
    local ok, v = pcall(fn, p)
    return ok and v == true
  end
  if is("IsEmpireSuperUnhappy") then return "super_unhappy" end
  if is("IsEmpireVeryUnhappy") then return "very_unhappy" end
  if is("IsEmpireUnhappy") then return "unhappy" end
  return nil
end

-- turn_status.alerts (#39; alerts_since above is the digest's engine banners, a different thing): facts a
-- seat once acted without because they sat on overview and not on the status the loop reads (2026-09-26, Mongolia t41: happiness 1, a Circus queued, todo empty, and the
-- turn looked quiet). Copied from the reads overview uses -- GetExcessHappiness, the unhappy tier,
-- strategic_resources -- with no advice and no build attached. A happiness row when the total is
-- LOW_HAPPINESS or below or a tier is set; a strategic_deficit row for each revealed strategic whose
-- available count is negative (an unrevealed resource stays unknown, as on the top bar). Alerts never
-- block end-turn and never enter todo. Returns the list plus the bare total and tier, which turn_state
-- carries on every status so game.py can tell a drop from a steady low number.
H.LOW_HAPPINESS = 2

function H.status_alerts(pid)
  local p = Players[pid]
  local out = {}
  local okh, happiness = pcall(function() return p:GetExcessHappiness() end)
  if not okh or type(happiness) ~= "number" then happiness = nil end
  local tier = H.unhappy_tier(p)
  if tier or (happiness and happiness <= H.LOW_HAPPINESS) then
    out[#out + 1] = { kind = "happiness", happiness = happiness, unhappy = tier }
  end
  -- A partial player (a mock, a seat mid-load) has no resource table: then there is no deficit to report.
  local oks, strat = pcall(H.strategic_resources, pid)
  if oks and type(strat) == "table" then
    local names = {}
    for name in pairs(strat) do names[#names + 1] = name end
    table.sort(names)
    for _, name in ipairs(names) do
      local e = strat[name]
      if type(e) == "table" and type(e.available) == "number" and e.available < 0 then
        out[#out + 1] = { kind = "strategic_deficit", resource = name, available = e.available,
                          deficit = -e.available, total = e.total, used = e.used }
      end
    end
  end
  -- v254: the top bar's unit-supply string (toppanel.lua UnitSupplyString: shown only while
  -- GetUnitProductionMaintenanceMod is nonzero) -- over the cap every city builds slower and the
  -- extra gold is already in gold_breakdown. Live t153 Venice: 15 units of 14 supplied read as
  -- `remaining -1` on overview and nowhere else; the engine's own deficit (military units only)
  -- was 0, so no row. The row names the penalty so a seat can weigh a disband or a gift.
  local oku, supply = pcall(H.unit_supply, pid)
  if oku and type(supply) == "table" and type(supply.deficit) == "number" and supply.deficit > 0 then
    out[#out + 1] = { kind = "unit_supply", deficit = supply.deficit, cap = supply.cap, used = supply.used,
                      production_penalty = supply.production_penalty }
  end
  return out, happiness, tier
end

-- Top-bar luxury list: owned / imported / exported copies. last_copy is the "selling this costs a
-- happiness luxury" warning the trade screen also shows.
function H.luxuries(pid)
  local p = Players[pid]
  local team = Teams[p:GetTeam()]
  local out = {}
  if not (GameInfo and GameInfo.Resources) then return out end
  for res in GameInfo.Resources() do
    if res and res.ID and res.ResourceClassType == "RESOURCECLASS_LUXURY" and resource_revealed(res, team) then
      local a = resource_amounts(p, res.ID)
      if a.available ~= 0 or a.total ~= 0 or a.imported ~= 0 or a.exported ~= 0 then
        out[short(res.Type)] = resource_entry(a, { last_copy = true })
      end
    end
  end
  return out
end

-- Resource list's bonus stack (resourcelist.lua): Wheat, Cattle, and the rest. The screen shows a
-- row only when the empire's total is above zero or something is being exported. A luxury or a
-- strategic is not repeated here. Unrevealed resources stay hidden, same as the top bar.
function H.bonus_resources(pid)
  local p = Players[pid]
  local team = Teams[p:GetTeam()]
  local out = {}
  if not (GameInfo and GameInfo.Resources) then return out end
  for res in GameInfo.Resources() do
    if res and res.ID and res.ResourceClassType == "RESOURCECLASS_BONUS" and resource_revealed(res, team) then
      local a = resource_amounts(p, res.ID)
      if a.total > 0 or a.exported > 0 then
        out[short(res.Type)] = resource_entry(a)
      end
    end
  end
  return out
end

-- The word a bare icon stands for where its name misleads: the faith icon is the dove, science the flask, a
-- happiness face carries a number ("Culture, Peace, Gold, Production, Research" for God-King, GitLab #103).
-- The same table as harness/game_parts/icon_words.py; tests/test_plain_text_icons.py holds both to it.
local ICON_WORDS = {
  PEACE = "Faith", RESEARCH = "Science", HAPPINESS_1 = "Happiness", HAPPINESS_3 = "Unhappiness",
  HAPPINESS_4 = "Unhappiness", GREATPEOPLE = "Great People", RANGE_STRENGTH = "Ranged Strength",
  TURNS_REMAINING = "Turns", INTERNATIONAL_TRADE = "Trade Route",
}
local function icon_word(name)
  local hit = ICON_WORDS[name]
  if hit then return hit end
  if name:sub(1, 4) == "RES_" then name = name:sub(5) end   -- a resource icon is its resource
  return (name:lower():gsub("_", " "):gsub("(%a)([%w]*)", function(a, b) return a:upper() .. b end))
end

-- Color, icon and Civilopedia-link tags off a screen string ("Construct a [LINK=IMPROVEMENT_FARM]Farm[\LINK]"
-- keeps its word). Same cleanup the league tooltips use.
local function plain_text(s)
  if type(s) ~= "string" or s == "" then return nil end
  s = s:gsub("%[NEWLINE%]", "\n")
  s = s:gsub("%[LINK=[^%]]*%]", ""):gsub("%[\\LINK%]", "")
  s = s:gsub("%[ICON_BULLET%]", "• ")
  -- An icon is normally followed by its word ("[ICON_GOLD] Gold"); one that stands alone before punctuation, the
  -- end, or another icon becomes its word, as harness.game_parts.support.plain_text does -- the great-work
  -- tooltip "+2 [ICON_CULTURE], +2 [ICON_TOURISM]" read "+2 , +2" (GitLab #148).
  local function bare(name) return " " .. icon_word(name) .. " " end
  for _ = 1, 4 do   -- a run of icons settles one per pass, the one before another icon first
    s = s:gsub("%[ICON_([A-Z0-9_]+)%](%s*)(%[ICON_)", function(name, _, nxt) return bare(name) .. nxt end)
    s = s:gsub("%[ICON_([A-Z0-9_]+)%](%s*)([,.;:%)])", function(name, _, punct) return bare(name) .. punct end)
    s = s:gsub("%[ICON_([A-Z0-9_]+)%](%s*)$", function(name) return bare(name) end)
  end
  s = s:gsub("%[ICON_[A-Z0-9_]+%]", "")
  s = s:gsub("%[COLOR:[^%]]+%]", "")
  s = s:gsub("%[COLOR_[A-Z0-9_]+%]", "")
  s = s:gsub("%[ENDCOLOR%]", "")
  s = s:gsub("[ \t]+\n", "\n"):gsub("\n[ \t]+", "\n"):gsub("  +", " "):gsub(" ([,.;:%)])", "%1")
  s = s:gsub("^%s+", ""):gsub("%s+$", "")
  if s == "" then return nil end
  return s
end

local function plain_key(key, ...)
  if not (Locale and Locale.ConvertTextKey) then return nil end
  local ok, s = pcall(Locale.ConvertTextKey, key, ...)
  if not ok then return nil end
  return plain_text(s)
end

-- Happiness tooltip (toppanel.lua HappinessTipHandler) plus the rows the Happiness screen
-- expands (happinessinfo.lua). Zero buckets are omitted. `difficulty` is that screen's residual
-- ("from Difficulty Level"), so anything the screen does not itemize — garrison happiness is the
-- usual one — sits in it, matching the number a human reads. A city row omits a zero the screen
-- prints as a dash. Hover sentences are the Number of Cities / Citizens tooltips.
function H.happiness_breakdown(pid)
  local p = Players[pid]
  local function n(fn, scale)
    local ok, v = pcall(fn)
    if not (ok and v) or v == 0 then return nil end
    return scale and (v / scale) or v
  end
  local resources = n(function() return p:GetHappinessFromResources() end)
  local variety = n(function() return p:GetHappinessFromResourceVariety() end)
  local buildings = n(function() return p:GetHappinessFromBuildings() end)
  local policies = n(function() return p:GetHappinessFromPolicies() end)
  local cities_h = n(function() return p:GetHappinessFromCities() end)
  local garrison = n(function() return p:GetHappinessFromGarrisonedUnits() end)
  local connected = n(function() return p:GetHappinessFromTradeRoutes() end)
  local religion = n(function() return p:GetHappinessFromReligion() end)
  local wonders = n(function() return p:GetHappinessFromNaturalWonders() end)
  local minors = n(function() return p:GetHappinessFromMinorCivs() end)
  local extra_city = n(function() return p:GetExtraHappinessPerCity() * p:GetNumCities() end)
  local total_h = n(function() return p:GetHappiness() end)
  local unh_cities = n(function() return p:GetUnhappinessFromCityCount() end, 100)
  local unh_captured = n(function() return p:GetUnhappinessFromCapturedCityCount() end, 100)
  local unh_puppet = n(function() return p:GetUnhappinessFromPuppetCityPopulation() end, 100)
  local unh_spec = n(function() return p:GetUnhappinessFromCitySpecialists() end, 100)
  local unh_pop_raw = n(function() return p:GetUnhappinessFromCityPopulation() end, 100)
  local unh_occupied = n(function() return p:GetUnhappinessFromOccupiedCities() end, 100)
  local unh_units = n(function() return p:GetUnhappinessFromUnits() end, 100)
  local unh_opinion = n(function() return p:GetUnhappinessFromPublicOpinion() end)
  local unh_total = n(function() return p:GetUnhappiness() end)
  local pop = unh_pop_raw
  if pop and unh_spec then pop = pop - unh_spec end
  if pop and unh_puppet then pop = pop - unh_puppet end
  if pop == 0 then pop = nil end
  local out = {
    total = p:GetExcessHappiness(),
    happiness = { total = total_h, luxuries = resources, luxury_variety = variety, buildings = buildings,
                  policies = policies, cities = cities_h, garrisons = garrison, connected_cities = connected,
                  religion = religion, natural_wonders = wonders, city_states = minors, extra_per_city = extra_city },
    unhappiness = { total = unh_total, number_of_cities = unh_cities, captured_cities = unh_captured,
                    population = pop, puppet_population = unh_puppet, specialists = unh_spec,
                    occupied = unh_occupied, units = unh_units, public_opinion = unh_opinion },
  }
  -- The expandable rows. A failure here must not drop the totals above.
  pcall(function()
    local raw = {
      policies = p:GetHappinessFromPolicies() or 0,
      resources = p:GetHappinessFromResources() or 0,
      buildings = p:GetHappinessFromBuildings() or 0,
      cities = p:GetHappinessFromCities() or 0,
      trade = p:GetHappinessFromTradeRoutes() or 0,
      religion = p:GetHappinessFromReligion() or 0,
      wonders = p:GetHappinessFromNaturalWonders() or 0,
      minors = p:GetHappinessFromMinorCivs() or 0,
      extra_city = (p:GetExtraHappinessPerCity() or 0) * (p:GetNumCities() or 0),
      league = p:GetHappinessFromLeagues() or 0,
      gross = p:GetHappiness() or 0,
      variety = p:GetHappinessFromResourceVariety() or 0,
      extra_lux = p:GetExtraHappinessPerLuxury() or 0,
    }
    local h = out.happiness
    if raw.league ~= 0 then h.league = raw.league end
    local difficulty = raw.gross - raw.policies - raw.resources - raw.buildings - raw.cities
      - raw.trade - raw.religion - raw.wonders - raw.minors - raw.extra_city - raw.league
    if difficulty ~= 0 then h.difficulty = difficulty end
    if raw.extra_lux >= 1 then h.extra_per_luxury = raw.extra_lux end

    local base, kinds = 0, 0
    local lux = {}
    if GameInfo and GameInfo.Resources then
      for resource in GameInfo.Resources() do
        if resource and resource.ID then
          local happy = p:GetHappinessFromLuxury(resource.ID) or 0
          if happy > 0 then
            kinds = kinds + 1
            base = base + happy
            lux[#lux + 1] = {
              resource = short(resource.Type),
              name = plain_text(L(resource.Description)) or short(resource.Type),
              happiness = happy,
            }
          end
        end
      end
    end
    if #lux > 0 then h.by_luxury = lux end
    local misc = raw.resources - base - raw.variety - (raw.extra_lux * kinds)
    if misc > 0 then h.other_luxury = misc end

    local per_conn = 0
    if p.GetHappinessPerTradeRoute then per_conn = (p:GetHappinessPerTradeRoute() or 0) / 100 end
    local show_conn = raw.trade ~= 0
    local rows = {}
    if p.Cities then
      for c in p:Cities() do
        local row = { id = c:GetID(), name = c:GetName() }
        local bh = (c.GetHappiness and c:GetHappiness()) or 0
        if bh ~= 0 then row.buildings = bh end
        local lh = (c.GetLocalHappiness and c:GetLocalHappiness()) or 0
        if lh ~= 0 then row.local_happiness = lh end
        local capital = c.IsCapital and c:IsCapital()
        local linked = (not capital) and p.IsCapitalConnectedToCity and p:IsCapitalConnectedToCity(c)
        if show_conn and linked and per_conn ~= 0 then row.connection = per_conn end
        local uh = p.GetUnhappinessFromCityForUI and p:GetUnhappinessFromCityForUI(c) or 0
        if uh ~= 0 then row.unhappiness = uh / 100 end
        local no_occ = c.IsNoOccupiedUnhappiness and c:IsNoOccupiedUnhappiness()
        if c.IsOccupied and c:IsOccupied() and not no_occ then row.occupied = true end
        if row.buildings or row.local_happiness or row.connection or row.unhappiness or row.occupied then
          rows[#rows + 1] = row
        end
      end
    end
    if #rows > 0 then out.cities = rows end

    local function keep_sentences(...)
      local keys = { ... }
      local list = {}
      for i = 1, #keys do
        local s = plain_key(keys[i])
        if s then list[#list + 1] = s end
      end
      if #list > 0 then return list end
    end
    out.unhappy = H.unhappy_tier(p)
    if out.unhappy == "super_unhappy" then
      out.penalties = keep_sentences("TXT_KEY_TP_EMPIRE_SUPER_UNHAPPY", "TXT_KEY_TP_EMPIRE_VERY_UNHAPPY")
    elseif out.unhappy == "very_unhappy" then
      out.penalties = keep_sentences("TXT_KEY_TP_EMPIRE_VERY_UNHAPPY")
    elseif out.unhappy == "unhappy" then
      out.penalties = keep_sentences("TXT_KEY_TP_EMPIRE_UNHAPPY")
    end

    local handicap
    if GameInfo and GameInfo.HandicapInfos and p.GetHandicapType then
      handicap = GameInfo.HandicapInfos[p:GetHandicapType()]
    end
    local function add_line(lines, key, ...)
      local s = plain_key(key, ...)
      if s then lines[#lines + 1] = s end
    end
    local function city_count_extras()
      local lines = {}
      local mod = handicap and handicap.NumCitiesUnhappinessMod
      if mod and mod ~= 100 then add_line(lines, "TXT_KEY_NUMBER_OF_CITIES_HANDICAP_TT", 100 - mod) end
      if p.GetCityCountUnhappinessMod then
        local m = p:GetCityCountUnhappinessMod()
        if m and m ~= 0 then add_line(lines, "TXT_KEY_UNHAPPINESS_MOD_PLAYER", m) end
      end
      if p.GetTraitCityUnhappinessMod then
        local m = p:GetTraitCityUnhappinessMod()
        if m and m ~= 0 then add_line(lines, "TXT_KEY_UNHAPPINESS_MOD_TRAIT", m) end
      end
      if Game and Game.GetWorldNumCitiesUnhappinessPercent then
        local w = Game:GetWorldNumCitiesUnhappinessPercent()
        if w and w ~= 100 then add_line(lines, "TXT_KEY_UNHAPPINESS_MOD_MAP", 100 - w) end
      end
      return lines
    end
    local function join_tip(base, extras, normally)
      if not base then return nil end
      if #extras == 0 then
        if normally then return base .. "." end
        return base
      end
      local head = base
      if normally then
        local word = plain_key("TXT_KEY_NORMALLY") or "(Normally)"
        head = base .. " " .. word .. "."
      end
      return head .. "\n\n" .. table.concat(extras, "\n\n")
    end
    local tips = {}
    local city_extra = city_count_extras()
    local city_base = (#city_extra > 0) and plain_key("TXT_KEY_NUMBER_OF_CITIES_TT_NORMALLY")
      or plain_key("TXT_KEY_NUMBER_OF_CITIES_TT")
    tips.city_count = join_tip(city_base, city_extra, false)
    local pop_extra = {}
    local pop_mod = handicap and handicap.PopulationUnhappinessMod
    if pop_mod and pop_mod ~= 100 then add_line(pop_extra, "TXT_KEY_NUMBER_OF_CITIES_HANDICAP_TT", 100 - pop_mod) end
    if p.GetUnhappinessMod then
      local m = p:GetUnhappinessMod()
      if m and m ~= 0 then add_line(pop_extra, "TXT_KEY_UNHAPPINESS_MOD_PLAYER", m) end
    end
    if p.GetTraitPopUnhappinessMod then
      local m = p:GetTraitPopUnhappinessMod()
      if m and m ~= 0 then add_line(pop_extra, "TXT_KEY_UNHAPPINESS_MOD_TRAIT", m) end
    end
    if p.GetCapitalUnhappinessMod then
      local m = p:GetCapitalUnhappinessMod()
      if m and m ~= 0 then add_line(pop_extra, "TXT_KEY_UNHAPPINESS_MOD_CAPITAL", m) end
    end
    local half = p.IsHalfSpecialistUnhappiness and p:IsHalfSpecialistUnhappiness()
    if half then add_line(pop_extra, "TXT_KEY_UNHAPPINESS_MOD_SPECIALIST") end
    tips.population = join_tip(plain_key("TXT_KEY_POP_UNHAPPINESS_TT"), pop_extra, true)
    if unh_captured then
      tips.occupied_cities = join_tip(plain_key("TXT_KEY_NUMBER_OF_OCCUPIED_CITIES_TT"), city_extra, true)
    end
    local occupied_pop = 0
    if p.Cities then
      for c in p:Cities() do
        local no_occ = c.IsNoOccupiedUnhappiness and c:IsNoOccupiedUnhappiness()
        if c.IsOccupied and c:IsOccupied() and not no_occ then
          occupied_pop = occupied_pop + (c:GetPopulation() or 0)
        end
      end
    end
    if occupied_pop ~= 0 then
      local occ_extra = {}
      if pop_mod and pop_mod ~= 100 then add_line(occ_extra, "TXT_KEY_NUMBER_OF_CITIES_HANDICAP_TT", 100 - pop_mod) end
      if p.GetOccupiedPopulationUnhappinessMod then
        local m = p:GetOccupiedPopulationUnhappinessMod()
        if m and m ~= 0 then add_line(occ_extra, "TXT_KEY_UNHAPPINESS_MOD_PLAYER", m) end
      end
      if half then add_line(occ_extra, "TXT_KEY_UNHAPPINESS_MOD_SPECIALIST") end
      tips.occupied_population = join_tip(plain_key("TXT_KEY_OCCUPIED_POP_UNHAPPINESS_TT"), occ_extra, true)
      -- The screen's "Occupied Citizens (N)" title. Not the unhappiness number (`occupied`).
      out.unhappiness.occupied_citizens = occupied_pop
    end
    if p.GetTotalPopulation then
      local total = p:GetTotalPopulation()
      if type(total) == "number" then
        -- "Citizens (N)" is everyone who is not in an occupied city.
        out.unhappiness.citizens = total - occupied_pop
      end
    end
    if next(tips) then out.unhappiness.tooltips = tips end
  end)
  return out
end

-- socialpolicypopup.lua / cultureoverview.lua: Content vs Dissidents vs ... plus preferred ideology.
function H.public_opinion(pid)
  local p = Players[pid]
  if not p then return nil end
  -- Both stock screens read public opinion only once an ideology is adopted (cultureoverview.lua:1832 `if
  -- iIdeology ~= NO_POLICY_BRANCH_TYPE`, socialpolicypopup.lua's HasIdeology branch). The engine's fields
  -- outlive the game that set them (GitLab #107 t0: the previous game's ideologies in the tooltip; #151
  -- hotseat t0: DISSIDENTS, Order preferred, two unmet civs named as the pressure), so the ideology gates the read.
  local tree
  pcall(function() tree = p:GetLateGamePolicyTree() end)
  if type(tree) ~= "number" or tree < 0 then return nil end
  local out = {}
  pcall(function()
    local t = p:GetPublicOpinionType()
    if t == nil then return end
    out.type = H.enum_name("PublicOpinionTypes", PublicOpinionTypes, t)
    if type(out.type) ~= "string" then out.type = t end
  end)
  pcall(function()
    local u = p:GetPublicOpinionUnhappiness()
    if type(u) == "number" and u ~= 0 then out.unhappiness = u end
  end)
  pcall(function()
    local pref = p:GetPublicOpinionPreferredIdeology()
    if pref and pref >= 0 and GameInfo.PolicyBranchTypes and GameInfo.PolicyBranchTypes[pref] then
      out.preferred_ideology = GameInfo.PolicyBranchTypes[pref].Type
    end
  end)
  pcall(function()
    local tip = p:GetPublicOpinionTooltip()
    if type(tip) == "string" and tip ~= "" then
      out.tooltip = (tip:sub(1, 8) == "TXT_KEY_") and H.L(tip) or tip
    end
  end)
  -- With no unhappiness and no preferred ideology there is no public opinion to report (#107).
  if out.unhappiness == nil and out.preferred_ideology == nil then return nil end
  -- socialpolicypopup.lua: the unhappiness figure's own hover, the current ideology, and the
  -- Switch Ideology button (enabled only while public-opinion unhappiness is positive) with the
  -- confirm's numbers: anarchy turns and the tenets kept after the switch (GitLab #13).
  pcall(function()
    local tip = p:GetPublicOpinionUnhappinessTooltip()
    if type(tip) == "string" and tip ~= "" then out.unhappiness_tooltip = plain_text(tip) end
  end)
  pcall(function()
    if GameInfo.PolicyBranchTypes[tree] then
      out.ideology = GameInfo.PolicyBranchTypes[tree].Type
      local unh = p:GetPublicOpinionUnhappiness()
      out.can_switch = (type(unh) == "number" and unh > 0) or false
      if out.can_switch and out.preferred_ideology then
        local now = p:GetNumPoliciesInBranch(tree)
        local kept = now - (GameDefines and GameDefines.SWITCH_POLICY_BRANCHES_TENETS_LOST or 2)
        if kept < 0 then kept = 0 end
        out.switch_cost = { anarchy_turns = GameDefines and GameDefines.SWITCH_POLICY_BRANCHES_ANARCHY_TURNS or nil,
                            tenets_now = now, tenets_kept = kept, to = out.preferred_ideology }
      end
    end
  end)
  if not next(out) then return nil end
  return out
end

-- The Switch Ideology confirm's Yes (Network.SendChangeIdeology): only while the button is enabled.
function H.change_ideology(pid)
  local po = H.public_opinion(pid) or {}
  if not po.ideology then return { ok = false, err = "no ideology adopted yet" } end
  if not po.can_switch then
    return { ok = false, err = "the Switch Ideology button is disabled: no public-opinion unhappiness", ideology = po.ideology }
  end
  Network.SendChangeIdeology()
  return { ok = true, from = po.ideology, to = po.preferred_ideology, cost = po.switch_cost }
end

-- Gold tooltip (toppanel.lua GoldTipHandler). Cities vs international trade routes are split
-- the same way the panel does (GetGoldFromCitiesTimes100 minus GetGoldFromCitiesMinusTradeRoutesTimes100).
function H.gold_breakdown(pid)
  local p = Players[pid]
  local function n(fn, scale)
    local ok, v = pcall(fn)
    if not (ok and v) or v == 0 then return nil end
    return scale and (v / scale) or v
  end
  local gold = p:GetGold()
  local gpt = p:CalculateGoldRate()
  local diplo = n(function() return p:GetGoldPerTurnFromDiplomacy() end) or 0
  local from_deals, to_deals = diplo > 0 and diplo or nil, diplo < 0 and -diplo or nil
  local ok_all, cities_all = pcall(function() return p:GetGoldFromCitiesTimes100() / 100 end)
  local ok_minus, cities_minus = pcall(function() return p:GetGoldFromCitiesMinusTradeRoutesTimes100() / 100 end)
  local cities, trade_routes
  if ok_minus then
    if cities_minus and cities_minus ~= 0 then cities = cities_minus end
  elseif ok_all and cities_all and cities_all ~= 0 then
    cities = cities_all
  end
  if ok_all and ok_minus then
    local tr = (cities_all or 0) - (cities_minus or 0)
    if tr ~= 0 then trade_routes = tr end
  end
  local out = {
    gold = gold,
    gold_per_turn = gpt,
    income = {
      cities = cities,
      trade_routes = trade_routes,
      city_connections = n(function() return p:GetCityConnectionGoldTimes100() end, 100),
      deals = from_deals,
      traits = n(function() return p:GetGoldPerTurnFromTraits() end),
      religion = n(function() return p:GetGoldPerTurnFromReligion() end),
    },
    expenses = {
      unit_maintenance = n(function() return p:CalculateUnitCost() end),
      unit_supply = n(function() return p:CalculateUnitSupply() end),
      building_maintenance = n(function() return p:GetBuildingGoldMaintenance() end),
      improvement_maintenance = n(function() return p:GetImprovementGoldMaintenance() end),
      deals = to_deals,
    },
  }
  -- toppanel.lua GoldTipHandler opens with TXT_KEY_TP_ANARCHY like the science/culture/faith hovers;
  -- seen live t239 after the ideology switch (GitLab #13), when this hover alone lacked the line.
  local ok_a, is_a = pcall(function() return p:IsAnarchy() end)
  if ok_a and is_a then out.anarchy_turns = n(function() return p:GetAnarchyNumTurns() end) end
  -- economicgeneralinfo.lua unit-expense tooltip: paid vs maintenance-free units and gold per paid unit.
  pcall(function()
    local total = p:GetNumUnits()
    local free = 0
    local ok_f, v = pcall(function()
      if DomainTypes and DomainTypes.NO_DOMAIN ~= nil then
        return p:GetNumMaintenanceFreeUnits(DomainTypes.NO_DOMAIN, false)
      end
      return p:GetNumMaintenanceFreeUnits()
    end)
    if ok_f and v then free = v end
    local paid = total - free
    if paid < 0 then paid = 0 end
    out.expenses.unit_paid = paid
    if free > 0 then out.expenses.unit_free = free end
    local maint = out.expenses.unit_maintenance
    if maint and paid > 0 then
      out.expenses.unit_cost_per = math.floor(maint / paid * 100 + 0.5) / 100
    end
  end)
  -- toppanel.lua GoldTipHandler / live t182 Losing Gold notice: empty treasury + negative GPT
  -- takes unpaid expenses out of science; units later go on strike (IsStrike was still false at −23).
  if gold + gpt < 0 then
    out.losing_science_from_deficit = true
    out.note = "unpaid expenses come out of science (science_breakdown.budget_deficit); state(what='city', view='screen') buildings with can_sell / order(to='city', action='sell_building') raise gold"
  end
  local ok_s, strike = pcall(function() return p:IsStrike() end)
  if ok_s and strike then out.is_strike = true end
  local ok_t, turns = pcall(function() return p:GetStrikeTurns() end)
  if ok_t and turns and turns > 0 then out.strike_turns = turns end
  return out
end

-- Science tooltip (toppanel.lua ScienceTipHandler). The boolean on GetScienceFromCitiesTimes100
-- is "exclude trade routes": true = cities only, false = cities + ITR.
function H.science_breakdown(pid)
  local p = Players[pid]
  local function n(fn, scale)
    local ok, v = pcall(fn)
    if not (ok and v) or v == 0 then return nil end
    return scale and (v / scale) or v
  end
  local ok_c, cities_raw = pcall(function() return p:GetScienceFromCitiesTimes100(true) / 100 end)
  local ok_p, plus_raw = pcall(function() return p:GetScienceFromCitiesTimes100(false) / 100 end)
  local cities = (ok_c and cities_raw ~= 0) and cities_raw or nil
  local trade
  if ok_c and ok_p then
    local tr = (plus_raw or 0) - (cities_raw or 0)
    if tr ~= 0 then trade = tr end
  end
  local anarchy
  local ok_a, is_a = pcall(function() return p:IsAnarchy() end)
  if ok_a and is_a then anarchy = n(function() return p:GetAnarchyNumTurns() end) end
  return {
    total = p:GetScience(),
    anarchy_turns = anarchy,
    budget_deficit = n(function() return p:GetScienceFromBudgetDeficitTimes100() end, 100),
    cities = cities,
    trade_routes = trade,
    city_states = n(function() return p:GetScienceFromOtherPlayersTimes100() end, 100),
    happiness = n(function() return p:GetScienceFromHappinessTimes100() end, 100),
    research_agreements = n(function() return p:GetScienceFromResearchAgreementsTimes100() end, 100),
    tech_city_cost_mod = n(function() return Game.GetNumCitiesTechCostMod() end),
  }
end

-- Culture tooltip (toppanel.lua CultureTipHandler). Golden-age remainder is total minus the
-- named sources, same as the stock panel.
function H.culture_breakdown(pid)
  local p = Players[pid]
  local function n(fn)
    local ok, v = pcall(fn)
    if not (ok and v) or v == 0 then return nil end
    return v
  end
  local function z(v) return (v and v ~= 0) and v or nil end
  local total = p:GetTotalJONSCulturePerTurn()
  local acc = p:GetJONSCulture()
  local next_cost = p:GetNextPolicyCost()
  local needed = (next_cost or 0) - (acc or 0)
  local turns
  if needed <= 0 then turns = 0
  elseif not total or total == 0 then turns = nil
  else turns = math.ceil(needed / total) end
  local free = n(function() return p:GetJONSCulturePerTurnForFree() end) or 0
  local cities = n(function() return p:GetJONSCulturePerTurnFromCities() end) or 0
  local happiness = n(function() return p:GetJONSCulturePerTurnFromExcessHappiness() end) or 0
  local traits = n(function() return p:GetJONSCulturePerTurnFromTraits() end) or 0
  local minors = n(function() return p:GetCulturePerTurnFromMinorCivs() end) or 0
  local religion = n(function() return p:GetCulturePerTurnFromReligion() end) or 0
  local bonus = n(function() return p:GetCulturePerTurnFromBonusTurns() end) or 0
  local ga = (total or 0) - free - cities - happiness - minors - religion - traits - bonus
  local anarchy
  local ok_a, is_a = pcall(function() return p:IsAnarchy() end)
  if ok_a and is_a then anarchy = n(function() return p:GetAnarchyNumTurns() end) end
  return {
    total = total, accumulated = acc, next_policy_cost = next_cost, turns = turns,
    anarchy_turns = anarchy, free = z(free), cities = z(cities), happiness = z(happiness),
    traits = z(traits), city_states = z(minors), religion = z(religion), bonus_turns = z(bonus),
    bonus_turns_remaining = bonus ~= 0 and n(function() return p:GetCultureBonusTurns() end) or nil,
    golden_age = z(ga),
    policy_city_cost_mod = n(function() return Game.GetNumCitiesPolicyCostMod() end),
  }
end

-- Tourism tooltip (toppanel.lua TourismTipHandler): great-work fill plus culture-victory progress
-- when that victory type is on.
function H.tourism_breakdown(pid)
  local p = Players[pid]
  local function n(fn)
    local ok, v = pcall(fn)
    if not ok then return nil end
    return v
  end
  local works = n(function() return p:GetNumGreatWorks() end) or 0
  local slots = n(function() return p:GetNumGreatWorkSlots() end)
  local out = {
    tourism = n(function() return p:GetTourism() end) or 0,
    great_works = works,
    empty_slots = slots and (slots - works) or nil,
  }
  local ok_v, cult = pcall(function()
    local v = GameInfo.Victories["VICTORY_CULTURAL"]
    return v and PreGame.IsVictory(v.ID)
  end)
  if ok_v and cult then
    out.influential_on = n(function() return p:GetNumCivsInfluentialOn() end)
    out.needed = n(function() return p:GetNumCivsToBeInfluentialOn() end)
  end
  return out
end

-- Faith tooltip (toppanel.lua FaithTipHandler). Next-prophet threshold is also on religion_overview.
function H.faith_breakdown(pid)
  local p = Players[pid]
  local function n(fn)
    local ok, v = pcall(fn)
    if not (ok and v) or v == 0 then return nil end
    return v
  end
  local anarchy
  local ok_a, is_a = pcall(function() return p:IsAnarchy() end)
  if ok_a and is_a then anarchy = n(function() return p:GetAnarchyNumTurns() end) end
  return {
    total = p:GetTotalFaithPerTurn(),
    accumulated = p:GetFaith(),
    anarchy_turns = anarchy,
    cities = n(function() return p:GetFaithPerTurnFromCities() end),
    city_states = n(function() return p:GetFaithPerTurnFromMinorCivs() end),
    religion = n(function() return p:GetFaithPerTurnFromReligion() end),
    next_great_person = n(function() return p:GetMinimumFaithNextGreatProphet() end),
  }
end

function H.player_summary(pid)
  local p = Players[pid]
  local research = p:GetCurrentResearch()
  local era = GameInfo.Eras[p:GetCurrentEra()]
  local trade_gate = H.trade_unit_gate(p)      -- can any city train a Caravan / Cargo Ship now, and the engine's sentence if not
  return {
    id = pid, name = p:GetName(), civ = p:GetCivilizationShortDescription(), leader = L(GameInfo.Leaders[p:GetLeaderType()].Description),
    human = p:IsHuman(), alive = p:IsAlive(), turn_active = p:IsTurnActive(), team = p:GetTeam(), score = p:GetScore(),
    gold = p:GetGold(), gold_per_turn = p:CalculateGoldRate(), science = p:GetScience(),
    research = research >= 0 and short(info_type(GameInfo.Technologies, research)) or nil,
    research_turns_left = research >= 0 and p:GetResearchTurnsLeft(research, true) or nil,
    culture = p:GetJONSCulture(), culture_per_turn = p:GetTotalJONSCulturePerTurn(), next_policy_cost = p:GetNextPolicyCost(),
    faith = p:GetFaith(), faith_per_turn = p:GetTotalFaithPerTurn(),
    happiness = p:GetExcessHappiness(), golden_age_turns = p:GetGoldenAgeTurns(), era = era and short(era.Type),
    golden_age_progress = (p.GetGoldenAgeProgressMeter and p:GetGoldenAgeProgressMeter()) or nil,
    golden_age_threshold = (p.GetGoldenAgeProgressThreshold and p:GetGoldenAgeProgressThreshold()) or nil,
    num_cities = p:GetNumCities(), num_units = p:GetNumUnits(), military_might = p:GetMilitaryMight(),
    trade_routes_used = p.GetNumInternationalTradeRoutesUsed and p:GetNumInternationalTradeRoutesUsed() or nil,
    trade_routes_available = p.GetNumInternationalTradeRoutesAvailable and p:GetNumInternationalTradeRoutesAvailable() or nil,
    -- trade units queued in any city count against the training gate (H.trade_unit_count, runtime v252)
    trade_units_queued = H.trade_unit_count(p).queued,
    -- the second gate (H.trade_unit_gate, runtime v253): {caravan=bool, cargo_ship=bool} and the engine's reasons
    trade_units_trainable = trade_gate.trainable,
    trade_units_refused = trade_gate.engine_reason,
    idle_trade_units = H.idle_trade_units(p, pid),
    idle_spies = H.idle_spies(pid),
    turn = Game.GetGameTurn(), year = Game.GetGameTurnYear(),
    strategic_resources = H.strategic_resources(pid),
    luxuries = H.luxuries(pid),
    bonus_resources = H.bonus_resources(pid),
    happiness_breakdown = H.happiness_breakdown(pid),
    gold_breakdown = H.gold_breakdown(pid),
    science_breakdown = H.science_breakdown(pid),
    culture_breakdown = H.culture_breakdown(pid),
    tourism_breakdown = H.tourism_breakdown(pid),
    faith_breakdown = H.faith_breakdown(pid),
    -- Military Overview header + toppanel unit-supply string (shown when over the cap).
    unit_supply = H.unit_supply(pid),
    -- Diplo list / Victory Progress score tooltip (diplolist.lua).
    score_breakdown = H.score_breakdown(pid),
    public_opinion = H.public_opinion(pid),
  }
end

function H.score_breakdown(pid)
  local p = Players[pid]
  if not p then return nil end
  local function n(fn)
    local ok, v = pcall(fn)
    if ok and type(v) == "number" and v ~= 0 then return v end
  end
  local out = {
    total = p:GetScore(),
    cities = n(function() return p:GetScoreFromCities() end),
    population = n(function() return p:GetScoreFromPopulation() end),
    land = n(function() return p:GetScoreFromLand() end),
    wonders = n(function() return p:GetScoreFromWonders() end),
    great_works = n(function() return p:GetScoreFromGreatWorks() end),
  }
  if not (Game.IsOption and GameOptionTypes and Game.IsOption(GameOptionTypes.GAMEOPTION_NO_SCIENCE)) then
    out.techs = n(function() return p:GetScoreFromTechs() end)
    out.future_tech = n(function() return p:GetScoreFromFutureTech() end)
  end
  if not (Game.IsOption and GameOptionTypes and Game.IsOption(GameOptionTypes.GAMEOPTION_NO_POLICIES)) then
    out.policies = n(function() return p:GetScoreFromPolicies() end)
  end
  if not (Game.IsOption and GameOptionTypes and Game.IsOption(GameOptionTypes.GAMEOPTION_NO_RELIGION)) then
    out.religion = n(function() return p:GetScoreFromReligion() end)
  end
  return out
end

-- Shared with later fragments, which import these at their top (load order: harness/runtime_source.py MANIFEST).
H._ns.plain_key = plain_key
H._ns.plain_text = plain_text

function H.gold_now(pid) return Players[pid]:GetGold() end
function H.city_count(pid) return Players[pid]:GetNumCities() end
function H.unit_count(pid) return Players[pid]:GetNumUnits() end
function H.free_great_people(pid) return Players[pid]:GetNumFreeGreatPeople() end

-- The game's identity for the notebook key (harness/notebook_identity.py, GitLab #168): facts fixed when the map
-- is made and kept in the save -- the seat's own starting plot, the civilization in every major slot and the
-- city-state in every minor slot. A reload reads the same string; two games set up alike start apart.
local function game_identity(pid)
  local plot = Players[pid]:GetStartingPlot()
  if not plot then return "" end
  local majors, minors = {}, {}
  for i = 0, GameDefines.MAX_CIV_PLAYERS - 1 do
    local q = Players[i]
    if q and q:IsEverAlive() then
      if q:IsMinorCiv() then
        minors[#minors + 1] = i .. ":" .. tostring(q:GetMinorCivType())
      else
        majors[#majors + 1] = i .. ":" .. tostring(q:GetCivilizationType())
      end
    end
  end
  return plot:GetX() .. "," .. plot:GetY() .. "|" .. table.concat(majors, ",") .. "|" .. table.concat(minors, ",")
end

-- What names a game in the notebook (harness/game_parts/notebook.py game_key): leader, civ, map, the identity;
-- the capital and its founding turn name the key written before #168, which a game under way adopts once.
function H.game_key_facts(pid)
  local p = Players[pid]
  local cap = p:GetCapitalCity()
  local ms = (PreGame and PreGame.GetMapScript and PreGame.GetMapScript()) or ""
  -- A game set up with map type Random hides the script from its human players; the engine still knows it
  -- (GetMapScript answers the real one). The key says "random" then, as the setup read does (GitLab #119).
  local random = PreGame and PreGame.IsRandomMapScript and PreGame.IsRandomMapScript() == true
  return { leader = tostring(p:GetLeaderType()), civ = tostring(p:GetCivilizationType()),
           map = random and "random" or (tostring(ms):match("([^/\\]+)%.lua$") or tostring(ms)),
           cap = cap and cap:GetName() or "", founded = cap and cap:GetGameTurnFounded() or -1,
           name = (PreGame and PreGame.GetGameName and PreGame.GetGameName()) or "", start = Game.GetStartTurn(),
           turn = Game.GetGameTurn(), identity = game_identity(pid) }
end
