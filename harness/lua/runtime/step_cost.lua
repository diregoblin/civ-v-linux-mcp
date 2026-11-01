-- Shared by earlier fragments (load order: harness/runtime_source.py MANIFEST).
local move_denom, remembered_feature_id = H._ns.move_denom, H._ns.remembered_feature_id
local info_type, short = H._ns.info_type, H._ns.short

-- What one step onto a neighbouring plot costs this unit, and whether zone of control ends its move there (GitLab
-- #180, Celts t11: a Warrior with 2 moves stepped onto open plains beside a barbarian and arrived with 0).
-- The engine's own answer is Plot:MovementCost, and that call crashed the game even inside pcall (t183,
-- docs/LIMITATIONS.md), so this is BNW's CvUnitMovement::MovementCost read off the facts it reads, each from the
-- engine's own getters and tables:
--   every move left: a river crossed without a bridge (Unit:IsRiverCrossingNoPenalty; Team:IsBridgeBuilding with a
--     usable route on both plots), embarking or disembarking, or zone of control -- leaving a plot next to a visible
--     enemy combat unit or enemy city for another plot next to the same enemy (the pedia's rule; an IgnoreZOC
--     promotion exempts the unit);
--   one move: a unit with FlatMovementCost, or a Danish-style disembark (Traits.EmbarkedToLandFlatCost);
--   otherwise the feature's Movement (the terrain's without one), +HILLS_EXTRA_MOVEMENT on hills without a city, less
--     GetExtraMoveDiscount, halved by a hills / terrain / feature double-move promotion, one on hills for a
--     FasterInHills trait, +1 for the Great Wall's border; a usable road or railroad on both plots caps it at the
--     route's Movement (+ the team's GetRouteChange) or FlatMovement x the unit's base moves.
-- A step never spends more than the unit has: with any moves left it may enter, and arrives with none.
-- Fog: a fogged plot is read as last seen (remembered feature, revealed route and owner), never live.

local function yes(obj, method, ...)
  local f = obj and obj[method]
  if not f then return false end
  local ok, v = pcall(f, obj, ...)
  return (ok and v) and true or false
end

local function number(obj, method, ...)
  local f = obj and obj[method]
  if not f then return 0 end
  local ok, v = pcall(f, obj, ...)
  return (ok and type(v) == "number") and v or 0
end

local function round2(x) return math.floor(x * 100 + 0.5) / 100 end

