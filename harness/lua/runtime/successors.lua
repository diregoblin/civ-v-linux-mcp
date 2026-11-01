-- Shared by earlier fragments (load order: harness/runtime_source.py MANIFEST).
local info_type, move_denom, short = H._ns.info_type, H._ns.move_denom, H._ns.short

-- A unit the engine replaced under a new id while an order of mine ran (GitLab #169, Maya t5): a Scout moved onto
-- Ancient Ruins and the ruins made it a Mayan Atlatlist with a new id on the ruins plot. The move's read-back found
-- the old id gone and answered "no such unit" for a move that had happened; the digest's unit_upgraded row placed
-- the Scout where the turn began and blamed automation; the assignment stayed on the vanished id. The engine fires
-- no event that names the new unit, so it is found the way an assignment finds an upgrade (assignment_facts): one of
-- my units created this turn, of a type the old one becomes, where the old one went.

-- Whether short type `new` is what `old` can become: its upgrade (Unit_ClassUpgrades, H.is_upgrade_of) or its ruins
-- upgrade (Units.GoodyHutUpgradeUnitClass: a Scout's ruins make the civ's Archer, the Maya's Atlatlist).
function H.is_successor_type(old, new)
  if H.is_upgrade_of(old, new) then return true end
  local ok, yes = pcall(function()
    local o, n = GameInfo.Units["UNIT_" .. old], GameInfo.Units["UNIT_" .. new]
    return o ~= nil and n ~= nil and o.GoodyHutUpgradeUnitClass ~= nil and o.GoodyHutUpgradeUnitClass == n.Class
  end)
  return ok and yes or false
end

-- H.successors (bootstrap.lua carries it over a re-injection): seat -> old id -> {id, type, x, y, turn, how}, so the
-- destroy hook and a retried order still name the successor.

local function successor_row(u)
  return { id = u:GetID(), type = short(info_type(GameInfo.Units, u:GetUnitType())), x = u:GetX(), y = u:GetY(),
           moves = u:MovesLeft() / move_denom(), hp = u:GetCurrHitPoints() }
end

-- My units created this turn that `old_type` becomes: on (x1, y1) first, else within `reach` plots of (x0, y0).
-- One answer is the successor; several (or none) are said as they are, never guessed between.
local function find(old_id, old_type, x0, y0, x1, y1, reach, pid)
  local turn = Game.GetGameTurn()
  local at, near = {}, {}
  for u in Players[pid]:Units() do
    local ok, fresh = pcall(function()
      return u:GetID() ~= old_id and not u:IsDelayedDeath() and u:GetGameTurnCreated() == turn
    end)
    if ok and fresh then
      local row = successor_row(u)
      if H.is_successor_type(old_type, row.type) then
        if x1 ~= nil and row.x == x1 and row.y == y1 then
          at[#at + 1] = row
        else
          local okd, d = pcall(function() return Map.PlotDistance(x0, y0, row.x, row.y) end)
          if x0 ~= nil and okd and d <= reach then near[#near + 1] = row end
        end
      end
    end
  end
  if #at == 1 then return at[1], nil end
  if #at == 0 and #near == 1 then return near[1], nil end
  local all = {}
  for _, r in ipairs(at) do all[#all + 1] = r end
  for _, r in ipairs(near) do all[#all + 1] = r end
  return nil, all
end

-- Keep what was found, and put it on the unit_destroyed row already logged for the old id (the destroy hook may
-- have run before the order's read-back, or run later and read H.attach_successor itself).
local function record(old_id, row, how, pid)
  H.successors[pid] = H.successors[pid] or {}
  local rec = { id = row.id, type = row.type, x = row.x, y = row.y, turn = Game.GetGameTurn(), how = how }
  H.successors[pid][old_id] = rec
  H.pending_moves[H.pm_key(old_id, pid)] = nil   -- the standing move died with the old unit
  for i = #H.events, 1, -1 do
    local e = H.events[i]
    if e.turn ~= rec.turn then break end
    if e.kind == "unit_destroyed" and e.data and e.data.player == pid and e.data.unit == old_id then
      H.attach_successor(e.data)
    end
  end
  return rec
end

-- The destroy hook's half: a loss whose successor is known names it and the plot the old unit last stood on.
function H.attach_successor(d)
  local rec = H.successors[d.player] and H.successors[d.player][d.unit]
  if not rec then return end
  d.new_unit, d.new_type, d.x, d.y, d.moved_by = rec.id, rec.type, rec.x, rec.y, rec.how
  d.plot_from = nil
end

-- The move's read-back found `old_id` gone: the unit that replaced it, recorded when there is exactly one. `old_type`,
-- (x0, y0) and `reach` are the old unit's type, start plot and moves as move_unit read them before the order.
function H.move_successor(old_id, old_type, x0, y0, x1, y1, reach, pid)
  if type(old_type) ~= "string" then
    local r = H.roster[pid] and H.roster[pid][old_id]
    old_type = r and r.unit
  end
  if not old_type then return { ok = true, candidates = {} } end
  local row, others = find(old_id, old_type, x0, y0, x1, y1, tonumber(reach) or 3, pid)
  if row then return { ok = true, successor = record(old_id, row, "order", pid) } end
  return { ok = true, candidates = others }
end

-- An order to an id that is gone (a retry, or a briefing older than the turn): the successor recorded for it, else
-- one found this turn from the roster's last plot and the standing move it was walking (Celts t22: a Scout on a
-- standing move took ruins at the turn start and the next move to it answered a bare "no such unit").
function H.successor_of(old_id, pid)
  local rec = H.successors[pid] and H.successors[pid][old_id]
  if rec then return { ok = true, successor = rec } end
  local r = H.roster[pid] and H.roster[pid][old_id]
  if not r or not r.unit then return { ok = true } end
  local pm = H.pending_moves[H.pm_key(old_id, pid)]
  local row = find(old_id, r.unit, r.x, r.y, pm and pm.x, pm and pm.y, 3, pid)
  if row then return { ok = true, successor = record(old_id, row, pm and "standing_move" or "unknown", pid) } end
  return { ok = true }
end
