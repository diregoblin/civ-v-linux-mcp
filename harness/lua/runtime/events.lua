-- Shared by earlier fragments (load order: harness/runtime_source.py MANIFEST).
local info_type, short = H._ns.info_type, H._ns.short

---------------------------------------------------------------- event recorder
-- Who fought, as the combat animation shows it to the active player: captured inside the EndCombatSim
-- hook, while the unit still exists (a killed unit is in delayed death, not gone yet). Our own side is
-- always described; the other side only while its plot is visible to us and the unit is not invisible
-- (submarines), and its owner is named only once met -- otherwise "Unknown", like the unit flag.
-- Who owns something, as the viewer is allowed to know it: "you", "Barbarians", the civ's short name
-- once met, "Unknown" otherwise. Never leaks the identity of a civ we have not met.
function H.owner_label(pid, viewer)
  viewer = viewer or Game.GetActivePlayer()
  local p = Players[pid]
  if viewer < 0 or not p then return nil end
  if pid == viewer then return "you" end
  if p:IsBarbarian() then return "Barbarians" end
  if Teams[Players[viewer]:GetTeam()]:IsHasMet(p:GetTeam()) then return p:GetCivilizationShortDescription() end
  return "Unknown"
end

function H.combat_side(pid, uid, viewer)
  viewer = viewer or Game.GetActivePlayer()
  local p = Players[pid]
  if viewer < 0 or not p then return nil end
  local team = Players[viewer]:GetTeam()
  local out = { owner = H.owner_label(pid, viewer) }
  local u = p:GetUnitByID(uid)
  if not u then
    -- GitLab #126/#118: my own unit killed while defending is gone by the time the hook fires and read
    -- "your unit (not visible)" with no plot; the roster of my turn end knows it.
    local was = H.roster and H.roster[pid] and H.roster[pid][uid]
    if was and pid == viewer then out.unit, out.x, out.y, out.killed, out.hp = was.unit, was.x, was.y, true, 0 end
    return out
  end
  local plot = u:GetPlot()
  if pid ~= viewer and not (plot and plot:IsVisible(team, false) and not u:IsInvisible(team, false)) then return out end
  out.unit = short(info_type(GameInfo.Units, u:GetUnitType()))
  out.x, out.y = u:GetX(), u:GetY()
  out.hp, out.max_hp = u:GetCurrHitPoints(), u:GetMaxHitPoints()
  out.killed = u:IsDelayedDeath() or u:GetCurrHitPoints() <= 0 or nil
  out.ranged = H.ranged_strength(u) > 0 or nil
  return out
end

-- With quick combat on (always, in multiplayer) RunCombatSim/EndCombatSim never fire: a fight is two
-- SerialEventUnitSetDamage(player, unit, newDamage, oldDamage) -- defender, then attacker -- followed
-- by the GameplayAlertMessage banner ("Your Warrior (29 damage) attacked an enemy Brute (36 damage)!").
-- Live-audited 2026-09-18 with a human at the screen, three fights, identical each time. One `damage`
-- row per unit the viewer can see; healing (newDamage < oldDamage) is not combat and is skipped.
-- Hotseat: the AI phase runs while the PREVIOUS human is still the active player, so a hit on another
-- human seat's unit is filed for that seat, not for whoever happens to be active.
function H.unit_damaged(pid, uid, newDmg, oldDmg)
  local dmg = (newDmg or 0) - (oldDmg or 0)
  local viewer = Game.GetActivePlayer()
  local p = Players[pid]
  if dmg <= 0 or viewer < 0 or not p then return end
  -- AI-phase events arrive in a batch after every fight has resolved, so the unit's live hp is the
  -- FINAL value for each of them (live: two hits on a Scout both read "46 left"): take it from the event.
  local function at_event(side)
    if side and side.max_hp then
      side.hp = math.max(0, side.max_hp - newDmg)
      side.hp_before = math.max(0, side.max_hp - (oldDmg or 0))   -- GitLab #132: a heal before the hit is otherwise invisible
      if side.hp <= 0 then side.killed = true end
    end
    return side
  end
  if pid ~= viewer and p:IsHuman() and PreGame.IsHotSeatGame() then
    H.record("damage", { player = pid, unit_id = uid, dmg = dmg, side = at_event(H.combat_side(pid, uid, pid)) }, pid)
  end
  local side = H.combat_side(pid, uid)
  if not side or (pid ~= viewer and not side.unit) then return end  -- side.unit is only set when we can see it
  H.record("damage", { player = pid, unit_id = uid, dmg = dmg, side = at_event(side) })
end

-- Hit points of our own units, snapshotted when our turn ends and compared when the next one starts:
-- EndCombatSim is a graphics event and does not fire for combat the engine resolves without an
-- animation (quick combat, off-screen AI phase), so an unexplained loss is reported on its own.
-- Last-known roster of a seat's own units. SerialEventUnitDestroyed is a graphics event that arrives after
-- the unit is gone (live 2026-09-24: Unit:Kill() fired nothing synchronously and GetUnitByID was already nil
-- inside the hook), so a loss can only be named from what we knew: the roster at our turn start and end, plus
-- any unit we just ordered into a fight. That is also what a human knows -- where the Worker was left.
function H.note_units(pid)
  H.roster = H.roster or {}
  local r = {}
  for u in Players[pid]:Units() do
    local okA, auto = pcall(function() return u:IsAutomated() end)
    r[u:GetID()] = { unit = short(info_type(GameInfo.Units, u:GetUnitType())), x = u:GetX(), y = u:GetY(),
                     automated = (okA and auto) and true or nil }
  end
  H.roster[pid] = r
end