-- The leader traits the cost reads (GameInfo.Leader_Traits, as the briefing's civ card reads them).
local TRAIT_FLAGS = { "FasterInHills", "MoveFriendlyWoodsAsRoad", "EmbarkedToLandFlatCost" }
local function trait_flags(p)
  local out = {}
  pcall(function()
    local leader = GameInfo.Leaders[p:GetLeaderType()]
    for row in GameInfo.Leader_Traits{ LeaderType = leader.Type } do
      local t = GameInfo.Traits[row.TraitType]
      if t then
        for _, k in ipairs(TRAIT_FLAGS) do if t[k] == true or t[k] == 1 then out[k] = true end end
      end
    end
  end)
  return out
end

-- An IgnoreZOC promotion on the unit (UnitPromotions.IgnoreZOC; the engine's Lua names no getter for it).
local function ignores_zoc(u)
  local ok, v = pcall(function()
    for row in GameInfo.UnitPromotions() do
      if (row.IgnoreZOC == true or row.IgnoreZOC == 1) and u:IsHasPromotion(row.ID) then return true end
    end
    return false
  end)
  return (ok and v) and true or false
end

local function hostile_team(team, other)
  local op = Players[other]
  if not op then return false end
  if op:IsBarbarian() then return true end
  return yes(Teams[team], "IsAtWar", op:GetTeam())
end

-- Every visible enemy whose zone of control reaches out of the plot the unit stands on: an enemy city or an enemy
-- combat unit next to it (CvUnitMovement::IsSlowedByZOC: an embarked enemy exerts none on a land unit; an enemy
-- ship's reaches a land unit only onto water). The plots next to the unit are in its sight.
local function zoc_sources(u, pid, team)
  local out = {}
  if GameDefines and GameDefines.ZONE_OF_CONTROL_ENABLED == 0 then return out end
  if ignores_zoc(u) then return out end
  local land, sea = DomainTypes and DomainTypes.DOMAIN_LAND or 0, DomainTypes and DomainTypes.DOMAIN_SEA or 1
  local dom = u:GetDomainType()
  for d = 0, 5 do
    local p = Map.PlotDirection(u:GetX(), u:GetY(), d)
    if p and p:IsVisible(team, false) then
      local px, py = p:GetX(), p:GetY()
      local c = H.enemy_city_at(p, pid)
      if c then out[#out + 1] = { x = px, y = py, city = c:GetName(), owner = c:GetOwner() } end
      for i = 0, p:GetNumUnits() - 1 do
        local o = p:GetUnit(i)
        if o and o:IsCombatUnit() and not o:IsInvisible(team, false) and not yes(o, "IsDelayedDeath")
           and hostile_team(team, o:GetOwner()) then
          local odom = o:GetDomainType()
          if (odom == dom or odom == sea) and not (dom == land and yes(o, "IsEmbarked")) then
            out[#out + 1] = { x = px, y = py, id = o:GetID(), unit = short(info_type(GameInfo.Units, o:GetUnitType())),
                              owner = o:GetOwner(), water_only = (odom ~= dom) or nil }
          end
        end
      end
    end
  end
  return out
end

-- The facts of a plot the cost reads, under the human's fog: a fogged plot as last seen.
local function plot_facts(q, team, city)
  local f = { water = q:IsWater() and true or false, hills = q:IsHills() and true or false, terrain = q:GetTerrainType(),
              city = city and true or false }
  if q:IsVisible(team, false) then
    f.feature, f.route, f.owner = q:GetFeatureType(), q:GetRouteType(), q:GetOwner()
    f.route_pillaged = yes(q, "IsRoutePillaged")
  else
    f.feature = remembered_feature_id(q, team) or -1
    f.route, f.owner = q:GetRevealedRouteType(team, false), q:GetRevealedOwner(team, false)
  end
  return f
end

-- Returns cost(q, city, crossing) for the unit's neighbours: { cost, left, zoc } in moves, or nil for a unit whose
-- step has no cost to read (an air unit). `city`: a city stands on q (as the reply knows it); `crossing`: the step
-- crosses a river edge. With no moves left the step is priced from next turn's full moves, as the engine does.
local function step_costs(u, pid)
  local p = Players[pid]
  local team = p:GetTeam()
  local denom = move_denom()
  local land = DomainTypes and DomainTypes.DOMAIN_LAND or 0
  local dom = u:GetDomainType()
  if DomainTypes and dom == DomainTypes.DOMAIN_AIR then return nil end
  local max = number(u, "MaxMoves")
  local have = u:MovesLeft()
  if have <= 0 then have = max end
  local base = math.max(1, math.floor(max / denom))
  local traits = trait_flags(p)
  local hills_extra = (GameDefines and GameDefines.HILLS_EXTRA_MOVEMENT) or 1
  local here = plot_facts(u:GetPlot(), team, false)
  local zoc = zoc_sources(u, pid, team)
  local unit = {
    ignore_terrain = yes(u, "IgnoreTerrainCost"), flat = yes(u, "FlatMovementCost"),
    discount = number(u, "GetExtraMoveDiscount"), hills_double = yes(u, "IsHillsDoubleMove"),
    no_river_penalty = yes(u, "IsRiverCrossingNoPenalty"), enemy_route = yes(u, "IsEnemyRoute"),
    embarked = yes(u, "IsEmbarked"),
  }
  local bridges = yes(Teams[team], "IsBridgeBuilding")

  local function usable_route(f)
    if f.route == nil or f.route < 0 or f.route_pillaged then return false end
    return unit.enemy_route or f.owner == nil or f.owner < 0 or not hostile_team(team, f.owner)
  end
  local function route_costs(rt)
    local row = GameInfo.Routes[rt] or {}
    return (row.Movement or 0) + number(Teams[team], "GetRouteChange", rt), (row.FlatMovement or 0) * base
  end

  -- CvUnitMovement::GetCostsForMove, in 60ths of a move.
  local function terrain_cost(to)
    local regular
    if unit.ignore_terrain then regular = 1
    else
      local row = (to.feature >= 0) and GameInfo.Features[to.feature] or GameInfo.Terrains[to.terrain]
      regular = (row and row.Movement) or 1
      if to.hills and not to.city then regular = regular + hills_extra end
      if regular > 0 then regular = math.max(1, regular - unit.discount) end
      if traits.FasterInHills and to.hills then regular = 1 end
    end
    regular = regular * denom
    if unit.hills_double and to.hills then regular = math.floor(regular / 2)
    elseif to.feature >= 0 then
      if yes(u, "IsFeatureDoubleMove", to.feature) then regular = math.floor(regular / 2) end
    elseif yes(u, "IsTerrainDoubleMove", to.terrain) then regular = math.floor(regular / 2) end
    if dom == land and not to.water and to.owner and to.owner >= 0 then
      local op = Players[to.owner]
      local ot = op and op:GetTeam()
      if ot and ot ~= team and (yes(Teams[ot], "IsBorderObstacle") or yes(op, "IsBorderObstacle"))
         and not yes(Teams[ot], "IsAllowsOpenBordersToTeam", team) then
        regular = regular + denom   -- the Great Wall
      end
    end
    local best = regular
    if usable_route(here) and usable_route(to) and (bridges or not to.crossing) then
      local m1, f1 = route_costs(here.route)
      local m2, f2 = route_costs(to.route)
      best = math.min(best, math.max(m1, m2), math.max(f1, f2))
    elseif traits.MoveFriendlyWoodsAsRoad and to.owner == pid and to.feature >= 0 and GameInfoTypes
           and (to.feature == GameInfoTypes.FEATURE_FOREST or to.feature == GameInfoTypes.FEATURE_JUNGLE)
           and GameInfoTypes.ROUTE_ROAD then
      local m, f = route_costs(GameInfoTypes.ROUTE_ROAD)
      best = math.min(best, m, f)
    end
    return math.max(1, best)
  end

  return function(q, city, crossing)
    local to = plot_facts(q, team, city)
    to.crossing = crossing and true or false
    local out = {}
    for _, s in ipairs(zoc) do
      if Map.PlotDistance(s.x, s.y, q:GetX(), q:GetY()) == 1 and (not s.water_only or to.water) then
        out.zoc = { x = s.x, y = s.y, id = s.id, unit = s.unit, city = s.city, owner = s.owner }
        break
      end
    end
    local spent
    local embarking = dom == land and (unit.embarked or here.water) ~= to.water
    local bridged = bridges and usable_route(here) and usable_route(to)
    if out.zoc then spent = have
    elseif embarking and not to.water and traits.EmbarkedToLandFlatCost then spent = denom
    elseif embarking or (dom == land and to.crossing and not unit.no_river_penalty and not bridged) then spent = have
    elseif unit.flat then spent = denom
    else spent = terrain_cost(to) end
    spent = math.min(spent, have)
    out.cost, out.left = round2(spent / denom), round2((have - spent) / denom)
    return out
  end
end

-- Shared with later fragments, which import it at their top (load order: harness/runtime_source.py MANIFEST).
H._ns.step_costs = step_costs
