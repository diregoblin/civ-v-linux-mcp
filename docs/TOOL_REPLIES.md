# Tool replies, key by key

Served by `reference(book="playbook", section=<heading>)` (the old tool name works too). Each section is the full description of one reply: the tool's own
description keeps what a turn needs (a client shows only its first couple of thousand characters) and points
here for the rest. The text below is the description as it stood before it was shortened (2026-09-27), kept
whole; extend it here when a reply gains a key.

## turn(action="finish")

The turn boundary as one call: end my turn, wait until it is my turn again, and return the new turn --
`status` (as turn(action="status"): todo, blocking_name + blocking_hint, popups), `digest` (as the briefing's digest: what
happened while I was away), `turn`, and `notes` (what I told the notebook since my last finish or
briefing; `notes_unshown` {count, more} counts the older ones, notebook(action="recall") has them all; notes="all" brings
the latest eight back). Progress notifications go out every few seconds while waiting. If the turn will
not end, ok=false and `end_turn` carries the refusal with the todo that blocks it: nothing is waited on.

`actions=[{tool, args}, ...]` runs those orders first, exactly as `do` would: in order, stopping at the first
refusal, each order's own `action_id` replaying on a retry. The turn is ended only when every order was ok.
`batch` is on the reply either way, with `do`'s shape (`done`, `results` [index, tool, result], `skipped`,
`hint`): on success beside the new turn, on a refusal beside the current `status` and `gate` with `ended:
false` and a `hint` -- read the results, re-check the state, and call again with the orders still wanted (or
none). An order that ran but left a blocker standing (a unit still needing orders) shows as a normal `end_turn`
refusal after the batch. Waiting, loading, the turn's end and the batch itself are refused inside the
list, as in `do`.

When the engine refuses the end because units still have movement (`end_turn.blocking` is
`ENDTURN_BLOCKING_UNITS`, `end_turn.todo.units` lists them), the refusal also carries `end_turn.skip_actions`:
one `{tool: "unit_mission", args: {unit_id, mission: "MISSION_SKIP"}}` per listed unit, ready to pass as the next
call's `actions` -- and `end_turn.hint` says so. A plain `end_turn` refusal carries the same two keys at top
level. A unit keeps the turn open while it has moves left after its order (a one-plot move, an attack): it can
still act, and the list is the set of decisions still open, not a list of units to skip. Skip the ones you mean
to leave; give the rest a real order.

