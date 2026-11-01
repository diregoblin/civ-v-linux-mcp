# Playbook for an LLM seat

You are one player in a game of Sid Meier's Civilization V (Brave New World). The other seats are the game's
own AI, one or more humans, or other LLMs; the mode (solo, hotseat, LAN) does not change how you play. You
control your seat only through the `civ5` MCP tools. You see only what a human in your seat would see:
fogged tiles carry no live units, unmet civs do not exist for you, and no tool reads another player's
private state. Do not try to work around that.

There are nine tools. The game is a clock (`turn`), a world of objects each carrying the actions the engine
allows right now (`state` reads one, `order` writes to one you own), the questions it asks (`question`,
`answer`), your notebook (`notebook`), many orders at once (`batch`), the session (`session`: saves, loads,
the seat) and the books (`reference`: the rule book, and this playbook by topic). Every reply that lists what
can be done hands back `actions` / `call` rows -- complete calls, `{tool, args}`, to copy as they are into
`batch` or to make one at a time. `reference(book="playbook", section="orders")` prints every order's target,
action and arguments and every object's views, from the same data the server validates with.

The game instance and the tuner bridge are set up for you (`docs/AGENT_INSTALL.md`). If `turn(action="status")`
reports `ingame: false`, no game is loaded: `session(action="load_latest")` resumes the newest save in a solo
game; in a game with other people, ask the human before loading anything. A load works only from the main
menu: `session(action="main_menu")` leaves the loaded game (quick-saving first when it is your turn in a solo
game) and, in a game with other people, ends it for them too, so ask first.

**Read `gate` first.** Every status (`turn(action="status")`, `turn(action="wait")`, `turn(action="finish")`)
and every refusal carries `gate`. `null` means you may act. Anything else means nothing works until it is
cleared, and the object says what and how: `name` and `why` describe it, `clear_with` is the call that clears
it, and `actions` are the calls as rows you can run as they are (the read first when one shows the choices; a
row with `choose` needs its argument picked from that read -- `id` and a plot's `x` / `y` on a read go at the
top of the row, a choice such as `item` or `tech` under its `args`). `question()` shows the question a gate asks with its `answers`
rows, `answer(choice)` takes one. Run the gate's rows; do not work the situation out from the other flags, and
do not read the board while a gate is up -- nothing has changed since it went up. The gates, in the order they
are enforced: `no_game`, `game_over`, `other_seat_active` (not your turn), `hand_off_screen` (your own
Continue screen, in hotseat), `processing`, `load_screen` (the Dawn of Man splash of a single-player game
started or loaded by hand), `paused`, `turn_not_active`, `leader_screen`, `discussion`, `tech_choice`,
`decision_popup`, `announcement_screen`. The first six and the last are cleared by `turn(action="wait")`.
Your own Continue screen and the splash are pressed for you by whatever you call first (`hand_off_cleared` /
`load_screen_cleared: true` in that answer, and the turn is yours), so `hand_off_screen` and `load_screen`
appear only when that press did not take. Announcement screens (a Great Person born, a city-state met, a wonder, an era: nothing to
decide) are closed the same way by whatever you call first, reads included (`swept_popups` names them), so
`announcement_screen` appears only when that close did not take. The end-turn blocker is not a gate: it stops
the turn's end, not you, and `blocking_name` / `blocking_hint` / `todo` say what clears it.

`status.seat` is the player you are. In hotseat, a different `active_player` is the other player's turn, not
a reason to change seats. Only when your server's seat was guessed (`--seat auto`) and nobody else plays the
seat on screen, `session(action="seat", args={"seat": N})` moves it there (`session(action="seat")` re-detects).
A server started with `--seat N` refuses to move, and a server whose tunerd connection is seat-bound (the
daemon has a seat table) plays that seat and no other: a seat change onto another seat is refused with `bound`,
`session(action="seat")` lands on the binding, and `bound to seat N` on every tool means the server was started
with the wrong `--seat` (the human restarts it). Never take a seat another player is playing.

## The turn loop (every turn, in this order)

