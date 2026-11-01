-- Shared by earlier fragments (load order: harness/runtime_source.py MANIFEST).
local do_command, info_id, info_type = H._ns.do_command, H._ns.info_id, H._ns.info_type
local move_denom, own_active_unit = H._ns.move_denom, H._ns.own_active_unit
local peaceful_occupant_err, push_mission = H._ns.peaceful_occupant_err, H._ns.push_mission
local require_revealed_plot, short = H._ns.require_revealed_plot, H._ns.short

-- Snapshot of the city a religious unit (Missionary / Inquisitor / Prophet) would act on: the city on
-- its own plot or an adjacent one. Used by unit_mission to measure MISSION_SPREAD_RELIGION /
-- MISSION_REMOVE_HERESY instead of trusting PushMission's unconditional acceptance.
function H.religion_target(unit_id, pid)
  local u = Players[pid]:GetUnitByID(unit_id)
  if not u then return { ok = false, err = "no such unit" } end
  local rel = u.GetReligion and u:GetReligion() or -1
  local city = nil
  local here = Map.GetPlot(u:GetX(), u:GetY())
  if here and here:IsCity() then city = here:GetPlotCity() end
  if not city then
    for d = 0, DirectionTypes.NUM_DIRECTION_TYPES - 1 do
      local p = Map.PlotDirection(u:GetX(), u:GetY(), d)
      if p and p:IsCity() then city = p:GetPlotCity(); break end
    end
  end
  local out = { ok = true, unit_religion = rel, spreads_left = u.GetSpreadsLeft and u:GetSpreadsLeft() or nil,
                strength = u.GetConversionStrength and u:GetConversionStrength() or nil }
  if rel and rel >= 0 and Game.GetReligionName then out.unit_religion_name = H.L(Game.GetReligionName(rel)) end
  if not city then out.city = nil; return out end
  return H.city_religion_state(city, rel, pid, out)
end

-- The city half of religion_target, keyed by city plot so it can be re-read after the acting unit
-- was consumed by its last charge (unit_id is gone by then).
function H.city_religion_at(x, y, rel, pid)
  local p = Map.GetPlot(x, y)
  if not p or not p:IsCity() then return { ok = false, err = "no city at that plot" } end
  return H.city_religion_state(p:GetPlotCity(), rel, pid, { ok = true, unit_religion = rel })
end

function H.city_religion_state(city, rel, pid, out)
  local owner = city:GetOwner()
  local maj = city:GetReligiousMajority()
  out.city = city:GetName(); out.city_owner = owner; out.x = city:GetX(); out.y = city:GetY()
  out.population = city:GetPopulation()
  out.majority = maj
  if maj >= 0 and Game.GetReligionName then out.majority_name = H.L(Game.GetReligionName(maj)) end
  out.followers = (rel and rel >= 0) and city:GetNumFollowers(rel) or nil
  out.majority_followers = maj >= 0 and city:GetNumFollowers(maj) or nil
  local op = Players[owner]
  if op and op:IsMinorCiv() then out.influence = op:GetMinorCivFriendshipWithMajor(pid) end
  return out
end

-- What a human sees when a unit moves: the fog pulls back. move_unit snapshots how much of the map within
-- REVEAL_RADIUS of the unit its team can see as it sends the order (same tuner trip), and the read-back that
-- follows (H.unit_pos with reveal=true) reports what is revealed now and was not then, plus what stands on
-- plots that came from fog into sight -- so "move the scout and see what is there" is the move's own answer,
-- not a second read. Per plot it reads only IsRevealed / IsVisible; the new plots go through H.describe_plot,
-- which says nothing about an unrevealed plot and nothing live about a fogged one. Since #153 the reply
-- names what is worth a look on the new ground, not every new plot.
local REVEAL_RADIUS = 12
local function seen_level(plot, team)
  if not plot:IsRevealed(team, false) then return 0 end
  if plot:IsVisible(team, false) then return 2 end
  return 1
end

function H.reveal_mark(u, pid)
  local team = Players[pid]:GetTeam()
  local x, y = u:GetX(), u:GetY()
  local seen = {}
  for dx = -REVEAL_RADIUS, REVEAL_RADIUS do for dy = -REVEAL_RADIUS, REVEAL_RADIUS do
    local p = Map.PlotXYWithRangeCheck(x, y, dx, dy, REVEAL_RADIUS)
    if p then seen[p:GetX() .. ":" .. p:GetY()] = seen_level(p, team) end
  end end
  H.reveal_marks[H.pm_key(u:GetID(), pid)] = { x = x, y = y, seen = seen }
end

