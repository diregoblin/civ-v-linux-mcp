# Agentic MCP tools for Sid Meiers Civilization 5: Brave New World

> **Give your agent a civilization. See what survives.**

![Civilization V armies gathering across a river and contested border, official game screenshot](https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/8930/ss_84ee7ab3b0148a260359f8d5a78a2ab9033aa695.1920x1080.jpg)

*Game image from [Civilization V on Steam](https://store.steampowered.com/app/8930/Sid_Meiers_Civilization_V/).*

[![civ-v-llm-harness MCP server – quality and maintenance score on Glama](https://glama.ai/mcp/servers/ty-meador/civ-v-linux-mcp/badges/card.svg)](https://glama.ai/mcp/servers/ty-meador/civ-v-linux-mcp)

# Built for agentic play

A rival settles the river first. Your peaceful science plan now has a border problem. The agent in that seat
sees the same fogged map you would, knows only the civilizations it has met, and has to decide anyway.

This harness puts an AI agent in a real seat in **Sid Meier's Civilization V**. You own the game, you
host the table, and the agent takes a *human* seat: across from you in hotseat or over LAN, in your chair
against the game's AI, or beside other agents in one match. It plays by the same rules as everyone else at
the table and sees no more than you would.


> **Ready to play?** Give an LLM of your choice the [agent install guide](docs/AGENT_INSTALL.md) and ask it
> to set up the harness and start a game. The guide has the commands and checks; this page is for you.
> [Give your agent the raw guide](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/raw/main/docs/AGENT_INSTALL.md).

| Requirements | Current release | Ways to play |
| --- | --- | --- |
| Native Linux Steam build, Brave New World | **2.10.0** · Lua runtime **v328** | Solo · hotseat · LAN · multi-LLM |

## On this page

- **Before you start**
  - [What you need](#what-you-need)
  - [Fair play](#fair-play)
  - [Built for how an agentic model plays](#built-for-how-a-model-plays)
- **At the table**
  - [What a game looks like](#what-a-game-looks-like)
  - [What to expect](#what-to-expect)
  - [Ways to play](#ways-to-play)
- **Under the hood**
  - [How it works](#how-it-works)
  - [Honest limits](#honest-limits)
  - [Documentation](#documentation)
  - [Development](#development)
  - [Authorship](#authorship)
  - [License](#license)

## What you need

| | |
|---|---|
| **The game** | Sid Meier's Civilization V with Brave New World on your own Steam account, as the native Linux build. Steam downloads it once you turn Proton off for the game. |
| **A Linux desktop** | x86_64 with a display. The game runs in a normal window on your screen. A Steam Deck works ([`docs/DECK_HOWTO.md`](docs/DECK_HOWTO.md)). |
| **An agent that speaks MCP** | Claude Code, Codex CLI or any other MCP client, with whatever agent and budget you give it. Each agent at the table gets its own server. |
| **Python 3.11 or newer** | No compiler and no `uv` needed. |

Setup is one sitting, and your agent does it. Hand it the install guide and it works through the checks,
telling you exactly when it needs a click from you in Steam (switch the game off Proton, enable the tuner
in the game's config). The game itself takes about two minutes to cold start.

## Fair play

The agent sits in a human seat and gets a human's information, nothing more. That is the whole design.

- **Fog of war is fog.** Fogged tiles carry no live units. Unexplored land is a frontier the agent has to go
  and look at, not a list of unknown tiles to plan over.
- **Unmet civilizations do not exist** until the agent meets them. The AI's private plans stay private.
- **Diplomacy goes through the game's own screens.** Deals, demands, peace terms, friendship, denouncement
  and leader conversations are the same ones the AI offers you, with the AI's actual replies. Trades between
  you and the agent work in hotseat and LAN.
- **A seat is bound to its channel.** With a seat table on the daemon (`--seats`), each connection is bound to
  one seat by a token or by its OS user, the daemon writes that seat into every call itself, and a server started
  for another seat, a seat change onto it, or any raw Lua is refused. Two agents in one hotseat see only their own
  seat (`docs/AGENT_INSTALL.md`, "Two agents, one game").
- **Refusals mirror the UI.** If the game would not let you click it, the harness refuses it and says why.
  Every screen, hover and refusal reason a human reads is what the agent reads.
- **No back door.** The raw Lua escape hatch is off unless you turn it on.
  [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) lists what is withheld and why, each item checked against the
  engine.
- **The whole game.** Units, cities, research, policies, religion, espionage, World Congress, trade routes,
  archaeology, ideology, great works, city-states and the spaceship. No shortcut to a victory.

## Built for how a model plays

The world reaches the agent as text shaped to its way of thinking, so it spends tokens on decisions rather
than on scrolling. That is what keeps a turn affordable and the game moving while you wait for it.

- **Tiles as text, at the coordinates the move tools take.** Every revealed tile comes back as terrain,
  yields, resources, what a worker could build there and who is standing on it.
- **The rules once, not on every row.** `reference` is every unit, building, tech, policy, promotion,
  belief and terrain with its effect text, read once from the game's database (mods included). Lists carry
  names and live numbers only, so no hover is paid for twice.
- **One call per turn.** `turn(action="finish")` ends the turn, waits, and comes back with the new turn's status, what
  happened in between, and the agent's own notes. `briefing` folds a whole turn into one compact read:
  about 2.5 KB for a 38-unit empire where the separate reads are 30 KB.
- **It sleeps through quiet turns, by its own choice.** With `skip_quiet_turns` the agent asks to be left
  alone until something a human would look up for: combat of its own, a leader at the door with a decision, an
  empty city, happiness falling out of the comfortable band, a deal in its last turns (once), a threat beside a
  unit on the move. Other players' wars, alliances, denouncements and quests, a splash the harness already
  swept and a leader's plain remark are quiet. The agent picks how many turns to let pass; the harness only
  ever wakes it early.
- **Standing orders.** `notebook(action="give_order")` hands a unit a short plan (walk there, build a farm; heal to 80%, go
  back, fortify) that runs itself at the start of each turn through the ordinary move tools. The moment
  anything unplanned happens it pauses and hands the unit back with a reason. It never attacks, declares war
  or ends the turn on its own.
- **Assignments and a notebook that survive amnesia.** `assign` gives a unit or city a role, a target and a
  done-when, and every briefing re-checks it against what the seat can see now. `remember` / `recall` keep
  the plan, threats and promises beside the game. Both outlive a context reset, so a model that forgets
  everything mid-game picks its own plan back up.
- **It looks before it leaps.** the tactical view (`state(what="unit", id, view="tactical")`) is a unit's six neighbours with what a move would do there
  (attack, open, refused with why, enemy). `compare` lays out a few production, research or worker options
  side by side with costs, turns and effects (a building already in the queue reads as queued, not refused).
  Neither picks for the agent.
- **Batches and safe retries.** `batch(actions=[...])` runs a list of orders and stops at the first refusal. An `action_id`
  makes a retried call a replay, never a second move.
- **A refusal says what to do instead.** A mission name the engine does not have comes back with the
  nearest real ones and the unit's legal orders; a sleep where the unit can fortify names the equivalent; an
  end refused for units with movement left carries the exact skip orders for the next finish; a greyed
  button, a refused purchase, peace or ranged attack carries the engine's own sentence; a melee attack the
  engine drops without a word is named as a refused attack with the first closed gate the harness can read,
  not as an occupied plot. A refused building names the rule from the game's own table (a Windmill off flat
  land, Big Ben without Commerce, a resource the city lacks); a refused ideology tenet names its level gate, an
  unknown policy name comes back with the real names behind the shown ones, and a Great Prophet that has
  spread its religion is told that is what keeps it from a Holy Site. Every refusal is a next step, never a
  dead end.
- **A Great Person's withheld missions are explained.** `state(what="unit", id, view="actions").missing` says why
  the engine greys a mission out: the Great Work slot census (filled / total, the buildings that carry one), the
  nearest plot where a concert tour or a trade mission plays, no moves left. A concert tour's reply says the
  tourism and who received it; a gift row names the city-state whose plot the unit stands on.
- **It knows when it has won, and when it has lost.** The last spaceship part's reply says `game_over` and
  `victory: "science"`, the spaceship screen reads `complete`, and the `game_over` gate names `session(action="main_menu")`;
  the engine's own end-turn blocker freezes at that moment and is not the read to trust. A capital taken ends
  with `defeat`: the last city, where it stood and who took it.
- **A turn is one call when nothing needs a look.** `turn(action="finish", actions=[...])` runs the closing orders
  and ends the turn together, ending nothing if an order is refused; a move's result carries `revealed`, what
  the move showed, so "move the scout and see" needs no second read.
- **It says what a human sees on the leader screen and on the map.** Every war the seat is in comes with the
  Negotiate Peace gate (`wars`, the briefing's `at_war` rows: peace can be asked now, or why not) -- an
  agent sat twenty turns in a siege that one white-peace offer ended. A unit the engine moved while the others
  played is a `unit_displaced` event with where it went and what shares the tile it left. A frontier plot a
  foreign unit or city stands on says `occupied`, names the city, and stays in the reply however long the
  frontier is. A neighbour's Great General taking land is named with the plots it took, not just the headline.
  A turn no wait of ours opened still gets its turn-start work before its first order, and a turn
  that began while a leader screen was being answered is handed back unended with what it needs, never ended
  blind.
- **You can watch the seats think.** `python -m harness.spectator --ledger logs/calls.jsonl` serves a page
  (a canvas map that stays at the frame on Huge maps, d3 for the zoom and the panels) where every plot a tool
  reply handed a model pulses in that seat's colour over a greyscale map, acts stay
  painted until the turn ends, the last seat's footprint ghosts through the next, and an Observer / Seat N switch
  cuts between the unfogged world and what one seat's replies contained. A seat view draws only what that
  seat's screen shows: never-seen plots black, fogged plots dimmed, other players' units only where visible.
  Read-only, records and replays with a scrubber (play/pause, speed, a slider whose ticks are the turn
  boundaries), and reads the game only when the world moves (`docs/VISUALIZATION.md`).

<details>
<summary>The fine print: measurements and edge cases</summary>

- **`briefing` measured live.** Over four hotseat turns played both ways (`docs/NOTES.md`): 4.25 calls a turn
  against 8 with the separate reads, no refused order against two, about the same bytes.
- **The tactical view never guesses.** Adjacency and map wrap come from the engine. One step's cost and the
  zone of control that ends it follow the engine's movement rules on the plots as seen; no turns-to-reach,
  which the engine cannot give safely. Nothing fogged is called safe.
- **`compare` keeps a tile's own gain apart from the empire's** (nothing until a city works it) and never
  calls a trade destination safe under fog.
- **A trade unit's second gate.** Past the slot count the engine asks whether some city of yours can start a
  new route of that kind now; when it cannot, the briefing, `compare` and a refused production order quote the
  engine's own sentence ("no available sea trade routes") instead of offering to build or buy.
- **What an assignment review can report.** `on_track`, `condition_met`, or `needs_review` with the
  observation behind it: a unit gone (an upgrade on its last plot is named; a unit our own order used up -- a
  Great Work written, a religion's last spread, a gift to a city-state -- is `unit_spent` with the reason, a
  plundered caravan says plundered; our own upgrade order carries the assignments and the open order onto the
  new id by itself), a reused id never followed, a
  city lost, a settle site now too close to a city, or a target out of sight kept as last seen, never assumed
  gone. `notebook(action="amend")` and `notebook(action="close")` do the rest.
- **What pauses a standing order.** A hostile in sight, damage, an enemy on the destination, a refused step,
  no progress, or a direct command to that unit.
- **What wakes `skip_quiet_turns`.** Combat of our own, a leader message that asks something, an empty city,
  a happiness drop out of the comfortable band (or five at once), a deal in its last turns (once), a new
  strategic-resource shortfall, or a barbarian camp or hostile unit beside a unit on its way somewhere. A
  caller's `wake_on` words always wake; a fight between other players, their alliances, denouncements and
  quests, and a splash the harness swept never do.
- **After a context reset**, a briefing carries the latest notes again and every assignment is re-checked.

</details>

## What a game looks like

the agent plays through tool calls; you watch the game window. On its turn it checks what changed, inspects
its cities and units, chooses actions the game permits, then ends the turn. In hotseat the window passes
back to you and you take your turn as usual. Nine tools -- `turn`, `state`, `order`, `question`,
`answer`, `notebook`, `batch`, `session`, `reference` -- and the loop is four lines:

```
turn(action="finish")                      -> the new turn: status, digest, notes; read `gate` first
question() -> answer(choice)               -> whatever the game asks, from its own `answers` rows
state(what="units", view="actions") ...  -> every reply that lists what can be done carries the order to copy
order(to="unit", id, action="move", args)  -> then notebook(action="remember") and turn(action="finish") again
```

When something blocks the turn, the status names it and hands back the rows that clear it. Refused orders
explain why, the shape they should have had, and an example. The 145 one-tool-per-button names of the 1.x
releases still answer, each reply naming the call to copy instead.

<details>
<summary>A real turn status from a live solo game</summary>

Turn 269, trimmed for width. It predates runtime v217; a status now also names the `seat`, carries the
`gate` to clear first, `happiness` and any `alerts`, and lists automated or already-moving units under
`todo.ongoing`:

```json
{"turn": 269, "my_turn": true, "mode": "single", "blocking_name": "NO_ENDTURN_BLOCKING_TYPE",
 "todo": {"promotions": [], "research_unset": false, "cities": [], "units": []},
 "pending_popups": [], "game_over": false, "notifications": {"live": 2, "held": 99}}
```

</details>

## What to expect

- **It is slow and it costs tokens.** A developed empire means dozens of tool calls per turn. A game to
  victory is a long project; an evening is a few dozen turns. Quiet-turn skipping and standing orders are
  what keep that bill down.
- **Leave the window alone during the agent's turn.** It drives the game's own screens the way a mouse
  would, and a stray click from you lands in its turn.
- **The game crashes sometimes.** The Linux port does, with or without the harness. Quick saves every turn
  in solo (`session(action="save")` is one call elsewhere), the game's own autosaves and `session(action="load_latest")` make it a pause,
  not a loss. A supervisor can relaunch the game and rejoin a LAN game on its own.
- **You can read its mind.** Every note the agent writes to itself and every assignment it gives a unit is
  a plain JSON file under `~/.local/share/civ5-harness/notes/`, per game and seat. You can see what it
  planned before you find out whether it worked.

## Ways to play

| Mode | Who is where | Start it with |
|---|---|---|
| Solo | LLM in seat 0 versus the game's AI | `harness.cli start-single --civ CIVILIZATION_ROME` |
| Hotseat | You and the LLM(s) at one machine, turn by turn | `harness.cli host-hotseat --humans 0 1 --nick 1=Claude` |
| LAN | Each LLM runs its own game instance and joins like any player | `scripts/launch_llm_client.sh`, then `harness.cli join-lan <host>` |

All three share the same tools. Several agents in one game each get their own MCP server, one per seat;
every status names the seat it is playing, and `session(action="seat")` moves a server to another human seat without a
restart. The agent cannot take over one of the built-in AI seats; the game does not expose that. To move a
two-seat hotseat game along between sessions, `scripts/hotseat_rounds.py` alternates the seats and stops at
the first turn that needs a decision.

The install guide walks through each mode. Saved states in `saves/` reproduce late-game diplomacy, peace
terms, Venice puppets and a combat lab if you want to drop a model into something interesting on turn one.

## How it works

```mermaid
flowchart LR
    A["LLM client"] -->|stdio| B["MCP server<br/>nine tools"]
    B -->|Unix socket| C["tunerd<br/>one tuner connection"]
    C -->|TCP 4318| D["Civilization V<br/>preload shim + FireTuner"]
```

Civilization V ships a debugging channel, FireTuner, that is a remote Lua console into the game's own UI
contexts. The harness keeps that channel open in multiplayer with a small preload shim, injects a Lua
runtime that ports the stock UI's own logic (combat previews, trade legality, hovers), and drives every
screen the way a mouse would. Because the network only carries player commands in a lockstep simulation, a
real game instance is the only faithful client; that is why the LLM gets one. `docs/ARCHITECTURE.md` has
the long version.

## Honest limits

- Linux only, native Steam build only, Brave New World only. No Windows, no macOS, no Proton.
- With the tuner enabled the game listens on every interface by default. The install guide binds it to
  loopback; do not skip that on a shared network.
- A blocker the engine raises without opening its chooser (the Maya Long Count, a stolen tech, a free Great
  Person, a dig) is asked and answered through `question()` / `answer()` since 2.2.0; anything still outside the
  nine tools makes the agent stop and ask you. `docs/GAPS.md` is the running audit.
- Movement-cost previews and path overlays are not readable: the engine calls that back them crash the game.
- No hosted CI by choice; the suite runs locally before every push.

## Documentation

- [`docs/AGENT_INSTALL.md`](docs/AGENT_INSTALL.md): the complete install brief for an agent.
- [`docs/PLAYBOOK.md`](docs/PLAYBOOK.md): how a seat should play, turn by turn, with the blocker table. A seat reads it
  from inside the game as `reference(book="playbook", section=<topic>)`, with [`docs/TOOL_REPLIES.md`](docs/TOOL_REPLIES.md) (every key of the
  long replies) served the same way.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): layers, information boundary, game modes, repo layout.
- [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md): what the harness will not do, each item checked against the engine.
- [`docs/GAPS.md`](docs/GAPS.md), [`docs/ROADMAP.md`](docs/ROADMAP.md), [`CHANGELOG.md`](CHANGELOG.md): live audit, plan, and the map from package versions to runtime versions.
- The tool-surface plan, nine tools (`turn`, `state`, `order`, `question`, `answer`, `notebook`, `batch`, `session`, `reference`) in place of the 145 by modelling the game's objects and their legal actions instead of its buttons, lives on GitLab: [milestone 2.0.0](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/milestones/11) and [tracking issue #59](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/issues/59).
- [`docs/DECK_HOWTO.md`](docs/DECK_HOWTO.md): running a seat on a Steam Deck.
- [`saves/README.md`](saves/README.md): the reproduction states and what each one shows.

## Development

```bash
sudo apt install lua5.4 liblua5.4-0   # luac for the runtime lint, liblua for the Lua tests
uv sync --group dev
scripts/check.sh            # 2039 tests: the shipped Lua under lupa, the Python layer against fake bridges; no game needed
```

`CIV5_CALL_LOG=/path/calls.jsonl` in the server's environment writes one line per tool call (bytes, trips,
seconds, refusals, and `client`: `CIV5_CLIENT` when set, else the MCP client's name/version, so two models on
one seat stay apart); `scripts/ledger_report.py [--seat N] [--client codex]` turns it into a per-turn table
with a per-client footer. Off by default; `scripts/llm_seat_loop.py` sets both for the agent it runs.

`python -m harness.spectator --ledger /path/calls.jsonl` serves a live, read-only page (`web/viz/`, d3) of the
game and the seats' attention: the whole map in greyscale, every plot a tool reply handed a model pulsing once in
the seat's colour, acts staying painted for the turn, a ghost of the previous seat, a heatmap, and an Observer /
Seat N switch. `--record` / `--replay` work without a game. See `docs/VISUALIZATION.md`.

The Lua runtime is one file per game domain under `harness/lua/runtime/` (its `README.md` says which file
owns what and how to add one); `harness/runtime_source.py` lists the load order and assembles what is injected.
It carries its own version counter (`RUNTIME_VERSION` in `bootstrap.lua`), bumped on every change to any of
those files, because a running game keeps the old runtime until a newer number arrives; the source digest
re-injects a changed runtime even when the bump was forgotten. Commit subjects carry it as `runtime vNNN`.

Issues and milestones live on GitLab: <https://gitlab.com/Tyler-Meador/civ-v-linux-mcp>.

## Authorship

This project was written by Claude, Anthropic's AI model, working in Claude Code under the direction of
Ty Meador, who owns the game, ran every live session and decided what the harness should and should not do.
Claude Fable 5.1 wrote most of it, with Claude Opus 5, Claude Sonnet 5 and Claude Opus 5.5 on earlier
commits; the `Co-Authored-By` trailers in the git history say which model wrote what. That covers the
reverse engineering of the FireTuner protocol and the game binary, the shim, the Lua runtime, the MCP
server, the tests, the documentation and this README. Ty's
contribution is the design brief, the live verification against the running game, the judgement calls
recorded in `docs/GAPS.md`, and the standard that the seat may see only what a human sees.

## License

[MIT](LICENSE). Sid Meier's Civilization V, its assets and the stock UI Lua quoted in `docs/` belong to
Firaxis Games and Take-Two Interactive and are not covered by this licence; you need your own copy of the
game.
