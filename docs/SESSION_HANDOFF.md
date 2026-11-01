# Resume here -- 2026-10-31 (night): main = 2.13.0 (runtime v335, 9 tools, 2114 tests; tagged 2026-10-31, with v2.11.0 and v2.12.0 backfilled at 8b10ac9 / 6c7b76f).
**The thirteen issues of the 2026-10-30 three-seat hotseat (milestones 2.11.0, 2.12.0, 2.13.0) are fixed on main
and released**, each as one commit with a regression test and a GitLab note: #168 (9cc36ec, the notebook key ends in a
per-game identity, old-key notebooks adopted once and quarantined), #174 + #172 (50675bf, the shared hotseat scratch
trade table is read seat-aware), #175 (8b10ac9, a human seat is asked on the trade table: friendship as a DoF deal,
war through SendChangeWar, denounce refused), #181 + #182 (90edcba, orders.counts after the run; direct_command
never pauses the order it creates), #176 + #169 (6c7b76f, the `hold` block; the ruins successor named by the move),
#180 + #177 (e9241f9, step_cost.lua ports CvUnitMovement::MovementCost; a city is the cell's ground letter), #179 +
#178 + #171 (343af86, locked ideologies as names; belief rows carry their call; tests/test_playbook_examples.py checks
every served example). CHANGELOG's Unreleased holds the entries; the trackers #167 / #173 stay open as the record.
**Nothing of this was seen live** (no game ran tonight; the last live process was runtime v328). Next: a live
session on the three-seat hotseat save (or the t237 Maya save) to read back, in this order: `H.game_key_facts`
before and after a reload (GetStartingPlot stable; the live notebooks adopt once with orders paused); #172's deal
sequence (0->2 unseen on seat 1, then 0->1, 1->2, overlapping offers); a DoF deal read on both seats and IsDoF
after the accept; tactical `cost` against the moves an order actually spends (forest on hills, a river, a road, a
ZOC step); `GetFortifyTurns` right after MISSION_FORTIFY; a ruins step's successor at the read-back. The releases are cut: `v2.11.0`
and `v2.12.0` tagged after the fact on the commits that closed their milestones (8b10ac9, 6c7b76f), `v2.13.0` on the
bump commit; CHANGELOG split into the three entries, README row + bullets + test count, AGENT_INSTALL line 8, ROADMAP;
GitLab and GitHub Release objects for all three, the three milestones closed.