-- GitLab #77 (Assyria t239-t244): a Worker automated at t239 was back in todo.units at t244 at the same plot and
-- nothing said automation had ended or why. Before the roster is renewed at the turn start, every unit noted as
-- automated that is not any more (and still mine) is a digest row; the engine gives no reason, so the two it has
-- are named.
function H.automation_compare(pid)
  local r = H.roster and H.roster[pid]
  if not r then return end
  for u in Players[pid]:Units() do
    local was = r[u:GetID()]
    if was and was.automated then
      local okA, auto = pcall(function() return u:IsAutomated() end)
      if okA and not auto and not u:IsDelayedDeath() then
        H.record("automation_ended", { unit = u:GetID(), unit_type = short(info_type(GameInfo.Units, u:GetUnitType())),
                                       x = u:GetX(), y = u:GetY(),
                                       reason = "the engine stopped automating it: nothing left to build in reach, or a threat beside it; "
                                             .. "re-automating now does the same unless the map changed -- give it an order" }, pid)
      end
    end
  end
end
function H.note_unit_by_id(unit_id, pid)
  local u = Players[pid]:GetUnitByID(unit_id)
  if u then H.note_unit(u, pid) end
  return true
end
function H.note_unit(u, pid)
  H.roster = H.roster or {}
  H.roster[pid] = H.roster[pid] or {}
  H.roster[pid][u:GetID()] = { unit = short(info_type(GameInfo.Units, u:GetUnitType())), x = u:GetX(), y = u:GetY() }
end

function H.hp_snapshot(pid)
  local snap = {}
  for u in Players[pid]:Units() do
    local row = { hp = u:GetCurrHitPoints(), unit = short(info_type(GameInfo.Units, u:GetUnitType())), x = u:GetX(), y = u:GetY() }
    -- v265: a unit the engine will move on its own at the next turn start (a standing multi-turn move of ours
    -- carries on before the hook fires; an automated unit walks) is not "displaced" when it has.
    local ok, moving = pcall(function() return u:GetLengthMissionQueue() > 0 or u:IsAutomated() end)
    if ok and moving then row.moving = true end
    snap[u:GetID()] = row
  end
  H.roster = H.roster or {}
  H.roster[pid] = snap
  -- One slot per seat: in hotseat the other human's turn start used to find "someone else's" snapshot in
  -- the single slot and throw it away, so neither seat ever got a unit_lost / unit_hurt row.
  H.hp_snaps = H.hp_snaps or {}
  H.hp_snaps[pid] = { player = pid, units = snap }
end
function H.hp_compare(pid)
  local s = H.hp_snaps and H.hp_snaps[pid]
  if not s then return end
  H.hp_snaps[pid] = nil
  local p = Players[pid]
  for id, was in pairs(s.units) do
    local u = p:GetUnitByID(id)
    if not u or u:IsDelayedDeath() then
      H.record("unit_lost", { player = pid, unit_id = id, unit = was.unit, x = was.x, y = was.y, hp_before = was.hp })
    elseif u:GetCurrHitPoints() < was.hp then
      H.record("unit_hurt", { player = pid, unit_id = id, unit = was.unit, x = u:GetX(), y = u:GetY(),
                              hp_before = was.hp, hp = u:GetCurrHitPoints() })
    end
  end
end

-- A unit of ours standing somewhere else at our turn start than where our turn end (or our last order) left
-- it, with no order of ours behind the move: the engine moved it. Live 2026-10-08 (England t120-t125, twice):
-- a Great General sleeping in London was standing one plot outside the city at the next turn start whenever a
-- Caravan shared the city tile at the turn end (bought, then built); the unit panel showed nothing, a human
-- sees the unit jump. Units the engine moves on purpose are left out: automated ones (explore / build / a
-- trade route) and ones carrying on a multi-turn move of ours (a mission still queued). Runs before note_units
-- rewrites the roster.
function H.displaced_compare(pid)
  local r = H.roster and H.roster[pid]
  if not r then return end
  local p = Players[pid]
  for id, was in pairs(r) do
    local u = p:GetUnitByID(id)
    if u and not was.moving and not u:IsDelayedDeath() and (u:GetX() ~= was.x or u:GetY() ~= was.y) then
      local automated = pcall(function() return u:IsAutomated() end) and u:IsAutomated()
      local queued = (pcall(function() return u:GetLengthMissionQueue() end) and u:GetLengthMissionQueue() or 0) > 0
      local trade = pcall(function() return u:IsTrade() end) and u:IsTrade()
      if not automated and not queued and not trade then
        local d = { player = pid, unit_id = id, unit = was.unit, from_x = was.x, from_y = was.y, x = u:GetX(), y = u:GetY(),
                    summary = "your " .. tostring(was.unit) .. " was moved by the engine from (" .. was.x .. "," .. was.y ..
                              ") to (" .. u:GetX() .. "," .. u:GetY() .. ") -- no order of yours did it" }
        -- The tile it left: a trade unit of ours still standing there names the stacking rule seen live.
        local plot = Map.GetPlot(was.x, was.y)
        if plot then
          for i = 0, plot:GetNumUnits() - 1 do
            local o = plot:GetUnit(i)
            if o and o:GetOwner() == pid and o:GetID() ~= id and pcall(function() return o:IsTrade() end) and o:IsTrade() then
              d.shared_with = { unit_id = o:GetID(), unit = short(info_type(GameInfo.Units, o:GetUnitType())) }
              d.summary = d.summary .. "; a " .. tostring(d.shared_with.unit) .. " of yours shares the tile it left " ..
                          "(the engine moves a civilian off a tile a trade unit stands on at the turn start)"
              break
            end
          end
        end
        H.record("unit_displaced", d)
      end
    end
  end
end