**Two agents, one hotseat game.** Each agent runs its own MCP server pinned to its seat (`--seat 0`,
`--seat 1`); both may sit in `turn(action="finish")` at once, the inactive one waits while the active one
plays. Every call is one operation on a lock shared by every process on the tuner socket; a wait holds it only
for the instant of each poll. `another game operation is running` tells you only what the hand-off screen
would: another seat is acting (retry, or wait for your turn), or one of your own earlier calls still runs
(named, with its pid). A refusal that lasts a minute at game start is the first call injecting the runtime.
Keep your seat: a different `active_player` between turns is the other player's turn, not a reason to move
the seat onto it (a server started with `--seat N` refuses to). While it is not your turn every tool but the
waits and the notebook answers `this seat is not active`: you see nothing of the other player's turn, as a
human waiting for the hand-off screen sees nothing. Do not run `scripts/mcp_call.py` for waits from a shell you
will stop watching; a one-shot server keeps polling until its timeout.

**Two clients, one seat.** `other_clients` on a status names every other live MCP server of your seat attached
to this game (pid, client label, how long, when it last called); an idle one is harmless, an earlier session of
yours is worth stopping. The turn's first order claims the turn for that process (a file beside the lock,
per socket and seat). A refusal or status carrying `turn_claim` means another client of your own seat is
playing this turn: its pid, how long it has held the turn and when the claim lapses are in the answer. Read,
wait, take notes; do not end the turn under it. The claim lapses 180 s after that client's latest order, or at
once when its process is gone; `force: true` on `turn(action="end")`, `turn(action="finish")` or `batch` takes
it over (the other client crashed, or you are the one taking over on purpose). The claim carries the holder's
client label; `same_client: true` in the refusal means the holder carries yours -- an earlier session of your
own agent, kept alive by your client after a context reset -- and `force: true` is the right answer at once;
without it, a different model on your seat is still playing. A `skip_quiet_turns` run owns each turn it ends
and stops, handing the turn back, if another client acts on one first (`woke_because:
["other_client_holds_turn"]`).

A leader's offer can come up at the end of your turn, during the AI round; answering it takes a few seconds,
and the round may finish meanwhile. The `turn(action="finish")` you then make ("call again") meets the new
turn cold: nothing of yours has seen it, so it comes back **unended** -- `unseen_turn: true`, `woke_because:
["turn_unseen", ...]`, `ended: false`, with its status and digest. Play it, then finish again. With
`skip_quiet_turns` a quiet one passes like any other; `turn(action="finish", actions=[...])` on one runs none
of the orders (`batch.skipped`), since they were meant for the turn before. An **order** sent while the AIs
still move is not refused: the engine answers it once the round ends, so the call blocks until your turn
arrives and the order then runs on the new turn, its reply carrying `arrival` (the turn's standing moves and
open orders, and the `digest` when this is the first call to see the turn). Send `turn(action="wait")` first
when you want to read the new turn before ordering anything on it.

1. `turn(action="finish")` (it sends progress while it waits; the default timeout_seconds of 600 is verified
   safe in Claude Code, which moves a call past 120 s to a background task and reports its result; with a
   client that has a hard per-call limit, pass a smaller value). It ends your turn, blocks until you may act
   again, clears informational popups, and returns the new turn: `status` (as `turn(action="status")`),
   `digest` (combat, captures, growth, leader messages, notifications; `turn(action="briefing",
   detail="digest")` on its own), `turn`, and `notes` (what you told the notebook since your last finish or
   briefing; `notes_unshown` counts the older ones, `notebook(action="recall")` has them all and `notes="all"`
   brings the latest eight back). Read its result:
   - `ok: false` with an end_turn object: the turn did not end. `status.todo` and `blocking_hint` say why;
     fix it and finish again.
   - `discussion_pending: true`: a leader is on screen and wants an answer. See "Leader screens". Then finish
     again: it notices the turn already ended and only waits.
   - `tech_popup_pending: true`: research is unset. `state(what="options", view="research")`, then its row
     `order(to="empire", action="research", args={"tech": ...})`, then finish again.
   - `timed_out: true`: the other players are still moving. `next` is the call that resumes the wait; the
     default 600 s with progress notifications every 5 s is one call where 50 s windows are three.
   - otherwise it is your turn; continue.
   On the very first turn of a session use `turn(action="wait")` instead (nothing to end yet). The pieces also
   exist on their own: `turn(action="end")`, `turn(action="wait")`, `turn(action="status")`.