A `stale_leader_view_cleared` event in the digest says the engine's End Turn was disabled by nothing on screen
-- the leader view an exit to the main menu left open into this game (GitLab #137) -- and the harness asked the
engine to leave it (UI.RequestLeaveLeader()) before the send; the turn ended as usual. session(action="main_menu")
itself leaves a leader on screen first and says `left_leader_view: true`.

Safe to repeat: when it is already not my turn (a client timeout cut the previous call, or an AI's question
was just answered) it only waits, it never ends a second turn. A turn that began while nothing of mine was
looking -- an AI's offer answered at the end of my turn, the round finishing during the answer, the next call
meeting the new turn cold (live t147, England) -- is handed back **unended**: `unseen_turn: true`,
`ended: false`, `woke_because: ["turn_unseen", ...what it needs]`, its `status` and `digest`, and a hint; play
it, then call again. With skip_quiet_turns such a turn passes when it is quiet; with `actions` none of them
runs (`batch.skipped`, they were meant for the turn before). Returns early with discussion_pending=true
(an AI wants an answer: question() then answer(choice=<button> / "accept" / "refuse" / "leave"),
then call this again) or tech_popup_pending=true (order(to="empire", action="research")), like turn(action="wait").

skip_quiet_turns=N: keep ending turns, up to N more, while nothing needs me -- no unit awaiting orders, no
empty city, no promotion, no popup, no blocker, no expiring city-state ally, and nothing eventful in the
digest (combat, losses, cities changing hands, wars, leaders talking, wonders, great people, religion,
espionage, congress, trade routes...). wake_on adds my own words to that list, matched case-insensitively
against event kinds and notification text (e.g. ["Machinery", "Pocatello"]). The digests of the skipped
turns are merged into the result and `turns_skipped` / `woke_because` say what happened. The harness never
issues an order on my behalf: cities keep building their queues and research continues, that is all.
`status.alerts` wakes the run only when it worsens against the previous turn this seat saw (happiness_drop,
unhappy:<tier>, strategic_deficit:<resource>, unit_supply:<deficit>): the same happiness 1 across a five-turn Circus does not, but the
alert is on every returned status regardless. `todo.ongoing` (automated units, standing moves) never wakes
the run by itself; a row's `attention` does (ongoing:<unit_id>:camp / hostile / destination_unrevealed ...):
an explorer simply exploring lets the run continue, one beside a visible camp or brute stops it.
`expiring_deals` / `expiring_friendships` wake it like an expiring city-state ally does.
`status.orders` (when I have conditional orders, see notebook(action="give_order")) says what each did at this turn start: rows
with `did`, `status`, `state`, `pause`; an order that paused, failed or completed wakes the run
(order:<id>:<status>), one simply walking or building does not. With briefing=true the top-level `orders`
keeps only each order's id, unit, status and `did`; its state (now, pause, steps) is in briefing.orders.

`digest.omitted` {count, turns [first, last], by_kind, hint} appears when more than 120 events had piled up
since the previous digest (a cursor that had not moved for many turns): the newest 120 are kept, the rest are
counted; state(what="notifications") still has every notice and turn(action="briefing", since="turn") this turn's events.

timed_out=true means the AIs (or the other human seat) are still moving after timeout_seconds; the reply is not a
refusal: `next` is the call that resumes the wait, and progress notifications ride on every wait every 5 s, so one
call with the default 600 s replaces several short ones (GitLab #160). In hotseat, when the turn
this call ended is over and the other human seat is on screen, the timeout answer carries the `digest` too
(the boundary has passed; it would otherwise wait for a call that never completes in a two-seat session).
Verified in Claude Code
(2026-09-25): a 420 s wait with progress every 5 s came back with the server's own timeout, not a client
cutoff (the client moves a call past 120 s to a background task and reports its result), so 600-1800 is
fine there; with a client that has a hard per-call limit, stay under it.

game_over=true (with woke_because ["game_over"] and the game_over gate) means the game ended while the AIs
moved: `victory` {winner, type, text, turn} is the game's own notification ("Catherine has won the game
through a Science Victory!") when the log holds one, and `hint` names session(action="main_menu"). The wait never
runs to its timeout on a finished game.

One client owns the turn: the turn's first order claims it for that process, and another client of the
same seat calling this gets ok=false with `turn_claim` (holder pid, how long it has held the turn, when
the claim expires) instead of ending a turn out from under it. The claim lapses 180 s after the holder's
latest order or when its process exits; force=true takes it over at once. A quiet-turn run claims each
turn it ends; if a second client acts on one first, the run stops and returns that turn
(woke_because other_client_holds_turn).

briefing=true hands the new turn back as `briefing` (see the briefing tool: decisions, changes, board,
threats, notes) in place of `status` and `digest`: the briefing counts and lists the same events from the
game's log, and turn(action="briefing", since="turn", limit=50) repeats every one of them. When the turn comes back behind
a gate (a discussion, a timeout, another seat) only the gate is briefed and `status` / `digest` stay as
usual.

## turn(action="briefing")

My turn in one compact read, for deciding (and for recovering after a context reset): what I must do,
what changed, and what the board looks like. Keys:
`seat`, `turn`, `gate` (as the status; while one is up only the gate comes back, `withheld` says so).
`baseline`: what the changes compare against -- {comparable, turn, turns_ago, events_since} after an
earlier briefing of this game and seat; comparable=false with `reason` on the first briefing, or when the
last one was on a later turn (a save was loaded). The baseline is kept beside my notebook, so a new
session still compares against the last briefing, and every briefing replaces it.
`decisions`: every mandatory item, never cut -- units needing orders (id, type, x, y, moves), promotions,
cities with nothing to build, research unset, an incoming deal, a spy's stolen tech, decision popups, and the
blocker when it is none of those -- each with `actions`: the `{tool, args}` rows that clear it, exactly as
`batch(actions=[...])` and `turn(action="finish", actions=[...])` take them -- the read first (run it as is), then the order;
a row carrying `choose` names the arguments still to pick from that read's reply
(`{"tool": "set_production", "args": {"city_id": 7}, "choose": ["item"]}`). A unit's one row is its
`state(what="units", view="actions", detail="summary")` read, whose unit rows carry the unit's own orders. `decisions_total` counts
them. `tools` (kind -> one sentence naming the tools) is the pre-2.0.0 form, kept one release beside the rows;
`tools_note` says so.
`warnings`: facts that do not block the turn (status alerts, expiring deals / friendships / city-state
allies, and the wars I am in: one `at_war` row per major civ {civ, leader, player_id, peace_possible, and either
the peace hint or `peace_note` / `locked_turns` from the Negotiate Peace button}, plus one
`at_war_city_states` row {count, civs}). `opportunities`: optional -- idle caravans and spies (each with
`actions` rows like a decision's), free trade-route slots.
`changes`: since the baseline -- `empire` totals {was, now}, `cities` (new, gone, pop, production: the item
a city was building left its queue), `units` (new, gone), `territory` (only when a plot changed hands:
`plots` {was, now}, `lost` -- every plot mine at the baseline and not now, each with who holds it now, the
improvement and resource on it; a neighbour's Citadel or a city lost, the map's border change -- and
`gained`, capped at `limit`), and `events` {total, by_kind, items} from the
game's event log. The briefing reads that log with its own cursor, so it never takes events away from
the digest, and they never take them from it.
`empire`: the overview totals. `cities`: {total, rows} -- only cities worth a look (no production,
completes or grows next turn, starving, damaged, razing) with `why`. `units`: {total, by_type, ongoing,
attention (ongoing units beside a camp or hostile), damaged}. `threats`: visible hostile combat units within
4 plots of a city or 2 of a unit, nearest first: id, unit, hp, x, y (owner when not barbarian), `near`
{unit, unit_d, city, city_d} and an `assessment` that is distance only (no combat odds); one my previous
briefing listed is marked `seen` and, unless it moved (`moved_from`), carries only its position, hp and
`d` (plots to my nearest unit or city); detail="full" gives every field of every row. Plus revealed
barbarian `camps` within 4 plots of a city. `civ_rules`: my leader's trait text (Venice cannot found
cities; ...), included when there is no comparable baseline or since="turn".
`notes`: my notebook entries written since my last briefing or finish (notes="new"), with
`notes_unshown` {count, more} for the rest -- notebook(action="recall") has every note; notes="all" is the latest `limit`
of them; the default "auto" is "all" with since="turn" and "new" otherwise. A note marked `adopted` (`notes_adopted` says
why) came from the notebook this seat kept before the game had its own key (GitLab #168): trust the board, then rewrite or
forget it. `assignments` (only when I have active ones; see assign):
{active, by_state, rows} -- condition_met and needs_review first, each with purpose, state, reasons or
evidence, its units / cities as they are now and the target as observed; a unit_orders decision whose unit
is assigned carries `assignment` {id, role}. One more game read when there are any.
`orders` (only when I have open conditional orders; see notebook(action="give_order")): {open, paused, rows} -- paused first, each
with its unit, `now` (the current step), `state` and `pause` (kind, reason, hint); a unit_orders decision whose
unit has one carries `order` {id, status, reason}. Read from the notebook: no game read. An assignment or order taken
over from that older notebook reads needs_review / paused with kind `adopted` until I amend, close, resume or cancel it.
Size: every list except `decisions` stops at `limit` (default 8, max 50) with `omitted` and `more` naming the
tool that shows the rest. since="turn" lists every event after my previous turn ended (use it after a
context reset, or with a larger limit to see events a short briefing left out); the default lists those
since my previous briefing. Five game reads; nothing another seat can see is read.

## turn(action="status")

Whose turn it is, current turn number, whether it is my turn, what blocks ending it,
and whether a greeting/discussion/tech/great-person screen is up (those are not in pending_popups).
todo.steal_tech is a pending spy-steal chooser even when blocking_name is something else
(the engine reports one blocker at a time; a human still sees the Steal Technology notice).
While a leader screen is up (leader_greeting_pending / discussion_pending) the game freezes blocking_name
and todo: read it with question(), close a plain greeting with answer(choice="leave"), then look again.
From the main menu (no game loaded) reports {"ingame": false, "screen": ...} instead: use session(action="load_latest")
/ session(action="load", args={filename}) to get back into a game. `seat` is the player this server plays.
`alerts` is a short list of facts about my own empire that do not block the turn and are not in todo, copied
from the same reads as overview: {kind: "happiness", happiness, unhappy} when the total is 2 or below or an
unhappy tier (unhappy / very_unhappy / super_unhappy) is set, and {kind: "strategic_deficit", resource,
available, deficit, total, used} for each revealed strategic resource with a negative available count, and
{kind: "unit_supply", deficit, cap, used, production_penalty} while the empire is over its unit supply cap
(the top bar's own string: the engine's deficit counts military units, so 15 units of 14 supplied with no
penalty is not a row). `happiness` (the bare total) rides on every status. Empty means neither applies; a happy empire with spare
iron has []. No advice is attached: which building or trade would change the number is a different read.
`todo.ongoing` lists my units the game is already moving -- automated (AUTOMATE_EXPLORE / AUTOMATE_BUILD) or
walking a move that needs more turns -- with id, type, x, y, moves, hp, `automated`, `mission_name`
and `going_to: {x, y}` when a destination is stored. They never block end_turn and are not decisions; a new
a move or mission order takes an automated unit back. `attention` on a row names what a human would look at:
a visible barbarian camp on or beside the unit, a visible hostile combat unit beside it, a destination no
longer revealed or passable. Absent when nothing is ongoing.
`expiring_deals` lists my deals with a major civ ending within 3 turns: {player_id, civ (only once met),
turns_left, ends_on, reoffer_on, items: ["we give GOLD_PER_TURN 1", "they give ALLOW_EMBASSY", ...]} -- the rows
the deals screen prints; `reoffer_on` (ends_on + 1) is the first turn a proposal may renew a resource, open
borders, a research agreement or a defensive pact it carries (refused as not legal before; gold per turn is
not gated). It is left off while the trade table holds an offer or a draft (the snapshot never
clears one) and while another seat's proposal waits. `expiring_friendships` lists declarations of
friendship ending within 5 turns: {player_id, civ, turns_left, ask_too_soon when the leader screen greys
out the renewal}; order(to="civ", action="friendship") renews one. Both are read on my own turn only and absent when empty.
`wars` (own turn only, absent when at peace with everyone) is every war I am in: `majors` [{player_id, civ,
leader, peace: {ok, locked_turns, note}}] -- `peace` is the leader screen's Negotiate Peace gate
(CanChangeWarPeace, the turns still locked into war; `ok` true means order(to="civ", id, action="peace") can be asked now,
the trade catalog's `peace` adds the deal's own answer) -- and `minors` [{player_id, civ}] (their peace is
order(to="city_state", id, action="make_peace"); a peace with their ally's civ takes them along).
`gate` is the one thing to read first: null means act freely; otherwise it names what must happen before
any action works (not your turn, your hand-off screen, a paused engine, a leader screen, a decision popup...)
and `clear_with` is the call that does it; `actions` are the same as rows for `batch(actions=[...])` -- the read
first (`read_first`), then the call that clears it with its `args`, a row carrying `choose` naming the arguments
still to pick from that read, then the alternatives. Every refusal carries the same object. A question-shaped read
(`question()`, whatever is asked) carries `answers`: one complete row per button
or choice it offers.
`other_clients` (absent when none) lists the other live MCP servers of this seat attached to this game --
{pid, client (its label), attached_for_s, last_call_s, code_behind} -- with `other_clients_note`: an idle one is
harmless, two playing contend for the turn (`turn_claim`). `server_outdated` (absent while this server runs the
code on disk) says the harness's Python changed after this server started: {files_changed, newest,
running_for_s, note} -- its tool listing and behaviour are the older code's until the client restarts its MCP
server (Claude Code: /mcp reconnect). Both ride on the `status` of turn(action="finish") too.

## state(what="empire")

My empire at a glance: gold, science, culture, happiness, research, era, counts, turn/year, and
`strategic_resources` (revealed ones only) with `available` spare copies -- negative means a deficit:
units/buildings consume more than the empire owns and they fight/produce at a penalty.
`luxuries` is every revealed luxury with owned/imported/exported copies (`last_copy` if selling it
would drop the happiness bonus). `bonus_resources` is the resource list's bonus stack (Wheat,
Cattle, and the rest): a row only when the empire's total is above zero or some is exported.
A revealed strategic also carries `used` when the resource list would print that column.
`happiness_breakdown` / `gold_breakdown` / `science_breakdown` /
`culture_breakdown` / `tourism_breakdown` / `faith_breakdown` are the top-bar tooltips.
`happiness_breakdown` also carries the Happiness screen's expandable rows: `happiness.by_luxury`
(each luxury's happiness, not its copy count), `extra_per_luxury`, `league`, `difficulty`
(the residual the screen labels "from Difficulty Level"), `cities` (building happiness, local
happiness, connection happiness, unhappiness, and whether the city is occupied), and
`unhappiness.tooltips` (the Number of Cities / Citizens hovers). `unhappy` is unhappy /
very_unhappy / super_unhappy, and `penalties` are the red sentences on the tooltip.
`gold_breakdown.expenses.unit_paid` / `unit_free` / `unit_cost_per` is the Economic Overview
unit-maintenance tooltip (gold per paid unit). `unit_supply` is the Military Overview header
(cap from handicap/cities/population, remaining or deficit + production_penalty when over).
`score_breakdown` is the diplo-list / Victory Progress score tooltip (cities, pop, land, wonders,
techs, policies, great works, religion). `golden_age_progress` / `golden_age_threshold` are the
meter toward the next golden age.
trade_routes_used counts caravans/cargo ships alive, not running routes: `idle_trade_units` lists the ones sitting
without a route (give them one with state(what="options", view="trade_routes", id) + order(to="unit", id, action="trade_route")). `trade_units_queued` is the
ones in any city's queue; the engine trains none once used + queued reaches trade_routes_available, so
`free_trade_route_slots` = available - used - queued and `trade_note` says what to route and what to build.
`idle_spies` lists unassigned spies the same way (state(what="options", view="spy_cities", id) + order(to="spy", id, action="move")).
An idle trade unit carries `in_city` (its city, or false in the field) plus the nearest city to walk
it to: only one standing in a city of mine can be given a route at all.

## state(what="unit", view="tactical")

How to read the tactical view's `grid`, `move`, `vis`, `sight` and `fog`:

- **grid**: each cell is two letters, terrain then occupant; rows run north (top) to south, the number is y;
  odd rows sit half a cell to the right (Civ V's offset hexes), so a cell's neighbours are the two beside it and
  the two touching it in the rows above and below; `cols` is each column's x (-1 = off the map; a wrapped map
  repeats x); a blank cell (two spaces) is off the map or farther than `radius`, the same plots `occupants` and
  `fog` cover. Terrain: M mountain/impassable, ~ water, H hills, F forest/jungle/marsh, . open, _ unrevealed.
  Occupant: @ this unit, X hostile unit or city, C city, u your unit, o another player's unit, ? fogged (last
  seen, may hide units), blank = seen, empty.
- **move**: what `order(to="unit", action="move")` does with a one-step order there: `attack` = a melee attack
  (preview in `targets`); `open` = the order is sent (no path cost or turns are estimated; the engine's pathing
  decides); `refused` = the order refuses it, `why` says why; `enemy` = a visible enemy you cannot melee. Every
  open or attack neighbour carries `call`, the move order ready to copy.
- **vis**: `visible` = in sight now; `fogged` = last seen, occupants unknown; `unrevealed` = never seen.
- **sight**: `unit.sight` is what this unit itself sees (the engine's canSeePlot: high ground adds a plot, hills
  and forest in between block); `unit.fire_los` the same test with a ranged unit's attack range, which a ranged
  attack must pass; `in_sight` / `in_fire_los` on occupant and city rows; `radius_from = sight` means the view
  was sized to that reach.
- **fog**: fogged and unrevealed plots can hold units that are not shown: a plot is never reported safe.

This text rides on a server session's first tactical reply as `legend`; every reply after carries a one-line `key`
that names this section (GitLab #152: a seat paid two thousand characters of legend on every move check).

## state(what="compare")

Your candidates side by side in one read, for a decision you are weighing; the facts, never a pick.
kind="production": city_id + candidates (up to 8 UNIT_/BUILDING_/PROJECT_/PROCESS_ types, e.g. from
state(what="city", id, view="production")): can_produce (or `why` not: missing tech or building, resource, civ restriction, puppet;
why_unknown=true when no rule was found), cost, stored, turns, gold/faith price with *_can_buy and *_short
(treasury gap), effects (strength or flat / per-pop / percent yields, happiness, slots), conditional (per-tile
yields with how many of this city's tiles qualify, worked or not), estimated_change (city yields; the formula
is in assumptions), maintenance (unit upkeep is empire-wide, so a unit's is "unknown"), unique_replaces; a
Venice puppet is purchase_only.
kind="research": candidates = up to 8 TECH_ types: status (researched / current / available / locked /
never), cost, progress, turns (available ones), missing_prereqs, path_beakers and path_turns_estimate for a
locked one, unlocks.
kind="improvements": unit_id (a worker) + optional plots ([[x, y], ...], default: plots within 2 you own or
with a resource) + optional candidates (BUILD_ types; default: every legal build but roads and forts): per plot
yields_now, worked, city; per build legal (or why), turns (work only; the walk is not included), tile_change,
empire_change only when a city works the tile, removes / chop_production, connects (a resource), maintenance.
Fogged plots are not read. sort= a yield (largest tile gain first) or "turns".
kind="trade": unit_id (a caravan or cargo ship in a city): every destination with what each end receives,
distance, and hazard (visible hostiles and camps near the destination, not_visible plot count, danger =
visible_threat / none_visible -- never "safe": the path is unknown before the route is set). sort= gold,
science, food, production, *_them or distance.
Every answer has context (seat, turn, city/unit), sources (where each field comes from), assumptions (behind
every estimate), n / returned, and `omitted` with the arguments that fetch the rest (`limit`, 1-20).
detail="full" adds help text (production) and the chooser's hover breakdown (trade).

## order(to="civ", action="propose_deal")

Offer a trade to another civ. With an AI: drives the game's real leader/trade screens (the only
crash-free path; headless deal building crashes the engine), proposes, reads the reply, closes the
screens and reports measured `effects` (gold, gold/turn, happiness, deal count, per-resource
import/export before vs after) -- so there is nothing to poll afterwards. With another human seat:
builds the same table on the PvP deal screen and sends it (`pvp: true`, `pending: true`); that seat
sees it as the status's pending_deal_from / question() on its turn and answers with answer(choice="accept") or
"refuse", after which both seats' deals screens agree. No other seat sees it: the trade table every hotseat
seat shares keeps a sent proposal on it, and a table this seat is no party to reads as empty. The answer's
reply is {ok, other: the proposing seat, accepted_items / refused_items: the rows answered}; a refuse of a
proposal whose items did not load carries `unread: true` and a note naming the seat. Lump-sum gold is legal only under a
Declaration of Friendship with that civ (a Brave New World rule, human or AI alike; the trade catalog's
`gold.note` says so); gold per turn is not gated (given income).
items: [{"type":"RESOURCES","resource":"RESOURCE_DYE","from_us":true,"amount":1},
        {"type":"RESOURCES","resource":"RESOURCE_SPICES","from_us":false,"amount":1}]
Types: GOLD / GOLD_PER_TURN (amount), RESOURCES (resource, amount), OPEN_BORDERS, ALLOW_EMBASSY,
DEFENSIVE_PACT, RESEARCH_AGREEMENT, TRADE_AGREEMENT (one item, either side: the screen places the pair, a row
from each side, in one press -- a second item of the type is skipped; live t196 it had doubled the deal and its
gold cost), CITIES (city_id),
VOTE_COMMITMENT (resolution_id, choice_id, repeal: a World Congress vote pledge; the side's whole core
vote goes on the table, as the screen's pocket does -- pick from the trade catalog's vote_commitments),
THIRD_PARTY_WAR / THIRD_PARTY_PEACE (other: player id; the side declares war on / makes peace with that
civ or city-state when the deal is accepted -- pick an `ok` row from the trade catalog's third_party).
PEACE_TREATY (no fields): at war every table carries the treaty on both sides (the screens seed it), so any
A proposal while at war is a peace deal with terms; refused with the leader screen's reason while locked
into war -- see the trade catalog's `peace`, or order(to="civ", id, action="peace", args={items}).
Use state(what="civ", id, view="trade_catalog") first to see what is legal, how much gold / gold-per-turn each side can put
up, and which cities (`cities.us` / `cities.them`) the game allows trading -- capitals never are.
Refuses -- without opening any screen -- an amount that is not a positive whole number or exceeds what
that side has, and a city_id outside the catalog's cities; refuses -- without proposing -- if any item
does not land on the table at the requested amount (e.g. they own none of that resource).
ask_counter=true: on rejection also returns the AI's own counter-offer (`counter.items`) which can be
passed straight back into the proposal. Duration of timed items is the game's deal length (30 turns).

## notebook(action="give_order")

Give one of my units a short sequence of steps that the harness carries out over the coming turns, so a
plan already chosen does not cost a call every turn. steps (at most 6, in order):
{kind: "move", x, y} -- walk there (a move; multi-turn); {kind: "build", build: "FARM"} -- build it on
the plot the previous move ends on (or where the unit stands; x, y to name another); {kind: "heal", hp: 80}
-- heal until hp is at least that percent (default 100); {kind: "hold", mission: "fortify"|"sleep"|"alert"}
-- the last step. Example: move to (12,8), then build FARM; or heal to 80, move to (30,14), hold.
The order runs now (start=true) as far as it can, then again at the start of each of my turns (the result
of the finish / wait carries `orders`): each step is issued through the move and mission orders,
at most once per turn, after the checks below.
It pauses and hands the unit back -- with `pause.reason` and `hint` -- instead of taking another step when:
a hostile comes into sight within interrupt.hostile_within plots (default 2; 0 = off; those in sight now
are acknowledged), the unit was damaged (interrupt.damaged, default true), hp is below interrupt.hp_below
percent (off by default, never during a heal), an enemy stands on the destination (an order never attacks),
a move would refuse the destination, a step is refused, the unit is not where a build needs it, the unit
makes no progress for a turn, a save was loaded, or I give that unit a direct order (a move or
mission takes it back). A lost or replaced unit fails the order. An order never declares war, attacks,
ends the turn or touches any other unit. A unit on automation (AUTOMATE_BUILD / AUTOMATE_EXPLORE) leaves it the moment its order is stored, even when no step could run yet (`automation_stopped`), so the game never walks it away first. One open order per unit: replace_id replaces one (a new unit id
after an upgrade too). A first step that cannot run now refuses the order and stores nothing. Stored in my
notebook, so orders survive a restart; the briefing lists them.