-- A met major civ that died since the last turn start (the game announces it to everyone who knew it). Live
-- t444: India conquered America, our declaration-of-friendship partner, and the digest only showed four
-- "deal ended" notices. The first call just takes the snapshot.
function H.check_eliminations(viewer)
  local now = {}
  for i = 0, GameDefines.MAX_MAJOR_CIVS - 1 do
    local p = Players[i]
    if p and p:IsAlive() and not p:IsMinorCiv() then now[i] = true end
  end
  local before = H.alive_majors
  H.alive_majors = now
  if viewer < 0 then return end
  local team = Teams[Players[viewer]:GetTeam()]
  -- GitLab #107 (Maya t18-t88): Zurich became Venice's and nothing said a city-state was conquered; the move
  -- refusal "inside Venice's borders" was the first sign. The capital of every city-state is remembered, and a
  -- city-state I had met that is gone at my next turn start is a row naming who holds its city now.
  pcall(function()
    H.minor_caps = H.minor_caps or {}
    for i = GameDefines.MAX_MAJOR_CIVS, (GameDefines.MAX_CIV_PLAYERS or 64) - 1 do
      local m = Players[i]
      if m and m:IsMinorCiv() then
        local was = H.minor_caps[i]
        if m:IsAlive() then
          local cap = m:GetCapitalCity()
          if cap then H.minor_caps[i] = { x = cap:GetX(), y = cap:GetY(), name = cap:GetName(), met = team:IsHasMet(m:GetTeam()) } end
        elseif was then
          H.minor_caps[i] = nil
          if was.met then
            local plot = Map.GetPlot(was.x, was.y)
            local city = plot and plot:GetPlotCity()
            local owner = city and city:GetOwner() or -1
            local by = (owner >= 0 and team:IsHasMet(Players[owner]:GetTeam())) and Players[owner]:GetCivilizationShortDescription() or nil
            H.record("city_state_fell", { player = i, name = was.name, x = was.x, y = was.y, by = by,
                                          by_player = by and owner or nil, destroyed = (city == nil) or nil })
          end
        end
      end
    end
  end)
  if not before then return end
  for i in pairs(before) do
    local p = Players[i]
    if not now[i] and i ~= viewer and team:IsHasMet(p:GetTeam()) then
      H.record("civ_eliminated", { player = i, civ = Locale.Lookup(p:GetCivilizationShortDescriptionKey()),
                                   leader = p:GetName() })
    end
  end
end