2. `notebook(action="recall")` if `notes` did not already tell you the plan. Your context will be compacted or
   lost between sessions; the notebook is what a human keeps in their head. It is per game and per seat.
3. `turn(action="briefing")` is the short way in: every decision of the turn with its `actions` rows, warnings,
   what changed since your last briefing (empire, cities, units, events), notable cities, damaged units,
   visible threats near your cities and units (compact rows; a threat your previous briefing listed is only
   marked `seen` unless it moved; `detail="full"` for whole rows), and the notes you wrote since your last
   briefing or finish. After a context reset call `turn(action="briefing", since="turn")`: it re-lists this
   turn's events, your civ's own rules and every recent note. `turn(action="finish", briefing=true)` hands each
   new turn back this way. For the full picture: `state(what="empire")` (gold, science, culture, happiness,
   era, your player id), `state(what="units")`, `state(what="cities")`, and the briefing's board for the
   map you can see. Prefer the briefing and `state(what="map", view="grid")` over large windows; keep
   `state(what="map", view="window", x, y, radius)` at radius 3 or below. For one unit's next step or attack,
   `state(what="unit", id, view="tactical")` answers in one read: neighbours by coordinate with the move's
   answer, attack previews, occupants and fog.
4. Give every unit an order and every city a production item. Read before you act:
   `state(what="units", view="actions")` (the legal actions of every unit that still needs an order, and of
   every unit with a promotion waiting, in one call; `state(what="unit", id, view="actions")` is the same for
   one unit with its targets and previews; `detail="summary"` is one short row per unit -- position, moves, hp,
   its orders as `actions` rows ready for `batch` (a `choose` row needs its plot or enum picked first); every
   options read hands each choice back with `call`, the write that takes it, so an order is a row copied out
   of a read), `state(what="city", id, view="production")`, `state(what="options", view="research")`,
   `state(what="options", view="policies")`. Names are the game's own ids (`UNIT_WARRIOR`,
   `BUILDING_MONUMENT`, `TECH_POTTERY`, `POLICY_TRADITION`, `BUILD_FARM`, `MISSION_FORTIFY`). Those rows carry
   the id, the name and the live numbers (turns, cost, purchase price) -- not what the thing does. That is the
   rule book, `reference(section)`: `units`, `buildings`, `techs`, `policies`, `promotions`, `beliefs`,
   `resources`, `terrain`, `improvements`, `projects`, `processes`, `specialists`, `actions`, read once from
   this game's own database. Read the whole book at the start of a game if your context can hold it (it is
   long), otherwise the section a choice needs; it never changes mid-game, so never re-read it for the same
   question. It is also the MCP resource `civ5://reference` and works while it is not your turn.
   Torn between a few options? `state(what="compare", kind=...)` puts them side by side in one read:
   `kind="production"` with `city_id` and up to 8 item ids, `kind="research"` with tech ids,
   `kind="improvements"` with a worker's `unit_id` (and `plots` / `BUILD_` ids if you have some in mind;
   `sort="food"` etc.), `kind="trade"` with a caravan's `unit_id` (`sort="gold"` etc.). Rows keep engine
   numbers, table effects and estimates apart, and `assumptions` says what each estimate leaves out;
   `empire_change` is empty for a tile no city works, and a trade `hazard` of `none_visible` still has fog in
   it. You choose the objective.
5. `turn(action="status")`: `blocking_name` names what still prevents ending the turn and `blocking_hint`
   names the read and the order that clear it (table below). Resolve it, read the status again, repeat until
   it is clear, or only `ENDTURN_BLOCKING_UNITS` remains for units you deliberately left idle (give them
   `MISSION_SKIP` or `MISSION_FORTIFY`).
