# Working notes (chronological findings)

## What one unit order costs, traced query by query (2026-09-27, t151)

An in-process trace (wrap `Game.q`, call the guarded tool function) of `unit_mission(90120, MISSION_SKIP)` on the
Venice/Mongolia hotseat at t151 showed five tuner queries where two were expected: `H.turn_state`, `H.modal_flags`,
the push, `H.unit_pos`, and once per process the notebook's `game_key`. The `modal_flags` trip was the gate's
`g.discussion_pending()` in `_refusal_for`, asked of the game although `H.turn_state` has carried the flag since
runtime v214; every mutating call paid it. Timings: each trip is ~45 ms and lands on the next game frame (the game
ran at ~20 fps here), and a read issued right after a push already shows the order applied -- six pushes
(MISSION_SKIP / AUTOMATE_BUILD alternating on a Worker), six first reads, 43-60 ms each. So the fixed 0.25 s before
the automate check and 0.2 s before the plain read-back were most of an order's wall time. After the fix a lone
order is `turn_state`, the push, the read-back (ledger 6 -> 5 trips, 0.30 -> 0.21 s; the ledger's two extra are
the per-call lock and connect), and a `do` batch reads all its units in one query at its end (two orders: 10 -> 7
trips, 0.50 -> 0.31 s). What remains per order is the gate's `turn_state` (1 trip, the safety read between orders:
a unit meeting a city-state mid-batch opens a popup the next order must see) and the push itself; a refused order
still spends two reads explaining itself (`available_unit_actions` + the unit rows), which would need the runtime
to answer the legal missions in the refusal.

## The wait reply after #43 (2026-09-27)

Status: **shipped in 1.7.0 and measured two ways against the 1.5.0 ledger.** #36 found that the seat's notes
(~600 B) and the visible-threat rows (~250 B each, the same barbarians turn after turn) were most of the
`finish_turn(briefing=true)` reply. 1.7.0 changes three things, all in `harness/briefing.py`, `harness/notes.py`
and the `finish_turn` wrapper (no Lua change):

- Notes ride once. The notebook counts writes (`rev` on every note; the hand-off cursor `notes_seen` is a rev,
  so a rewritten note is new again) and `finish_turn` / `briefing` carry only the notes written since the
  seat's last hand-off, with `notes_unshown` {count, more} for the rest. `notes="all"` is the old behaviour and
  `briefing(since="turn")` uses it by default, so the recovery read after a context reset still has them.