-- What a human notices on newly uncovered ground: ruins, a barbarian camp, a luxury or strategic resource, a
-- natural wonder, a city. Everything else about a new plot is the map window's to show when it is wanted
-- (GitLab #153: a GOODY_MAP reward listed 49 plots, most of them fogged ocean, for a one-tile move).
local NOTABLE_IMPROVEMENTS = { GOODY_HUT = "ruins", BARBARIAN_CAMP = "barbarian camp" }
local function resource_notable(name)
  local ok, class = pcall(function() return GameInfo.Resources["RESOURCE_" .. name].ResourceClassType end)
  if not ok or not class then return true end
  return class ~= "RESOURCECLASS_BONUS"
end
local function natural_wonder(name)
  local ok, feat = pcall(function() return GameInfo.Features["FEATURE_" .. name] end)
  return ok and feat and (feat.NaturalWonder == true or feat.NaturalWonder == 1) or false
end
local function notable_row(e)
  if not e then return nil end
  local what = {}
  if e.city then what[#what + 1] = "city " .. tostring(e.city.name) end
  if e.improvement and NOTABLE_IMPROVEMENTS[e.improvement] then what[#what + 1] = NOTABLE_IMPROVEMENTS[e.improvement] end
  if e.resource and resource_notable(e.resource) then what[#what + 1] = e.resource end
  if e.feature and natural_wonder(e.feature) then what[#what + 1] = "natural wonder " .. e.feature end
  if #what == 0 then return nil end
  local row = { x = e.x, y = e.y, what = table.concat(what, ", ") }
  if e.owner then row.owner = e.owner end
  if e.vis == false then row.fogged = true end
  return row
end
local WATER = { OCEAN = true, COAST = true }

-- nil when no mark was taken for this unit; else {count (newly revealed plots), water (how many of them are
-- ocean or coast), notable ({x, y, what, owner?, fogged?} rows for the new plots worth a look, up to 20,
-- more_notable beyond that), sighted ({x, y, units, city, owner} of fogged plots now in sight with foreign
-- units or a city on them)}. The new plots themselves are state(what="map", view="window") (#153).
function H.reveal_diff(unit_id, pid)
  local mark = H.reveal_marks[H.pm_key(unit_id, pid)]
  if not mark then return nil end
  local team = Players[pid]:GetTeam()
  local notable, sighted, count, water, more = {}, {}, 0, 0, 0
  for dx = -REVEAL_RADIUS, REVEAL_RADIUS do for dy = -REVEAL_RADIUS, REVEAL_RADIUS do
    local p = Map.PlotXYWithRangeCheck(mark.x, mark.y, dx, dy, REVEAL_RADIUS)
    if p then
      local before, now = mark.seen[p:GetX() .. ":" .. p:GetY()] or 0, seen_level(p, team)
      if before == 0 and now > 0 then
        count = count + 1
        local e = H.describe_plot(p, team)
        if e and WATER[e.t] then water = water + 1 end
        local row = notable_row(e)
        if row then
          if #notable < 20 then notable[#notable + 1] = row else more = more + 1 end
        end
      elseif before == 1 and now == 2 then
        local e = H.describe_plot(p, team)
        local foreign = nil
        for _, ue in ipairs(e and e.units or {}) do
          if ue.owner ~= pid then foreign = foreign or {}; foreign[#foreign + 1] = ue end
        end
        if e and (foreign or e.city) then
          -- the city in short form: a sighted Zurich came with its whole religion table, ~700 B (GitLab #148)
          local city = e.city and { name = e.city.name, owner = e.city.owner, pop = e.city.pop } or nil
          sighted[#sighted + 1] = { x = e.x, y = e.y, units = foreign, city = city, owner = e.owner }
        end
      end
    end
  end end
  local out = { count = count }
  if water > 0 then out.water = water end
  if #notable > 0 then out.notable = notable end
  if more > 0 then out.more_notable = more end
  if #sighted > 0 then out.sighted = sighted end
  return out
end

function H.move_unit(unit_id, x, y, pid)
  local u, err = own_active_unit(unit_id, pid)
  if not u then return err end
  local blocked = require_revealed_plot(x, y, pid, u)
  if blocked then return blocked end
  local m = info_id("MISSION_MOVE_TO")
  if m == nil then return { ok = false, err = "unknown mission" } end
  local legal = false
  if u.CanStartMission then
    local ok, v = pcall(function() return u:CanStartMission(m, x, y, false) end)
    legal = ok and v
  end
  if not legal then return { ok = false, err = "move is not currently legal" } end
  -- CanStartMission(MOVE_TO) is true for any valid plot, even one no path reaches (a natural
  -- wonder / mountain, or across unexplored water): the engine then drops the mission silently.
  local dest = Map.GetPlot(x, y)
  if u:MovesLeft() <= 0 and (H.melee_defender(u, dest, pid) or H.enemy_city_at(dest, pid)) then
    -- GitLab #110 (live Maya t119): a move onto an enemy at 0 moves was "queued": the engine kept a mission it
    -- never ran, the unit sat on HOLD at full moves the next turn in no list, and the Hand-Axe shooting the
    -- workers lived another turn. An attack is never a standing order; say so now.
    return { ok = false, err = "no moves left this turn to attack: the engine would hold the order and never run it; "
                               .. "order the attack next turn (an attack is never kept as a standing move)",
             x = u:GetX(), y = u:GetY(), moves = 0 }
  end
  local refused = H.move_refusal(u, dest, pid, false)
  if refused then return refused end
  local x0, y0, m0 = u:GetX(), u:GetY(), u:MovesLeft()
  pcall(H.reveal_mark, u, pid)
  -- A move onto one of our own units of the same class is a swap: the engine walks the other unit
  -- back to this plot (live t252: a Worker ordered into Goshute traded places with the Worker there,
  -- which ended the turn on the far tile with no moves). A human watches the second unit hop; the
  -- reply only said "arrived". Remember who stood on the destination so _move_unit can report the
  -- one now standing here as `swapped_with`.
  local swap_candidates = nil
  pcall(function()
    if not dest then return end
    for i = 0, dest:GetNumUnits() - 1 do
      local o = dest:GetUnit(i)
      if o and o:GetOwner() == pid and o:GetID() ~= u:GetID() and not o:IsDelayedDeath()
         and not (DomainTypes and o:GetDomainType() == DomainTypes.DOMAIN_AIR) then
        swap_candidates = swap_candidates or {}
        local ot = GameInfo.Units[o:GetUnitType()]
        swap_candidates[#swap_candidates + 1] = { id = o:GetID(), type = ot and short(ot.Type) or o:GetUnitType() }
      end
    end
  end)
  local pushed = push_mission(u, m, x, y)
  if not pushed.ok then return pushed end
  -- Remember the destination: a MOVE_TO that needs more than this turn does NOT resume by itself at the
  -- next turn start (live, Caravel t256-264), so H.resume_moves re-pushes it until the unit arrives.
  -- Never for an attack: the unit does not "arrive", so the standing order re-fired as a second,
  -- unordered attack at the next turn start (live 2026-09-18, warrior vs a camp Brute: 73 -> 42 hp).
  if H.melee_defender(u, Map.GetPlot(x, y), pid) or H.enemy_city_at(Map.GetPlot(x, y), pid) then
    H.pending_moves[H.pm_key(unit_id, pid)] = nil
  else
    H.pending_moves[H.pm_key(unit_id, pid)] = { x = x, y = y, pid = pid, unit_id = unit_id }
  end
  local out = { ok = true, x = x0, y = y0, moves = m0 / move_denom(), swap_candidates = swap_candidates }
  -- type and max_moves: what the read-back needs to find the unit's successor when the move replaced it (#169).
  -- The move is sent: nothing read after it may turn the answer into an error.
  pcall(function() out.type = short(info_type(GameInfo.Units, u:GetUnitType())) end)
  pcall(function() out.max_moves = u:MaxMoves() / move_denom() end)
  return out
end

-- The destination checks move_unit makes before it sends anything: each is an order the engine accepts and
-- then drops without a word. Shared with H.tactical_view so the view's "refused" is exactly move_unit's.
-- fog_safe (the view) reads a fogged plot's owner as the last-seen one, never the live one; move_unit keeps
-- its live read (the engine's own answer to the order would use it too).
function H.move_refusal(u, dest, pid, fog_safe)
  -- Unit:GeneratePath is NYI in this build (throws). Plot:MovementCost crashed the live process
  -- (t183, 2026-09-19) even inside pcall -- do not call it. GetPathEndTurnPlot is nil without a
  -- mouse-driven UI pathfinder. Do not fake turns-to-reach. So the checks are per-destination-plot:
  -- IsImpassable catches natural wonders (Uluru), IsMountain catches mountains (whose terrain type
  -- still reads GRASS/PLAINS, so callers can't tell from the map), CanMoveOrAttackInto catches the rest.
  if dest and dest:IsImpassable() and not (u.CanMoveImpassable and u:CanMoveImpassable()) then
    return { ok = false, err = "destination plot is impassable" }
  end
  -- Domain: a ship ordered onto land (or a land unit onto water before Optics) is dropped silently by
  -- the engine (live t252: Caravel -> a newly sighted plains plot, ok:true, never moved). Say so.
  if dest and DomainTypes then
    local dom = u:GetDomainType()
    if dom == DomainTypes.DOMAIN_SEA and not dest:IsWater() and not dest:IsCity() then
      return { ok = false, err = "destination is land; a sea unit can only enter water plots or a coastal city" }
    end
    -- Unit:CanEmbark(plot) asks whether it can embark FROM that plot: false for any inland unit even with
    -- Optics (live t412: a Missionary at (35,29), team can embark, refused as "needs Optics"). Ask whether the
    -- unit can embark at all: its embarkation promotion, or the team-wide ability.
    local canEmbark = false
    pcall(function() canEmbark = u:IsHasPromotion(GameInfoTypes.PROMOTION_EMBARKATION) end)
    if not canEmbark then pcall(function() canEmbark = Teams[u:GetTeam()]:CanEmbark() end) end
    if dom == DomainTypes.DOMAIN_LAND and dest:IsWater() and not canEmbark then
      return { ok = false, err = "destination is water and this unit cannot embark (needs Optics; a ship or cargo ship is the alternative)" }
    end
  end
  if dest and dest:IsMountain() then
    local ok, can = pcall(function() return u:CanMoveOrAttackInto(dest) end)
    if not (ok and can) then return { ok = false, err = "destination plot is a mountain" } end
  end
  -- NOTE: CanMoveOrAttackInto(dest) is false for perfectly legal multi-step destinations (live: a
  -- warrior moving into its own adjacent city), so it is only consulted for the mountain case above.
  -- One combat unit per tile: a move whose destination already holds one of our own combat units
  -- (e.g. "send the new bowman to Nanjing" while a warrior garrisons it) has no legal end plot and is
  -- dropped silently by the engine (live, turn 110). Refuse it up front.
  if dest and u:IsCombatUnit() then
    for i = 0, dest:GetNumUnits() - 1 do
      local o = dest:GetUnit(i)
      if o and o:GetOwner() == u:GetOwner() and o:GetID() ~= u:GetID() and o:IsCombatUnit()
         and o:GetDomainType() == u:GetDomainType() then
        return { ok = false, err = "destination already holds one of your combat units (one per tile); pick an adjacent plot or move that unit first" }
      end
    end
  end
  -- One civilian per tile too. The view called a Worker's move onto another Worker's plot "open" while move_unit
  -- answered "unit did not move: your WORKER already holds it" (Grok, Venice/Mongolia 2026-09-27): the same rule,
  -- up front. A trade unit on its route passes through; every other civilian blocks, automated or not (live
  -- Assyria t135: a Great Prophet ordered onto the plot of an automated Worker was dropped by the engine with
  -- "no path", and the old exemption for any automated unit had let the order through). Name the unit.
  if dest and dest.GetNumUnits and not u:IsCombatUnit() then
    for i = 0, dest:GetNumUnits() - 1 do
      local o = dest:GetUnit(i)
      if o and o.IsCombatUnit and o:GetOwner() == u:GetOwner() and o:GetID() ~= u:GetID() and not o:IsCombatUnit()
         and o:GetDomainType() == u:GetDomainType() and not (o.IsTrade and o:IsTrade()) then
        local what = "civilian"
        pcall(function()
          local row = GameInfo and GameInfo.Units and GameInfo.Units[o:GetUnitType()]
          if row and row.Type then what = row.Type:gsub("^UNIT_", "") end
        end)
        local auto = (o.IsAutomated and o:IsAutomated()) and " (automated; it still holds the plot)" or ""
        return { ok = false, err = "destination already holds your " .. tostring(what) .. " " .. tostring(o:GetID())
                 .. auto .. " (one civilian per tile); pick an adjacent plot or move that unit first",
                 blocking_unit = { id = o:GetID(), type = tostring(what), automated = auto ~= "" } }
      end
    end
  end
  -- Nobody enters another player's city plot at peace: CanStartMission says yes, the engine drops the
  -- mission silently, and the unit sits there with full moves blocking the turn. Live t213: a Missionary
  -- ordered onto Lhasa's own plot (49,5) to answer its spread-religion quest lost two turns to this
  -- before an adjacent plot worked; the same shape is noted at t266 in resume_moves. At war the move is
  -- an attack and stays legal. Only for a plot we have revealed -- that is when a human sees the banner
  -- and would be refused by the same rule.
  local occupied_city = nil
  pcall(function()
    local myTeam = Players[pid]:GetTeam()
    if not (dest and dest:IsCity() and dest:IsRevealed(myTeam)) then return end
    local c = dest:GetPlotCity()
    if not c or c:GetOwner() == pid or c:GetTeam() == myTeam then return end
    -- The view never names a city founded in the fog since the plot was last seen: the engine's per-team
    -- city reveal flag is the banner a human has on the map.
    if fog_safe and not dest:IsVisible(myTeam, false) and not c:IsRevealed(myTeam, false) then return end
    if Teams[myTeam]:IsAtWar(c:GetTeam()) then return end
    occupied_city = { ok = false, err = "that plot is the city of " .. c:GetName() ..
      ", which cannot be entered while at peace; move to a plot next to it instead (a Missionary, "
      .. "Great Person or trade unit does its job from an adjacent plot)",
      city = { name = c:GetName(), owner = c:GetOwner(), x = dest:GetX(), y = dest:GetY() } }
  end)
  if occupied_city then return occupied_city end
  -- Another major civ's territory is closed without open borders (or war); the engine finds no path
  -- and drops the order silently (live t256: Caravel -> India's coast). Name the owner instead.
  local closed = nil
  pcall(function()
    local owner = dest and dest:GetOwner() or -1
    if fog_safe and dest and not dest:IsVisible(Players[pid]:GetTeam(), false) then
      owner = dest:GetRevealedOwner(Players[pid]:GetTeam(), false)
    end
    if owner >= 0 and owner ~= pid then
      local o = Players[owner]
      local myTeam, theirTeam = Teams[Players[pid]:GetTeam()], o and Teams[o:GetTeam()] or nil
      -- A unit the engine flags as rival-territory capable (Unit:IsRivalTerritory(): Missionaries, Great Prophets,
      -- Inquisitors) enters closed borders by rule; live Assyria t141 the guard refused a Missionary bound for the
      -- Zulu capital while the engine's own flag said yes.
      local ignores_borders = u.IsRivalTerritory and u:IsRivalTerritory() or false
      if o and theirTeam and not o:IsMinorCiv() and not myTeam:IsAtWar(o:GetTeam()) and not ignores_borders
         and not (theirTeam.IsAllowsOpenBordersToTeam and theirTeam:IsAllowsOpenBordersToTeam(Players[pid]:GetTeam())) then
        closed = { ok = false, err = "destination is inside " .. o:GetCivilizationShortDescription()
                   .. "'s borders and you have no open-borders agreement with them (trade one via order(to='civ', action='propose_deal'), or path around)",
                   owner_player_id = owner }
      end
    end
  end)
  if closed then return closed end
  local occ = H.peaceful_occupant(dest, pid)
  if occ then return { ok = false, err = peaceful_occupant_err(occ) } end
  return nil
end

-- Every seat's units share one id space (seat 0 and seat 1 both start with a Worker 57350), so a standing
-- order is filed under the seat as well as the unit. Live 2026-09-24 t214 (two-human hotseat): seat 1's
-- untouched Worker was refused MISSION_SKIP as "already on a multi-turn move" -- the record was seat 0's
-- Worker of the same id, and seat 0's Settler orders were being overwritten by seat 1's in the same way.
function H.pm_key(unit_id, pid)
  return tostring(pid or 0) .. ":" .. tostring(unit_id)
end

-- Where a standing move is taking `u` (#37): the destination move_unit stored for it, nil when there is
-- none or the unit already stands on it (an arrived record is stale bookkeeping, not a plan).
function H.going_to(u, pid)
  local pm = H.pending_moves[H.pm_key(u:GetID(), pid)]
  if not pm or pm.pid ~= pid then return nil end
  if pm.x == u:GetX() and pm.y == u:GetY() then return nil end
  return { x = pm.x, y = pm.y }
end

-- Why an ongoing unit (automated, or walking a standing move) needs the seat back this turn (#37): a
-- barbarian camp on or beside its plot, a hostile combat unit beside it, or a destination the seat can no
-- longer path to. Only plots this seat can see are read (a fogged neighbour is as unknown here as on the
-- map); nothing is read about the destination beyond the static revealed/impassable facts. nil when the
-- unit is merely moving: an explorer walking into the unknown is the ordinary case, not an alert.
function H.ongoing_attention(u, pid, going)
  local out = {}
  local p = Players[pid]
  local team = p:GetTeam()
  local imp = GameInfoTypes and GameInfoTypes.IMPROVEMENT_BARBARIAN_CAMP
  local x, y = u:GetX(), u:GetY()
  pcall(function()
    for dy = -1, 1 do
      for dx = -1, 1 do
        local q = Map.GetPlot(x + dx, y + dy)
        if q and Map.PlotDistance(x, y, q:GetX(), q:GetY()) <= 1 and q:IsVisible(team, false) then
          if imp and q:GetRevealedImprovementType(team, false) == imp then
            out[#out + 1] = { kind = "camp", x = q:GetX(), y = q:GetY() }
          end
          if not (dx == 0 and dy == 0) then
            for i = 0, q:GetNumUnits() - 1 do
              local d = q:GetUnit(i)
              if d and d:GetOwner() ~= pid and d:IsCombatUnit() and not d:IsInvisible(team, false) then
                local dp = Players[d:GetOwner()]
                if dp and (dp:IsBarbarian() or Teams[team]:IsAtWar(dp:GetTeam())) then
                  out[#out + 1] = { kind = "hostile", owner = H.owner_label(d:GetOwner(), pid),
                                    unit = short(info_type(GameInfo.Units, d:GetUnitType())),
                                    x = q:GetX(), y = q:GetY(), hp = d:GetCurrHitPoints() }
                end
              end
            end
          end
        end
      end
    end
  end)
  if going then
    local q = Map.GetPlot(going.x, going.y)
    if not q then
      out[#out + 1] = { kind = "destination_gone", x = going.x, y = going.y }
    elseif not q:IsRevealed(team, false) then
      out[#out + 1] = { kind = "destination_unrevealed", x = going.x, y = going.y }
    else
      local oki, imp2 = pcall(function() return q:IsImpassable() end)
      if oki and imp2 then out[#out + 1] = { kind = "destination_impassable", x = going.x, y = going.y } end
    end
  end
  return #out > 0 and out or nil
end

-- After a move settled: which of `ids` (the units that stood on the destination when the order went
-- out) now stands on (x, y), the mover's old plot. That unit was swapped, not stepped over.
function H.swapped_unit(ids, x, y, pid)
  local p = Players[pid]
  for _, id in ipairs(ids or {}) do
    local o = p:GetUnitByID(id)
    if o and not o:IsDelayedDeath() and o:GetX() == x and o:GetY() == y then
      local ot = GameInfo.Units[o:GetUnitType()]
      return { ok = true, unit = { id = id, type = ot and short(ot.Type) or o:GetUnitType(), x = x, y = y,
                                   moves = o:MovesLeft() / move_denom() } }
    end
  end
  return { ok = true }
end

-- A multi-turn move pushed from Lua does NOT resume at the next turn start (live: Caravel, t256-258):
-- the unit sits in ACTIVITY_MISSION with a queued MOVE_TO, moves still in hand, and the engine will
-- not spend them. That is the "stalled" shape, and such a unit DOES block end_turn. todo() and the
-- MISSION_SKIP guard both have to agree about it -- they did not (live t186: turn_status listed Great
-- General 335877 as blocking with stalled_mission=true while unit_mission(MISSION_SKIP) refused it as
-- "already on a multi-turn move and does not block end_turn"), so they now ask the same function.
-- A Worker mid-build also idles at full moves and is not stalled.
function H.is_stalled_mission(u)
  if not (u and u.GetActivityType) then return false end
  local activity = u:GetActivityType()
  -- ACTIVITY_HOLD (1) with a mission still queued is the same shape (GitLab #110, live Maya t120: a move onto an
  -- enemy ordered at 0 moves sat on HOLD at full moves the next turn, in no list; #83: a spaceship part ordered
  -- in at 0 moves the same way). The engine raises no blocker for it; the seat has to.
  local queued = (u.GetLengthMissionQueue and u:GetLengthMissionQueue() or 0) > 0
  if not (activity == 6 or (activity == 1 and queued)) then return false end
  if not (u.MovesLeft and u:MovesLeft() > 0) then return false end
  if u.GetBuildType and u:GetBuildType() ~= -1 then return false end
  return true
end

-- Why a standing move is NOT re-issued this turn (GitLab #98), or nil when it may go on: a hostile combat unit
-- or a barbarian camp beside the unit (the engine's own "enemy in sight" interrupt, which a Lua-pushed move
-- never gets), or a civilian whose destination is within this turn's movement -- it would arrive with 0 moves
-- and lose the turn its purpose needs (found, spread, build); left to the seat, the same move plus the
-- purpose fit in one turn. The seat sees the unit in todo.units with its moves and this reason.
function H.hold_standing_move(u, pm, pid)
  local going = { x = pm.x, y = pm.y }
  local att = H.ongoing_attention(u, pid, going)
  if att then
    for _, a in ipairs(att) do
      if a.kind == "hostile" or a.kind == "camp" then
        local what = a.kind == "camp" and ("a barbarian camp at (" .. a.x .. "," .. a.y .. ")")
                     or (tostring(a.owner) .. " " .. tostring(a.unit) .. " at (" .. a.x .. "," .. a.y .. ")")
        return { kind = a.kind, attention = att,
                 err = "standing move held: " .. what .. " is beside the unit, so it keeps its moves this turn; "
                       .. "order(to='unit', action='move') to the same plot resumes it, another plot redirects it, "
                       .. "action='mission' with MISSION_SKIP or COMMAND_CANCEL drops the path" }
      end
    end
  end
  local okc, combat = pcall(function() return u:IsCombatUnit() end)
  if okc and not combat and Map and Map.PlotDistance then
    local okd, dist = pcall(function() return Map.PlotDistance(u:GetX(), u:GetY(), pm.x, pm.y) end)
    local moves = u:MovesLeft() / move_denom()
    if okd and dist and dist > 0 and dist <= moves then
      return { kind = "within_reach",
               err = "standing move held: the destination (" .. pm.x .. "," .. pm.y .. ") is " .. dist .. " plot(s) away and the unit has "
                     .. moves .. " moves, so it keeps them this turn; order(to='unit', action='move') there, then act on arrival "
                     .. "(found, spread, build) in the same turn instead of arriving with 0 moves" }
    end
  end
  return nil
end

-- The hold a move was given (#105): fortify, sleep or alert, with the engine's own swap when the unit cannot take
-- the one asked (a unit that can fortify never sleeps; one that cannot fortify sleeps). "hold" means whichever.
function H.hold_unit(u, mission, pid)
  local id = u:GetID()
  local want = mission
  if mission == "hold" or mission == "fortify" then want = "MISSION_FORTIFY"
  elseif mission == "sleep" then want = "MISSION_SLEEP"
  elseif mission == "alert" then want = "MISSION_ALERT" end
  local r = H.unit_mission(id, want, -1, -1, nil, pid)
  if type(r) == "table" and r.ok then return { ok = true, mission = want } end
  local other = (want == "MISSION_FORTIFY" or want == "MISSION_ALERT") and "MISSION_SLEEP" or "MISSION_FORTIFY"
  local r2 = H.unit_mission(id, other, -1, -1, nil, pid)
  if type(r2) == "table" and r2.ok then return { ok = true, mission = other, swapped_from = want } end
  return { ok = false, mission = want, err = type(r) == "table" and r.err or "the hold was refused" }
end

-- A hold recorded for a standing move (#105): set when the move was ordered with `then`; lands when the unit
-- arrives (resume_moves), or next turn start when it arrived this turn with no moves left.
function H.set_pending_then(unit_id, mission, pid)
  local u = Players[pid]:GetUnitByID(unit_id)
  if not u then return { ok = false, err = "no such unit" } end
  local key = H.pm_key(unit_id, pid)
  local pm = H.pending_moves[key]
  if not pm then
    pm = { x = u:GetX(), y = u:GetY(), pid = pid, unit_id = unit_id }
    H.pending_moves[key] = pm
  end
  pm.then_mission = mission
  return { ok = true, x = pm.x, y = pm.y, then_mission = mission }
end

-- Re-issue standing move orders whose unit is idle at full moves (the "stalled_mission" shape) and drop
-- the ones that arrived or whose unit is gone. Called by wait_for_my_turn once the turn is ours. `skip` lists
-- unit ids a conditional order owns (#32): the order decides whether their move goes on, after its checks.
function H.resume_moves(pid, skip)
  local out = {}
  local owned = {}
  for _, id in ipairs(skip or {}) do owned[id] = true end
  for key, pm in pairs(H.pending_moves) do
    if pm.pid == pid and not owned[pm.unit_id or key] then
      local id = pm.unit_id or key
      local u = Players[pid]:GetUnitByID(id)
      if not u or u:IsDelayedDeath() then
        H.pending_moves[key] = nil
      elseif u:GetX() == pm.x and u:GetY() == pm.y then
        H.pending_moves[key] = nil
        local row = { unit_id = id, x = pm.x, y = pm.y, arrived = true }
        if pm.then_mission then
          -- GitLab #105: "go there and hold" -- the hold the move was given lands the turn the unit arrives with
          -- its moves (a fortify sent at 0 moves is a one-turn HOLD the engine forgets).
          local hr = H.hold_unit(u, pm.then_mission, pid)
          row.held, row.hold_ok = hr.mission, hr.ok
          if not hr.ok then row.hold_err = hr.err end
        end
        out[#out + 1] = row
      elseif u:MovesLeft() > 0 and u:MovesLeft() == u:MaxMoves()
             and not (u.GetBuildType and u:GetBuildType() ~= -1) then
        -- No progress since the last resume (same plot a whole turn later) means the engine keeps
        -- dropping the path (e.g. a Missionary ordered INTO a foreign city plot, t266): stop re-issuing
        -- and tell the caller, rather than pushing the same dead order every turn forever.
        if H.melee_defender(u, Map.GetPlot(pm.x, pm.y), pid) or H.enemy_city_at(Map.GetPlot(pm.x, pm.y), pid) then
          -- An enemy now stands on the destination: re-issuing the move would be an attack nobody ordered.
          H.pending_moves[key] = nil
          out[#out + 1] = { unit_id = id, x = pm.x, y = pm.y, dropped = true,
                            err = "an enemy unit now stands on the destination; order(to='unit', action='move') there again to attack it" }
        elseif H.peaceful_occupant(Map.GetPlot(pm.x, pm.y), pid) then
          H.pending_moves[key] = nil
          out[#out + 1] = { unit_id = id, x = pm.x, y = pm.y, dropped = true,
                            err = peaceful_occupant_err(H.peaceful_occupant(Map.GetPlot(pm.x, pm.y), pid)) }
        elseif pm.last_x == u:GetX() and pm.last_y == u:GetY() then
          H.pending_moves[key] = nil
          out[#out + 1] = { unit_id = id, x = pm.x, y = pm.y, dropped = true,
                            err = "no progress toward the destination for a full turn; the engine finds no path -- pick another plot" }
        elseif H.hold_standing_move(u, pm, pid) then
          -- GitLab #98 (live Maya t34-t38, t54-t62): the resume ran at the turn start, before the seat saw the
          -- turn, so a Spearman and then a Scout walked a plot a turn around a barbarian camp, arrived in
          -- `ongoing` with 0 moves every turn, were bombarded every AI turn and died without one turn to react;
          -- Settlers and Prophets arrived with 0 moves and lost the turn their purpose needed. The record is kept
          -- and the move is not re-issued: the unit keeps its moves and stands in todo.units with the reason.
          local why = H.hold_standing_move(u, pm, pid)
          out[#out + 1] = { unit_id = id, x = pm.x, y = pm.y, held = true, reason = why.kind, attention = why.attention,
                            err = why.err }
        else
          pm.last_x, pm.last_y = u:GetX(), u:GetY()
          local r = H.move_unit(id, pm.x, pm.y, pid)
          if r.ok then
            H.pending_moves[key] = pm  -- H.move_unit replaced the record; keep the progress marker
            out[#out + 1] = { unit_id = id, x = pm.x, y = pm.y, resumed = true }
          elseif r.blocking_unit then
            -- GitLab #86 (Assyria t253): an automated Worker walked into the capital the night before the Booster's
            -- standing move landed, and the move was dropped for good. One of my own civilians on the destination
            -- moves on: keep the record and try again at the next turn start; the row says who stands there.
            out[#out + 1] = { unit_id = id, x = pm.x, y = pm.y, held = true, reason = "own_unit_on_destination",
                              blocking_unit = r.blocking_unit,
                              err = r.err .. "; the standing move is kept and tries again next turn start" }
          else
            H.pending_moves[key] = nil
            out[#out + 1] = { unit_id = id, x = pm.x, y = pm.y, dropped = true, err = r.err }
          end
        end
      end
    end
  end
  return out
end

-- MISSION_FOUND pre/post check. PushMission(MISSION_FOUND) returns "ok" even when the settler has no
-- moves left (live t283: the standing order had just walked it onto the site, activity went to HOLD and
-- no city appeared), so the wrapper reads this before and after. (x, y) is the settler's plot, kept by
-- the caller because the unit is consumed on success.
function H.found_check(unit_id, x, y, pid)
  local p = Players[pid]
  local u = p:GetUnitByID(unit_id)
  local out = { ok = true, unit_exists = u ~= nil }
  if u then
    x, y = u:GetX(), u:GetY()
    out.x, out.y = x, y
    out.moves = u:MovesLeft() / GameDefines.MOVE_DENOMINATOR
    -- The roster is what names the unit once it is gone (SerialEventUnitDestroyed finds no unit): at turn 0
    -- no turn start has filled it yet and the founding Settler arrived in the digest as a bare id (live
    -- Assyria t0: "gone during your own turn with no combat" beside city_created). Note it before the mission.
    if H.note_unit then pcall(H.note_unit, u, pid) end
    -- Unit:CanFound(plot, n) wants a number for arg 2 (a boolean raises "number expected", the pcall
    -- swallowed it and every MISSION_FOUND was refused as "cannot found"; live t284). Omit it.
    local okc, v = pcall(function() return u:CanFound(u:GetPlot()) end)
    out.can_found = okc and v and true or false
    if not out.can_found then
      -- Why not (live Assyria t24: (19,28) three plots from Assur was refused with three possible reasons in one
      -- sentence). A city within MIN_CITY_RANGE plots blocks the site (the engine's findCity range: distance 3
      -- blocked with the define at 3, so cities need range + 1); a known city is named, a fogged one is not.
      pcall(function()
        local pl = u:GetPlot()
        local team = Teams and p.GetTeam and p:GetTeam() or nil
        if pl:IsWater() then out.water = true end
        local owner = pl:GetOwner()
        if owner and owner >= 0 and owner ~= pid then out.foreign_owner = H.owner_label(owner, pid) end
        local range = (GameDefines and tonumber(GameDefines.MIN_CITY_RANGE)) or 3
        out.min_distance = range + 1
        -- A City has Plot(), not GetPlot() (live Assyria t60: Malacca three plots from (19,23) raised "attempt to
        -- call method 'GetPlot'" inside this pcall, which lost the whole answer and left the refusal with its three
        -- guesses; an own city never reached the call). Each city's read is its own pcall, and the nearest one
        -- found so far is written out as it is found.
        for i = 0, (GameDefines and GameDefines.MAX_CIV_PLAYERS or 64) - 1 do
          local pp = Players[i]
          if pp and pp:IsAlive() then
            for c in pp:Cities() do
              local d = Map.PlotDistance(x, y, c:GetX(), c:GetY())
              if d <= range and (not out.nearest_city or d < out.nearest_city.distance) then
                local best = { distance = d, x = c:GetX(), y = c:GetY() }
                out.nearest_city = best
                pcall(function()
                  local cp = (c.Plot and c:Plot()) or Map.GetPlot(c:GetX(), c:GetY())
                  local seen = i == pid or (team ~= nil and cp ~= nil and cp:IsRevealed(team, false))
                  if seen then best.name, best.owner = c:GetName(), H.owner_label(i, pid) end
                end)
              end
            end
          end
        end
      end)
    end
  end
  local pl = (x and y) and Map.GetPlot(x, y) or nil
  if pl and pl:IsCity() then
    local c = pl:GetPlotCity()
    out.city = { id = c:GetID(), name = c:GetName(), owner = c:GetOwner(), x = x, y = y }
  end
  return out
end

-- A refused order must not cost the unit its standing move (live t26: a BUILD_FARM refused mid-walk wiped
-- the Worker's move_unit record, so resume_moves skipped it and it idled a turn as "stalled_mission").
function H.unit_mission(unit_id, mission, x, y, build, pid)
  local key = H.pm_key(unit_id, pid)
  local standing = H.pending_moves[key]
  local r = H.unit_mission_order(unit_id, mission, x, y, build, pid)
  local u = Players[pid] and Players[pid]:GetUnitByID(unit_id)
  local arrived = u and standing and u:GetX() == standing.x and u:GetY() == standing.y
  if type(r) == "table" and r.ok == false and standing and not arrived and H.pending_moves[key] == nil then
    H.pending_moves[key] = standing
    r.standing_move_kept = { x = standing.x, y = standing.y }
  end
  return r
end

function H.unit_mission_order(unit_id, mission, x, y, build, pid)
  local u, err = own_active_unit(unit_id, pid)
  if not u then return err end
  if mission == "MISSION_SKIP" then
    -- A skip on a unit that is mid-way through a multi-turn move cancels the engine's path (live t306:
    -- the Caravel's standing order to (54,29) died to a reflex MISSION_SKIP and it sat at (54,13) with
    -- 4 moves next turn). Such a unit does not block end_turn, so refuse instead of cancelling.
    -- A standing order whose destination the unit already stands on is finished, not "mid-way" (live
    -- t315: the Caravel arrived with 1 move left, the stale record refused every skip while the engine
    -- kept ENDTURN_BLOCKING_UNITS on it -- a refusal deadlock).
    local key = H.pm_key(unit_id, pid)
    local pm = H.pending_moves[key]
    if pm and pm.x == u:GetX() and pm.y == u:GetY() then H.pending_moves[key] = nil end
    local busy = (u.GetLengthMissionQueue and u:GetLengthMissionQueue() or 0) > 0
    if not busy and u.GetActivityType and ActivityTypes and u:GetActivityType() == ActivityTypes.ACTIVITY_MISSION then busy = true end
    -- ...but a stalled one blocks end_turn (todo() lists it), and refusing the skip there is a
    -- deadlock: turn_status says "this unit stops the turn", unit_mission says "it does not".
    -- A human at the same screen just presses Space.
    if (busy or H.pending_moves[key]) and not H.is_stalled_mission(u) then
      return { ok = false, err = "unit is already on a multi-turn move and does not block end_turn; "
                                 .. "MISSION_SKIP would cancel that path: give it a new order(to='unit', action='move') instead, "
                                 .. "or order(to='unit', action='mission', args={mission='COMMAND_CANCEL'}) to drop the path on purpose",
               x = u:GetX(), y = u:GetY() }
    end
  end
  H.pending_moves[H.pm_key(unit_id, pid)] = nil  -- a new order replaces any standing move
  if build ~= nil and build ~= "" and mission ~= "MISSION_BUILD" then
    return { ok = false, err = "build requires MISSION_BUILD" }
  end
  if type(mission) == "string" and mission:match("^AUTOMATE_") then
    -- Automation is a command, not a mission: the unit panel's button goes through Game.HandleAction ->
    -- GAMEMESSAGE_DO_COMMAND(COMMAND_AUTOMATE, automate type). Live t316: AUTOMATE_EXPLORE resolved to
    -- GameInfoTypes id 1 and went out as mission 1 = MISSION_ROUTE_TO(-1,-1), which "succeeded".
    local a = GameInfoTypes and GameInfoTypes[mission]
    if a == nil or not (CommandTypes and CommandTypes.COMMAND_AUTOMATE) then return { ok = false, err = "unknown automation" } end
    local ok, can = pcall(function() return u:CanAutomate(a) end)
    if not (ok and can) then return { ok = false, err = "action is not currently legal" } end
    local sent = do_command(u, CommandTypes.COMMAND_AUTOMATE, a, -1)
    if not sent.ok then return sent end
    return { ok = true, automate_pending = a }
  end
  -- COMMAND_* (delete/disband, wake, cancel...) are listed by available_unit_actions and go out as
  -- GAMEMESSAGE_DO_COMMAND like the unit panel's buttons; t370 unit_mission refused COMMAND_DELETE as an
  -- "unknown mission" although the action list offered it. Promotion/upgrade keep their own tools.
  if type(mission) == "string" and mission:match("^COMMAND_") then
    local c = CommandTypes and CommandTypes[mission]
    if c == nil then return { ok = false, err = "unknown command" } end
    if mission == "COMMAND_PROMOTION" or mission == "COMMAND_UPGRADE" then
      return { ok = false, err = "use order(to='unit', action='promote') / order(to='unit', action='upgrade') for this command" }
    end
    local ok, can = pcall(function() return u:CanDoCommand(c, -1, -1) end)
    if not (ok and can) then return { ok = false, err = "action is not currently legal" } end
    local sent = do_command(u, c, -1, -1)
    if not sent.ok then return sent end
    return { ok = true, command_pending = mission }
  end
  -- MISSION_SWAP_UNITS is accepted by the engine and does nothing in this build (live England t225, v272: an
  -- Infantry with full moves and a fortified Gatling Gun with full moves inside the city; the unit sat in
  -- ACTIVITY_MISSION, nothing moved, and the reply said ok). A raw MISSION_MOVE_TO onto the other combat
  -- unit is dropped too; the GAMEMESSAGE_SWAP_UNITS net message crashed the game. Two civilians do trade
  -- places through move_unit (the engine walks the other one back). Say so instead of claiming ok.
  if mission == "MISSION_SWAP_UNITS" then
    local hint = u:IsCombatUnit()
      and "move the unit on the destination out first, then this one in (two moves; a garrison swap takes a turn)"
      or "order(to='unit', action='move') onto the other civilian's plot: the engine swaps the two (swapped_with in the reply)"
    return { ok = false, err = "MISSION_SWAP_UNITS does nothing in this build: the engine accepts it and no unit moves",
             hint = hint, x = u:GetX(), y = u:GetY() }
  end
  -- Only real mission names: GameInfoTypes also maps builds, automates, units... to small ints that
  -- collide with mission ids (the AUTOMATE_EXPLORE -> MISSION_ROUTE_TO accident above).
  if not (MissionTypes and MissionTypes[mission] ~= nil) then
    return { ok = false, err = "unknown mission (use a MISSION_* name from state(what='unit', view='actions'); "
                               .. "AUTOMATE_* names are accepted too, builds go in build= with MISSION_BUILD)" }
  end
  local m = MissionTypes[mission]
  local d1, d2 = -1, -1
  if type(x) == "number" then d1 = x end
  if type(y) == "number" then d2 = y end
  if build ~= nil and build ~= "" then
    local b = info_id(build)
    if b == nil then return { ok = false, err = "unknown build" } end
    local legal = false
    if u.CanBuild then
      -- Unit:CanBuild(plot, build): with only the build id the call errors ("Instance does not
      -- exist"), the pcall swallows it, and every MISSION_BUILD was refused as "not legal".
      local ok, v = pcall(function() return u:CanBuild(u:GetPlot(), b) end)
      legal = ok and v
    end
    if not legal then return { ok = false, err = "action is not currently legal" } end
    -- The engine applies this turn's work the moment the build mission starts. A short build
    -- (BUILD_REPAIR, chops, anything whose remaining work fits in one turn) therefore FINISHES
    -- inside PushMission and GetBuildType() is already -1 again on return -- seen live twice
    -- (pasture + quarry repairs, China game t196/t198) and misreported as "did not start a
    -- build". Snapshot the plot so an instant completion is recognised instead.
    local pl = u:GetPlot()
    -- Owners of this plot and its neighbours: a Citadel annexes every adjacent tile, which is the
    -- only reason anyone builds one, and the old before/after diff watched improvements only.
    local before = { imp = pl:GetImprovementType(), pillaged = pl:IsImprovementPillaged(),
                     route = pl:GetRouteType(), route_pillaged = pl:IsRoutePillaged(),
                     feature = pl:GetFeatureType(), moves = u:MovesLeft(),
                     owners = H.plot_owners_around(pl, 1) }
    local pushed = push_mission(u, m, b, -1)
    if not pushed.ok then return pushed end
    -- The order lands on a later game update; the Python wrapper polls H.build_check with `before`.
    return { ok = true, pending = true, build_id = b, x = pl:GetX(), y = pl:GetY(), before = before }
  end
  if d1 >= 0 and d2 >= 0 then
    local blocked = require_revealed_plot(d1, d2, pid)
    if blocked then return blocked end
  else
    d1, d2 = -1, -1
  end
  local legal = false
  if u.CanStartMission then
    local ok, v = pcall(function() return u:CanStartMission(m, d1, d2, false) end)
    legal = ok and v
  end
  if not legal then return { ok = false, err = "action is not currently legal" } end
  if H.NEEDS_MOVES[mission] and u:MovesLeft() <= 0 then
    -- GitLab #83 (live Assyria t254): MISSION_SPACESHIP at 0 moves answered ok, the engine queued it on HOLD and
    -- never ran it, the Booster count stayed 0/3 and the part left todo. The same for every mission that acts
    -- (CvUnitMission starts it only when the unit can move); the hold missions (skip, sleep, fortify, alert,
    -- heal) work at 0 moves and are not in the table.
    return { ok = false, err = "the unit has no moves left this turn: the engine would hold " .. mission
                               .. " and never run it; order it next turn (or before moving)",
             x = u:GetX(), y = u:GetY(), moves = 0 }
  end
  local pushed = push_mission(u, m, d1, d2)
  if not pushed.ok then return pushed end
  if mission == "MISSION_ENHANCE_RELIGION" or mission == "MISSION_FOUND_RELIGION" then
    -- the Prophet is spent and the belief choice is open from now until it is made (#109)
    H.religion_pending = H.religion_pending or {}
    H.religion_pending[pid] = mission == "MISSION_ENHANCE_RELIGION" and "enhance" or "found"
  end
  return { ok = true }
end

-- Missions that act and need a move left to run (GitLab #83); pushed at 0 moves the engine holds them and does
-- nothing. MISSION_FOUND, RANGE_ATTACK and PILLAGE have their own earlier refusals on the Python side with the
-- unit's facts; they are here too so the rule holds for every caller.
H.NEEDS_MOVES = {
  MISSION_SPACESHIP = true, MISSION_PILLAGE = true, MISSION_FOUND = true, MISSION_RANGE_ATTACK = true,
  MISSION_SPREAD_RELIGION = true, MISSION_REMOVE_HERESY = true, MISSION_TRADE = true, MISSION_DISCOVER = true,
  MISSION_HURRY = true, MISSION_GOLDEN_AGE = true, MISSION_CULTURE_BOMB = true, MISSION_CREATE_GREAT_WORK = true,
  MISSION_ONE_SHOT_TOURISM = true, MISSION_GIVE_POLICIES = true, MISSION_BUY_CITY_STATE = true,
  MISSION_REPAIR_FLEET = true, MISSION_SELL_EXOTIC_GOODS = true, MISSION_PLUNDER_TRADE_ROUTE = true,
  MISSION_JOIN = true, MISSION_CONSTRUCT = true, MISSION_LEAD = true, MISSION_FOUND_RELIGION = true,
  MISSION_NUKE = true, MISSION_PARADROP = true, MISSION_AIR_ATTACK = true,
}

-- Poll after an AUTOMATE_* command: the engine flags the unit automated once the command lands (and
-- an explorer may already have moved on the same update).
function H.automate_check(unit_id, pid)
  local u = Players[pid]:GetUnitByID(unit_id)
  if not u then return { ok = true, gone = true } end
  return { ok = true, automated = u:IsAutomated(),
           x = u:GetX(), y = u:GetY(), moves = u:MovesLeft() / move_denom() }
end

-- Poll after a MISSION_BUILD: `started` when GetBuildType() shows the build, `completed` when the plot
-- already changed (a short build -- BUILD_REPAIR, a chop -- finishes the moment it starts and
-- GetBuildType() is -1 again; seen live twice, China game t196/t198).
-- Owners of a plot and its neighbours, for the before/after diff of a build that moves borders.
-- Every read is guarded: this runs on the way into an ordinary worker build, where a missing getter
-- must cost the diff and nothing else.
function H.plot_owners_around(plot, r)
  local out = {}
  if not plot or not Map then return out end
  for dx = -r, r do for dy = -r, r do
    local ok, p2 = pcall(function()
      if Map.PlotXYWithRangeCheck then
        return Map.PlotXYWithRangeCheck(plot:GetX(), plot:GetY(), dx, dy, r)
      end
      return Map.GetPlot and Map.GetPlot(plot:GetX() + dx, plot:GetY() + dy) or nil
    end)
    if ok and p2 then
      pcall(function() out[p2:GetX() .. "," .. p2:GetY()] = p2:GetOwner() end)
    end
  end end
  return out
end

function H.build_check(unit_id, x, y, before, pid)
  local u = Players[pid]:GetUnitByID(unit_id)
  local pl = Map.GetPlot(x, y)
  local out = { ok = true, unit_exists = u ~= nil }
  local running = nil   -- the build in progress on the plot, the unit's own or (a dig, #140) the plot's record
  if u then
    out.buildtype = u.GetBuildType and u:GetBuildType() or -1
    out.moves = u:MovesLeft() / move_denom()
    running = H.unit_build and H.unit_build(u, pid, pl) or nil
    if running and running.from_plot and (u:GetX() ~= x or u:GetY() ~= y) then running = nil end
    out.started = running ~= nil
    -- Name it: a bare id (15 for both a Silk plantation and a forest-hill mine, live t79) said nothing.
    if running then
      out.build = running.build
      out.buildtype = running.id or out.buildtype
      out.turns_left = running.turns_left   -- the unit row's number (builds.lua, #165)
      if running.from_plot then out.from_plot = true end
    end
  end
  if pl and before then
    local changed = pl:GetImprovementType() ~= before.imp or pl:IsImprovementPillaged() ~= before.pillaged
      or pl:GetRouteType() ~= before.route or pl:IsRoutePillaged() ~= before.route_pillaged
      or pl:GetFeatureType() ~= before.feature
    -- A dig clears the improvement under it the moment it starts (live t218: a Trading Post gone, the dig
    -- 4 turns out): a plot that changed while a build still runs on it has not completed anything.
    out.completed = changed and not running
    if running and before.imp and before.imp >= 0 and pl:GetImprovementType() ~= before.imp then
      pcall(function() out.replaced_improvement = short(info_type(GameInfo.Improvements, before.imp)) end)
    end
    if out.completed then
      pcall(function()
        local imp = pl:GetImprovementType()
        if imp and imp >= 0 and GameInfo.Improvements then
          out.improvement = short(info_type(GameInfo.Improvements, imp))
        end
      end)
      -- A Great Person is expended by its build; saying "the unit is gone" beats leaving the caller
      -- to notice that unit_exists went false.
      if not u then out.unit_consumed = true end
      if before.owners then
        local claimed = {}
        for key, was in pairs(before.owners) do
          local sx, sy = key:match("^(-?%d+),(-?%d+)$")
          local p2 = sx and Map.GetPlot(tonumber(sx), tonumber(sy))
          if p2 and p2:GetOwner() ~= was and p2:GetOwner() == pid then
            local row = { x = tonumber(sx), y = tonumber(sy) }
            -- Taking a tile off another civ is an incident the stock tooltip warns about; name them.
            if was and was >= 0 then
              row.taken_from = was
              row.taken_from_name = H.owner_label(was, pid)
            end
            claimed[#claimed + 1] = row
          end
        end
        if #claimed > 0 then out.claimed_plots = claimed end
      end
    end
  end
  return out
end

function H.unit_is_automated(unit_id, pid)
  local u = Players[pid]:GetUnitByID(unit_id)
  return u ~= nil and u:IsAutomated() or false
end

-- Standing-move bookkeeping (keyed per seat since the hotseat fix, H.pm_key).
function H.drop_pending_move(unit_id, pid)
  H.pending_moves[H.pm_key(unit_id, pid)] = nil
  return true
end

function H.drop_pending_move_at(unit_id, x, y, pid)
  local k = H.pm_key(unit_id, pid)
  local pm = H.pending_moves[k]
  if pm and pm.x == x and pm.y == y then H.pending_moves[k] = nil; return true end
  return false
end