# Previous -- 2026-10-30 (evening): main = 2.10.0 (runtime v328, 9 tools, 2039 tests; tagged 2026-10-30).
**2.10.0 "Decisions explained, lean replies" is shipped**: the seven issues of milestone 19 in the planned order, each with
a regression test and a GitLab note (CHANGELOG 2.10.0). #142 and #148 were done this evening and seen live on the t237
Maya save (`Pacal_0237 maya-t237`, single/): a Great Musician spawned beside Palenque read `missing` rows for the Great
Work (music slots 2/2, "build one of: Opera House, Ceilidh Hall, Broadcast Tower") and the concert tour (nearest Venetian
plot (29,63), 5 away), its tour order was refused up front from home soil; a Warrior spawned on Almaty's plot carried the
COMMAND_GIFT row with owner Almaty and the complete gift_unit call; the map window on fogged Zurich (27,62) named the city;
culture_works tooltips read "+2 Culture, +2 Tourism"; Venice's trade catalog listed 2 peace rows and counted 13 + 11 "not
at war" ones; the Units row has no GreatWorkType column at runtime (the Great Work class comes from
Unit:GetGreatWorkSlotType, v328). **The game on screen is the t237 Maya save, unsaved, with three Lua-spawned test units**
(Writer 991264 at (34,62), Musician 999457 at (34,63), Warrior 1007645 at (40,52)); nothing was saved, the quick slot is
untouched. Steam, the game (launched 20:1x by `scripts/launch_civ5.sh main`) and tunerd (no seat table, `logs/tunerd.log`)
are up; the live process runs runtime v328. Next: the three tracking issues (#149, #150, #157) stay open as the record of
the 2026-10-29 sessions; a new play session (Codex / Grok hotseat or the Maya game) files the next milestone. Glama's TDQS
re-score of 2.8.0-2.10.0 is still to be read back (the nine descriptions did not change in 2.10.0).

# Previous -- 2026-10-30 (morning): main = 2.9.0 (runtime v322, 9 tools, 2001 tests; tagged 2026-10-30).
**2.9.0 "Reads and schemas tell the truth" is shipped**: the eight issues of milestone 18 in the planned order, each with
a regression test and a GitLab note (CHANGELOG 2.9.0), and the milestone's done-when seen live: #165 on the hotseat game
at t39 (the Worker's quarry: order reply, unit row and plot line all 4), #163 / #164 / #146's refusal shapes at t39,
#140 on the t237 Maya save (an Archaeologist spawned by Lua on the (41,55) site, `dig_sites`, the dig `started,
turns_left 4` on all three reads, `todo.dig_choice` at t240, question() with the note, answer(choice=2) naming the
Doubloon in Palenque's Museum; the drive refused an AI's Research Agreement and a coop-war ask, voted the Congress host
and set Wealth in two idle cities on the way), #156 on S3 combat-lab (Musketman 630799 killed the barbarian Warrior at
(49,18): `defender {hp 0, killed}`, damage 100 / 5). **The game on screen is the hotseat game at t39 again**, seat 0's
turn, research unset, reloaded from the new S12 `Pacal-Isabella_0039 t39-quarry-165-check` (hotseat/); the t237 Maya
save and S3 were not re-saved after the checks. The live process runs runtime v322 (installed by the scripts/mcp_session.py
servers of the checks); any `--seat auto` MCP server of an older Claude Code session must be restarted (/mcp reconnect)
before it is used on this game. Next: milestone 2.10.0 (GitLab 19), #142 first; its order is in the milestone description
and `docs/ROADMAP.md`. Glama's TDQS re-score of 2.8.0 / 2.9.0 is still to be read back (offline lint 0 warnings, the
notebook description 1979 characters).

# Previous -- 2026-10-30 (early morning): main = 2.8.0 (runtime v320, 9 tools, 1978 tests; tagged 2026-10-30).
**2.8.0 "Hotseat: nothing stalls or leaks" is shipped**: the nine issues of milestone 17 in the planned order, each with
a regression test and a GitLab note (CHANGELOG 2.8.0), and the milestone's done-when seen live: the Codex/Grok hotseat
game (Maya seat 0 / Spain seat 1) was on screen at t38 behind a stale, empty trade table; `leave` now cancels such a
table, seat 0 proposed a two-item deal, seat 1's question() read it as a screenless question and refused it, seat 1
proposed one back, seat 0 read and refused it at t39. **The game on screen is that hotseat game at t39, seat 0's turn,
research unset** (ENDTURN_BLOCKING_RESEARCH); the save before the check is S11 `Pacal-Isabella_0038 before-161-check`
(hotseat/). The live process runs runtime v320 (installed by the scripts/mcp_session.py servers of the check); three
`--seat auto` MCP servers of Claude Code sessions still hold v318 code -- restart them (/mcp reconnect) before they are
used on this game. Next: milestone 2.9.0 (GitLab 18), #156 first; its order is in the milestone description and
`docs/ROADMAP.md`. Glama's TDQS re-score of 2.8.0 is still to be read back (the listing changed by one clause of
`question`; offline lint 0 warnings).

# Previous -- 2026-10-30: main = 2.7.1 (runtime v318, 9 tools, 1963 tests). **Planned, not started:** the 24 issues
from the 2026-10-29 play sessions (#149 Maya t203-t237, #150 Grok hotseat seat 1, #157 Codex hotseat seat 0) sit in
three ordered milestones, 2.8.0 (17), 2.9.0 (18), 2.10.0 (19); the order is in each milestone's description and in
`docs/ROADMAP.md`. Start with 2.8.0's #161 (an incoming human deal cannot be read). #140-#148 were filed with empty
bodies (the filing script's inner heredoc swallowed the outer one); their text was restored from the session transcript.
#139 closed as shipped.

# Previous -- 2026-10-29 (late night): main = 2.7.1 (runtime v318, 9 tools, 1963 tests; tagged 2026-10-29). **2.7.1: the four descriptions Glama's TDQS panel marked under 4.5 are restructured** (GitLab #139: `turn` 3.6 -> 4.6, `notebook`, `answer`, `batch` 4.2-4.3 -> 4.6-4.8; hosted TDQS 4.7 A, every tool 4.6 or better, report https://tdqs.dev/reports/p0usqgjwik; Glama's own re-score of v2.7.1 is still to be read back from the admin panel and recorded on #139; the admin panel's marks on v2.7.0 are `docs/measurements/2026-10-29-glama-tdqs-admin-v2.7.0.md`). **2.7.0: `inspect` is `state`** (GitLab #138, the user's pick for a strict all-noun set after Glama's naming 4/5): same arguments and replies, `inspect` retired with `renamed` like the 145 old names; every doc, row and runtime string says `state`; a running client's server must be restarted (/mcp reconnect) to list it, and 2.7.0 was cut the same night (Releases on both forges) so Glama's scorer sees it. Milestones 2.2.0 (17 issues), 2.3.0 (21), 2.4.0 (12), 2.5.0 (8) and 2.6.0 (11) are closed, every issue fixed in the milestone's order with a regression test and a GitLab note (CHANGELOG 2.2.0-2.6.0). **The game on screen is the Maya t200 save** (`Pacal_0200 maya-t200`, reloaded 2026-10-29 for the 2.6.0 measurement). **That open point is solved (GitLab #137, 670d705, runtime v317, released as 2.6.1):** the End Turn stayed disabled because the reload followed a `session(action='main_menu')` with Dido's leader screen up (her friendship request comes during the AI turns after every t200 finish); the exe keeps the leader view open into the next game loaded and `UI.RequestLeaveLeader()` clears it. The exit now leaves a leader on screen first (`left_leader_view: true`) and `H.end_turn_send` clears a stale view itself (digest event `stale_leader_view_cleared`); both verified live on the t200 save, which is on screen at t200, turn start, nothing blocking, End Turn enabled. The stack is up (Steam, Civ5XP, tunerd on the plain daemon). The 2.6.0 before/after bytes are in CHANGELOG 2.6.0 (`state(what='city_state', view='full')` 8109 -> 5508 B). **After a release cut, restart the client's MCP server** (Claude Code: /mcp reconnect): a running server keeps its import-time listing; since 2.6.0 its status says `server_outdated` and names the seat's other servers (`other_clients`). The hand-started Random-map Maya game of the day is saved as `Pacal_0005 maya-random-t5`. GitHub Releases: v2.5.0 and v2.6.0 exist (created 2026-10-29; the mirror github.com/ty-meador/civ-v-linux-mcp carries a tag about a minute after a mirror sync, which the 5-minute throttle may delay). 2026-10-29 evening: Glama re-scored the 2.0.0 listing by itself (2026-10-28, A 4.4/5.0: completeness 5, naming 4, disambiguation 5, tool count 5), recorded on #59 and in CHANGELOG 2.0.0; #58, #59 and milestone 2.0.0 closed; the eight play-session trackers closed (every linked issue was already closed). **No GitLab issue is open.** 2.6.1 was cut the same evening with Releases on GitLab and the GitHub mirror (v0.3.0 and v0.5.0 backfilled too). Next: the next play session's findings. The Assyria notes below are the 2026-10-27 state, kept for the record.

This file holds the current state only. Earlier "Resume here" sections (58 of them, 2026-09-19 to 2026-10-11) live
in git: `git log -p -- docs/SESSION_HANDOFF.md`; the 2026-10-11 version carries this game's t0-t163 turn by turn.
Shipped work is in `CHANGELOG.md` (the 1.16.0 section holds t164-t208's fixes); known gaps are inventoried in
`docs/GAPS.md`.

## Where the game is

- **The save and the lost turn.** The newest file is the quick save written 2026-10-15 00:07 at **t238** (now also
  `single/Ashurbanipal_0238 international-games`); the engine's autosaves stop at t230. The notebook's briefing
  baseline says t239: the last session ended one turn past the save, and that turn's work is in no file. `load_latest`
  opens t238; the briefing then rightly says the baseline restarts.
- **t238, turn start, nothing blocks.** `gate` null, `decisions` empty, `todo.units` / `cities` empty, no threats in
  sight, no war. Eight units are `ongoing` (two automated Workers 475160 / 507929, six Caravans on routes). Events
  at the turn start: International Games PASSED (14 Yea from me, 9 Siam, 2 more), Ban Luxury: Crab FAILED (my 10
  Nay against Siam 7 + Portugal 5 Yea), two "Great Person born" notices, Sofia cancelled a quest, Antwerp seeks a
  Great Writer. **Look first:** the units list shows no new Great Person beyond Great Engineer 1130538 (t221) and
  Great General 1122345 (t220), so whoever was born at t238 was spent before the quick save or is not what the
  notice says -- `units` / `great_person_progress` settle it.
- **Empire (t238).** Assur (16,27) pop 25, Nineveh (20,28) 20, Nimrud (18,23) 16, Kar-Tukulti-Ninurta (12,26) 15;
  all Judaism, all garrisoned, all growing. Gold 2334 at +56, science 850, culture 275 a turn with 2691 stored
  (next policy 3575), faith 1065 at +94, happiness 68, 53 units, score 1607. Golden Age over (t235). Era: Future
  (Satellites t224).
- **Science victory.** Apollo Program done t223 in Assur; SS Cockpit bought (2160 g, t224) and added t225. Now:
  Assur builds the **SS Stasis Chamber** (8 turns; Nanotechnology is known), Nineveh and Nimrud finish **Spaceship
  Factories next turn** (Assur has one), K-T-N runs the Research process. The **SS Engine** needs Particle Physics
  (Atomic Theory researching, 5 turns, 408 stored; then Particle Physics); the **three SS Boosters** need Advanced
  Ballistics, not yet in `available_research` (Archaeology 1 turn and Lasers 7 are the other two offered). No rival
  has Apollo (`spaceship_status.rivals` empty). The habit that got here: faith-buy a Great Scientist whenever faith
  allows (2680 at t228) and bulb it; Hubble (t226) gave two; the Great Engineer rushed Hubble.
- **Policies.** Tradition and Patronage done, Rationalism finished t188 (free Flight), Freedom since t200: Avant
  Garde, Civil Society, New Deal (t195), Creative Expression / Space Procurements (t209-t213), Capitalism (t216),
  Volunteer Army (t221: six Foreign Legions), Treaty Organization (t225), Cultural Diplomacy (t230), Merchant
  Confederacy (t231). Universal Suffrage was refused at t208 by the level gate (runtime v283 names it).
- **Diplomacy** (note 2, t236, is the full picture). SIAM (Ramkhamhaeng, player 2) adopted Order t234 and
  **denounced me t235**, three turns after renewing the DoF: the largest army on the continent, borders Nimrud and
  Nineveh from the north, at war with Shaka since t229-t230; a war risk from now on. Deals running with Siam: the
  Research Agreement signed t220 (pays t245; I gave 268 g + 5 Coal + 3 Aluminum + 9 gpt), Marble for 5 gpt to t248,
  open borders to t249 (consider not renewing), and **Salt for 5 gpt ended this turn (reoffer t239)**. PORTUGAL
  (Maria, player 1): neutral-friendly, Salt for Truffles to t247 (Truffles is my only copy). ZULU (Shaka, player
  3): friendly, open borders to t250, **Fur + 4 Iron for Dye ended this turn (reoffer t239; Dye is my only copy;
  Nimrud's WLTKD ended t234 and it now wants Crab)**. Promised t201: no more conversions in Siam.
- **United Nations.** I host; 24 delegates (4 + 2 host + 18 from nine allies) against Siam 16, Portugal 8, Zulu 4.
  World Leader needs 42 and is **"Not allowed by this game's options"** (diplomatic victory is off in this game).
  Active: Sciences Funding, World Religion Buddhism, Cultural Heritage Sites (+3 culture per wonder), and now the
  **International Games project** (cost 1929; 482 production for tier 2, the top contributor gets +100% tourism for
  20 turns and a free policy; I have contributed 0 -- Nineveh and Nimrud are free after their factories). My
  proposal **International Space Station** (free Great Scientist, research boost, the ISS wonder) is pending;
  Siam says Yea (16); the session is in 6 turns (t244). World's Fair finished with me at tier 3 (644 of 938).
- **City-states.** Nine allies (2 delegates each); the t196 list was Mombasa, Yerevan, Malacca, La Venta,
  M'banza-Kongo, Ormus, Monaco, Sofia, with Belgrade added t216 and Colombo / Antwerp lost to Portugal at t231;
  `city_state_bonuses` is the live list. Siam buys city-states aggressively (Bratislava, Byblos, Zurich flip back
  and forth); Treaty Organization plus caravan routes to La Venta, Malacca, Sofia and Nobamba is the counter.
  Gifted units keep arriving (Paratroopers from Belgrade t231 and M'banza-Kongo t233, Rocket Artillery, an
  Infantry); the spare Knights 868385 / 892934 are `gift_unit` candidates.
- **Assignments and orders.** Two active garrison roles, both `on_track`: 4 (Nimrud; Swordsman 335873 -- which
  stands on (16,24), not in the city, see Still open) and 6 (Nineveh; French Musketeer 704517 in place). No open
  standing order: the last, 51 (Scout 98304 home to (14,26)), completed t229. Notes: 1 (t93 plan, stale), 2 (t236
  diplomacy, current), 3 (t196 plan, the strategy; its numbers are stale), 4 (t98 diplomacy, stale). A fresh plan
  note at t238 is the first thing to write.
- **Military.** 53 units: six Foreign Legions, four Infantry, two Paratroopers, two Rocket Artillery, an Artillery,
  four Hwacha, a Gatling Gun, an Anti-Aircraft Gun, and a long tail of obsolete units (Swordsmen, Pikemen,
  Crossbowmen, a Trebuchet, a Lancer, Knights, a Horseman, a Musketman, Ski Infantry); plus five Workers and six
  Caravans. Upgrades were never a priority; with Siam hostile they may become one (`upgrade_unit` carries the
  notebook over).

## Where the code is

- **main = 2.0.0, tagged 2026-10-26** (runtime v287, 9 tools, 1694 tests): "The tool surface" (milestone 11,
  #44-#58) -- nine tools where 145 were, every old name answering through the retirement map, every listing
  reply carrying the order to copy, the words and the runtime strings in the new vocabulary, fresh Claude Code
  and Codex sessions through the nine. README has the release row and the test count; ROADMAP the release
  paragraph and row 5; AGENT_INSTALL says 2.0.0; the CHANGELOG entry carries the 2026-10-04 Glama marks with
  the 2.0.0 re-score to be written beside them. 1.16.0 (2026-10-24, runtime v283, 145 tools, 1548 tests) was
  the twenty-eight fixes from the England game's end and this game's t0-t208.
- **The fair-play design note (8728ded, 2026-10-24).** A `--seat N` server refuses `set_seat` onto the other human
  seat and nothing else stands between one agent and the other's map (tunerd forwards any Lua for any caller; a
  second server, `scripts/mcp_call.py --seat N` and `harness.cli lua` reach the same socket). `docs/GAPS.md` has
  the threat model and a first count of runtime entries by seat argument (81 take `pid` first, about a hundred
  take a unit / city / plot and get their seat from the owner); `docs/ROADMAP.md` the five-stage route with tunerd
  as the enforcement point. Not started. (The small follow-up on `docs/AGENT_INSTALL.md`'s Codex paragraph was done 2026-10-27: it registers
  `--seat auto`, and one paragraph states the seat rule for every client -- auto for solo play, a pin only for a
  shared hotseat, with the reason.)
- **Live processes (2026-10-24 21:45).** Game pid 38183 (launched 21:42 by `scripts/launch_civ5.sh main`; Steam was
  already up), tunerd on `/run/user/1000/civ5-tuner.sock` since 21:44 (48 Lua states on its first connect), the
  Claude Code session server pid 25370 started 21:02 from current main. The quick save was loaded through
  `load_latest` at 21:45; runtime v283 answered the first briefing. Runtime v284 has been in the game since
  22:10 (injected by a fresh `scripts/mcp_session.py` server for the live checks above); the session server pid
  25370 still runs the v283 Python, so its `assignments` rows lack `distance` and an `amend_assignment` through it
  would refuse `review.max_distance` as an unknown key until it is restarted from current main.
- **Where t208-t238 is written down.** Nowhere in the repo: those turns were played on 2026-10-14/15 without a
  code change (the commits stop at t208). The notebook (note 2) and the saves are the record; the memory plugin's
  observations hold a turn-by-turn narrative outside the repo.
- **Memory-rule reminders**: the ctx sandbox lacks XDG_RUNTIME_DIR, export
  `CIV5_TUNERD_SOCK=/run/user/1000/civ5-tuner.sock` before any `harness.cli` call there; `pkill -f` in a
  compound Bash call kills the shell; disband is denied to the auto-mode classifier; copy QuickSave to a named
  file before loading another save into a live game (done this evening: S10).

## Still open

- **Seen at t238, understood and read since (runtime v284, 2026-10-24 late evening; CHANGELOG Unreleased).** (1) The
  two "Great Person born" notices were a Great Scientist (bulbed: Nanotechnology) and a Great Musician (a Great
  Work), both spent on 2026-10-15 in the same t238 before the quick save -- the call ledger's `do` row at 00:07
  has both missions; `notification_log` now names the person (`unit: SCIENTIST` / `MUSICIAN`, `of_type_now: 0`)
  and a notice whose person the hook saw born reads `unit_gone` once it is spent. The Great Person count of
  t238 is therefore right: nothing is missing. (2) Assignment 4's Swordsman 335873 stands THREE plots from Nimrud
  (Map.PlotDistance agrees), not two; every assignment unit row now carries `distance`, both garrison assignments
  (4 and 6) carry `review.max_distance: 0`, and assignment 4 reads needs_review ("3 plot(s) from its post (18,23)")
  until the Swordsman is back on (18,23) or the assignment is amended. (3) `league_status` carries
  `diplomatic_victory_enabled: false` with `diplo_victory_note`; the 42 is moot in this game.
- **The Siam risk.** Denounced t235, Order against my Freedom, their army the largest, open borders running to t249.
  Nothing in the harness is missing for a war (the England siege read everything), but the garrison roles and the
  obsolete army are the seat's own problem; the renewals due t239 (Zulu Dye, Siam Salt) are the first decisions.
- **Not yet seen live**: `quick_save` under a decision popup (coded 2026-10-11), the `fogged_destination` hint on a
  "no path" refusal (unit tests only), S9's RETURN_CIVILIAN re-raise on load, the refused-melee *rule* (GAPS §0
  Blocked: needs a war with the t200 shape -- a city tile, a river, a second unit in the city; only the wording is
  done).
- **Two tests failed once, together, on the first `scripts/check.sh` run of 2026-10-10 evening** (the 1.15.0 cut):
  `test_ranged_preview.py::test_ground_ranged_has_no_retaliation_or_interceptor_read` and
  `test_runtime_source.py::test_a_failure_midway_is_not_current_and_the_corrected_retry_carries_state`; one of the
  two failed once more in a loop of three runs of just those two files. The assertion text was not captured
  either time. Not reproduced since: every full run through 2026-10-24 (three today, 1548 green) and 37 runs of the
  pair. Both build a Lua state from `runtime_source.snapshot()` (one under ctypes liblua5.4, one under lupa). If it
  shows again, keep the `E` lines: a `pairs`-order dependency under a randomized string-hash seed is the first
  suspect, load the second.
- `unit_displaced` (read live England t131): a *route* caravan on the city tile at the turn end did not move the
  General, only an idle trade unit does; why the engine moves the civilian and not the trade unit, and whether a
  Worker or Settler is moved the same way, is not known; the row reports the fact either way.
- Spectator page: it still holds every parsed row of a recording (fine since the cadence fix; the 72 MB pre-fix
  file was 122 MB of heap under node, 70-72 MB in Chrome); a bounded window is the ROADMAP's open visualization
  item.
- **Seat binding, stage 1 done (2026-10-24 late evening, uncommitted runtime untouched):** tunerd `--seats FILE`
  binds connections by token or uid and refuses unbound `exec`/`query` (`tests/test_tunerd_seats.py`, 21 tests).
  The live tunerd runs without a table (solo game; nothing to bind). **Stage 2 done 2026-10-25**
  (`scripts/seat_survey.py`, GAPS "Stage 2, the survey"): the seat slot is per entry (90 first / 102 last / 15
  middle), three Python-reached entries lack one (`H.diplo_event`, `H.plot_units`, `H.plots_around`), `Game.seat`
  is the one attribute stage 3 replaces, and 48 `InGame` ad-hoc bodies become named entries. **Stage 3 done
  2026-10-25 evening (runtime v285, `tests/test_seat_call.py`), not yet seen live:** tunerd's `call` / `runtime`
  ops write the seat and install the runtime; `Game.h` names entries; no Lua text goes to `InGame` from the Python
  side. Seen live the same evening after a cold start (Steam was up, the game was not): `load_latest` and every
  read of the turn through `call` on a plain daemon; then on a daemon with a one-seat token table a tokened
  `mcp_session.py` read `turn_status` / `units` / `todo_actions` / `generic_popup` / `tactical_view`, an untokened
  one was refused unbound, and a tokened `cli lua` was refused for `InGame`. The stack was left up: the game at
  t238 (nothing ordered, no turn ended), tunerd restarted **without** a table (the new code; the idle Claude Code
  servers reconnect by themselves). **Next session's first `finish_turn` is the live turn through `call`**: watch
  `logs/calls.jsonl` trips stay the usual (the daemon adds no trip once the runtime is checked) and the tunerd log
  for a single `runtime v285 ... installed` on a bound daemon. **Stage 4 done 2026-10-25 late evening**
  (`tests/test_seat_escape_hatches.py`): a bound server plays its binding only (a wrong `--seat` is refused on every
  tool, `set_seat` moves nowhere else, the `lua` tool refuses), seen live at t238 on a one-seat table from this
  sandbox (eight probes), tunerd restored **without** a table again. **Stage 5 done 2026-10-25 night, the route
  complete:** the Alpha/Bravo hotseat (S2a, t229) played on a two-seat token table by two processes each holding only
  its own token (`play_loop.py --seat N`): seat 0 ended t229-t231, seat 1 t229-t230, every turn end through `call` on a
  bound daemon (so the live turn through `call` is seen; the Assyria `finish_turn` is still the user's), no refusal in
  the tunerd log, and the eight escape-hatch probes from each agent's process as stage 4 says. The Assyria game was
  quick-saved as `Ashurbanipal_0238 pre-stage5` before and reloaded after; the hotseat result is
  `Alpha-Bravo_0231 two-agents-bound`; tunerd runs **without** a table again. The tool-surface plan is now GitLab
  milestone 2.0.0 (one issue per stage item, tracking issue listed in `docs/ROADMAP.md`); work from the issues.
  **Stage 0 (#44) done 2026-10-25 night:** `harness/surface/` (vocabulary, retirement map, survey, audit),
  `scripts/tool_survey.py --write` -> `docs/measurements/tool_survey.md`, `tests/test_tool_survey.py`; the baseline
  reproduces. **Stage 1a (#45) done 2026-10-25 night:** `harness/affordances.py` is the one place a `{tool, args}`
  row is written; every `decisions` / `opportunities` row of the briefing carries `actions` (the read as is, then the
  order, `choose` naming the arguments left to pick), the `todo_actions` summary's `actions` are the unit's orders
  themselves, the prose `tools` map stays one release with `tools_note`, `attention.py` walks `actions` rows for any
  tool, `tests/test_affordances.py` plays a fake-bridge turn from the rows alone; seen live at Assyria t238 with reads
  only (an Infantry's and a Worker's summary rows; the briefing has no decisions there). **Stage 1b (#46) done the same
  night:** `harness/rows.py` holds the row shape, every gate carries `actions` (from `gate.rows_for` / `popup_rows`),
  the ten question-shaped reads carry `answers` (attached in the game mixins through `affordances.answered`); seen live
  at t238 with reads only (`gate` null, `faith_great_person_options.answers` three rows, the rest `[]`). **Stage 1c
  (#47) code done the same night:** `harness/affordances/` is a package (`decisions`, `units`, `questions`, `choices`,
  `objects`); every `available_*` reply hands each choice back with `call` (and `buy`), the unit action rows carry
  `call` / `read`, `units()` / `cities()` rows carry `actions`, `city_state_actions` and `trade_catalog` their buttons,
  a paused order its two calls; 28 of 31 affordance replies carry rows (`turn_status`, `city_state_bonuses`,
  `purchase_cost` only inform). Seen live at t238 with reads only. **Open on #47:** the live Assyria turn played from
  rows alone -- it ends a game turn, so it waits for the user's go-ahead; the recipe is `scripts/mcp_session.py`
  (reads from the briefing's rows, orders copied out of the reads' `call` rows, `finish_turn` last), ledger rows to
  `docs/measurements/`. **Stage 2a (#48) done the same night:** `harness/surface/dispatch.py` (the retirement map
  read the other way, the disambiguators, the shape refusal with an example, `answer` on the gate) and
  `harness/mcp_tools/surface.py` (the nine registered beside the 145; `reference` grew a `book`); every new call runs
  the old handler through `_run_tool_here`, replies unchanged; `tests/test_tool_surface.py`. Seen live at Assyria
  t238 with reads only (c8a9a6b): a fresh server lists 153 tools (145 + the eight new; `reference` grew in place),
  `state(what="league")` and `state(what="units")` match `league_status()` / `units()` byte for byte, `turn("status")`
  reads t238 with no gate, `question()` says nothing is pending, `order(to="city", action="produce", id=8192)` is refused
  naming `item` with an example row, `state("options", view="research")` hands back the three techs with their
  `set_research` rows, `reference(book="playbook", section="turn_loop")` serves the playbook. **Stage 2c (#50) done 2026-10-25 (late night):** `harness/surface/forward.py` (the map read forward: `old_name`,
  `new_call`, `renamed`, `example`, `marked`; `ALIASES` folded in from the server) and `harness/surface/schemas.py`
  (the lazy schema leaf); `mcp_server.find_tool` resolves a called name once for the call wrapper, `_run_tool_here`
  and `call`; an unlisted old name or alias runs its handler with `renamed` on the reply, the nine run the handlers
  with `renamed=False`. Seen live at t238 with reads only through fresh stdio servers (`summary`, `status`,
  compact-hidden `league_status` carry `renamed`; `overview` does not). **Stage 2b (#49) code done the same night:** `harness/surface/listing.py` (oneOf / flat `order` schema from the
  vocabulary, the variant per client), set on the listing by a middleware in `harness/mcp_tools/surface.py`;
  `--order-schema` / `CIV5_ORDER_SCHEMA` force one. **Open on #49:** the measurement on the three clients (the
  table in ARCHITECTURE): Claude Code needs a session reconnected to a server on this code (then `ToolSearch` on
  `order` shows what the client holds and a wrong pair shows who refuses it); Codex and the Grok client are the
  user's sessions. **Stage 2d (#51) done 2026-10-26 (afternoon):** `harness/surface/classes.py` holds every
  classification set keyed `(tool, action)` (`Keys` with `*` wildcards; `of_call` from a call's arguments,
  `of_handler` from an old handler's row, `called_as` for the ledger row); the server's six name sets, the
  ledger's `READ_TOOLS` / `WAIT_TOOLS`, `gate.resolutions_by_tool` (now `resolutions_by_key`) and attention's name
  sets are gone; ledger rows carry `tool` / `action` / `called` and the page prints `tool · action`
  (`callLabel`); `--tools compact` is gone and `call` is retired (`mcp_server.retire`, `retired_tools()`; the
  table #52 fills). Seen live the same afternoon at Assyria t238 with reads only after a cold start (Steam, the
  game, tunerd without a table; `load_latest` opened the t238 quick save): 152 names listed, old name and new call
  one ledger key, `call` with the inner `renamed`, a batch refusing `turn(action="finish")`; the alias row's
  `called` fixed from it. The stack was left up: game at t238 (nothing ordered, no turn ended), tunerd on
  `/run/user/1000/civ5-tuner.sock`, the idle Claude Code session server (pid 5315, started before this commit:
  its listing still carries `call` and its ledger rows the old `tool` names until it is restarted). 1671 tests.
  **Stage 2e (#52) done 2026-10-26 (evening):** `@retired` where `@mcp.tool()` stood; the listing is the nine
  (`scripts/mcp_call.py --list` prints 9, seen live), old names answer through the map with the request context
  passed on and strict argument errors, the nine find their handlers by exact name, `--retired-names off` /
  `CIV5_RETIRED_NAMES=off` makes old names unknown (seen live: `units` unknown, `state(what="units")` and
  `turn(action="status")` answer), `tests/test_nine_only.py` is marked `new_vocabulary` and `scripts/check.sh`
  runs the marker a second time with the map off; a list reply in a batch no longer marks it refused. Stage 2 of
  the milestone is complete. The idle Claude Code session server (pid 5315) still lists the 153 of its own start.
  **Stage 3a (#53) done 2026-10-26 (evening):** the instructions (1961 characters) and `docs/PLAYBOOK.md` in
  the nine-tool vocabulary, `harness/surface/table.py` behind `reference(book="playbook", section="orders")`,
  every reply's `hint` / `tool` sentence in the new words, the audit's `named_in` rule, the index's reply
  references by their new call; seen live at Assyria t238 with reads only (the table through a fresh server,
  the index, a refusal's hint). **Stage 3b (#54) done the same evening:** TOOL_REPLIES headings as the new
  calls (either name reaches a section), README's loop in four lines and the nine named, AGENT_INSTALL /
  ARCHITECTURE / LIMITATIONS in the new words, ROADMAP's before / after picture (145 tools, 112 KB -> 9 tools,
  11 KB), `TheWordsTests` reads the five docs. **Stage 3c (#55) done the same night:** every row a reply hands
  back is the new call (`harness/rows.py` renders through the map; `TOP_LEVEL` in the vocabulary), the gate's
  `clear_with` / `read_first` / `why` say the new calls, `InvariantsTests` hold the nine's rules. Standing rule
  from the user (2026-10-26): tests never weigh a refactor; they enforce the design. Stage 3 complete. Next:
  stage 4. **Stage 4 (#56), the harness's half, done the same night:** `play_loop --profile` before / after (72
  trips both), and `scripts/turn_from_rows.py` ended **t238 through the nine alone** (retired names off): the
  Yerevan gift (250 gold, from the city-state read's row) and the turn's end in one call; **the game is now at
  t239**, with its decisions open -- Worker 106504 and Great Merchant 1343522 need orders, Nineveh (16385) and
  Nimrud (24578) have empty queues (their factories done), the Zulu Dye and Siam Salt renewals are due, the UN
  session is at t244; the quick-save slot holds t239 (the finish's autosave), S10 still holds t238. A dry run
  listed t239's rows and ordered nothing: the first production item of a list is UNIT_SETTLER, not a choice for
  the science race. Open on #56: the league vote at t244 and the two fresh sessions (Claude Code reconnected to
  a server on this code, Codex) -- the user's; #47's live turn from rows is this one. Then stage 5 (#57 the
  runtime's strings and its `how` row, #58 release 2.0.0 and the Glama marks); the #49 measurement on the three
  clients folds into the sessions. The audit's "seam" table in the measurement file lists the sites by file and
  line (the briefing's eleven sentences stay until the prose `tools` map goes). Re-run `scripts/tool_survey.py --write`
  after any tool or docstring change (the doc test checks the counts, not the bytes). **Stage 5a (#57) done
  2026-10-26 evening, runtime v286:** the 87 runtime strings that named a retired tool say the new call, the
  city-state gift's `how` row is the new row, a unit action row's `target_tool` is `target_view` (`targets` /
  `home`); `tests/fixtures/runtime_entries.json` pins the 331 entries and 257 seat slots (text-only bump),
  `harness/surface/runtime_audit.py` + `tests/test_runtime_words.py` keep the fragments' strings clean, the
  survey prints the (empty) table. Deployed live at t239 by this session's own first `turn(action="status")`
  (the plain daemon: the client installs; 392 trips once, then 4). **#56's Claude Code half done the same
  evening:** this cleared session played **t239** through the nine as listed (20 calls, 122 trips): the Great
  Merchant's trade mission at Belgrade (+770 gold, Belgrade the tenth ally, 26 delegates now), Nineveh and Nimrud
  on PROCESS_RESEARCH, Worker 106504 automated, Portugal denounced me (answered "Very well."), Shaka's 1 Fur for
  5 Iron refused; **the game is at t240, my turn, nothing blocking** (gold 2890; the UN session is t244 with
  International Space Station and Ban Furs proposed; the Zulu Dye deal ended t239 and is worth re-proposing).
  Found and fixed: four Python reply strings named old tools (`drill_down`, `how_to_answer`, `leader_screen_note`,
  the frozen-game refusal; keys added to `audit.KEYS`), `turn`'s `notes` wording. **Done the same night:** (1) the missing notes were a
  key that changed form (runtime v285 ships the map pattern's backslash intact: `pangaea`, where the inline
  snippet had made it `Assets_Maps_pangaea`); `Notebook.adopt` renames a legacy file once, the live notebook was
  merged by hand (five notes, six assignments, forty orders under `L36-C36-pangaea-Assur-t0-s0-seat0`) and the
  session server reads it; (2) the 26 `err` / `note` sentences say the new calls and `audit.KEYS` holds both keys.
  **The league vote done later the same night (t240-t246 played through the nine):** the t244 UN session's
  votable rows carried no row and the vote's list reached Lua as a string (`_lua_items`, a v285 regression:
  `league.lua:493 bad argument #1 to 'ipairs'`); fixed (the list goes as a list, `affordances/objects.py
  league_rows` on the league read, the audit counts the league as a choice read) and the vote was cast from the
  Furs row through a fresh `scripts/mcp_session.py` server (28 Nay; the ban failed 36-10, the ISS passed), the
  proposal rows at t245 carry their calls and World Ideology: Freedom was proposed from one (session t251;
  `docs/measurements/2026-10-26-assyria-t244-league-vote.md`). The audit now reads every sentence of the source
  (81 more sites fixed, runtime v287 text only). **#56's Codex half done 2026-10-26 late night (stage 4
  complete, #56 closed):** a fresh Codex session on a nine-only server (`CIV5_RETIRED_NAMES=off` in
  `~/.codex/config.toml`, the stale per-tool approvals replaced by the nine) played t247 -- Ur's 500-gold gift
  from its row (49 -> 89, the twelfth ally), ten calls, 77 trips, no refusal
  (`docs/measurements/2026-10-26-assyria-t247-codex-session.md`). Its one report was #49's Codex
  measurement: Codex renders schemas as TypeScript and the `oneOf` became a union of the branches alone, `id` /
  `args` gone; `codex` is in `listing.FLAT_CLIENTS` (clientInfo `codex-mcp-client`) and the flat declaration
  was measured complete through `codex exec`. **The game is at t248, my turn:** the SS Stasis Chamber unit
  stands in Assur (add it to the ship), Assur's queue is empty, Nuclear Fission came free from the Siam RA,
  the Siam open borders end t249 (do not renew), the Portugal Salt-Truffles deal ended t247 (reoffer now, t248);
  happiness 74, twelve allies (Ur since t247), 28 delegates, World Ideology: Freedom on the t251 session.
  **2.0.0 cut the same night** (`v2.0.0`, #58). **Open for the next session:** the Glama re-score (the user
  re-submits https://glama.ai/mcp/servers/ty-meador/civ-v-linux-mcp; the GitHub mirror carries the tag), then
  the four marks next to the 2026-10-04 ones on #59 and in the 2.0.0 changelog entry, and #58 / #59 closed;
  #49 closed 2026-10-27: the Grok row measured from a fresh Grok CLI session at t238 (verbatim passthrough, no
  validation) and Claude Code 2.1.311 measured again (the oneOf rendered as a wrong "exactly one of" sentence;
  shown flat since); `docs/measurements/2026-10-27-assyria-t238-grok-session.md`.
- **A test that can collide with a live game:** `tests/test_assignments.py::McpAssignmentTests::test_the_four_tools`
  failed once on 2026-10-25 night with `another game operation is running (your own load_save, pid ...)` because
  the suite ran while this sandbox's `load_save` held the real per-socket lock; alone it passes (31/31). The MCP
  path takes the lock keyed by the live socket even under a fake game; worth a scratch lock path in that test.
- The rest: `docs/GAPS.md` (§0 for the read gaps, the 2026-10-24 section for the seat-binding design gap).
