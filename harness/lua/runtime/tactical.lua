-- Shared by earlier fragments (load order: harness/runtime_source.py MANIFEST).
local info_id, info_type, move_denom = H._ns.info_id, H._ns.info_type, H._ns.move_denom
local short, step_costs = H._ns.short, H._ns.step_costs

-- ActivityTypes by the engine's own names (raw ints otherwise mean nothing to a caller), the words units() reads
-- through H.unit_activity. ACTIVITY_SLEEP is both a sleep and a fortify; `hold` (H.unit_hold_state) says which
-- (GitLab #176: "SLEEP_OR_FORTIFY" here and "SLEEP" in the unit list described one warrior two ways).
local ACTIVITY_NAMES = { [0] = "AWAKE", [1] = "HOLD", [2] = "SLEEP", [3] = "HEAL", [4] = "SENTRY", [5] = "INTERCEPT", [6] = "MISSION" }
function H.activity_name(a) return ACTIVITY_NAMES[a] or tostring(a) end

-- reveal=true (the read-back after move_unit): adds `revealed`, what the move showed (H.reveal_diff).
function H.unit_pos(unit_id, pid, reveal)
  local u = Players[pid]:GetUnitByID(unit_id)
  if not u then return { ok = false, err = "no such unit" } end
  local denom = move_denom()
  local out = {
    ok = true, x = u:GetX(), y = u:GetY(),
    moves = u:MovesLeft() / denom,
    activity = u.GetActivityType and u:GetActivityType() or nil,
    activity_name = u.GetActivityType and H.activity_name(u:GetActivityType()) or nil,
    buildtype = u.GetBuildType and u:GetBuildType() or nil,
    hold = H.unit_hold_state(u),   -- #176: fortified or fortifying, and whether the end-turn list still wants it
  }
  if reveal then
    local okr, diff = pcall(H.reveal_diff, unit_id, pid)
    if okr then out.revealed = diff end
  end
  return out
end

-- Where the known map ends for one unit: revealed, passable plots of the unit's domain that touch at
-- least one unrevealed plot, nearest first. This is the fog boundary a human sees on the minimap --
-- the only thing read about an unrevealed plot is that it is unrevealed (IsRevealed), never its
-- terrain, owner or occupants. move_unit refuses unrevealed targets, so an explorer uses this to pick
-- its next stop instead of guessing coordinates.
function H.explore_frontier(unit_id, pid, limit)
  local u = Players[pid]:GetUnitByID(unit_id)
  if not u then return { ok = false, err = "no such unit" } end
  local team = Players[pid]:GetTeam()
  local sea = (u:GetDomainType() == DomainTypes.DOMAIN_SEA)
  local embarked = (u.IsEmbarked and u:IsEmbarked()) and true or false
  local ux, uy = u:GetX(), u:GetY()
  local out, unrevealed = {}, 0
  local w, h = Map.GetGridSize()
  local function traversable(p)
    -- IsImpassable() is false for a mountain in this build (live 2026-09-18: (42,27) offered as reachable
    -- DESERT, move_unit refused it) -- mountains are a plot type, not an impassable terrain/feature.
    return not p:IsImpassable() and not p:IsMountain() and (p:IsWater() == sea or (embarked and p:IsWater()))
  end
  -- Borders: the engine's pathfinder will not cross another civ's territory without open borders (or a
  -- war), and refused a city-state's coast outright (live t287: Caravel -> (53,32) inside Sidon, "no
  -- path" although the flood fill said reachable). Owner is the last-seen owner a human sees on the
  -- map (GetRevealedOwner), never the true one on a fogged plot.
  local open_cache = {}
  local function closed_owner(p)
    local o = p.GetRevealedOwner and p:GetRevealedOwner(team, false) or (p.GetOwner and p:GetOwner()) or -1
    if o == nil or o < 0 or o == pid then return nil end
    if open_cache[o] == nil then
      local ot = Players[o] and Players[o]:GetTeam() or -1
      local ok = (ot == team)
      if not ok and ot >= 0 and Teams then
        local mine, theirs = Teams[team], Teams[ot]
        ok = (mine and mine.IsAtWar and mine:IsAtWar(ot)) and true or false
        if not ok and theirs and theirs.IsAllowsOpenBordersToTeam then ok = theirs:IsAllowsOpenBordersToTeam(team) and true or false end
      end
      open_cache[o] = ok
    end
    if open_cache[o] then return nil end
    return o
  end
  -- Flood fill from the unit over revealed, traversable plots: which frontier plots are reachable
  -- through the KNOWN map (Unit:GeneratePath is NYI here, so this is the only path hint). A plot on
  -- the far side of a landmass is reachable=false even when its hex distance is small (live t272:
  -- the Caravel was sent to (52,6), distance 2, and the engine detoured it west for two turns).
  -- Only IsRevealed is read on fogged plots; the fill never steps into them.
  local reached, frontier_queue, head = {}, {}, 1
  local function key(x, y) return y * w + x end
  reached[key(ux, uy)] = true
  frontier_queue[1] = Map.GetPlot(ux, uy)
  while head <= #frontier_queue do
    local c = frontier_queue[head]; head = head + 1
    local cx, cy = c:GetX(), c:GetY()
    for dx = -1, 1 do for dy = -1, 1 do
      local q = Map.PlotXYWithRangeCheck(cx, cy, dx, dy, 1)
      if q and not reached[key(q:GetX(), q:GetY())] and q:IsRevealed(team, false) and traversable(q) and not closed_owner(q) then
        reached[key(q:GetX(), q:GetY())] = true
        frontier_queue[#frontier_queue + 1] = q
      end
    end end
  end
  for i = 0, Map.GetNumPlots() - 1 do
    local p = Map.GetPlotByIndex(i)
    if p then
      if not p:IsRevealed(team, false) then
        unrevealed = unrevealed + 1
      elseif traversable(p) then
        local px, py, n = p:GetX(), p:GetY(), 0
        for dx = -1, 1 do for dy = -1, 1 do
          local q = Map.PlotXYWithRangeCheck(px, py, dx, dy, 1)
          if q and (q:GetX() ~= px or q:GetY() ~= py) and not q:IsRevealed(team, false) then n = n + 1 end
        end end
        if n > 0 then
          local e = { x = px, y = py, unrevealed_neighbors = n,
                      distance = Map.PlotDistance(ux, uy, px, py),
                      reachable = reached[key(px, py)] == true,
                      t = short(info_type(GameInfo.Terrains, p:GetTerrainType())) }
          -- The map's top/bottom rows are the polar ice a human sees on the minimap frame; a frontier
          -- plot there mostly reveals more ice, so flag it rather than let it outrank real coastline.
          -- (rows 0-1 and h-2..h-1 are the ice; a plot on row 2 only borders it, so flag it too: live
          -- t272 the whole y=2 row outranked the real eastern coastline)
          if py <= 2 or py >= h - 3 then e.map_edge = true end
          local co = closed_owner(p)
          if co then e.closed_border = co end  -- owner id: a border the unit may not cross (no open borders)
          -- v266: a visible unit of another player on the plot (live 2026-10-08, England t129 and t130: the top
          -- row was an Ottoman Gatling Gun's plot, then an Ottoman Worker's; move_unit refuses both, a human sees
          -- the unit). Named and sorted after the free plots, never dropped: it is still where the fog ends.
          -- v268: a visible city of another player on the plot is named the same way (`city`): move_unit refuses
          -- it at peace and a human sees the banner (live England t138: Edirne's own plot bordered the fog, and its
          -- row said only that a Great General stood there).
          local okv, vis = pcall(function() return p:IsVisible(team, false) end)
          if okv and vis then
            pcall(function()
              if p:IsCity() then
                local c = p:GetPlotCity()
                if c and c:GetOwner() ~= pid then e.city = { player_id = c:GetOwner(), name = c:GetName() } end
              end
            end)
            pcall(function()
              for k = 0, p:GetNumUnits() - 1 do
                local o = p:GetUnit(k)
                if o and o:GetOwner() ~= pid and not (o.IsInvisible and o:IsInvisible(team, false)) then
                  e.occupied = { player_id = o:GetOwner(), unit = short(info_type(GameInfo.Units, o:GetUnitType())) }
                  break
                end
              end
            end)
          end
          out[#out + 1] = e
        end
      end
    end
  end
  -- A held plot (a foreign unit or city on it) sorts after the free ones, so frontier[1] is always a plot the
  -- explorer can walk to when one exists.
  local function held(e) return e.occupied ~= nil or e.city ~= nil end
  table.sort(out, function(a, b)
    if a.reachable ~= b.reachable then return a.reachable end
    if held(a) ~= held(b) then return not held(a) end
    if a.distance ~= b.distance then return a.distance < b.distance end
    if a.unrevealed_neighbors ~= b.unrevealed_neighbors then return a.unrevealed_neighbors > b.unrevealed_neighbors end
    if a.x ~= b.x then return a.x < b.x end
    return a.y < b.y
  end)
  local frontier_total = #out
  limit = limit or 12
  -- v268: the cut keeps the nearest `limit` free plots and, after them, every held plot no farther than the
  -- farthest free plot shown (at most `limit` of those). Cutting the sorted list at `limit` dropped every held
  -- row as soon as the frontier was longer than the limit: live England t138, 143 frontier plots, an Ottoman
  -- Rifleman two plots from the scout and Edirne's plot at three sorted 59th and 60th, behind every free plot,
  -- out of reach of any limit the tool accepts. A unit two plots away is frontier the explorer walks around.
  if #out > limit then
    local kept, n_free, far = {}, 0, 0
    for _, e in ipairs(out) do
      if not held(e) and n_free < limit then
        n_free = n_free + 1; kept[n_free] = e
        if e.distance > far then far = e.distance end
      end
    end
    if n_free == 0 then far = math.huge end
    local n_held = 0
    for _, e in ipairs(out) do
      if held(e) and e.distance <= far and n_held < limit then n_held = n_held + 1; kept[#kept + 1] = e end
    end
    out = kept
  end
  return { ok = true, unit = { id = unit_id, x = ux, y = uy, domain = sea and "SEA" or "LAND", embarked = embarked },
           map = { width = w, height = h }, unrevealed_plots = unrevealed,
           frontier_total = frontier_total, frontier = out,
           note = (frontier_total == 0) and ((unrevealed == 0) and "the whole map is revealed"
                  or "no revealed plot of this unit's domain borders the fog; the remaining fog is not reachable from here without embarking or another unit") or nil }
end

-- The six neighbours in the engine's own direction order, with the name a caller can say back.
local DIRECTION_NAMES = { "NE", "E", "SE", "SW", "W", "NW" }

-- Whether stepping from `a` to its neighbour `b` in direction index d (0 = NE .. 5 = NW) crosses a river.
-- A plot stores the river on three of its edges: IsWOfRiver = its east edge, IsNWOfRiver = its south-east
-- edge, IsNEOfRiver = its south-west edge (the setters AssignStartingPlots and the map scripts use); the
-- other three edges belong to the neighbour. Static terrain, read only for revealed plots.
local function river_crossing(a, b, d)
  local ok, v = pcall(function()
    if d == 0 then return b:IsNEOfRiver() end
    if d == 1 then return a:IsWOfRiver() end
    if d == 2 then return a:IsNWOfRiver() end
    if d == 3 then return a:IsNEOfRiver() end
    if d == 4 then return b:IsWOfRiver() end
    return b:IsNWOfRiver()
  end)
  return (ok and v) and true or nil
end

-- A plot's grid cell: ground letter then occupant letter (the legend is the reply reference, docs/TOOL_REPLIES.md state(what="unit", view="tactical"); GitLab #152).
-- The ground is the terrain, or C for a city in sight: the city is the plot, its units are what stands on it, so a unit
-- in a city keeps the city drawn (GitLab #177, Celts t4: a Scout on Edinburgh read ".@" and the city was gone).
-- Fog rules as describe_plot: a fogged plot shows remembered terrain and '?' for its occupant.
local ROUGH_FEATURES = { FOREST = true, JUNGLE = true, MARSH = true }
local function tactical_cell(q, team, u, pid, hostile_at)
  if not q then return "  " end
  if not q:IsRevealed(team, false) then return "__" end
  local t = "."
  if q:IsVisible(team, false) and q:IsCity() then t = "C"
  elseif q:IsMountain() or q:IsImpassable() then t = "M"
  elseif q:IsWater() then t = "~"
  elseif q:IsHills() then t = "H"
  else
    local f
    if q:IsVisible(team, false) then
      local fid = q:GetFeatureType()
      f = fid >= 0 and short(info_type(GameInfo.Features, fid)) or nil
    else
      f = H.remembered_feature(q, team)
    end
    if f and ROUGH_FEATURES[f] then t = "F" end
  end
  if not q:IsVisible(team, false) then return t .. "?" end
  if q:GetX() == u:GetX() and q:GetY() == u:GetY() then return t .. "@" end
  local k = q:GetX() .. "," .. q:GetY()
  if hostile_at[k] then return t .. "X" end
  local mine, other = false, false
  for i = 0, q:GetNumUnits() - 1 do
    local o = q:GetUnit(i)
    if o and not o:IsInvisible(team, false) then
      if o:GetOwner() == pid then mine = true else other = true end
    end
  end
  if other then return t .. "o" end
  if mine then return t .. "u" end
  return t .. " "
end

-- #31: one bounded read around one unit -- the picture a human gets by looking at the map around a selected
-- unit, with the relationships spelled out: the six neighbours by coordinate (the engine's PlotDirection, so
-- map wrap and the edge rows are the engine's own answer), what move_unit would do with each, the visible
-- occupants and known cities in `radius`, and the unit's attack targets with the combat panel's own previews
-- (H.melee_targets / H.ranged_targets, not a second combat model). Fog is the human's: a fogged plot shows
-- what was last seen and never a live occupant; an unrevealed one shows nothing but that it is unrevealed.
-- Movement: `move` is move_unit's own answer before it sends anything (H.move_refusal, the same checks); an open
-- step says what it costs this unit (`cost`, `left`, in moves) and names the enemy whose zone of control ends the
-- move there (`zoc`), from step_cost.lua (GitLab #180). There are no turns-to-reach: Unit:GeneratePath is NYI and
-- Plot:MovementCost crashes the game (docs/LIMITATIONS.md).
function H.tactical_view(unit_id, pid, radius, detail)
  local p = Players[pid]
  local u = p and p:GetUnitByID(unit_id)
  if not u then return { ok = false, err = "no such unit" } end
  local radius_given = radius ~= nil
  radius = radius or 2
  local full = (detail == "full")
  local team = p:GetTeam()
  local ux, uy = u:GetX(), u:GetY()
  local here = Map.GetPlot(ux, uy)
  local denom = move_denom()
  local moves = u:MovesLeft() / denom
  local unit = { id = unit_id, type = short(info_type(GameInfo.Units, u:GetUnitType())), x = ux, y = uy,
                 moves = moves, hp = u:GetCurrHitPoints(), max_hp = u:GetMaxHitPoints() }
  pcall(function() unit.max_moves = u:MaxMoves() / denom end)
  pcall(function()
    unit.domain = (u:GetDomainType() == DomainTypes.DOMAIN_SEA and "SEA")
                  or (u:GetDomainType() == DomainTypes.DOMAIN_AIR and "AIR") or "LAND"
  end)
  if u.IsEmbarked and u:IsEmbarked() then unit.embarked = true end
  unit.territory = H.plot_territory(here, pid)   -- v248: whose land the unit stands on, when not its own
  if u:IsCombatUnit() then
    pcall(function() unit.strength = u:GetBaseCombatStrength() end)
    pcall(function()
      local rs = H.ranged_strength(u)
      if rs > 0 then
        unit.ranged_strength = rs
        local row = GameInfo.Units[u:GetUnitType()]
        unit.range = (u.Range and u:Range()) or (row and row.Range) or nil   -- Range(): promotions count
      end
    end)
  else
    unit.civilian = true
  end

  -- v261: the unit's own line of sight, from the engine's CvPlot::canSeePlot -- the test canRangeStrikeAt makes
  -- for a ranged unit that does not ignore LOS, with the unit's attack range in place of its sight: high ground
  -- adds a plot, hills and forest in between block. Live t183 (Venice): a Crossbowman on hills saw 31 plots out
  -- to 3 and could fire at all of them, one on flat ground 24, a Musketman 20 -- the fixed radius 2 drew 18
  -- either way and never listed the ring a hill lets a ranged unit shoot into. With no radius given the view
  -- reaches as far as the unit itself sees or shoots (at least 2, at most 5).
  local los, fire_los, probed = {}, {}, {}
  local sight = { range = 0, on_hills = here:IsHills() and true or false, plots = 0, reach = 0 }
  pcall(function() sight.range = u:VisibilityRange() or 0 end)
  local fire = nil
  if unit.range and unit.range > 0 then
    fire = { range = unit.range, plots = 0, reach = 0 }
    pcall(function() if u:IsRangeAttackIgnoreLOS() then fire.ignores_los = true end end)
  end
  if here.CanSeePlot and (sight.range > 0 or fire) then
    -- The unit sees the plot it stands on: the probe below skips it (CanSeePlot is asked of other plots), so a
    -- garrisoned Archer's own city read in_sight false at distance 0 (GitLab #131, Siam t4 and t31). Its fire
    -- LOS stays unset there: a ranged unit cannot target its own plot.
    if sight.range > 0 then los[ux .. "," .. uy] = true end
    local probe = math.min(5, math.max(sight.range, fire and fire.range or 0) + 1)
    for dx = -probe, probe do for dy = -probe, probe do
      local q = Map.PlotXYWithRangeCheck(ux, uy, dx, dy, probe)
      if q and not (q:GetX() == ux and q:GetY() == uy) then
        local k = q:GetX() .. "," .. q:GetY()
        if not probed[k] then
          probed[k] = true
          local d = math.floor(Map.PlotDistance(ux, uy, q:GetX(), q:GetY()))  -- an integer: it sizes the loops below
          local ok_s, s_ok = pcall(function() return sight.range > 0 and here:CanSeePlot(q, team, sight.range, -1) end)
          if ok_s and s_ok then
            los[k] = true; sight.plots = sight.plots + 1
            if d > sight.reach then sight.reach = d end
          end
          if fire then
            local can
            if fire.ignores_los then can = d <= fire.range
            else
              local ok_f, f_ok = pcall(function() return here:CanSeePlot(q, team, fire.range, -1) end)
              can = ok_f and f_ok
            end
            if can then
              fire_los[k] = true; fire.plots = fire.plots + 1
              if d > fire.reach then fire.reach = d end
            end
          end
        end
      end
    end end
  end
  unit.sight = sight
  if fire then unit.fire_los = fire end
  local radius_from = "given"
  if not radius_given then
    local reach = math.max(sight.reach, fire and fire.reach or 0)
    if reach > 2 then radius = math.min(5, reach); radius_from = "sight" else radius_from = "default" end
  end

  local players = {}
  local function label(o)
    if o and o >= 0 then players[tostring(o)] = players[tostring(o)] or H.owner_label(o, pid) end
    return o
  end

  -- Attack targets with the combat panel's previews; the summary keeps the numbers, full keeps the modifiers.
  local targets = {}
  local attack_at = {}
  for _, list in ipairs({ H.melee_targets(u, pid), H.ranged_targets(u, pid) }) do
    for _, t in ipairs(list) do
      if not full and t.preview and t.preview.modifiers then
        -- The summary keeps the numbers; the modifier rows become one line a side (#121: the agent wanted to see
        -- where an 8-strength Warrior's 9.6 came from without the full view).
        local brief = {}
        for _, side in ipairs({ "mine", "theirs" }) do
          local rows = t.preview.modifiers[side]
          if type(rows) == "table" and #rows > 0 then
            local parts = {}
            for _, m in ipairs(rows) do
              if type(m) == "table" and m.text then
                local v = m.value
                local vs = v and ((v > 0 and "+" or "") .. tostring(v) .. (m.percent and "%" or "")) or nil
                parts[#parts + 1] = vs and (tostring(m.text) .. " " .. vs) or tostring(m.text)
              end
            end
            if #parts > 0 then brief[side] = table.concat(parts, "; ") end
          end
        end
        if next(brief) then t.preview.modifiers_brief = brief end
        t.preview.modifiers = nil
      end
      t.kind = (t.how and t.how:find("RANGE", 1, true)) and "ranged" or "melee"
      if t.kind == "melee" then attack_at[t.x .. "," .. t.y] = t end
      targets[#targets + 1] = t
    end
  end

  -- Visible occupants and known cities in radius; fog counts.
  local occupants, cities, hostile_at = {}, {}, {}
  local fog = { visible = 0, fogged = 0, unrevealed = 0, unseen_within_2 = 0 }
  -- The plots in radius once each (on a wrapped map narrower than the square, two offsets name one plot).
  local area, seen_plot = {}, {}
  for dx = -radius, radius do for dy = -radius, radius do
    local q = Map.PlotXYWithRangeCheck(ux, uy, dx, dy, radius)
    if q and not seen_plot[q:GetX() .. "," .. q:GetY()] then
      seen_plot[q:GetX() .. "," .. q:GetY()] = true
      area[#area + 1] = q
    end
  end end
  for _, q in ipairs(area) do
    do
      local qx, qy = q:GetX(), q:GetY()
      local d = Map.PlotDistance(ux, uy, qx, qy)
      if not q:IsRevealed(team, false) then
        fog.unrevealed = fog.unrevealed + 1
        if d <= 2 then fog.unseen_within_2 = fog.unseen_within_2 + 1 end
      elseif not q:IsVisible(team, false) then
        fog.fogged = fog.fogged + 1
        if d <= 2 then fog.unseen_within_2 = fog.unseen_within_2 + 1 end
        pcall(function()
          local c = q:IsCity() and q:GetPlotCity()
          if c and c:IsRevealed(team, false) then
            cities[#cities + 1] = { x = qx, y = qy, distance = d, name = c:GetName(), owner = label(c:GetOwner()),
                                    last_seen = true }
          end
        end)
      else
        fog.visible = fog.visible + 1
        if q:IsCity() then
          local c = q:GetPlotCity()
          local row = { x = qx, y = qy, distance = d, name = c:GetName(), owner = label(c:GetOwner()),
                        hp = c:GetMaxHitPoints() - c:GetDamage(), max_hp = c:GetMaxHitPoints() }
          pcall(function() row.strength = c:GetStrengthValue() / 100 end)
          if sight.range > 0 then row.in_sight = los[qx .. "," .. qy] and true or false end
          if fire then row.in_fire_los = fire_los[qx .. "," .. qy] and true or false end
          if H.enemy_city_at(q, pid) then row.hostile = true; hostile_at[qx .. "," .. qy] = true end
          cities[#cities + 1] = row
        end
        for i = 0, q:GetNumUnits() - 1 do
          local o = q:GetUnit(i)
          if o and not (o:GetOwner() == pid and o:GetID() == unit_id) then
            if not o:IsInvisible(team, false) and not o:IsDelayedDeath() then
              local owner = o:GetOwner()
              local row = { x = qx, y = qy, distance = d, owner = label(owner), id = o:GetID(),
                            unit = short(info_type(GameInfo.Units, o:GetUnitType())), hp = o:GetCurrHitPoints() }
              if sight.range > 0 then row.in_sight = los[qx .. "," .. qy] and true or false end
              if fire then row.in_fire_los = fire_los[qx .. "," .. qy] and true or false end
              if o:IsCombatUnit() then
                pcall(function() row.strength = o:GetBaseCombatStrength() end)
                pcall(function()
                  local rs = H.ranged_strength(o)
                  if rs > 0 then
                    row.ranged_strength = rs
                    local r = GameInfo.Units[o:GetUnitType()]
                    row.range = (o.Range and o:Range()) or (r and r.Range) or nil
                  end
                end)
              else
                row.civilian = true
              end
              if owner ~= pid then
                local op = Players[owner]
                if op and (op:IsBarbarian() or Teams[team]:IsAtWar(op:GetTeam())) then
                  row.hostile = true
                  hostile_at[qx .. "," .. qy] = true
                end
              end
              occupants[#occupants + 1] = row
            end
          end
        end
      end
    end
  end
  table.sort(occupants, function(a, b)
    if (a.hostile or false) ~= (b.hostile or false) then return a.hostile == true end
    if a.distance ~= b.distance then return a.distance < b.distance end
    if a.x ~= b.x then return a.x < b.x end
    if a.y ~= b.y then return a.y < b.y end
    return a.id < b.id
  end)
  table.sort(cities, function(a, b) return a.distance < b.distance end)

  -- The six neighbours: coordinates, remembered terrain, river crossing, occupants, and move_unit's answer.
  local move_mission = info_id("MISSION_MOVE_TO")
  local okc, step_cost = pcall(step_costs, u, pid)   -- nil: no cost is read (an air unit, or a getter failed)
  if not okc then step_cost = nil end
  local neighbors = {}
  for d = 0, 5 do
    local q = Map.PlotDirection(ux, uy, d)
    local n = { dir = DIRECTION_NAMES[d + 1] }
    if not q then
      n.off_map = true
      n.move = "refused"; n.why = "off the map edge"
    else
      n.x, n.y = q:GetX(), q:GetY()
      local e = H.describe_plot(q, team)
      if not e then
        n.vis = "unrevealed"
        n.move = "refused"; n.why = "plot is not revealed"
      else
        n.vis = e.vis and "visible" or "fogged"
        n.t = e.t
        for _, f in ipairs({ "hills", "mountain", "lake", "feature", "remembered", "improvement", "pillaged", "route" }) do
          n[f] = e[f]
        end
        if e.owner then n.owner = label(e.owner) end
        n.river_crossing = river_crossing(here, q, d)
        if e.city then n.city = e.city.name end
        if e.units then
          local seen = {}
          for _, o in ipairs(e.units) do
            label(o.owner)
            seen[#seen + 1] = { owner = o.owner, id = o.id, unit = o.type, hp = o.hp }
          end
          n.units = seen
        end
        local k = n.x .. "," .. n.y
        if attack_at[k] then
          n.move = "attack"
        elseif hostile_at[k] then
          -- Why it is not an attack, from the same facts H.melee_targets checks (live t42: a Warrior with its
          -- moves spent beside a Barbarian read "no melee attack").
          n.move = "enemy"
          if not u:IsCombatUnit() then
            n.why = "a visible enemy holds this plot; a civilian cannot attack"
          elseif unit.ranged_strength then
            n.why = "a visible enemy holds this plot; a ranged unit shoots it from here (see targets) and does not melee"
          elseif moves <= 0 then
            n.why = "a visible enemy holds this plot; this unit has no moves left to attack it this turn"
          elseif H.melee_domain_refusal(u, q) then
            n.why = "a visible enemy holds this plot; " .. H.melee_domain_refusal(u, q)
          else
            n.why = "a visible enemy holds this plot and this unit cannot attack it"
          end
        else
          local r = H.move_refusal(u, q, pid, true)
          if r then
            n.move = "refused"; n.why = r.err
          elseif moves > 0 and move_mission and u.CanStartMission then
            local ok, can = pcall(function() return u:CanStartMission(move_mission, n.x, n.y, false) end)
            if ok and can then n.move = "open" else n.move = "refused"; n.why = "move is not currently legal" end
          else
            n.move = "open"
          end
          if n.move == "open" and step_cost then
            local okn, c = pcall(step_cost, q, e.city ~= nil, n.river_crossing)
            if okn and c then
              n.cost, n.left = c.cost, c.left
              if c.zoc then label(c.zoc.owner); n.zoc = c.zoc end
            end
          end
        end
      end
    end
    neighbors[#neighbors + 1] = n
  end

  -- The picture: (2r+1) rows north to south, columns listed with their wrapped x.
  local w, h = Map.GetGridSize()
  local wrap = false
  pcall(function() wrap = Map.IsWrapX() and true or false end)
  local cols = {}
  for dx = -radius, radius do
    local gx = ux + dx
    if wrap then gx = gx % w elseif gx < 0 or gx >= w then gx = nil end
    cols[#cols + 1] = gx or -1
  end
  local rows = {}
  for gy = uy + radius, uy - radius, -1 do
    if gy >= 0 and gy < h then
      local cells = {}
      for i, gx in ipairs(cols) do
        -- The box's corners lie beyond `radius` in hex steps: blank, like off-map, so the picture covers
        -- exactly the plots occupants and fog count (live t42: a hostile could be drawn with no occupant row).
        local q = gx >= 0 and Map.PlotDistance(ux, uy, gx, gy) <= radius and Map.GetPlot(gx, gy) or nil
        cells[i] = tactical_cell(q, team, u, pid, hostile_at)
      end
      rows[#rows + 1] = string.format("%3d %s%s", gy, (gy % 2 == 1) and " " or "", table.concat(cells))
    end
  end

  local out = {
    ok = true, unit = unit, radius = radius, radius_from = radius_from, detail = full and "full" or "summary",
    map = { width = w, height = h, wrap_x = wrap },
    neighbors = neighbors, targets = targets, occupants = occupants, cities = cities, fog = fog,
    players = players,
    grid = { cols = cols, rows = rows },
  }
  if moves <= 0 then out.note = "this unit has no moves left this turn; `move` shows what order(to='unit', action='move') would do next turn from here" end
  if full then
    local plots = {}
    for _, q in ipairs(area) do
      local e = H.describe_plot(q, team)
      if e then plots[#plots + 1] = e end
    end
    out.plots = plots
  end
  return out
end