6. `notebook(action="remember", args={"text": ..., "tag": ...})` what future-you must know: the plan (`tag:
   plan`; use `replace_id` to keep one living plan), threats, promises, why you did something. A replace
   returns `previous` (what it overwrote) and is refused when your tag differs from the note's stored tag: the
   id was probably wrong, so check `notebook(action="recall")` before passing `retag: true`.
   `notebook(action="forget", args={"note_id": N})` removes a stale note. What a unit or city is *for* goes in
   an assignment instead: `notebook(action="assign", args={"role", "purpose", "unit_ids", "city_ids",
   "target", "done_when", "review"})`, e.g. an escort (`unit_ids: [archer, settler]`, `target: {x, y}`,
   `done_when: "city_at"`), an improvement (`done_when: {kind: "improvement", improvement: "FARM"}`), a
   diplomatic reminder (`target: {player}`, `review: {turn: N}`). The briefing lists them with `state`: close
   `condition_met` ones with `notebook(action="close", args={"assignment_id": N})`; read each `needs_review`
   row's `reasons` and `notebook(action="amend", ...)` or close it (a unit upgraded with
   `order(to="unit", id, action="upgrade")` keeps its assignments and order under the new id by itself:
   `carried_over`). Nothing is ever ordered or closed for you.
7. `turn(action="finish")` exactly once (it quick-saves first by default). In hotseat and LAN games a second
   end is refused with `turn_complete_sent`; that is not an error. Back to step 1.

### Letting quiet turns pass

`turn(action="finish", skip_quiet_turns=N)` keeps ending turns, up to N more, while nothing needs you: no unit
awaiting orders, no empty city, no promotion, no popup, no blocker, no expiring city-state ally, deal or
declaration of friendship, and nothing eventful in the digest (combat with a unit of yours in it -- a fight
between other players is not, losses, cities changing hands, wars, leaders talking, wonders, great people,
religion, espionage, congress, trade routes; a popup the harness closes itself -- the tech award, Who's
Winning, a new era -- is not eventful (whether already closed or still listed for the sweep), nor is a notice
that decides nothing for you: a city-state changing hands between two other players, a denouncement or
declaration of friendship between others, a city-state's quest, "May Purchase With Faith", the end of your
golden age. The same events about you -- "Influence over Yerevan has increased", "than you", "Denounced us!"
-- still wake). `wake_on=["Machinery", "Askia"]` adds your own words, matched against event kinds and
notification text, and always wakes. Cities keep building their queues and research continues; the harness
never gives an order for you. The digests of the skipped turns are merged into the result, and
`turns_skipped` / `woke_because` say what happened. Use it the way a human presses End Turn a few times while
a wonder builds: with a plan in the notebook and units fortified or sleeping, not mid-war.

