-- Harness runtime injected into the InGame Lua state through the tuner.
-- Everything lives under the global table H so re-injection is idempotent.
local RUNTIME_VERSION = 333
if H and H.version == RUNTIME_VERSION then return true end  -- true: tells the installer to stop here
local old = H
-- _enum_names is intentionally NOT carried over from `old`: it is a pure cache derived from live game
-- globals, not accumulated state, and carrying a stale (possibly wrong, e.g. built by since-fixed buggy
-- code) cache across a version bump is exactly how a real fix here silently failed to take effect once
-- already -- caught live. Only genuinely irreplaceable state (recorded events, hook closures needed to
-- Events.Remove() them) belongs in the carry-over list below.
H = { version = RUNTIME_VERSION, events = old and old.events or {}, event_seq = old and old.event_seq or 0,
      cursors = old and old.cursors or {}, popups = old and old.popups or {},
      hook_fns = old and old.hook_fns or {}, _enum_names = {},
      -- _ns: the top-level locals one fragment shares with later ones (`H._ns.short = short` at the owner's
      -- end, `local short = H._ns.short` at the consumer's top; load order in harness/runtime_source.py
      -- MANIFEST). Like _enum_names it is rebuilt by every injection, never carried over.
      _ns = {},
      -- dedupe memory for engine events that fire more than once (notifications re-added at the hotseat
      -- hand-off, popups re-queued, war state per direction): wiping it on a reload re-reports them
      seen_notes = old and old.seen_notes or {}, popup_rows = old and old.popup_rows or {},
      -- last-seen features per team (GitLab #19): what a human still sees drawn under fog. Only ever
      -- written from a visible plot; wiping it on a reload would forget every forest seen since load.
      seen_features = old and old.seen_features or {},
      last_war_key = old and old.last_war_key or nil,
      known_sites = old and old.known_sites or {},  -- team -> plot index -> true: ruins/camps already reported (H.new_sites)
      route_units = old and old.route_units or {},  -- seat -> unit id -> {key, turn, turns_left}: which route each caravan is on (H.trade_routes)
      pending_moves = old and old.pending_moves or {},  -- unit_id -> {x, y}: standing move orders (see H.resume_moves)
      reveal_marks = {},  -- pm_key -> what was revealed around a unit when move_unit sent it (H.reveal_mark / H.reveal_diff); per call, never carried
      hp_snaps = old and old.hp_snaps or {},  -- seat -> own units' hp at its turn end (H.hp_snapshot / H.hp_compare)
      successors = old and old.successors or {},  -- seat -> old unit id -> the unit that replaced it under a new id (successors.lua, #169)
      roster = old and old.roster or {},  -- seat -> unit id -> {unit, x, y}: last-known own units (H.note_units), for losses the destroy event no longer lets us read
      turn_seat = old and old.turn_seat or nil,  -- the seat whose turn is running (ActivePlayerTurnStart); GetActivePlayer already names the next seat when ActivePlayerTurnEnd fires in hotseat
      alive_majors = old and old.alive_majors or nil }  -- player id -> true at the last turn start (H.check_eliminations)