-- `audience` overrides who the row is for (default: the active player); only H.unit_damaged passes it.
function H.record(kind, data, audience)
  local viewer = Game.GetActivePlayer()
  if viewer < 0 then return end
  -- Engine events include information which the active player cannot see.
  -- Capture the audience now; never infer visibility later after the fog changes.
  if kind == "unit_destroyed" or kind == "city_created" or kind == "city_destroyed" then
    if data.player ~= viewer and audience ~= data.player then return end
  elseif kind == "city_captured" then
    if data.player ~= viewer and data.by ~= viewer then return end
  elseif kind == "combat" then
    if data.att_player ~= viewer and data.def_player ~= viewer then return end
  elseif kind == "notification" then
    if data.player ~= viewer then return end
    -- Hotseat re-adds every live notification when the panel is rebuilt at the hand-off: same id, same
    -- text, fired twice (live 2026-09-18). One bubble on screen is one row here.
    H.seen_notes = H.seen_notes or {}
    local key = data.player .. ":" .. tostring(data.id)
    if H.seen_notes[key] == data.text then return end
    H.seen_notes[key] = data.text
    pcall(H.locate_notification, data)  -- never lose the row over its location
  elseif kind == "war_state" then
    local team = Players[viewer]:GetTeam()
    if data.team1 ~= team and data.team2 ~= team then return end
    -- The engine fires it once per direction ([0,3,true] then [3,0,true], live 2026-09-18): one row.
    local a, b = math.min(data.team1, data.team2), math.max(data.team1, data.team2)
    local key = a .. ":" .. b .. ":" .. tostring(data.at_war) .. ":" .. Game.GetGameTurn()
    if H.last_war_key == key then return end
    H.last_war_key = key
  elseif kind == "chat" then
    -- Target enum semantics vary by mode; only record our own outgoing chat.
    if data.from ~= viewer then return end
  end
  H.event_seq = H.event_seq + 1
  H.events[#H.events + 1] = { seq = H.event_seq, turn = Game.GetGameTurn(), audience = audience or viewer, kind = kind, data = data }
  if #H.events > 3000 then table.remove(H.events, 1) end
end

-- GitLab #114 (live Maya t173-t178): Korea completed the Porcelain Tower and Palenque's queued copy left its
-- queue without a line; the city came up idle five turns later. The engine drops an item it can no longer
-- build (CvCity::doCheckProduction) silently. Each seat's queues are snapshotted at its turn end and compared
-- at its next turn start: an item gone from the queue that the city cannot build any more -- and did not just
-- complete there -- is a `production_dropped` event for the digest (it wakes a quiet run).
H.queue_snap = H.queue_snap or {}
function H.queue_snapshot(pid)
  local p = Players[pid]
  if not (p and H.queue_items) then return end
  local snap = {}
  for c in p:Cities() do snap[c:GetID()] = { name = c:GetName(), items = H.queue_items(c) } end
  H.queue_snap[pid] = snap
end

-- GitLab #141 (Maya t232): a Caravan that completed with every route slot used reads CanTrain false the
-- same turn, and so does any one-per-city unit; the unit it made is the proof it was built, not dropped.
-- Production completes at the owner's turn start, so the unit was created this turn and stands on or
-- beside its city (the engine places it next door when the city plot is full).
local function unit_completed_here(city, unit_type_id)
  local found = false
  pcall(function()
    local turn = Game.GetGameTurn()
    for u in Players[city:GetOwner()]:Units() do
      if u:GetUnitType() == unit_type_id and u:GetGameTurnCreated() == turn
         and Map.PlotDistance(u:GetX(), u:GetY(), city:GetX(), city:GetY()) <= 1 then
        found = true
        return
      end
    end
  end)
  return found
end

local function still_buildable(city, item)
  local info = GameInfo.Buildings[item]
  if info then
    if city:IsHasBuilding(info.ID) then return true end          -- it completed here: not dropped
    return city:CanConstruct(info.ID, 0) and true or false
  end
  info = GameInfo.Units[item]
  if info then
    if unit_completed_here(city, info.ID) then return true end   -- it completed here: not dropped (#141)
    return city:CanTrain(info.ID, 0) and true or false
  end
  info = GameInfo.Projects[item]
  if info then
    local t = Teams[city:GetTeam()]
    if t and t.GetProjectCount and t:GetProjectCount(info.ID) > 0 then return true end
    return city:CanCreate(info.ID, 0) and true or false
  end
  return true   -- a process, or something unknown: never reported
end

function H.queue_compare(pid)
  local snap = H.queue_snap[pid]
  local p = Players[pid]
  if not (snap and p and H.queue_items) then return end
  for c in p:Cities() do
    local was = snap[c:GetID()]
    if was then
      local now = {}
      for _, it in ipairs(H.queue_items(c)) do now[it] = true end
      for _, it in ipairs(was.items) do
        if not now[it] then
          local ok, buildable = pcall(still_buildable, c, it)
          if ok and not buildable then
            H.record("production_dropped", { city = c:GetID(), name = c:GetName(), item = it,
                                             reason = "the city can no longer build it (a wonder completed elsewhere, or a prerequisite lost); the queue moved on without it" }, pid)
          end
        end
      end
    end
  end
  H.queue_snap[pid] = nil
end
function H.events_since(seq, pid)
  local out = {}
  for _, e in ipairs(H.events) do
    if e.seq > seq and e.audience == pid then
      if e.data.site_pending then  -- the plot was not revealed yet inside the hook: one retry, at read time
        pcall(H.locate_notification, e.data)
        e.data.site_pending = nil
      end
      out[#out + 1] = e
    end
  end
  return out
end
-- Banners recorded after `seq` for `pid` (GameplayAlertMessage rows), without moving the digest cursor.
-- The air-strike result reads the interception the engine announced here: "Your Bomber was intercepted
-- by an enemy Anti-Aircraft Gun! (40% Damage)" / "Your Bomber was shot down by an enemy Fighter!".
function H.alerts_since(seq, pid)
  local out = {}
  for _, e in ipairs(H.events) do
    if e.seq > seq and e.audience == pid and e.kind == "alert" and e.data and e.data.text then out[#out + 1] = e.data.text end
  end
  return out
end

-- Where a notification points. A human clicks the bubble and the camera jumps there; the event itself
-- carries no plot (live 2026-09-18: "Ruins discovered" / "Barbarian Encampment discovered" arrive with
-- data -1,-1), so the place is read back from what the team can see.
-- Ruins/camps: visible plots showing that improvement which no earlier row reported. The first call for
-- a team seeds the memory with the sites it knows but cannot see right now.
function H.new_sites(team, improvement)
  local imp = GameInfoTypes[improvement]
  if not imp then return {} end
  local known = H.known_sites[team]
  local seed = known == nil
  if seed then known = {}; H.known_sites[team] = known end
  local out = {}
  for i = 0, Map.GetNumPlots() - 1 do
    local plot = Map.GetPlotByIndex(i)
    if plot:IsRevealed(team, false) and plot:GetRevealedImprovementType(team, false) == imp and not known[i] then
      if plot:IsVisible(team, false) then
        known[i] = true
        out[#out + 1] = { x = plot:GetX(), y = plot:GetY() }
      elseif seed then
        known[i] = true
      end
    end
  end
  return out
end
local SITE_NOTIFICATIONS = { NOTIFICATION_GOODY = "IMPROVEMENT_GOODY_HUT", NOTIFICATION_BARBARIAN = "IMPROVEMENT_BARBARIAN_CAMP" }
-- The Great Person a NOTIFICATION_GREAT_PERSON_ACTIVE_PLAYER row is about: `unit` is the type d1 names; `unit_id`,
-- `x`, `y` the unit of mine of that type created on `turn` (the newest when several); without one, `of_type_now`
-- counts my units of that type as they are now (0 when the person was spent in the same turn).
function H.great_person_facts(p, d1, turn)
  local name = type(d1) == "number" and d1 >= 0 and info_type(GameInfo.Units, d1) or nil
  if not name or not p or not p.Units then return nil end
  local out, best, count = { unit = short(name) }, nil, 0
  for u in p:Units() do
    if u:GetUnitType() == d1 and not u:IsDelayedDeath() then
      count = count + 1
      local ok, c = pcall(function() return u:GetGameTurnCreated() end)
      if ok and c == turn and (not best or u:GetID() > best:GetID()) then best = u end
    end
  end
  if best then out.unit_id, out.x, out.y = best:GetID(), best:GetX(), best:GetY() else out.of_type_now = count end
  return out
end

function H.locate_notification(data)
  local p = Players[data.player]
  if not p then return end
  for name, improvement in pairs(SITE_NOTIFICATIONS) do
    if data.ntype and NotificationTypes[name] == data.ntype then
      local sites = H.new_sites(p:GetTeam(), improvement)
      if #sites > 0 then data.sites = sites; data.site_pending = nil else data.site_pending = true end
      return
    end
  end
  -- City growth carries the city id in d1 (live: "Venice has Grown!" d1 = 8192).
  if data.ntype == NotificationTypes.NOTIFICATION_CITY_GROWTH then
    local city = p:GetCityByID(data.d1 or -1)
    if city then data.x, data.y = city:GetX(), city:GetY() end
  -- A promotion carries the unit id in d2 (live: d1 = 83 unit type, d2 = 16385).
  elseif data.ntype == NotificationTypes.NOTIFICATION_UNIT_PROMOTION then
    local unit = p:GetUnitByID(data.d2 or -1)
    if unit then data.unit_id = data.d2; data.x, data.y = unit:GetX(), unit:GetY() end
  -- "A Great Person has been born in your civilization!" names neither the person nor the city: d1 is the unit
  -- type, d2 is -1 (live Assyria t238: 148 UNIT_MUSICIAN and 4 UNIT_SCIENTIST, both spent the same turn, so the
  -- notification_log read found no unit behind either). Attach the type and the unit of mine born this turn.
  elseif data.ntype ~= nil and data.ntype == NotificationTypes.NOTIFICATION_GREAT_PERSON_ACTIVE_PLAYER then
    local g = H.great_person_facts(p, data.d1, Game.GetGameTurn())
    if g then for k, v in pairs(g) do data[k] = v end end
  end
  -- "Machu has been converted to another religion!" never names the new majority (live t179: a
  -- 2-2 tie, cities().religion was nil). Attach the city-banner tooltip the click would show.
  H.attach_conversion_banner(data, p)
  -- "Steal Technology" names the victim civ but not which tech (live t181: Inca, only Sailing).
  -- The click opens BUTTONPOPUP_CHOOSE_TECH_TO_STEAL; attach the same list steal_tech_options returns.
  H.attach_steal_tech(data, p)
  -- "Losing Gold!" names the empty treasury but not current GPT / strike / that unpaid
  -- expenses come out of science (live t182: gold 0, gpt −23, IsStrike still false).
  H.attach_gold_deficit(data, p)
  -- "A Worker was captured by the Barbarians!" names neither the unit nor the tile; the click pans there.
  H.attach_capture(data, p)
  -- "The International Games project has been completed." says nothing of our tier or reward (GitLab #148).
  H.attach_league_project(data, p)
end

-- A completed World Congress project (TXT_KEY_NOTIFICATION_LEAGUE_PROJECT_COMPLETE_TT): our contribution, the
-- tier it earned and that tier's reward text, from the same read state(what='league').projects gives -- without
-- it the tier was nowhere but the 25 KB league read.
function H.attach_league_project(data, p)
  if not (data and p) then return end
  local text = (type(data.text) == "string" and data.text or "") .. " " .. (type(data.summary) == "string" and data.summary or "")
  if not text:find("project has been completed", 1, true) then return end
  local ok, projects = pcall(H.league_projects, data.player or Game.GetActivePlayer())
  if not (ok and type(projects) == "table") then return end
  for _, row in ipairs(projects) do
    if row.name and text:find(row.name, 1, true) then
      local reward
      for _, r in ipairs(row.rewards or {}) do if r.tier == row.our_tier then reward = r.text end end
      data.league_project = { project = row.project, name = row.name, our_contribution = row.our_contribution,
                              our_tier = row.our_tier, reward = reward,
                              note = row.our_tier == 0 and "we contributed below tier 1: no reward" or nil }
      return
    end
  end
end

-- Capture notice (TXT_KEY_UNIT_CAPTURED_DETAILED / _BARBS_DETAILED): "A Worker was captured by Alpha!" /
-- "A Worker was captured by the Barbarians! They will take it to their nearest Encampment." The bubble
-- names the unit type and the captor, nothing else; clicking it pans to the plot. The engine killed the
-- captured unit just before adding the notice (SerialEventUnitDestroyed kept its type and plot), so tie
-- the two: the unit id and tile, the captor now standing there when the tile is in sight, and for the
-- barbarians the nearest camp the team has revealed -- where the human would look. Nothing under fog.
function H.attach_capture(data, p)
  if not (data and p and type(data.text) == "string") then return end
  local text = data.text
  if not text:find(" was captured by ", 1, true) then return end
  local pid = data.player
  local turn = Game.GetGameTurn()
  local row
  for i = #H.events, 1, -1 do
    local e = H.events[i]
    if (e.turn or turn) < turn - 1 then break end
    local d = e.data
    if e.kind == "unit_destroyed" and d and d.player == pid and d.unit_type and not d.captured then
      local ok, name = pcall(function()
        local info = GameInfo.Units["UNIT_" .. d.unit_type]
        return info and info.Description and Locale.Lookup(info.Description) or nil
      end)
      local gone = true
      pcall(function() gone = p:GetUnitByID(d.unit) == nil end)
      if ok and name and text:find(name, 1, true) and gone then row = d; break end
    end
  end
  if not row then return end
  H.capture_details(data, row, p)
end

-- The destroy event is delayed graphics, so it can also arrive AFTER the notice (live S1 t267: a Worker
-- taken on our own turn came as notification seq 28, unit_destroyed seq 29, and the notice stayed bare).
-- From the destroy side, find the unlinked notice this turn that names the unit's type and tie them.
function H.link_late_capture(d)
  if not (d and d.unit_type and d.player) then return end
  local p = Players[d.player]
  if not p then return end
  local turn = Game.GetGameTurn()
  local okn, name = pcall(function()
    local info = GameInfo.Units["UNIT_" .. d.unit_type]
    return info and info.Description and Locale.Lookup(info.Description) or nil
  end)
  if not (okn and name) then return end
  for i = #H.events, 1, -1 do
    local e = H.events[i]
    if (e.turn or turn) < turn then break end
    local n = e.data
    if e.kind == "notification" and n and n.player == d.player and not n.unit_id
       and type(n.text) == "string" and n.text:find(" was captured by ", 1, true) and n.text:find(name, 1, true) then
      H.capture_details(n, d, p)
      return
    end
  end
end

-- Shared tail of both directions: mark the destroy row, point the notice at the unit and tile, name the
-- captor standing there when the tile is in sight, and the nearest revealed camp for the barbarians.
function H.capture_details(data, row, p)
  local text = data.text or ""
  local pid = data.player
  row.captured = true
  data.unit_id, data.unit, data.x, data.y = row.unit, row.unit_type, row.x, row.y
  local barbs = text:find("Barbarians", 1, true) ~= nil
  pcall(function()
    local team = p:GetTeam()
    local plot = Map.GetPlot(row.x, row.y)
    if plot and plot:IsVisible(team, false) then
      for i = 0, plot:GetNumUnits() - 1 do
        local u = plot:GetUnit(i)
        if u and u:GetOwner() ~= pid and u:IsCombatUnit() and not u:IsInvisible(team, false) then
          data.captor = { owner = H.owner_label(u:GetOwner(), pid), unit = short(info_type(GameInfo.Units, u:GetUnitType())),
                          x = u:GetX(), y = u:GetY(), hp = u:GetCurrHitPoints() }
          break
        end
      end
    end
    if barbs then
      local imp = GameInfoTypes and GameInfoTypes.IMPROVEMENT_BARBARIAN_CAMP
      local best
      if imp then
        for i = 0, Map.GetNumPlots() - 1 do
          local pl = Map.GetPlotByIndex(i)
          if pl:IsRevealed(team, false) and pl:GetRevealedImprovementType(team, false) == imp then
            local dist = Map.PlotDistance(row.x, row.y, pl:GetX(), pl:GetY())
            if not best or dist < best.distance then best = { x = pl:GetX(), y = pl:GetY(), distance = dist } end
          end
        end
      end
      if best then data.nearest_revealed_camp = best end
    end
  end)
  data.hint = "a combat unit moved onto the captor's tile takes the unit back (order(to='unit', action='move'))"
    .. (barbs and "; the barbarians walk it toward their nearest camp (state(what='map', view='index') lists camps)" or "")
end

-- Pending spy-steal chooser. The engine's EndTurnBlockingType is one-at-a-time, so this can sit
-- behind POLICY/PRODUCTION/etc. (live t181: blocking_name was POLICY, pending_popups empty,
-- GetNumTechsToSteal(Inca) == 1). A human still sees the notification and can open the chooser.
function H.attach_steal_tech(data, p)
  if not (data and p) then return end
  local text = type(data.text) == "string" and data.text or ""
  local summary = type(data.summary) == "string" and data.summary or ""
  if not (summary:find("Steal Technology", 1, true) or text:find("steal a technology", 1, true)) then
    return
  end
  local ok, steal = pcall(H.steal_tech_options, data.player or Game.GetActivePlayer())
  if ok and type(steal) == "table" and (steal.n or 0) > 0 then
    data.steal_tech = steal.victims
    data.hint = "question() then answer(choice=<tech>)"
  end
end

-- Empty-treasury notice: GPT, whether units are already on strike, and the science hit.
function H.attach_gold_deficit(data, p)
  if not (data and p) then return end
  local text = type(data.text) == "string" and data.text or ""
  local summary = type(data.summary) == "string" and data.summary or ""
  if not (summary:find("Losing Gold", 1, true) or text:find("treasury is empty", 1, true)) then
    return
  end
  pcall(function() data.gold = p:GetGold() end)
  pcall(function() data.gold_per_turn = p:CalculateGoldRate() end)
  local ok_s, strike = pcall(function() return p:IsStrike() end)
  if ok_s then data.is_strike = strike and true or false end
  local ok_t, turns = pcall(function() return p:GetStrikeTurns() end)
  if ok_t and turns and turns > 0 then data.strike_turns = turns end
  data.hint = "unpaid expenses come out of science (science_breakdown.budget_deficit); state(what='city', view='screen') buildings with can_sell / order(to='city', action='sell_building') raise gold. Units disband if GPT stays at the threshold named in this notice."
  -- Military Overview / toppanel unit-supply string: over the cap is extra gold + a production penalty.
  local ok_u, supply = pcall(H.unit_supply, data.player)
  if ok_u and type(supply) == "table" and supply.deficit then
    data.unit_supply = supply
    data.hint = data.hint .. " Over the unit supply cap (overview.unit_supply): extra maintenance and a production penalty; disband or wait for more cities/pop."
  end
end

-- Banner tooltip for a "city converted / adopted a religion" notice: majority name when there is
-- one, else note the tie, plus followers/pressure for every religion the banner lists.
function H.attach_conversion_banner(data, p)
  if not (data and type(data.text) == "string" and p) then return end
  local text = data.text
  if not (text:find("converted to another religion", 1, true) or text:find("has adopted a religion", 1, true)) then
    return
  end
  for c in p:Cities() do
    local name = c:GetName()
    if name and name ~= "" and text:find(name, 1, true) then
      data.city_id = c:GetID()
      data.x, data.y = c:GetX(), c:GetY()
      local maj = c.GetReligiousMajority and c:GetReligiousMajority() or -1
      if maj and maj > 0 then
        if Game.GetReligionName then data.religion = H.L(Game.GetReligionName(maj)) end
        if GameInfo.Religions and GameInfo.Religions[maj] then data.majority = GameInfo.Religions[maj].Type end
      elseif maj == 0 then
        data.religion = "PANTHEON"
        data.majority = "RELIGION_PANTHEON"
      else
        data.religion = nil
        data.majority = nil
        data.note = "no religion holds a majority in this city now"
      end
      if c.GetNumFollowers and GameInfo.Religions then data.religions = H.city_religions(c) end
      return
    end
  end
end
function H.take_events(pid)
  local out = H.events_since(H.cursors[pid] or 0, pid)
  H.cursors[pid] = H.event_seq
  return out
end
function H.install_hooks()
  local function hook(name, fn)
    local ev = Events[name]
    if not ev then return end
    local prev = H.hook_fns[name]
    if prev then local ok = pcall(function() ev.Remove(prev) end) end
    local wrapped = function(...) local ok, err = pcall(fn, ...); if not ok then H.record("hook_error", {name=name, err=tostring(err)}) end end
    ev.Add(wrapped)
    H.hook_fns[name] = wrapped
  end
  hook("ActivePlayerTurnStart", function()
    local pid = Game.GetActivePlayer()
    H.turn_seat = pid
    H.record("turn_start", { player = pid }); H.hp_compare(pid)
    pcall(H.queue_compare, pid)
    pcall(H.displaced_compare, pid)
    pcall(H.automation_compare, pid)
    pcall(H.note_units, pid)
    pcall(H.check_eliminations, pid)
  end)
  -- Hotseat: when ActivePlayerTurnEnd fires, GetActivePlayer() already names the NEXT seat (live 2026-09-24:
  -- Alpha's turn end was filed for Bravo, and Bravo's units were the ones snapshotted). The seat that ended
  -- is the one whose turn started last.
  hook("ActivePlayerTurnEnd", function()
    local pid = H.turn_seat or Game.GetActivePlayer()
    H.record("turn_end", { player = pid }, pid); H.hp_snapshot(pid)
    pcall(H.queue_snapshot, pid)
  end)
  hook("GameplaySetActivePlayer", function(new, old) H.record("active_player", { new = new, old = old }) end)
  -- Roster positions: refreshed at turn start and turn end (hp_snapshot) and after each harness-ordered
  -- move (H.move_unit), so a loss during the other players' turns is placed where the unit was left.
  -- LocalMachineUnitPositionChanged was tried for engine-driven moves during our own turn and rejected:
  -- it fires BEFORE the unit's plot changes (live S1 t267: reading the unit inside it gave the old tile),
  -- and it carries only world coordinates. A unit the engine automates during our turn and then loses
  -- during our own turn (only reachable through Lua surgery) keeps its turn-start plot.
  -- The unit is still readable inside the hook (delayed death): keep its type and plot, so the loss can be
  -- named and a capture notice ("A Worker was captured by the Barbarians!") tied to the unit and the tile the
  -- click would pan to (live 2026-09-24 t217: Bravo's Settler arrived as a bare id beside the notice).
  -- Hotseat: the barbarian/AI phase runs while the previous seat is still active, so a loss belonging to
  -- another human seat is filed for that seat (same as H.unit_damaged).
  hook("SerialEventUnitDestroyed", function(playerID, unitID)
    local d = { player = playerID, unit = unitID }
    pcall(function()
      local u = Players[playerID] and Players[playerID]:GetUnitByID(unitID)
      if u then
        d.unit_type = short(info_type(GameInfo.Units, u:GetUnitType()))
        d.x, d.y = u:GetX(), u:GetY()
      else
        local r = H.roster and H.roster[playerID] and H.roster[playerID][unitID]
        -- The roster's plot is where the unit was last noted (turn start, turn end, a harness move): a unit the
        -- engine moved on automation since (an explorer taking ruins, #100) stood elsewhere. Say which it is, and
        -- whether the roster saw it moving on its own (automated or on a standing move) -- never assume it (#169).
        if r then
          d.unit_type, d.x, d.y, d.plot_from = r.unit, r.x, r.y, "roster"
          if r.automated or r.moving then d.moving = true end
        end
      end
    end)
    pcall(H.attach_successor, d)   -- #169: the unit my order saw replaced (successors.lua), with the plot it took
    pcall(H.link_late_capture, d)
    local audience
    pcall(function()
      if playerID ~= Game.GetActivePlayer() and Players[playerID]:IsHuman() and PreGame.IsHotSeatGame() then audience = playerID end
    end)
    H.record("unit_destroyed", d, audience)
  end)
  hook("SerialEventCityCreated", function(hex, playerID, cityID)
    -- `hex` is in hex space, not plot coordinates (live: Rio at plot (46,24) arrived as hex x=34).
    local x, y
    if hex then x, y = ToGridFromHex(hex.x, hex.y) end
    local d = { player = playerID, city = cityID, x = x, y = y }
    -- The city stands by now: carry its name (the row read {player, city, x, y} and only the alert said "Assur").
    pcall(function()
      local c = (x and y) and Map.GetPlot(x, y):GetPlotCity() or nil
      if c then d.name = c:GetName() end
    end)
    H.record("city_created", d)
  end)
  hook("SerialEventUnitSetDamage", function(playerID, unitID, newDamage, oldDamage) H.unit_damaged(playerID, unitID, newDamage, oldDamage) end)
  hook("SerialEventCityDestroyed", function(hex, playerID, cityID) H.record("city_destroyed", { player = playerID, city = cityID }) end)
  -- `cityID` here is the PREVIOUS owner's id for the city, and city ids are per-player: the Inca's
  -- 8192 is a different city from our own 8192. Live t190, capturing Cusco: the row read
  -- `{player=2, city=8192, by=0}`, and 8192 looked up in cities() is our capital Moson Kahni --
  -- an id that silently resolves to the wrong city is worse than no id. Name the plot's city, which
  -- by now belongs to the captor, and keep the raw one under a name that cannot be mistaken for ours.
  hook("SerialEventCityCaptured", function(hex, playerID, cityID, newPlayerID)
    local d = { player = playerID, by = newPlayerID, former_city_id = cityID }
    if hex then d.x, d.y = ToGridFromHex(hex.x, hex.y) end
    pcall(function()
      local pl = (d.x and d.y) and Map.GetPlot(d.x, d.y) or nil
      local c = pl and pl:GetPlotCity()
      if c then d.name, d.city_id, d.owner = c:GetName(), c:GetID(), c:GetOwner() end
    end)
    H.record("city_captured", d)
  end)
  hook("WarStateChanged", function(team1, team2, atWar) H.record("war_state", { team1 = team1, team2 = team2, at_war = atWar }) end)
  hook("GameMessageChat", function(from, to, text, target) H.record("chat", { from = from, to = to, text = text, target = target }) end)
  hook("EndCombatSim", function(attPlayer, attUnit, attDmg, attFinal, attMax, defPlayer, defUnit, defDmg, defFinal, defMax)
    H.record("combat", { att_player = attPlayer, att_unit = attUnit, att_dmg = attDmg, att_hp = attFinal, def_player = defPlayer, def_unit = defUnit, def_dmg = defDmg, def_hp = defFinal,
                         attacker = H.combat_side(attPlayer, attUnit), defender = H.combat_side(defPlayer, defUnit) }) end)
  hook("NotificationAdded", function(id, type, toolTip, summary, data1, data2, playerID)
    H.record("notification", { id = id, ntype = type, text = toolTip, summary = summary, d1 = data1, d2 = data2, player = playerID }) end)
  hook("AILeaderMessage", function(playerID, diploState, message, animation, data1)
    -- harness_initiated: said while the harness itself had the leader/trade screen open (propose_deal,
    -- negotiate_deal); it is the reply to OUR visit, not the AI approaching us. turn_digest hides these.
    H.record("leader_message", { player = playerID, state = H.diplo_state_name(diploState), text = message,
                                 harness_initiated = H.harness_diplo or nil })
  end)
  hook("GameplayAlertMessage", function(text)
    if text == "Quicksaving..." then return end  -- our own quick_save, fired twice per save: digest noise
    local row = { text = text }
    -- "The enemy has been spotted near Nanjing!" names a city but no plot; a human looks at the map
    -- next to it. Attach the hostile units visible within 3 plots of any own city the text names.
    local ok, near = pcall(H.hostiles_near_named_city, text, Game.GetActivePlayer())
    if ok and near then
      row.city = near.city
      -- "Assur has been founded." carried `hostiles: []` (live Assyria t0): an empty list says nothing.
      if type(near.hostiles) == "table" and #near.hostiles > 0 then row.hostiles = near.hostiles end
    end
    H.record("alert", row)
  end)
  -- The digest row is recorded when the popup is QUEUED: the harness's own popup sweep can close a
  -- popup before it is ever "Shown" (live 2026-09-18: the barbarian-camp reward never reached the
  -- digest). The same popup can be queued repeatedly (hotseat, reopened screens): one row per turn.
  hook("SerialEventGameMessagePopup", function(info)
    local key = Game.GetGameTurn() .. ":" .. Game.GetActivePlayer() .. ":" .. tostring(info.Type) .. ":" .. tostring(info.Data1) .. ":" .. tostring(info.Data2)
    H.popup_rows = H.popup_rows or {}
    if H.popup_rows[key] then return end
    H.popup_rows[key] = true
    local row = { type = info.Type, name = H.enum_name("ButtonPopupTypes", ButtonPopupTypes, info.Type) }
    if info.Type == ButtonPopupTypes.BUTTONPOPUP_GOODY_HUT_REWARD then
      local g = GameInfo.GoodyHuts[info.Data1]   -- Data1 = GoodyHuts row id, Data2 = amount (gold, culture...) when any
      row.reward = g and g.Type or nil
      if (info.Data2 or 0) > 0 then row.amount = info.Data2 end
    elseif info.Type == ButtonPopupTypes.BUTTONPOPUP_BARBARIAN_CAMP_REWARD then
      row.gold = info.Data1   -- live 2026-09-18: Data1 = 16 with "...recovered 16 Gold!"
    elseif info.Type == ButtonPopupTypes.BUTTONPOPUP_NATURAL_WONDER_REWARD then
      row.x, row.y = info.Data1, info.Data2   -- live: [46, 17] = the wonder's plot
      local plot = Map.GetPlot(info.Data1, info.Data2)
      local f = plot and plot:GetFeatureType() or -1
      if f >= 0 then row.wonder = short(info_type(GameInfo.Features, f)) end
    elseif info.Type == ButtonPopupTypes.BUTTONPOPUP_CITY_STATE_GREETING then
      local cs = Players[info.Data1]              -- live: [31, 30] = minor player id, gold gift on meeting
      row.city_state = cs and cs:GetName() or nil
      if (info.Data2 or 0) > 0 then row.gold_gift = info.Data2 end
    end
    H.record("popup_shown", row)
  end)
  hook("SerialEventGameMessagePopupShown", function(info)
    H.popups[info.Type] = {type=info.Type, player=Game.GetActivePlayer(), data1=info.Data1, data2=info.Data2, data3=info.Data3,
                           data4=info.Data4, data5=info.Data5, option1=info.Option1, option2=info.Option2}
  end)
  hook("SerialEventGameMessagePopupProcessed", function(kind)
    H.popups[kind] = nil
  end)
  hook("SerialEventEnterCityScreen", function() end)
end

-- The digest's follow-up reads (harness/game_parts/events.py), named entries since stage 3 of the seat binding.
function H.units_alive(ids, pid)
  local p, out = Players[pid], {}
  for _, id in ipairs(ids or {}) do
    local u = p:GetUnitByID(id)
    if u and not u:IsDelayedDeath() then out[#out + 1] = id end
  end
  return out
end

function H.conversion_banner(text, pid)
  local d = { text = text, player = pid }
  H.attach_conversion_banner(d, Players[pid])
  return d
end

function H.steal_tech_note(text, summary, pid)
  local d = { text = text, summary = summary, player = pid }
  H.attach_steal_tech(d, Players[pid])
  return d
end

function H.delivered_notification_texts(pid)
  local t = {}
  for _, e in ipairs(H.events) do
    if e.kind == "notification" and e.audience == pid and e.data and e.data.text then t[#t + 1] = e.data.text end
  end
  return t
end

function H.route_start_rows() return H.route_starts or {} end
function H.event_seq_now() return H.event_seq end