`status.alerts` is the exception to "quiet means todo is empty": it lists low happiness (2 or below, or an
unhappy tier) and every revealed strategic resource in deficit, on every status, without blocking anything.
A run wakes on it only when the figure worsens against the previous turn this seat saw (`woke_because`
`happiness_drop:4->1`, `unhappy:unhappy`, `strategic_deficit:IRON:-2`); a steady happiness of 1 through a
five-turn Circus lets the run continue; a drop of one or two is a city growing and stays quiet (3 -> 2 is not
news); a drop of 3 or more that lands below 10, any drop into the negative, or 5 or more at once anywhere (a
luxury lost) wakes. The baseline lives in the notebook file, so a server started mid-game compares against the
last turn any process of this seat saw; a seat no process has seen yet has none. An expiring deal, friendship
or city-state ally wakes a run once, the turn it enters its warning window, and that too is remembered across
processes; the AI usually offers a deal's renewal itself at the turn it ends (a deal screen with `renewal:
true`, `answer(choice="accept")`) -- propose on `reoffer_on` only when it did not. Read the alert before
swapping a build: on 2026-09-26 the
Circus that held Mongolia at happiness 1 was the easy thing to swap away while the total sat on the empire
read, one the loop never called.

`todo.ongoing` is the other exception: units the game is already moving -- on `AUTOMATE_EXPLORE` /
`AUTOMATE_BUILD`, or walking a move that needs more turns (`going_to: {x, y}`, also on
`state(what="units")`) -- with their plot, moves and hp. They are yours but not decisions: they never block
end-turn and a run does not wake for an explorer merely exploring. Each row's `attention` lists what would
pull a human back -- a visible barbarian camp on or beside the unit, a visible hostile combat unit beside it,
a destination no longer revealed or passable -- and any of those wakes the run (`woke_because`
`ongoing:<id>:camp`). Only plots you can see are read. A new move or mission takes an automated unit back; a
standing move is replaced by any new order. On 2026-09-26 (Mongolia, t42) the auto-explore scout drifting
toward a camp was on no list at all.

## Many orders, one call

`batch(actions=[{"tool": "order", "args": {"to": "unit", "id": 7, "action": "mission", "args": {"mission":
"MISSION_FORTIFY"}}}, ...])` runs a list of orders in sequence and returns each one's result. It stops at the
first refusal and lists the rest under `skipped`: re-read the state before re-issuing those, since what you
reasoned about may have changed. Reads first, then one batch of orders, is a normal turn. The waits, the
turn's end, a load and the seat never go inside a batch.

The orders that close a turn go in `turn(action="finish", actions=[...])` with it: they run exactly as
`batch` would, and the turn ends only when every one was ok. The reply carries `batch` (the same `results` /
`skipped`) either way -- with the new turn on success, with the current `status` and `ended: false` on a
refusal, so nothing is ended on a board you misread. A turn that needs no look is then one call. A turn that
needs one first (move the scout, see what is there, then decide) is two: `batch` or one move for the look,
then the finish with the rest. A move's result carries `revealed` -- how many plots the move uncovered
(`count`, `water`), the `notable` ones among them (ruins, a camp, a luxury or strategic resource, a natural wonder,
a city) and the foreign units or cities that came from fog into sight (`sighted`); `count: 0` says nothing new,
and `map` is the map-window read of the new ground when you want the plots themselves -- so the look needs no
tactical view or unit list after it.

A unit that still has movement after its order keeps the turn open: a one-plot move with two moves, a ranged
attack, a worker sent to the next tile. That unit can still act this turn -- a second move, an attack, a
fortify -- and the engine refuses the end (`ENDTURN_BLOCKING_UNITS`) so the choice is yours rather than
forfeited. Decide for every unit you touched before the turn closes: give it a closing order in the same
batch (a longer move, `MISSION_FORTIFY`, `MISSION_SLEEP`, or `MISSION_SKIP` when it has nothing to do), or,
when the refusal comes, treat the reply's end_turn object's `todo.units` as the list of open decisions and
pass its `skip_actions` (the MISSION_SKIP orders for exactly those units) as the next finish's `actions` only
for the units you mean to leave.

Every row a reply hands you is callable as it is: a gate's `actions`, a unit's `actions`, a choice's `call`, a
`{tool, args}` row inside a batch. The old tool names (one per button, before version 2.0.0) still run and
their reply carries `renamed`, the same call in the nine-tool vocabulary; copy that. `inspect` (the 2.0.0 to 2.6.1
name of `state`) answers the same way, with the arguments unchanged.

Any action may carry an extra `action_id` (any string you choose, e.g. `"t42-move-7"`). Calling the same
tool again with the same `action_id` returns the earlier result with `replayed: true` and runs nothing:
use one whenever you retry after a transport error or timeout, so a unit never moves twice.

## Verify, do not assume

Every order returns the state it could read back. Check it before moving on:

- `order(to="unit", id, action="move", args={"x", "y"})` returns the unit's new `x`, `y`, `moves`. If they did
  not change, the path was blocked or the unit had no moves; do not re-issue blindly. Read
  `state(what="unit", id, view="tactical")`: each neighbour's `move` says whether the move would be refused
  and why.
- `action="mission"` with `MISSION_FOUND` on a settler with 0 moves does nothing and silently resets. Move
  first, found next turn when `moves > 0`, then confirm with `state(what="cities")`.
- `MISSION_BUILD` takes `build="BUILD_FARM"` (the improvement id) in `args`, never x/y. The result says whether
  the build stuck. Workers keep building across turns; leave them alone until done.
- `order(to="city", action="produce")` and `order(to="empire", action="research")` verify the change and
  refuse illegal choices. On `ok: false`, read `err`, re-read the options, choose again.
- After a batch of orders, read `state(what="units")` once and confirm nothing you moved still sits on its
  old tile with full moves.
- A refused order never crashes anything. Its `err` says why and, where possible, what to do instead; a
  malformed one names the shape it should have had, with an example.
- Unit ids are per player: another civ's unit can carry the same `id` as one of yours (a Venetian Lancer and
  a Maya Musician both 942113 in one map window). Match a foreign unit by `id` AND `owner`, never by id alone;
  your own orders take your ids only.

## What `blocking_name` means and what clears it

`turn(action="status")` carries the same mapping live as `blocking_hint`; this table is for planning. The
read shows the choices, each with its `call`; the order is that row. A popup's choices come from `question()`
and its `answers` rows; `answer(choice)` takes one.

| blocking_name | Clear it with |
|---|---|
| `ENDTURN_BLOCKING_UNITS`, `UNIT_NEEDS_ORDERS` | an order for every unit in `todo.units`: `order(to="unit", id, action="move", args={x, y})`, or `action="mission"` with MISSION_SKIP / MISSION_SLEEP / MISSION_FORTIFY / MISSION_BUILD |
| `ENDTURN_BLOCKING_STACKED_UNITS` | move one of the two units off the shared tile. Skip and fortify do not clear this, even on a city tile |
| `ENDTURN_BLOCKING_UNIT_PROMOTION` | `state(what="unit", id, view="actions")` `.promotions`, then `order(to="unit", id, action="promote", args={promotion})`; `todo.promotions` lists the units |
| `ENDTURN_BLOCKING_RESEARCH`, `FREE_TECH` | `state(what="options", view="research")` then `order(to="empire", action="research", args={tech})` |
| `ENDTURN_BLOCKING_PRODUCTION` | `todo.cities`, then `state(what="city", id, view="production")` and `order(to="city", id, action="produce", args={item})` |
| `ENDTURN_BLOCKING_POLICY`, `FREE_POLICY` | `state(what="options", view="policies")` then `order(to="empire", action="policy", args={policy})` (a branch's POLICY_BRANCH_ id opens the branch) |
| `ENDTURN_BLOCKING_CHOOSE_IDEOLOGY` | `order(to="empire", action="ideology", args={branch})` with POLICY_BRANCH_FREEDOM, ORDER or AUTOCRACY; irreversible short of a revolution |
| `ENDTURN_BLOCKING_FOUND_PANTHEON` / `FOUND_RELIGION` / `ENHANCE_RELIGION` / `ADD_REFORMATION_BELIEF` | `state(what="options", view="beliefs", kind=...)`, then `order(to="empire", action="pantheon" / "religion" / "enhance_religion" / "reformation")` |
| `ENDTURN_BLOCKING_FAITH_GREAT_PERSON`, `FREE_ITEMS` | `question()` then `answer(choice=<UNIT_ id>)` |
| `ENDTURN_BLOCKING_STEAL_TECH` | `question()` then `answer(choice=<TECH_ id>, args={player_id})` |
| `ENDTURN_BLOCKING_LEAGUE_CALL_FOR_PROPOSALS` | `state(what="league")`, then `order(to="league", action="propose", args={resolution_type, choice})` or `action="repeal"` |
| `ENDTURN_BLOCKING_LEAGUE_CALL_FOR_VOTES`, `DIPLO_VOTE` | `state(what="league")` then `order(to="league", action="vote", args={votes})` |
| `ENDTURN_BLOCKING_CITY_RANGE_ATTACK` | `state(what="city", id, view="strikes")` then `order(to="city", id, action="strike", args={x, y})`, or `turn(action="end")` once you have decided not to |
| `ENDTURN_BLOCKING_CHOOSE_ARCHAEOLOGY` | `question()` then `answer(choice=<number>, args={x, y})` |
| `ENDTURN_BLOCKING_MAYA_LONG_COUNT` | `question()` then `answer(choice=<UNIT_ id>)` |
| `ENDTURN_BLOCKING_MINOR_QUEST` | a city-state quest popup; `turn(action="wait")` sweeps it |

`pending_popups` in the status lists open choice windows; the answer that resolves a popup clears it. A popup
that nothing answers: call `turn(action="wait")` again, then read the status. If it is still there after two
tries, stop and tell the human exactly what the status shows. A popup left open can stack with the next one
and become impossible to clear from the tools.

`blocking_stale: true` means the engine froze its blocker while a popup was up and the todo no longer shows
it: `ENDTURN_BLOCKING_UNITS` with no unit needing orders, `ENDTURN_BLOCKING_PRODUCTION` with no empty city,
`ENDTURN_BLOCKING_RESEARCH` with research set; the turn's end sweeps the popup, lets the engine re-evaluate
and sends once more.

## Leader screens and diplomacy

- When `discussion_pending` is true, `question()` gives the leader, their speech, the response buttons as
  `answers` rows and, on a trade screen, the deal. Answer with exactly one of `answer(choice=<button id>)`,
  `answer(choice="accept")`, `answer(choice="refuse")`, or `answer(choice="leave")` (only when there are no
  buttons and no deal). The gate's rows say which. Several leaders can be queued at one turn start (three at
  once has happened): the answer to one then carries `still_pending: true`, `next` (the next leader's screen,
  words, buttons, the deal) and the gate it raises, so answer that one next; no need to read the question
  again. Then `turn(action="wait")` (or carry on with the turn if it was already yours). Nothing else works
  while a leader screen is open.
- `state(what="civs")` for the overview of every civ you have met; `state(what="civ", id, view="summary")`
  before answering a demand or deciding on war, `view="war"` for what a war would cost.
- Trade: `state(what="civ", id, view="trade_catalog")` shows what each side may put up and why a row is
  grey, with the deal calls to copy; `order(to="civ", id, action="negotiate", args={items})` asks the AI what
  would work without committing; `order(to="civ", id, action="propose_deal", args={items})` proposes and
  reads the reply. To a human seat it sends the table, which that seat -- and no other -- reads as `question()`
  and answers with `answer(choice="accept")` or `"refuse"`; the answer names the other seat (`other`) and the
  items (`accepted_items` / `refused_items`). `action="demand"` is the leader screen's Demand button.
- War and peace: `order(to="civ", id, action="declare_war")`, `action="peace"` (with `items`),
  `action="denounce"`, `action="friendship"`; a declaration of friendship offered to you is
  `answer(choice="accept_friendship", args={"id": player})`. The AI rejects peace for about ten turns after a
  declaration; do not spam it.
- City-states: `state(what="city_state", id, view="summary")` for quests, tribute and protection, with the
  screen's buttons as rows (`order(to="city_state", id, action="pledge" / "bully_gold" / "make_peace" ...)`);
  `view="full"` adds the gifts, the bonuses and the units and tiles you may give; then
  `order(to="city_state", id, action="gift_gold", args={amount})` with one of the listed tiers. City-state ids
  are the `minor: true` rows of `state(what="civs")`.
- The league: during a session `state(what="league")` carries `votable` rows, each with a yes and a no vote
  to copy (`order(to="league", action="vote", ...)`). One vote call commits the whole delegation: put every
  proposal you vote on in the same `votes` list and split `num_votes` between them; a list that leaves
  delegates unassigned is refused unless `abstain: true` (they would abstain for good), and a second call in
  the same session is refused. Between sessions there is nothing to vote on and the
  proposal rows carry their `call` to propose or repeal instead.

## Rules of the house

- Save often: `session(action="save")` before ending the turn and after anything expensive (a city founded, a
  policy, a war). In a game with other people, do not load a save yourself; ask the human.
- Never call `lua`. It is off by default and a raw call has crashed the game before.
- On a connection error ("tunerd lost its connection", "connection refused", "No such file or
  directory"), the game or the bridge is down. Stop and report it; the human brings it back.
- Do not burn turns. If you are calling the same tool with the same arguments a third time, stop and report
  what you see.
- Play to win and be a good sport: the other seats can see your diplomacy, not your reasoning.

## Minimal first turn

```
turn(action="wait") -> state(what="empire") -> state(what="units") -> turn(action="briefing")
order(to="unit", id=settler, action="mission", args={"mission": "MISSION_FOUND"})   # on turn 0 the settler has moves; found on the spot or 1 tile over
order(to="unit", id=warrior, action="move", args={"x": x, "y": y})                   # explore
turn(action="status") -> order(to="empire", action="research", args={"tech": ...})
                      -> order(to="city", id=city, action="produce", args={"item": "UNIT_SCOUT" or "UNIT_WARRIOR"})
notebook(action="remember", args={"text": "Plan: scout, then settler at 3 pop; Pottery -> Writing", "tag": "plan"})
turn(action="status") (blocking clear?) -> turn(action="finish")
```
