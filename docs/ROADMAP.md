# Road to 1.0.0

Reconciled `docs/GAPS.md` §0 against `harness/` at runtime v191 on 2026-09-24 (progress through v201 the same day: 0.2.0 closed, 0.3.0 complete and tagged, 23 of 29 issues closed or declared; open: #23, #29 tracking; #13 and #15 closed live 2026-09-25; #21 closed live and 0.5.0 tagged `v0.5.0` = runtime v206 on 2026-09-25 with #23 left open until a state reproduces it; #23 closed v207 the same day -- the engine freezes its blocker while a popup is up, reproduced by meeting a city-state through a unit's own move; 1.0.0 tagged `v1.0.0` = runtime v207 on 2026-09-25 after a three-turn `play_loop` pass on a clean S1 load): every open item is still open in code (grep-verified; the suite is at 401 passing, not the 391 the doc said). Planned on GitLab: milestones 0.2.0–1.0.0, one issue per gap with the game state that closes it, tracking issue [#29](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/29), board "Road to 1.0.0".

Order is by dependency: boundary first (nothing new may leak), then the trade table (its hotseat war/peace states feed 0.5.0), then the remaining screens, then live verification, then release hygiene. Package version follows the milestone; `RUNTIME_VERSION` keeps its own counter (see #26).

## Game states the plan depends on

| Key | Save | Used for |
|---|---|---|
| S1 | `single/Pocatello_0266 solo-final.Civ5Save` (Shoshone, Emperor, t266) | embassies, World Congress, spies, late-game culture/religion screens, city hovers |
| S2 | `hotseat/Alpha-Bravo_0227 peace.Civ5Save` (Korea vs Austria, Duel, Atomic, at peace) | PvP deals, peace with terms, third-party items, scratch-deal payload reads, greeting popup |
| S2b | `hotseat/Alpha-Bravo_0237 peace-terms.Civ5Save` (Bravo's t237, right after accepting peace + Silk + Salzburg; treaty to t247, deal to t262) | the ceded city's first turns, the peace-with-terms deal rows, a fresh 10-turn forced peace |
| S3 | `single/Pocatello_0266 combat-lab.Civ5Save` (S1 + barbarian Warrior on the hills at 49,18, Archer at 48,18, raider at 47,13 beside a sleeping Worker; Musketman 630799 has Drill I) -- replaces the overwritten t230 hotseat quicksave | modifier rows, captor visibility (fire support is off in stock BNW) |
| S5 | `hotseat/Doge_0215 venice-puppet.Civ5Save` (Venice, one human seat, Wittenberg bought at t215) | puppet purchases (#15) |
| S6 | `hotseat/Shah_0214 golden-age.Civ5Save` (Persia "Shah", one human seat vs England, Duel / Quick / Atomic; 10 golden-age turns granted by Lua, at war with England, two English Warriors beside Infantry 32771 and 40964) | the golden-age combat modifier row (#21) |

Saves live under `~/.local/share/Aspyr/Sid Meier's Civilization 5/Saves/`. Scenario surgery goes through `harness.cli lua`.

## 0.2.0 Information boundary

Nothing new may leak and no read may truncate. Saves: S1 (embassies), S2 (deal payloads via Lua).

| # | Issue | Labels |
|---|---|---|
| [#1](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/1) | ~~Leak: embassy exposes a rival's full technology list~~ closed (v192) | leak, area::tech, needs-game-state |
| [#2](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/2) | ~~Leak: deal rows carry coordinates of unrevealed cities~~ closed (v192) | leak, area::trade, needs-game-state |
| [#3](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/3) | ~~Query chunking budgets characters, not escaped bytes~~ closed (a18f4ea) | transport, bug, area::infra |

## 0.3.0 Trade table

Everything a human can put on, read from, or answer on the trade table. Primary state: the Alpha/Bravo hotseat, re-entering war where needed.

| # | Issue | Labels |
|---|---|---|
| [#4](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/4) | ~~Trade proposals between human seats (PvP deal screen)~~ closed (886fe67, live accept t227 / refuse t228) | parity-write, parity-read, area::trade, needs-game-state |
| [#5](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/5) | ~~Peace with terms (gold, cities, resources) through the real screen~~ closed (v200, live t237: Silk + Salzburg accepted by the other human seat) | parity-write, area::trade, needs-game-state |
| [#6](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/6) | ~~Third-party war/peace items and the Demand button~~ closed (third-party v199 live t234; Demand v202 live S1 t266, Darius refused) | parity-write, parity-read, area::trade, needs-game-state |
| [#7](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/7) | ~~World Congress vote commitments on the trade table~~ closed (v198, live pledge accepted t233) | parity-read, parity-write, area::trade, needs-game-state |
| [#8](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/8) | ~~City population on trade rows and in trade_catalog~~ closed (v192) | parity-read, area::trade |

## 0.4.0 Screens before the decision

The remaining screens and hovers a human reads before deciding.

| # | Issue | Labels |
|---|---|---|
| [#9](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/9) | ~~Coup odds and why the coup button is grey~~ closed (v194) | parity-read, area::espionage, needs-game-state |
| [#10](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/10) | ~~Spy-city potential hover (effective potential, modifiers, catch-spies lines)~~ closed (v194) | parity-read, area::espionage, needs-game-state |
| [#11](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/11) | ~~Religion Overview: automatic faith purchase selection~~ closed (v194) | parity-read, parity-write, area::religion, needs-game-state |
| [#12](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/12) | ~~Culture Overview: great-work swap tab~~ closed (v195) | parity-read, parity-write, area::culture, needs-game-state |
| [#13](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/13) | ~~Change ideology: unhappiness hover, switch cost, and the switch itself~~ closed: read v197; live switch S4 t239 (Bravo's eight concert tours put Alpha in Civil Resistance, Autocracy -> Order with 2 turns of anarchy); the gold hover's anarchy line v204 | parity-read, parity-write, area::culture, needs-game-state |
| [#14](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/14) | ~~City screen: per-yield hover breakdowns~~ closed (v193) | parity-read, area::city |
| [#15](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/15) | ~~Purchases in Venice's puppets~~ closed: catalog v201, live S5 Doge t215 (Wittenberg bought with a Merchant of Venice, Monument purchased in the puppet); v205 localized `producing` and gave Venice the purchase hint instead of "annex first" | parity-read, area::city, needs-game-state |
| [#16](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/16) | ~~Specialist yields on the city screen~~ closed (v193) | parity-read, area::city |
| [#17](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/17) | ~~Help text on buildings the city already owns~~ closed (v193) | parity-read, area::city |
| [#18](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/18) | ~~Stored research on non-current techs~~ closed (v193) | parity-read, area::tech |
| [#19](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/19) | ~~Remembered terrain features under fog (last-seen cache)~~ closed (v196) | parity-read, area::map, needs-game-state |

## 0.5.0 Live verification

Reads with regression coverage only, closed by a live reproduction, plus the open turn-loop defect.

| # | Issue | Labels |
|---|---|---|
| [#20](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/20) | ~~Live: nonzero melee fire support~~ closed as declared limitation: `FIRE_SUPPORT_DISABLED = 1` in stock BNW, engine returns no support unit even with every gate satisfied (S1 t266) | live-verify, area::combat, blocked-engine |
| [#21](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/21) | ~~Live: golden-age and rough-terrain combat modifier rows~~ closed: rough/open terrain and flanking rows live S1 t266; golden-age row live S6 t214 (Persia in a Lua-granted golden age, Infantry vs England's Warriors: "Golden Age Bonus +10", 70 -> 77 strength, row gone with the golden age off) | live-verify, area::combat, needs-game-state |
| [#22](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/22) | ~~Live: captured civilian with a visible captor, and capture by the other human seat~~ closed: barbarian captor S1 t267, Bravo's Infantry as captor S2b t237-238 (v203 fixed the notice-first ordering and the stale roster plot) | live-verify, area::combat, needs-game-state |
| [#23](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/23) | ~~Bug: CityStateGreeting popup leaves ENDTURN_BLOCKING_UNITS with an empty todo~~ closed v207: reproduced live S6 line t215 once the meeting came from a unit's own move (the three `Teams:Meet` attempts never could: the engine rule is that `GetEndTurnBlockingType` is not re-evaluated while a popup is up, so the last ready unit's order plus any announcement popup -- a city-state met on the way, a natural wonder, a plain text box -- leaves UNITS on the books with `HasReadyUnit()` false). `turn_status` now says `blocking_stale` with the true hint, `end_turn` treats the popup as the blocker, and the sweep processes a popup the engine waits on that nothing draws | bug, area::turn-loop |

## 1.0.0 Release

CI, semantic version and tags, CHANGELOG, docs refresh, save library, declared engine limitations.

| # | Issue | Labels |
|---|---|---|
| [#24](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/24) | ~~Engine limitation: path overlay and movement cost~~ declared in `docs/LIMITATIONS.md` (with fire support, lump gold, LOS, forced peace) | blocked-engine, area::map |
| [#25](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/25) | ~~CI: run the regression suite on every push~~ resolved locally: no shared GitLab runner minutes for this project, so `scripts/check.sh` (locked `dev` group + pytest) is the pre-push check and `.gitlab-ci.yml` was removed 2026-09-25 | release, area::infra |
| [#26](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/26) | Versioning: semantic version, tags, CHANGELOG, runtime-version mapping -- `CHANGELOG.md` added with the two-counter rule and the runtime map; tags `v0.3.0` (runtime v202), `v0.5.0` (runtime v206) and `v1.0.0` (runtime v207) | release, area::infra |
| [#27](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/27) | Docs: README/ARCHITECTURE refreshed 2026-09-25; declared limitations split out to `docs/LIMITATIONS.md`, GAPS.md kept as the audit log | release |
| [#28](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/28) | ~~Save library for the reproduction states~~ `saves/` holds S1, S2, S2a, S2v, S2b, S3, S4, S5, S6 with a README | release, needs-game-state |
| [#29](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/29) | ~~Road to 1.0.0 (tracking)~~ every row above closed or declared; `v1.0.0` tagged 2026-09-25 (runtime v207, 495 tests) | release |

## After 1.0.0

Everything a model needs to play a turn as one call, then whatever a live game shows is still slow or
unseen. The 0.3.0-1.0.0 milestones were closed on 2026-09-26; the post-1.1 plan is below.

| Version | Item | State |
|---|---|---|
| 1.1.0 | `finish_turn` (end_turn + wait + digest, `skip_quiet_turns`), MCP progress every 5 s, notebook `remember`/`recall`/`forget`, `do` batches, `action_id` replay, `set_seat`, `exit_to_main_menu`, finish_turn default 600 s | tagged `v1.1.0` 2026-09-25 (runtime v212) |
| 1.2.0 | `gate`, the rule book, `todo_actions`, one-query screen reads, turn claim (#41), notebook replace guard (#40), `alerts` (#39), `todo.ongoing` (#37), `expiring_deals` / `expiring_friendships` (#38) | tagged `v1.2.0` 2026-09-26 (runtime v219); see the ranked table below |
| 1.3.0 | `todo_actions(detail="summary")` (#35), `briefing` and `finish_turn(briefing=true)` (#30), `tactical_view` (#31) | tagged `v1.3.0` 2026-09-26 (runtime v223); see the ranked table below |
| 1.4.0 | structured assignments (#33), `compare` (#34) | tagged `v1.4.0` 2026-09-27 (runtime v225); see the ranked table below |
| next | ~~Legal actions for many units in one read~~ `todo_actions` (runtime v213, live S1 t270: 38 units in one 0.5 s query). The per-unit read turned out to cost 0.37 s, so the ~15 min a late `play_loop.py` turn takes is not this; where it goes is unmeasured | closed |
| next | ~~Where a late-game `scripts/play_loop.py` turn spends its time~~ timed with `play_loop.py --profile` (runtime v214): S1 t270 took 97 s, not 15 min, and 250 of its 278 tuner trips were popup-screen reads (`turn_state` 8 trips, the sweep ~20, both on every wait poll). `H.modal_flags` reads every screen in one query; `turn_state` is 1 trip, `end_turn` 8 (was 93) | closed |
| next | ~~`unit_mission` trips: a plain order is 2 (order + `unit_pos`), a refused one 3; the automate path's confirmation poll (up to 12 x 0.25 s `automate_check`)~~ measured live t151 with an in-process trace of every query: the gate's `discussion_pending()` was a second trip on every mutating call (`H.turn_state` carries the flag since v214; the gate now reads it), a `do` batch reads every unit order back in one query at its end (`after_pending` markers), and the fixed 0.2-0.25 s waits before the first read are 50 ms (an order lands on the next frame). Lone order 6 -> 5 ledger trips (0.30 -> 0.21 s), two-order batch 10 -> 7 (0.50 -> 0.31 s). A refused order still explains itself with two more reads | closed (unreleased) |
| later | LAN mode since 0.5.0 and `declare_war` on a city-state syncing over LAN (`docs/LIMITATIONS.md`) | needs a LAN game |
| later | ~~Game over: `turn_status.game_over` against a stale PRODUCTION blocker, seen once at t457, no regression state~~ seen a second time at t502 (S7 `Wu Zetian_0502 science-victory-eve` is the state one call before the win; the blocker froze at UNITS this time); `spaceship_status.complete` and the completing mission's `game_over` / `victory` fields shipped in 1.9.0 | closed |

## 1.2.0-1.6.0: LLM play usability

Ranked 2026-09-26 from the 2026-09-26 hotseat play review (tracking issue
[#36](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/36), which carries the reasoning). One
GitLab milestone per group; the issue board's Manual sort follows the rank. Do the work in this order:
small fixes found in live play first, then the shared compact-response controls, then the reads built on
them, then persistent intent, then the orders that depend on it.

| Rank | Issue | Milestone | Depends on |
|---|---|---|---|
| 1 | [#40](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/40) `remember(replace_id)` refuses a different tag, returns the previous text | 1.2.0 Turn status tells the whole turn | -- |
| 2 | [#41](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/41) One client claims a seat's turn | 1.2.0 | -- |
| 3 | [#39](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/39) Happiness and strategic-deficit alerts on `turn_status` | 1.2.0 | -- |
| 4 | [#37](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/37) Automated units and standing-move destinations on the checklist | 1.2.0 | -- |
| 5 | [#38](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/38) Expiring deals and declarations of friendship | 1.2.0 | -- |
| 6 | [#35](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/35) Compact response modes with drill-down (record the baseline first) | 1.3.0 Compact briefing and tactical view | -- |
| 7 | [#30](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/30) Compact turn briefing | 1.3.0 | #35, #37-#39 |
| 8 | [#31](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/31) Unit-centered tactical view | 1.3.0 | #35; no #24 probes |
| 9 | [#33](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/33) Structured assignments on the notebook | 1.4.0 Plans that survive a context reset | #40, #30 |
| 10 | [#34](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/34) Compact comparisons for production, improvements, research, trade | 1.4.0 | #35 |
| 11 | [#42](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/42) Split the runtime file (tech debt, ahead of the rest of 1.5.0) | 1.6.0 Runtime split | -- |
| 12 | [#32](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/32) Conditional unit orders | 1.5.0 | #33, #30, #41; lands in `movement.lua` / `turn.lua` |
| 13 | [#36](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/36) Tracking | 1.5.0 | all of the above |
| 14 | [#43](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/43) The size of the `finish_turn` reply: notes ride once, threats compact and `seen`, orders not twice | 1.7.0 | #36 |

1.2.0 also ships the runtime v215 (`gate`) and v216 (rule book) work. Its five issues are closed and one
live hotseat turn (t42, both seats) showed the new status fields: tagged `v1.2.0` 2026-09-26 (runtime v219,
840 tests). 1.3.0 so far: #35 `todo_actions(detail="summary")` (runtime v220) and #30 the `briefing` tool and
`finish_turn(briefing=true)` (runtime v221, 873 tests), both checked live on Venice t42 and S1 t266-t267;
#31 the `tactical_view` tool (runtime v222, 885 tests), checked live on Venice t42. With those three the
milestone's issues are done. Checked together on one live hotseat turn (t42) and tagged `v1.3.0` 2026-09-26
(runtime v223: the tactical grid now stops at `radius`, 886 tests). Next: milestone 1.4.0, #33 then #34.
1.4.0 so far: #33 structured assignments (runtime v224, 913 tests), checked live read-only on Venice t42; a
real unit loss and upgrade were not played out live (tests cover both). #34 compact comparisons (runtime v225,
931 tests), checked live on Venice t42, S5 t215 (the Venice puppet) and S1 t266 (trade, through an AI
caravan: seat 0's four were all on routes). With those two the milestone's issues are done. Used together on one live hotseat turn (t42) and tagged
`v1.4.0` 2026-09-27 (runtime v225, 931 tests). 1.5.0: #32 conditional unit orders (runtime v226-v227, 970
tests), checked live t42-t48 on the Venice/Mongolia hotseat; #36 closed with a measured turn loop (t48-t51 played
twice: 8.0 -> 4.25 calls a turn, two refusals -> none, bytes level; `docs/NOTES.md`). Tagged `v1.5.0` 2026-09-27
(runtime v227, 983 tests). 1.6.0: #42 the runtime split (runtime v241-v242, 1000 tests): one Lua file per domain under
`harness/lua/runtime/`, each its own named chunk, loaded in `harness/runtime_source.py` order; checked live on the
Venice/Mongolia hotseat t52-t53 (inject over v227, reads, one `set_research`, forced reload, a hand-off both ways).
Tagged `v1.6.0` 2026-09-27 (runtime v242, 1000 tests). 1.7.0: #43 the size of the `finish_turn` reply (1058 tests, no runtime change): measured by replaying the #36 replies through the new composer and by playing the same t48-t51 save live again, 26% off the wait reply, a third on turns with open orders (`docs/NOTES.md`). Tagged `v1.7.0` 2026-09-27 (runtime v242, 1058 tests). 1.8.0 (no issue; the day's work after the milestones): the
MCP server in one core plus a tool module per domain, `how_to_play(topic)` with the instructions and descriptions
under the client's 2000-character cut, gates that name the right tool, runtime v244-v252 (civilian one-per-tile,
the wait gate's AI round, `territory`, permanent deals, `todo.policy`, the trade-unit cap and stable
caravan-route rows), `remove_from_queue`, `scripts/hotseat_rounds.py`, and an install that needs neither
gcc nor uv (Steam Deck). Tagged `v1.8.0` 2026-09-27 (runtime v252, 144 tools, 1136 tests). 1.9.0 (no issue): a
unit order one trip cheaper and a `do` batch one per order (measured live t151), and the science-victory end state
(live t502, S7 saved). Tagged `v1.9.0` 2026-09-29 (runtime v252, 144 tools, 1158 tests). 1.10.0 (no issue): the live visualization
(`harness/spectator`, `web/viz`, the ledger's attention fields), checked on the Pocatello solo save and one
Venice/Mongolia hotseat round (t150-t152); `set_production` by button name. Tagged `v1.10.0` 2026-09-30 (runtime
v252, 144 tools, 1200 tests). 1.11.0 (no issue): a seat view that draws only what that seat's screen shows,
a spectator snapshot read when the world moves and pushed when it changed (72 MB -> 532 KB for a hotseat
round), and runtime v253, the trade unit's second gate (`CanTrain` per city and kind with the engine's own
sentence), all checked on the Venice/Mongolia hotseat at t152-t153. Tagged `v1.11.0` 2026-10-01 (runtime v253,
144 tools, 1208 tests). 1.12.0 (no issue): a turn's closing orders and its end are one
call (`finish_turn(actions=[...])`, a move's `revealed`, `--tools compact` with `call`), a call ledger that
names the client behind each row and a turn claim that recognises its own client, refusals that say what to
do instead (`did_you_mean` and the unit's legal missions, the sleep/fortify equivalent, `skip_actions` for
leftover movement, the engine's sentence on a greyed button, a purchase, peace, a ranged attack), runtime
v254-v263 (a seat's digest at the hand-off, ranged strength, tactical_view sized to sight, free tenets,
deal givers and renewals), all checked on the Venice/Mongolia hotseat at t153-t256 and Codex's 73 turns as
Portugal. Tagged `v1.12.0` 2026-10-04 (runtime v263, 145 tools, 1430 tests). 1.13.0 (no issue): the spectator's
scrubber (play/pause, speed, a slider with turn ticks, `/recording`), a turn that arrives before its first order
when no wait of ours opened it, a tuner stream that resyncs after a timed-out command, a finished game as the
wait's answer with the winner, and what a human sees in a siege -- `wars` with the Negotiate Peace gate and the
briefing's `at_war` rows, a leader screen outranking "turn not active" in the gate, `unit_displaced` for a unit
the engine moved, the league's special session, `occupied` frontier plots (runtime v264-v266), found and checked
on Codex's Portugal game (t83-t95) and Grok's abandoned England game, played from t118 to t133. Tagged
`v1.13.0` 2026-10-08 (runtime v266, 145 tools, 1469 tests). 1.14.0 (no issue): the spectator map moved from SVG
to a canvas (`docs/CANVAS_MIGRATION.md`: the plan, the SVG baseline, the side-by-side on synthetic maps up to
200x120 and on two real recordings; on the frame everywhere the SVG spent 44-148 ms a frame), with
`scripts/viz_bench.mjs` to re-measure through the DevTools protocol; the spectator dumps the map again when a
snapshot's `map_key` changes, a seek applies the latest snapshot before its target, the `civ5://playbook`
resource reads the shipped playbook, and two tech-debt sweeps (dead code out, seven more ruff rules, the slow
tests' sleeps patched, the 2026-09-19 coverage audit marked historical with its closure table; runtime v267).
Tagged `v1.14.0` 2026-10-09 (runtime v267, 145 tools, 1475 tests). 1.15.0 (no issue): five fixes found playing
Grok's England game from t133 to t214 -- `explore_frontier` keeps the held plots within the cut and names a
foreign city on a frontier plot (runtime v268); a melee attack the engine drops is reported as a refused attack
naming the first closed gate (the t200 rule itself still needs a war); a turn that began while a leader screen
was being answered is handed back unended (`unseen_turn`); `compare(kind="production")` reads a queued building
as queued, not refused (runtime v269); and `upgrade_unit` carries the assignments and the open order onto the
new id (`carried_over`). Tagged `v1.15.0` 2026-10-10 (runtime v269, 145 tools, 1495 tests). 1.16.0 (no issue):
twenty-eight fixes from the end of Grok's England game (t214-t226) and a solo Assyria game played from its first
turn to t208 -- a quiet run stays quiet on what decides nothing for this seat (other players' wars, alliances,
denouncements and quests, a swept splash, a leader's plain remark, a happiness dip inside the comfortable band;
one wake per expiring deal); a refusal names its rule (the Buildings table's location, resource and policy-branch
columns, an ideology tenet's level gate, a Prophet that has spent a spread, a closed border's rival-territory
flag, `did_you_mean` for a policy name); a unit our own order used up is `unit_spent` with the reason and a
plundered caravan says so; the briefing names the plots a neighbour took, a repair step completes when the plot
is mended, the Ottoman war's four reads (narration carry-over, the swap refusal, the open-borders embassy note,
a note-only amend), a defeat read with the last city, and a new game's first turns (runtime v270-v283). Tagged
`v1.16.0` 2026-10-24 (runtime v283, 145 tools, 1548 tests). 2.0.0 (milestone 11, #44-#58, "The tool surface" below):
nine tools -- `turn`, `state`, `order`, `question`, `answer`, `notebook`, `batch`, `session`, `reference` --
where 145 were, every old name answering through the retirement map with `renamed`, every reply that lists what
can be done carrying the order to copy, the words and the runtime strings in the new vocabulary, the live checks
from fresh Claude Code and Codex sessions. Tagged `v2.0.0` 2026-10-26 (runtime v287, 9 tools, 1694 tests). 2.1.0: the listing as a judge reads it -- MCP
annotations, a description on every parameter, purpose and reply shape in every description, one flat `order`
schema (the `oneOf` and its per-client variants removed after the three-client measurement), the Grok row of #49;
TDQS 3.4 B -> 4.6 A. Tagged `v2.1.0` 2026-10-28 (runtime v287, 9 tools, 1706 tests). 2.2.0 (milestone 16, seventeen
issues from the 2026-10-27/28 play sessions): nothing stalls, crashes or leaks -- the splash and the Long Count no
longer stop a turn, the swap row is gone, the Random map's script stays hidden, a vote call commits once and
refuses what cannot count, standing moves hold beside an enemy, a queue never loses an item silently, a note
remembers its unit ids. Tagged `v2.2.0` 2026-10-29 (runtime v296, 9 tools, 1846 tests). 2.3.0 (milestone 17,
twenty-one issues): reads tell the truth -- the combat preview says what its strengths are, a refused build or
policy names the engine's rule, the own plot is in sight, city rows say whose city an id is, a wait and a move
carry what happened, grids keep their columns, the index keeps a seen wonder, the embassy flags point the right
way, delegate counts and purchase refusals follow the engine, the gate carries a screen's own buttons. Tagged
`v2.3.0` 2026-10-29 (runtime v305, 9 tools, 1871 tests). 2.4.0 (milestone 18, twelve issues): every decision is a
row -- a worker's remote build, a move with its plot to choose, "go there and hold", a starving city, a city strike,
religion founding and beliefs, a Great Person on a stacked tile, a caravan's route and refusal, a merchant's trade
mission, a negotiation, religious defense. Tagged `v2.4.0` 2026-10-29 (runtime v310, 9 tools, 1911 tests). 2.5.0
(milestone 19, eight issues): late game and strategy reads -- a spaceship part as a decision, a kept standing move,
the wonders still open, the culture estimate and warning, trade routes sorted and measured, a league project's
tiers, a Settler's sites. Tagged `v2.5.0` 2026-10-29 (runtime v313, 9 tools, 1923 tests). 2.6.0 (milestone 20, eleven issues): quiet turns
that stay quiet, a gold-per-turn drop with its cause, automation that ended, an alliance cascade as one row, a lean
city-state read, the seat's other servers and a server behind main, the small reply gaps of five play sessions. Tagged
`v2.6.0` 2026-10-29 (runtime v316, 9 tools, 1950 tests). 2.6.1 (#137): the leader view an exit to the main menu left
open no longer disables the next loaded game's End Turn. Tagged `v2.6.1` 2026-10-29 (runtime v317, 9 tools, 1956
tests). 2.7.0 (#138): `inspect` is `state`, nine nouns, the old name retired with `renamed`. Tagged `v2.7.0` 2026-10-29
(runtime v318, 9 tools, 1963 tests). 2.7.1 (#139): the four descriptions Glama's TDQS marked under 4.5 (`turn` 3.6)
restructured; hosted TDQS 4.7 A with every tool 4.6 or better. Tagged `v2.7.1` 2026-10-29 (runtime v318, 9 tools, 1963
tests). The 2026-10-29 play sessions (Maya t203-t237 #149 by Claude Code; the two-agent hotseat, Codex seat 0 #157 and
Grok seat 1 #150) filed 24 issues, planned 2026-10-30 as three milestones in this order:
[2.8.0 Hotseat: nothing stalls or leaks](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/milestones/17) (nine: the
unreadable human deal #161 first, the two leaks #151 #154 (#162 closed as parity: the stock trade screen shows the
other side's available gold), lost notes #159, the startup race #158, the paused
order #143, the greeting-close wait #155, the order during the AI turn #147);
[2.9.0 Reads and schemas tell the truth](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/milestones/18) (eight: stale
melee hp #156, the dig's state #140, false production_dropped #141, the build turn count #165, the two schema
mismatches #163 #164, the notebook contract #166, refusals naming retired calls #146);
[2.10.0 Decisions explained, lean replies](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/milestones/19) (seven:
Great People missions #142, the ideology read #145, the deal-window wakes #144, the three-call handoff #160, the
repeated legend #152, the ruins plot dump #153, small gaps #148). Each milestone's description carries the order and
its done-when line; #139 closed as shipped in 2.7.1. **2.8.0 shipped 2026-10-30**, the nine in order: #161 (a human
seat's proposal is a question without a screen beside the #95 blockers; seen live both ways at t38-t39 on S11), #151 (no
public opinion before an ideology: the stock screens' own rule), #154 (a greeting read is the greeting), #162 (parity),
#159 (the notebook follows the seat through the founding of its capital), #158 (the main menu is the no_game gate for
every tool), #143 (a destination pause skips the unit and retries by itself; a direct order replaces a paused order),
#155 (the AIs-moving hint rests on a read after the close), #147 (the first reply to meet a turn carries its digest);
and `leave` cancels a bare trade table. Tagged `v2.8.0` 2026-10-30 (runtime v320, 9 tools, 1978 tests). **2.9.0 shipped
2026-10-30**, the eight in order: #156 (the melee block reads the blow: defender.hp after it, damage_dealt / taken, the
roll note; seen live on S3), #140 (the dig's state from the plot, the order closed complete when the dig consumes the
Archaeologist, dig_choice in the todo and the briefing, the find and its Great Work on the answer, dig_sites on the
actions; seen live on the t237 Maya save through the Doubloon in Palenque's Museum), #141 (a unit that completed is not
production_dropped), #165 (one build turn count, the unit panel's; seen live at t39), #163 and #164 (the state schema
says which view takes x, y, radius and id), #166 (the notebook's contract is what give_order does), #146 (refusals
accept the 2.x call, the produce refusal carries the engine's reason, the price read says can_build). Tagged `v2.9.0`
2026-10-30 (runtime v322, 9 tools, 2001 tests). **2.10.0 shipped 2026-10-30**, the seven in order: #142 (a Great
Person's withheld missions are `missing` rows with why -- the slot census, the nearest qualifying plot, no moves; the
gift row names its city-state; the concert tour's reply says the tourism and the receiver; seen live on the t237 Maya
save with spawned Great People), #145 (the ideology choice in one read; seen live at t237), #144 (one wake per expiring
deal, the happiness baseline in the notebook), #160 (a timed-out wait is a resumable `next`), #152 (the tactical legend
once), #153 (a move's revealed as notable rows, not a plot dump), #148 (the small gaps: lean league choices, the vote
echo, counted third-party peace rows, icon words, the fogged city, the league project notice, `refused`, the remark's
owner, one route-end row; seen live at t237). Tagged `v2.10.0` 2026-10-30 (runtime v328, 9 tools, 2039 tests). Next:
the three tracking issues (#149, #150, #157) hold what the 2026-10-29 sessions found; a new play session files the next
milestone.

The three-seat hotseat of 2026-10-30 (Codex seat 0 #167, Grok seat 1 #173, Claude seat 2) filed 13 issues, planned the
same night as three milestones: [2.11.0 Hotseat: deals and notebooks belong to one seat and one game](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/milestones/20)
(the notebook collision #168 first, the unreadable human deal #174 and its other side #172, friendship with a human
seat #175); [2.12.0 Orders report what they did](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/milestones/21) (the completed order counted open #181, the remote
build pausing its own order #182, the fortify reply #176, the ruins successor #169); [2.13.0 Reads before the order](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/milestones/22)
(the step cost #180, the locked ideology text #179, the belief order row #178, the city under its unit #177, the
stale playbook examples #171). **All three shipped 2026-10-31**, each issue one commit with a regression test: the
notebook keyed by a per-game identity (9cc36ec, runtime v330), the shared scratch trade table read seat-aware
(50675bf, v331), a human seat asked on the trade table (8b10ac9, v332; tagged `v2.11.0` after the fact, 2070 tests);
orders counted after they run and a command never pausing the order it creates (90edcba), the `hold` block and the
ruins successor (6c7b76f, v333; tagged `v2.12.0` after the fact, 2094 tests); step_cost.lua porting the engine's
movement rules and the city as the cell's ground (e9241f9, v334), locked ideologies as names, belief rows with their
order, every served playbook example checked by a test (343af86, v335). Tagged `v2.13.0` 2026-10-31 (runtime v335,
9 tools, 2114 tests). None of it seen live yet: docs/SESSION_HANDOFF.md lists the read-backs for the next session.

## A seat bound to its channel (fair play by mechanism)

Raised 2026-10-24 (`docs/GAPS.md`, "The seat is bound to the agent's own process"). Today a `--seat N` server
refuses `set_seat` onto the other human seat, and nothing else stands between one agent and the other's map:
tunerd forwards any Lua for any caller, a second server, `scripts/mcp_call.py --seat N` or `harness.cli lua`
reach the same socket, and two agents on one machine are one user. The guard catches a mistake, not intent.
The fix moves the seat binding to tunerd, the one process every path already crosses, and makes the per-seat
Lua something the daemon writes rather than something the caller sends.

Needs a two-agent hotseat game to check live (the Venice/Mongolia and Codex/Grok shapes; a solo game shows
only that nothing changed). Opt-in throughout: a daemon with no seat table is today's daemon.

| Stage | Work | Done when |
|---|---|---|
| 1 | tunerd learns seats: `--seats <file>` (token-to-seat, or uid-to-seat for `SO_PEERCRED`); a connection's first message binds it or it is refused; `states` / `events` / `ping` stay open, `exec` / `query` need a binding | a raw client with no token is refused on a daemon with a table; the same client works on a daemon without one. **Done 2026-10-24** (`harness/tunerd.py` `SeatTable` / `gate`, `harness/client.py` sends `CIV5_TUNERD_TOKEN` as the first message of every connection, `harness/tunerd-seats.example.json`; 21 tests, and the real daemon checked on a scratch socket with no game). Both identities at once: a token in a first `hello` *and* the peer uid, the table in a file (`--seats`, `CIV5_TUNERD_SEATS`); a uid-bound connection takes only its own seat's token. Not yet seen from a second agent's sandbox in a live hotseat (stage 4's check). |
| 2 | survey `harness/lua/runtime/*.lua`: every `H.*` read and write takes the acting seat as its own argument and never a caller-chosen player id in that role; list the Python call sites that compose Lua ad hoc (`game.py`, `game_parts/*`) | the survey is a table in `docs/GAPS.md` with the exceptions named. **Done 2026-10-25** (`scripts/seat_survey.py`; GAPS "Stage 2, the survey"): 207 of 263 entries carry `pid` (90 first, 102 last, 15 in the middle, so the slot is per entry, not positional); the exceptions reached from Python are `H.diplo_event` (a write as the active team), `H.plot_units` and `H.plots_around` (a caller-chosen team); every `Game` method resolves `pid=None` to `Game.seat`, the one attribute stage 3 replaces; 137 ad-hoc Lua bodies in Python: 49 front end, 40 screen buttons and probes, 48 `InGame` bodies to fold into named entries. |
| 3 | `{"op": "call", "fn": "H.<name>", "args": [...]}`: tunerd writes `H.<name>(<bound seat>, ...)` itself; the server's `Game.q` / `Game.lua` take that path on a bound connection and free Lua text is refused there; the ad-hoc call sites move into named runtime entries | the server plays a full turn loop through `call` only (fake-bridge tests and one live turn). **Done 2026-10-25** (runtime v285; `harness/lua_wire.py`, `dispatch.lua` with `H._seat_slot` generated at build, `Game.h` / `Game.hs`, tunerd `call` and `runtime` ops, `tests/test_seat_call.py`, 32 tests): every `InGame` read and write of the Python side is a named entry, the daemon installs the runtime itself, and a bound connection's Lua text is refused for `InGame` and forwarded to a screen state only while its seat is active. Seen live the same evening (Assyria t238, cold start): on a daemon without a table every read of a turn (`turn_status`, `units`, `cities`, `todo_actions`, `briefing`, `overview`, `league_status`, `trade_routes`, ...) came through `call`; on a daemon with a one-seat token table a tokened session read the same and its `generic_popup` screen read passed as the active seat, an untokened session was refused unbound, and a tokened `harness.cli lua` to `InGame` was refused with the named-calls hint. No turn was ended (the user's campaign); the live *turn* through `call` is the next session's first `finish_turn`. |
| 4 | the escape hatches connect like any client: `harness.cli lua`, `--allow-lua`, `scripts/mcp_call.py`, `scripts/mcp_session.py`; no bypass flag on a daemon with a table | from seat 0's sandbox, `mcp_call.py --seat 1 overview` and `cli lua` are refused at the daemon, live. **Done 2026-10-25** (`Game.bound_seat`; `tests/test_seat_escape_hatches.py`, 9 tests): a server whose connection is bound plays the binding and nothing else. A different `--seat` (what `scripts/mcp_call.py` and `scripts/mcp_session.py` pass as `CIV5_SEAT`) is refused on every tool, naming the binding and the fix, instead of being overridden in silence; `set_seat` onto another seat is refused with `bound` and `set_seat()` lands on the binding without asking the engine; `detect_seat` returns the binding; the raw `lua` tool (`--allow-lua`) refuses before any trip; and the harness client without a token is unbound, so there is no flag to bypass. Seen live at Assyria t238 from this sandbox on a one-seat token table: `mcp_call.py --seat 1 overview` refused, `set_seat(1)` refused, `set_seat()` -> seat 0, `turn_status` as seat 0 fine, the `lua` tool refused, a tokened `cli lua` refused at the daemon, an untokened `mcp_call.py` and `cli lua` refused unbound; tunerd was restored without a table. Still to see: the same refusals from a *second* agent's sandbox in a two-agent hotseat (stage 5). |
| 5 | the two-agent recipe: one sandbox or OS user per agent holding its token, `docs/AGENT_INSTALL.md` (Codex registered with `--seat auto` for solo play, a pinned seat and a token for a shared hotseat, the reason stated once for every client), `docs/PLAYBOOK.md`, one README "Fair play" sentence, `docs/LIMITATIONS.md` on the shared display and the save files | a two-agent hotseat played a few turns on bound sockets with the usual loop unchanged. The words are written (2026-10-25: `docs/AGENT_INSTALL.md` "Two agents, one game", `docs/PLAYBOOK.md`, README "Fair play", `docs/LIMITATIONS.md` on the shared display and the save files). **Done 2026-10-25** (seen live the same night): the Alpha/Bravo hotseat (S2a, t229, loaded on a plain daemon after the Assyria game was quick-saved as `Ashurbanipal_0238 pre-stage5`) on a two-seat token table, one process per seat holding only its own token in its environment (`scripts/play_loop.py --seat N`, the `Game` object bound through the one client; the two processes were one OS user on one machine, so the token secrecy was organisational, as the words say it must be): the usual loop unchanged, blockers resolved, a Settler queued, two promotions, seat 0 ended t229-t231 and seat 1 t229-t230 in under a minute (the AI round between humans is short in this game), the tunerd log shows only `connection bound to seat N by token` and no refusal, and every turn end went through `call` on a bound daemon (the live turn through `call` stage 3 left open). From each agent's own process the eight escape-hatch probes landed as stage 4 says: a wrong pinned `--seat` refused naming the binding and the fix, `set_seat` onto the other seat refused with `bound`, `set_seat()` and `--seat auto` on the binding, `cli lua` to `InGame` refused with the named-calls hint, an untokened client refused unbound, the own seat's reads fine, and a seat's `units` read while the other seat is on screen answers `this seat is not active`. Saved as `Alpha-Bravo_0231 two-agents-bound`; the Assyria game reloaded after, tunerd restored without a table. |

Decisions taken in the first stage (2026-10-24): both identities, since they cost the same code -- a token in
a first `hello` (works across users and machines, needs a secret per sandbox) and the peer uid (nothing to
remember, needs one user per agent); the seat table is a file (a token on a command line is in every `ps`).
The token never appears in a tool reply, a refusal, the daemon's log, the call ledger or the spectator (the
no-other-seat-metadata rule holds for it too); the daemon warns when the table file is readable by others.
What stage 1 does not do: scope the Lua. A bound connection still sends free text and tunerd still forwards
it; the binding is only *known* at the daemon (`Bridge.handle(req, seat=...)`) until stage 3 uses it.

## The tool surface (model the game, not its buttons)

Raised 2026-10-25 by the Glama listing's marks (completeness 5/5, naming 4/5, disambiguation 3/5, tool
count 1/5: 145 tools against a rubric that wants 3 to 15). Tracking issue #59 holds the model: a game
is a clock, a world of objects each carrying the actions the engine allows right now, the questions the
game asks, my notebook and the session, so the surface is nine tools -- `turn`, `state(what, id, view)`,
`order(to, id, action, args)`, `question`, `answer`, `notebook`, `batch`, `session`, `reference` -- and
every reply that lists what can be done hands back the `order` / `answer` row itself instead of a prose
hint. A new feature is a new view or action, never a new tool. Every one of the 145 names stays callable
through a retirement map (checked by script: each maps to exactly one row). Python and docs only; the Lua
runtime does not move except for one text-only bump at the end. A first draft that folded families into
enums (ac28a1b, 87 tools plus a hidden tier) was dropped the same day as still modelling the interface.
Planned on GitLab 2026-10-25: milestone [2.0.0 The tool surface](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/milestones/11), tracking issue [#59](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/59), one issue per item: stage 0 #44; stage 1 #45 (todo rows), #46 (question-shaped reads and the gate's rows), #47 (`available_*`, object reads, the live turn from rows); stage 2 #48 (`harness/surface.py`), #49 (`oneOf` on three clients), #50 (the retirement map), #51 (gate, ledger, tool sets, spectator), #52 (unregister the 145); stage 3 #53 (instructions and playbook), #54 (the other docs), #55 (`tests/test_tool_surface.py`); stage 4 #56 (the two live sessions); stage 5 #57 (the runtime strings), #58 (release 2.0.0 and the Glama marks). Work proceeds from the issues, in that order; this table is the summary. The plan document (`docs/TOOL_SURFACE.md`) was folded into the issues the same day and deleted: #59 carries the model, the vocabulary, the touch list and the risks, #50 the mapping table from each old name, #44 the baseline count, #48 the action and view tables; the issues are linked in dependency order.

**Before and after** (both from `scripts/tool_survey.py`, under `docs/measurements/`): the 1.16.0 listing was 145
tools, 112 KB and ~28k tokens on every request of a client that does not defer tool schemas (`--tools compact`
33 KB); since stage 2e the listing is 9 tools, 11 KB and ~2.8k tokens, and the 145 old names answer through the
retirement map with `renamed` on the reply.

| Stage | Work | Done when |
|---|---|---|
| 0 | `scripts/tool_survey.py`: catalog by module, listing size, every name's row in the mapping, the affordance audit (which replies carry `{tool, args}` rows, which carry prose) | its tables reproduce the baseline on #44, under `docs/measurements/`. **Done 2026-10-25** (`harness/surface/`: `vocabulary.py` the nine tools' words, `retirement.py` the 145-row map with argument renames, `survey.py` the counts and the listing's size, `audit.py` the affordance scan; `scripts/tool_survey.py --write` -> `docs/measurements/tool_survey.md`; `tests/test_tool_survey.py`): 145 tools / 35 zero-argument reads by module and the eight shapes reproduce #44 exactly, every name maps to one row and none is left over, the full listing is 110 KB (~27.6k tokens at bytes/4) and `--tools compact` 33 KB, the seam is 77 sites (the briefing's 11 todo sentences, the gate's 41 bare names, 25 refusal hints naming a tool), and of the 31 replies that list what can be done only `todo_actions` carries a `{tool, args}` row today. |
| 1 | affordances as data in today's vocabulary: todo rows, popup / discussion reads and every `available_*` reply carry `actions: [{tool, args}]`; `attention.py` reads only rows | a fake-bridge turn and one live Assyria turn play from affordance rows alone. **1a done 2026-10-25** (#45; `harness/affordances.py` is the one place a row is written: every `decisions` / `opportunities` row of `briefing` and `finish_turn(briefing=true)` carries `actions` -- the read as is, then the order, `choose` naming the arguments left to pick -- and the `todo_actions` summary's `actions` are the unit's orders themselves (one row per non-routine action, melee target, ranged target, promotion; a targeted mission as its targets read then the order); the prose `tools` map stays one release with `tools_note`; `attention.py` walks `actions` rows for any tool; the audit counts a reply calling into the module as rows (`briefing`, `finish_turn`, `todo_actions`); `tests/test_affordances.py` plays a fake-bridge turn from the rows alone and checks its own source types no tool name but `do`; seen live at Assyria t238: an Infantry's and a Worker's summary rows, the empty t238 briefing). **1b done 2026-10-25** (#46; `harness/rows.py` is the leaf that holds the row shape, `harness/gate.py` owns its rows: every gate carries `actions` -- the read, the call that clears it with its `args` and the arguments left to `choose`, the alternatives -- and a decision popup's rows come from the one resolution table (`popup_rows`: the read with the arguments the popup fixes, such as `available_beliefs(kind=...)`, the resolver, the `also` resolvers; the promotion popup reads `todo_actions` now, not `available_unit_actions` with a unit_id it cannot know); the ten question-shaped reads (`generic_popup`, `discussion`, `incoming_deal`, `goody_hut_options`, `maya_options`, `city_capture_options`, `steal_tech_options`, `free_great_person_options`, `faith_great_person_options`, `archaeology_options`) carry `answers`, one complete row per button or choice, attached in the game mixins so every caller sees them; `tests/test_gate.py` resolves every gate's rows to a registered tool whose required arguments are given or to choose; seen live at Assyria t238 with reads only: `gate` null, `faith_great_person_options.answers` three rows, the other eight empty with nothing pending). **1c code done 2026-10-25** (#47; `harness/affordances/` is a package now -- `decisions`, `units`, `questions`, `choices`, `objects` -- and every `available_*` reply hands each choice back with `call`, the complete write that takes it (`set_research`, `set_production` plus `buy` when the city can purchase, `choose_policy` / `unlock_policy_branch`, `found_pantheon` / `add_reformation_belief`, `establish_trade_route`, `move_spy`, `unit_mission` for a mission target or a new home, `city_ranged_attack`, `gift_unit`, `gift_tile_improvement`, `minor_gold_gift`); `available_unit_actions` and the normal / full `todo_actions` rows carry `call` (and `read`) beside every action, target and promotion; `units()` and `cities()` rows carry `actions`; `city_state_actions` carries its buttons as rows and `trade_catalog` the two deal calls plus a one-item ask per resource; a paused order names `resume_order` / `cancel_order`; the audit now finds a reply's mixin in any game_parts file, so 28 of the 31 affordance replies carry rows and the three left only inform (`turn_status`, `city_state_bonuses`, `purchase_cost`); the fake-bridge turn copies `call` rows out of the reads; seen live at t238 with reads only). **Open:** the live Assyria turn played from rows alone -- it ends a game turn, so it waits for the user's go-ahead (#47's last box). |
| 2 | `harness/surface.py`: the nine tools dispatching to the existing functions, per-action validation with a refusal that names the shape, `oneOf` on `order` (checked on Claude Code, Codex, Grok; string fallback), the retirement map with `renamed`, gate and ledger by `(tool, action)`, `--tools compact` and `call` retired, the 145 unregistered | `mcp_call.py --list` prints 9; the suite passes through the retirement map and again with it emptied. **2a done 2026-10-25** (#48; `harness/surface/dispatch.py` reads the retirement map the other way -- which old handler a new call runs, the arguments renamed back, the old names that share a row told apart by the argument given (a city's `governor` by focus / avoid / automatic, `policy` by the POLICY_BRANCH_ prefix, a city-state screen button through `city_state_action`), `state("city_state", view="full")` a composite of its five reads, a refusal naming the shape with `accepts` and one `example` row; `harness/mcp_tools/surface.py` registers the nine beside the 145 (`reference` is the old tool grown a `book`), each running the old handler through the server's runner so guard, ledger row and reply are unchanged -- `state(what="league")` is `league_status()` byte for byte; `question()` reads the gate's question with its `answers` and `answer(choice)` dispatches on the gate (a fixed word needs none); `turn(action="finish")` keeps its progress notifications; `tests/test_tool_surface.py` (13) reaches every old name from its row, refuses the malformed, checks every popup's answer and the server path). **2c done 2026-10-25** (#50; `harness/surface/forward.py` reads the map forward: an unlisted old name or an alias (`summary`, `status`, ..., the server's former `TOOL_ALIASES`) runs its old handler through `find_tool` and the reply carries `renamed`, the new call rendered with the arguments given; `new_call()` is the one place the new call's shape is written, from the new tool's schema, and the refusals' example comes from it; every one of the 145 names round-trips in the suite; seen live at t238 with reads only). **2b code done 2026-10-25** (#49; `harness/surface/listing.py` writes `order`'s schema from the action tables, oneOf per target or flat, chosen per client by `clientInfo` name / `CIV5_ORDER_SCHEMA`; set before each `tools/list` by an mcp 2.x middleware; the three clients' rendering measured: Claude Code 2026-10-25 / 2026-10-27 (2.1.311 turns the oneOf into a wrong "exactly one of" sentence, shown flat since), Codex 2026-10-26 (flat), Grok 2026-10-27 (verbatim passthrough, keeps oneOf; `docs/measurements/2026-10-27-assyria-t238-grok-session.md`); table in ARCHITECTURE; #49 closed 2026-10-27; the oneOf and its per-client variants removed the same night, one flat shape for every client (no client validated against it, and TDQS counted its branches as a shadowing cost)). **2d done 2026-10-26** (#51; `harness/surface/classes.py`: every set the server, the gate and the ledger sort a call by is keyed `(tool, action)` with `*` wildcards -- MENU, ANYTIME, WAIT, READ / HARMLESS, RESPONSE, SAVE, BATCH_EXCLUDED, the religion blockers, attention's FOCUS -- and a call's key comes from its arguments (`of_call`) or, for the old handler the guard wraps, from its row (`of_handler`), so an old name and the new call it means are one key; a ledger row carries `tool` (one of the nine), `action` and `called`; the spectator prints `tool · action`; `--tools compact` gone, `call` retired into the retired-handler table `mcp_server.retire` keeps (callable by name, its reply carrying the inner call's new name); `tests/test_read_tools.py`, `tests/test_retired_call.py`; seen live at Assyria t238 with reads only: same bytes and one ledger key for an old name and its new call, `tool · action` rows, `call` answering with the inner `renamed`, a batch refusing the turn's end by key). **2e done 2026-10-26** (#52; `@retired` where `@mcp.tool()` stood in every tool module registers the handler and takes it off the listing at once, so `scripts/mcp_call.py --list` prints the nine; an old name answers through the map with `renamed`, the request context passed on and a bad argument raised as before; the nine reach their handlers by exact name (`find_tool(exact=True)`); `--retired-names off` / `CIV5_RETIRED_NAMES` makes an old name unknown, and `scripts/check.sh` runs the tests marked `new_vocabulary` (`tests/test_nine_only.py`) a second time that way; seen live at Assyria t238 with reads only: the listing is 9, `league_status` answers with `renamed`, and with the map off `units` is unknown while `state(what="units")` and `turn(action="status")` answer). Stage 2 complete. |
| 3 | the words: instructions, PLAYBOOK, TOOL_REPLIES, AGENT_INSTALL, README, ARCHITECTURE; `reference("playbook", "orders")` prints the action table from the validator's own data; `tests/test_tool_surface.py` | the README teaches the loop in four lines: `turn` -> `question` -> `state` -> `order`. **3a done 2026-10-26** (#53; the server instructions rewritten around the nine under the 2000-character cut; `docs/PLAYBOOK.md` and its topics in the new vocabulary, the blocker table as reads and orders / `question` and `answer`; `harness/surface/table.py` prints every order's target, action, arguments and example and every object's views from the vocabulary, the retirement map and the forward map -- `reference(book="playbook", section="orders")` and the `orders` topic serve it, a test diffs them; every `hint` / `tool` sentence a reply carries names the new call (the audit's `named_in` rule: a new call or a quoted value names no old tool, a word that is also an old name counts only as a call form); the index lists the reply references by their new call and `reference(book="playbook", section=<new call>)` reaches them; `unit` and `city` lost their empty default view). **3b done 2026-10-26** (#54; `docs/TOOL_REPLIES.md` headings are the new calls with the keys unchanged and either name reaches a section; README teaches the loop in four lines and names the nine; AGENT_INSTALL's examples, ARCHITECTURE (a `Game.` method keeps its dotted name), LIMITATIONS in the new words; the before / after picture above; `TheWordsTests` reads the five docs with the audit's rule; the listing measured as listed: 9 tools, 11 KB). **3c done 2026-10-26** (#55; every `{tool, args}` row a reply hands back is written in the nine-tool vocabulary at the one leaf (`harness/rows.py` through `forward.new_call`; `vocabulary.TOP_LEVEL` says which arguments ride at the top), the gate's words follow (`gate.worded`), `question_read` and the ledger's attention read the new rows; `InvariantsTests`: the nine and no more, every description under the cut with every vocabulary word explained, `TOP_LEVEL` is the registered schema, every gate row resolves to a listed tool and a valid action; the Lua runtime still names the old tools in its own strings and one `how` row, re-rendered at the boundary until #57). Stage 3 complete. |
| 4 | live: a full Assyria turn from a fresh Claude Code session and a fresh Codex session; `play_loop --profile` before and after | both reach a city-state gift and a league vote without a name they were not shown; trip count unchanged. **Partly done 2026-10-26** (#56; `docs/measurements/2026-10-26-assyria-t238-*`): `play_loop --profile` on the S10 save before the surface (the commit before stage 0, in a worktree) and after -- 72 trips both times, 9.1 s against 8.9 s; `scripts/turn_from_rows.py` played t238 through a server that lists the nine alone (`CIV5_RETIRED_NAMES=off`): the briefing, Yerevan's full view, the league, then `turn(action="finish", actions=[<the gift row>])` -- the 250-gold gift ran from its row and t239 came back (4 calls, 62 trips); on t239 a dry run listed the Worker's, the Merchant's and two empty cities' rows and ordered nothing (the campaign is the user's). Open: the league vote (the session is t244), and the two fresh sessions (Claude Code, Codex), the user's. **The Claude Code half done 2026-10-26 evening:** a cleared session played t239 with the nine as listed (20 calls, 122 trips after the v286 install; the Merchant's trade mission made Belgrade an ally, both cities on Research, the denouncement and Shaka's offer answered through the gate, t240 reached; `docs/measurements/2026-10-26-assyria-t239-claude-code-session.md`). It met four Python reply strings naming old tools (`drill_down`, `how_to_answer`, `leader_screen_note`, the frozen-game refusal), fixed the same evening with their keys added to the audit; the refusals' `err` / `note` sentences (26 sites) say the new calls since the same night and `audit.KEYS` holds both keys; the empty notebook was the key's map part changing form at runtime v285 (`Assets_Maps_pangaea` -> `pangaea`): `Notebook.adopt` renames a legacy file once and the live notebook was merged by hand. **The league vote done 2026-10-26 night:** the t244 UN session through a fresh server -- the votable rows carried no row and the vote's list went to Lua as a string (a v285 regression): `league_rows` and the list fix, then the vote copied from the Furs row (28 Nay; the ban failed 36-10, the ISS passed), and at t245 the proposal rows carry their calls (`docs/measurements/2026-10-26-assyria-t244-league-vote.md`). **The Codex half done 2026-10-26 late night, stage 4 complete:** a fresh Codex CLI session (0.160.0, `gpt-6.1-sol`) on a server listing the nine alone played t247 -- Ur's 500-gold gift from its full view's row (49 -> 89, allied), the league read, a note, t248 reached; ten calls, 77 trips, no refusal (`docs/measurements/2026-10-26-assyria-t247-codex-session.md`). Its one report is #49's Codex measurement: the `oneOf` rendered as a TypeScript union of the branches alone, `id` / `args` dropped; `codex` is in `FLAT_CLIENTS` and the flat declaration measured complete. |
| 5 | runtime strings naming retired tools (one text-only `RUNTIME_VERSION` bump in a quiet window); release 2.0.0; re-submit to Glama and record the marks | the new marks sit next to today's on #59 and in the 2.0.0 changelog entry. **5a done 2026-10-26** (#57): 87 runtime strings in 19 fragments say the new call, the gift's `how` row is the new row, `target_tool` is `target_view`; runtime v286 is text only (`tests/fixtures/runtime_entries.json` pins the 331 entries and 257 seat slots, `tests/test_runtime_words.py`); `harness/surface/runtime_audit.py` scans the fragments' string literals under the Python audit's rule and the survey prints the (empty) table. An edit deploys at the next call (tunerd installs for a seat-bound connection, the client itself on a plain daemon): seen live at Assyria t239 on the plain daemon, the first `turn(action="status")` installed v286 (392 trips, the shipping) and answered in the new words, the next was the usual 4 trips. **5b: `v2.0.0` tagged 2026-10-26** (#58; runtime v287, 9 tools, 1694 tests; the README release row, test count and bullets, AGENT_INSTALL line 8, this paragraph). **The Glama re-score arrived by itself** (scored 2026-10-28, read 2026-10-29): A 4.4/5.0 across 9 tools, completeness 5/5, naming 4/5, disambiguation 5/5, tool count 5/5, next to 2026-10-04's 5 / 4 / 3 / 1 on #59 and in the 2.0.0 changelog entry; #58, #59 and milestone 2.0.0 closed 2026-10-29. |