- Compact threat rows: id, unit, hp, x, y, `near` {unit, unit_d, city, city_d}, `assessment` (owner only when not
  barbarian). A threat the previous briefing listed comes back marked `seen` with only its position, hp and `d`,
  or with `near` again and `moved_from` when it moved; the listed ids ride on the baseline snapshot.
  `detail="full"` keeps every field. `decisions` is never cut (#30).
- With a briefing, the top-level `orders` of `finish_turn` keeps only each order's id, unit, status and `did`:
  the whole rows (steps, pause reason, hint, hostiles) were in it and in `briefing.orders` both, ~1.1 KB a turn
  with two open orders.

Measured first by replaying run B's recorded replies (the t48-t51 texts kept from #36) through the new composer:
the same turns, events and orders, only those sections change. Then the same save was played live t48-t51 once
more the same way (`docs/measurements/2026-09-27-venice-t48-t51-1.7-tools.jsonl`; each seat-0 turn a fresh
`scripts/mcp_session.py`, seat 1 by the same fixed script) and the board repeated the #36 run turn for turn: the
same six threats on t48, the same four on t49, the same one decision on t51, the warrior's order paused by the
same galley.

| wait reply (bytes) | 1.5.0, recorded | 1.5.0 text through the 1.7.0 composer | 1.7.0, played live |
|---|---|---|---|
| t48 -> t49 (no open orders, 8 event items) | 5028 | 4255 (-15%) | 4223 |
| t49 -> t50 (two open orders, one paused) | 5206 | 3628 (-30%) | 3614 |
| t50 -> t51 | 4670 | 3125 (-33%) | 3124 |
| the three together | 14904 | 11008 (-26%) | 10961 (-26%) |

Where it went, on t49 -> t50: `notes` 583 -> 90; `threats` 915 -> ~430 (one of three seen); top-level `orders`
1148 -> ~260. The issue's target of a third is met on a turn with open orders and not on one without: on
t48 -> t49 what is left is `changes.events` (1.47 KB: eight items with texts up to 160 characters) and
`woke_because` (300 B, which repeats the event kinds); neither was in #43's scope and both are left as they were.

Not the same as #36, and left in the ledger: the seat's notebook had five notes by now (Codex played this game on
after the #36 measurement), so the t48 recovery briefing was 4030 B against 3833; one `compare(kind="research")`
without candidates was refused (my call, not the tool's); a `give_order` to farm a plot that already had a farm
completed at once and left the worker on the todo, so one `finish_turn` was refused (1452 B) before the turn
ended. Per turn from `ledger_report.py`: reads 1.2 / 2938 B a turn against 1.0 / 3000 B in run B.

Found by measuring, and expensive: `finish_turn`'s autosave writes `QuickSave`, so the quick save that held the
night game's turn 129 was overwritten by the measurement's own turns. The game resumed from `AutoSave_0120`
(turn 121); the hotseat autosaves every ten turns (`PostTurnAutosaves = 0`). Before loading another save into a
live game, copy `QuickSave.Civ5Save` to a named file first.

## What a turn costs with the 1.5.0 tools (#36, 2026-09-27)

Status: **measured live; the tracking issue is closed with these numbers.** The instrument is new:
`CIV5_CALL_LOG=/path/calls.jsonl` in the MCP server's environment appends one row per tool call
(`harness/call_ledger.py`: seat, tool, read / write / wait, reply bytes, tuner trips, seconds, a refusal with its
`err`, the turn the answer names, and since 2026-10-03 `client` -- `CIV5_CLIENT` from the environment, else
the MCP client's name/version from the initialize handshake -- so rows from different models on one seat can
be told apart); `scripts/ledger_report.py [--client X]` groups the rows into turns at each wait that
succeeded, keeps the wait's seconds apart from inspection and lists every client label seen. The two ledgers are in `docs/measurements/`.

Method. The same save (`Venice-Mongolia_0048 orders-validated`: the Venice/Mongolia hotseat, seat 0 = Venice,
one city, eight units; the three #32 test orders were cancelled first) was played t48-t51 twice by the same
player making the same kind of decisions, each seat-0 turn in a fresh process (`scripts/mcp_session.py`), so
every turn is the hotseat context-recovery case. Seat 1 (Mongolia) was played by a fixed script between seat
0's turns: automate the explorers, Library first, the fastest tech, the first policy, the first pantheon. Run A
used only tools that existed at 1.2.0 (`turn_status`, `recall`, `units`, `cities`, `todo_actions`,
`map_window`, `available_unit_actions`, `available_research`, `move_unit`, `unit_mission`, `remember`,
`end_turn`, `wait_for_my_turn`, `turn_digest`); run B used `briefing` / `finish_turn(briefing=true)`,
`tactical_view`, `compare`, `give_order` / `resume_order`. The calls in both were the ones a careful player
needs, judged turn by turn; neither run is a minimal script. `~tok` is bytes / 4 (no client tokenizer).

A turn is every call up to and including the wait that ended it, so run B's `finish_turn` reply -- which is
the next turn's briefing -- counts in the turn it closes. All calls and all bytes, per completed turn:

| | Run A, 1.2.0 tools | Run B, 1.5.0 tools |
|---|---|---|
| calls / turn | 8.0 | 4.25 |
| bytes / turn, every reply | 7446 (~1.9k tok) | 8216 (~2.1k tok) |
| of which the wait's reply | 848 | 4598 |
| inspection calls / turn (reads) | 3.5 (13.5 KB on the cold t48, 2.8-5.0 KB after) | 1.0 (7.1 KB on the cold t48, 0-3.3 KB after) |
| refused orders | 1 (`move_unit` onto the plot the Merchant of Venice held), then a refused `end_turn` | 0 |
| model-side seconds / turn (reads + writes) | 8.3 | 7.3 |
| what was missed | a barbarian Brute at 10 hp beside Warrior 16385 at (74,34), outside the map window read | nothing that came to light later |

Per turn (from `ledger_report.py`; `wait s` is not comparable, see below):

```
Run A   turn reads  bytes  trips read_s writes refused wait_s     Run B   turn reads  bytes  trips read_s writes refused wait_s
          48     6  13543     21    6.8      0       0    6.3               48     2   7112     17    5.8      1       0   29.4
          49     2   2828      7    2.3      5       1   13.9               49     1   3334      3    0.9      3       0   25.7
          50     2   3308      6    2.2      2       0    6.2               50     1   1554      3    1.1      2       0   31.4
          51     4   4974     11    3.8      3       0    3.2               51     0      0      0    0.0      2       0    5.3
```

What the numbers say:

- Calls halved (8.0 -> 4.25) and refusals went to none; bytes did not fall (+10%). Run B's `finish_turn`
  reply is 4.7-5.2 KB every turn: four to six threat rows at ~250 B each, the event list, the orders, and the
  seat's two old notes (~600 B) ride on every one. Run A read less because it looked at less: on t49 and t50
  it never read the board at all.
- What the bytes bought. t48's briefing listed a `BARBARIAN_WARRIOR` at 10 hp adjacent to Warrior 16385;
  `tactical_view` previewed `target_would_die` (21 damage expected, 22 taken); the attack killed it and took
  the camp: +16 gold, Tyre +12 and +50 quest influence, Yerevan's quest too. Run A's `map_window` around
  Venice never showed it and the warrior stayed fortified. On t49 `compare(improvements)` showed the worked
  Cow as the only plot whose build changes the empire's yield now; run A first sent the same worker onto the
  hill the Merchant of Venice stood on (refused), then to the Cow. By t51 run B needed no read: the briefing
  that closed t50 named the turn's one decision, and t52 arrived with nothing to decide (the warrior's
  heal-then-fortify order completed on its own; both worker orders were building).
- Not a saving, and not comparable: tuner trips (45 -> 56 a turn) and wait seconds. Run B's `finish_turn`
  polled through seat 1's whole turn; run A's seat 1 was played between its `end_turn` and its
  `wait_for_my_turn`. Read trips alone fell 11.2 -> 5.8, plus the briefing's own reads inside `finish_turn`.
- Found by measuring: on t50 a 600 s `finish_turn` came back `timed_out` after 24 s. Seat 1's `end_turn` held
  the per-socket lock past one poll's 10 s acquire timeout and the `TimeoutError` left the wait. Fixed in
  `a0b2692` (`LockBusy`: a busy lock skips that poll, not the wait; the wait's own deadline still names the
  holder). It cost run B one extra call and 1.7 KB, both left in the table.
- Not run: a developed-empire turn loop. The per-read figures for S1 t266 (38 units) are in the #35 and #30
  sections below (30 KB of separate reads against a 2.5 KB briefing); a played loop there was not measured.
- Worth an issue: the notes and the threat rows are most of the wait reply at this size; a cap or `since` for
  the notes that ride on `finish_turn` and a shorter threat row would take about a third off it.

## Compact comparisons (#34, 2026-09-27)

Status: **shipped; checked live** (runtime v225 `H.compare_production`, `H.compare_research`,
`H.compare_improvements`, `H.compare_trade_routes`, `harness/compare.py`, the `compare` tool and `GET /compare`,
`tests/test_compare.py`).

- One tool, four kinds, one runtime read each. The runtime returns engine answers and table rows; compare.py
  adds `context`, `sources`, `assumptions`, the `limit` cut and `omitted` (with the exact arguments for the
  rest). `sort` exists only for improvements and trade, and only orders by a field the caller names; production
  and research keep the caller's order. Nothing is ranked.
- Refusals name the rule this read can check (tech, building needed in the city, national-wonder counts, a
  world wonder already built, coastal / river / fresh water / mountain / hill, resources, the civ's own class
  replacement, Venice's trait) and otherwise say `why_unknown`. Venice's Settler: `CanTrain` is false with no
  class override (Civilization_UnitClassOverrides only swaps the Merchant and the Galleass); the rule is
  Traits.NoAnnexing on a `Found` unit. Contrast checked live: Mongolia (seat 1, same game) trains Settlers,
  `MayNotAnnex()` false.
- A price is shown only where the buy button exists (`IsCanPurchase` with the cost test off), so a Settler
  or a built Monument carries none. The same check now guards `purchase_cost`'s "not enough gold" reason.
- `estimated_change` = (base + added) x (city modifier% + building%) / 100 - now per city yield, `added` =
  flat + per-pop x population + conditional x tiles worked now. City only: Venice t42's city screen shows
  culture 6 (3 from policies) where `GetBaseYieldRate(culture)` is 3, which is why empire and policy terms
  are named as left out rather than folded in.
- Improvements: yields from `CalculateYield` / `GetYieldWithBuild`, the same pair `available_unit_actions`
  uses; a fogged plot is not read at all. `connects` only for luxuries and strategics (a Cow is never
  "connected").
- Trade: the chooser's rows (`available_trade_routes`) plus `distance` and `hazard` around both ends; a
  potential route's path does not exist before it is set, so nothing is said about the way there.

Live checks:

| State | Check | Result |
|---|---|---|
| Venice t42 seat 0 | production: Settler, Monument, Library, Worker, Pyramid, Lighthouse, Trireme, Granary | turns / price identical to `available_production` and `purchase_cost` for the four buildable ones; Settler `why` = trait, Monument already built, Pyramid needs Masonry, Lighthouse needs Optics; Library +2.5 science (5 pop x 0.5), Granary +3 food (2 flat + the worked Deer); 4.9 KB |
| Venice t42 seat 0 | research: Writing, Philosophy, Pottery, Currency | Philosophy 135 / 17 turns as `available_research`; Currency locked behind The Wheel + Mathematics, 255 beakers, 32 turns at 8 science |
| Venice t42 seat 0 | improvements, Worker 49155 | 6 rows; the worked Cow's pasture is an `empire_change`, the unworked Wheat farm is not; gold mines connect a luxury (happiness 4 if first) |
| S5 t215 (Venice) | production in the puppet Wittenberg | `purchase_only`, producing Observatory; the five unit prices equal the puppet's purchase list (70, 60, 280, 250, 280), no turns |
| S5 t215 (Venice) | production in Venice | University +5 science (33% plus a worked jungle), Stock Exchange needs a Bank, a Garden (no table effect) carries its help text |
| S5 t215 (Venice) | improvements, Worker 65543 | 11 rows, turns and tile changes identical to `available_unit_actions`; a mine on forest hills removes the forest (13 hammers) and connects Gold; Coal is `strategic` |
| S1 t266 | trade | seat 0's four caravans are all on routes, refused as `available_trade_routes` refuses them. Mechanics checked through Ethiopia's (player 4) idle caravan in Addis Ababa: 14 destinations, `sort="gold"` gives 27 / 22.58 / 20.66 / 18.82 / 16.76, equal to the chooser; 5 rows 3.8 KB against 10.2 KB for the whole list; distant destinations read 19 of 19 plots not visible |
| S1 t266 | research, late game | Rifling / Military Science match `tech_tree` (2240, 15 turns); Nanotechnology has 18 missing prerequisites, 103571 beakers, 696 turns at 149 science (`tech_tree` prints 83 turns: that tech alone) |

Not seen live: a trade destination with a visible hostile or camp near it (tests cover it), a puppet's faith
price, a world wonder completed elsewhere. The hotseat was reloaded from `codex-grokadile_0042 measure-baseline`
afterwards (t42, seat 0 to move).

## Structured assignments (#33, 2026-09-26)

Status: **shipped; checked live read-only** (runtime v224 `H.assignment_facts`, `H.is_upgrade_of`,
`harness/assignments.py`, the notebook's `assignments`, the `assign` / `assignments` / `amend_assignment` /
`close_assignment` tools and HTTP routes, the briefing's `assignments` section, `tests/test_assignments.py`).

- Identity: a unit is (id, type, `GetGameTurnCreated`), a city (id, x, y, `GetGameTurnFounded`), fingerprinted
  when assigned. The same id reading back as another type or creation turn is the assigned entity gone, never
  followed (live Venice t42: Warrior 16385 against a SCOUT/t7 fingerprint). The notebook file is per game
  and seat, so the other seat never sees an assignment (live: seat 1's server answered "no assignment 1" with an
  empty id list). A new game did, until the key named the game by its identity rather than by leader, civ, map and
  capital (GitLab #168: a fresh Maya game's Warrior 16385 matched the previous Maya game's fingerprint exactly).
- An upgrade gives the unit a new id on the same plot. A missing unit's facts list my units on its last plot and
  mark the ones `Unit_ClassUpgrades` says it upgrades to (`H.is_upgrade_of`; live WARRIOR -> SWORDSMAN true,
  -> SPEARMAN false in this BNW database). The reason line names it; the model amends. Nothing is re-pointed
  automatically: a different Swordsman on that plot would look the same.
- Fog: target plots answer with revealed owner and improvement under fog and nothing about units or cities;
  a foreign unit only while in sight, and a dead unit reads the same as a hidden one. The last sighting (`seen`)
  is stored on visible reads only, so an out-of-sight target stays "stale, last seen turn N" (live: a
  barbarian archer in sight was tracked; an id not in sight with a visible last plot got "not on the plot it
  was last seen on; where it went (or whether it still exists) is not in sight").
- City sites: `GameDefines.MIN_CITY_RANGE` is **3** in this game (live), and it counts my own cities: a
  site two plots from Venice was flagged "Venice (you) stands 2 plot(s) away".
- Cost: one runtime read for all active assignments. Live t42 with four assignments: `assignments()` 3 trips,
  2.1 KB; the briefing 8 trips and 4.3 KB, of which the section was 1.4 KB (purposes are most of it).
- Not exercised live: an actual unit loss or upgrade. Disbanding units on the measurement baseline was
  declined; the mocked-engine tests cover both (`test_my_units_live_a_missing_one_and_its_upgrade_on_the_last_plot`,
  `test_an_upgrade_is_surfaced_and_taken_over_with_amend`). A real game with a Warrior upgrade is the next check.

## The tactical view (#31, 2026-09-26)

Status: **shipped and checked live** (runtime v222 `H.tactical_view`, `H.move_refusal`, `Game.tactical_view`,
the `tactical_view` tool, `GET /tactical_view`, `tests/test_tactical_view.py`).

- Movement legality is only what `move_unit` itself refuses before sending: its checks now live in
  `H.move_refusal(u, dest, pid, fog_safe)` and both call it, so the view and the order cannot disagree (live:
  the Scout's coast neighbour, identical text). `open` means only "the order would be sent"; `CanStartMission`
  is asked per neighbour when the unit has moves. No #24 probes: no GeneratePath, no MovementCost.
- Fog-safe variant: under fog the border check uses `GetRevealedOwner`, and a foreign city on a fogged plot is
  named only when `City:IsRevealed(team)` (the banner a human has). `move_unit` keeps its live reads.
- River crossings come from the edge flags: a plot owns its E (`IsWOfRiver`), SE (`IsNWOfRiver`) and SW
  (`IsNEOfRiver`) edges; NE, W and NW are read from the neighbour. Checked live: for all 4,160 plots of the
  Venice map, "some edge has a crossing" equals `IsRiver()`. `IsRiverCrossingToPlot` exists in the DLL but was
  not called (untested getter; the flags are the ones the map scripts set).
- Adjacency is `Map.PlotDirection` (0 = NE .. 5 = NW). Live: 2,434 neighbours of the edge rows, both seam
  columns and 200 random plots, all at `PlotDistance` 1 and distinct; 350 off the map (the polar rows).
- Found live and fixed before the commit: a melee Warrior with its moves spent beside a Barbarian read "no melee
  attack" (melee_targets is empty at 0 moves); `enemy` now says which of civilian / ranged / no moves / cannot.
- Sizes on Venice t42, radius 2: Scout 2,790 B, Warriors 2,661 / 2,754, Worker 2,237, Archer 2,091 (the legend
  is ~0.9 KB of each); `map_window(r=2)` + `available_unit_actions` for the same units 2,414-3,066 B in two
  calls. `detail="full"` 3.8-5.2 KB. About 0.4 s a view.
- Not seen live yet: a unit beside a river (no unit of either seat stands next to one at t42), a crowded
  friendly stack (one-per-tile refusal is unit-tested only), a melee `attack` neighbour with moves.

## The turn briefing (#30, 2026-09-26)

Status: **shipped and checked live** (runtime v221 `H.briefing_board`, `harness/briefing.py`, `Game.briefing`,
the `briefing` tool, `finish_turn(briefing=true)`, `GET /briefing`, `tests/test_briefing.py`).

Design points that are not obvious from the code:
- Events come from the runtime's event log (`H.events_since`) with the briefing's own cursor, stored as
  `event_seq` in the baseline. The digest's cursor (`H.take_events`) is never moved by a briefing, so
  `turn_digest` / `finish_turn` and the briefing each see every event once. Checked live on S1 t266-t267: the
  events the discussion-interrupted `finish_turn` had already delivered (Ethiopia's remark, Sidon lost) were
  still in the next briefing.
- The baseline (empire totals, city pop/production, unit ids, `event_seq`) lives in the seat's notebook file
  under `briefing`, so a new server process or a reset context still diffs against the seat's last briefing.
  A baseline from a later turn than the game shows (a reload) is not comparable; a log head below the
  stored cursor (a load gives the runtime a fresh log) re-reads from the seat's last `turn_end`.
- `stacked` in `todo` is listed for every shared tile (a worker beside a caravan too): the briefing makes it a
  decision only when `blocking_name` is `ENDTURN_BLOCKING_STACKED_UNITS`, a warning otherwise.
- Markup is stripped before an event line is cut to 160 characters (a cut `[ICON_...` is not a tag any more).

Measured with `scripts/measure_reads.py` (bytes are the reply string; trips include the guard's own
`turn_state`):

| Case | six-call recovery (table above) | `briefing(since="turn")` | `briefing()` |
|---|---|---|---|
| Venice t42 hotseat seat 0 | 7202 B, 15 trips, 5.2 s, no threats | 3416 B, 9 trips, 3.3 s | 2580 B, 7 trips, 2.7 s |
| S1 t266 (2 units to order) | 29872 B, 15 trips, 5.3 s | 2466 B, 7 trips, 2.8 s | 2063 B, 7 trips, 2.8 s |
| S1 t267 (12 units to order) | -- | 4559 B, 9 trips, 3.4 s | 3124 B, 7 trips, 2.9 s |

The briefing also carries what the six calls do not: visible threats (Venice t42: three barbarians, one at
10 hp beside warrior 16385, which otherwise needs `known_world`, 24.8 KB), the civ's trait text (Serenissima:
no settlers, no annexing), and changes since the last briefing. Per the issue, shorter is not the claim: the
decisions list is never cut, and every capped list says how many it left out and which tool shows them.

Live path, S1 t266 -> t267 through `finish_turn(briefing=true)`: the first end was refused (stacked workers,
then a worker with a move left), `status` / `end_turn` came back as before; the next stopped at Ethiopia's
remark (discussion_pending, no briefing attached, status and digest kept); after the answer the briefing arrived
in place of status and digest: baseline t266 comparable, Goshute Walls -> "" (a new `city_production` decision),
Machu Bank -> Walls, happiness 4 -> 0, seven events listed. Seat 1 asking for a briefing while seat 0 is on
screen got the `other_seat_active` refusal and no board read.

## What a turn's reads cost, and `todo_actions(detail="summary")` (#35, 2026-09-26)

Status: **baseline recorded, summary level shipped and checked live** (runtime v220, `harness/game.py`
`_summary_unit_row`, `scripts/measure_reads.py`, `tests/test_todo_actions.py`). The milestone 1.3.0 order
says: measure first. `scripts/measure_reads.py --seat N --label ...` calls the MCP tool functions in-process,
so the bytes are the exact reply string (`J(...)`), and counts tuner trips by wrapping `Civ5.call`. It orders,
ends and consumes nothing. No client tokenizer is available here: `~tok` is bytes / 4 and only a guide.

Baseline, before any change (runtime v219), the reads a fresh context makes before it can decide:

| Read | Venice t42 hotseat seat 0 (early) | S1 Shoshone t266 solo (developed) |
|---|---|---|
| `turn_status` | 1416 B, 5 trips, 1.3 s | 4486 B, 5 trips, 1.3 s |
| `recall` | 672 B (2 notes), 1 trip | 96 B (0 notes), 1 trip |
| `overview` | 2563 B, 2 trips | 4369 B, 2 trips |
| `cities` | 485 B (1 city), 2 trips | 4408 B (8 cities), 2 trips |
| `units` | 1934 B (5 units), 2 trips | 15258 B (38 units), 2 trips |
| `todo_actions` (the todo units) | 648 B (1 unit), 3 trips | 1255 B (2 units), 3 trips |
| **context recovery, 6 calls** | **7718 B (~1.9k tok), 15 trips, 5.2 s** | **29872 B (~7.5k tok), 15 trips, 5.3 s** |
| `todo_actions` every unit / `full` | 3833 / 4056 B (5 units) | 26600 / 29066 B (38 units) |
| `known_world` (for scale) | 24893 B | 88939 B |

The early-empire row doubles as the hotseat context-recovery case: seat 0 of the two-agent game, read cold by
a process that had never seen it. The documented v213 figure (30 KB default, 59 KB `full` for 38 units) had
already fallen to 26.6 / 29.1 KB with the v216 rule book. What is left is the action rows: 19.7 KB of the
26.6 KB, ~60 bytes each for `{"type":"MISSION_SKIP","kind":"mission","mission":"MISSION_SKIP"}` on every unit.

After: `todo_actions(detail=...)` is `summary`, `normal` (default, the old rows) or `full` (= `full=true`),
all cut in Python from the same one Lua read, so trips and facts are identical at every level:

| Case | summary | normal | full | trips (each) |
|---|---|---|---|---|
| S1 t266, all 38 units | 5701 B | 26632 B | 29096 B | 3 |
| S1 t266, the 2 todo units | 708 B | 1286 B | -- | 3 |
| Venice t42, all 5 units | 1311 B | 3833 B | 4056 B | 3 |
| Venice t42, the 1 todo unit | 572 B | 679 B | -- | 3 |

-79% for the 38-unit case, -66% for the early empire. A summary row keeps id, type, x, y, moves, hp when
damaged (the one field the rows lacked: v220 adds `hp` / `max_hp` to damaged units at every level),
`promotion_ready`, the non-routine actions as `{tool, args}` rows for do() (since #45; bare type strings before
2.0.0), a count of the routine ones (move, route,
swap, skip, sleep, fortify, alert, wake, cancel, delete, automate / stop, remove route -- named once in
`routine_actions`), promotion enums, targets in reach (x, y, unit or city, owner, hp; the previews stay in
normal) and worker `build_plots` (x, y, builds, resource). `drill_down` holds the exact normal-level args.
`limit=N` returns the first N in todo order and lists every other id under `omitted` with the args that fetch
it. Live checks: on S1 every summary row's actions plus the routine ones equal the normal row's types for all
38 units; a Paratrooper given 30 damage by Lua read hp 70/100 in summary, normal and `units()` alike, then
was restored to 100; on Venice t42 the two damaged units (Scout 67, Warrior 77) carry hp and the Worker's
five improvable plots come through as `build_plots`. `normal` stays the default: rolling the compact form out
by default is #30's briefing, and play with it should count drill-down calls and refused orders so a smaller
reply does not just move the cost into more calls.

## Bytes are not tokens: the hover text moved into one rule book (2026-09-26)

Status: **done and checked live** (runtime v216, `harness/reference.py`, `tests/test_reference.py`). Live
2026-09-26 on the Codex/Grok hotseat save (Venice, t42, stock BNW), from a fresh `Game()` after the other
servers were stopped: the one `H.reference()` trip took 0.8 s after the 52 s re-injection; every section
filled (148 units, 140 buildings, 81 techs, 214 promotions, 111 policies in 12 branches, 69 beliefs, 42
resources, 29 improvements, 9 terrains + 25 features, 119 actions, 7 specialists, 6 projects, 5 processes),
no `errors`; the whole book is 238 KB of Markdown, about 59k tokens, saved beside the notebooks. Rows that
have no sentence are the ones the database gives none (terrains, bonus resources, most improvements, the Great
People units whose abilities are their actions). `available_production` (11 rows), `available_research`
(7 rows) and a radius-3 `map_window` (8 resource plots) came back with no `help` / `resource_*` hover fields;
`resource_requires_tech` / `resource_usable` remain, as they should.

The question was whether to shrink `map_window` by coding terrain as one character ("grasslands" -> a glyph,
nine bytes a tile). The README's "not a list of coordinates" line was also called out: every plot record does
open with `x`, `y`, because `move_unit` takes them; the sentence was about unexplored land and now says so.

Why the glyph is the wrong lever: the model pays in tokens, and "GRASS" is one token in every major
tokenizer while a non-ASCII glyph is two to four (multi-byte sequences split). The terrain word is already
the cheapest part of a plot record; the JSON scaffold around it costs more. And letter codes trade tokens
for reasoning: a model reading `G` has to hold a legend and decode on every tile, which is worth it for the
bird's-eye grid (`revealed_map` already does exactly that, per-reply legends and all) and not when deciding
where one settler goes.

Where the fat was: `describe_plot` attached the resource hover (happiness, improved yields, blurb) to every
resource tile, verbatim, since v179; `available_production` attached `Help` to every unit/building/
project/process row, in every city, every turn; `available_research` / `tech_tree` the tech sentence and the
unit/building blurbs under each unlock; `promotion_options` the effect line; `available_policies` and
`available_beliefs` the effect text; `city_screen` the building help (GitLab #17); `available_unit_actions`
the standing sentence under every button and every nearby build. Tens of tokens per row against four for a
terrain word, and none of it changes during a game.

The fix follows the one already used for the grid legends: hoist. `H.reference(section)` walks GameInfo once
(a database cursor -- one pass per link table, bucketed by key, never one pass per parent row) and returns
the whole civilopedia's static text; the Python side renders Markdown and caches per process. The rows keep
enums, names and live numbers. The split inside `action_help` is the interesting one: the panel computes a
handful of lines per unit (upgrade target and price, scrap gold, golden-age length, paradrop range, the
"cannot fortify" swap) and those stay on the row; the standing sentences moved to `H.action_static_help`
and the book. `todo_actions(full=true)` now keeps only the computed lines.

Test worlds index GameInfo tables as plain Lua tables (`GameInfo.Resources[1] = {...}`) while the game's are
callable cursors, so the reference iterates with `ref_each` (call it; if that fails, walk keys in order) and
finds an id with `ref_id` (the `ID` column, or the key the row sits under).

## The Continue screen nobody named: `gate`, and why `screens.PlayerChange` never saw it (2026-09-26)

Status: **fixed** (runtime v215, `harness/gate.py`, `tests/test_gate.py`).

From the Codex transcripts of the Codex/Grok hotseat game (seat 0, Venice), two stalls on the hand-off screen
in one hour, both the harness's fault:

1. **The other seat's screen, read as advice.** After a context reset, `turn_status` answered
   `my_turn=false, active_player=1` and the note "seat 1 is on screen. set_seat(player_id) changes the seat".
   Codex called `set_seat(1)` (refused: pinned server) and then `harness.cli lua 'OnContinue()' --state
   PlayerChange` -- the other player's Continue button, through raw Lua, because nothing had told it that
   waiting was the whole answer.
2. **Its own screen, invisible in the status.** Turn 22 came back as `my_turn=true, paused=true, popup_up=true,
   pending_popups=[], blocking_name=NO_ENDTURN_BLOCKING_TYPE, todo={}`. Reads work under the hand-off screen,
   so it read the board for four minutes; its first order was refused with `game is paused, processing, or
   waiting; use wait_for_my_turn`, and its retry with the same `action_id` got that refusal replayed from the
   cache. `wait_for_my_turn`, when it finally came, cleared the screen in one poll. The same shape was on
   screen again at t24 while this was being written.

Why the status could not name it: `H.modal_flags` reads `screens.PlayerChange` like every other context,
`LookUpControl(path):IsHidden()`. Verified live at t24 with the screen up: the PlayerChange context answers
`IsHidden() == true` while `UIManager:IsModal(ctx)` is true and its `MainContainer` is visible. That is the
rule `game.py`'s `player_change_pending()` has always used from inside the PlayerChange state (two trips);
`H.hand_off_up` now asks it from InGame in the same trip as everything else, and `turn_state` carries
`hand_off_pending`. `paused` was the screen's shadow all along (`OnPlayerChange` calls
`Game.SetPausePlayer`), which is why the guard refused correctly and the status still said nothing useful.

The general fix is `gate`: the precedence the guard, the wait loop and this file enforced in three places is
one function (`compute_gate`) and one field on every status and every refusal -- `null`, or the first
precondition with the tool that clears it. Injection caveat: `ensure_runtime` compares a source digest, so a
running server built from the old source and a new one on the same game re-inject each other (~70 s each,
under the lock) until the old one restarts; the live game was left alone for that reason and the Lua probe
was verified inline instead.

Addendum, the same afternoon: naming the screen was still one step short. An agent that (re)started on its
own Continue screen read `hand_off_screen` and had to call `wait_for_my_turn` to press a button its human
would press before anything else -- a UI gate handed to a player who wanted a game state. Pressing it is
safe to do unasked: it is only ever our own screen (`active_player` must be our seat; the other seat's is
untouched, so nothing crosses the information boundary), nothing about the game changes between the
hand-off and Continue, and the press is idempotent. So `Game.clear_hand_off` runs in the guard, in
`turn_status` and in the HTTP `/turn_status`: two presses, then the state as the wait would return it
(`_arrive`: standing orders resumed, expiring city-states) with `hand_off_cleared: true`. The gate stays
as the fallback for a press that does not take, and says so. One latent bug fell out: under our own
hand-off screen `my_turn` already reads true, so a `finish_turn` retried after a client timeout that
landed on the next turn's Continue screen would have ended that turn blind; it now waits instead.

## Open bug: waiting holds the shared hotseat operation lock (2026-09-26)

Status: **fixed the same day** (the wait loops lock per poll; `tests/test_lock_liveness.py`), see the
addendum below for the holders. Written by Codex at `50bd73a`: **open, confirmed by source inspection at
`50bd73a` (runtime v214)**. Live symptoms match;
the process holding the lock in that session was not identified. This is a harness concurrency bug,
not an engine limitation. No runtime fix accompanies this report.

Expected: two MCP processes, each pinned to its own human seat, can share one hotseat game and tuner
bridge. The inactive seat may wait while the active seat dismisses Continue, plays, and ends its turn.
Only individual game operations need exclusive access.

Observed during the Codex/Grok hotseat session: after Codex ended Sweden's turn 1 and confirmed
`active_player=1, seat=0`, the user later reported that seat 0's Continue screen was waiting. Repeated
seat-0 `wait_for_my_turn` and `turn_status` calls returned
`{"ok":false,"err":"another game operation is running; retry"}` after approximately 10 seconds.
There was no successful state read during the stall; the on-screen condition was user-reported.
Attributing the lock specifically to Grok remains an inference, not a measured fact.

Cause and scope:

- `harness/mcp_server.py:guarded` acquires `action_lock(...)` around the entire tool call. Both
  `wait_for_my_turn` and `finish_turn` use this decorator. Their inclusion in `ANYTIME_TOOLS` only
  bypasses turn eligibility checks; it does not bypass or release the lock.
- `harness/action_lock.py:action_lock` takes a process-local `RLock` and a cross-process exclusive
  `flock` on `/tmp/civ5-actions-<hash(socket_path)>.lock`. Separate MCP processes using the same socket
  path and shared lock-file filesystem contend regardless of seat. The lock is keyed by the socket
  path string, not the seat; it is not a universal lock across independent machines/game instances.
- `harness/game.py:Game.wait_for_my_turn` sleeps and polls when `active_player != self.seat`. Because
  its MCP wrapper still holds the lock, the active seat cannot enter a guarded tool to dismiss its
  handoff or play. `Game.finish_turn` also waits under that outer lock after ending a turn.
- A competing call gives up acquiring the lock after 10 seconds. The wait holding it can last 90
  seconds by default (`wait_for_my_turn`) or 600 seconds (`finish_turn`), or a caller-selected duration.
  This is a circular wait bounded by timeout; immediate retries can repeatedly stall progress. Even
  `turn_status` is blocked. Increasing wait timeouts makes this failure last longer.

Reproduction (two independent MCP processes, same bridge, seats explicitly pinned to 0 and 1):

1. Leave seat 0 active, optionally at its PlayerChange/Continue screen.
2. From seat 1, start `wait_for_my_turn(timeout_seconds=60)` and let it enter its polling loop.
3. While that call is pending, from seat 0 call `turn_status` or `wait_for_my_turn(timeout_seconds=5)`.
4. Seat 0 receives the operation-lock error after about 10 seconds, so it cannot take the turn that
   seat 1 is waiting for. When seat 1's wait exits, seat 0 can acquire the lock again.

The same problem occurs when seat 1 calls `finish_turn` on its own turn, successfully hands control
to seat 0, and then keeps the lock while waiting for seat 1 again. These are reproduction instructions;
a controlled two-process replay was not run for this documentation-only change.

Temporary workaround: coordinate agents so only the active seat calls the game tools. Use `end_turn`
to hand off without waiting; the inactive agent waits outside the MCP operation. The newly active
agent may use `wait_for_my_turn` to dismiss its own Continue screen once the previous call has returned.
Keep each agent pinned to its assigned seat. A different active player is normal between turns;
`set_seat` must not be used to take the opponent's seat to resolve this stall. Short waits reduce the
blocked interval but do not fix the race. Do not delete a held lock file: that can create a second lock
inode and allow simultaneous game operations.

Required fix: scope exclusive access to each poll/operation, release it before sleeping or waiting
for another player, and reacquire it before checking and acting on the active seat. Preserve atomic
selection -> order -> postcondition sequences, seat checks, and handoff handling. `finish_turn` must
release the lock between its end-turn operation and subsequent polls, including quiet-turn loops.
Simply removing the guard from wait tools is insufficient because they also dismiss popups and resume
unit orders. Progress callbacks must not retain the operation lock while waiting on the client.

Acceptance coverage: use two processes with the same isolated test socket/lock to prove that an
inactive seat's wait allows the active seat's status/action calls to complete before that wait expires;
exercise both wait tools, timeout/cancellation cleanup, and continued serialization of actual actions.
Then verify several alternating turns in a live two-agent hotseat game, including Continue screens.
Existing `tests/test_mcp_progress.py` checks progress delivery with a fake game, and
`tests/test_mcp_safety.py` checks lock exclusion; neither establishes this two-process liveness property.

### Holders identified from both agents' transcripts (2026-09-26, follow-up)

The report above is correct about the mechanism. The Codex rollouts (`~/.codex/sessions/2026/09/26/`)
and the Grok session log (`~/.grok/sessions/.../01a0dbe4-.../events.jsonl`) carry UTC timestamps for
every tool call, and they line up. Three different processes held the lock in turn; none of them was
"the other agent's MCP server" doing anything wrong, and there was never one shared server instance:
Codex had `--seat 0` (registered with `codex mcp add` mid-session), Grok had `.mcp.json`'s `--seat auto`,
which is seat 1 in hotseat. Every process on the same tuner socket shares the flock, one-shot CLI
callers included.

1. **04:09:23-04:10:38, the first call after launch.** Grok's `turn_status` was the first tool call
   into the freshly launched game, so `game()` injected `runtime.lua` (~75 s, the known re-injection
   time) with the lock held. Codex's `mcp_call.py wait_for_my_turn` and `turn_status` at 04:09:23 and
   04:09:42 got the 10 s refusal. Grok's parallel `players` call in the same second got it too: the
   Grok CLI issues tool calls concurrently, and the in-process `RLock` refuses the second one after 10 s.
2. **04:15:12-04:18:15, an orphaned one-shot server, Codex's own.** Codex ran
   `scripts/mcp_call.py --seat 0 wait_for_my_turn '{"timeout_seconds":180}'` through its `exec_command`
   with a 30 s yield; the command kept running detached after the yield. `mcp_call.py` spawns a fresh
   `harness.mcp_server` per call, and that server (pid 198237, no `--seat` flag, `CIV5_SEAT=0` in env)
   sat in `wait_for_my_turn`'s `time.sleep(poll)` holding the flock for the full 180 s. This was Grok's
   turn: `set_production`, `move_unit`, `turn_status` and `generic_popup` were refused from 04:15:18 to
   04:17:27, and Grok's own probe at ~04:17:50 listed exactly that process with its worker thread in
   `hrtimer_nanosleep` next to Codex's real server (198166) blocked in `futex_do_wait`. Codex's own
   MCP calls from 04:16:13 on were refused by the same orphan. Grok's `do` succeeded at 04:18:33, seconds
   after the 180 s expired.
3. **04:18:42-04:23:45 and 04:24:59-04:30:02, the documented bug.** Grok ended its turn with
   `finish_turn(timeout_seconds=300)`. The end-turn half worked at once (Codex became active at
   04:18:4x, the PlayerChange screen came up), then the wait half held the lock for the remaining
   ~300 s, twice, until it timed out. Codex could not call `wait_for_my_turn` to clear its own Continue
   screen nor `turn_status`; the user saw the black hand-off screen sit there and asked "is the mcp
   server wedged". Codex cleared it at 04:21:56 with raw `harness.cli lua 'OnContinue()'`, which does
   not take the lock (only `mcp_server.guarded` does), then played turn 1 through MCP once the 300 s
   expired.

So the wedge is one cause seen three ways: any call that sleeps under `guarded` (a wait, or the first
runtime injection) starves every other process on the socket for its whole duration, and the 10 s
acquire timeout turns that into a stream of refusals rather than a queue. The fix in the report above
stands: hold the lock per poll, not per wait.

**Fixed and verified live (same morning, 11:41-11:52 EDT).** With the per-poll lock (`e1ec34f`) the same
two agents replayed the same setup on the same socket: Codex's first `turn_status` injected the runtime
for ~60 s and Grok's calls were refused with `held by turn_status seat 0, pid 22154, for 35 s`, which
Grok read as "seat 0's server holds the lock, waiting for that turn" and waited out; from then on three
alternating hand-offs (t0 Codex -> Grok, t1 Grok -> Codex, t2 Codex -> Grok) with both agents in
`finish_turn` at once, the waiting one returning 7-8 s after the other's `finish_turn` began, and the
lock file cycling between `a wait poll of seat 0` and `a wait poll of seat 1`. Grok's three parallel
calls at connect (`set_seat` + `turn_status` + `players`) each took 10 s: the in-process RLock queues
them, so a client that fires reads in parallel pays the acquire timeout, not a refusal.

**What one agent can see of the other through the harness: nothing.** Off-turn,
every tool except the waits, the notebook, `set_seat` and `exit_to_main_menu` answers `this seat is not
active`, so an agent cannot read the map, units, cities or digest during the other's turn. On-turn,
reads are gated by its own seat's visibility (89 `IsRevealed`/`IsVisible`/`HasMet` checks in the runtime,
events stamped with their audience at capture, one notebook per game and seat; 46 parity tests, 81
safety tests). The lock refusal at first named the other agent's tool and how long it had run (`held by
turn_status seat 0, pid 22154, for 35 s`); the user's call was that a human does not get to watch the
other player's cursor and guess intentions from polled click timings, so it now says `it is not your
turn while another seat acts` and nothing more, and names a call only when it is the contender's own
seat's (an earlier call, a one-shot server it forgot). The one hole was `set_seat`: it
accepted any human seat, so an agent could have taken the other's seat on its turn; a server started
with an explicit `--seat` now refuses that. Outside the harness they share a machine and a shell (save
files, logs, each other's transcripts), which the harness cannot police.

What confused the agents, from their own transcripts:

- **Codex had no MCP tools at first.** `codex mcp list` was empty; `.mcp.json` is Claude Code's format
  and `docs/AGENT_INSTALL.md` only shows that. Codex fell back to `mcp_call.py` and `harness.cli`, and
  its detached `exec_command` is what left the orphan in step 2. `mcp_call.py` should not be the
  documented fallback for waits; a one-shot process that holds a lock for minutes after its caller
  stopped listening is the worst caller of `wait_for_my_turn` possible.
- **Codex misread the refusal as health.** At 04:19:08 it concluded "the server confirms a wait
  operation is already active, so it is correctly holding the turn loop until Grok ends" and kept
  polling `turn_status`, which needs the same lock. The error text names no holder, no seat and no
  remaining time, so there was nothing to reason from.
- **Seat numbering.** The user says "player 1 / player 2" and "seat 2"; the harness says player ids
  0 and 1. Both agents resolved it (Grok's `set_seat(2)` was refused with `human_seats: [0, 1]` and it
  mapped itself to 1), but only after a failed call each.
- **Parallel tool calls.** Grok routinely fires 2-3 civ5 calls at once (`turn_status`+`players`,
  `set_production`+`move_unit`, `units`+`map_window`+`turn_digest`). Reads in parallel are harmless
  today only because they finish inside 10 s; an order next to a read is a coin flip.
- **Both agents spent turn time in the harness source.** Grok read `action_lock.py` and
  `mcp_server.py` from inside its turn; Codex grepped `harness/` four times. A refusal that said
  "seat 0's wait_for_my_turn holds the lock, 212 s left" would have kept them playing.

## Environment
- Game: Aspyr Linux port, `Civ5XP` 32-bit ELF, build 1.0.3.279 (Firaxis 403694). Stripped, but ~44k dynamic symbols
  incl. full Lua 5.1 C API and C++ class names (cvTunerListener, FSocket, Net*, ...).
- Game core is a real shared object (`libCvGameCoreDLL_Expansion2.so`), loaded dynamically.
- Assets live in `steamassets/assets/` (lowercase). DLC packages under `steamassets/assets/dlc/*` with `.civ5pkg`.
- User data: `~/.local/share/Aspyr/Sid Meier's Civilization 5/` (config.ini, Logs/, Saves/, MODS/, ModUserData/).
- Desktop: COSMIC on Wayland, `DISPLAY=:1`, `WAYLAND_DISPLAY=wayland-1`. Steam client running.
- Toolchain: python3.12, gcc/clang with -m32, gdb, strace. No xdotool/Xvfb/sqlite3 CLI.

## Multiplayer model (why a from-scratch network client is infeasible)
- Strings: "City/Unit/Plot out of sync", NetMapScriptCheck checksum, "EnableOutOfSyncDebugging" =>
  lockstep deterministic simulation; the network carries player commands only.
  A custom client would have to reimplement the whole rules engine to know the game state.
- Chosen approach: a *real game instance* is the LLM's client; we drive it via the FireTuner socket.

## FireTuner (the control channel) — VERIFIED
- `EnableTuner = 1` in config.ini `[Debugging]`. Game then LISTENS on TCP **0.0.0.0:4318** (all interfaces!).
  `Civ5App::Init` -> `cvTunerListener::Enable(FInetHostAddress, 4318)`. Re-armed on ExitToMainMenu /
  ExitingMultiplayerStagingRoom.
- If something else already holds 4318 at init the game ABORTS ("Terminating due to uncaught exception ... of type int").
  (Three early crashes were exactly this: my probe listener held the port.)
- Wire format: `uint32 LE len | int32 LE tag | payload\0`.
  - tag 4 `APP:`  -> "Civ5\0Sid Meier's Civilization V\0<path>\0Eric Jordan\0Jon Shafer\0Brian Wade"
  - tag 4 `LSQ:`  -> NUL-separated (id, name) pairs. ids are sparse (no id 1). One state per UI context.
  - tag 3 `CMD:<id>:<lua>` -> zero or more tag -1 `O\0<text>` (one per print line, prefixed "<Context>: "),
    then tag 3 `""` (done) or tag 3 `ERR:Syntax Error: ...` / `ERR:Runtime Error: ...` (with traceback).
  - `return` values are not echoed: use print(). JSON helper injected by harness/tuner.py (`query()`).
- Other tuner verbs seen in strings: KILLQRY, LISTSEL, STRACKERS, START_TRACKER, STOP_TRACKER, SET:, help/tree requests.
- State 0 = "Main State" (bare Lua, no Game/PreGame). UI contexts (FrontEnd, MainMenu, MultiplayerSelect,
  StagingRoom, InGame, ...) have the full UI Lua API (Game, Players, PreGame, Network, Matchmaking, UI, Controls...).
- Client disconnect handling: see "Connection lifecycle" below.

## Launching
- `steam.sh -applaunch 8930` works from a shell with the desktop env vars; Steam even registers a directly
  launched `./Civ5XP` as the game process. Direct launch (scripts/launch_civ5.sh) also starts fine.
- A second instance can be started while the first is running (Steam did not refuse).
- Time to main menu ≈ 45-60 s. Tuner port opens ~40 s after launch.

## Front-end automation (Lua globals in the respective contexts)
- MultiplayerSelect: `HotSeatButtonClick()` / `LANButtonClick()` / `InternetButtonClick()`.
- MPGameSetupScreen: `Controls.NameBox:SetText(..)`, `OnStart()` -> Matchmaking.HostHotSeatGame / HostLANGame.
- StagingRoom: `SetSlotToHuman(id)`, `PreGame.SetSlotStatus(id, SlotStatus.SS_COMPUTER|SS_TAKEN|SS_OPEN|SS_CLOSED|SS_OBSERVER)`,
  `PreGame.SetNickName`, `PreGame.SetCivilization`, `PreGame.SetHandicap`, `Network.BroadcastPlayerInfo()`,
  `PreGame.SetReady(localID, true)`, `LaunchGame()` -> Matchmaking.LaunchMultiplayerGame().
- Lobby (LAN): `Matchmaking.InitLanLobby()`, `Matchmaking.RefreshLANGameList()`, `Matchmaking.JoinIPAddress(ip)`,
  `Matchmaking.JoinMultiplayerGame(idx)`.
- Hotseat in-game: context `PlayerChange` (ingame/playerchange.lua) is a modal shown on GameplaySetActivePlayer;
  it pauses the game (Game.SetPausePlayer). `OnContinue()` dismisses it (password check via PreGame.TestPassword).
- End turn: actioninfopanel.lua `OnEndTurnClicked()`; MP uses Network.SendTurnComplete/HasSentNetTurnComplete.

## Verified in-game (2026-09-15, hotseat, seat 1 = "Claude")
- Launch MUST go through Steam's container runtime (scripts/launch_civ5.sh reproduces reaper + SLR soldier
  entry points + STEAM_COMPAT_* env). A bare ./Civ5XP reaches the menu but dies silently when hosting MP.
- Tuner toggles found and neutralised by the shim: OnMultiplayerGameLaunched -> Disable (NOP the call);
  EnteringMultiplayerStagingRoom is a tail-jump to Disable (patched to `ret`); ExitingMultiplayerStagingRoom
  re-arms (Disable+Enable => drops the client once; tunerd reconnects). OnExitToMainMenu also re-arms.
- Tuner command payload limit is between 2000 and 3000 bytes -> harness ships big Lua in 1500-byte string
  chunks and loadstring()s them (Game.load_lua). Query bodies must stay small.
- The hotseat hand-off modal is context "PlayerChange". `ContextPtr:IsHidden()` lies for modals; use
  `UIManager:IsModal(ContextPtr) and not Controls.MainContainer:IsHidden()`. While it is up the game is paused
  (Game.IsPaused()==true) and queued orders (CityPushOrder etc.) are NOT processed until `OnContinue()`.
- Working actions: MISSION_FOUND via SelectionListGameNetMessage; Game.SelectionListMove for moves;
  Game.CityPushOrder(city, ORDER_TRAIN, id, false, true, true); Network.SendResearch(id, 0, -1, false);
  Game.DoControl(GameInfoTypes.CONTROL_ENDTURN) ends the turn (AI turns run, next human seat gets PlayerChange).
- Events hooks that fired: SerialEventCityCreated (hex arg is {x,y} in a different coordinate space than plot x),
  NotificationAdded, GameplayAlertMessage, SerialEventUnitDestroyed (settler consumed).

## LAN mode (verified 2026-09-15, joined a friend's LAN game hosted on a Steam Deck)
- Second instance on one machine: `XDG_DATA_HOME` is honoured -> profile under `$XDG_DATA_HOME/Aspyr/Sid Meier's
  Civilization 5/` (seed config.ini with EnableTuner=1; the rest is regenerated). Steam does not refuse a second
  Civ5XP under the same account. scripts/launch_llm_client.sh = launch_civ5.sh + CIV5_DATA_HOME + CIV5_TUNER_PORT.
- Tuner port 4318 is an immediate in the binary; the shim now hooks `bind()` and remaps it (CIV5_TUNER_PORT) and
  can pin the bind address (CIV5_TUNER_BIND=127.0.0.1). Generic remap for other ports: CIV5_PORT_MAP=a=b,...
  Log line: `[tuner_fix] bind: port 4318 -> 127.0.0.1:4319`. One tunerd per instance (--port/--sock or env
  CIV5_TUNER_PORT / CIV5_TUNERD_SOCK; clients pick the instance with CIV5_TUNERD_SOCK).
- Front-end flow (context names as the tuner lists them): MainMenu `MultiplayerClick()` -> MultiplayerSelect
  `LANButtonClick()` -> creates contexts **Lobby** and MPGameSetupScreen. Lobby: `Matchmaking.RefreshLANGameList()`
  (async, ~2-4 s), `Matchmaking.GetMultiplayerGameList()` entries {serverID, serverName, MapName, numPlayers,
  maxPlayers, Players="nick@HOST, ..."}; `Matchmaking.JoinMultiplayerGame(serverID)` or `JoinIPAddress(ip)`.
  Join goes JoiningRoom -> StagingRoom; the StagingRoom context is live once `Matchmaking.GetLocalID() >= 0`.
  `PreGame.SetNickName(localID, ..)`, `PreGame.SetReady(localID, true)`, `Network.BroadcastPlayerInfo()`;
  ready flag is read with `PreGame.IsReady(i)` (there is no GetReady). SlotStatus: SS_OPEN=0 SS_COMPUTER=1
  SS_CLOSED=2 SS_TAKEN=3 SS_OBSERVER=4. The host launches; the tuner survives the launch thanks to the shim.
- LAN discovery from the second instance found the Deck's game on the first refresh (UDP broadcast); joining by
  serverID worked without any port remap for game traffic (only the tuner port collides on a shared machine).
- In a network game the local player IS the active player: `Game.GetActivePlayer()` = our seat (Game.detect_seat()).
  No PlayerChange modal. End turn = same `Game.DoControl(CONTROL_ENDTURN)`; afterwards `Network.HasSentNetTurnComplete()`
  is true and a second CONTROL_ENDTURN would *un-ready* us (actioninfopanel.lua), so Game.end_turn() refuses it.
  Turn options: GAMEOPTION_SIMULTANEOUS_TURNS, GAMEOPTION_DYNAMIC_TURNS, GAMEOPTION_END_TURN_TIMER_ENABLED.
- A host sitting in an observer slot is not `IsHuman()` -> not listed by H.net_players().
- Shim log on this build shows `ExitingMultiplayerStagingRoom: unexpected prologue; NOT patched` (harmless: that
  path only re-arms the listener; tunerd reconnects).

## Diplomacy / leader interactions (added 2026-09-15, mostly static analysis + safe live checks)
- Bug found and fixed in the existing harness: the `AILeaderMessage` event hook had its arguments in the
  wrong order. The real signature (matches leaderheadroot.lua's own handler on the same event) is
  `(iPlayer, iDiploUIState, szLeaderMessage, iAnimationAction, iData1)`; the hook had `msg`/`animation` in
  the position of `iDiploUIState`/`szLeaderMessage`, so every `leader_message` event in the digest recorded
  the numeric diplo-state as the "text" and the real message as "anim". Fixed in runtime.lua v4.
- Second bug found and fixed: `H.install_hooks()` was guarded by a boolean `H.installed_hooks` that
  **carries over** from the previous `H` table on every version bump (see the `H = {...}` constructor at
  the top of the file). That meant any code change *inside* a hook's callback (like the fix above) never
  actually took effect on an already-running game instance -- only a fresh InGame context (leave to menu,
  or relaunch) would pick it up, silently. Fixed by tracking each hook's closure in `H.hook_fns` and having
  `install_hooks()` `Events[name].Remove(prev)` + re-`Add` on every (re)injection, so a version bump always
  takes effect immediately and never double-registers. Verified live: after bumping to v4 on the running
  LAN instance, `H.hook_fns.AILeaderMessage` was non-nil and `H.version` read back as 4 without restarting
  the game or affecting turn state.
- **Diplomatic actions bypass the UI entirely**, same pattern as `move_unit`/`set_production`:
  `Game.DoFromUIDiploEvent(FromUIDiploEventTypes.<NAME>, otherPlayerID, data1, data2)` is the exact call
  the game's own leader-head and discussion-dialog buttons make (`ui/ingame/leaderhead/leaderheadroot.lua`,
  `.../discussiondialog.lua`). It needs no popup open, so the harness never has to detect or click through
  the leader-head screen -- it can act straight from the `leader_message` event text.
  - `FromUIDiploEventTypes` (37 keys) and `DiploUIStateTypes` (42 keys) are live, non-empty globals in the
    InGame Lua context -- confirmed by reading them read-only from the running game (no state changed).
  - Enum values confirmed live (read-only lookup, no event fired): `FROM_UI_DIPLO_EVENT_HUMAN_DECLARES_WAR`
    = 0, `FROM_UI_DIPLO_EVENT_HUMAN_NEGOTIATE_PEACE` = 1, `FROM_UI_DIPLO_EVENT_DENOUNCE` = 20.
  - Full enum list (from grepping this build's Lua for every `FromUIDiploEventTypes.*` and
    `Game.DoFromUIDiploEvent(...)` call site, prefix `FROM_UI_DIPLO_EVENT_` omitted below):
    `HUMAN_DECLARES_WAR`, `HUMAN_NEGOTIATE_PEACE`, `DENOUNCE`, `HUMAN_WANTS_DISCUSSION`,
    `HUMAN_DISCUSSION_WORK_WITH_US` / `_END_WORK_WITH_US` / `_DONT_SETTLE` / `_STOP_DIGGING` /
    `_STOP_SPYING` / `_STOP_SPREADING_RELIGION` / `_SHARE_INTRIGUE`, `COOP_WAR_OFFER` / `_RESPONSE` /
    `_NOW_RESPONSE`, `WORK_WITH_US_RESPONSE`, `WORK_AGAINST_SOMEONE_RESPONSE`,
    `AI_REQUEST_DENOUNCE_RESPONSE`, `PLAN_RA_RESPONSE` (research agreement), `DEMAND_HUMAN_REFUSAL`,
    `REQUEST_HUMAN_REFUSAL`, `AGGRESSIVE_MILITARY_WARNING_RESPONSE`, `EXPANSION_WARNING_RESPONSE` /
    `_SERIOUS_WARNING_RESPONSE`, `PLOT_BUYING_WARNING_RESPONSE` / `_SERIOUS_WARNING_RESPONSE`,
    `ATTACKED_MINOR_RESPONSE`, `I_ATTACKED_YOUR_MINOR_CIV_RESPONSE`, `BULLIED_MINOR_RESPONSE`,
    `I_BULLIED_YOUR_MINOR_CIV_RESPONSE`, `KILLED_MINOR_RESPONSE`, `KILLED_MY_SPY_RESPONSE`,
    `CAUGHT_YOUR_SPY_RESPONSE`, `STOP_CONVERSIONS`, `STOP_DIGGING`. `data1`/`data2` vary per event (mostly
    a button-choice id and/or a third-party player id) -- read the call sites in discussiondialog.lua for
    the exact meaning of a given event before firing it with non-zero data.
  - **NOT live-tested**: no diplomatic event was actually fired against the friend's shared LAN game (that
    would have altered a real shared game state -- declaring war, denouncing, etc. -- without asking them).
    Only the read-only pieces (enum presence, id values, plumbing with a bogus event name) were verified.
  - **Open question, not yet checked**: whether a lingering leader-head/discussion popup (if one is ever
    shown, e.g. after a genuine `HUMAN_WANTS_DISCUSSION`) blocks `Game.DoControl(CONTROL_ENDTURN)` or
    `Game.IsProcessingMessages()`. Since diplomatic actions are fired directly on the engine rather than by
    clicking through that screen, this shouldn't matter in practice, but it hasn't been provoked and
    observed live.
  - Item-based trade deals (gold/tech/resource exchanges, not just discrete yes/no diplomatic events) use a
    separate `CvDeal`-style object API (`ui/ingame/worldview/tradelogic.lua`, `.../diplotrade.lua`) that
    was not reverse-engineered in this pass -- out of scope for this round.

## Phase 1 action tools (added after a live crash, verified only via static analysis + a Lua syntax check)
- **The crash**: a raw `lua()` call probing for a city-ranged-attack API crashed Civ5XP outright mid-session.
  Root cause found: the real path is `Game.SelectedCitiesGameNetMessage(GameMessageTypes.GAMEMESSAGE_DO_TASK,
  TaskTypes.TASK_RANGED_ATTACK, x, y)` (see `dlc/expansion2/ui/ingame/worldview/worldview.lua`'s
  `CityBombard()`), and it must be preceded by `UI.SelectCity(city)` and guarded by
  `city:CanRangeStrike()` / `city:CanRangeStrikeAt(x, y, true, true)` -- the probe almost certainly skipped
  one of those guards. `H.city_ranged_attack` now does both checks before calling `GAMEMESSAGE_DO_TASK`.
- **Policy adoption**: `Network.SendUpdatePolicies(id, isPolicy, true)` -- `isPolicy=true` adopts an
  individual policy (`id` = `GameInfo.Policies` index, gated by `Player:CanAdoptPolicy(id)`); `isPolicy=false`
  unlocks a branch (`id` = branch index, gated by `Player:CanUnlockPolicyBranch(id)`). Confirmed in
  `dlc/expansion2/ui/ingame/popups/socialpolicypopup.lua` (`OnYes`/`PolicySelected`/`PolicyBranchSelected`).
- **Unit promotion**: NOT resolved this pass. `unitpanel.lua`'s `OnPromotionButton` only toggles UI
  visibility; no `Network.Send*`/`GAMEMESSAGE_*` call for actually picking a promotion was found in a grep
  across the whole `ui/ingame` tree. Needs a dedicated look at whatever registers each individual promotion
  button's callback (likely built dynamically per-instance, not a single named function) before adding a
  `unit_promotion` tool -- do not guess here given the city-ranged-attack lesson above.
- **New Lua-syntax safety net**: no `lua`/`luac` binary is installed (only the shared libs), but `pip install
  lupa` in a scratch venv gives a working embedded Lua 5.x via `lua.compile(source)` (parses without
  executing, so it works even though the file references Civ5-only globals like `Players`/`GameInfoTypes`
  that don't exist outside the game). Used to syntax-check `runtime.lua` before every push to a live game
  from now on -- catches typos/syntax errors, NOT bad API calls (those can only be caught by reading the
  game's own Lua first, as above, or by testing against a throwaway game).
- Trade routes / spies / religion: see ARCHITECTURE.md and the function docstrings in `runtime.lua`
  (`H.establish_trade_route`, `H.plunder_trade_route`, `H.available_trade_routes`, `H.spies`,
  `H.found_pantheon`, `H.found_religion`) -- all added this pass, none live-tested yet (no game was running
  after the crash). Verify all of them against a throwaway game before relying on them live.

## Two more live-only bugs found verifying Phase 1b/1c (runtime.lua v5 -> v8)
- **`_G` does not exist** in Civ5's UI Lua contexts (confirmed: `type(_G) == "nil"` in InGame) -- a
  generalised `H.enum_name(table_name_as_string, v)` that tried `_G[table_name]` silently failed every
  lookup (pcall caught the "index a nil value" error and cached an empty table). Fixed by passing the enum
  TABLE itself at each call site (`H.enum_name("EndTurnBlockingTypes", EndTurnBlockingTypes, v)`) instead of
  looking it up by name -- direct global references work fine, only `_G`-style dynamic-by-name indexing
  doesn't. The original hand-written `H.diplo_state_name` (before this generalisation) never had the bug
  for exactly this reason.
- That fix alone did not take effect: `H._enum_names` (the per-enum reverse-lookup cache) was carried over
  from the OLD `H` table across the version bump the same way `H.events`/`H.hook_fns` are -- so the stale,
  empty cache built by the buggy code survived the reinject and kept masking the fix. `_enum_names` is a
  pure cache with no unique state worth preserving (unlike events/hook closures), so it's now always reset
  to `{}` on every (re)injection instead of inherited. **General rule for this codebase going forward: only
  carry state across a RUNTIME_VERSION bump that is genuinely irreplaceable (accumulated event log, hook
  closures needed for `Events.X.Remove()`); anything re-derivable from live game state should start fresh
  every time, or a fix to how it's derived can silently never take effect.**
- **Wrong enum table entirely for game state**: `Game.GetGameState()` pairs with the global
  `GameplayGameStateTypes` (`GAMESTATE_ON`/`_EXTENDED`/`_OVER`), not `GameStateTypes` -- a different, real
  global that turned out to be the UI's screen/view state machine (`CIV5_GS_EXIT`/`MAIN_MENU`/
  `MAINGAMEVIEW`/`LANLOBBY`/...). The original research grep (`GameStateTypes\.[A-Z_]+`, no left boundary)
  silently matched the *tail* of the longer identifier `GameplayGameStateTypes.GAMESTATE_ON` and reported it
  as `GameStateTypes.GAMESTATE_ON`. Both tables happen to define a value `0`, so the bug was invisible until
  live-checked: `game_state_name` resolved to the confusingly-wrong-but-real name `CIV5_GS_EXIT` while
  mid-game, and `game_over` (`gs == GameStateTypes.GAMESTATE_OVER`, which is `gs == nil`) was **silently
  always false** -- the entire point of Phase 1c. Fixed by pointing both at `GameplayGameStateTypes`;
  confirmed live (`game_state_name` now reads `GAMESTATE_ON` while genuinely mid-game).
- Lesson reinforced: an unanchored grep across DLC Lua for an enum's usage can match a substring of a
  *different, longer* identifier and look completely plausible (real values, real-sounding names) while
  being entirely wrong -- static analysis here still needs a live check on the actual returned value/name
  before being trusted, not just "did the grep find something."

## Verification coverage this pass (what was and wasn't exercised live)
Exercised live against a fresh throwaway hotseat instance (not any shared game): turn_state's new
blocking_name/game_state_name/game_over fields (including catching and fixing the two bugs above),
choose_policy/unlock_policy_branch/city_ranged_attack/found_pantheon's precondition-guard and
unknown-name error paths (all return clean {ok:false, err:...} rather than crashing), spies(),
available_trade_routes(), and a full crash-detect-relaunch-rejoin cycle (harness/supervisor.py) including a
real bug fix (wait_for_main_menu needed its own retry loop; wait_state fails fast rather than blocking).
**NOT exercised**: the actual success path of city_ranged_attack / establish_trade_route / plunder_trade_route
/ found_religion / enhance_religion (all need real in-game preconditions -- a valid ranged-attack target, a
caravan and a discovered destination, accumulated faith, a founded religion -- that a few-minute throwaway
game doesn't have time to reach). Their failure/validation paths are confirmed safe; their success paths are
not yet confirmed to use the right constant names end-to-end. Verify each once before relying on it in a
real game, the same discipline that would have caught tonight's crash in the first place.

## Phase 3a trade deals: CRASHED on first live test -- disabled, not root-caused
`H.propose_deal`/`Game.propose_deal` (item-based trade deals via `UI.GetScratchDeal()`) is implemented in
runtime.lua/game.py but **deliberately NOT exposed** as an MCP tool or HTTP route: the very first live test
-- proposing a single `ALLOW_EMBASSY` item to the AI player, nothing exotic, no gold/resource amounts that
could hit an unvalidated-quantity edge case -- crashed the game process outright (`tuner socket closed by
game`; Civ5XP gone from the process list; no Lua-level error, meaning pcall never even got a chance -- a
native crash, the same signature as the city_ranged_attack incident that started this whole round of work).

Every individual piece of the sequence is confirmed-real API, read directly from
`ui/ingame/worldview/tradelogic.lua`: `UI.GetScratchDeal()`, `:ClearItems()`, `:AddAllowEmbassy(playerID)`,
`:SetFromPlayer()`/`:SetToPlayer()`, `UI.DoProposeDeal()` -- the same file's own `OnPropose()` calls this
exact sequence for both PVP and human-vs-AI trades. The leading hypothesis (not confirmed) is that
`UI.DoProposeDeal()` -- a `UI.*`-namespaced call, unlike the `Game.*`/`Network.*` calls that work fine
headlessly elsewhere in this harness (`Game.DoFromUIDiploEvent`, `Network.SendFoundPantheon`, etc.) --
assumes some UI/popup state exists (e.g. the trade-deal screen actually being open, a real `ContextPtr`)
that isn't true when invoked from a bare tuner `exec` outside any popup. Not yet bisected to confirm which
single call in the sequence is the fatal one, or whether it's `DoProposeDeal()` specifically vs. one of the
`Add*`/`Set*Player` calls before it.

**Do not re-expose `propose_deal` as a tool until this is root-caused** (bisect each call in isolation
against a throwaway game, the same discipline this whole file has been reinforcing all night) and confirmed
safe, or an alternative lower-level call (a `Network.Send*` equivalent, if one exists, the same pattern that
worked for `SendFoundPantheon`/`SendFoundReligion`/`SendUpdatePolicies`) is found instead.

## Phase 3a follow-up (2026-09-16): root cause found and fixed, not yet re-verified live
Re-reading `tradelogic.lua` end to end (both the pocket-population code and `OnPropose`) found the actual
gate the crash was missing: **every single `Add*` call in the real UI is only reachable through a pocket
button that gets populated by first calling `deal:IsPossibleToTradeItem(from, to, TradeableItems.TRADE_ITEM_*,
...)`** -- e.g. `IsPossibleToTradeItem(g_iUs, g_iThem, TradeableItems.TRADE_ITEM_ALLOW_EMBASSY, g_iDealDuration)`
at line ~1124, similarly for gold (~1057), GPT (~1095), open borders (~1180), defensive pact (~1234),
research/trade agreement (~1283/~1351), declaration of friendship (~1403), cities (~1440), resources
(~1529). An item that fails that check is never even offered to a human player to add. `H.propose_deal`
skipped this gate entirely and called `Add*` unconditionally, so the crashing test (a single `ALLOW_EMBASSY`
item) almost certainly built a deal containing an item that was **not actually valid** between those two
players (the AI already had an embassy, or embassy trading was disallowed for some other precondition) --
and `UI.DoProposeDeal()` then crashed natively on the invalid deal rather than the earlier hypothesis of
`UI.DoProposeDeal()` needing an open popup/ContextPtr (nothing in `OnPropose`'s human-vs-AI branch does
anything beyond `SetFromPlayer`/`SetToPlayer`/`DoProposeDeal()`, the same three calls this harness was
already making -- so that hypothesis doesn't hold up under closer reading).

**Fix (runtime.lua v10)**: `H.propose_deal` now calls `deal:IsPossibleToTradeItem(...)` with the correct
per-item-type argument shape (matched 1:1 against each pocket-population call site above) before every
`Add*`, and aborts the whole deal with a clean `{ok:false, err:...}` if any item fails. Also mirrors two
smaller guards from the real UI: `OnPropose` returns early on an empty deal (`GetNumItems() == 0`), and
`OnOpenPlayerDealScreen` refuses to open a second negotiation while `UI.HasMadeProposal(pid)` shows one
already outstanding to a different player. `PEACE_TREATY` has no `IsPossibleToTradeItem` gate in the real
UI either (it's added unconditionally when `IsAtWar` is true in `OnOpenPlayerDealScreen`), so that one guard
is `Teams[fromTeam]:IsAtWar(toTeam)` instead, matching the same precondition.

Syntax-checked with lupa (see Phase 1 entry above for the technique) -- passes. **NOT YET LIVE-TESTED**: no
game was running in this pass. Before re-exposing `propose_deal` as an MCP tool or HTTP route, verify live
against a throwaway game: (1) a deal with a genuinely valid `ALLOW_EMBASSY` item does not crash and the AI
responds, (2) a deliberately invalid item (e.g. embassy already established) is rejected with a clean
`{ok:false, err:"item not tradeable: ..."}` instead of crashing, (3) an empty `items` list and a duplicate
in-flight proposal both return clean errors instead of touching the engine.

## Phase 3a live verification (2026-09-16, same day): the IsPossibleToTradeItem fix works, but it was not
## the whole story -- crashed the game twice more, root cause is deeper than a missing validation gate
Ran the verification the previous entry called for, against three successive throwaway hotseat instances
(never touched the friend's shared LAN game -- an AI opponent is all `propose_deal` needs). Findings, in the
order they happened:

1. **The `IsPossibleToTradeItem` gate works as designed.** A deliberately-invalid `ALLOW_EMBASSY` (to an
   unmet player) came back a clean `{ok:false, err:"item not tradeable: ..."}`, no crash. Every other item
   type (`GOLD`, `GOLD_PER_TURN`, `RESOURCES`, `OPEN_BORDERS`, `DEFENSIVE_PACT`, `RESEARCH_AGREEMENT`,
   `TRADE_AGREEMENT`) also came back a clean rejection against a fresh turn-0 AI (none of their preconditions
   are met that early) without crashing anything -- confirms the read-only `IsPossibleToTradeItem` query
   itself is safe to call headlessly for every item type tried.

2. **Second bug found and fixed live**: proposing `DECLARATION_OF_FRIENDSHIP` to an AI crashed the game
   outright (`tuner socket closed by game`, process gone) -- this time the crash was *inside* (or immediately
   around) the `IsPossibleToTradeItem` call itself for that one item type. Re-reading tradelogic.lua's pocket
   population code found the reason directly: the DoF pocket block is the **only** item wrapped in
   `if (g_bPVPTrade) then ... end` (line ~1399, comment: "Only PvP trade, with the AI there is a dedicated
   interface for this trade") -- the real UI never even calls `IsPossibleToTradeItem` for this item type
   against an AI, let alone `Add*`. Fixed in runtime.lua v11: `H.propose_deal` now checks
   `Players[other_player]:IsHuman()` and refuses `DECLARATION_OF_FRIENDSHIP` for an AI recipient *before*
   touching the engine at all (use `H.diplo_event`/`Game.diplo_event` with a DoF-flavoured
   `FromUIDiploEventTypes` event against an AI instead -- that's the "dedicated interface" the comment means).

3. **Third crash, and the important one**: relaunched again, declared war on the AI (so `PEACE_TREATY`
   passes its precondition -- `IsAtWar`, the same guard the real UI uses since peace treaties have no
   `IsPossibleToTradeItem` gate), and called the real `Game.propose_deal(1, [{"type":"PEACE_TREATY", ...}])`
   end to end. **Crashed again**, same signature. Bisected by hand this time, one raw Lua call per step
   against a fourth fresh instance, checking the process was still alive after each: `deal:ClearItems()` --
   fine (proven safe many times over by this point); `deal:AddPeaceTreaty(0, ...); deal:AddPeaceTreaty(1,
   ...)` (both sides, exactly matching `OnOpenPlayerDealScreen`'s own sequence at lines 300-303, unlike
   `H.propose_deal`'s current one-sided `AddPeaceTreaty(from, ...)`) -- **this line itself crashed the game**
   (`tuner socket closed by game`, confirmed via `ps aux` after the log line). Never got to
   `SetFromPlayer`/`SetToPlayer`/`DoProposeDeal()` at all.

**This means the "missing IsPossibleToTradeItem gate" fix from earlier today, while real and worth keeping
(the *query* call is genuinely safe and rejects invalid items cleanly, verified above), does NOT make
`propose_deal` safe to use.** The actual mutating `deal:Add*()` call can crash the game outright even when
the item is legitimately valid (we were actually at war; both required sides were added, matching the real
UI's own call sequence exactly) and even though the read-only validity check for the exact same item/players
just returned true moments earlier. This resurrects -- and for `AddPeaceTreaty` specifically, *confirms* --
the original hypothesis this file dismissed in the "Phase 3a follow-up" entry above: that dismissal was
premature. The deal-mutation methods (`Add*`, and very possibly `UI.DoProposeDeal()` itself, not yet reached
in this bisection) most likely depend on native `CvDeal`/negotiation state that only gets initialized when
the real trade-deal screen (`ui/ingame/worldview/tradelogic.lua`'s own `ContextPtr`) is actually open --
`UI.GetScratchDeal()` returns a real object headlessly (confirmed: `:ClearItems()`, `:IsPossibleToTradeItem()`
never crashed), but mutating it outside that live UI context appears to corrupt or dereference something
that isn't there.

**Do not re-expose `propose_deal`, in its current `UI.GetScratchDeal()`/`Add*`/`UI.DoProposeDeal()` form, as
a tool or route.** The `IsPossibleToTradeItem` validation and the PvP-only DoF guard stay in runtime.lua
(genuinely correct, tested behavior for the read-only path, and cheap safety nets if this is ever revisited),
but three live crashes in one day against this call pattern -- one avoidable by better validation, two not --
is enough signal that this whole approach needs a different foundation, not another patch. Next step, if
this is picked up again: look for a `Network.Send*` equivalent the way `SendFoundPantheon`/`SendFoundReligion`
/`SendUpdatePolicies` worked around the same class of problem for other systems, rather than trying to make
`UI.*`-namespaced deal calls work from a bare tuner `exec`. Three fresh throwaway instances were
launched/crashed/relaunched for this pass (`propose_deal_test`, `propose_deal_test2`, `propose_deal_test3` in
`logs/`); all cleaned up, no shared/LAN game was ever touched.

## Diplomacy escape hatch (`H.diplo_event`/`declare_war`/`make_peace`/`denounce`) fixed and live-verified (2026-09-16)
`H.diplo_event` previously fired `Game.DoFromUIDiploEvent(...)` unconditionally and returned a blind
`{ok=true}` no matter what -- never live-tested (see previous docstring caveat). Live-testing against a
throwaway hotseat instance (`diplo_test` in `logs/`) found the same false-success shape this file has been
hunting all day for `propose_deal`: `Game.DoFromUIDiploEvent` does not error or reject an invalid war/peace
event, it just silently no-ops, so the old code reported success for actions that did nothing.

**Fix, in two passes** (runtime.lua v12 then v13, re-reading `leaderheadroot.lua`'s `OnShowHide`/`OnWarOrPeace`
each time): v12 added `CanChangeWarPeace` (button-visibility gate) plus each direction's own precondition --
`GetNumTurnsLockedIntoWar(otherTeam) > 0` for peace, `IsForcePeace`/`CanDeclareWar` for war. Live-testing v12
immediately found the gap: `make_peace` against a player never met and never at war still returned
`{ok=true}` because `CanChangeWarPeace` and a 0 locked-war-turn count are both trivially true when no war
has ever happened. v13 added the missing `IsHasMet` precondition (the leaderhead screen this logic lives on
can't even open without it) and made the `IsAtWar` branch explicit, matching `OnWarOrPeace` exactly: peace
requires `IsAtWar == true`, war requires `IsAtWar == false`.

**Live-verified sequence** (fresh hotseat vs. 5 AI, seat 0/Korea targeting player 1/Babylon, no crashes at
any step): `make_peace` before meeting -> clean reject ("not at war with this player" -- caught before even
checking met-ness, since not-at-war is true either way; a not-yet-met target hits this same branch).
`Teams[0]:Meet(1, false)` (test-only bootstrap -- `MakeHasMet` isn't exposed to InGame Lua in this build;
`Meet` is, confirmed via metatable introspection: `getmetatable(Teams[0]).__index` listed
`GetHasMetCivCount`/`Meet`/`IsHasMet`/`HasMetHuman`) -> `diplomacy()` correctly flips `met: true`.
`make_peace` while met-but-at-peace -> clean reject ("not at war with this player"). `declare_war` while
met-and-at-peace -> `{ok:true}`, and `diplomacy()` confirms `at_war: true` immediately after. `declare_war`
again while already at war -> clean reject ("already at war with this player"), no double-declare sent.

**Important nuance for future sessions (and the reason this entry exists)**: `make_peace` called
*immediately* after the war declaration above still returned `{ok:true}` -- `GetNumTurnsLockedIntoWar`
read `0` right after declaring, so the v13 lock gate did not block it. The proposal reached the AI and was
(correctly, per `diplomacy()` still showing `at_war: true` afterward) not accepted. This matches what the
user flagged from prior play experience: after declaring war on a player, peace proposals toward that same
player get rejected by the game for roughly the next 10 turns. **That rejection is the AI's own
diplomatic-acceptance logic, not a `GetNumTurnsLockedIntoWar` button-lock** -- our gate mirrors the real
UI's button-enable state correctly (and that button really is enabled with 0 locked turns in this build/
ruleset right after a human-initiated declaration), but the UI enabling the button only means you're
*allowed to ask*, not that the AI will say yes. Don't misread a live `make_peace` test that "does nothing"
as a harness bug: check `diplomacy()`'s `at_war` field to see whether peace actually landed, and expect AI
refusals for a number of turns after any war declaration as normal, unfixable-on-our-end behavior.

`denounce` has no equivalent precondition in `discussiondialog.lua` (`OnDenonceConfirmYes` goes straight
from a confirm click to `DoFromUIDiploEvent`) and was left unguarded; fired cleanly against a met AI with no
crash. Runtime bumped to v13. Test instance (`diplo_test` in `logs/`) launched, driven via ad-hoc scripts
(not checked in), and fully torn down afterward -- no shared/LAN game touched. `declare_war`/`make_peace`/
`denounce` can now be considered safe to keep exposed as MCP tools/HTTP routes; `propose_deal` is still
disabled per the entry above.

## `propose_deal`: external research confirms the dead end, closing this out for now (2026-09-16)
Before spending more live-crash budget on `propose_deal`, checked for prior art instead of re-bisecting:

- **CivFanatics ["How to Force a Deal?"](https://forums.civfanatics.com/threads/how-to-force-a-deal.640218/)**
  (a modder hitting the exact same wall in 2018): no one in the thread found a Lua-only way to finalize an
  arbitrary `Deal` (gold/resources/embassy/etc). The one working pattern that emerged is unrelated to
  `Deal`/`UI.GetScratchDeal()` entirely -- `Teams[x]:MakePeace(y)` + `Teams[x]:SetPermanentWarPeace(true)`,
  a DLL-level *forced* peace with no AI consent involved, used for scripted scenario events. That's a
  different primitive than what `H.propose_deal`'s `PEACE_TREATY` item wants (a negotiated peace the AI can
  still evaluate) and doesn't help with economic items at all, but is worth remembering if a "hard reset to
  peace" tool is ever wanted (e.g. an admin/debug override, not a diplomacy action an LLM seat would call
  normally).
- **[Category:Civ5 Trade API](http://modiki.civfanatics.com/index.php?title=Category:Civ5_Trade_API)** (the
  full indexed list of `Deal.*`/`Team.*`/`Player.*`/`UI.*` trade functions): confirms there is no
  `Game.`/`Network.`-namespaced entry point into the deal system at all -- `UI.GetScratchDeal()` is the only
  documented way to obtain a `Deal` object, and finalizing one goes through `UI.DoProposeDeal()` /
  `UI.DoFinalizePlayerDeal()`, both `UI.*`-namespaced. There is no `SendFoundPantheon`-style `Network.Send*`
  sibling for deals to fall back to, unlike religion/policies.
- **[civ6-mcp](https://github.com/lmwilki/civ6-mcp)** (an existing, much larger MCP project doing the same
  FireTuner-based approach for Civ **VI**, found while looking for prior art on this project generally):
  Civ6 exposes a proper `DiplomacyManager`/`DiplomacySession` API built for exactly this kind of headless
  proposal-and-response flow, and civ6-mcp's `build_propose_trade`/`build_propose_peace` use it directly with
  no reported crash class like ours. That's a real engine-level difference between the two games, not a
  technique this harness was missing -- Civ5's Lua API for trade genuinely never got an equivalent, headless
  entry point. (Also worth a look for other design ideas -- it has a much larger surface, including a
  turn-blocker-resolution loop and a full eval framework, of a similar shape to `harness/supervisor.py` and
  the "blocking_name" fields here.)

**Conclusion: closing this out as a Civ5 engine limitation, not a solvable harness bug.** `propose_deal`
stays disabled/unexposed. If revisited, the only two remotely promising directions are (1) a DLL mod (out of
scope for this project, which is Lua/tuner-only by design) or (2) actually driving the real trade-screen
popup open (`LeaderHeadRoot`/`DiscussionDialog`'s `ContextPtr`) via tuner exec before touching `Deal`, so the
native code sees the UI state it expects -- unverified, likely to cost another crash or two to test, and not
attempted this pass.

## Live-play session (2026-09-16): found a real tuner-drop bug in multi-human hotseat, root-caused

Launched a throwaway instance (`playtest_session` in `logs/`) and drove it end-to-end through `harness.game.Game`
(no MCP client attached -- scripted directly, same calls the tools wrap) to exercise turns for real rather than
via a single short live-test. Intent was to reach the still-unverified success paths (`establish_trade_route`,
`plunder_trade_route`, `found_religion`/`enhance_religion`, `city_ranged_attack`); didn't get there this pass,
but surfaced a more fundamental issue first.

**What happened**: `host_hotseat(human_seats=[0, 1], ...)` (both seats human, rest AI -- 6 players total:
Sweden/us, Korea/us, Arabia, The Celts, Austria, The Aztecs) launched fine. Scripted through turn 0's blockers
in sequence (`ENDTURN_BLOCKING_UNITS` -> found city / fortify, `ENDTURN_BLOCKING_PRODUCTION` -> train a
warrior, `ENDTURN_BLOCKING_RESEARCH` -> pick a tech) for player 0, ended their turn cleanly, then did the same
for player 1. After player 1's `end_turn()` returned `{ok:true}`, the game never advanced: ~380 further polls
over several minutes all showed `active_player=1`, `turn=0`, `blocking_name=NO_ENDTURN_BLOCKING_TYPE`,
`processing=false` -- i.e. nothing indicated a problem, `end_turn()` kept returning `ok:true`, but the actual
game state was frozen. The loop exited normally (hit its iteration cap) rather than erroring, so this would
look like a silent hang to anything polling the same way (including `wait_for_my_turn`, which uses the same
`turn_state()` fields and would spin forever here without a `TimeoutError`, since every read reports `my_turn`
truthy-looking and no blocker).

**Root cause, found in `tunerd.err` and the shim's own log**: the tuner connection to the game genuinely dropped
partway through this (`[tunerd] game connection dropped; will reconnect (game must re-arm its listener)`,
timestamped well after the scripted turns had been running). `logs/playtest_session.err` explains why: this
launch's `[tuner_fix]` patch pass logged
```
EnteringMultiplayerStagingRoom at 0x897c378 -> ret
ExitingMultiplayerStagingRoom: unexpected prologue; NOT patched
patched call Disable() at 0x897bdb4 (OnMultiplayerGameLaunched+0xa4)
```
`shim/tuner_recv_fix.c`'s own comment on `ExitingMultiplayerStagingRoom` (line ~140): "tail-jumps to Disable();
... re-arms the listener (dropping the current client)". The shim tries to neutralize all three known
Disable()-triggering paths (`EnteringMultiplayerStagingRoom`, `ExitingMultiplayerStagingRoom`,
`OnMultiplayerGameLaunched`'s internal call), but `ExitingMultiplayerStagingRoom`'s prologue didn't match the
expected byte pattern in this build/run and the safety check refused to touch it -- so that one path stayed
live and, whenever the game happened to call it, dropped the tuner client exactly as observed. The gap between
"turn genuinely froze" (stale-looking success responses, no error) and "tunerd logs an actual drop" a few
minutes later is consistent with the OS-level TCP connection lingering half-open for a while after the game
side already stopped servicing it.

**Not yet confirmed**: the exact in-game trigger for the call (its name suggests staging-room exit, which
should only fire once at game launch, not mid-game at a hotseat `PlayerChange` hand-off -- but the timing here
points at player 1's turn-end/hand-off specifically). Worth confirming with a fresh instance: launch, immediately
check `playtest.err` for the same "unexpected prologue" line, then watch whether the tuner drops at the very
first hotseat hand-off rather than later.

**Impact / next steps**: this is a real gap in `harness/supervisor.py`'s crash-recovery coverage -- it watches
for the reaper process dying, not for "process alive, tuner silently wedged/dropped mid-poll returning stale
success". `wait_for_my_turn`/any polling loop needs either a liveness check (e.g. a monotonically-increasing
counter or a `ping` roundtrip with a tight timeout) distinct from "the last query happened to return ok", or
`tunerd`'s `ping` op (already exists: `{"ok":true,"connected":...}`) should be polled alongside `turn_state()`
so a dropped `connected:false` state surfaces immediately instead of silently. Fixing the shim's byte-pattern
match for `ExitingMultiplayerStagingRoom` in this Aspyr build revision (dump the actual prologue bytes at that
symbol and compare against the assumed `e8 00 00 00 00 58`) would remove the root cause entirely; not attempted
this pass -- requires disassembling the live binary to find the real prologue, out of scope for a live-play
session. Instance torn down after diagnosis (tuner unreachable, nothing more to learn from it); the
trade-route/religion/ranged-attack verification gaps from the "Verification coverage" section above are still
open for a future session, ideally against a build where this patch succeeds.

## Shim fix, root-caused and live-verified (2026-09-16, same day)

Disassembled the installed binary (`nm -D` for the address, `objdump -d -M intel`) instead of guessing.
`EnteringMultiplayerStagingRoom`'s entire body really is `call next; pop eax; add eax,...; lea eax,[...];
jmp eax` resolving into `Disable()` -- exactly the PIC prologue `patch_ret()` checks for, which is why it
already patched fine. `ExitingMultiplayerStagingRoom` is a real function (`push ebx; push edi; push esi;
sub esp,0x30`, not the `e8 00 00 00 00 58` pattern) that checks two flags, conditionally rebuilds an
`FInetHostAddress`, calls `Disable()` at `+0x46` (confirmed: `897c3d2: e8 43 fd ff ff call 897c11a
<Disable>`), then re-arms the socket -- that one `call Disable` is the actual drop, not the whole function.

**Fix**: added `patch_call_to_disable()` (factored out of the existing `OnMultiplayerGameLaunched`
scan-and-NOP logic) and used it for `ExitingMultiplayerStagingRoom` too, instead of the whole-function
`patch_ret()` that could never match its prologue. `EnteringMultiplayerStagingRoom` still uses `patch_ret`
(correct for it). Rebuilt `shim/libtuner_recv_fix.so`; fresh launch now logs all three as patched:
```
EnteringMultiplayerStagingRoom at 0x897c378 -> ret
ExitingMultiplayerStagingRoom: patched call Disable() at 0x897c3d2 (+0x46)
OnMultiplayerGameLaunched: patched call Disable() at 0x897bdb4 (+0xa4)
```
**Live-verified**: same hotseat setup as the bug report (human_seats=[0,1] + 4 AI), scripted through turns
0->1->2 with the exact same polling loop that stalled forever before -- this time `active_player` changed
away from p1 well within a few polls each time, turn count advanced normally, no stale `ok:true` responses.
Instance torn down clean afterward. `docs/lua_command_patterns.md`/anywhere else referencing the old
"NOT patched" behavior should be considered stale if it exists (not checked this pass).

**Still open**: the broader liveness-check gap this bug exposed (`wait_for_my_turn`/pollers can't currently
tell "quiet turn" from "tuner silently gone" without this specific root cause fixed) is now moot for *this*
cause, but the same class of bug could recur on a different Aspyr build/patch revision where these prologues
differ again -- `patch_call_to_disable` degrades safely (logs "NOT patched", touches nothing) if its scan
doesn't find a matching call, so a future occurrence would at least be diagnosable the same way this one was,
but still worth adding the `ping`-based liveness check as defense in depth. Not done this pass.

## `wait_for_my_turn` liveness check added (2026-09-16, same day)

Closed out the "still open" item above. `tunerd`'s `ping` op already reported `connected: bool` with no
lock/reconnect side effect (`Bridge.handle` short-circuits on it before touching `self.client`), it just
wasn't polled anywhere in the Python side's turn-wait loop. Added `Civ5.ping()` (`harness/client.py`) and a
new `TunerConnectionLost(TunerdError)` exception -- subclassing `TunerdError` rather than adding a new type
everywhere means the existing `except TunerdError` handlers in `cli.py`/`mcp_server.py`/`http_server.py`/
`supervisor.py` all pick it up with zero changes to those files.

`Game.wait_for_my_turn` (`harness/game.py`) now calls `self.c.ping()` once before the loop and again each
iteration alongside `turn_state()`; if `connected` flips `True -> False` between two polls, it raises
`TunerConnectionLost` immediately instead of continuing to poll `turn_state()` (which, per the bug above, can
keep returning stale-looking `{ok:true}` data for a long time after the underlying drop). This doesn't fix a
root cause -- it's exactly the defense-in-depth the prior entry called for, so a *different* build/revision
where the shim's byte-pattern patch fails again degrades to a fast, clear error instead of a silent multi-
minute hang.

**Verified against a fake tunerd** (no real game instance -- a throwaway Unix-socket server standing in for
`tunerd`'s `ping`/`exec`/`query` ops, driven straight through `Game`/`Civ5`, script not checked in): normal
case returns `turn_state()` as soon as `my_turn` flips true; a scenario that flips the fake server's
`connected` flag mid-poll (`turn_ready_after` set high enough that turn-readiness can't be the reason it
returns) raises `TunerConnectionLost` within one poll interval instead of running to `timeout`. Not
live-tested against the real game/tuner-drop scenario itself (that requires reproducing the actual
`ExitingMultiplayerStagingRoom` drop, which the shim fix above just closed for this build) -- worth a real
live-play pass if the drop class ever recurs on a different build, to confirm this actually shortens the
failure from "silent hang" to "clear error" in practice, not just in the fake-server harness.

## Fake-tunerd liveness test checked in (2026-09-16, follow-up session)

The prior entry's "script not checked in" fake-tunerd test surfaced a false negative in the same session it
was written (never landed): the drop scenario failed because `turn_ready_after` (~3 queries, ~0.2s at the
0.1s poll interval used) fired *before* the scheduled connection drop (0.3s), so `wait_for_my_turn` returned
normally before the drop branch could ever be reached -- an artifact of that script's own timing knobs, not
a bug in `wait_for_my_turn` (re-reading `harness/game.py`: `ping()` is polled and checked before
`turn_state()` on every loop iteration, so a drop that precedes readiness was always going to be caught).

Rewrote and checked in as `tests/test_liveness.py` (stdlib `unittest`, no new dependency -- the project has
no test framework configured yet): `FakeTunerd` handles `ping`/`exec`/`query` over a real Unix socket so
`Game`/`Civ5` are driven unmodified. `test_drop_before_turn_ready_raises` schedules the drop on the very
first `ping` (turn only becomes ready on the 3rd `query`), unambiguously exercising the raise path;
`test_normal_turn_ready_returns` is the control. Both pass (`python -m unittest tests.test_liveness -v`).
Still not live-tested against a real tuner drop (same caveat as above); this closes the "fake-server
harness" gap the prior entry left open, not the live-verification one.

## `scripts/play_loop.py` checked in; live-verified through turn 34; new `ENDTURN_BLOCKING_STACKED_UNITS` finding (2026-09-16, follow-up session)

Several previous sessions each wrote an ad hoc heuristic play loop from scratch to stress-test the harness
unattended (find bugs like the promotion/pantheon/stacked-unit ones above) and never checked it in. Rewrote
it once as `scripts/play_loop.py`: seat 0 only (see below for why that's the "single player" setup),
candidate-list heuristics for promotions/policies/pantheon beliefs/research/production (each candidate is
validated by the harness's own `Can*` guard before doing anything, so trying an unavailable one is a safe
no-op, not a risky guess), and a `--stall-limit` that exits cleanly with the full `turn_state` logged instead
of spinning forever when a blocker can't be resolved -- that exit is meant to be a diagnostic signal for the
next session, not just a failure.

**"Single player against AI" in this harness is `host_hotseat(human_seats=[0])`, not a real single-player
game.** The architecture note at the top of this file (and the project memory) already establishes that the
harness always drives the game through the multiplayer plumbing (hotseat/LAN) because that's what provides
the `Network.Send*` messages every action tool depends on -- there's no separate code path for the vanilla
single-player game type. `host_hotseat` with exactly one seat in `human_seats` is functionally identical to
single-player-against-AI (`PreGame.IsHotSeatGame()` is still true, but nothing ever sets another seat human,
so every other slot stays AI and there's no second hotseat hand-off) -- this is the right way to run an
unattended session without a human turn to wait on, not a corner case of `mode()`'s `'single'` string (which
is a fallback label in `H.turn_state`, never actually reachable from any of this harness's own hosting paths).

**New finding, live-verified**: `ENDTURN_BLOCKING_STACKED_UNITS` does NOT clear via `unit_mission()` with
`MISSION_SKIP` or `MISSION_FORTIFY`, even though the call returns `{ok:true}` either way and looks identical
to the call that reliably clears plain `ENDTURN_BLOCKING_UNITS` for a single idle unit. Reproduced at turn 18
with two idle Workers sharing the capital's own city tile: repeated `MISSION_SKIP` pushes left
`GetActivityType()`/`IsReadyToMove()`/`GetEndTurnBlockingType()` completely unchanged after 20+ attempts.
What actually cleared it: physically relocating one Worker off the tile with `move_unit()` -- confirmed live,
`blocking_name` flipped from `STACKED_UNITS` to plain `UNITS` for the one remaining idle unit immediately.
This also disproves an assumption an earlier draft of `play_loop.py` made (unit stacking is always legal on
a city tile, so only handle it for units in the open) -- empirically false: the blocker fired for two
Workers standing in the capital, and only moving one away resolved it, city tile or not. `play_loop.py`'s
`resolve_stacked_units` now always tries to move a unit off a shared tile first (any tile, including a city)
and only falls back to giving orders in place. Not root-caused via disassembly/Lua source this pass (unlike
the shim fix above) -- just empirically characterized through live trial and error; a real root cause would
need to find whatever check in the engine's end-turn validation specifically inspects tile occupancy for
this blocking type (distinct from whatever it checks for the plain `UNITS`/`UNIT_NEEDS_ORDERS` cases).

**Live run**: fresh single-seat hotseat game, turn 0 -> 34 in a single unattended background run (about 15
real minutes wall clock including two restarts to fix the play_loop.py bugs above), founded the capital,
adopted two Tradition policies, researched five early techs, recovered from the stacked-units blocker twice
without intervention after the fix above. Left running in the background past turn 34 for further
unattended stress-testing; no game crash this pass. Blockers this heuristic bot has no handler for yet
(will exit via `--stall-limit` with a clear log if hit): `ENDTURN_BLOCKING_CHOOSE_IDEOLOGY`,
`ENDTURN_BLOCKING_ADD_REFORMATION_BELIEF`, `ENDTURN_BLOCKING_DIPLO_VOTE`,
`ENDTURN_BLOCKING_LEAGUE_CALL_FOR_PROPOSALS`/`_VOTES`, `ENDTURN_BLOCKING_MAYA_LONG_COUNT`,
`ENDTURN_BLOCKING_MINOR_QUEST`, `ENDTURN_BLOCKING_STEAL_TECH`, `ENDTURN_BLOCKING_CHOOSE_ARCHAEOLOGY`,
`ENDTURN_BLOCKING_FAITH_GREAT_PERSON`, `ENDTURN_BLOCKING_FREE_POLICY`/`_TECH`/`_ITEMS`,
`ENDTURN_BLOCKING_CITY_RANGE_ATTACK` -- none of these have a harness tool to resolve them yet; add one
following the `choose_promotion`/`choose_policy`/`found_pantheon` pattern (find the real
`Network.Send*`/direct-engine-state call the popup's own confirm button makes, guard it with the same
precondition the popup itself checks) if one of these actually gets hit.

## Playing manually turn-by-turn (not via play_loop.py); several real API bugs found and fixed (2026-09-16, follow-up session)

Stopped `play_loop.py` (it was still running unattended, turn 92+ at session start) and played turns 52-63
by hand, driving `harness.game.Game` the same way an MCP-tool-calling LLM would (no MCP client was attached
this session -- `.mcp.json` lives in this repo but the session's cwd was one level up at start, so the
`civ5` server was never loaded; drove the exact same `Game` methods the MCP/HTTP wrappers call instead).
Playing manually immediately surfaced problems the heuristic loop's narrow retry logic never would have
hit, because it only ever tries the same few things:

**The save was in a bad state**: turn 52, one city (pop 4), *seven* Workers, capital about to build an
eighth, capital growth stalled at `growth_turns: 2900` (never growing). Root cause, confirmed by reading
`scripts/play_loop.py`: idle Workers only ever get `MISSION_SKIP` (see `resolve_units_need_orders`) --
`play_loop.py` never once issues a `MISSION_BUILD`. 40 turns of unattended play produced zero tile
improvements. Fixed by hand: reassigned the surplus Workers to real builds (farm/mine/camp/roads),
redirected the capital's production from Worker #8 to a Settler, and founded a second city (Busan) by
turn 62 -- growth_turns dropped from 2900 to 11 once a farm actually finished.

**`unit_mission`'s `x`/`y` params silently swallowed `MISSION_BUILD`'s build-type id.** The underlying call
is `Game.SelectionListGameNetMessage(msg, mission, iData1, iData2, iFlags, ...)`, wired to this wrapper's
`(x, y, data2)` in that order -- so a build-type id passed as `data2` (reads like "the extra data slot for
this mission") actually lands in `iFlags`, which `MISSION_BUILD` ignores. Every one of those calls returned
`{ok:true}` and did nothing (`GetBuildType()` stayed -1). Root-caused live by comparing `u:GetBuildType()`
before/after. Fixed in `harness/game.py`: `unit_mission` now takes a `build=` kwarg that puts the id in the
correct `iData1`/`x` slot, and verifies `GetBuildType() != -1` afterward instead of trusting the unconditional
`{ok:true}`. Threaded through to the MCP tool and the HTTP `/unit_mission` route (`UnitMission.build`).

**`set_research`'s free-tech bug (previously diagnosed, never fixed) was live-reproduced and fixed.** Same
root cause as the session that first found it: `Network.SendResearch(id, 0, -1, false)` hardcodes 0 for the
"free techs" argument; the real UI (`techtree.lua`) always passes `player:GetNumFreeTechs()`. With a free
tech pending (this game had one banked from an early ruins pop), the hardcoded 0 makes the call silently
no-op -- `{ok:true}` comes back, `GetCurrentResearch()` stays -1, and `end_turn` refuses to advance with no
visible error (`ENDTURN_BLOCKING_RESEARCH` just persists). Fixed in `harness/game.py`: passes
`p:GetNumFreeTechs()`, checks `IsHasTech` up front (a second silent-no-op case: requesting an
already-researched tech), and verifies `GetCurrentResearch()` actually changed afterward. Note while
testing: requesting `TECH_CURRENCY` (prereqs not yet met) set current research to `TECH_MATHEMATICS`
instead -- the engine substitutes the nearest unresearched prerequisite rather than erroring, so success is
checked as "research changed to *something*", not an exact id match.

**`set_production` has the same class of bug**: `Game.CityPushOrder` accepts and silently drops an invalid
order. Reproduced live requesting `BUILDING_MONUMENT` a second time (already built): `{ok:true}` came back
but the queue never changed (`production` empty, `turns` stuck at the `2147483647` "nothing queued"
sentinel). Fixed by checking the matching `CanConstruct`/`CanTrain`/`CanCreate`/`CanMaintain` guard up front.

**Async/stale-read pattern, generalized.** The existing `wait_for_my_turn` liveness fix from earlier today
fixed one instance of this; the same pattern showed up in three more places this session, all fixed the
same way (issue the command, then poll briefly for the state to actually change before trusting a read
taken in the same Lua call as the mutation):
- `move_unit`: `u:GetX()/GetY()` read in the same call as `Game.SelectionListMove` reports the *pre-move*
  position -- confirmed live (moved a unit two tiles, immediate read said "didn't move", re-read 2s later
  showed it had). Now polls up to `settle_timeout` (default 1s) for position/moves to change.
- `set_production`: see above -- `GetProductionNameKey()` read in the same call as `CityPushOrder` reports
  the *previous* head-of-queue item. Now re-reads after a 0.3s settle delay.
- `set_research`: same shape, same fix.

**`MISSION_FOUND` issued with 0 moves left does not persist to the next turn.** Moved a Settler its full 2
tiles this turn (using both `move_unit` then `unit_mission(..., 'MISSION_FOUND')` as two separate calls --
the move used up all its moves), and the mission showed as queued (`GetActivityType() == 1`) at the moment
it was issued. Next turn: the settler was back to idle (`GetActivityType() == 0`) with full moves and
`CanFound() == true` again -- the queued FOUND had been silently dropped, not carried over and
auto-executed once moves refreshed, unlike a Worker's `MISSION_BUILD` (which *does* persist and resume
across turns, confirmed separately this session). Re-issuing `MISSION_FOUND` once moves were actually
available worked immediately. Practical implication for a caller: don't issue `MISSION_FOUND` (or
presumably other action missions, unverified) right after a move that exhausts movement in the same call
sequence -- check `MovesLeft() > 0` first, or issue found on a separate turn.

**`plots_around` overflows the tuner's output channel once enough of the map is revealed**, failing with
`no JSON sentinel in output: ['O']` -- not a Lua error, a transport-level truncation (the JSON response
itself gets cut mid-stream). Radius 3 (~35 tiles) was reliable all session; radius 5/6 worked early in the
session (~15 minutes into it, before much fog had been cleared by the workers/warrior/settler moving
around) and then started failing later once more terrain was visible, i.e. this is response-size-dependent,
not a fixed radius cap -- the same radius that works right after a fresh game start can fail later in the
same game. Not fixed this pass (would need `client.py`/`tunerd.py` to chunk large responses); worked around
by using smaller radii and re-centering the query near the area of interest instead of one big radius.

**Live-verified working this session, no bug**: `unit_mission(..., build="BUILD_FARM")` on a *forested*
tile auto-chains through `BUILD_REMOVE_FOREST` first and (if left alone) continues to the originally
requested improvement afterward -- `GetBuildType()` correctly showed the forest-removal step's id, not a
failure, while the mission was still in progress. Don't mistake this for the swallowed-data2 bug above:
check whether the *reported* build type is a forest/jungle/marsh-removal type before concluding a build
request failed.

**Game crashed mid-session (2026-09-16 ~14:14 local), cause not identified.** `tunerd`'s connection dropped
(`ConnectionResetError`) immediately after a routine `move_unit` call (the Warrior, marching from Seoul to
reinforce Busan against a Barbarian Galley raid) -- the *next* Lua command in the same script never even
reached the log, and `Civ5XP` was gone from `ps` afterward (not just a tuner-listener drop the shim could
recover from, per the existing `ExitingMultiplayerStagingRoom`-triggered-disconnect class of bug -- the
whole process exited). This was NOT an unguarded raw `lua()` probe (the known cause of the one previously
documented crash) -- every call in the sequence leading up to it was a previously-exercised, already-working
wrapper method (`move_unit`), called the same way it had been successfully called a dozen+ times already
this session. The crash coincided with active combat (a Barbarian Galley had just bombarded Busan down to
198/200 HP the same turn, and a `city_ranged_attack` had just been fired back at it) -- plausible but
unconfirmed that combat-animation/resolution processing concurrent with tuner traffic is implicated; no
crash dump was found (`ps`/`dmesg` checked, nothing under the game's data dir either). Worth watching for a
repeat under similar conditions (active combat + simultaneous tuner queries) to narrow this down further;
not enough signal yet to turn into a guarded workaround the way the `ExitingMultiplayerStagingRoom` shim fix
was.

## `quick_save` added; two more UI-popup blockers found (leader greeting, tech popup); a SECOND unexplained crash (2026-09-16, same session, after a restart)

Restarted with a fresh hotseat game (turn 0) after the crash above, since hotseat can't auto-rejoin. The
user watched the actual screen live and caught two things the harness gave no signal about at all:

**No way to save at all.** Added `quick_save()` (`harness/game.py`, MCP tool, HTTP `/quick_save`) wrapping
`UI.QuickSave()` -- same call as `gamemenu.lua`'s Quick Save / F5. Live-verified it writes a real file
(`Saves/single/quick/QuickSave.Civ5Save`, one slot, overwritten each call -- not versioned history, just
crash insurance). No load counterpart existed yet either -- see the `Events.PlayerChoseToLoadGame` entry
below, added later this same session.

**LeaderHeadRoot popup (a leader-greeting screen) silently hung `wait_for_my_turn` to its full timeout.**
Germany made first contact; the popup came up; `turn_state()["my_turn"]` stayed `false` the entire time
(confirmed live) with nothing in `turn_state`/`blocking_name`/anything else indicating why -- the user had
to point out "you are now in a leader meeting screen" from the actual game window, since nothing in the
harness's own output showed it. Root-caused via `leaderheadroot.lua`: that popup only ever shows for three
states per its own `bMyMode` check -- a first-contact/general greeting, an echo of a war we just declared,
or an echo of peace we just made -- all purely informational, none needing a response (an actual
negotiation/demand goes through the separate `DiscussionDialog`/`DiscussLeader` states, untouched, already
surfaced via `turn_digest`'s `leader_message` events). Added `leader_greeting_pending()` (checks
`UI.GetLeaderHeadRootUp()`) / `dismiss_leader_greeting()` (same as the popup's own Back button: `DequeuePopup`
+ `UI.SetLeaderHeadRootUp(false)` + `UI.RequestLeaveLeader()`), wired into `wait_for_my_turn`'s poll loop.

**TechPopup ("you have discovered X! choose next research") had the same silent-hang shape**, and is
plausibly the real explanation for an earlier-session mystery (this file, above): `GetEndTurnBlockingType()`
reading `NO_ENDTURN_BLOCKING_TYPE` right after a tech completed even though `end_turn` still silently
refused to advance. `set_research()` sets the real research choice directly via `Network.SendResearch` and
never touches this popup (`techpopup.lua`) -- so the modal can be left visually open, independent of whether
the underlying choice already succeeded. The user was manually dismissing this one by hand every time
("I've been dismissing this for you") before flagging it. Added `tech_popup_pending()`
(`not ContextPtr:IsHidden()` in the `TechPopup` state) / `dismiss_tech_popup()` (same two calls
`techpopup.lua`'s own `ClosePopup()` makes: `ContextPtr:SetHide(true)` *and*
`Events.SerialEventGameMessagePopupProcessed(ButtonPopupTypes.BUTTONPOPUP_CHOOSETECH, 0)` -- `SetHide` alone
is not sufficient, confirmed by reading the source before ever calling it live). Wired into
`wait_for_my_turn`, but gated on `GetCurrentResearch() ~= -1` first: auto-dismissing an *unresolved* choice
would silently leave research unset with no reliable blocking signal to catch it (the exact failure mode
being fixed), trading one silent hang for a worse one.

**A second, unexplained crash**, ~10 minutes after the first one and the relaunch/fresh-game-start that
followed it. Turn 6, mid a completely ordinary sequence: `set_research` succeeded, `end_turn` succeeded
(`{ok:true}`), then a later plain `end_turn()` call (not touching any of the new popup-dismiss code above --
`tech_popup_pending()` had just read `false`, so `dismiss_tech_popup()` was never even called this time)
got `ConnectionError: tuner port 127.0.0.1:4318 not reachable: [Errno 111] Connection refused`, and
`Civ5XP` was gone from `ps` again. `Lua.log`'s last line before the gap is an ordinary `turn_state()` read
that returned fine -- the crash happened in the few-hundred-ms gap between that read and the next call, not
inside any identifiable Lua execution. No combat, no new/experimental code path involved this time (unlike
the first crash, which coincided with active combat) -- the only common thread between the two crashes so
far is "some point during ordinary hotseat turn-advancement under repeated tuner polling," which is thin
enough to not be a real lead yet. Two crashes in roughly 30-40 minutes of active polling is a real pattern,
not a one-off; if a third occurs, worth trying an isolation test (a stretch of `wait_for_my_turn`/`end_turn`
polling with NO other Lua calls in between, to rule polling frequency itself in or out) before spending more
effort on per-popup fixes.

**Save-game *load* is possible after all -- found `Events.PlayerChoseToLoadGame`.** The earlier assumption
in this file (and in `supervisor.py`'s docstring) that hotseat saves can't be reloaded programmatically was
about *auto-rejoining a live lobby*, which is genuinely impossible for hotseat -- but a plain save-file
*load* is a different, simpler thing that was just never implemented. Found via `loadmenu.lua` (the popup
`singleplayer.lua`'s Load Game button opens): `OnStartButton()` calls
`Events.PlayerChoseToLoadGame(fileName)` where `fileName` is `g_FileList[i]` -- a bare filename with no
path or `.Civ5Save` extension (e.g. `"QuickSave"` for `Saves/single/quick/QuickSave.Civ5Save`). Not yet
implemented/tested live this pass (found by reading source only, deliberately not tried mid-crash-recovery
given the two unexplained crashes above) -- worth adding as `load_save(filename)` and testing from a clean
`MainMenu` state next session, which would finally let `quick_save()` actually pay off instead of only
being insurance against a *different*, still-worse loss.

## Third crash root-caused (partially) via kernel segfault logs -- reproducible address, likely a Linux-port rendering bug, NOT harness-call-triggered (2026-09-16, same session)

While trying to test `load_save` from a relaunch, the relaunched instance unexpectedly auto-continued into
a completely unrelated, much older single-player game (turn 180, Korea/Sejong, Renaissance era, 3 cities --
not anything from this session; confirmed with the user before touching it further, since it looked like it
could have been a real save of theirs). The very next call after confirming it was fine to use --
a plain, read-only `turn_state()`, the single most-used call in the entire harness -- got
`ConnectionError: ... Connection refused`. Third crash of the session.

This time, `journalctl -k` (not checked after the first two crashes -- worth doing immediately every time
from now on) had real signal: **kernel segfault records for all three crashes**, and critically, **crashes
2 and 3 are the exact same deterministic segfault** -- identical instruction pointer (`0x885bd5f`), identical
binary offset, both inside `Civ5XP` itself (not `libCvGameCoreDLL_Expansion2.so`, where several *earlier*
sessions' unrelated crashes were). Not a heisenbug -- the same code path faults every time this trigger
condition is hit.

Symbolication (the binary reports `stripped` to `file`, but `nm -D` still lists ~28k *dynamic* text symbols
-- there is no local `.symtab`, so this is as precise as it gets): the crash address falls in a ~16KB gap
between `cvCityVisSystem::WonderRenderJob::Execute(unsigned int)` and `cvWonderLibrary::cvWonderLibrary()`
-- i.e. inside some unexported, static function in the city-visualization / wonder-rendering render-job
subsystem, not resolvable to an exact function name without a symbol table this binary doesn't have. This
region has no obvious connection to anything the harness's Lua calls touch directly (no wonder was being
built, examined, or rendered in either crashing game as far as any tool call shows) -- the working
hypothesis is an intermittent bug in an asynchronous render-job queue (scheduled independently of the main
game-logic thread the tuner talks to), which would explain why it doesn't correlate with *what* Lua command
was last issued -- the crash and the preceding tuner call are likely coincidental neighbors in time, not
cause and effect. Consistent with this: crash 1 (documented above, during active Barbarian combat) was a
*different* address (`Civ5XP` offset `c90534`, fault at address 0 vs `0x14` for crashes 2/3) -- three
crashes, two distinct fault sites, no shared harness action.

Circumstantial support for a graphics-stack angle rather than a harness-call angle: this instance runs at
`Width=320 Height=190` (config.ini) -- a deliberately tiny/headless-ish window -- on a modern
`AMD Radeon RX 7600` via Mesa RadeonSI (`OpenGL 4.6, Mesa 26.1.6`), an unusual pairing for a 2010, originally
DirectX9-targeting game's Linux port. Not confirmed, but worth trying if this recurs: check for a config.ini
flag to disable wonder-completion movies/animations specifically (none found under an obvious name this
pass), or try a larger/different window size, before assuming it's something fixable in `harness/`.

**Recurred a 4th time (2026-09-16, ninth session)**, exact same signature: `journalctl -k` showed
`Civ5XP[...]: segfault at 0 ip ... error 4 in Civ5XP[c90534,897d000+1972000]` -- identical offset (`c90534`)
and identical fault address (`0`) to "crash 1" above. This time there was no barbarian combat or anything
else notable in flight; the preceding harness activity was a burst of `plots_around`/raw `query()` calls
(including a deliberate 50000-byte stress payload) verifying the tuner-output-chunking fix just below, ending
about a minute before the crash. Given it's the identical fault site as a crash that happened under
completely different circumstances (active combat, no unusual query load), this is further evidence for the
existing hypothesis -- an intermittent async render-job bug that fires on its own schedule, not correlated
with whatever Lua/tuner call happens to be most recent. Recovered the same way as always: relaunch, `load_save`
the last quicksave, continue -- no data lost since a `quick_save()` immediately preceded the risky test burst.

**5th occurrence, ~22 minutes later (turn 248, right after adopting Merchant Confederacy)**: identical
signature again (`Civ5XP[c90534,897d000+1972000]`, fault address `0`). Five occurrences now, spanning
barbarian combat, a stress-test query burst, and routine policy adoption -- no correlation with any
particular harness call has held up across any of them. Treating this as ambient and moving on rather than
continuing to hunt it; `quick_save()` before anything non-trivial remains the actual mitigation.

## `dismiss_pending_popups()` was blind to GreatWorkPopup since it was added -- wrong visibility check, and its documented dismiss call doesn't work either (2026-09-16, ninth session continued)

User was watching the actual game window (something this harness otherwise has no visibility into) and
caught something no state query surfaced: "I saw you buying stuff while a leader trade screen was active,"
then, once that turned out not to be currently open, "there is also a modal over the main map ... because a
great work was completed." Checked immediately: `GreatWorkPopup` (Lua state 145) existed, and
`dismiss_pending_popups()`'s own check for it -- `not ContextPtr:IsHidden()`, the same line already in the
codebase from an earlier session -- read **false** (i.e. "not visible"), while the user could plainly see it
on screen. `ContextPtr:IsHidden()` reading wrong for a popup is the exact same failure mode already
documented for `PlayerChange` and `DiscussionDialog` (see their own docstrings) -- this makes GreatWorkPopup
a third confirmed instance, not a one-off. `UIManager:IsModal(ContextPtr)` also read `false`, equally wrong.
The one signal that read correctly: the popup's own content container,
`Controls.GreatWorkSplashContainer:IsHidden()`, read `false` (i.e. genuinely visible) at the same moment --
found by pulling the container name straight out of `greatworkpopup.xml` rather than guessing.

**Practical impact**: `dismiss_pending_popups()` had been evaluating this exact (wrong) condition since the
popup handling was added last session -- meaning it always silently found nothing here and moved on, for
every GreatWorkPopup that has ever appeared since. Any past "why is end_turn stuck" investigation that used
this function to rule GreatWorkPopup out was not actually checking it. Fixed the detection to read the
container instead of `ContextPtr`/`IsModal`.

**Second bug found while verifying the first fix**: with detection now correct, dismissal still didn't
work. The code's dismiss call was `UIManager:DequeuePopup(ContextPtr)` -- copied directly from
`greatworkpopup.lua`'s own `OnClose()` body, on the (reasonable, but wrong) assumption that calling the
exact function the real Close button calls would behave like clicking it. Confirmed live twice: the fixed
detection kept reporting the popup as still up after "successfully" dismissing it 5 times in a row (the
function's per-call retry cap), and calling `OnClose()` directly followed by a 1-second wait still showed
`GreatWorkSplashContainer:IsHidden() == false`. Whatever `DequeuePopup` does to the popup manager's queue,
it is not reflected in this container's hidden flag. Switched the dismiss call to
`Controls.GreatWorkSplashContainer:SetHide(true)` directly -- same "go straight to the control instead of
the documented close handler" pattern already used for `CityStateGreetingPopup` (whose `CloseButton` also
turned out not to be reachable the normal way) -- confirmed live: the container hides immediately and stays
hidden through a subsequent `dismiss_pending_popups()` call (returns `[]`, correctly finding nothing left to
do).

**Lesson**: this is now the third Civ5 popup where `ContextPtr:IsHidden()`/`IsModal()` lied and the fix was
to find the actual content container instead -- worth defaulting to that approach immediately for any
*next* newly-discovered popup rather than trying the generic checks first. Also a concrete case for reading
comments literally: the code's own docstring for this branch already said "untested whether SetHide alone
would also clear the blocking flag" and "no reason to guess" about `DequeuePopup` being correct -- it was
guessed correctly about which call the UI uses, but never actually verified to work, and it didn't.

**Correction, minutes later: this was misattributed -- the actual stuck popup was `WhosWinningPopup`, not
`GreatWorkPopup`.** The GreatWorkPopup fix above is still real (verified independently, its own detection
and dismiss were genuinely broken, and it's a real hard end-turn blocker) but was not what the user was
looking at. The user's first report ("a great work was completed") was a reasonable inference from a recent
notification, not a description of the screen itself; once asked to describe the actual content ("everyone's
military score", then explicitly "it's a 'whos winning' style screen ... one for each military, happiness,
science, etc") it was clearly `WhosWinningPopup` instead -- already in `_SWEEP_POPUP_STATES` on the
assumption that its generic `ContextPtr:IsHidden()`/`SetHide(true)` handling worked, untested until now.
Same failure shape as GreatWorkPopup, confirmed the same way: `ContextPtr:IsHidden()` read `true` and
`UIManager:IsModal(ContextPtr)` read `false` while genuinely visible; found the real content controls by
enumerating `pairs(Controls)` live (`ListNameLabel`, `PresentsLabel`, `PlayerListStack`, `CloseButton`,
`PlayerListScrollPanel`) rather than guessing from source (this one has no single obvious "container" name
the way GreatWorkPopup's XML did) -- all five read `IsHidden() == false` while stuck. The documented close
path (`OnClose()`, the real CloseButton's callback) does NOT hide them either, same as GreatWorkPopup's
`DequeuePopup`. Fixed by hiding all five children directly and pulling `WhosWinningPopup` out of
`_SWEEP_POPUP_STATES` into its own explicit case in `dismiss_pending_popups()` (`harness/game.py`) -- the
generic sweep can't be trusted for any state that turns out to share this failure mode, and now that two
different popups have both turned out to have it, the other five names still in `_SWEEP_POPUP_STATES`
(`GoldenAgePopup`, `NaturalWonderPopup`, `BarbarianCampPopup`, `GoodyHutPopup`, `WonderPopup`, `NewEraPopup`,
`TechAwardPopup`) are more suspect than "swept defensively, probably fine" implied -- none of them are
actually live-confirmed either. **User visually confirmed the fix**: watching the real game window
(something no state query can substitute for), the screen actually disappeared after the child-hide call.

**Possible connection to the recurring `Civ5XP[c90534]` crash (see above, five occurrences this session)**:
worth revising the earlier "ambient, unrelated to harness calls" conclusion in light of both fixes above.
`dismiss_pending_popups()` has silently failed to detect *or* clear GreatWorkPopup and WhosWinningPopup since
they were added -- meaning either could have sat genuinely stuck open indefinitely, across many turns of
continued harness activity (turn-advancing Lua calls, production/purchase/policy mutations) happening
underneath them the whole time. The standing crash hypothesis already names "an intermittent bug in an
asynchronous render-job queue" in the "city-visualization / wonder-rendering render-job subsystem" as the
likely fault site -- a stuck full-screen popup with continued rendering and engine mutation happening behind
it is a much closer match to that than pure coincidence. Not confirmed -- the crash has also happened with
neither popup anywhere nearby (the barbarian-combat instance) -- but with both bugs now fixed in the same
session, worth watching whether crash frequency actually drops from here, rather than continuing to treat
every future occurrence as automatically ambient.

## WonderPopup and TechPopup have the same broken-`IsHidden()` bug -- and a 6th crash, this time the OTHER known signature, right after fixing them live (2026-09-16, ninth session continued)

Same investigation, continued: Taj Mahal completed, then Scientific Theory completed, both while the user
was watching the live game window and reporting what was actually on screen. Checked both the same way as
GreatWorkPopup/WhosWinningPopup: `WonderPopup`'s `ContextPtr:IsHidden()` read `true` while all seven of its
real controls (`WonderIcon`, `Title`, `CloseButton`, `Quote`, `LowerTitle`, `WonderSplash`, `Stats`, found by
enumerating `pairs(Controls)` live) read `IsHidden() == false` -- genuinely visible. Hiding all seven
directly worked, user-confirmed visually. `TechPopup` -- which already had dedicated `tech_popup_pending()`/
`dismiss_tech_popup()` functions from an earlier session, not part of the generic sweep -- turned out to have
the exact same problem despite already looking handled: its `ContextPtr:IsHidden()` check is exactly as
unreliable as the others, and its documented dismiss call (`ContextPtr:SetHide(true)` +
`Events.SerialEventGameMessagePopupProcessed(...)`) does NOT hide its real controls (`OpenTTButton`,
`ScrollPanel`, `ButtonStack`, `ScrollPanelBlackFrame`, `ScrollPanelFrame`, `TechBackground`) either --
confirmed live, called it directly and the controls stayed `IsHidden() == false`. This is now a fourth
independently-confirmed instance of "the documented/obvious close call doesn't work, only directly hiding
the real controls does" (after CityStateGreetingPopup's CloseButton, GreatWorkPopup's DequeuePopup, and
WhosWinningPopup's OnClose) -- strong enough of a pattern now that it should be the *first* thing tried for
any newly-found stuck popup, not a fallback after the "proper" call fails.

**Not yet ported into `game.py`** -- found and confirmed via raw `c.exec()` calls against the live game, not
yet written into `dismiss_pending_popups()`/`dismiss_tech_popup()`, because of what happened next.

**A crash immediately followed, with the OTHER known signature.** After hiding WonderPopup's controls
directly (confirmed working, user saw it disappear) and then hiding TechPopup's controls + firing the popup-
processed event for a *second*, reused instance of the same TechPopup state (Scientific Theory reusing the
same Lua state TechAward/tech-discovery popups apparently share, same pattern as GreatWorkPopup being reused
across multiple works) -- the very next live query crashed: `journalctl -k` showed
`Civ5XP[...]: segfault at 0x14 ip 0x885bd5f ... in Civ5XP[813d5f,8048000+933000]`. This is NOT the
`c90534`/fault-`0` signature seen five times earlier this session -- it's the OTHER one, already documented
above as "crashes 2 and 3," itself already hypothesized to be in "the city-visualization / wonder-rendering
render-job subsystem" based on symbol-table proximity (`cvCityVisSystem::WonderRenderJob::Execute` /
`cvWonderLibrary::cvWonderLibrary()`). Directly manipulating a *wonder* popup's render controls
(`WonderIcon`, `WonderSplash`, etc.) via raw `SetHide()` calls, immediately followed by a crash whose
existing hypothesis names the wonder-rendering subsystem specifically, is a real correlation -- but it is
one data point, done as a rapid double operation (Wonder then Tech, back to back) rather than isolated, so
it's not possible to say from this alone whether WonderPopup's fix, TechPopup's fix, doing both in quick
succession, or something unrelated actually caused it. Recovered the normal way: relaunch (`sp14`),
`load_save("QuickSave")` (landed on turn 254, since the last quicksave predated this whole WonderPopup/
TechPopup investigation) -- turns 255-257's decisions need to be replayed.

**Practical takeaway for next time**: the WonderPopup/TechPopup fixes are real and verified (both
independently confirmed working via direct testing before the crash), but given this correlation, the next
session should port them into `game.py` and then test each one in isolation (quicksave first, one popup type
at a time, watching `journalctl -k` after each) before assuming they're crash-neutral like the
GreatWorkPopup/WhosWinningPopup fixes turned out to be (those were each tested individually with no crash
following). If a future WonderPopup or TechPopup dismiss reliably precedes a `0x885bd5f`/`0x14` crash, that
would upgrade this from correlation to a real causal lead -- and the fix would need to be something other
than direct `SetHide()` on render controls (perhaps deferring the hide until the render job in question is
confirmed idle, if there's any query for that).

**Correction on the WonderPopup fix itself, plus an independent finding (2026-09-16, same investigation,
after recovering from the crash above)**: replaying forward to the same Taj Mahal completion, the user
reported the popup background had turned solid red -- and initially attributed this to my earlier
child-hiding fix. Traced it via `wonderpopup.xml`
(`dlc/expansion2/ui/ingame/popups/wonderpopup.xml`): the 7 named controls found live via
`pairs(Controls)` (`WonderIcon`, `Title`, `CloseButton`, `Quote`, `LowerTitle`, `WonderSplash`, `Stats`) are
all nested *inside* several layout wrappers -- a top-level `<Box Style="BGBlock_ClearTopBar"/>`, a
`<ScrollPanel>`, a second `<Box Color="White.0">`, and a `<Grid>` -- none of which have an `ID` attribute, so
none of them are reachable through `Controls` at all. Hiding only the named leaves would strip the content
but leave any of those anonymous wrappers rendering underneath, which looked like a plausible explanation
for a stuck solid-color panel.

**Turned out not to be the actual explanation this time**: on the *next* fresh instance of this exact popup
(post-crash-recovery replay, before any dismiss code had touched it at all this time) the user confirmed the
popup looked entirely normal -- title, quote, icon, close button all fine -- except the `WonderSplash` hero
image specifically, which was solid red on its own, natively, with no harness interaction involved. This is
a genuine texture-load failure for that one asset (independent evidence for the graphics-stack hypothesis
already on file: unusual `320x190` window + modern AMD/Mesa driver for a 2010 DirectX9-era port), not
something the dismiss fix caused. The anonymous-wrapper concern above is still architecturally real for this
popup (worth keeping in mind for *other* Wonders' splash images, or if a similar "children hidden but
something remains" report ever recurs) but wasn't what was actually observed here.

Tried `ContextPtr:SetHide(true)` (the single call that should hide everything including anonymous
children, since they're all descendants of `ContextPtr`) at the user's request. The popup did disappear, but
the user flagged a real ambiguity immediately after: they may have hit Enter on the wrong window at the same
moment, which could have triggered the real CloseButton instead. **Not counted as a confirmed fix** for that
reason -- inconclusive, not verified, don't cite this as "WonderPopup dismiss works now."

**7th crash, turn 260, right after a plain `set_research("TECH_STEEL")` call** -- nearby but distinct offset
(`Civ5XP[c90232,...]`, fault address `0`, vs the `c90534` seen five times earlier) -- same general fault
class, mundane trigger action, further evidence for "ambient, on its own schedule" over any specific harness
call being the cause. Recovered the same way (relaunch, `load_save("QuickSave")` -> turn 257).

**Practical takeaway for future sessions**: three crashes in under an hour of active polling means sustained
multi-hour unattended-adjacent play sessions are NOT currently reliable in this environment, independent of
anything `harness/game.py` does right or wrong. `quick_save()` (added this session) plus a habit of calling
it after anything costly is the mitigation that actually matters here -- not chasing this further inside the
harness's own code, since the evidence so far points outside it. Check `journalctl -k -n 50 | grep -i civ5xp`
immediately on the next unexplained tuner disconnect, before assuming it's a harness/Lua bug -- that one
command is what finally turned "mystery" into "reproducible address, probably-rendering, probably not us."

## `load_save()` implemented and live-verified; `establish_trade_route`'s real bug found (wrong API, not a slot/timing issue); a FOURTH crash (same known segfault) (2026-09-16, seventh session)

Continuing manual play per the user's standing instruction (see memory: no automation scripts, play turn by
turn, fix bugs as hit). User asked to load one of their own pre-existing saves as a more complex test
candidate instead of another fresh game -- `Saves/single/Sejong_0180 AD-1200.Civ5Save` (turn 180, Korea/
Sejong, Renaissance, 3 cities), sitting alongside this session's own `QuickSave.Civ5Save` and several
`auto/AutoSave_*` files.

**`load_save(filename)` (flagged "not yet implemented/tested" at the end of the previous session) is now
implemented and live-verified**, `harness/game.py`. Two things the earlier from-reading-source-only note got
wrong:
1. **The event argument is NOT a bare filename.** `Events.PlayerChoseToLoadGame(fileName)` wants the *exact*
   string `UI.SaveFileList()` produces: a full OS path with `.Civ5Save`, backslash-separated (`\home\ty\...
   \Saves\single\Sejong_0180 AD-1200.Civ5Save` -- this is a Windows port, even on Linux). The bare display
   name (`Path.GetFileNameWithoutExtension`) is only for the list UI's button labels. Confirmed via `strings`
   on `Civ5XP`: the real listener is a native `InterfaceBuddy::OnPlayerChoseToLoadGame`, so it fires from any
   Lua state without the popup ever needing to be open -- this part of the original assumption held.
2. **`UI.SaveFileList(t, gameType, showAutoSaves, true)`'s `showAutoSaves` bool SWITCHES which folder gets
   listed, it doesn't add to it** -- confirmed live: `false` lists `Saves/single/` + `quick/` (manual +
   quick saves), `true` lists only `Saves/single/auto/` (+ a `prev/` backup). `load_save()` now tries both
   and matches by basename via `pathlib.PureWindowsPath(...).stem`.

**A load (or a fresh single-player game start) lands paused, and every action silently no-ops until this is
dismissed** -- `loadscreen.lua`'s `OnSequenceGameInitComplete` calls `Game.SetPausePlayer(activePlayer)`
after init and waits for the "Dawn of Man" screen's Continue button (`OnActivateButtonClicked`, which fires
`Events.LoadScreenClose()` + `Game.SetPausePlayer(-1)` for non-hotseat/non-MP games) -- a step nothing
tuner-driven ever clicks. Symptom if missed: `turn_state()` looks completely normal (`my_turn: true`,
`blocking_name: NO_ENDTURN_BLOCKING_TYPE`) except `paused: true`, and `end_turn()`/production/etc. all return
`{ok:true}` while nothing actually changes -- an easy trap since nothing errors. `load_save()` now dismisses
this itself right after `wait_ingame()` returns, same two calls the real button makes, from the `LoadScreen`
Lua state (best-effort: wrapped so a hotseat/MP load, which auto-dismisses on its own per that same source
file, isn't affected).

**`establish_trade_route`'s silent no-op was NOT the selection-timing bug it initially looked like** (the
`MISSION_BUILD`-style "same Lua call as the mission push" pattern that bit `unit_mission` before) -- fixing
that (moving `UI.SelectUnit` to its own round-trip via `select_unit()` + a settle delay, matching
`unit_mission`'s pattern) changed nothing. The real bug: **`H.available_trade_routes` was calling the wrong
API entirely.** `Players[pid]:GetTradeRoutesAvailable()` returns entries with an `eDomain` field (0 land / 2
sea) that looks superficially like the mission's `trade_type` argument but isn't it -- passing it into
`MISSION_ESTABLISH_TRADE_ROUTE`'s data2 slot silently no-ops exactly like a bad build-type id does (`{ok:
true}`, unit's `mission` stays -1, never leaves the city). Found the real source by grepping the actual game
UI (`chooseinternationaltraderoutepopup.lua`'s `RefreshData`): it builds its list from the *per-unit*
`Players[pid]:GetPotentialInternationalTradeRouteDestinations(unit)` instead, and the `TradeConnectionType`
field *that* call returns -- not `eDomain` -- is what gets passed back into the mission call
(`OnConfirmYes`). Rewrote `H.available_trade_routes` (now `available_trade_routes(unit_id, pid)`, signature
change threaded through the MCP tool and HTTP route too) to use the correct per-unit call; live-verified
establishing a real Seoul-to-Stockholm international route (1786 gold) with a cargo ship that had been
blocking `end_turn` on `ENDTURN_BLOCKING_UNITS`. Runtime bumped to v16. General lesson matching the
`MISSION_BUILD` case: when a `{ok:true}` PUSH_MISSION call visibly does nothing, suspect the argument value
came from the wrong native API before suspecting a slot or timing bug -- grep the actual UI Lua for the
exact call site rather than guessing from an adjacent-looking API.

**A fourth crash**, mid-session, while testing the newly-fixed `establish_trade_route` -- `journalctl -k`
confirmed the *exact same* segfault address (`0x885bd5f`, same offset in `Civ5XP`) as crashes 2 and 3 from
the previous session, reinforcing that this is a pre-existing graphics-stack issue independent of whatever
harness code happens to be running at the time (this crash hit right after a `load_lua`/`ensure_runtime`
call, not an action call at all). Recovered cleanly: relaunched, `load_save("QuickSave")` back to the
turn-181 checkpoint taken just before the crash, replayed the one lost decision (the trade route). No new
information on root cause; the standing mitigation (quicksave after anything costly, expect this environment
to crash roughly every 20-40 minutes of active polling) continues to be the practical answer, not further
harness debugging.

**A third silent-hang popup found the same way as the leader-greeting and tech-popup ones before it: the
user watching the actual screen live.** `wait_for_my_turn` spun for minutes with `my_turn` stuck false and
no other signal while the game sat on an AI leader's trade/negotiation screen (`DiscussionDialog` +
`DiploTrade`) -- Sweden had opened a trade discussion. Unlike the greeting popup, this is a REAL decision
(accept/reject a deal, respond to a demand), so it is deliberately NOT auto-dismissed the way the
informational one is -- added `discussion_pending()` (checks `Controls.LeaderPanel:IsHidden()` inside the
`DiscussionDialog` state; that state's own `ContextPtr:IsHidden()` stayed `true` the whole time it was
visibly up, live-confirmed unreliable) and `dismiss_discussion()` (same `OnBack(true)` the screen's own Back
button calls). `wait_for_my_turn` now returns early with `discussion_pending: true` merged into the normal
turn_state instead of continuing to poll to `timeout` -- exposed as an MCP tool + HTTP route since callers
(the LLM players) need a way to act on the new signal, unlike the two auto-resolved popups which stayed
internal-only. No accept/read-terms path exists yet (deliberately, given the known `propose_deal` crash) --
this is "leave" only, for when a proposal isn't worth building that out for yet.

**`Controls.LeaderPanel:IsHidden()` turned out to be just as unreliable as `DiscussionDialog`'s own, within
the same session** -- a SECOND real trade offer (Spain this time, right after the Sweden one above) had
`LeaderPanel` reporting hidden while visibly up, disproving the fix within minutes of writing it. `OnBack(true)`
still closed it regardless (confirmed: it's the umbrella "leave this whole leader interaction" call, not
scoped to whichever specific sub-panel happens to be showing), so `dismiss_discussion()` needed no change --
only `discussion_pending()`'s detection did. Switched to checking `DiploTrade`'s own `ContextPtr:IsHidden()`
instead, the one signal that actually tracked correctly across both live offers. Still only two data points,
both trade offers -- a pure demand/ultimatum with no trade terms to show might not un-hide DiploTrade at all,
so this may need another pass if that shape is observed hanging the same way.

## World Congress / League support added: `league_status`/`league_propose_enact`/`league_propose_repeal`/`league_cast_votes` (2026-09-16, eighth session)

Continuing manual play on the same sp6 Korea/Sejong game (still running, no crash across this whole session
-- context was `/clear`ed between sessions but the game process and tunerd were untouched, picked back up
mid-game at turn 213). Hit a genuinely new blocker: `ENDTURN_BLOCKING_LEAGUE_CALL_FOR_PROPOSALS`, the World
Congress "make a proposal" requirement (turn 213, "First Rio de Janeiro Conference"), which this harness had
never handled before -- no League/Congress code existed in `runtime.lua` at all.

**Confirmed live: this is a HARD block, unlike every other popup-shaped blocker in this file.** The trick
that clears TechPopup/discussion/greeting popups -- fire `Events.SerialEventGameMessagePopup{Type=...,
Data1=leagueId}` to open the `LeagueOverview` state properly (confirmed via
`Events.SerialEventGameMessagePopup.Add(OnPopup)` in `leagueoverview.lua`) and then call its own `OnClose()`
(`Events.SerialEventGameMessagePopupProcessed.CallImmediate(BUTTONPOPUP_LEAGUE_OVERVIEW, 0)`) -- was tried
first and does NOT clear this blocking type; `end_turn()` still came back with `blocking_before: 20` and
`turn_complete_sent: false` afterwards. Only an actual `Network.SendLeagueProposeEnact(leagueId,
resolutionType, playerId, choice)` call (found by reading `ProposalController:CommitProposals` in the real
`leagueoverview.lua`) clears it -- confirmed live by proposing `RESOLUTION_SCIENCES_FUNDING` (a no-downside
pick for a science-leaning civ, chosen since it takes `RESOLUTION_DECISION_NONE` -- no extra choice
argument needed) and watching `blocking_name` flip to `NO_ENDTURN_BLOCKING_TYPE` immediately. Turn advanced
213 -> 215 cleanly afterward (two more stacked AI discussion popups along the way, dismissed as usual --
see `discussion_pending`/`dismiss_discussion` above).

**Built out the full read/write League API in `runtime.lua` (bumped to v17)** rather than just enough to
unblock the one turn, since the same source dive (`leagueoverview.lua`) already surfaced the vote-session
call shapes too and re-deriving this later would cost the same research again:
- `H.league_status(pid)`: read-only. `has_league=false` before any Congress exists. Between sessions
  (`in_session=false`): `proposable_enact` (resolution types `CanProposeEnactAnyChoice` allows right now,
  each with a `choices` list when the resolution needs one -- confirmed `league:CanPropose(pid)` and
  `CanProposeEnactAnyChoice` already fold in the remaining-proposal-count check themselves, both flip to
  `false` once `GetRemainingProposalsForMember` hits 0, so no extra gating was needed) and
  `proposable_repeal` (active resolutions `CanProposeRepeal` allows). During a session (`in_session=true`):
  `votable`, this session's enact/repeal proposals with their voter choices, source of truth for
  `league_cast_votes`.
- `H.league_propose_enact(resolution_type, choice, pid)` / `H.league_propose_repeal(resolution_id, pid)`:
  the two calls above, each gated on the matching `CanPropose*` check first (same "validate before touching
  the engine" pattern as `propose_deal`'s `IsPossibleToTradeItem` gate) plus an explicit "this resolution
  needs a choice, you didn't give one" check before ever reaching `Network.Send*`.
- `H.league_cast_votes(votes, pid)`: takes a list of `{resolution_id, direction, choice, num_votes}`,
  wraps `Network.SendLeagueVoteEnact`/`SendLeagueVoteRepeal` per entry, then `Network.SendLeagueVoteAbstain`
  for whatever's left of `GetRemainingVotesForMember` -- matching `VoteController:CommitVotes`'s own
  always-abstain-the-remainder behaviour exactly.

**Found and fixed a real bug during pre-emptive testing, before this was ever needed live**: an early version
of `league_cast_votes` had no `league:IsInSession()` check. Calling it out-of-session with a fake
`resolution_id` came back `{ok:true, votes_cast:1}` -- `Network.SendLeagueVoteEnact` does NOT validate
server-side that a session is actually running, the same "accepted but silently does nothing real" shape
that bit `MISSION_BUILD` and the original `available_trade_routes` implementation. Added an explicit
`IsInSession()` gate before touching the network call at all; re-verified the same call now returns a clean
`{ok:false, err:"no World Congress session is in progress right now"}`.

**Caveat: the `in_session`/`votable` read branch and the whole `league_cast_votes` write path are reasoned
from `leagueoverview.lua`'s source (`VoteController`), not independently live-verified** -- this playthrough's
Congress was between sessions (28 turns out) for the entire testing window, so no real vote session was
available to exercise. Re-check this the next time `ENDTURN_BLOCKING_LEAGUE_CALL_FOR_VOTES` actually comes
up before trusting it blindly, the same way `ENDTURN_BLOCKING_LEAGUE_CALL_FOR_PROPOSALS` turned out to need
more than the popup-open/close trick despite looking similar on paper.

Threaded through `harness/game.py` (`league_status`/`league_propose_enact`/`league_propose_repeal`/
`league_cast_votes`), `harness/mcp_server.py` (four new `@mcp.tool()`s), and `harness/http_server.py` (one
new GET route + three new POST routes + matching Pydantic bodies), following the exact same shape as the
trade-route additions earlier this session.

## A fifth crash while deliberately re-testing `propose_deal`; found and fixed a real `load_save("QuickSave")` bug during recovery (2026-09-16, eighth session continued)

User explicitly asked to start exercising paths not yet tried this session -- "make a new trade, propose or
alter a trade" -- specifically to probe `propose_deal` for corner cases, despite (because of) its known crash
history (see "Phase 3a" and the `H.propose_deal` docstring in `runtime.lua`/`game.py`: three crashes in one
prior day, never re-exposed as an MCP tool/HTTP route, called directly here for controlled testing only).

**`quick_save()` first (turn 219, established habit), then two tests**:
1. A one-sided `GOLD` gift to Assyria (`{"type":"GOLD","from_us":true,"amount":50}`, no reciprocal item) --
   came back a clean `{ok:false, err:"item not tradeable: GOLD from 0 to 1"}`. No crash. New data point:
   `deal:IsPossibleToTradeItem` rejects a pure one-sided gold gift with nothing coming back -- worth
   remembering if a future "give the AI gold to sweeten a deal" flow needs a reciprocal item to pass this
   gate, not just a willing recipient.
2. A mutual `OPEN_BORDERS` proposal (both sides) to Assyria -- **the game process died outright**, tunerd's
   next call came back `ConnectionError: tuner port 127.0.0.1:4318 not reachable`.

**The crash signature is the SAME address (`0x885bd5f` in `Civ5XP`) as every other unexplained crash
documented in this file across multiple sessions** (`journalctl -k`), and it landed ~72 minutes into this
session's uptime -- squarely inside the previously-documented "roughly every 20-40 minutes of active
polling" ambient pattern, not a fresh address. Best read: this is very likely the same pre-existing
graphics-stack issue coincidentally firing during the OPEN_BORDERS call, not proof that `OPEN_BORDERS`
itself is unsafe the way `PEACE_TREATY` was proven to be -- but it is NOT proof of safety either, since it
did happen immediately after that specific call and OPEN_BORDERS was never individually live-tested before
this. Treat `propose_deal` as still fundamentally unproven for re-exposure; this session neither clears nor
newly convicts OPEN_BORDERS specifically.

**Recovery from this crash surfaced a real, independent bug that matters far more than the crash itself: a
same-basename ambiguity in `load_save()` silently loaded the WRONG save.** Relaunched (`launch_civ5.sh sp7`),
then `load_save("QuickSave")` came back `{ok:true, turn:215}` -- four turns behind the `quick_save()` taken
*right before* the propose_deal tests at turn 219. Root cause, confirmed by listing `UI.SaveFileList`'s raw
output: **two genuinely different files both display as bare name "QuickSave"** -- the native F5 hotkey
quicksave writes `Saves/single/QuickSave.Civ5Save` (stale, turn 215, from earlier in this session), while
this harness's own `quick_save()` (`UI.QuickSave()`) writes a *separate* file, `Saves/single/quick/
QuickSave.Civ5Save` (fresh, turn 219). Both appear in the same `showAutoSaves=false` listing under the same
basename, and the old `load_save()` code just took `next()` -- the first list match -- which happened to be
the stale top-level one. Exactly the "accepted but silently wrong" failure shape this harness keeps hitting
in other areas (`MISSION_BUILD`, the original `available_trade_routes`, the out-of-session `league_cast_votes`
bug found earlier this session) -- except this one is in the crash-recovery path itself, the one piece of
this harness every other mitigation in this file depends on.

**Fixed in `harness/game.py`**: `load_save` now collects every candidate matching the requested basename (not
just the first) and disambiguates by real filesystem mtime (`_newest_save`, new module-level helper) rather
than trusting `UI.SaveFileList`'s return order. The raw path is a genuine Linux path with backslash
separators (a Windows-port quirk, not an actual Windows path), so this stats it directly --
`pathlib.Path(p.replace("\\", "/")).stat().st_mtime`. Falls back to the first candidate if none can be
stat'd, matching the old behavior only in that degenerate case. **Live-verified the fix immediately**:
re-ran `load_save("QuickSave")` right after applying it and got `{ok:true, turn:219}` -- the correct, fresh
save -- with the game otherwise fully healthy (gold, turn state all matching pre-crash values).

**Takeaway for future sessions**: don't assume "QuickSave" (or any bare save name) is unambiguous just
because it displays as one name in the list UI -- two different save *mechanisms* (native hotkey vs.
`UI.QuickSave()`) can and do collide on the same display name while writing to different files. If a
`load_save()` call ever comes back with a turn number lower than expected again, suspect this same class of
ambiguity before suspecting the save itself is corrupt or the quicksave silently failed.

## `propose_deal` conclusively broken for ANY deal contents, not just PEACE_TREATY -- three more crashes, converging evidence (2026-09-16, eighth session continued)

Continued deliberately probing `propose_deal` at the user's explicit request ("keep poking"), now with a
proper recovery loop (relaunch as a fresh instance name each time -- sp7, sp8, sp9 -- then `load_save
("QuickSave")`, now fixed above). Before each risky call: checked the actual precondition state directly
rather than guessing.

**Ruled out a rules/precondition explanation first** (the user's good instinct, worth checking before
blaming the engine): web search claimed Open Borders needs `TECH_CIVIL_SERVICE` and an established embassy.
Checked live -- `Teams[myTeam]:HasEmbassyAtTeam(otherTeam)` true both directions, not at war,
`Teams[team]:GetTeamTechs():HasTech(GameInfoTypes.TECH_CIVIL_SERVICE)` true, and critically
`deal:IsPossibleToTradeItem(me, other, TradeableItems.TRADE_ITEM_OPEN_BORDERS, duration)` -- the exact same
call the real UI uses to grey out an option -- returned `true` both directions. A human player would see
this as a fully legal, clickable trade right now. The crash is NOT a missing-precondition case.

**Three more live crashes, one per item type, each immediately after the call, each recovered cleanly**:
1. Mutual `OPEN_BORDERS` retried immediately after the first crash (see previous entry) -- crashed again,
   this time inside `libCvGameCoreDLL_Expansion2.so` itself (offset `184d73`), a DIFFERENT signature from the
   recurring ambient `Civ5XP[813d5f]` rendering-stack crash documented elsewhere in this file. Two crashes,
   two different addresses, both immediately following the identical call, only ~5 minutes apart (nowhere
   near the ambient bug's 20-40 minute cadence) -- this alone was already strong evidence of causation, not
   coincidence.
2. A read-only sweep (zero mutation calls, just `deal:IsPossibleToTradeItem` in isolation) mapped what's
   currently tradeable with Assyria: `GOLD_PER_TURN` and `DEFENSIVE_PACT` both `true`/`true`;
   `RESEARCH_AGREEMENT`, `TRADE_AGREEMENT`, `ALLOW_EMBASSY` (already have one) all `false`/`false`;
   `RESOURCES` (sheep) `false` (no real surplus, 1 owned is fully worked). `DECLARATION_OF_FRIENDSHIP` reads
   `true` but stays blocked by this harness's own PvP-only precondition (see `H.propose_deal`) regardless.
3. A one-sided `GOLD` gift (no reciprocal item) came back a clean `{ok:false, err:"item not tradeable"}` --
   no crash. **A one-sided gift is genuinely rejected by `IsPossibleToTradeItem` itself**; useful to know for
   any future "give the AI something to sweeten a deal" flow -- it needs a reciprocal item, not just a
   willing recipient.
4. `GOLD_PER_TURN` (also one-sided, `IsPossibleToTradeItem` had confirmed `true` for this one) -- crashed a
   third time. `journalctl -k` showed the exact SAME offset in `libCvGameCoreDLL_Expansion2.so` as the
   OPEN_BORDERS crash (`184d73`, only the `.so`'s ASLR base address differed) for a COMPLETELY different item
   type and a COMPLETELY different validation outcome (this one *was* one-sided and *did* pass
   `IsPossibleToTradeItem`).

**Conclusion: this is not an item-specific or a validation-specific bug.** Three crashes across two
different item types (one mutual, one one-sided; one passing every precondition check available, one
already known-bad) converging on the identical DLL offset points at something common to the whole
`deal:SetFromPlayer`/`SetToPlayer`/`UI.DoProposeDeal()` sequence itself -- not any particular `Add*Trade`
call. This matches and substantially strengthens the theory already on record for `PEACE_TREATY`
specifically ("the native deal-mutation methods need real trade-screen UI state that a bare tuner exec
doesn't have") -- promote that from a `PEACE_TREATY`-specific theory to a whole-function one. **Do not
re-attempt `propose_deal` for ANY item combination from this harness without first finding a genuinely
different underlying API** (a lower-level `Network.Send*` per item type, if one exists, the same pattern
that worked for `SendFoundPantheon`/`SendFoundReligion`/`SendUpdatePolicies`/the new League `Network.Send*`
calls this session) -- testing more item types one at a time will very likely just keep reproducing the same
crash for no new information.

**Checked for precedent in other Civ5 LLM-agent projects before continuing** (web search): no direct hit.
`corytodd/civ5-mcp` is read-only (game state -> SQLite for LLM advice, never issues write actions at all).
`alonekite/civ5-agent-macos` is deliberately narrow and rigorous -- its only live-verified write command is
`skip_unit`, with a full re-select + predicate + post-state-verify protocol; it has not attempted trade
deals, positive or negative. Neither confirms nor refutes this bug -- nobody else has gotten this far. One
circumstantial, unconfirmed lead: a CivFanatics thread titled "Diplomacy Crash - Only One Civ, Crash when
Clicking 'Offer a Deal...'" describes a crash from the REAL in-game UI (not any tuner/mod tooling), which
would suggest this might not even be a bare-tuner-context problem specifically but a genuine, rarer-to-hit
vanilla BNW engine bug in the trade-deal path itself -- couldn't read the thread (bot-walled), so this is a
lead for a future session to follow up on, not a confirmed explanation.

## Espionage support added: `spies`/`available_spy_cities`/`move_spy`/`stage_coup` (2026-09-16, eighth session continued)

Picked up the other long-standing flagged gap in this harness: `H.spies` had been read-only (a bare unit
count) since Phase 1, explicitly noted as needing "its own research pass" since no `MissionTypes.MISSION_*
SPY*` constant exists in this build's Lua. Same research method as the League work earlier this session --
read the real game's `ui/ingame/popups/espionageoverview.lua` for the actual call sites, then verify every
field shape live against the running game before writing any Lua of our own (all three of `GetEspionageSpies()`
's fields, `GetAvailableSpyRelocationCities(agentID)`'s fields, and the final `move_spy` call were confirmed
against turn 219's real state before being trusted).

**Spies are not part of the unit-mission system at all** -- they're a wholly separate mechanism:
`Player:GetEspionageSpies()`/`GetAvailableSpyRelocationCities(agentID)` to read, and exactly two
`Network.Send*` calls to act: `Network.SendMoveSpy(playerID, agentID, targetPlayerID, targetCityID,
bAsDiplomat)` (recall home: `targetPlayerID=-1, targetCityID=-1`; `bAsDiplomat` only matters when the target
is another major civ's capital while at peace -- the real UI offers a spy-vs-diplomat choice there,
everywhere else just passes `false`) and `Network.SendStageCoup(playerID, agentID)` (gated by
`Player:CanSpyStageCoup(agentID)`, mirrored as a precondition check before ever calling it).

Bumped runtime to v18. `H.spies` upgraded from `{count=N}` to a real per-agent list (agent_id, name, rank,
state, where stationed, turns_left/percent_complete, is_diplomat, established_surveillance,
can_stage_coup); new `H.available_spy_cities(agent_id, pid)` (targets with the real UI's displayed success
`potential`); new `H.move_spy`/`H.stage_coup`. Threaded through `game.py`, four new `mcp_server.py` tools,
and matching `http_server.py` routes (2 GET, 2 POST + Pydantic bodies), same shape as every other addition
this session.

**Live-verified the full round trip, not just the call succeeding**: our one spy (agent 0) was sitting on
counter-intel duty in Seoul. `available_spy_cities(0)` listed 15 valid targets (my own 2 cities plus every
met civ's capital and every known city-state, all currently `potential: 99`). Sent it to Antwerp (a
city-state, player 26) with `move_spy(0, 26, 8192, false)` -- came back `{ok:true}`, and a follow-up
`spies()` call confirmed the state genuinely changed (`city_name: "Antwerp"`, `city_owner: 26`, `state:
TXT_KEY_SPY_STATE_TRAVELLING`, `turns_left: 1`), not another silent no-op like the original
`available_trade_routes` bug earlier this project. Quicksaved afterward -- this was a real move in the
ongoing game, not a throwaway test.

## `GreatWorkPopup` found to be a hard end-turn block, missing from `dismiss_pending_popups`'s sweep (2026-09-16, eighth session continued)

Turn 221, playing manually: Seoul finished the Globe Theatre (set new production: Leaning Tower of Pisa), and
a Great Writer (F. Scott Fitzgerald) had spawned and was ready for orders. `unit_mission(id,
"MISSION_CREATE_GREAT_WORK")` was available and came back `{ok:true}`; the unit was confirmed genuinely
consumed afterward (gone from `units()`, not another blind `{ok:true}`). But `end_turn()` then stayed stuck
on `ENDTURN_BLOCKING_UNITS` across 15+ polls over ~22 seconds and several repeated `end_turn()` calls -- the
turn number never advanced.

**Misleading trail, worth remembering**: `blocking_name` said "units," but `Players[pid]:GetFirstReadyUnit()`
-- the actual engine call `actioninfopanel.lua` itself uses to find and highlight the supposedly-blocking
unit for `ENDTURN_BLOCKING_UNITS`/`_UNIT_NEEDS_ORDERS`/`_STACKED_UNITS` -- returned `nil` the whole time, and
manually inspecting every unit (`IsAutomated`/`IsReadyToMove`/`MovesLeft`/activity) found nothing obviously
stuck either. The real cause was found by scanning every currently-loaded Lua state for one that was
actually visible (`not ContextPtr:IsHidden()`) rather than trusting the blocking-type name at face value:
**`GreatWorkPopup` was up**, undismissed, from creating the Great Work -- not in `_SWEEP_POPUP_STATES` (the
existing generic-popup dismiss list), so `dismiss_pending_popups()` never touched it. Closing it
(`UIManager:DequeuePopup(ContextPtr)`, the exact call `greatworkpopup.lua`'s own `OnClose()` makes) cleared
`blocking_name` to `NO_ENDTURN_BLOCKING_TYPE` immediately.

**`GreatWorkPopup` closes differently from the rest of the sweep list** -- its `OnClose()` calls
`UIManager:DequeuePopup(ContextPtr)`, not `ContextPtr:SetHide(true)` like every entry in
`_SWEEP_POPUP_STATES`. Added it to `dismiss_pending_popups()` as its own explicit case (not folded into the
generic `SetHide`-based sweep, since whether plain `SetHide` alone would also have cleared the blocking flag
was never tested -- `DequeuePopup` is the real button's own call, so there was no reason to guess when the
correct call was already known). **Live-verified the underlying mechanism** (the manual `DequeuePopup` call
above, moments before the code change, cleared the exact stuck state) but **not independently re-verified
through the new `dismiss_pending_popups()` code path itself** -- no second Great Person was available this
session to retrigger the popup. Re-check this the next time a Great Writer/Artist/Musician creates a work,
the same discipline `league_cast_votes`' in-session branch is still waiting on.

**General lesson reinforced**: when `blocking_name` points at one category (here, "units") but the category's
own dedicated diagnostic (`GetFirstReadyUnit`, or the per-unit fields) comes up empty, don't keep
re-checking that category harder -- scan every loaded Lua state for one that's actually visible instead.
That's what actually found this, in under a minute, versus a much longer dead end re-inspecting units that
were never the real cause.

## Gold/faith rush-buying added (`purchase_cost`/`purchase_production`); a SIXTH crash, found and fixed the same session (2026-09-16, eighth session continued)

User: "play it however you want until you find a bug and then fix the bug. the savegame is yours" -- explicit
license to play autonomously and treat bugs as the thing to look for, not just work around. Gold had been
piling up with nothing to spend it on (~4000 and climbing at turn 225) -- genuinely never-implemented in this
harness (`grep`-confirmed: no purchase/rush/buy call anywhere in `game.py`/`runtime.lua` before this pass).
Found the real API in `ui/ingame/popups/productionpopup.lua`'s `OnProductionButtonClick`:
`Game.CityPurchaseUnit/CityPurchaseBuilding/CityPurchaseProject(city, id, eYield)`, gated by
`city:IsCanPurchase(true, true, unitID, buildingID, projectID, eYield)` (the real "can actually complete
this" check, not just "would show in the list"), with per-category cost getters
(`GetUnitPurchaseCost`/`GetUnitFaithPurchaseCost`/`GetBuildingPurchaseCost`/`GetBuildingFaithPurchaseCost`/
`GetProjectPurchaseCost`). Confirmed live: wonders (`ORDER_CREATE`... **see correction below, wonders are
actually `ORDER_CONSTRUCT`**) are never purchasable in vanilla BNW -- the real UI hardcodes
`isDisabled = true` unconditionally right after the wonder-list `IsCanPurchase` check, so `can_purchase`
correctly reads false for them without needing a special case.

**The crash, and the real lesson**: testing the new `purchase_cost`, called it as
`purchase_cost(8192, "ORDER_CREATE", "BUILDING_SISTINE_CHAPEL")` -- a genuine mistake (wonders are
`BUILDING_*` items built via `ORDER_CONSTRUCT`, exactly like any other building; `ORDER_CREATE` is for the
separate `PROJECT_*` category, e.g. Manhattan Project/Apollo Program). This crashed the game outright (new
signature: `libCvGameCoreDLL_Expansion2.so` offset `306a50`, distinct from every other crash address in this
file). **Root cause: `GameInfoTypes` is a single flat id-space shared across EVERY GameInfo table in the
game.** `GameInfoTypes["BUILDING_SISTINE_CHAPEL"]` resolves to a real, valid-looking id -- just one that
indexes the *Buildings* table, not *Projects*. Passing it into `city:GetProjectPurchaseCost(id)` (a
Projects-table call) indexed out of bounds natively. This is a systemic risk, not unique to purchasing:
**`set_production` had the exact same latent exposure** (`city:CanTrain(id, 0)` called with a building's id
if `order`/`item` were ever mismatched) -- it happened to never be hit because every caller so far passed a
consistent pair, not because anything actually prevented it.

**Fixed generally, not just patched for this one case**: added `_check_order_item(order, item)`
(`harness/game.py`), a zero-cost plain-string-prefix check (`UNIT_`/`BUILDING_`/`PROJECT_`/`PROCESS_` --
this game's own naming convention, the same one `mcp_server.py`'s `set_production` wrapper already uses to
*derive* `order` from `item`) run before any of `set_production`/`purchase_cost`/`purchase_production` ever
touch the engine. Re-ran the exact crashing call afterward: clean `{ok:false, err:"item
'BUILDING_SISTINE_CHAPEL' does not match order 'ORDER_CREATE' (expected a PROJECT_* item)"}`, game
untouched. At the `mcp_server.py`/`http_server.py` layer, `order` is always derived from `item`'s own prefix
(same pattern as `set_production`), so a caller through those surfaces can't even construct a mismatched
pair to begin with -- the `game.py`-level check is the real backstop for direct callers (like this session's
own testing).

**Live-verified the actual success path, not just the error path**: recovered (relaunch as `sp10`,
`load_save("QuickSave")` correctly landed on the turn-225 save -- the disambiguation-by-mtime fix from
earlier this session holding up under a second real crash), then for real: `purchase_cost(16385,
"ORDER_CONSTRUCT", "BUILDING_MARKET")` read `{cost:500, can_purchase:true, balance:3809}`;
`purchase_production(...)` came back `{ok:true, balance:3309}` (exactly 500 gold deducted); a follow-up raw
check confirmed `city:IsHasBuilding(BUILDING_MARKET) == true` -- genuinely built, not another silent no-op.
Queued Bank next in the same city. Six crashes total this session (three `propose_deal`, one `GreatWorkPopup`-
adjacent stall which wasn't itself a crash, this one, plus the earlier ambient one at session start) --
five of six were root-caused and fixed or conclusively characterized; only `propose_deal` remains
unresolved by design (needs a different underlying API entirely, see its own entry above).

## `cli.py status` reported a hidden leftover screen instead of the real one (2026-09-16, ninth session)

Relaunched as `sp11` after `sp10` was found dead (no reaper process; the instance had silently exited
sometime after the last session's crash-recovery testing). `cli.py status` came back `"JoiningRoom"`
repeatedly for over a minute after launch and stayed there through several manual "leave the room" attempts
(`Matchmaking.LeaveMultiplayerGame()`, `UIManager:DequeuePopup(ContextPtr)` on that state) that had no
effect. **Root cause: `cmd_status` picked the first name match in a fixed priority list out of
`set(g.states().values())`, with no visibility check** -- Civ5 keeps several frontend screens' Lua states
loaded-but-hidden simultaneously (confirmed live: `states()` had both `JoiningRoom` (id 41) and `MainMenu`
(id 44) registered at once), and a stale `JoiningRoom` from an old abandoned LAN-rejoin attempt outranked
`MainMenu` in the priority list regardless of which one was actually on screen. Checking
`ContextPtr:IsHidden()` per id (`JoiningRoom` -> `true`, `MainMenu` -> `false`) showed the game had been
sitting at the main menu the whole time -- every "leave the room" call had been a no-op against a screen
that was never actually blocking anything. Fixed generally in `cli.py`'s `cmd_status`: instead of trusting
bare name presence, it now groups state ids by name and, in the same priority order as before, picks the
first one whose own `ContextPtr:IsHidden()` reads false -- the same idiom already used throughout
`game.py`'s popup checks (`player_change_pending`, `city_state_greeting_pending`, etc.), just applied here
too. Live-verified: `load_save("QuickSave")` then worked immediately once `status` correctly reported
`MainMenu`.

## Tuner output truncates silently past ~4085 bytes -- systemic fix in `TunerClient.query()` (2026-09-16, ninth session continued)

User: "play like you mean it, make decisions, pressure test what we have so far" -- pushed past the routine
turn loop into less-exercised API surface. `plots_around(x, y, r)` at `r=4` (61 plots) came back
`TunerError: no JSON sentinel in output: ['O']`; `r=3` (37 plots, 3.1KB of JSON) worked fine. Binary-searched
the actual limit directly (`q("return string.rep('a', N))")` for varying `N`): **4071 bytes round-trips
intact, 4072 comes back as a single mangled `'O'` output line with the closing sentinel gone.** This isn't
our socket framing (that's a plain length-prefixed protocol, no size cap) -- it's Civ5's own native
print()-to-Tuner-OUTPUT relay silently truncating at what's almost certainly a fixed ~4096-byte buffer,
independent of and invisible to anything in this harness. Every `query()`-based call was exposed to this
whenever its JSON result crossed that size (not just `plots_around` -- `cities()`/`units()`/`notifications()`
etc. would hit the same wall given enough entries), silently returning corrupted/absent data instead of an
obvious error the few times it *did* raise.

**Fixed generally in `TunerClient.query()` (`harness/tuner.py`)**, not just for `plots_around`: the injected
Lua now slices `__hjson(result)` into <=3500-byte pieces (comfortably under the 4085-ish observed ceiling)
and `print()`s each with the `@@HJ@@` sentinel prefix instead of one `print()` wrapping the whole payload
between two sentinels; Python-side reassembly changed from a single `find`/`rfind` pair to collecting every
output line that starts with the sentinel and concatenating them in order (still silently discards
unrelated game print() chatter that doesn't carry the tag, same as before). **Restarting `tunerd` to pick up
the fix required care**: it's a long-running process holding the one live socket to the game, and the game
only re-arms its tuner listener on `ExitToMainMenu`/leaving the MP staging room -- restarting it while still
in-game would have stranded the connection. Sequenced as: `quick_save()` -> `leave_to_main_menu()` on the
*old* tunerd (plain `exec`, unaffected by this bug) -> confirmed `MainMenu` via the now-fixed `cli.py status`
-> killed old tunerd, launched a fresh one -> it reconnected cleanly since the game was already back at the
main menu -> `load_save("QuickSave")` restored turn 237 exactly where it left off. Live-verified the fix
afterward: `plots_around` at r=4/5/7/10 (up to 227 plots) all round-tripped correctly, and a direct 50000-byte
`string.rep` stress test came back byte-for-byte intact.

## Manual play session (2026-09-16, turn 258+): DiscussionDialog only ever declines; found the real accept
## path for `DISCUSS_WORK_WITH_US` via `diplo_event`, live-verified after the fact

Resumed via `load_save("QuickSave")` after the game had crashed back to `MainMenu` on its own between sessions
(journalctl showed a fresh segfault, `Civ5XP[c90232]`, at 19:31:41 -- SAME offset already root-caused this
session as the TechPopup-not-in-`dismiss_pending_popups()` gap, now patched in the working tree; this crash
predates that patch reaching a running instance, not a new bug). Newest save picked correctly by the
mtime-disambiguation fix (`Saves/single/quick/QuickSave.Civ5Save`, turn 257) -- confirmed working as designed.

**Immediately hit `dismiss_pending_popups()` finding `TechPopup`/`GreatWorkPopup`/`WhosWinningPopup` all
genuinely stuck open from the crash recovery** -- the already-documented fixes for all three worked
correctly first try.

**New gap found: `discussion_pending()`/`dismiss_discussion()` are correct but `dismiss_discussion()` can
ONLY decline.** After `end_turn()`, polled `turn_state()` directly (not `wait_for_my_turn()`) for ~15s seeing
`my_turn=false`, `blocking_name=NO_ENDTURN_BLOCKING_TYPE`, `processing=false`, and `dismiss_pending_popups()`
returning empty every time -- looked exactly like the "silent hang" failure shape catalogued elsewhere in
this file. Root cause was NOT a hang: a `DiscussionDialog` was up (Assyria/player 1 proposing a Declaration
of Friendship, per `events_peek()`'s `leader_message`), which `discussion_pending()` correctly detects but
which nothing in a plain `turn_state()`/`dismiss_pending_popups()` poll loop surfaces -- exactly what
`wait_for_my_turn()` exists to catch (its docstring already warns against blind auto-decline). Lesson for any
manual-play driver: **use `wait_for_my_turn()` after `end_turn()`, not a raw `turn_state()` poll loop** -- it
surfaces `discussion_pending` in its return dict instead of looking like a hang.

Called `dismiss_discussion()` on this Assyria offer before realizing what it was (declines via
`OnBack(true)`, the only path that function has). A second discussion then appeared (Brazil/player 7,
`DIPLO_UI_STATE_TRADE_AI_MAKES_OFFER`, a luxury-resource trade) -- also declined, since `TRADE_AI_MAKES_OFFER`
genuinely has no branch in `discussiondialog.lua` (grep-confirmed across the live `expansion2` UI file: zero
occurrences) and no accept path is known for it.

**But `DISCUSS_WORK_WITH_US` (the DoF proposal) *does* have a real accept path, found by reading
`discussiondialog.lua`'s own `OnButton1`**: `Game.DoFromUIDiploEvent(FromUIDiploEventTypes.FROM_UI_DIPLO_EVENT_WORK_WITH_US_RESPONSE,
iAIPlayer, iButtonID, 0)` with `iButtonID=1` for "yes, work together" (`iButtonID=2` is decline, same event).
This is exactly what `H.diplo_event`/`Game.diplo_event()` already fires generically -- no code change needed,
just the right event name. **Live-verified it still works retroactively, after the dialog had already been
declined and closed**: `g.diplo_event("WORK_WITH_US_RESPONSE", 1, 1, 0)` came back `{ok:true}`, and unlike the
usual "ok:true proves nothing" risk with unguarded events (see this function's own docstring), this one was
independently confirmed genuinely real by reading engine state directly afterward: `Players[me]:IsDoF(1)` ->
`true` (found via `grep IsDoF` on `diploglobalrelationships.lua`'s own live UI check, `pOtherPlayer:IsDoF(iThirdPlayer)`
-- confirmed on the correct object, `Player`, not `Team`, since an initial guess at `Teams[t]:IsDoF()` errored
with `attempt to call method 'IsDoF' (a nil value)`). So a `DISCUSS_WORK_WITH_US` offer can be safely declined
first and accepted later with no time pressure, at least in this one live case -- worth trusting more only
after a second confirmation on a fresh (not previously-declined) offer.

**Second confirmation, turn 263, fresh (not previously-declined) offer this time**: Sweden (player 2)
proposed `DISCUSS_WORK_WITH_US`; dismissed the dialog normally, then immediately called
`diplo_event('WORK_WITH_US_RESPONSE', 2, 1, 0)` -> `{ok:true}`, and `Players[me]:IsDoF(2)` read `true`
right after. Two-for-two now (one retroactive after decline, one immediate after decline) -- this accept
path can be trusted as a general pattern for `DISCUSS_WORK_WITH_US` specifically, not just a one-off.
Worth promoting to a real `accept_friendship(player_id)` wrapper in `game.py` if this keeps coming up
(every AI DoF offer so far has used this exact state).

**Not pursued further this session**: a generic `accept_discussion()`/`respond_discussion(button)` wrapper
would need per-`DiploUIState` button-to-event mapping (`discussiondialog.lua`'s `OnButton1..8` bodies are one
big per-state dispatch, not a uniform "button 1 = yes" convention throughout -- e.g. `DISCUSS_WORK_AGAINST_SOMEONE`
puts the polite decline on Button1 and the offended response on Button3), and `TRADE_AI_MAKES_OFFER` acceptance
would need the same `Game.propose_deal`-adjacent trade-construction path already flagged as crash-prone and
unresolved by design elsewhere in this file -- not worth the crash risk for a single luxury-resource trade.
Filed as a known gap, not fixed: for now, `diplo_event` is the only accept path, one hand-verified event
(`WORK_WITH_US_RESPONSE`) at a time, looked up from the real game Lua before firing.

Added a real `accept_friendship(player_id)` wrapper (`game.py`/`mcp_server.py`/`http_server.py`) around the
now-twice-confirmed `diplo_event('WORK_WITH_US_RESPONSE', pid, 1, 0)` pattern above, since it already came up
twice in five turns of manual play (Assyria, Sweden) -- likely to keep recurring.

## Same session, turn 264: another ambient rendering crash (`Civ5XP[c90534]`, same family as `[c90232]`
## ~29 min earlier -- matches the documented 20-40 min cadence), then a REAL crash-recovery bug: `load_save
## ("QuickSave")` silently loaded a save 3-4 turns stale because a newer AUTOSAVE existed on disk

Relaunched (`sp12`) and reconnected tunerd fine. Recovery reflex was `load_save("QuickSave")` (muscle memory
from every earlier recovery in this file) -- came back `{ok:true, turn:257}`. That's wrong: this same
session had already played turns 258-264 (including the two live-verified `accept_friendship` calls above),
and turn_state() confirmed only turn 258 after the "load". **Root cause, found by listing actual save files
by filesystem mtime**: `Saves/single/auto/AutoSave_0260 AD-1750.Civ5Save` (mtime 19:52:35) was newer than
BOTH `QuickSave.Civ5Save` candidates (newest at 19:29:06) -- the periodic engine autosave had run during this
session's manual play, after the last explicit quicksave, and `load_save("QuickSave")` never looks at
autosaves at all when a quick/manual match already exists (by design -- see its own docstring: `show_auto`
iterates `false` then `true`, stopping at the first non-empty match, and "QuickSave" always matches in the
`false` pass). Not a bug in `load_save` itself -- it does exactly what a name-based load should -- but the
*recovery reflex* of reaching for `load_save("QuickSave")` specifically is wrong whenever autosaves are on
and the last explicit quicksave predates the crash by more than one autosave interval, which is common.
Loaded `load_save("AutoSave_0260 AD-1750")` instead (exact basename) and recovered to turn 261 -- lost the
turn 261-264 diplomacy/tech-research actions from before the crash, but far less than reverting to 257 would
have.

**Fixed properly, not just worked around**: added `Game.load_latest()` (`harness/game.py`, plus
`mcp_server.py`/`http_server.py` wrappers) -- gathers `UI.SaveFileList` for BOTH `showAutoSaves` values
(no early break) and loads whichever single file has the newest real mtime via the existing `_newest_save`
helper, reusing `load_save`'s post-selection logic (`Events.PlayerChoseToLoadGame` + `LoadScreen` dismiss)
via a new shared `_finish_load()` method. Not yet live-tested end-to-end (written after this session's
recovery already completed via the manual autosave-name workaround) -- verify on the next real crash that
`load_latest()` alone reaches the same result before trusting it as the new default recovery reflex.

**Live-verified minutes later on an actual third crash this session** (turn 263, another ambient
`Civ5XP[c90232]`/`[c90534]` double-fault, only ~6 minutes after the previous one -- notably faster than the
20-40 min cadence documented elsewhere in this file, though not enough data points yet to call that a real
pattern shift). Relaunched (`sp13`), reconnected tunerd, called `load_latest()` directly with no manual
mtime-checking -- came back `{ok:true, turn:261}`, independently confirmed correct by listing the actual
save files by mtime right after (`AutoSave_0260 AD-1750` newest on disk, exactly what it picked). This is
now the trusted default crash-recovery call going forward; `load_save("QuickSave")` should only be reached
for when you specifically want the named quicksave over a possibly-newer autosave.

## Manual-play gap: no way to notice a stuck popup or new AI event except by actively polling; user
## caught a TechPopup that sat open long enough they clicked it themselves rather than risk a crash

Turn ~271: research (Steel, cheap at 485 cost) finished between two of this session's tool calls while
attention was on other things (World Congress, city production). The resulting TechPopup (choose the next
tech) sat open on the real game window for a while with nothing on the harness/agent side noticing --
`dismiss_pending_popups()` correctly refuses to auto-dismiss it (by design: it only clears TechPopup once a
next research IS already chosen, never picks one for you). The user, watching the actual window and not
wanting to risk a crash by leaving a real popup open indefinitely, clicked it away manually rather than
wait. Separately, a World Congress session came into `in_session` with a real vote pending and was also only
caught because the user flagged it -- `league_status()`'s `in_session`/`votable` aren't part of any
turn-blocking check either (voting is optional, not a hard end-turn block, unlike `ENDTURN_BLOCKING_LEAGUE_CALL_FOR_VOTES`
proposals).

**Root problem**: this harness's whole design (and every prior session's driving pattern) is pull-based --
nothing surfaces until a caller explicitly asks (`turn_state()`, `discussion_pending()`, `league_status()`,
`tech_popup_pending()`). A human/LLM driving turn-by-turn only sees these between its own actions, so
anything that changes state *while attention is elsewhere* (an AI trade offer, a completed research, a
League session opening) is invisible until the next explicit check -- exactly the class of thing the user
flagged twice in one session.

**Mitigation, not a full fix**: added `scripts/watch_game.py`, a standalone poll loop (default 6s) that
prints one line whenever `turn_state`/`league_status`/`tech_popup_pending` change, and opportunistically
calls the existing `dismiss_pending_popups()` each pass (safe subset only -- see its own docstring; never
touches discussion dialogs or league votes, which always need a real decision). Meant to run continuously
alongside manual play in a separate process/terminal (or, in an agent session, under a background
poll/notify mechanism) so a human or LLM driving the game gets pushed a signal instead of having to keep
re-polling or waiting for someone watching the screen to say something. Does not solve the deeper problem
of "no true event push from the engine itself" -- this is still polling, just polling on a timer instead of
on the driver's own action cadence, and a genuinely instantaneous popup (or one that resolves itself within
one 6s window) can still be missed.

**The watcher immediately paid off**: within a minute of it running, the user reported a popup was STILL up
on the real game window right after `dismiss_pending_popups()` had already run and found nothing. Checked
every likely candidate state's `ContextPtr:IsHidden()` directly (`LeagueOverview`, `VoteResultsPopup`,
`DiploVotePopup`, `TechPopup`, `WonderPopup`, `GreatWorkPopup`, `WhosWinningPopup` -- all `false`/hidden) and
found the real culprit: `LeagueSplash` (the "here's what happened at the World Congress" summary screen,
shown right after casting the League votes above) read `true`/visible. Unlike GreatWork/WhosWinning,
`ContextPtr:IsHidden()` is actually RELIABLE for this one (confirmed both directions) -- this was a pure
coverage gap, not another unreliable-IsHidden case. Its own `OnClose()` (fires
`SerialEventGameMessagePopupProcessed` for `BUTTONPOPUP_LEAGUE_SPLASH` then `UIManager:DequeuePopup`) closed
it cleanly, confirmed by re-checking `IsHidden()` after. **Fixed generally**: added `LeagueSplash` as its own
explicit case in `dismiss_pending_popups()` (`harness/game.py`), calling `OnClose()` directly rather than
assuming a bare `SetHide(true)` would be equivalent (untested, and GreatWorkPopup already showed those two
aren't always interchangeable). The already-running watcher instance had the old code loaded in memory, so
it was stopped and restarted from `scripts/watch_game.py` (the persisted copy) to pick up the fix.

## Root-caused the actual crash instead of just recovering from it: this is a known Civ5 Linux-port bug
## (CPU affinity / logical-core count), not a harness/MCP-induced crash

User pushed back on chasing crash-recovery mechanics alone: "focus on why the game is crashing before the
MCP server ... it's likely a known issue if you look online -- we may be conflating true MCP-induced crashes
with linux port flakiness." Web search confirmed it immediately: Steam Community threads document a
long-known Civ5 Linux-port bug where the game segfaults on machines with >8 logical CPUs, with the exact
crash address `Civ5XP+0xc90534` reported by other players -- identical to one of the two addresses
(`c90232`/`c90534`, ~29 min and ~6 min apart respectively this session) crashing here. This machine is a
12-thread Ryzen 5 3600XT (`nproc`=12, 6c/12t) -- squarely in the affected range. `config.ini` already had
`MaxSimultaneousThreads = 8` set (the commonly-cited fix), but crashes kept happening anyway: that setting
only caps the engine's own worker-pool size, it does NOT change what CPU topology the process observes via
`get_nprocs()`/`sched_getaffinity()` -- whatever code path indexes a per-hardware-thread array by that raw
topology count still sees 12, not 8, regardless of the pool-size hint. The actual fix reported by affected
users is `taskset -c 0-7 %command%`, restricting the process's CPU affinity mask itself.

**Fixed in `scripts/launch_civ5.sh`**: added a `CIV5_TASKSET` env var (default `0-7`) that wraps the whole
launch chain (reaper -> pressure-vessel -> Civ5XP) in `taskset -c $CIV5_TASKSET` -- affinity is inherited
across fork/exec, so this reaches the actual game binary without needing to reach into the sandboxed
container separately. Live-verified the mask actually lands on the real leaf process, not just the reaper
wrapper (`ps -eLf | grep Civ5XP` to find the true PID -- `pgrep -f Civ5XP` matches the reaper too, since its
own argv contains "Civ5XP" as the final arg): `taskset -cp <real Civ5XP pid>` read back `0-7` after relaunch.
Set `CIV5_TASKSET=""` to disable on a machine with 8 or fewer logical cores where this doesn't apply.

**Not yet conclusively proven fixed** -- this needs the game to survive a full multi-hour session without
the `c90232`/`c90534` signature recurring before calling it closed; a false negative from just "no crash in
the next 20 minutes" is possible given the ambient cadence was already irregular (6-29 min observed). Next
session: if this exact signature reappears even with taskset applied and confirmed active, the bug is either
not what the community threads describe or needs a lower core count / different affinity mask.

Also added a related independent mitigation while investigating, since crashes will keep costing lost turns
until/unless the above is fully confirmed: `end_turn(autosave=True)` (the harness default now) calls
`UI.QuickSave()` right before `CONTROL_ENDTURN`, single-player only. Confirmed this does NOT create
per-turn files -- `UI.QuickSave()` always writes the same fixed path (`Saves/single/quick/QuickSave.Civ5Save`,
~1.3MB), overwritten in place each call (checked file listing + mtime before/after) -- not a storage
accumulation risk despite firing every single turn.

## A left-open TechPopup stacked with WhosWinningPopup and became unclearable via Lua -- only physical
## Escape (twice) fixed it; this may be a genuine "we act faster than the engine renders" hazard

Turn ~274: research (Gunpowder) had completed, opening a TechPopup, while other actions (dismissing several
trade-offer discussions, checking city production) continued without addressing it first. The user, watching
the real game window, reported it never actually went away, then reported "a new, second full-screen popup
has attempted to render and they are fighting one another on the screen" -- confirmed live to be
`WhosWinningPopup` stacked on top/underneath it. **Every dismissal attempt from the Lua side failed**:
`dismiss_pending_popups()` (which does include both TechPopup and WhosWinningPopup handling) found nothing;
`tech_popup_pending()`/the `TechBackground` check read `false` (not visible) throughout, even while the user
confirmed the popup was genuinely on screen; forcing every single named control on both popups to
`SetHide(true)` directly via raw `lua()` calls, plus `ContextPtr:SetHide(true)`, did not clear the visual
conflict either. **What actually worked**: the user pressed physical Escape twice, which cleared each popup
in reverse order of appearance -- exactly matching a real per-popup `InputHandler` (`KeyDown` +
`VK_ESCAPE` -> that popup's own `ClosePopup()`/`OnClose()`) being processed one at a time through the
engine's normal per-frame input+render loop, which our batched tuner `exec()` calls (multiple Lua mutations
fired back-to-back with no real frame render settling between them) evidently do not reproduce once two
popups are already stacked.

**Working theory, not confirmed**: this harness drives the game by calling engine/Lua state directly
(`Network.Send*`, `Game.DoControl`, raw `Controls:SetHide`), which can act *underneath* a modal that would
physically block a human player's mouse/keyboard input -- confirmed explicitly by the user ("you are hitting
'next turn' behind a modal that would normally be un-click-through-able to a human"). Whether this is purely
a visual/rendering-settle problem (most likely, given `TechBackground:IsHidden()` read `false` the whole
time -- suggesting the ENGINE genuinely considered it hidden, just hadn't redrawn the screen) or is
occasionally masking a REAL state inconsistency (two Lua states both trying to claim modal focus, not just a
stale frame) is not yet known. Given this project's history of ambient rendering-stack segfaults
(`WonderRenderJob`, `Civ5XP+0xc90232/0xc90534`), a plausible follow-up hypothesis worth testing later: does
driving actions faster than the UI would ever naturally pace them (no per-click render settle time, unlike a
real player) increase the rate of those crashes, independent of the already-confirmed CPU-affinity cause?
Not tested this session -- noted for future investigation, not concluded.

**Process fix adopted for the rest of this session (not yet a code change)**: the moment research completes
(`summary()`'s `research` going empty, or any turn transition implying a tech finished), stop before any
other action -- diplomacy, production, `end_turn()` -- and clear the TechPopup first via `tech_popup_pending()`/
`dismiss_tech_popup()`, re-verifying before moving on. Letting other popups (trade offers, embassy requests)
queue up on top of an unhandled TechPopup appears to be exactly what caused the stacking/fighting above.
If Lua-side dismissal genuinely doesn't clear it, tell the user rather than continuing to hammer it
programmatically -- physical Escape is the only thing that worked live.

## Steam Deck seat: first crash is a NEW signature, in the gameplay DLL, not the known Civ5XP rendering/affinity one (2026-09-17)

Deck (8 logical CPUs, native Linux build, shim loaded, no taskset since the >8-core bug does not apply) crashed
about a minute into a fresh LAN game (3 seats: Claude host on desktop, Grok on the Deck, 1 AI; Continents/Small):

```
kernel: Civ5XP[22095]: segfault at 14 ip 00000000c555f53b sp 00000000e14fd080 error 4
        in libCvGameCoreDLL_Expansion2.so[28553b,c52da000+55f000]
```

- `segfault at 14` = NULL-pointer dereference (+0x14 field read) inside `libCvGameCoreDLL_Expansion2.so`
  at file offset 0x28553b. That DLL exports only two dynamic symbols (`DllGetGameContext` and one more), so
  it cannot be symbolicated with `nm -D` the way the Civ5XP crashes were; an objdump around 0x28553b is the
  only next step. Same DLL build as the desktop (md5 01337dcf12d3...).
- This is NOT the desktop's `Civ5XP[c90534]`/`[c90232]` family (rendering subsystem, mitigated by pinning to
  8 CPUs). Different binary, different cause. Graphics were already at minimum, smallest window, 2D map view.
- Context: the Deck instance had just loaded into the launched game as a LAN client (seat 1, Siam) and the
  other LLM had started its turn 0. Whether one of its tool calls triggered it is unknown: that seat's tunerd
  log was deliberately not read (it is another player's private game). If it recurs at the same offset on the
  first turn, suspect a gameplay call rather than ambient instability.
- Recovery: LAN clients can rejoin a game in progress (`cli join-lan <host-ip>`); the host kept running with
  `everyone_connected: true` and the dropped seat listed as not connected. No host restart needed.

## 2026-09-17 (eighth session): solo China game, turns 0-97, five harness fixes found by playing

Fresh single-player game (Wu Zetian / China, Emperor, small map). Played by hand through the real MCP
tool layer (`scripts/mcp_call.py --seat 0 ...`; note the sandbox needs `XDG_RUNTIME_DIR=/run/user/1000`
or tunerd's socket path resolves to nothing). Status at turn 97: four cities (Beijing t1 on a river hill,
Shanghai t41 coastal by Uluru, Guangzhou t68 beside a mountain, Nanjing t82 in the northern desert), two
barbarian camps cleared, Liberty through Meritocracy, trade route to Antwerp, met Sweden by sea at t94.
The landmass is shared only with the city-states Antwerp (south) and Ur (further south-west).

Harness bugs found live and fixed (runtime.lua v32 -> v38, all committed individually):

1. **`move_unit` silently no-op'd on unreachable destinations.** `CanStartMission(MISSION_MOVE_TO)` is
   true for any valid plot; the engine then drops the mission and the unit sits with full moves while the
   call reports `ok`. Hit twice: a scout ordered onto Uluru (natural wonder, `IsImpassable`), and a settler
   + an archer ordered onto (30,23), a **mountain whose terrain type reads GRASS** -- `map_window` does
   carry a `mountain` flag but nothing else hints at it. Fix: refuse `IsImpassable()` plots and
   `IsMountain()` plots (the latter via `CanMoveOrAttackInto`). `Unit:GeneratePath` is **NYI** in this
   build (throws), and `CanMoveOrAttackInto(dest)` is false for perfectly legal multi-step destinations
   (it refused a warrior entering its own adjacent city), so it is only consulted for the mountain case.
2. **`choose_promotion` never actually promoted.** `SetHasPromotion(id, true) + SetPromotionReady(false)`
   set the flag but left the unit at level 1 and skipped one-shot effects: PROMOTION_INSTA_HEAL healed
   nothing. The UI path is `Game.HandleAction` on the *selected* unit (UI.SelectUnit flips 2D/3D, so no);
   `Unit:DoCommand(CommandTypes.COMMAND_PROMOTION, id, -1)` runs the same `CvUnit::promote()` locally and
   is what the tool now uses (verified: level 1->2, 48hp->98hp on insta-heal, promotion consumed).
   `CanDoCommand` is false right after the unit's own ranged attack (still "busy"); the tool now refuses
   in that case instead of falling back to the bare flag (which had to be repaired by hand once).
3. **Every worker `MISSION_BUILD` was refused as "action is not currently legal".** `unit_mission` called
   `u:CanBuild(b)`; the Lua signature is `CanBuild(plot, build)`, the call errored ("Instance does not
   exist"), the pcall swallowed it. Now passes `u:GetPlot()`. (Whatever the earlier sessions verified
   MISSION_BUILD with, it wasn't this code path.)
4. **`NewEraPopup` was never swept**: it was in `_SWEEP_POPUP_STATES` but had no entry in the handlers
   dict, so BUTTONPOPUP_NEW_ERA stayed pending after the sweep at the Classical era. Added `OnClose`.
5. Two-tile `move_unit` into a plot adjacent to a barbarian camp was dropped where a one-tile move worked
   -- not root-caused (may be the same mountain plot as in (1); it was (30,23)).

Play notes worth keeping:
- **Hex distance:** odd-r offset. Odd row neighbours at row±1 are x and x+1; even row: x-1 and x. A city
  strike / archer shot "at 2 tiles" that comes back "not legal" is usually distance 3 in truth.
- A ranged unit in forest/jungle usually has no line of sight 2 tiles out; step onto a hill or open tile.
- Barbarian camps on Emperor respawn a brute every few turns; two warriors + an archer clear one, and
  PROMOTION_INSTA_HEAL (now that it works) is the difference between winning and losing that fight.
- City-state territory is freely passable (no DECLAREWARMOVE popup for Antwerp).
- Trade route to Antwerp was plundered once by a barbarian hidden in fog on the jungle path; a warrior now
  sits on the river hill at (27,19) along that path.
- Sweden's first contact arrived as a trade-screen embassy offer (DIPLO_UI_STATE_TRADE_AI_MAKES_OFFER):
  `wait_for_my_turn` returns early with `discussion_pending: true` and `my_turn: false` -- **read that
  field**; I filtered it out of a grep and spent ten minutes thinking Sweden's AI turn had hung.
  `accept_deal` answered it (`DiploTrade.OnPropose`).
- `available_research` is right when The Wheel is missing: it needs Archery too.
- Happiness went to -2 at the fourth city; the 250-gold Antwerp gift only reaches 25 influence (friends
  at 30), so the plan is Construction -> Colosseums plus Meritocracy city connections (road Shanghai-Beijing
  under way).

## Ninth session (2026-09-17, ~07:40 onward): China game t190-218, upgrade_unit, instant-build fix

Played by hand via `scripts/mcp_call.py --seat 0`. Turn 190 -> 218. Beliefs/policies/production chosen
turn by turn; quick_save before every end_turn (scratch `endturn.sh` wrapper: status -> save -> end ->
wait -> digest/ready/needs-production).

Harness changes (commit 2b4fcd9, runtime v41 -> v42):

- **`upgrade_unit` tool / `/upgrade_unit` route / `Game.upgrade_unit`.** `Network.SendDoCommand` does
  not exist (probed live: nil), so it uses `Unit:DoCommand(COMMAND_UPGRADE, -1, -1)` exactly like
  `choose_promotion`. The engine replaces the unit object: the old id dies (a `unit_destroyed` event
  shows up in the next digest), a new unit of the upgraded type appears on the same plot and the new id
  is returned as `unit_id` (`old_unit_id` is the one passed in). `old_still_exists` reads true inside
  the same Lua call because the kill is deferred; ignore it. Live-verified five times: Warrior ->
  Swordsman (80g) x3, Composite Bowman -> Chu-Ko-Nu (100g) x2. `CanUpgradeRightNow()` false-cases seen:
  a bowman fortified one tile outside our borders (moved it onto an owned tile, then it worked).
- **`unit_mission` MISSION_BUILD false failure fixed.** The engine applies the current turn's work
  inside `PushMission`, so a build whose remaining work fits in one turn (BUILD_REPAIR on a pillaged
  pasture t196 and quarry t198, both finished instantly) returns with `GetBuildType() == -1` and the
  harness reported "mission accepted but did not start a build". `H.unit_mission` now snapshots the
  plot (improvement / pillaged / route / route-pillaged / feature) before pushing and returns
  `{ok:true, completed:true}` if the plot changed. The eighth-session note "repair failures explained:
  target improvements no longer pillaged" was this same bug seen from the other side.

Observed, not fixed:

- **`incoming_deal` can show a stale merged deal.** After `refuse_deal` (DiploTrade.OnBack) of
  Washington's Dye-for-6gpt offer, his *next* offer (an embassy swap, per the speech) read as 5 items:
  the old Dye + gpt items plus two embassies. The scratch deal apparently keeps the refused items until
  something clears it. Refused that one to be safe. Other leaders' subsequent offers read clean (n=2).
  Worth checking whether `refuse_deal` should `ClearItems()` after OnBack, or whether `incoming_deal`
  should read the AI's proposed deal from a different source than `UI.GetScratchDeal()`.
- `BUILD_FARM` was "not currently legal" on flat grass (29,24) next to Guangzhou (river/fresh-water
  unknown) while a trading post was fine there, and a farm was fine on similar grass at (31,24) and
  (25,21). Not investigated; the CanBuild guard is honest, the reason is a game rule I did not chase.
- `available_unit_actions` for a Worker does not list any BUILD_* entries even when builds are legal
  (only SKIP/SLEEP/AUTOMATE/MOVE...). Builds have to be tried via `unit_mission(build=...)`.
- `move_unit` to a multi-turn destination reports the unit's *current* plot after the first leg with
  `activity: 6` (MISSIONING), e.g. asked for (29,22) it reported (29,25); it arrived two turns later.

Play notes: Iron Working had never been researched at t191 (army was 4 Warriors + 2 Composite
Bowmen); fixed via Iron Working -> Machinery -> Metal Casting -> Physics -> Acoustics -> Chivalry.
India traded 1 Iron for open borders (t212). Refused Sweden's coop war vs Poland (t201), refused all
Dye-for-gold offers while happiness was 0, refused Poland's open borders twice (they are at war with
Sweden from t214). World Congress founded t211 (Venice host); proposed Scholars in Residence. Spy
placed in Stockholm. Great Writer -> Political Treatise -> Consulates (t195). Great Prophet -> enhanced
Taoism with Swords into Plowshares + Religious Texts (t213). Circus Maximus took happiness from -1 to +4.

### Ninth session addendum: t219-229

- **`steal_tech_options` / `steal_tech`** (commit 98e8440, runtime v43) clear `ENDTURN_BLOCKING_STEAL_TECH`.
  `Network.SendResearch(tech, p:GetNumFreeTechs(), victim, false)` is the CHOOSE_TECH_TO_STEAL message.
  Live: stole Steel from Sweden t219. The grant raises BUTTONPOPUP_TECH_AWARD and the blocker stays set
  until that popup is swept -- `steal_tech` now runs `dismiss_pending_popups()` and reports `blocking`.
- The instant-completion fix (v42) has now been confirmed live three times: quarry/pasture repairs,
  a BUILD_REPAIR of a pillaged trading post (t221), and a Great Scientist's BUILD_ACADEMY (t228) --
  all return `{ok:true, completed:true}` where the old code said "did not start a build".
- Re-read of the "stale incoming_deal" observation: tradelogic.lua's OnBack (non-PVP) *does*
  `g_Deal:ClearItems()`, so Washington's 4-item read (Dye + gpt + embassies) was most likely the real
  bundled offer, with the speech line keyed off a different item. Treat `incoming_deal` as truthful;
  the earlier "stale" note above is downgraded to "unexplained once, not reproduced".
- Two civilian units cannot share a tile: `move_unit` of the Great Scientist onto a tile with a
  sleeping Worker returned ok with no position change (the known silent no-op). Moved to another tile.
- Barbarian Crossbowman raid on Guangzhou t219-220: Chu-Ko-Nu + city strike + Swordsman melee (via
  `move_unit` onto the enemy plot) killed it; it pillaged one trading post first, repaired t221.
- Accepted DoF with Poland (t220), embassy swaps with Venice/America(refused: bundled Dye)/India/Poland,
  Iron-for-open-borders from India (t212) and Venice (t223) -> 4 iron, all four Warriors are Swordsmen.
  Opened Rationalism t227. Great Scientist -> Academy at (23,22) t228.

## Tenth session (2026-09-17, ~09:30 onward): `propose_deal` finally works -- through the real trade screen

The user nudged ("you could propose the offer") while I was stuck at -1 happiness with a spare Dye and no
way to offer it. Direction (2) from the "external research" entry above -- drive the actual trade-screen
popup open before touching the Deal -- was the one thing never tried. It works, first time, no crash.

**Root cause of all eight earlier crashes, now confirmed live**: the native deal-mutation calls need a trade
*session* open in the engine. The human UI starts one from the leader screen's Trade button
(`leaderheadroot.lua` `OnTrade`): `Players[ai]:DoTradeScreenOpened()` + `UI.OnHumanOpenedTradeScreen(ai)`.
That fires AILeaderMessage(DIPLO_UI_STATE_TRADE) -> `tradelogic.lua`'s `LeaderMessageHandler` queues the
DiploTrade popup and initialises `g_Deal` (= `UI.GetScratchDeal()`) with from/to. With that session open, the
very same `Add*` calls that crashed before (made via tradelogic's own global pocket handlers
`PocketResourceHandler(isUs, rid)`, `PocketGoldPerTurnHandler(isUs)`, ...) and `OnPropose()` ->
`UI.DoProposeDeal()` behave exactly like mouse clicks: the AI answers through the normal AILeaderMessage path
(`Controls.DiscussionText` in DiploTrade changes to "Unacceptable." / "This is not at all acceptable...", or on
acceptance the trade screen closes and a DiscussionDialog shows "I graciously accept.").

The exact sequence, each step verified live (Venice, America, Sweden, India; ~12 open/close cycles):
1. InGame: `UI.SetRepeatActionPlayer(o); UI.ChangeStartDiploRepeatCount(1); Players[o]:DoBeginDiploWithHuman()`
   (what `diplolist.lua` does when you click a leader). `UI.GetLeaderHeadRootUp()` goes true within ~0.5 s.
2. LeaderHeadRoot context: check `Controls.TitleText:GetText() == GameplayUtilities.GetLocalizedLeaderTitle(Players[o])`
   (GameplayUtilities only exists in UI contexts, nil in InGame) and `Controls.TradeButton:IsDisabled()`; then `OnTrade()`.
3. DiploTrade context (tradelogic.lua's globals are `local` -- `g_Deal`, `g_iThem`, `PROPOSE_TYPE` are unreadable
   from a tuner exec, but every `function Name(...)` is global): pocket handlers to add items; amounts via
   `UI.GetScratchDeal():ChangeResourceTrade/ChangeGoldTrade/ChangeGoldPerTurnTrade(...)` + `DisplayDeal()`
   (same object as g_Deal). `H.incoming_deal` (InGame) reads the table back -- it is the same scratch deal.
4. `OnPropose()`; poll DiscussionText / DiploTrade hidden / DiscussionDialog visible. Truth for "accepted" is
   `UI.GetNumCurrentDeals(pid)` going up, not the text.
5. Close: DiploTrade `OnBack()` (also tells the AI via DoTradeScreenClosed), DiscussionDialog `OnBack(true)`
   for a button-less remark, LeaderHeadRoot `OnReturn()`. Loop until all three are down.
   AI-assist buttons also work headlessly: `OnEqualizeDeal()`, `OnWhatWillAIGive()`, `OnWhatDoesAIWant()`.

**Two gotchas that cost a spare Copper.** (a) Opening a second leader while the previous leader screen is still
up ("Anything else?" after a trade) leaves tradelogic's `g_iThem` on the OLD counterpart even though
LeaderHeadRoot shows the new one -- my Copper-for-Spices to "America" went to Venice. (b) Adding a resource the
other side does not own puts it on the table at amount 0 (the pocket handler clamps to `GetNumResource`), and
the AI happily accepts "1 Copper for 0 Spices". Venice got a free Copper for 30 turns (t231-261). Both are now
guarded: every open verifies the leader title and the table's counterpart, every add is read back and any
item missing or clamped aborts before proposing, and a legality pre-check (`trade_catalog`) runs before
any screen opens.

Harness (runtime v43 -> v44, only to retire the headless `H.propose_deal` body):
- `Game.propose_deal(other, items, ask_counter=False)` / MCP `propose_deal` / `POST /propose_deal`: whole
  flow in one call; returns `accepted`, `reply`, `table`, `counter` (the AI's equalized version on
  rejection when asked), `closed`, and measured `effects` (gold, gpt, happiness, deal count, per-resource
  import/export before vs after). Nothing to poll afterwards -- the user's "the MCP keeps the player on
  track" principle.
- `Game.negotiate_deal(other, items, mode)` / MCP `negotiate_deal` / `POST /negotiate_deal`:
  equalize / what_will_ai_give / what_does_ai_want without proposing.
- `Game.close_trade_screens()`: the cleanup loop; `_open_trade_screen`, `_add_deal_items`, `_check_deal_items`.
- `guarded` in mcp_server.py now turns ANY exception into a JSON error (a KeyError in the new code surfaced
  as the MCP layer's bare "Error executing tool" and left the leader screen up).
- Human recipients (PvP `OnOpenPlayerDealScreen` path) are refused for now; DECLARATION_OF_FRIENDSHIP and
  PEACE_TREATY items are not offered (peace: the leader screen's own "negotiate peace" button is
  `FROM_UI_DIPLO_EVENT_HUMAN_NEGOTIATE_PEACE`, a natural next step; it opens the same trade screen with
  the treaty pre-added).

Market reality at t231 (Emperor, everyone already owns Dye): nobody pays for my spare Dye; every AI's
"what do you want for X" answer for a luxury was 2-3 of my luxuries plus embassy/9 gpt. Happiness stays -1
until Zoos.

### Tenth session addendum: t231-247, four more "keep the player on track" fixes

- **`turn_status.todo`** (runtime v47): units awaiting orders, promotion-ready units, cities with an empty
  queue, research unset -- computed for the active seat. One read replaces units()+cities()+overview() polling.
- **`available_trade_routes`** yields were x100 and one-sided (a 611 meant 6.11 gpt; internal food/production
  routes read as all zeros). Now per-turn for both ends plus `kind`.
- **`unit_mission`** returns the unit's position/moves afterwards, or `consumed: true` (Great Person missions).
- **`set_research` false failure on a free tech**: Oxford's free Industrialization was granted with current
  research untouched, and the "research did not change" check reported an error while the blocker was
  already clear. Now: with free techs pending, success = the tech is known (`granted`).
- **`unit_destroyed` false positives**: SerialEventUnitDestroyed is a graphics event -- it fired for all four
  workers on the Industrial era change (t244), for caravans starting a route and for the used Great Writer.
  `events_since_last` now checks the live unit list and relabels survivors `unit_graphics_reset`.
- **Fog leak fixed** (runtime v45): `describe_plot` read `IsImprovementPillaged` before the visibility gate.
  Tests updated (stubs lagged move_unit/unit_mission/accept_deal); 32/32 pass via `uv run --with pytest pytest -q tests`.
- Live-verified this session: league_cast_votes (1 vote, Scholars in Residence passed), league_propose_enact
  (Sciences Funding), naval move_unit (Caravel took a 4-tile coastal path), MISSION_GIVE_POLICIES (+216 culture),
  city_ranged_attack + MISSION_RANGE_ATTACK vs barbarians (Chu-Ko-Nu double shot works), BUILD_REPAIR instant.
- The `lua` escape hatch in mcp_server.py is deliberately not registered as an MCP tool ("Unknown tool: lua");
  use `Game().q(...)` from Python for ad-hoc reads.

## Eleventh session (2026-09-17, ~11:00 onward): "first-time LLM" pass -- t247 onward, runtime v47 -> v53

Theme for this session (user's brief): play, and at every step ask "how would an LLM meeting this
server for the first time want to be told what it can and cannot do?" Each item below was found by
hitting it live, not by review.

- **Workers listed no builds at all.** `available_unit_actions` called `Unit:CanBuild(build)` with one
  argument; that form errors, the pcall swallowed it, and every BUILD_* action was silently "not legal" --
  so a new caller had no way to discover that a Worker can farm/mine here. Fixed (`CanBuild(plot, build)`,
  the same fix unit_mission already had) and added `nearby_builds`: a radius-2 scan of plots that still
  need work (no improvement, or pillaged) with the builds legal on each. First draft listed every plot
  (you can always overbuild a FARM/TRADING_POST/FORT) and buried the two real jobs in 15 entries; now only
  unimproved/pillaged plots, FORT and REMOVE_ROUTE dropped, routes listed separately.
- **`growth_turns: 5165`** is the engine's sentinel for a stagnant city (GetFoodTurnsLeft with zero
  surplus). A human sees "Stagnant"; the raw number reads as a bug or a 5000-turn wait. `cities` now
  reports `growth` = growing|stagnant|starving with `food_surplus`, and `growth_turns` only while growing.
- **`players` looked like "everyone" but lists human seats only** (one entry in a solo game). Docstring now
  points at `diplomacy` for AI civs and their player_ids, which the trade/diplomacy tools need.
- **Attacks returned `{ok:true}` and nothing else.** `city_ranged_attack` and
  `unit_mission(MISSION_RANGE_ATTACK)` now read the target plot before, poll until it changes (the attack is
  an async net message), and return `target_before/target_after`, `damage_dealt` or `killed`. Live: city
  27 dmg, Chu-Ko-Nu 29 then the kill, all reported in-call -- no digest reading needed to know the result.
- **`end_turn` refusal said only "turn has unresolved decisions"** with the blocker's enum name. Now the
  err carries a per-blocker hint (which tool clears it; `H.blocking_hint`, 24 ENDTURN_BLOCKING_* types
  covered, including the ones with no tool yet) plus the `todo` list; `turn_status` gains `blocking_hint`.
  `H.todo()` extracted from turn_state so both use one implementation.
- **`turn_digest` was polluted by my own trade-screen visits**: every negotiate_deal produced 3-4
  `leader_message` events ("Let's hear your offer", "What do you propose?") indistinguishable from an AI
  approaching me. `_open_trade_screen` sets `H.harness_diplo` until the screens close; the AILeaderMessage
  hook tags those `harness_initiated` and events_since_last drops them (relationship().history keeps them).
- **`move_unit` into the unknown**: the refusal ("plot is not revealed") now carries `nearest_revealed`,
  the closest revealed, passable plots of the unit's domain around the target, so an explorer can step to
  the edge of the map instead of guessing coordinates. Advisory: the scan is inside a pcall and the err
  text is unchanged (a test pins it). Live: Caravel asked for (30,13), was offered (29,13); took it.
- **`minor_gold_gift` returned pre-gift numbers** (friendship 20 / gold 376 after a gift that took
  friendship to 50 / gold to 126): same async-mutation class as set_production's old bug. Now polls
  city_state_gifts and reports before/after. `diplomacy` lists each city-state's `trait` and `influence`
  -- Antwerp is MERCANTILE, and the 250g small gift (during its "seeks investors" quest) took empire
  happiness from -1 to +2 and science 164 -> 180. Cheaper than the 740g Zoo I was saving for.
- **`activity: 2`** in unit results is now paired with `activity_name` (SLEEP_OR_FORTIFY, MISSION, ...).
- **Server `instructions`** rewritten around the solo loop (wait_for_my_turn -> turn_digest -> turn_status
  todo/blocking_hint -> act -> end_turn) and the rule that a refusal never crashes and says what to do.
- **Not polling**: `scripts/et.sh` (quick_save -> end_turn -> wait_for_my_turn -> digest/overview) run as a
  *background* job is the "MCP pings me" pattern from inside Claude Code: the session is re-invoked when
  it exits, i.e. when it is my turn again or an AI needs an answer mid-turn (wait_for_my_turn returns early
  on `discussion_pending` -- Sweden's coop-war request against Poland arrived that way; declined with
  respond_discussion button 1). It stops instead of waiting when end_turn is refused.
- Pre-existing test failure fixed: `test_unit_mission_python_does_not_select` counted exactly one query,
  but unit_mission gained an after-state read last session; it now asserts no UI select in any call.
- **`move_unit` returned ok:true for a move that never happened.** The Caravel was ordered onto a
  newly sighted plains plot (t252): CanStartMission(MOVE_TO) is true for it, the engine drops the mission,
  and the harness reported the pre-move position with ok:true. Two fixes: (a) Lua refuses wrong-domain
  destinations up front (ship -> land unless a city; land unit -> water unless it can embark), (b) Python
  reports `ok:false, "unit did not move: the engine found no path"` when nothing changed within the
  settle window and the unit still had moves; a 0-move unit keeps the order queued (`queued: true`).
- **`spies` returned raw TXT_KEY_ names/ranks/states**; now localized, with `state_key` kept for code.
  `available_spy_cities` said pass `city_id` "straight into move_spy", whose parameter is `target_city_id`.
- **`establish_trade_route` returned only ok:true.** Now confirms via the international-route count
  (`established`, `routes_used`, `routes_available`); the caravan stays alive walking the route so the
  unit's existence proves nothing.
- World Congress mid-turn: turn_status said ENDTURN_BLOCKING_RESEARCH while a "Choose Host" vote was
  also open (league_status.in_session); votes cast fine before research was set, so the blockers are
  independent, not sequential.
- **`trade_routes` read tool** (runtime v57): `Player:GetTradeRoutes()` is the Trade Route Overview's own
  data -- from/to city, TurnsLeft, yields x100. A caller finally knows *when* each caravan comes home.
  establish_trade_route now confirms by that list gaining an entry: `GetNumInternationalTradeRoutesUsed`
  read 5 before AND after a successful establish (it counts trade units, not routes), and the caravan is
  consumed and re-created under a new unit id when the route starts, so the unit id vanishing is normal.
- **Do not edit `scripts/et.sh` while a background copy is running**: bash reads scripts incrementally,
  the running instance executed a half-line ("ntil: command not found") and re-entered the wait loop.
  Harmless that time (it was already my turn), but write to a temp file and `mv` over it next time.
- **et.sh was passing `{"timeout": 900}` to a tool whose parameter is `timeout_seconds`**: pydantic
  ignores the unknown key, so every wait used the 90s default. AI turns here take ~60s so it never bit,
  but a long AI turn would have "returned" with my_turn=false and the script would have carried on.
  Fixed (loop until my_turn or discussion_pending). Worth remembering for any caller: MCP tool argument
  typos are silent.
- **Closed borders** (runtime v58): a destination inside another major civ's territory without open
  borders (and not at war) is refused by name ("inside India's borders ... no open-borders agreement")
  instead of the engine dropping the order silently. City-state land is open, so minors are exempt.
- **Queued multi-turn moves are not reliable**: a Caravel given a 2-turn destination with 0 moves left
  showed activity MISSION at end of turn, but next turn sat at the intermediate plot with mission -1 and
  full moves (twice, t256-257). The `queued: true` result from move_unit therefore means "accepted", not
  "will happen"; re-issue the move next turn. Such a unit reports IsReadyToMove()=false and was NOT in
  todo, so a caller relying on todo alone would leave it idle forever. Fixed in runtime v59: todo.units
  lists it with `stalled_mission: true` (activity MISSION, full moves, not a Worker mid-build).
- **HTTP server parity**: 15 MCP tools had no HTTP route (discussion/respond_discussion, incoming/accept/
  refuse_deal, trade_catalog, trade_routes, city_state_gifts/minor_gold_gift, relationship,
  available_policies, available_city_strikes, choose_promotion, free_great_person_options/
  choose_free_great_person, turn_status). Added; `python -c "import harness.http_server"` -> 72 routes.
- **`available_production` carries `gold` (rush-buy price) and `can_buy`** per unit/building (runtime v60),
  built from the same matched getter/IsCanPurchase pairs purchase_cost uses; -1 ("never") is omitted.
  `move_spy` returns the spy's after-state entry. Both are the "no second call to confirm" principle.
- Map knowledge (t261): the eastern continent has India (Delhi region south-east, Pataliputra at (47,12)),
  city-states Zanzibar (38,18), Florence (48,17), plus Genoa and Monaco met via the Caravel, and an
  UNCLAIMED strip of grass/plains at (41-45, 9-13) north of India -- a possible overseas fifth city once
  embarkation (Optics: yes) and a Settler are available. Caravel is looping around an inlet to reach it.
- **Luxury market at t262** (after the t231-261 deals expired): "what_will_ai_give" for a spare luxury
  returns strategic resources (America: 5 Horses for Dye; Venice: 5 Iron for Copper) and a luxury-for-luxury
  ask is still 2-3 of mine for 1 of theirs. But `equalize` with a GPT draft ([luxury from us, 4-5 GPT from
  them]) comes back "5 GPT + their Open Borders" from both, and propose_deal of exactly that was accepted by
  both in one call each (effects: gold_per_turn 6 -> 11 -> 16). Recipe: negotiate_deal(equalize, luxury +
  ~5 GPT) then propose_deal(the returned items). A renewal prompt from an AI (Venice, "shall we renew?")
  arrives as discussion(screen=trade, buttons=[]) with the terms in incoming_deal -- read it before
  accepting: Venice's was my Copper for a 0-amount Spices line, i.e. for nothing.
- **Standing move orders now resume by themselves** (runtime v61). `H.pending_moves[unit_id] = {x, y}`
  is recorded by move_unit (carried across runtime version bumps like events/popups -- it is the
  caller's real state), `H.resume_moves(pid)` re-pushes MOVE_TO for any unit still short of its
  destination that sits idle at full moves (the stalled shape; Workers mid-build excluded), drops orders
  whose unit is gone or has arrived, and wait_for_my_turn calls it once the turn is ours (result gains
  `resumed_moves`). Any unit_mission on the unit cancels its standing order. First live test: the
  Missionary bought t265 (0 moves) was given move_unit -> Ur and reported `queued: true`; t266 should show
  it resumed. If that works, the caravel's per-turn re-issue chore is gone.
- `purchase_production` for a unit now returns `unit` {id, x, y, type} (polled from the unit list diff) --
  the bought Missionary had no id in the old result and needed a units() read to find.
- Faith purchase live (t265): UNIT_MISSIONARY 400 faith via purchase_production(yield_type=FAITH);
  purchase_cost read `can_purchase` true for Missionary/Inquisitor, false for Prophet (500 > 405).
- **Auto-resume verified live t266**: wait_for_my_turn reported `resumed_moves` for the Caravel (which
  then moved on by itself) and the Missionary. The Missionary's did NOT move: its destination was Ur's
  own city plot, which a foreign civilian cannot enter, and CanStartMission(MOVE_TO) says yes anyway.
  resume_moves (v62) now drops an order that made no progress for a full turn with an explanatory err;
  the unit shows in todo.units as a plain idle unit meanwhile. Spread religion from an ADJACENT plot.

## Twelfth session (2026-09-17, ~12:40 onward): t267 onward, runtime v62 -> v63

- **MISSION_SPREAD_RELIGION now reports measured `effects`** (runtime v63). The engine accepts the
  mission unconditionally, so a Missionary standing anywhere returned `{ok:true, moves:0}` with no
  way to tell whether Ur actually gained followers. `H.religion_target` snapshots the city on the
  unit's plot or an adjacent one (followers of the unit's religion, majority, population, city-state
  influence, spreads_left) before and after; `H.city_religion_at` re-reads by plot when the last
  charge consumed the unit (the unit_id is gone, so a unit-keyed after-read fails). Refuses up front
  when no city is on/adjacent. Live t267: Ur followers 3 -> 4, spreads 2 -> 1; t268 second charge
  consumed. Religion names come back localized (Game.GetReligionName returns a TXT_KEY).
- Antwerp influence decays ~1/turn from a 250g mercantile gift (50 at t263 -> 31 at t267, "Losing
  Grasp" notification at 31); the gift is worth +30 so the friendship needs topping up every ~20
  turns. `city_state_gifts(player_id)` wants the minor's *player id* (Antwerp = 27 in this game --
  read it from `diplomacy`), not -1.
- Fifth-city site confirmed from the caravel at (46,10): unclaimed grass/plains at (42-44, 8-12)
  with Sheep (44,7) and Porcelain (45,7) in tundra just north; India (player 5) already owns
  (44,11)/(47,11-12) so the window is closing. Plan: Shanghai (coastal, Bank done t270) -> Settler,
  embark across.

## Thirteenth session (2026-09-17, ~14:00 onward): t269-272, runtime v63 -> v65

- **`explore_frontier(unit_id, limit)`** (runtime v64/v65, MCP tool + `/explore_frontier`): `map_window`
  and `known_world` omit unrevealed plots entirely, and `move_unit` refuses an unrevealed target, so an
  explorer had no way to ask "where does the known map end?" short of guessing coordinates until
  `nearest_revealed` corrected it (live t269: Caravel -> (51,5) refused). The tool lists revealed,
  passable plots of the unit's domain (water for a ship, land otherwise, both when embarked) that
  border at least one unrevealed plot, nearest first, with `unrevealed_neighbors`, terrain `t` and
  `map_edge=true` on the two polar rows (mostly ice beyond). The only thing read about a fogged plot is
  `IsRevealed`, enforced by a test with an erroring metatable. Live: 66x42 map, 2034 of 2772 plots still
  unrevealed at t270, 103 frontier plots for the Caravel.
- Caveat learned the same turn: `distance` is hex distance, not path length. (52,6) was distance 2 from
  the Caravel at (50,5) but the engine routed it (50,5) -> (49,2) -> (46,5) -- a long detour around
  land -- and `resume_moves` keeps re-issuing it each turn. Unit:GeneratePath is NYI in this build, so
  path length cannot be reported; treat a far-off `distance` as a lower bound and prefer plots on the
  unit's own side of any land.
- `mcp_call.py`: a tool error now exits 1 cleanly; before, `raise SystemExit` inside the anyio task
  group printed a 40-line ExceptionGroup traceback for something as small as an unknown tool name
  (`nearby_builds` is a field of `available_unit_actions`, not a tool).
- Turn log: t270 America (Washington) asked for a coop war on India via DISCUSS_COOP_WAR mid-AI-turn;
  declined (button 1, "That is disappointing."), `et.sh --wait-only` resumed. t271 Electricity done ->
  Navigation (4t); Nanjing Settler (3t, for the eastern strip at (42-45, 8-12)); Shanghai Public School
  (18t); a mine started on the last unimproved hill (26,21). Antwerp + Zanzibar elections rigged t270,
  Antwerp back to Friends. Happiness 11, gold 333 at +37.

## Fourteenth session (2026-09-17, ~16:40 onward): t273 onward, runtime v66 -> v67

- **Lesson + fix: selling the last copy of a luxury costs happiness, and nothing warned.** t273: the
  Dye->America GPT deal had expired ("GPT from Washington ended"), `trade_catalog(2)` said we could export
  GEMS, and `propose_deal` (Gems -> 5 GPT) was accepted -- `effects.happiness` then showed 10 -> 6. Gems
  was our only copy. The catalog only answered "is it legal", not "what does it cost". Runtime v67:
  every `trade_catalog` resource row now carries `class` (ResourceClassType), `us_available` /
  `them_available` (Player:GetNumResourceAvailable(id, true) -- the numbers the trade screen shows a
  human) and `last_copy=true` + `note` when a luxury export would be our only copy. Test
  `test_trade_catalog_flags_last_luxury_copy`. The 30-turn Gems deal stands until ~t303.
- t273: Nanjing finished its Settler -> Opera House (6t). Settler 638976 given a standing order to
  (43,12) -- coastal plains hill on the eastern strip with Wheat (42,12), Fish (42,14)/(45,12), Horse
  (44,11), Aluminum (44,10), Silver (44,9) in range; Monaco (city-state, (40,8)) owns the plots west of
  it, not India as the t272 handoff guessed (`map_window` only shows `owner` on currently visible plots).
  First leg went (24,28) -> (25,22) on roads in one turn. Turn 273's end hit ENDTURN_BLOCKING_LEAGUE_
  CALL_FOR_VOTES (Third Congress of Venice: Sciences Funding proposed by us, Arts Funding by Venice);
  2 votes cast for Sciences Funding, et.sh had exited on the block and was re-run.
- **`overview.strategic_resources`** (runtime v68/v69): `{IRON={available=-2,total=2}, HORSE=..., COAL=...}` for
  every strategic resource whose `TechReveal` tech the team knows (the top bar's rule; probed live:
  `Team:IsResourceRevealed` is nil in this build). Negative `available` is a deficit -- the Iron -2 at
  t275 was only noticed through `trade_catalog`'s new `us_available`. RESOURCE_HIDDEN_ARTIFACTS is a
  RESOURCECLASS_RUSH archaeology marker and is skipped. Test `test_strategic_resources_only_revealed_rush_and_modern`.
- t275: Metallurgy chosen (4t; Radio 17t, Archaeology, Fertilizer were the others). Washington declared war
  on Gandhi (t275). t276: Beijing Public School done -> Opera House (7t); Worker 49155 sent after the
  Settler with a standing order to (43,12) (the engine routed both north-east, Settler (26,17) -> the
  Shanghai coast); Worker 204809 slept (no builds anywhere). Caravel reached (37,17).
- **`disband_unit(unit_id)`** (runtime v70/v71, MCP tool + `/disband_unit`): there was no way to delete a
  unit. Needed at t277: four Swordsmen held 4 Iron against 2 owned (`available=-2`), and `upgrade_unit`
  refused (target Longswordsman also needs Iron; CanUpgradeRightNow fails in a deficit). COMMAND_DELETE
  via `Unit:DoCommand` works but the unit is removed on the next game tick, not inside DoCommand -- the
  first live call reported "still exists" while the second call already saw the unit count drop. The
  wrapper now polls `H.disband_unit_check` (<= 3 s) and reports `effects.before/after` (unit count +
  strategic_resources). Disbanded the two level-1 Swordsmen (409615, 360449): Iron -2 -> 0.
- t277: Caravel to (35,21) via `explore_frontier` (heading south around the landmass). Happiness 5.
- **`explore_frontier.reachable`** (runtime v72): a BFS from the unit over revealed, traversable plots of
  its domain (water for a ship; land, or both when embarked, for a land unit) marks each frontier plot
  `reachable=true/false`; unreachable ones sort last. This is the "path length" substitute the
  thirteenth-session caveat asked for (Unit:GeneratePath NYI): a plot on the far side of a landmass or
  behind an unknown strait is now flagged instead of outranking real coastline by hex distance. Live t278:
  all 10 nearest Caravel frontier plots reachable (open ocean south of (35,21)). Tests: fog-safety test
  extended, plus `test_explore_frontier_marks_plots_behind_land_unreachable` (embarked unit crosses land).
- t278: Guangzhou Machu Picchu done -> Public School (19t); gold +58/turn now (Machu Picchu + two fewer
  units). Caravel -> (37,24), MISSION_SKIP on its last move before et.sh (a unit with moves left blocks
  end_turn). Metallurgy 1t.
- t279: Metallurgy done -> Fertilizer (6t; Archaeology/Rifling/Military Science/Radio 15t were the
  others; Fertilizer + Archaeology -> Biology -> Refrigeration -> Plastics for Research Labs). Great
  Scientist born in Guangzhou -> walking to (29,21) (the only unimproved owned tile nearby, banana
  jungle hill) for an Academy next turn. Two caravans returned (old ones expired as `unit_destroyed`):
  only city-state destinations are in land range (Antwerp 7.1 gpt, Ur 9.2 gpt, science 0) -- major
  civs need Cargo Ships; re-established both, 5/5 routes. Nanjing Opera House done -> Garden (3t).
  "India stole Industrialization!" = stolen from us. Caravel (38,27), still open ocean south.
- t279 AI phase: Venice (Dandolo) asked for a coop war on India via DISCUSS_COOP_WAR; declined (button 1,
  "That is a shame."), `et.sh --wait-only` resumed cleanly. t280: third returned caravan Nanjing -> Ur
  (6.69 gpt, 24t). Great Scientist arrived at (29,21) with 0 moves (standing order consumed the turn);
  Academy at t281. Settler (37,16) + Worker (37,17) embarked, ~6 plots from (43,12). Caravel (40,30).
- t281: Academy built at (29,21) by the Great Scientist (`unit_mission MISSION_BUILD BUILD_ACADEMY`,
  completed=true, unit consumed). Met Quebec City (Caravel, t280). Returned Beijing caravan re-sent as a
  production route to Shanghai (5 prod/turn, 28t) -- Beijing already holds the Antwerp and Ur slots, and
  `available_trade_routes` lists no other international target within land range. 5/5 routes:
  Beijing->Antwerp (2t left), Nanjing->Antwerp, Beijing->Ur, Nanjing->Ur, Beijing->Shanghai. Caravel (38,33).
- t281 AI phase: Poland (Casimir) offered a Declaration of Friendship; accepted (button 1, "Excellent.").
  Washington made peace with Gandhi. t282: Settler disembarked at (41,13) (0 moves, can_found=true) --
  the standing order handled embark, 5 sea turns and the landing without a single refusal; Worker at
  (42,14) still embarked. Nanjing Garden done -> Temple (3t). Beijing caravan back -> Antwerp again
  (9.71 gpt, 28t). Caravel to (40,36) COAST (first coast plot seen in the south).
- t283: Settler on (43,12) with a standing order just spent: `MISSION_FOUND` was accepted by PushMission
  but no city appeared (activity HOLD). New `H.found_check` pre/post check around MISSION_FOUND
  (runtime v73/v74): refuses with 0 moves, confirms the city after the push, reports `city` + `consumed`.
- t284: the pre-check itself refused every founding: `Unit:CanFound(plot, false)` raises "number expected,
  got boolean" (arg 2 is a number in this build), the pcall swallowed it and `can_found` read false while
  `units` (which calls `CanFound(plot)`) said true. Fixed (v74) -> **Xian founded at (43,12)** (city id
  40964). Pataliputra (India) owns (44,11)/(45,12) next door but the engine allows the site (distance to
  Monaco 5, MIN_CITY_RANGE 3). A barbarian camp sits at (43,11) adjacent to Xian with a Musketman (83 hp)
  and a captured Settler + Worker: Worker 49155 moved into the city, Musketman bought in Xian (540 g,
  0 moves this turn), Monument queued, city strike 29 dmg on the barb Musketman. Caravel -> (46,36).
- t285: Fertilizer done -> Archaeology (7t). Nanjing Temple done -> Stock Exchange (10t). Xian struck the barb
  Musketman again (27), Musketman 737280 attacked into (42,11) via `move_unit` onto the enemy plot (no
  confirmation for barbarians), killed it and captured the Settler -> **BUTTONPOPUP_RETURN_CIVILIAN**
  ("return it to America, or take it as a Worker"). Nothing in the harness could answer it; done by hand
  with `Network.SendReturnCivilian(true, 2, <unit id>); HideWindow()` in state GenericPopup, then
  Washington's thank-you needed `dismiss_discussion`. New tools **`generic_popup` / `answer_popup`**
  (runtime v75, `harness/lua/generic_popup_shim.lua` in the GenericPopup state wraps AddButton so the
  button closures can be replayed; installed by `ensure_runtime`, must be in place before the popup
  opens). `pending_popups` rows now carry `data3`. Worker 49155 farming Wheat (42,12).
- t285 AI phase: Zanzibar became our ally (rigged election), happiness 5 -> 13. Met Sidon. Public
  declarations from America/Poland/India (notifications only, no text captured).
- t286: Musketman captured the barb-held Worker at (43,11) -> RETURN_CIVILIAN again (Genoa's, +45
  influence for returning); `answer_popup(1)` pressed "Return the Unit" live, popup closed, no leader
  screen for a city-state. Caravel (51,35), east coast finally in reach.
- t286 AI phase: Poland proposed a Research Agreement (DiploTrade offer); `accept_deal` closed it (gold
  551 -> 308, `relationship(4).research_agreement=true`) but crashed afterwards in `_diff_snapshot`:
  an empty Lua `resources` table decodes as `[]`. Fixed. "Your City Converted" t287 (no city shows a
  religion in `cities` -- the field is not exposed; not chased).
- t287: Caravel refused (53,32): the plot is Sidon's coast and the engine finds no path into a
  city-state's / closed-border territory, while `explore_frontier` said reachable. Runtime v76: the
  flood fill stops at plots whose revealed owner gives no open borders (war excepted), and such
  frontier plots carry `closed_border=<owner>`. Sent to (54,35) instead.
- t288: barbarian Musketman at (24,30) next to Nanjing: city strike 34 + Chu-Ko-Nu 368644 two range
  attacks (27, 21; `MISSION_RANGE_ATTACK` twice works for the UU) -> 18 hp. Shanghai Public School done
  -> Opera House (12t). Caravel (55,34) heading to (56,32). Archaeology 2t.
- t289: Nanjing's strike killed the barbarian Musketman. Worker 49155 -> Farm on (43,11). Caravel (57,30).
  `cities.religion` added (runtime v77): Beijing Taoism, Xian Catholicism (the t287 "Your City
  Converted" was Xian, converted from India's side).
- t290: Archaeology done -> Biology (11t). Two Antiquity Sites discovered near Nanjing (CHOOSE_ARCHAEOLOGY
  still untested -- needs an Archaeologist). Great Writer born in Beijing: `MISSION_CREATE_GREAT_WORK`
  consumed it (culture 47 -> 53/turn) and left BUTTONPOPUP_GREAT_WORK_COMPLETED_ACTIVE_PLAYER pending,
  which the sweep (GreatWorkPopup.OnClose) clears. Xian pop 2. Caravel (58,27), 1731 plots unrevealed.
- t291-292: quiet turns; Caravel up the east coast (61,22). Washington declared war on Florence. A
  barbarian Gatling Gun appeared at (24,31) south of Nanjing. `available_production` now lists faith
  purchases (runtime v78/v79): Beijing shows Prophet 500 / Missionary 400 / Inquisitor 400 with
  `faith_can_buy=false` at 267 faith (`IsCanPurchase(false, true, ...)` skips the cost test so rows
  show while saving up; `IsCanPurchase(true, ...)` is the affordable-now flag).
- t292 AI phase: Venice asked to renew Copper -> 5 GPT + Open Borders (30t); `accept_deal` ok, deals 6 -> 7.
- t292 AI phase, three renewals in a row, each interrupting `wait_for_my_turn` (accept, then
  `et.sh --wait-only`): Venice Copper -> 5 GPT+OB, America Dye -> 5 GPT+OB, Sweden Copper -> 4 GPT+OB.
  `trade_catalog` does not list a resource that is under the expiring deal, so `incoming_deal`
  resource rows we would give now carry `us_owned / us_available / us_imported / us_exported`,
  `class` and `last_copy` (runtime v80/v81). Gotcha: `Player:GetNumResourceTotal(id, true)` is net of
  exports (Copper: total 1, exported 2, available 1 = 3 owned), so `us_owned` adds the exports back;
  a renewal of an existing export is never flagged as our last copy.
- t293-294: barbarian Gatling Gun at (23,29) pillaged a Nanjing pasture; city strike + two Chu-Ko-Nu
  shots per turn (26/19/16, then 29/15/14) left it at 6 hp -- it heals ~25/turn in the open, so
  three ranged hits a turn is only just enough; a melee finisher near Nanjing would help. Xian
  Monument done -> Granary (14t); Worker 49155 farm (43,11) done -> farm (42,11). Caravel (63,18),
  1665 unrevealed. Someone adopted an Ideology (t293 notification); Genoa/Ur/Sidon culture quests.
- t294 AI phase: Sweden asked us to join a war on Poland (DISCUSS_COOP_WAR, 4 buttons) -> button 1
  "no interest" (`still_pending=true` because Poland's open-borders offer was queued right behind it:
  `accept_deal`, deals 6 -> 7). The `et.sh --wait-only` job was then killed by the session runner for
  "low memory" although the box had 50 GB free; the game was fine, resumed with turn_status/quick_save.
- t295: Nanjing's strike killed the Gatling Gun (6 hp). Policy: Humanism (Rationalism; next 1695).
  Guangzhou Public School done -> Opera House (11t); Nanjing Stock Exchange done -> Museum (8t).
  Chu-Ko-Nu 368644 Accuracy I. Caravel (63,15). Fourth Congress of Venice in 5 turns.
- t295 AI phase: America then Sweden offered Declarations of Friendship (accepted both), India asked us
  to join a war on Venice (declined). Three leaders queued behind one another: `respond_discussion`
  now returns `next` (the following leader's screen/speech/buttons, plus the deal items when it is a
  trade) so each answer needs no extra `discussion` read. America captured Florence.
- t296: quiet; Caravel (62,12), 1631 unrevealed. Gold 793 +58, faith 315 (Missionary 400 still not affordable).
- t296 AI phase: America proposed a Research Agreement (accepted, gold 793 -> 493). "Losing Grasp on
  Zanzibar!" -> t297 `minor_gold_gift` 250 (influence 60 -> 75, still ally). `city_state_gifts.rivals`
  added (runtime v82): met majors' influence with the minor, highest first.
- t297 AI phase: Venice asked us to war America (declined; `respond_discussion.next` showed Sweden's
  RA offer queued behind it -- accepted, gold 302 -> 2). Three RAs running (Poland t286, America
  t296, Sweden t297). The session runner killed the `--wait-only` job again for "low memory" (50 GB
  free); harmless, the game keeps running -- check turn_status and resume.
- t298: Biology done -> Refrigeration (12t; Rifling 4t was the safe alternative). Zanzibar rivals live:
  India 47, Sweden 43 vs our 75. Caravel (58,9) rounding the north-east.
- t299: Xian's five owned land plots are all improved (an ARTIFACTS site sits at (41,12) for a future
  Archaeologist); Worker 49155 slept inside Xian. Caravel (57,6). 1584 plots unrevealed. The session
  runner keeps killing the background `et.sh` job for "low memory" right after the turn arrives, so
  `logs/et_last.log` may end at wait_for_my_turn; `turn_status` + `turn_digest` fill the gap.
- t300: Shanghai Opera House done -> **Cargo Ship** (5t; the first one, to test sea routes to majors).
  Caravan 770063 returned to Nanjing (route expired) and slept: only internal food/production routes
  are in land range and the 5th slot is being kept for the Cargo Ship. Fourth Congress of Venice in
  session: Ban Dyes (Venice) and Ban Silver (Sweden) proposed; 3 votes cast No on the Dyes ban
  (`choice=0`; leagueoverview.lua kChoiceNo=0 / kChoiceYes=1, -1 = none -- documented on the tool).
  Worker 49155 MISSION_SLEEP inside Xian (a MISSION_SLEEP issued with 0 moves left only produced HOLD
  and the unit was back in todo next turn; re-issued with moves -> SLEEP_OR_FORTIFY). Caravel (55,3).
- t301: Congress result: Ban Dyes failed, Ban Silver passed. Venice built the Louvre. Antwerp and Zanzibar
  elections rigged again by our spies. Xian pop 3. Caravel (55,7) turning back west along the north
  coast; the whole east side of the map is now known (1545 plots left, mostly polar/west ocean).
- t302: Venice (leader_message) resents our No vote on its Dyes ban. Genoa wants a trade route (a
  Cargo Ship target once Shanghai finishes it, ~3t). Happiness 9 and falling with growth: next
  happiness lever is a luxury import (America has Spices/Salt spare) or a Colosseum in Xian.
- t303: Beijing **Porcelain Tower** done -> free Great Scientist 786444, slept in Beijing for a later
  bulb (Academy now ~8/turn vs a bulb worth ~8 turns of 320+ science later). Beijing -> Garden (4t).
  "Biology stolen!" (from us). Caravan 778257 returned -> Nanjing->Antwerp (8.05 gpt, 4/5 routes; the
  5th slot waits for Shanghai's Cargo Ship, 2t). `establish_trade_route` now accepts `city_name`
  (+ `kind`) instead of copying dest_x/dest_y/trade_type out of available_trade_routes.
- t304: the 30-turn Gems -> America deal (t273) expired, giving back our own Gems while Sweden's import
  (t283-313) still runs: `trade_catalog` showed Gems us_available 2, so `propose_deal` Gems <-> Spices
  1-for-1 with America was accepted at once (happiness 9 -> 13, measured in `effects`). Watch t313:
  when Sweden's Gems end we drop to one copy, exported -- renew Sweden's deal or the Spices swap costs
  4 happiness. Nanjing Museum done -> Artists' Guild (5t). Caravel (53,14) heading down the east coast
  gap; 1516 plots unrevealed.
- t304 AI phase: Venice declared war on America, Sweden on Poland (friends of ours on both sides; we
  stay out). The `et.sh` job was killed mid `end_turn` by the runner; turn_status still showed t304
  my_turn=true, so it was simply re-run (end_turn is idempotent enough: nothing had been sent).
- t305: **Golden Age** (Great Artist-free, from happiness). Shanghai's first **Cargo Ship**:
  `available_trade_routes` lists sea targets at last (Venice 27.4 gpt +1 sci, Stockholm 25.2,
  M'banza-Kongo 19.7, six city-states ~11-13, Xian food/production 10); `establish_trade_route
  city_name="Venice"` -> Shanghai->Venice, 44 turns, gold/turn 41 -> 67. Shanghai -> Seaport (13t),
  Guangzhou Opera House done -> Windmill (12t), Xian Granary done -> Lighthouse (12t). Guangzhou WLTKD.
- t306: Caravan 819207 returned (Beijing->Ur expired) -> re-sent Beijing->Ur by `city_name` (10.38
  gpt; 5/5 routes, gold/turn 85). Monaco allied with someone and declared war on Poland. Caravel given
  a standing order to (54,29) (south-east coast gap); the engine's first leg went north-east to
  (54,13) -- the pathfinder detours around Sidon/India waters, so multi-turn legs look odd.
- t306 AI phase: Poland (at war with Sweden and Monaco) asked for a 15 GPT gift on the trade screen
  (DEMAND-style "show generosity"): `refuse_deal` -> "That is a shame." follow-up discussion with
  two buttons -> button 1 ("sorry this caused a divide"). Sidon declared war on Venice and Monaco.
  Gold/turn 95 with the sea route + Ur.
- t307: the Caravel had NOT continued to (54,29): the reflex `MISSION_SKIP` after `move_unit` cancels
  the engine's multi-turn path (and cleared H.pending_moves). Runtime v83: MISSION_SKIP is refused for
  a unit with a mission queue / ACTIVITY_MISSION / a standing order ("does not block end_turn").
  Re-issued the move; the engine's leg went to (57,10) (it is routing round the north). Beijing Garden
  done -> National Epic (9t). Xian pop 4. Refrigeration 3t.
- t308: Sweden entered the Modern Era. Nanjing Artists' Guild done -> Hospital (9t). Caravan 835585
  returned (Beijing->Shanghai production expired) -> re-sent, `city_name="Shanghai", kind="production"`.
  5/5 routes: Antwerp x2, Ur, Venice (sea), Shanghai. Caravel (60,12) still on its engine path.
- t309: Caravan 851981 returned (Beijing->Antwerp expired) -> re-sent (10.98 gpt). Someone's trade
  route was plundered (notification only). Another civ adopted an Ideology. Refrigeration 1t.
  Caravel (63,14) still routing; 5/5 trade routes.
- t309 AI phase: India asked us to war America again (declined). t310: Refrigeration done -> Rifling
  (3t; only Rifling / Military Science / Radio were offered -- Plastics needs Electricity first, and
  the Research Lab's PrereqTech is `TECH_PLASTIC`, singular: `GameInfoTypes.TECH_PLASTICS` is nil and
  `Team:IsHasTech(nil)` returns true, a probe trap). Beijing offers Stadium/Hotel now (Refrigeration).
  Third spy Yang recruited -> Stockholm (Sweden, Modern era) to steal tech. Caravel (63,18) still routing.
- t310 AI phase: India declared war on America. t311: barbarian Caravel next to Shanghai killed by the
  city strike. **ENDTURN_BLOCKING_CHOOSE_IDEOLOGY** (first time): new `choose_ideology(branch)` tool
  (runtime v84) = chooseideologypopup.lua's Confirm (`Network.SendIdeologyChoice(pid, branchId)`),
  polled via `Player:GetLateGamePolicyTree()`, popup closed with its OnClose, H.popups record dropped.
  Ideologies are public: Sweden Autocracy, India Order (others none) -> chose **Order**; the block
  then became ENDTURN_BLOCKING_FREE_POLICY (1 free tenet, `available_policies.free_policies` still
  said 0) -> `choose_policy(POLICY_SOCIALIST_REALISM)`: +2 happiness per Monument, happiness 10 -> 20.
  PolicyBranchTypes has no LateGame column here; `PurchaseByLevel=true` marks the three ideologies.
- t311 AI phase: India (Order, borders Xian, at war with America) offered a Declaration of Friendship;
  accepted -- expect an America "friends with our enemy" grumble. Friends now: Poland, America, Sweden, India.
- t312: nothing pending; bought Xian's Paper Maker (400) and a Work Boat (240) for the Fish at (42,14)
  (gold 1061 -> 421; the Work Boat needs a move_unit + MISSION_BUILD next turn). Caravel (60,26).
- t312 AI phase: India offered mutual Open Borders (accepted, deals 9 -> 10).
- t313: Rifling done -> Steam Power (6t; Military Science / Radio were the others -- Electricity still
  not offered). Work Boat moved to (42,14) and `MISSION_BUILD BUILD_FISHING_BOATS` completed in the
  same turn (`completed=true`, unit consumed). Sweden's Gems import still active (imp 1). Happiness 18.

## Sixteenth session (2026-09-17, ~22:00): raw `lua` gated; `propose_deal` residual crash vectors closed (runtime v85)

User asked whether an LLM unfamiliar with the server could crash the game. Audit answer, with fixes:

- **Raw `lua` tool is now opt-in.** It was already undecorated (not in the tool list) but had no positive
  switch; now `register_lua_if_allowed()` adds it only when `CIV5_ALLOW_LUA=1` (env) or `--allow-lua`
  (mcp_server main) is set, and the function body refuses too (second fence). Mirrors the HTTP server's
  per-seat `allow_lua`. Live: without the flag `Unknown tool: lua`; with it, 72 tools and `lua` works.
  `RawLuaGateTests` in tests/test_mcp_safety.py.
- **`propose_deal`/`negotiate_deal` crash class: root-caused in the tenth session (trade session must be
  open), and empirically crash-free since** -- kernel log shows no Civ5XP segfault since Sep 16 20:06 (the
  known c90232/c90534 rendering/affinity signatures); the current instance has run since 00:17 through ~80
  turns of deal traffic. Re-reading tradelogic.lua for what the harness could still hand the engine that a
  human never could found two gaps, both fixed:
  1. **CITIES** items skipped `_check_deal_items` entirely and went straight to `OnChooseCity(who, id)`,
     whose body is an unconditional `g_Deal:AddCityTrade(playerID, cityID)`; the real UI only lists cities
     that pass `IsPossibleToTradeItem(from, to, TRADE_ITEM_CITIES, x, y)`. An arbitrary/nonexistent
     `city_id` (the default was -1!) reached `AddCityTrade` -- the exact "mutating Add* on an invalid item"
     shape that crashed natively eight times before the session fix. Now: `H.trade_catalog` returns
     `cities.us` / `cities.them` (id, name, x, y) through that same gate (capitals are never listed, live:
     Beijing and Stockholm absent), `_check_deal_items` refuses any id not in the list (with the list), and
     `_add_deal_items` re-checks `GetCityByID` + `IsPossibleToTradeItem` on the live table before
     `OnChooseCity`.
  2. **Amounts** went to `ChangeGoldTrade` / `ChangeGoldPerTurnTrade` / `ChangeResourceTrade` unclamped;
     the trade screen clamps a typed number to `deal:GetGoldAvailable`, `CalculateGoldRate`,
     `deal:GetNumResource` first (tradelogic.lua `ChangeGoldAmount` & co.). Now `trade_catalog` reports
     `gold.us_available/them_available` and `gold_per_turn.us_available/them_available`,
     `_check_deal_items` refuses non-positive / non-integer amounts and anything above the side's limit
     (`available` in the reply), and `_add_deal_items` applies the UI's `math.min(...)` clamp inline before
     the engine call (read-back still refuses a clamped amount rather than proposing it).
  Also: a non-object item is refused with the expected shape (the MCP layer's own pydantic validation
  catches it first with "Input should be a valid dictionary"), PEACE_TREATY / DECLARATION_OF_FRIENDSHIP stay
  unsupported (clean "unsupported item type" listing the supported ones).
- Live (t314, Sweden = player 3, quick_save first): city 999999 and 8193 -> refused with the four tradeable
  cities; GOLD 999999 -> "exceeds ... (616)"; GOLD -5 -> "must be a positive whole number"; GPT 500 from
  them -> "exceeds ... (53)"; MARBLE x7 -> "exceeds the 1 copies"; all refused before any screen opened
  (~4s each = catalog read only). Happy path through the new clamp Lua: negotiate_deal what_will_ai_give
  with 10 GOLD landed 10 on the table, AI replied, screens closed cleanly; what_does_ai_want with 5 GPT from Sweden -> they asked 165 GOLD; what_will_ai_give for our (last-copy) Marble -> 7 GPT offered. Game alive, turn 314 clean afterwards.
  `DealItemLegalityTests` + `test_trade_catalog_lists_tradeable_cities_and_availability_without_adding`.
- **Does a refused LLM learn why?** Yes by design: every refusal is `{ok:false, err:<reason>}` and the
  MCP `instructions` string says so up front; the informative ones carry a next step (`blocking_hint`,
  `hint` for popups, `tradeable_cities` / `tradeable_resources` / `available`, "use map_window",
  "see league_status(...)"). The only messages not written by the harness are argument-schema errors from
  the MCP library (wrong JSON types), which still name the offending field and expected type.

## 2026-09-17 (seventeenth session) — LAN client desync: unit orders must use the game's network path (runtime v86)

- **What happened.** First launch of the 2-LLM LAN game (Claude host = Huns, Grok on the Deck = Carthage,
  hybrid turns). Grok founded his capital and moved his warrior through the harness; at the turn-0 rollover
  the host's `net_message_debug.log` logged `Received a sync request for City (8192) which does not exist
  locally!`, `Unit out of sync. Player=1 ... Warrior`, `Variable Out Of Sync: CvPlayer::m_iCapitalCityID /
  m_bFoundedFirstCity / ...`, then `NetForceResync` (879 KB, host state pushed to the client). Player 1 was
  never set turn-active on turn 1 and `Players[1]:IsAlive()` was false: the game treated Carthage as
  defeated. Grok's client showed the defeat screen. The only messages the host ever received from player 1
  were TurnSlice / PlayerOption / PlayerReady / TurnAllComplete — no unit order at all.
- **Root cause.** `Unit:PushMission` / `Unit:DoCommand` (and the pre-v86 `push_mission` helper) mutate only
  the local gamecore. Single human seat: fine. LAN host: the host's copy wins every resync, so it looked
  fine too. LAN client: the order exists only on the client, the host resyncs it away, and a settler-less
  civ with no city is dead. Same class of failure as the first Deck attempt (2026-09-17 morning).
- **Fix (v86).** Every unit order now goes the way the game's own UI does: `UI.SelectUnit(u)` then
  `Game.SelectionListGameNetMessage(GAMEMESSAGE_PUSH_MISSION | GAMEMESSAGE_DO_COMMAND, type, d1, d2, 0,
  false, false)` (`net_unit_message` in runtime.lua; used by move_unit, unit_mission incl. MISSION_FOUND /
  MISSION_BUILD, establish_trade_route, choose_promotion, upgrade_unit, disband_unit). `Civ5XP` has no
  `Network.SendPushMission` / `SendDoCommand` (checked the binary's strings: the Network.Send* set is
  DoTask, Research, UpdatePolicies, FoundPantheon/Religion, EnhanceReligion, GreatPersonChoice,
  IdeologyChoice, League*, MoveSpy, StageCoup, ReturnCivilian, GiftUnit, ChangeWar, DiploVote, MinorCiv*,
  CityBuyPlot, SellBuilding, SetCityAIFocus, UpdateCityCitizens, RenameCity/Unit, ...). City production
  (`Game.CityPushOrder`), purchases (`Game.CityPurchase*`), research, policies, city tasks, spies and the
  league already used network calls, which is why Grok's research choice survived while his city did not.
- **Consequences handled.** Selection can land a frame late (the pre-v40 same-call SelectUnit+send no-op):
  Lua answers `select_pending` when `UI.GetHeadSelectedUnit()` is not the unit yet and `Game._order`
  re-issues the identical call (<= 6 x 0.2 s). The order is applied on a later game update even locally,
  so nothing is read back inline any more: `build_check` (MISSION_BUILD started/completed),
  `promotion_check`, `upgrade_unit_check`, plus the existing found_check / unit_pos / disband_unit_check /
  trade_routes polls. `UI.SelectUnit` flips the local 2D/3D view (the reason v40 moved away from it);
  accepted — the LLM seat's screen is nobody's, and correctness across peers matters more.
- **Not yet verified live**: the v86 path has only run under the Lua mock tests (56 pass). First live
  checks next launch: does `SelectionListGameNetMessage` work from the tuner's InGame context, does
  selection land same-call or need the retry, and does the host log stop showing `Out Of Sync` after the
  Deck seat's first turn. Deck tree rsynced to v86 (`harness.game.RUNTIME_VERSION` = 86 there).
- Turn-type note: the user set "hybrid" for the restaged lobby; `turn_status` still reports
  `simultaneous=false, dynamic_turns=false` at turn 0 — those flags come from the game options the harness
  can see and may not reflect hybrid. `players` showed both humans `turn_active` at turn 0.

## 2026-09-18 (nineteenth session) — event audit against the user's screen (hotseat, v89 -> v94), then v95 offline

The v89-v94 fixes are described in their commit messages (`git log 06f1ff1..a9afe3d`). v95 was written
after the hotseat game was killed, so **nothing in v95 is verified live**:

- **Audit gap #16 was not stale state.** `turn_status` kept showing `ENDTURN_BLOCKING_POLICY` and
  `leader_greeting_pending` after the policy was adopted and `dismiss_discussion` returned ok (t12). The
  user confirmed Temujin's screen really was still up: `dismiss_discussion` only knew DiscussionDialog, and
  the engine does not re-evaluate the end-turn blocker while a leader screen is open (it read -1 as soon
  as `end_turn`'s popup sweep closed the greeting). Now: `discussion()` reads the greeting
  (`screen: "greeting"`, same TitleText/MoodText/LeaderSpeech controls), `dismiss_discussion()` closes it,
  and `turn_status` adds `leader_screen_note` saying blocking_name/todo are frozen.
- **Notification locations.** `NotificationAdded` carries no plot for ruins/camps (data -1,-1) and Lua has
  no getter for the notification's x/y. `H.new_sites` reads it back from the map: visible plots whose
  revealed improvement is a goody hut / camp and that no earlier row reported (`sites: [{x,y}]`; memory in
  `H.known_sites`, carried across reloads; one retry at digest-read time if the plot was not revealed yet
  inside the hook). City growth gets the city's x,y (d1 = city id), promotion gets unit_id + x,y (d2).
- **`players` hid nothing**: it listed every human seat's civ. The game's own list (mplist.lua) shows a
  human's nickname always but the civ only once met; `H.net_players(pid)` now does the same (`met`, `civ`
  nil until met, name from GetNickName because GetName can fall back to the leader name).

Still open from the audit: peace, city capture, live checks of v91 (`war_state` single row, insta-heal),
v94 (wonder / city-state popup rows) and everything in v95.

## 2026-09-18 (twentieth session) — overnight solo China game from t314, runtime v95 -> v101

User asleep; playing the solo China save (`Wu Zetian_0314 AD-1888`) by hand, crash-watching (mem_watch.sh
running, kernel log checked after any exit, `turn_status.notifications` as a new correlate).

- **Load took > 5 min** from a cold boot (Lua.log's first InGame lines at 432 s after launch). `load_save`
  raised a bare TimeoutError at 300 s although the load was fine. Now 600 s default, and a timeout returns
  `{ok:false, loading:true, err:...}` with the next step.
- **v86 network path verified live in single player**: move_unit, unit_mission (DISCOVER, RANGE_ATTACK,
  FORTIFY, GOLDEN_AGE), city_ranged_attack all land through SelectionListGameNetMessage.
- **v96 great-person yields** in available_unit_actions (`yield`): GetDiscoverAmount (live 2499 / 2521),
  GetHurryProduction, GetTradeGold/Influence, GetGivePoliciesCulture, GetBlastTourism, GetGoldenAgeTurns
  (live 8), GetSpreadsLeft — the same getters unitpanel.lua's tooltips use.
- **Notifications don't accumulate** (user's question): the gamecore keeps a ~100-entry history ring and
  marks entries dismissed by itself after about a turn (t315: 99 held, 89 dismissed from t285-313, 10 live
  from t314-315). v97 puts `{held, live}` in turn_status for crash correlation. The panel's own
  g_ActiveNotifications is a file-local, not reachable from the tuner.
- **set_research far goals** (tech-tree click semantics): Network.SendResearch on a tech with missing
  prerequisites queues the path; the reply carries `goal` + `queue` (GetQueuePosition). Live: TECH_PLASTIC
  -> [RADIO, PLASTIC]; when Radio completed the engine moved on to Plastics by itself (TECH_AWARD popup
  still queued and swept). First draft false-failed because Radio was already current ("did not change").
- **v98 ranged_targets**: available_unit_actions never listed a ranged shot (one-arg CanStartMission needs
  a target). Now CanRangeStrikeAt over GameInfo.Units.Range, visible unit/city plots only. Live: Chu-Ko-Nu
  listed the barbarian at (25,30), hp 61.
- **v100 AUTOMATE_* bug**: `unit_mission(AUTOMATE_EXPLORE)` returned ok:true and did nothing —
  GameInfoTypes.AUTOMATE_EXPLORE = 1 was pushed as mission 1 = MISSION_ROUTE_TO(-1,-1). Automation is
  GAMEMESSAGE_DO_COMMAND(COMMAND_AUTOMATE, automate id) (what Game.HandleAction does for the unit panel
  button); polled via IsAutomated (Unit:GetAutomateType is nil in this build). unit_mission now refuses any
  name that is not in MissionTypes. Live: Caravel automated, stops blocking end_turn.
- **v101 alert locations**: "The enemy has been spotted near Nanjing!" carries no plot; alerts that name an
  own city now carry `city` + `hostiles` (visible, at-war/barbarian, within 3 plots). Smoke-tested live
  (no hostiles at the time) — positive case not yet seen.
- Game: bulbed two Great Scientists (Steam Power, Replaceable Parts), Great Artist -> Golden Age (t318),
  Radio done, Plastics queued. Sweden captured Warsaw t316 — building Great War Infantry for defense.
- **purchase_cost `reason`** (t319: 975 gold vs a 960 GWI, can_purchase false with no why — a Swordsman on
  the city tile). Now: not buyable here / not enough gold (have of cost) / same-kind unit on the tile
  (`blocking_units`) / refused this turn. Its first live call came back `ERR:Syntax Error` with the source
  cut mid-string: **the tuner truncates a command at ~2.5 KB** (known for load_lua, never enforced on
  queries). `Game.q` now ships any body over 2000 chars in string chunks under a per-call global and runs
  it through loadstring; test_query_chunking runs the shipped Lua in lupa.
- **Unknown tool names get hints**: the SDK said only `Unknown tool: summary`. Now `Did you mean: overview?`
  (aliases for summary/plots_around/turn_state + difflib + substring).
- **t320-327 harness pass (runtime v102-v104)**, all from live play:
  - turn_digest printed every notification twice (~5 KB) and all tool text carried [COLOR_*]/[ICON_*]/[NEWLINE]
    markup: `Game.turn_digest` (shared by MCP + HTTP) dedupes, `plain_text` strips markup in every MCP reply.
  - Unknown item/tech names carry `did_you_mean` (UNIT_GREAT_PROPHET -> UNIT_PROPHET, TECH_PLASTICS -> TECH_PLASTIC);
    rejected tool arguments append the tool's signature (x/y vs dest_x/dest_y on establish_trade_route).
  - AI renewal offers get `renewal: true` and per-item "keeps our supply unchanged" (us_exported already counts
    the running export) -- I refused a free Copper renewal from Venice at t322 misreading it as our last copy.
    The inline relationship in discussion() drops third-party relations (~3 KB per AI question).
  - v102 `overview.idle_trade_units`: GetNumInternationalTradeRoutesUsed counts trade UNITS; two caravans sat idle
    in Nanjing under "6 of 6 used". v103: a caravan leaving on a route is `trade_route_started` (was `unit_spent`),
    one vanishing with no combat is explained as a finished route.
  - move_unit: `arrived` / `destination` / still-on-its-way note; an attack order that ran out of moves on the
    way says `attack.happened: false` (was a hp-unchanged block that read like a fight).
  - v104: "enemy spotted near <city>" widens the hostile search to 6 plots when nothing is within 3 (the alert
    fires for units inside our borders; live t327 horseman at distance 4). Positive case of v101 seen at t325.
  - Deferred: faith Great-Person unlocks (which policy finisher enables which unit) are not in the XML/DB -- not
    explained by purchase_cost beyond "not sold for faith".
  - incoming_deal research agreements carry `gold_cost` = Game.GetResearchAgreementCost(us, them) (what tradelogic.lua
    shows). Live t327 it read 350 and exactly that was charged: 775 -> 491 looked like 284 only because the turn's
    +66 income had already landed when I read gold (the AI phase was still running, overview said turn 327).
- **t328-340 (runtime v105-v106)**: league_status.pending_proposals + propose readback; unit_mission illegal ->
  legal_missions + stacking reason; move_unit names my own blocker (trade units excluded -- a route caravan
  passing through is not one); standing moves verified (a "resumed" order that did not move is reported
  dropped); spread religion `converted` = majority now ours (gained_followers split); great-person missions
  report the empire number before/after; purchase_production says what was bought + flags an emptied queue;
  set_production append=true (shift-click queue); research-agreement gold_cost; incoming_deal flags renewals
  itself.
- **Visibility fix (v106)**: city_state_gifts returned `rivals` = every met major's influence with the
  city-state. No screen shows that -- the UI's only other-major read is GetAllyToolTip (the ally, named if
  met, and the gap to pass it). Now `ally` carries exactly that. Worth auditing other reads the same way:
  grep the stock UI for the getter before exposing a number about another player.
- **Visibility audit (v107, live-verified t342)**: a read-only pass over every H.* read against the stock UI Lua
  found three more leaks in `relationship` -- third-party defensive pacts (IsHasDefensivePact appears in no UI
  file), third-party city-state friendships (Global Relations shows alliances only), and a city-state ally named
  even when unmet -- plus trade_catalog's them_available (shown by the trade screen only for what they can trade
  us, without imports). All fixed. **Open**: describe_plot on fogged plots reads the live feature (a forest cut in
  fog shows as cut); no revealed-feature getter was found, and the UI Lua does not show what the renderer draws.
- **t343-368 (runtime v108-v109)**: propose_friendship (renews expired DoFs; replies flagged harness_initiated);
  available_spy_cities.potential = the espionage screen's BasePotential ("unknown" when 0 -- the relocation list's
  own Potential read 99 everywhere); diplomacy city-states carry influence_per_turn + turns_until_status_lost and
  wait_for_my_turn/turn_status warn via expiring_city_states (the Monaco alliance lapsed at 59/60 unwarned; a rival
  overtaking it -- Sweden, t361 -- cannot be warned about, rivals' influence is hidden); overview.free_trade_route_slots;
  respond_discussion expect= (refuses when the button text does not match); digest no longer repeats notifications
  an earlier digest delivered. Game: Sciences Funding passed t350; Monaco re-allied with a 500-gold gift t367.
- **t369-396 (runtime v110-v111)**: unit_mission COMMAND_* (disband/wake/cancel via DO_COMMAND; a delete verified by
  the unit vanishing); LeagueProjectPopup swept (a completed World Congress project blocked end_turn with a
  TECH_AWARD behind it); generic_popup drops its "BLAH BLAH" placeholder when closed; MISSION_DISCOVER reports
  research_turns_left before/after; purchase_* accept PROJECT_* (was KeyError); renewal note states what holds
  either way (us_exported can be another partner's export); league_status.members (delegates per member, host) +
  votes_needed_for_diplo_victory -- live t394 Venice 20 of 30 as host; **load_lua race**: two processes reloading a
  bumped runtime shared __H_SRC and one died mid-load -- now a per-load global.
  Game: World Ideology Order passed t371; Apollo Program started t391 (Beijing); Future era t394; research goal
  Nanotechnology (Robotics first). Venice (host, World Religion) is the diplomatic-victory threat.


## t437-438: league vote choice, production-queue refusals
- Yes/no World Congress votes need choice 1 (yes) / 0 (no), leagueoverview.lua kChoiceYes/kChoiceNo; -1 is
  kChoiceNone. league_cast_votes now maps yes/no words and refuses a yes/no row with no choice. First repeal
  cast with an explicit yes (Historical Landmarks, 12 votes) passed at t438; the two earlier World Religion
  repeals failed -- unknown whether their choice was set.
- Spaceship-part caps (3 boosters) count parts in any city's queue: a 4th appended booster was silently
  dropped. set_production now names the cap / an already-queued item and verifies the order landed.
- t449: the World Religion repeal failed again with all 12 China votes cast as an explicit yes, so the earlier
  failures were Venice's vote weight, not a missing choice. Landmarks (t438) passed because Venice did not oppose.
- t449: an idle Caravan home on Beijing's plot blocked the last SS Booster from entering the capital; the
  move_unit blocker hint now names idle (non-automated) trade units.
- t453-457: endgame. turn_status after the last part: game_over true / GAMESTATE_OVER in the same call sequence as
  MISSION_SPACESHIP; end_turn blocker still reads ENDTURN_BLOCKING_PRODUCTION (stale once the game is over --
  a client should check game_over first). Science Victory t457.

## 2026-09-19 (twenty-third session) — new Shoshone game from the main menu, runtime v117 -> v119

- **Single-player start from the menu** (`Game.start_single_player`, `cli start-single`): MainMenu `SinglePlayerClick()`
  -> state `SinglePlayer` `SetupGameClicked()` -> the GameSetupScreen. Front-end contexts all exist from boot and
  `GameSetupScreen` exists three times (single player / mods / scenarios); the opened one is the only one with
  `ContextPtr:IsHidden() == false`. `PreGame.SetCivilization(0, -1)` = random leader, `PreGame.SetHandicap(0, id)`,
  then the screen's own `OnStart()`. Map/size/pace/victories are the persisted Play Now settings (reported back).
- **Dawn of Man pause**: a fresh game is paused behind the load screen exactly like a loaded save; both now share
  `_dismiss_load_screen()` = LoadScreen `OnActivateButtonClicked()` (also re-enables popups, which the old inline
  Lua skipped).
- **Shoshone ruins choice** (live t2): BUTTONPOPUP_CHOOSE_GOODY_HUT_REWARD (data2 = unit id) blocked every action
  tool ("popup needs a decision") with nothing to answer it. `goody_hut_options` / `choose_goody_hut` follow
  choosegoodyhutreward.lua: goody type = GoodyHuts row order, `Player:CanGetGoody(plot, type, unit)`,
  `Network.SendGoodyChoice(pid, x, y, type, unitID)`, then hide the context as Confirm does. Verified live
  (GOODY_POPULATION: capital 1 -> 2). The follow-up BUTTONPOPUP_GOODY_HUT_REWARD is swept as before.
- **Beliefs** (audit gaps 1, 6): `available_beliefs(kind)` from `Game.GetAvailable*Beliefs()`; found/enhance refuse a
  belief that is not in its slot's list (order: pantheon-if-none, founder, follower, bonus); reformation uses the
  pantheon popup's `Network.SendFoundPantheon` gated on the end-turn blocker. Listing verified live; the
  found/enhance/reformation success paths are NOT yet exercised in this game.
- **v120-v125, same session (t5-t11)**, each from the audit, stock-UI call cited in the runtime comment:
  - `faith_great_person_options` / `choose_faith_great_person` (Network.SendFaithGreatPersonChoice; the blocker hint
    used to name choose_free_great_person, which needs *free* great people). NOT live-tested (Industrial era).
  - Attack previews: enemy **cities** now appear in `attack_targets` with UpdateCombatOddsUnitVsCity's numbers, ranged
    targets carry `preview.expected_damage_dealt` (GetRangeCombatDamage, no rand). A move onto an enemy city is never
    kept as a standing order (resume_moves would have re-attacked unordered). Loads live; numbers NOT yet compared
    with a real fight.
  - `religion_overview` (three tabs of religionoverview.lua; unmet founder -> "unknown"). Live t8. Note
    `CanCreatePantheon(true)` is the with-faith check, `(false)` only "pantheons still possible".
  - `trade_catalog` city x,y only when the plot is revealed (rule-2 leak from the audit).
  - `city_state_actions` / `city_state_action`: quests text comes from `GetActiveQuestToolTip` executed in the
    CityStateDiploPopup context (the helper include lives there, not in InGame). Live t11 on Sidon: read OK, bully
    `details` text is the real tooltip, **pledge verified** (protecting=true, 10 turns committed). Tribute / war /
    peace not exercised yet.
  - Process slip: one commit went in with a failing test because the shell lines were not chained with `&&`
    (pipefail alone does not stop a script). Chain test -> commit with `&&`.
- Game: met Sidon (militaristic, pledged) t10, the Inca (Pachacuti) t11. AUTOMATE_EXPLORE works through
  `unit_mission` and the ruins popup still interrupts it correctly.
- **v126-v128 (t13-t18)**:
  - `war_consequences(player_id)` = declarewarpopup.lua GatherData minus the deal list (that part reads the scratch
    deal through UI.LoadCurrentDeal; the scratch deal is the headless crash vector, so it is only noted). Live t13.
  - `city_capture_options` / `choose_city_capture` (popupsgeneric/puppetcitypopup.lua): unhappiness deltas from
    GetUnhappinessForecast, GetWarmongerPreviewString / GetLiberationPreviewString, Network.SendDoTask
    TASK_ANNEX_PUPPET / TASK_CREATE_PUPPET / TASK_RAZE or Network.SendLiberateMinor, then GenericPopup HideWindow().
    The popup hook now also keeps Data4, Data5, Option1, Option2. Only the "nothing pending" refusal is live-checked:
    **verify on the first real capture** (does H.popups still hold the entry, does HideWindow close it, after-state).
  - `unit_mission` takes a BUILD_* name directly (available_unit_actions lists builds that way; live t14 refusal).
  - `religion_overview.pantheons`: rival pantheons as the Beliefs tab shows them (live: Inca, Goddess of Protection).
- Game t19: capital pop 4, Shrine done, Warrior next, Bronze Working; six ruins taken (pop x2, culture x2, tech x2 =
  Archery, Animal Husbandry). Met Inca, Sidon (pledged), Wittenberg. Camps at (43,29) and (51,7).
- **t22-t33 (runtime v129)**:
  - `found_pantheon` was refused at t22 ("this religious choice is not pending"): the MCP guard demanded
    blocking_name == FOUND_PANTHEON, but the engine reports ONE blocker at a time and PRODUCTION was ahead of it.
    Guard removed (H.found_pantheon checks CanCreatePantheon + the available list). **Success path verified live**:
    Earth Mother, faith 1 -> 3/turn.
  - plain_text: an [ICON_*] standing alone for its word (God King: "yields: , , , ,") now keeps its name.
  - `unit_mission` cleared the unit's standing move BEFORE validating; a refused BUILD_FARM mid-walk left the Worker
    "stalled_mission" next turn. A refusal now restores the record (`standing_move_kept`), unless the unit already
    stands on the destination (the t315 skip-deadlock case).
  - First combat (t32, Warrior vs camp Warrior): attack_targets preview 27 dealt / 32 taken, actual 32 / 29 -- inside
    the roll's spread; formula is enemyunitpanel's. Digest reported both sides. accept_deal handled Ethiopia's
    embassy-for-1gpt offer during the AI phase (t22->23); after answering, re-issue any stalled move (resume_moves
    only runs inside wait_for_my_turn).
  - Not a bug: move_unit refusing a destination that holds an own combat unit -- the engine drops such a path.
- **t34-t100 (runtime v130 -> v134)**, each fix found live:
  - v130 `available_city_strikes`: target hp + expected damage (UpdateCombatOddsCityVsUnit).
  - v131 `move_unit` / `resume_moves`: a destination held by a civ we are at PEACE with is refused/dropped
    (`H.peaceful_occupant`). The engine answers such a move with BUTTONPOPUP_DECLAREWARMOVE, not a path (t55: resumed
    Settler order onto the site an Inca Settler+Warrior had reached). The popup sweep's HideWindow is the No path.
  - v132 `disband_unit`: a unit with no moves left cannot be disbanded -- the refusal now says so (t59). Note a
    standing move is re-pushed at turn start and spends the moves before you can disband.
  - `found_religion` now polls religion_overview and returns `founded` (religion, holy city, beliefs). **Success path
    verified live t64** (Tengriism: Church Property + Pagodas, holy city Moson Kahni) -- the returned-shape change
    itself is not live-tested (religion already founded).
  - `move_unit`: a refused move clears its H.pending_moves record (t76: it survived as `standing_move_kept`).
  - v133 builds report `build` name + `turns_left`. A feature the improvement removes runs first as its own
    BUILD_REMOVE_* (Silk/forest plantation, forest-hill mine, marsh plantation) and the ordered build follows with no
    new order (verified: Spices marsh t71 -> plantation t79).
  - MISSION_ROUTE_TO: a route the engine drops ("Route to cancelled!") now returns ok:false (t96). Cause seen: another
    civilian (Worker mining) on a plot of the path -- one civilian per plot.
  - v134 `free_great_person_options` / `choose_free_great_person`: only this civ's own great people (class default
    unless Civilization_UnitClassOverrides); the list had offered the Mongolian Khan / Venetian Merchant (t98).
  - Verified live: attack previews vs results (t44 58/13 -> 57/12, t50 60/14 -> 65/11), Pagoda faith purchase,
    propose_friendship renewal, respond_discussion (Inca settle warning), accept/refuse_deal incl. a renewal.
  - Open usability gap: no "move then build" -- a build ordered to a multi-turn destination is refused; re-issue on
    arrival.
- Game t100: 5 cities (Moson Kahni, Te-Moak, Agaidika t55, Goshute t65, Pohokwi t88), Tengriism founded t64, Liberty
  finished (free Great General). Happiness hovers -1..+4 (Spices, Ivory, Silk, 2 Colosseums, Pagoda). Inca Machu at
  (47,10) directly north of Agaidika (49,15) is the first target; staged: 2 Catapults (48,16), Composite Bowman in
  Agaidika, Archer (50,16), Great General in Agaidika. Promised the Inca at t66 not to settle near them.
- **t101-t150 (runtime v135 -> v136)**, war on the Inca:
  - propose_deal: an empty trade table read as "a different player" -- every own proposal failed since the
    empty-table shape changed; fixed t107 (verified: salt->Ethiopia 60g, open borders with Ethiopia t125).
  - end_turn (single player) now confirms the turn actually left us; a unit with partial moves (worker finishing a
    route, catapult after set-up) made the engine refuse CONTROL_ENDTURN silently (t112, t115). Note: units with
    PARTIAL moves still slip past turn_status' NO_ENDTURN check until end_turn is attempted.
  - v135: a captured civilian reports `captured` + new id (verified live t148/t149 on two recaptured workers).
  - v136: a garrisoned enemy city is attacked/previewed as the city; capture reports city_captured (fix NOT yet
    exercised: no siege since).
  - **Verified live**: city_capture_options/choose_city_capture (Machu t119 puppet, happiness 1 -> -5 as forecast;
    Tiwanaku t129 ceded by treaty -> same popup, puppet), declare_war, war_consequences, incoming peace offers
    (t118 refused, t128 accepted with a ceded city), city strikes vs rebels, faith Pagodas, Great Writer policies.
  - Minor gaps noted, not fixed: pillage result omits gold gained (digest has it); city_ranged_attack omits
    damage_dealt when it kills; unit_lost for a barbarian-captured civilian is not linked to the capture notice;
    CITIES deal items show x,y without the city name; no tile/citizen management tool (Agaidika starved ~30 turns);
    a multi-turn move onto a lone enemy civilian (capture) is not resumed at turn start (re-issue each turn).
  - Play lessons: pull damaged ranged units out of city range (lost 2 Composite Bowmen at Machu); Catapults need line
    of sight (hill at (46,11) blocked); keep Workers inside cities when rebels spawn (2 captured, both recaptured).
- Game t150: 7 cities (Machu, Tiwanaku puppets). Happiness -6 (was -14 after Tiwanaku; rebels spawned t132-t148).
  Gold ~270 at -8/turn -- the main problem. Peace treaty with the Inca expired t139; Cusco not yet located. Army:
  2 Swordsmen, 1 Trebuchet (+1 building), 3 Catapults, 2 Composite Bowmen, Horseman (Tiwanaku), 2 Great Generals.

## 2026-09-19 (late): runtime v146 + MovementCost crash

v146 (tests 122): `units()` worker job (`build` / `build_turns_left` as unitpanel.lua, +1 on GetBuildTurnsLeft);
plot `under_construction` / `trade_route` / `lake` / `resource_requires_tech`; `H.city_state_quests` on
`city_state_actions.quest_list` (kill-camp x/y only when revealed). Live t183 then t182 recover: lumbermill
turns matched the plot; Lhasa/Sidon/Wittenberg quest lists matched the CS-screen tooltip.

**Do not call `Plot:MovementCost`.** A read-only probe on worker 352258 (visible adjacent, inside pcall)
killed Civ5XP at 23:10 (Steam "game stopped"). Tuner reported "socket closed by game". Recovered with
`load_latest` -> `Saves/single/quick/QuickSave` (t182 after Airport/Colosseum sales and the Lhasa 250 gift,
gold 0 / −11 gpt, Lhasa influence 46). t183 in-turn worker ROUTE_TO was not saved. Path overlay remains
blocked: GeneratePath NYI, GetPathEndTurnPlot nil, MovementCost crashes.

v147 (tests 125): `trade_routes` is `{outgoing, incoming}` (GetTradeRoutesToYou; unmet FromID omitted);
`overview.score_breakdown` from diplolist.lua getters; `cities().blockaded` / `wltkd_turns`. Live t182:
Moson Kahni/Te-Moak → Addis outgoing; Cusco → Tiwanaku incoming sea (turns_left −3 as the engine
reported); score 606 adds up; Tiwanaku WLTKD 6t. `establish_trade_route` now diffs `outgoing`.

v148 (tests 127): available_research/production `help`; nearby_builds `build_info` (turns + yield_delta from
GetBuildTurnsLeft / GetYieldWithBuild); overview.public_opinion; city_state_actions.gift_tile_improvement
read. Live t182: Steel help names Longswordsman+Armory; horse pasture 6t +1p; forest farm −1p +2f;
public opinion NO_PUBLIC_OPINION; CS tile gift 200g can=false.

## 2026-09-20: runtime v149 — air-strike preview parity (offline)

Continued the information-parity audit from v148. Civ5XP was not running; no save was loaded or turn advanced.
Compared the installed BNW `expansion2/ui/ingame/worldview/enemyunitpanel.lua` ranged branches
(`UpdateCombatOddsUnitVsCity` / `UpdateCombatOddsUnitVsUnit`) to the harness:

- Air strikes previously reported `expected_damage_taken=0`. They now use the target's
  `GetAirStrikeDefenseDamage(attacker, false)` and carry `interception_possible`, `visible_interceptors`
  (`GetInterceptorCount(..., true, true)`), and a warning that estimated damage excludes interception.
  Zero visible interceptors still carries the warning. A failed retaliation getter leaves damage unknown.
- Ranged previews include `my_strength` / `their_strength`; defender strength follows the stock
  embarked, ranged, naval, and ranged-support-fire branches.
- Air-strike `unit_mission_targets` pages now include target details/preview. Shared target selection
  gates fog/invisibility/war status and prioritizes the city over its garrison; off-page previews are not read.
- Regression suite: `uv run --offline --with pytest python -m pytest -q tests` — 134 passed.
  Seven new Lua regression tests cover retaliation, strength branches, visibility and pagination.
- Live verification remains pending. Existing melee previews also omit the stock panel's fire-support
  damage; individual combat modifier rows are still absent. Do not use `Plot:MovementCost`.

### v149 live verification after harness launch

User directed that changes must be tested by launching through the harness. Launched with
`scripts/launch_civ5.sh civ5`, waited for MainMenu on `/run/user/1000/civ5-tuner.sock`, then used MCP
`load_latest`: restored **t182**, active seat 0, runtime 149. Game remains running on t182.

Read `H.ranged_preview` for owned bomber 466967, fighter 516109, and Composite Bowman 221199 against
currently visible Ethiopian targets. Compared each result to the actual stock `EnemyUnitPanel` Lua state's
`UpdateCombatOddsUnitVsCity` / `UpdateCombatOddsUnitVsUnit`, reading `MyDamageValue`, `TheirDamageValue`,
`MyStrengthValue`, `TheirStrengthValue`. These are the same visible-target previews available by Alt-hover
at peace; no attack or declaration of war was needed. Panel hidden after comparison.

All **13 comparisons matched exactly** (damage dealt / taken):

| Visible target | Bomber | Fighter | Composite Bowman |
|---|---|---|---|
| Harar (city 16385, owner 4) | 40 / 22 | — | — |
| Pikeman 319502 | 34 / 26 | 27 / 32 | 17 / 0 |
| Crossbowman 434189 | 46 / 19 | 34 / 26 | 26 / 0 |
| Worker 98308 | 40 / 0 | 40 / 0 | 40 / 0 |
| Warrior 114694 | 70 / 12 | 45 / 19 | 31 / 0 |

Strengths also matched (e.g. bomber vs Harar 32.5 vs 20.85; bomber vs pikeman 32.5 vs 25.6).
Air cases returned zero visible interceptors while retaining the warning. Public MCP `unit_mission_targets`
for bomber `MISSION_MOVE_TO` returned `{ok:true,total:0,targets:[]}`, correct for the peaceful save.
Remaining live coverage: a nonempty legal air-strike page, nonzero visible interceptors, embarked/naval
defender branches. Those branches have offline regression coverage. No gameplay changes or turn advance.

## 2026-09-20: runtime v151 — itemised combat modifier rows

Continued the information-parity audit on the harness-launched Shoshone t182 save. `EnemyUnitPanel` prints,
beside the two damage numbers, the list of modifiers that produced the strengths ("+25% Fortified",
"-33% Empire Unhappy", "Flanking Bonus"). The harness had the totals but never the reasons, so it could not
tell a bad attack from a bad position. `H.combat_modifiers(u, d, c, ranged, support, intercept, aa)` and
`H.city_strike_modifiers(city, unit)` port all 131 rows of the three stock `UpdateCombatOdds*` functions --
same conditions, text keys, arguments, order and column -- and are attached to `melee_preview`,
`melee_city_preview`, `ranged_preview` and the `available_city_strikes` preview as
`modifiers.mine` / `modifiers.theirs`. Each row is `{text, value, percent, key}`; the panel's value-less
rows (AIR_INTERCEPT_WARNING1/2, VISIBLE_AA_UNITS, CAPTURE_CHANCE) are notes with no value. Every getter is
wrapped so an unreadable modifier drops its own row instead of being invented as a zero, and no supporting
unit's identity or location is read.

Two panel divergences fixed on the way: `available_city_strikes` capped its estimate at the target's
remaining hp where the panel caps at the unit's maximum hp (v150's cap fix had not reached this path), and
it now reports `my_strength` / `their_strength` from `GetStrengthValue` / `RangeCombatUnitDefense` as the
panel prints them.

Stock quirk: `UpdateCombatOddsUnitVsUnit` tests `pToPlot:IsFriendlyTerritory(c)` with an undefined `c` for
the attacker's fight-at-home rows. The port passes the attacker's player id (the evident intent); all 144
live FIGHT_AT_HOME_BONUS comparisons matched the panel anyway.

Eighteen new regression tests in `tests/test_combat_modifiers.py`; `uv run --offline --with pytest python -m
pytest -q tests`: **157 passed** (139 before).

Live verification reloaded v151 through the harness and compared the helpers against the real
`EnemyUnitPanel`. The panel's two instance managers are file-locals, so the probe hooked the shared
`InstanceManager.GetInstance` and returned recording proxies: the real controls were never touched and
nothing on screen changed. **1008 of 1008 comparisons matched** -- 12 own combat units x 28 visible foreign
targets (576) plus 7 own cities x 24 visible units (336); 460 had at least one row. Twelve distinct row
types appeared live, all matching: GG_NEAR, FIGHT_AT_HOME_BONUS, TRAIT_SMALL_SIZE_BONUS, TERRAIN_MODIFIER,
ROUGH_TERRAIN_DEF_BONUS, OPEN_TERRAIN_RANGE_BONUS, ADJACENT_FRIEND_UNIT_BONUS, DEFENSE_BONUS, ATTACK_CITIES,
ATTACK_CITIES_PENALTY, OPEN_TERRAIN_BONUS, BONUS_VS_CLASS. The rest have regression coverage only; they need
war, barbarians, a golden age or specific promotions to appear. Full results:
`logs/combat_modifiers_v151_live.json` (ignored log). Read-only -- no orders, attacks or turn advance
during verification.

## 2026-09-20: runtime v150 — melee fire-support damage and panel caps

Continued the information-parity audit in the already-running harness-launched Shoshone t182 game.
Both melee preview functions now follow the stock BNW `EnemyUnitPanel` fire-support calculation:
`GetFireSupportUnit(targetOwner, x, y)` → support unit's `GetRangeCombatDamage(attacker, nil, false)`.
This damage reduces the attacker's outgoing estimate and is added to incoming damage. The returned
`fire_support_damage` is only the stock panel's displayed aggregate; no support identity/location is read
or exposed. A failed support getter leaves damage unknown while retaining strengths. Damage estimates
also use the panel's maximum-HP caps (100 for units, `GetMaxHitPoints()` for cities), not remaining HP.

Five new regression tests cover unit/city support, absent support, failed support getters, and HP caps.
`uv run --offline --with pytest python -m pytest -q tests`: **139 passed**. The five new tests all failed
against v149 before the implementation was changed.

Live verification reloaded v150 through the harness, then compared its helpers with the actual
`EnemyUnitPanel` state's damage/strength controls for every combination of five owned melee units
(2 Swordsmen, Horseman, Paratrooper, Infantry) and 23 currently visible foreign targets. All **115/115**
matched: 95 unit and 20 city comparisons. 27 outgoing unit estimates hit the panel's 100-HP cap.
Example: Infantry vs Harar gave 187 damage dealt / 4 taken, strength 91 vs 20.85, matching the panel.
Full local results: `logs/melee_preview_v150_live.json` (ignored log).

All live fire-support reads were zero; nonzero support still needs a real live example, with unit/city
branches covered by regressions. These were Alt-hover-equivalent reads at peace, without attacks,
declarations of war, unit movement, or turn advancement. The stock panel was hidden after verification;
MCP `turn_status` still reports t182, active seat 0, no blocker. Next preview work: individual modifier rows.

## 2026-09-20: the first war — runtime v152–v156, found by playing one

The harness had never fought a war. Everything about combat was verified by hovering at peace
(v149–v151's 1008/1008 panel comparison included), and `docs/GAPS.md` said as much: the war-only
rows, a nonempty air-strike target page, city capture and peace-with-terms all had regression
coverage only. So this session declared one. Seat 0 (Shoshone, t182) declared war on the Inca
(`war_consequences` first: no Declaration of Friendship to break, no allied city-state to drag in,
only their incoming Cusco→Tiwanaku route lost — against Ethiopia it would have broken a DoF with 11
turns left and pulled in Wittenberg). Nine turns later Cusco was ours.

Five separate defects surfaced within the first three turns of fighting. None of them was reachable
at peace.

**v153 / air strikes returned nothing at all.** An air unit attacks by being sent *onto* the target
plot — the mission is `MISSION_MOVE_TO`, not `MISSION_RANGE_ATTACK` — and `unit_mission` only
attached combat results to RANGE_ATTACK / NUKE / PARADROP. The first strike of the war killed an
Inca Composite Bowman outright and cost the Bomber 11 hp, and the tool said
`{"ok":true,"x":50,"y":24,"moves":0}`: indistinguishable from a bomber that never flew. move_unit's
melee reporting is now shared as `_with_attack_result` and unit_mission's move-shaped missions route
through it. Verified live: Fighter 458773 → Warrior (44,22) reported 100→57 and 15 taken.

**v153 / an out-of-range strike was accepted.** An air unit does not walk toward a target; the
engine answers an illegal strike by doing nothing whatsoever. Fighter 458773 at (49,19) was sent at
Cusco (42,23) — nine plots against a range of eight — and returned ok with both sides' hp unchanged,
which inside the *new* attack reporting looks exactly like a strike that did no damage. This is the
"accepted but wrong" shape this project keeps meeting. `attack_before` now reports the engine's own
`CanRangeStrikeAt` and the unit's range for air units, and the order is refused before it is sent.
Ground units are untouched: a melee move at a distant enemy is a legal multi-turn order.

**v152 / the promotion chooser was unreadable.** The first kill earned a promotion and
`available_unit_actions` offered `["PROMOTION_INSTA_HEAL","PROMOTION_INTERCEPTION_1",
"PROMOTION_DOGFIGHTING_1"]`, which is not a choice anyone can make. The live help text settles what
the enum hides: Dogfighting I is "+33% Combat Strength when performing an Air Sweep", *not* the
interception bonus its name suggests, and Heal Instantly warns it consumes the promotion.
`H.promotion_options` now returns `{promotion, name, help}`.

**v155 / turn_status and unit_mission disagreed about who blocks the turn.** Great General 335877 sat
at (49,20) with 0.33 moves, listed in `todo.units` with `stalled_mission: true` under
`ENDTURN_BLOCKING_UNITS`, while `unit_mission(MISSION_SKIP)` refused it as "already on a multi-turn
move and **does not block end_turn**". Both cannot be true, and the pair deadlocks the turn. The two
carried separate copies of the rule — todo() with the literal activity 6 plus moves and mid-build
checks, the guard with `ActivityTypes.ACTIVITY_MISSION` and neither — which is how they drifted.
Both now ask `H.is_stalled_mission(u)`; the guard still protects a unit that really is mid-path (the
live t306 Caravel it was written for: ACTIVITY_MISSION with 0 moves).

**v154 / steal_tech took `victim` where everything else takes `player_id`.** A spy finished stealing
mid-war and `steal_tech(player_id=2, ...)` was rejected; the argument aliaser could not help because
it only maps `k` → `k_id`. `steal_tech_options` reported the same civ under a third spelling,
`player`. The parameter is now `player_id` and each victim carries `player_id` (keeping `player`),
so the read round-trips into the write.

**v156 / a turn that would not end, and nothing true to say about it.** On t189 `end_turn` answered
"CONTROL_ENDTURN was sent but the turn did not end: a unit or decision still blocks it" beside
`blocking NO_ENDTURN_BLOCKING_TYPE` and an empty todo — three statements that together say nothing.
No blocker, no popup, no ready unit, no busy unit, research set, nothing selected; `CONTROL_ENDTURN`,
`CONTROL_ENDTURN_ALT` and a cleared selection all did nothing. **`UI.CanEndTurn()` was false the
whole time** — the flag the stock HUD uses to grey out its own End Turn button, which the harness
never looked at. `H.end_turn_diagnosis(pid)` now reads it along with HasReadyUnit / HasBusyUnit /
GetEndTurnBlockingType / IsTurnActive / IsProcessingMessages / IsCityScreenUp / GetInterfaceMode
(each through pcall — these getters vary by build) and end_turn returns them as `engine`.

*The cause of that wedge is still unknown.* Ruled out: ready/busy units, the engine's blocking type,
pending popups, unset research, free techs or policies, a selected unit, the city screen, a visible
diplo/leader/trade context (only ActionInfoPanel, DiploCorner and DiploRelationships were unhidden),
and units with queued missions (the only two in ACTIVITY_MISSION were Workers mid-build at full
moves, the normal shape). **Exiting to the main menu and reloading cleared it**, and the turn ended
immediately — so it is UI-side state, not the save. If it recurs, `engine.can_end_turn` names it.

**The capture, and what only a capture shows.** Bomber and two Fighters ground Cusco from 200 hp down
over t183–t189 (the Bomber's own rows carried `STRATEGIC_RESOURCE −50%`, a modifier row never seen
live before — the empire is in strategic deficit), a Composite Bowman at (43,22) bombarded it 22→4,
and on t190 Infantry 507929 stepped (42,21)→(42,22)→(42,23). The move result carried
`attack.city_captured: true`.

Then the whole capture chain ran live for the first time:
`city_capture_options` → Cusco, pop 5, **157 gold**, 0 great works, 0 culture, `happiness_now` 1, and
exactly two options (no raze — it is a capital): annex at **+11 unhappiness** or puppet at **+7**,
both carrying "You will receive a MAJOR Warmonger penalty if you capture this city."
`choose_city_capture("puppet")` first refused with **"diplomatic decision pending"** — Pachacuti's
defeat screen ("This cannot be. My greatness, my brilliance, all brought to ruin, by you?") had
opened on top of the capture popup; `discussion()` showed it with no buttons, `dismiss_discussion()`
closed it, and the choice then went through. `after` reported `happiness −6, puppet true,
razing false, occupied false` — exactly the preview's 1 − 7. `domination_progress` now lists Cusco
with `original_player 2`, `controlled_by_us true`, `lost_capital true`.

Smaller things seen in passing:
- `incoming_deal` carried a real **PEACE_TREATY** for the first time: Pachacuti sued for a white
  peace on t188 (mutual PEACE_TREATY, duration 10, no concessions) with Cusco at 1 hp. Refused.
- The defeat screen reports `player: -1` in `discussion()` — the leader string
  ("Pachacuti the Pious of The Inca") is there but the id is not resolved. Not yet chased.
- `available_research` returns `name` as the raw key-ish "OPTICS"/"GUNPOWDER" where
  `steal_tech_options` returns "Optics". Cosmetic inconsistency, not yet chased.
- An attacked *city* used to be reported with the raw owner id (`owner: 2`) where an attacked unit
  gave `"The Inca"`. `H.owner_label` is now shared by both (v153).

**Harness plumbing, found before the game even loaded.** `launch_civ5.sh` opens the tuner port well
before the front end creates its Lua contexts, so the README's own `launch && python -m
harness.tunerd` lands in that gap: the handshake succeeds, logs "0 lua states", and that connection
then answers every later LSQ with an empty list — `turn_status` reports screen `"?"` and `load_latest`
fails "Lua state 'LoadMenu' did not appear" forever. tunerd now reconnects (6 tries, 5 s apart) when
a handshake yields no states. And because restarting tunerd is the documented fix for a wedged game
connection, `Civ5.call` now reopens its socket instead of answering "[Errno 32] Broken pipe" to every
tool for the rest of the process's life; it resends only when the write failed outright, never after
a clean EOF (a silently repeated `move_unit` or `end_turn` is worse than one visible error).

**v157 / the captured-city row pointed at the wrong city.** Civ5 city ids are per-player, and
`SerialEventCityCaptured` hands over the *previous owner's* id. Taking Cusco recorded
`{player: 2, city: 8192, by: 0}` -- and 8192 looked up in `cities()` is our own capital, Moson Kahni.
An id that silently resolves to the wrong city is worse than no id. The hook now converts the event's
hex to plot coordinates (as the `city_created` hook already did) and reads the city standing there,
which by then belongs to the captor, so the row carries `name`, `city_id`, `owner` and `x`/`y`; the
engine's id survives as `former_city_id`. **Regression-tested only** -- there was no second capture
this session to check it against.

**The Inca were destroyed.** Cusco was their last city, so the capture ended them. `civ_eliminated`
fired correctly at the t191 turn start -- `{player: 2, civ: "The Inca", leader: "Pachacuti",
summary: "The Inca (Pachacuti) has been eliminated: its deals, friendships and votes are gone"}` --
the first live exercise of a path that until now had infrastructure but no occurrence. Note the
timing: `H.check_eliminations` runs on `ActivePlayerTurnStart` and compares snapshots, so a civ that
dies during our own turn is reported at the *next* turn start, not immediately. Mid-turn,
`H.alive_majors` still listed the Inca while `Players[2]:IsAlive()` was already false; that is the
design, not a fault, but it is worth knowing before chasing it again.

Tests: 185 passing (157 at the start of the session), across
`test_tunerd_reconnect.py`, `test_air_strike_result.py`, `test_promotion_options.py`,
`test_stalled_mission.py`, `test_end_turn_diagnosis.py` and `test_city_captured_event.py`.

Seat left at t191, Shoshone, at peace with everyone, 8 cities (Cusco a puppet), quick-saved.

## Three session-killers before a single order was given (2026-09-21, Shoshone t192-)

Nothing in this session's first hour was about Civ V. Launching the game, connecting to it and
finding out which seat we were sitting in each failed in a way that could not be recovered from
without restarting a process that is not restartable mid-session. All three are fixed.

**The tuner port opens minutes before the Lua states exist, and the daemon latched onto the gap.**
Known since 2026-09-20; the fix then was to retry the handshake six times, five seconds apart.
This machine needed *five and a half minutes* to reach the main menu, so the budget ran out, and
`_connect_with_states` did what it was written to do on its last attempt: keep the connection it
had. That connection reports 0 Lua states forever, so every tool answers "Lua state 'X' did not
appear" until a human restarts the daemon. A bigger retry budget is still a guess. A stateless
connection is now *provisional* instead: `Bridge.ensure` retries it on the next request (at most
once every 5s, so a genuinely loading game is not hammered), and the first tool call after the main
menu appears simply works. `drop()` clears the flag too, so a reconnect must prove itself again.

**The 'auto' seat never got a second chance.** `game()` resolves the seat once, on first use, and
detection needs a loaded game -- which the MCP server, started with the session, usually does not
have. `detect_seat` raised, the exception was swallowed, and the seat silently stayed at its
*hotseat* default of 1. In this solo game we are player 0, so every single tool answered
`{"ok": false, "err": "this seat is not active", "active_player": 0}`, including `wait_for_my_turn`,
which sat waiting for a seat that will never be active. There was no way out from inside the
session: restarting the MCP server is exactly what loses `mcp__civ5__*` for good. Detection is now
retried until it resolves.

Both were found the hard way, and the second one cost this session its MCP tools anyway (the server
process had already cached the bad seat before the fix existed). `scripts/mcp_session.py` is the
workaround made reusable: it runs a whole script of tool calls over *one* stdio MCP server it spawns
itself, with `--seat` of our choosing -- the same end-to-end surface, no dependence on the
long-running server. Everything below was played through it.

**A launch footgun worth naming:** `scripts/tuner_probe.py` *binds* 127.0.0.1:4318. Run it while the
game is starting and it takes the port the game is about to want; Civ5 dies with "Terminating due to
uncaught exception ... of type int" during its front-end load. Poll `ss -ltn | grep 4318` instead --
watching a port is not the same as owning it.

## A puppet is not ours to run (runtime v158)

`set_production` was the one city write without the `IsPuppet` guard the other seven carry, and the
hole was not theoretical. Live t192, on freshly-captured Cusco: `set_production(UNIT_WORKER)` came
back `{ok: true, turns: 7001}` -- and it was still there after the turn boundary, while the other
two puppets (Machu, Tiwanaku) had picked a Market and a Monument for themselves. The order did not
bounce off the AI; it *replaced* it, permanently, at a city whose production makes a Worker a
7001-turn commitment. The stock city screen has no production picker for a puppet at all.

Two reads pointed straight at that hole. `available_production` listed every item as if one could be
chosen, and `turn_status.todo.cities` listed the puppet as a city needing production -- so the
blocking hint ("todo.cities, then available_production + set_production") walked the LLM into the
illegal order. `H.todo` now skips cities whose production is automated, which is the engine's own
predicate for "not your decision": live, `IsProductionAutomated()` was true for exactly the three
puppets and false for all five cities we run, and the engine raises no ENDTURN_BLOCKING_PRODUCTION
for them either. The read and the write both refuse now, naming the way out (annex via `city_task`).

`purchase_cost` needs no guard: the engine's own `IsCanPurchase` already answers false for a puppet
(verified live on Cusco -- cost 500, `can_purchase` false). Note the asymmetry, because it is the
whole reason this bug existed: buying is gated engine-side, queueing is not.

**Cusco is still building that Worker.** The fix closes the door; it cannot take back the order that
found the bug.

## The inline-query budget was a guess, and the guard fix tripped it

Adding the two guard lines to `set_production` broke it -- with a Syntax Error, for an edit that had
nothing to do with syntax. `Game.q` decides between an inline query and the chunked path by measuring
the *body* against a flat `Q_INLINE_MAX = 2000`, but the tuner measures the whole command, and
`query()` wraps every body in 268 bytes of pcall/JSON/print scaffolding. set_production's body went
from 1735 bytes to 1825; wrapped, from 2003 to 2093; the tuner's limit is **2048** (it truncates
there and the game reports "Syntax Error" quoting the cut-off source). So a limit that had held for
months was one short edit away from failing, anywhere in the file, for no visible reason.

The budget is now computed: `COMMAND_MAX - query_overhead() - margin`, from the real wrapper, which
puts the inline ceiling at 1716 bytes of body. `TunerClient.COMMAND_MAX = 2048` is measured, not
folklore -- 2003 bytes ran, 2093 did not.

## The same hole, one tool over (runtime v159)

Auditing every `own_city()` write for the puppet guard turned up `buy_city_plot` without one, and
the engine does not cover for it: live t193, `CanBuyPlotAt` returned **true** for all three puppets
with real prices (65g, 80g, 130g). The stock city screen shows no buy control for a puppet at all,
and the other four tile/citizen writes already refused. Guarded now, and verified live on Cusco's
(39,23) -- the plot it would have sold us for 130 gold.

The rule this leaves behind, because it is not guessable and cost two bugs to learn: **the gamecore
enforces only some of what the UI hides.** For a puppet city, `IsCanPurchase` is false (rush-buy is
gated engine-side) while `CityPushOrder` and `CanBuyPlotAt` are wide open. "The engine accepted it"
is not evidence a human could have done it -- it is only evidence that nobody in the gamecore
happened to check. So `tests/test_puppet_guards.py` is a lint rather than a behaviour test: every
`H.*` function that goes through `own_city()` must either guard or be named, with a reason, as
deliberately puppet-safe. The next city tool is then a decision someone made.

The eight hand-written `if c:IsPuppet()` copies are now one `H.puppet_guard(c, what)`. One of those
copies going missing is the entire story of v158 and v159.

## New live coverage: paradrop, disband, and what a refusal is for

`MISSION_PARADROP` has been implemented since v139 and had never been fired. Live t199, the
Paratrooper at (45,20) dropped to (43,11) -- nine plots north, into the frontier -- and the result
carried the evidence a human sees on screen: `target_before` empty, `target_after` holding
`{id 475136, PARATROOPER, hp 100, owner 0}`, `moves 1.5` left, activity AWAKE. It walked on to
(42,10) with the rest of its move and revealed seven plots (`explore_frontier`'s `unrevealed_plots`
2260 -> 2253).

It got there because a *refusal* was informative. `AUTOMATE_EXPLORE` on a Paratrooper came back
`{ok: false, err: "action is not currently legal"}` with `legal_missions` listing what it could do
instead -- including the paradrop nobody had thought to try. Two trebuchets refused `MISSION_FORTIFY`
the same way earlier in the turn (siege units cannot fortify) and named `MISSION_ALERT`.

`disband_unit` also ran live for the first time, twice, on the Worker glut `play_loop`'s heuristic
had built up: `effects.before/after` reported the unit count going 25 -> 24 -> 23 alongside the
strategic-resource table, which is where a disbanded unit's resource would come back.

`explore_frontier` earned its keep on the same turn: 2260 unrevealed plots of a 66x42 map, a
13-plot frontier, three reachable spots north, and the rest marked `reachable: false` with
`closed_border: 3` -- Persia's borders, named as the reason rather than left as a silent omission.

**Where the game stands.** Six majors, five alive: we have met Persia and Ethiopia and have *not*
met the Maya or Morocco, which is why `league_status` still answers `has_league: false` -- BNW founds
the World Congress only once a civ with Printing Press has met everyone, and exactly one civ has
Printing Press (not us). So the whole League surface, the one big subsystem with the most
never-exercised tools, is gated behind exploration from here. That is the obvious next arc: the
Paratrooper is already walking north, and the frontier list says where the map ends.

**Seat left at t205**, Shoshone, at peace, 8 cities (three of them puppets), gold 385 at +9/turn,
happiness back to +3 from -6, 23 units, researching Compass. Quick-saved. The empire's tech is
lopsided -- Industrial-era land units and aircraft, but no Optics/Compass until this session, hence
no navy at all -- which is why 2253 of 2772 plots are still dark. The route to the League runs
Compass -> Astronomy -> Navigation, build ships, meet the Maya and Morocco; Printing Press itself has
no missing prerequisites (13 turns). The Paratrooper sits at (42,10) on the northern frontier.

`scripts/play_loop.py` drove turns 193-205 unattended. Two things it taught:

- It was spending **2m26s per promotion** walking a hardcoded list of 26 candidates, one tuner
  round-trip each, because it predates `available_unit_actions(unit).promotions` (v153). It asks the
  unit now. (First attempt at that fix filtered on a `promotion_ready` field that belongs to
  `choose_promotion`'s *reply*, not to a `units()` row -- which skipped every unit and would have
  deadlocked the loop on ENDTURN_BLOCKING_UNIT_PROMOTION. `turn_status.todo.promotions` is the list
  the blocking hint actually points at.)
- Its heuristic queues a Worker in any city with an empty queue, so thirteen turns of it left seven
  Workers and a gold deficit. That is the bot being a bot, not a bug -- but it is why `disband_unit`
  finally got exercised.

## 2026-09-22: runtime v177 — the icons on a tech button

`tech_tree` and `available_research` listed a tech's cost, turns, and (on the leaf list) the help
paragraph. The paragraph is not civ-specific: Navigation still says "Frigate" for England, whose
button is Ship of the Line, and it never mentions Portugal's Feitoria. The buttons are
`AddSmallButtonsToTechButton`. `unlocks` follows that walk.

`GetHelpTextForUnit` is not in the InGame Lua state the tuner runs, so a unit button carries the
same facts the tooltip prints: `GetUnitProductionNeeded`, moves (not for air), range, ranged
strength, strength, `Game.GetNumResourceRequiredForUnit`, and the written Help. Another civ's
unique is excluded by the class-default / `Civilization_*ClassOverrides` rule. Ability icons use
the stock text keys. The help paragraph is stored with color and icon tags stripped.

Live on the loaded Shoshone game, turn 241, no orders: Navigation (current) was Frigate (185
production, strength 25, ranged 28, range 2, moves 5, 1 Iron), Privateer, Seaport. Military
Science was Comanche Riders, not Cavalry. Optics ended with "Allows land units to embark…".
Astronomy was faster embarked movement, then crossing oceans. Fertilizer's pasture said "Pasture
Food yield improved by 1." Guilds' Wealth said "Enables conversion of Production to Wealth."
Feitoria was absent. An independent walk of the same GameInfo tables matched the button prefix
on Navigation, Optics, Astronomy, Engineering, Military Science, Printing Press, and Bronze
Working. 298 tests. The turn was still `ENDTURN_BLOCKING_LEAGUE_CALL_FOR_PROPOSALS`.

## 2026-09-22: runtime v178 — the Happiness screen's rows

`happiness_breakdown` had the top-bar tooltip totals. The Happiness screen (click the happiness number)
expands further: which luxury is worth 4, which city's citizens cost what, and a hover that says the
count is not the usual 3 per city or 1 per citizen. `happinessinfo.lua` is that screen. The new fields
follow it.

`difficulty` is the residual `GetHappiness()` minus every itemized source, including league happiness,
which is the line the screen labels "from Difficulty Level". Garrison happiness is not itemized there,
so it falls into that residual. `by_luxury` is `GetHappinessFromLuxury` for each resource above zero.
A city row uses `GetHappiness` (buildings), `GetLocalHappiness`, connection happiness
(`GetHappinessPerTradeRoute() / 100` on a connected non-capital, and only when the empire total is not
zero), and `GetUnhappinessFromCityForUI() / 100`. Occupied is the tooltip "City is Occupied!". A zero
the screen prints as a dash is omitted. The citizen and city-count hovers are the same text keys, with
icon tags removed.

Live on the loaded Shoshone game, turn 241, no orders. Eight luxuries at 4 summed to the luxury total
of 32. Difficulty was 9, the same number as the residual computed beside it. Local happiness summed to
37 and connection happiness to 7, matching those empire totals. Eight cities, none occupied (Cusco
included), citizens 59. The citizen hover read "Because of bonuses your empire has earned, they produce
-5% the usual amount" (`GetUnhappinessMod` was -5; that is the stock wording). Per-city unhappiness
summed to 80.05 against an empire total of 80, which is the screen's per-city hundredths, not a second
formula. 341 tests. The turn was still `ENDTURN_BLOCKING_LEAGUE_CALL_FOR_PROPOSALS`.
