# Changelog

Two counters, on purpose (GitLab #26):

- **Package version** (`pyproject.toml`, git tag `vX.Y.Z`) follows the milestones in `docs/ROADMAP.md`:
  0.2.0 information boundary, 0.3.0 trade table, 0.4.0 screens before the decision, 0.5.0 live
  verification, 1.0.0 release.
- **`RUNTIME_VERSION`** (`harness/lua/runtime/bootstrap.lua`, read back by `harness/game.py`) counts
  injections of the Lua runtime. It goes up whenever any file under `harness/lua/runtime/` changes, because
  the game keeps the old `H` table alive until a newer number arrives; a stale MCP server re-injects the
  version it started with. Commit subjects carry it as `runtime vNNN`, so `git log --grep 'runtime v'` is
  the full map. (Since v226 the source digest re-injects a changed runtime even without a bump; the number
  stays the human-readable handle a live session reports.)

Dates are the day the change was committed; "live tNNN" is the game turn it was checked on.

## Unreleased

### Fixed
- **A tactical neighbour says what the step costs and which enemy's zone of control ends it** (GitLab #180,
  runtime v334, three-seat hotseat, seat 1 Celts t11 / t16). A Warrior with 2 moves read a plains neighbour as
  `move: open` with nothing else, stepped there and arrived with 0: a barbarian stood next to both plots, and
  leaving a plot next to an enemy for another plot next to the same enemy spends every move; a Scout stepping out
  of a barbarian's reach did the same. Every open neighbour now carries `cost` (the moves the step spends) and
  `left` (the moves after it; with none left now, from next turn's full moves), and `zoc` names the enemy unit
  (`id`, `unit`, `x`, `y`, `owner`) or city whose zone of control ends the move there. Plot:MovementCost crashed
  the game (t183), so the new step_cost.lua reads BNW's CvUnitMovement::MovementCost off the engine's getters and
  tables inside the view's one Lua call: all moves for zone of control (visible enemy combat units and cities next
  to the unit, not an embarked enemy, an enemy ship only onto water, none under an IgnoreZOC promotion), a river
  crossed without a bridged road (Team:IsBridgeBuilding, Unit:IsRiverCrossingNoPenalty), embarking and
  disembarking; one move for FlatMovementCost or an EmbarkedToLandFlatCost disembark; otherwise the feature's or
  terrain's Movement, HILLS_EXTRA_MOVEMENT on hills without a city, GetExtraMoveDiscount, the double-move
  promotions, FasterInHills, the Great Wall, and a usable road or railroad on both plots (Routes.Movement plus
  Team:GetRouteChange, FlatMovement x base moves; MoveFriendlyWoodsAsRoad). A fogged plot is priced as last seen.
  Not yet seen live: the numbers against the engine's own move on rivers, roads and forested hills.
- **The tactical grid keeps a city under the unit standing in it** (GitLab #177, seat 1 Celts t4). A Scout on
  Edinburgh read `.@`: the cell is two letters and this unit's `@` replaced the city's `C`, while `cities` still had
  Edinburgh at distance 0. A city in sight is now the cell's ground letter and its units the occupant: `C@` this
  unit in a city, `Cu` / `Co` a garrison, `CX` an enemy city, `C ` an empty one; a fogged city stays remembered
  terrain plus `?` (it is in `cities`). The legend (docs/TOOL_REPLIES.md) and the one-line key say so.
- **A hold order says what the unit is doing, and Wake is a row** (GitLab #176, runtime v333, three-seat hotseat,
  seat 1 Celts t7 / t12 / t24). MISSION_FORTIFY on a Warrior that had moved answered `activity_name:
  SLEEP_OR_FORTIFY` with its move left, units() read `SLEEP`, `fortified: false`, todo.units no longer named it,
  and its actions offered COMMAND_WAKE with no `call`. That is the engine's fortify: ACTIVITY_SLEEP plus a fortify
  count (GetFortifyTurns) that starts at the unit's next turn start when it moved this turn, grows to
  MAX_FORTIFY_TURNS (2 x 20% in BNW); no hold spends moves, and a holding unit is not IsReadyToMove, the end-turn
  list. A hold's reply (fortify, sleep, alert, skip, heal, garrison, wake) now carries `hold` from the same facts
  the unit list and todo.units read (H.unit_hold_state): `state` fortified / fortifying / asleep / alert /
  skipping / healing / awake, `fortify_turns`, `full_in`, `needs_orders`, a `summary`, and `moves` saying what the
  moves left mean; a move's `then` carries it too. units() rows add `fortifying`. The activity word is the
  engine's (`SLEEP`, as units() says) instead of SLEEP_OR_FORTIFY. COMMAND_WAKE and COMMAND_CANCEL rows carry
  their `call` (order(to="unit", action="mission", args={mission})). A standing order's hold step wakes a unit
  still resting from a heal first (t24: "heal to 90, then fortify" paused on "action is not currently legal",
  since the engine takes no new hold from a waiting unit) and is done at once for a unit already holding. Not yet
  seen live: GetFortifyTurns 1 at once for a fortify with full moves.
- **A move that ruins replace the unit on is a success that names the new unit** (GitLab #169, runtime v333,
  three-seat hotseat, seat 0 Maya t5, seat 1 Celts t22). Scout 24576 moved onto ruins at (22,21) and became Mayan
  Atlatlist 32770; the reply was `{"ok": false, "err": "no such unit"}` because the read-back found the old id
  gone, the next digest placed the Scout at its turn-start plot and said it "moved on automation", and
  assignment 8 stayed on the vanished id. The read-back now asks the runtime for the successor
  (harness/lua/runtime/successors.lua: one of my units created this turn whose type the old one upgrades or
  ruins-upgrades to -- Unit_ClassUpgrades or Units.GoodyHutUpgradeUnitClass -- on the destination first) and
  answers ok with `successor` {id, type, x, y, moves, hp}, `moved_from`, `unit_gone`, a tactical-view row for the
  new id, and `carried_over` (assignments and the open order follow it, as after an upgrade); with no single
  successor it says the move ran and `identity: "unknown"`, never a refusal. The successor is recorded and put on
  the unit_destroyed row, so the digest's unit_upgraded row names the new id and the ruins plot and says "your
  move took it there"; the roster fallback (#100) names automation only when the roster saw the unit moving on
  its own. A retry to the old id, or an order from a briefing older than a standing move's ruins (Celts t22), is
  refused naming the successor. Game.UnitSuccessorsMixin (harness/game_parts/unit_successors.py) keeps units.py
  from growing. Not yet seen live: the successor read right after the move (the new unit's GetGameTurnCreated).
- **A standing order that completes at the turn start is counted closed** (GitLab #181, three-seat hotseat, seat 0
  Maya t26; a regression past #113). The finish that ended t25 said `orders: {open: 1, paused: 0}` over a single
  row with `status: completed`: the turn-start window took `open` from the orders it was about to run, before the
  quarry's order completed in that run, and gave no `closed` count (#113 had fixed the briefing's count only).
  One count (`harness/orders.py` `counts`) now reads each returned row's status after the run -- `open` active +
  paused, `closed` completed / failed / replaced / cancelled (only when there are any), `paused` -- for the
  finish, the wait and the briefing alike.
- **A remote build keeps the order it creates** (GitLab #182, three-seat hotseat, seat 1 Celts t18). MISSION_BUILD
  on another plot became walk-then-build order 1, walked the Worker to (8,23), and the same reply paused order 1
  as "given a direct order (unit_mission); that command owns it now", its note still placing the Worker at
  (7,24). The one-owner rule lives in `Game.direct_command`: the order that held the unit before the command is
  taken (paused, or replaced when it was paused), never one the command itself opened; a remote build replaces
  the unit's open order instead of being refused by it. give_order's reply carries `at`, where the run left the
  unit, and the remote build's note names that tile.
- **A bare icon reads as its yield** (GitLab #103 follow-up from hotseat Maya t3, runtime v329). The engine writes
  some effects as icons alone -- God-King is "+1 to these yields: [ICON_CULTURE] , [ICON_PEACE] , [ICON_GOLD],
  [ICON_PRODUCTION], [ICON_RESEARCH]" -- and plain_text kept the icon's name, so it read "Culture, Peace, Gold,
  Production, Research". One word table (`harness/game_parts/icon_words.py`, mirrored in empire.lua's
  `icon_word`) names the faith dove Faith, the flask Science, a happiness face Happiness / Unhappiness,
  GREATPEOPLE Great People, a resource icon its resource; a test holds the Python and the Lua side to the same
  words.
- **A move refused as unrevealed notices swapped axes** (GitLab #150 F4, hotseat Spain t4). When the target read
  with x and y swapped is a revealed plot, the refusal carries `swapped` ({x, y}) and its hint says so, before
  the fog is blamed.
- **A notebook belongs to one game** (GitLab #168, fresh three-seat hotseat, seat 0 Maya, 2026-10-30; runtime
  v330). The key was leader, civ, map, capital and founding turn, so a new Maya game that founded Palenque on turn 0
  opened the previous Maya game's notebook: its notes, a Tikal garrison on Warrior 16385 (same id, type and
  creation turn), a turn-31 briefing baseline, and a standing order on Worker 40960 that ran on turn 1. The key
  now ends in the game's identity (`harness/notebook_identity.py`): a digest of the seat's own starting plot and
  the civilization / city-state in every slot, read by `H.game_key_facts` -- fixed when the map is made, kept in
  the save, different between two games set up alike (the engine has no game id; the debug menu's map and sync
  seeds were never seen to survive a reload). It does not change at the founding, so #159's before-capital
  adoption is gone. A notebook under the old label key is adopted once, by a game past its start turn (a game
  the harness plays is first seen on its start turn), and quarantined: notes carry `adopted` (`notes_adopted` / recall's `adopted`
  say why), active assignments read needs_review until amended or closed, open orders are paused with kind
  `adopted`, the briefing baseline and the memo are dropped. A fresh game opens an empty notebook and leaves the
  old file alone; the first look writes the identity's file, so the decision is made once.
- **A proposal shows only on the seat it is sent to** (GitLab #172, #174; three-seat hotseat 2026-10-30, t8 and
  t25; runtime v331). Seat 0 proposed to seat 2 alone, yet seat 1 -- which had not met seat 0 -- got
  todo.incoming_deal {from: 0, items: 2}; question() had nothing to show, the deals screen said the table was
  occupied, and the blind refuse finalized a 0 -> 1 deal that never was, so seats 0 and 1 both read "offer ... is
  no longer valid". Every hotseat seat shares one scratch deal, and a sent proposal stays on it (tradelogic.lua
  OnPropose hides the screen without ClearItems; the stock screen clears or reloads the table before a seat sees
  it); the todo row, the deals screen and refuse read whatever was there. `H.foreign_table` names a table this
  seat is no party to, or a human's table whose proposal the engine no longer holds: incoming_deal reads it as
  empty without naming its parties and loads this seat's own proposal over it, so the todo row, question(),
  answer and the deals screen agree. #161's question() path was right; the deal seat 1 could not read was never
  its own. The answer to a human deal echoes what it answered: {ok, other, accepted_items / refused_items}, and a
  refuse of a proposal whose items did not load says `unread` and names the seat.
- **Friendship with a human seat is a deal, not an AI's answer** (GitLab #175; three-seat hotseat 2026-10-30, t6;
  runtime v332). Seat 1 (Celts) asked seat 2 (Indonesia, human) for a Declaration of Friendship and got
  {"accepted": false, "reply": "Making such a declaration at this point in our relationship would be premature"} at
  once: propose_friendship fired the leader screen's HUMAN_DISCUSSION_WORK_WITH_US at seat 2, and seat 2's dormant
  diplomacy AI answered it; the civ summary kept the line under history. Every stock Game.DoFromUIDiploEvent call
  names an AI (the leader screens open for AI leaders only; the diplomacy list opens the PvP table for a human).
  Now order(to="civ", action="friendship") to a human seat proposes the PvP table's Declaration of Friendship
  (tradelogic.lua's DoF pocket, both sides in one press) and returns propose_deal's `pvp`, `pending`, `pending_to`
  with `friendship: true`; that seat answers it with question() / answer(choice="accept" / "refuse"). The item is
  `DECLARATION_OF_FRIENDSHIP` in propose_deal too, and the trade catalog's `declaration_of_friendship` row is the
  pocket's gate (asked of a human seat only: the same query about an AI crashed the game). `declare_war` on a
  human seat is the diplomacy list's War button (Network.SendChangeWar), which no leader answers; `denounce`, the
  raw `event` and answer(choice="accept_friendship") are refused for a human seat with what to do instead (the
  game has no denouncement between human players). The deal-item checks moved out of deals.py into
  `harness/game_parts/deal_items.py`, and the friendship calls out of diplomacy.py into `friendship.py`.

## 2.10.0 -- Decisions explained, lean replies (2026-10-30)

- **Small reply gaps of the Maya t203-t237 run closed (GitLab #148, runtime v327).** `state(what="league")`: a
  choice keeps only the lines its details add to the resolution's (Choose Host repeated 500 chars 12 times, Ban
  Luxury 22 times); a member's "Their interests are largely a mystery" becomes `interests_unknown`. The vote reply
  carries `votes` (resolution, name, direction, votes, choice text). `trade_catalog.third_party.peace` counts the
  civs nobody is at war with (`us_not_at_war_omitted`) instead of listing 40 "not at war" rows. The runtime's
  plain text keeps a bare icon's name like the Python side ("+2 Culture, +2 Tourism", not "+2 , +2"). A fogged
  city plot in the map window names its city (name, owner, city-state / capital: the map index's facts, no more);
  a move's `sighted` city is the short form. The "project has been completed" notice carries `league_project`
  (our contribution, tier, reward). `batch` replies carry `refused` (a count). Answering a leader: a screen another
  leader opens behind them is `next`, never this leader's `remark`, and a same-leader follow-up is `next` once
  (`same_leader`), not `follow_up` and `next`. A trade unit's end-of-route comes as one `unit_lost` row. The
  playbook says unit ids are per player (match a foreign unit by id and owner).
- **A Great Person's withheld missions are explained, a gift names its recipient, a concert tour says what it did
  (GitLab #142, runtime v326).** The actions read listed what the engine allowed and nothing about what it withheld
  (Maya t207-t234: a Great Writer with every writing slot full showed the treatise alone; a Great Musician at home
  showed no concert tour, the foreign-soil rule was found by walking). `state(what="unit", id, view="actions")`
  now carries `missing`: the Great Person missions the unit's class has (Units table columns, great_people.lua)
  that the engine withholds here, each with `why` -- the Great Work's slot census (filled / total, the buildings
  that carry such a slot), the nearest plot that qualifies for a concert tour (another major civ's) or a trade
  mission (a city-state's, not at war), "stand in one of your cities" for a hurry, the stock button's disabled line
  for the rest, and "no moves left" first. A COMMAND_GIFT row is listed on a city-state's plot only and names it
  (`owner`, `minor_id`; its `call` is the complete gift_unit order); on a major civ's land there is no row.
  MISSION_ONE_SHOT_TOURISM's reply carries `effect` (tourism, to_civ, others_percent) and is refused before the
  push from soil where it cannot play; its consumed-unit note names the tourism and the civ.
- **Choosing an ideology is explained in one read (GitLab #145, runtime v325).** The policies read gave three flag
  rows for the biggest single choice of the game (Maya t217). `state(what="options", view="policies").ideologies` now
  carries, per ideology, the met civs that follow it (`friend`, `denounced_us`, `we_denounced`, `at_war`, as the
  Diplomacy overview shows them), `free_tenets_on_adopt` (the popup's "Early Adopter Free Tenets",
  Game.GetNumFreePolicies) and, while no ideology is chosen, its tier-1 `tenets` with their text; `ideology` is
  mine, and while the engine asks for the choice each row carries its `order(to="empire", action="ideology")` call.
  `state(what="civs")` rows carry `ideology` once a civ has one. The ENDTURN_BLOCKING_CHOOSE_IDEOLOGY hint points
  at the rows. `H.ideologies` in policies.lua holds the read; the policies and civs reads only call it.

- **A hand-off is one resumable call (GitLab #160).** A hotseat seat's finish with a 50-second window came back
  `timed_out`, then two waits of 50 seconds: three clock calls, the middle one an error. A wait that runs out is
  no refusal -- it waited as asked -- so wait and finish now answer the same way: `ok`, `my_turn: false`,
  `timed_out`, `timeout_seconds`, `active_player`, `gate` and `next`, the one call that resumes the wait
  (`turn(action="wait", timeout_seconds=600)`). The wait's default is 600 seconds like finish's, and the hint says
  that progress notifications ride on every wait every 5 seconds, so one long call costs no more than several
  short ones. The surface description and the playbook say the same.

- **A quiet run is woken once per expiring deal, and the baseline outlives the process (GitLab #144, runtime v324).**
  Thirty-three Maya turns with `skip_quiet_turns` skipped one: every deal in its last three turns woke each finish,
  because the "once per row" memory and the happiness baseline were a process's own and the seat ran one finish
  per process. Both now live in the notebook file (`Notebook.memo`, per game and seat; `Game.memo` / `set_memo`
  read it each time), so the next process carries on where the last stopped. A happiness drop of one or two
  below the comfortable band is a city growing and stays quiet (3 -> 2 woke three runs); a drop of 3 or more
  below 10, any drop into the negative, or 5 or more at once wakes as before. The expiring-deal hint says first
  that the AI usually offers the renewal itself at the turn the deal ends, and to propose on `reoffer_on` only
  when it did not (every one of the run's ~15 renewals came from the AI).

- **The tactical legend is said once (GitLab #152, runtime v323).** Every `state(what="unit", view="tactical")` reply
  carried the same two thousand characters of legend (grid, move, vis, sight, fog), four times in a Grok seat's
  opening turns and on every move check after. The legend is now the view's reply reference in
  docs/TOOL_REPLIES.md (`reference(book="playbook", section='state(what="unit", view="tactical")')`); a server
  process puts it on its first tactical reply (`legend`) and a one-line `key` on every reply after, naming the
  section. `harness/legend.py` holds the key and the once-per-process rule; the Lua reply carries neither.
- **A move's `revealed` names what is worth a look, not every plot (GitLab #153, runtime v323).** A warrior's one-tile
  step onto ruins that paid a map (GOODY_MAP) listed 49 plots, most of them fogged ocean and coast. `revealed` now
  carries `count`, `water` (how many of the new plots are ocean or coast), `notable` rows (ruins, a barbarian camp,
  a luxury or strategic resource, a natural wonder, a city: x, y, what, owner, fogged), `sighted` as before, and
  `map`, the `state(what="map", view="window")` call around the unit for the plots themselves.

## 2.9.0 -- Reads and schemas tell the truth (2026-10-30)

- **A melee reply reads the blow, not the preview (GitLab #156).** `attack.defender.hp` was the pre-read's row copied
  as it was (100 while `def_hp` and the alert said 74, hotseat seat 1 t10-t11); the row now carries the health
  after the blow (`killed` / `captured` when so), and `damage_dealt` / `damage_taken` stand beside the before/after
  pairs. The preview's expected damage is the stock panel's own number, CvUnit::getCombatDamage without the random
  part, and the blow is rolled around it: `roll_note` says so once a blow landed. `harness/game_parts/combat_result.py`
  holds the block; `units.py` only calls it.
- **The dig's state comes from the plot (GitLab #140, runtime v321).** An Archaeologist's dig keeps the unit's
  GetBuildType at -1 while the plot carries the build (Maya t218: `buildtype -1, completed true` the second the dig
  started, the Trading Post under it gone). `builds.lua` reads one build state for every caller: `H.unit_build` (the
  unit's own type, else the plot's running build for a unit on MISSION_BUILD), `H.plot_under_construction`; the
  order and notebook replies say `started, turns_left` and `replaced_improvement`, never `completed` while a build
  runs. A build that spends its builder (`consumes_unit`: the Kill column, the dig) closes the order complete when
  the unit is gone after it was seen building (t235 read `failed, unit_gone`). The turn's todo and the briefing's
  decisions carry `dig_choice` from the engine's next completed-dig plot, whatever blocker it names first (t221,
  t234: PRODUCTION masked it until finish refused). question() says why only the landmark is offered
  (`landmark_only`: no free Art/Artifact or Writing slot, the stock popup's rule) and what `written`, the slots and
  the choices mean; answer() names the find and `outcome`: the Great Work with its city and building, the landmark,
  or the culture. An Archaeologist's actions list `dig_sites` (x, y, distance, owner, a running dig), nearest first.
- **A unit that completed is not production_dropped (GitLab #141).** A Caravan with every route slot used reads
  CanTrain false the turn it completes (Maya t232, Uxmal), as does any one-per-city unit; the queue watch now takes a
  unit of that type created this turn on or beside the city as the completion it is.
- **One remaining-turns number for a build (GitLab #165).** The order reply printed GetBuildTurnsLeft and the unit
  row the panel's number, one apart (`turns_left 3` beside `build_turns_left 4`, hotseat t28); `H.build_turns_left`
  gives the stock unit panel's count (unitpanel.lua line 392) to the order reply, the unit row, the plot's
  under-construction line and the notebook facts.

- **A refusal accepts the 2.x call, never the retired one (GitLab #146, #163, #164).** `accepts` printed the old
  handler's signature (`explore_frontier(unit_id, limit=12)`, `available_trade_routes(unit_id, ...)`,
  `turn_digest()`) beside a right example; `harness.surface.forward.new_signature` renders the row's fixed fields and
  the arguments under their new names (`state(what="map", view="frontier", id: integer, limit: integer = 12)`, what
  rides under `args` as `args={...}`), and every shape and ambiguity refusal uses it. The digest row says
  `detail='digest' takes no since or limit`. The state schema says which view takes which selector: x, y and
  radius for map/window and map/grid, radius alone for unit/tactical (centred on the unit, which took no x, y),
  `id` for map/frontier (the explorer) and options/trade_routes (the caravan). A produce refusal with no rule
  named carries the production popup's own disabled text (CanTrainTooltip / CanConstructTooltip / CanCreateTooltip:
  "Requires the University in this City." for an Archaeologist, Maya t224) as `engine_reason` and the refusal
  itself; the price read says `can_build`, and its no-gold-price reason names a unit the engine never sells.
  Runtime v322.
- **The notebook's contract is what give_order does (GitLab #166).** The description said nothing here moves a unit
  now and one step per turn; give_order and resume_order run the first steps at once (a move spends this turn's
  movement, a build starts) and carry on at each turn start, each step at most once per turn and the next as soon
  as one completes (Maya t29: move done and quarry started in one arrival). Notes and assignments move nothing.

## 2.8.0 -- Hotseat: nothing stalls or leaks (2026-10-30)

- **A human seat's proposal is readable and answerable (GitLab #161, runtime v319).** Codex on seat 0 (t15) had
  `pending_deal_from: 1` and a todo row saying question() shows the items, but question() found no screen and no
  blocker, said "nothing is asked" and handed back the same row; the deals screen refused with "trade table is
  occupied"; the proposal was refused unseen. The other human's proposal is now a question without a screen beside
  the #95 blocker questions (`gate.screenless_question`: a blocker first, else `PENDING_DEAL` while
  `status.pending_deal_from` names a seat): question() reads the table (`pending: true`, `from`, the items, the
  accept / refuse rows) and answer(choice='accept' / 'refuse') settles it; any other choice is refused naming the two.
  A proposal the engine holds but whose items did not load into the scratch (the second symptom: the todo row vanished
  after a policy popup while status still named the proposer) reads as `unread` with the refuse row alone, the todo
  row follows the engine's record (`H.pending_deal_from`), and `H.refuse_deal` finalizes the proposal itself. The
  `question` description names the case. **Seen live 2026-10-30 (the Codex/Grok hotseat, t38-t39):** seat 0's two-item
  proposal read by seat 1 as pending from 0 with both items and the accept / refuse rows, refused with one call, the
  status and todo clear after it; seat 1's one-item proposal read and refused by seat 0 at t39 the same way (the wait
  that opened t39 carried `pending_deal_from: 1` and the todo row). The save before the check is
  `hotseat/Pacal-Isabella_0038 before-161-check`.
- **answer(choice='leave') cancels a bare trade table.** The hotseat game stood at t38 with a DiploTrade from seat 0
  to seat 1 and nothing on it (left by the previous session); the gate said leader_screen, question() showed an
  empty deal, `leave` pressed Back on the hidden DiscussionDialog and closed nothing, and every order was refused on
  the gate. With only a trade table up, `dismiss_discussion` now presses the table's own Cancel (tradelogic.lua
  OnBack; CANCEL_TYPE for a PvP draft), the path close_trade_screens already used, and reports `closed: trade_table`.
- **No public opinion before an ideology (GitLab #151, runtime v320).** The turn-0 empire read of a hotseat seat said
  DISSIDENTS, Order preferred, and a tooltip naming two unmet civs as the pressure: the engine's fields outlive the
  previous game of the process (#107 was the same at Maya t0). Both stock screens read public opinion only once an
  ideology is adopted (cultureoverview.lua:1832, socialpolicypopup.lua's HasIdeology branch), so `H.public_opinion`
  is nil until `GetLateGamePolicyTree` names one; `change_ideology` says "no ideology adopted yet" as before.
- **A greeting read is the greeting (GitLab #154).** question() on a first-meeting leader screen (and the echo of a
  war or peace) carried the whole relationship block -- approach_guess, the discuss flags, the opinion table, the
  embassy and border flags, wars_fought -- beside an empty button list. Information-wise that is the Diplomacy
  overview's tooltip once the screen closes (parity, not a leak), but the screen shows the leader and their words
  alone: the read now carries those and the leave row, and `how_to_answer` names state(what='civ', view='summary')
  for the standing. Discussion and trade screens keep the block (it says what the leader's words rest on).
- **The notebook follows the seat through the founding of its capital (GitLab #159).** The key is built from the
  seat's capital and the turn it was founded, so a plan remembered at t0 before the Settler acted sat under
  `L31-C33-continents-t-1-s0-seat0` and the key became `...-Palenque-t0-s0-seat0` one call later: the recovered
  server read an empty notebook (the two files are on disk). `game_keys` now says whether the seat is `settled` and
  names the `before_capital` form of a settled key; the key is read again until the capital exists (so the writing
  process moves at the founding), and `notebook()` adopts the pre-capital file once, as it does the pre-v285 form.
- **The main menu is the no_game gate for every tool (GitLab #158).** A startup turn(action='briefing') with the
  game on a front-end screen came back as "harness error: KeyError: no Lua state named 'InGame'; have [...]" and no
  gate; only turn(action='status') knew the menu. `guarded` now answers that bridge error from the main menu with
  `no_game_reply` (ok: false, ingame: false, the screen, the seat, `err` naming load_latest and the no_game gate
  with its rows); status keeps its ok: true form of the same reply.
- **The "AIs are still moving" hint rests on a read after the screen closed (GitLab #155).** answer(choice='leave')
  on a first-meeting greeting named turn(action='wait') and the wait returned at once on the seat's own open turn:
  a leader screen freezes my_turn to false while it is up, and the hint read the state taken before the answer.
  `_ais_moving_after` reads the turn state once the screen is closed (not while another leader is queued) and
  names the wait only when the round is really on (#111's case, a deal answered mid-round, keeps it).
- **The first reply to meet a new turn carries its digest (GitLab #147).** An order sent while the AIs moved
  blocked until the turn arrived, ran, and carried `arrival` (orders, standing moves) with no digest; the finish
  beside it was refused on an idle city and carried none either. `arrive_if_due` asks whether the turn is unseen
  (its turn_start undelivered) and takes the digest with the arrival; finish_turn's unseen path hands that one back
  instead of reading an empty second. The playbook's turn loop says an order sent during the AI round blocks until
  the turn arrives and then runs on it. The unseen probe takes only the runtime's own `true`.
- **Notebook orders: a destination pause skips the unit and retries by itself; a direct order replaces a paused
  order (GitLab #143).** Maya t216: a Worker's order paused on a Cannon's plot and the Worker, at full moves, had
  the finish refused with ENDTURN_BLOCKING_UNITS; the pause waited for a manual resume while the plot freed. t234: a
  Musician's paused order kept its old destination and the todo's stalled_mission row after a direct move had taken
  the unit elsewhere. Now a destination pause (`orders.DESTINATION_PAUSES`: the plot refused, an enemy on it) skips
  the unit for the turn (MISSION_SKIP, `pause.skipped_turn`) and `run_orders` retries it at every turn start (a fresh
  start for the step, as a resume is; the turn claim covers the retry); a direct move or mission to a unit whose
  order is paused closes it as `replaced` (`order_replaced` on the reply) while an active order still pauses (#32).
  Hostile, damage and low-hp pauses stay the agent's to resume.

## 2.7.1 -- the four descriptions under 4.5 (2026-10-29)

- **The four descriptions Glama's TDQS marked under 4.5, restructured (GitLab #139).** Glama's own TDQS panel on the
  v2.7.0 release (admin view, scored 2026-10-30 00:30 UTC; the per-tool marks and every justification are
  `docs/measurements/2026-10-29-glama-tdqs-admin-v2.7.0.md`) averaged 4.5 across the nine with `turn` at **3.6**
  (behavior 3, conciseness 3, parameters 3: "a wall of text", no concurrency or permission semantics, nothing beyond
  the schema), `notebook` 4.2 (not told apart from `order`, the shape of `steps` missing), `answer` 4.3 (what an
  invalid or out-of-order answer does), `batch` 4.3 (`force` undescribed) and the server's coherence 4.2 (disambiguation
  4: `order` against `batch`, `turn(finish)` running a batch; completeness 4: undo and replay). Each of the four now
  opens with its purpose, says what it does to the game and what cannot be undone, names the sibling to use instead
  ("Not this tool: ..."), and explains its arguments beyond the schema: `turn` is five labelled actions, an
  "arguments by action" line, the side effects (a turn handed over cannot be taken back, a session save is the way
  back, a refused `actions` row leaves the turn open, finish only waits when it is not my turn, `turn_claim` and
  `args.force`), the timeouts (finish 600, wait 90, `timed_out`) and the refusal shape (`end_turn.todo`,
  `skip_actions`); `notebook` says nothing in it moves a unit now, lists the `steps` kinds of a standing order
  (`move`, `build`, `heal`, `hold`, at most 6) and its interrupts; `answer` says it settles the one popup
  `question()` shows, acts as the popup's own button would, and refuses an unoffered choice or an answer when nothing
  is asked with nothing happening; `batch` says the turn stays open, why a refusal stops the rest, what `force`
  takes over and when `order` or `turn(action='finish', actions=...)` is the better call. `turn`'s and `batch`'s
  `force` parameter descriptions say what they take over. Every description stays under the 2000-character client cut
  (`turn` 1994). Verified with the free offline lint (no shadow candidate, invocation costs unchanged) and **two hosted
  TDQS calls** (spec 1.2, 2026-10-29; the listings sent and the reports are
  `docs/measurements/2026-10-29-tdqs-tools-list-2.7.1*.json` / `-report-2.7.1*.json`): the first draft 4.7 A with
  `turn` 4.4 (conciseness still 3: "mixes multiple concerns in a single block"), the final text **4.7 A, every tool
  4.6 or better** (https://tdqs.dev/reports/p0usqgjwik): `order` / `batch` / `session` 4.8, `question` 4.7,
  `reference` / `turn` / `state` / `answer` / `notebook` 4.6; description quality 4.6, coherence 4.8 (completeness,
  disambiguation and tool count 5, naming 4: "not a strict verb_noun pattern"). Glama scores a release, so 2.7.1
  carries the text to its scanner. `tests/test_listing_quality.py` and the invariants test guard the openers, the
  `Returns` sentence and the cut as before.

## 2.7.0 -- nine nouns (2026-10-29)

- **`inspect` is `state`: nine nouns (GitLab #138; runtime v318).** Glama's re-score of the 2.0.0 listing (2026-10-28)
  and TDQS both marked naming 4/5 for one reason: eight tools are the things you touch (the turn, an order, the
  question, the answer, the notebook, a batch, the session, the reference) and one was a verb. `state(what, id,
  view)` reads the same objects with the same arguments and replies; `inspect` is retired like the 145 old names
  (`RENAMED_TOOLS` in the retirement map): it still answers, running `state` with `renamed: state(...)` on the
  reply, the ledger and a batch classify it by the new call's key, `CIV5_RETIRED_NAMES=off` makes it unknown, and
  the runtime audit forbids the old word in Lua strings (the 17 fragments that named it say `state(` now, a
  text-only bump). Instructions, descriptions, playbook, replies' `actions` rows, docs and tests speak the new
  name; the CHANGELOG's history and the measurements keep the old. `tests/test_renamed_tool.py` (8).
  **Scored by TDQS after the cut** (https://tdqs.dev/reports/lhsoppr5k9, spec 1.2, 2026-10-29, one manual call; the
  listing sent and the report are `docs/measurements/2026-10-29-tdqs-tools-list-flat.json` / `-report-flat.json`):
  overall **4.7 (A)**, up from 4.6; coherence **5.0** with naming consistency **5/5** (4 since 2.0.0), completeness 5,
  disambiguation 5, tool count 5; description quality 4.5 (A), per tool `order` / `session` 4.8, `state` / `batch` 4.7,
  `reference` / `notebook` 4.6, `question` 4.4, `turn` / `answer` 4.3.

## 2.6.1 -- the leader view left open (2026-10-29)

- **A game loaded after leaving one with a leader on screen could never end its turn (GitLab #137; runtime v317).**
  Live Maya t200 (2026-10-29): `turn(action="finish")` met Dido's friendship request during the AI turns;
  `session(action="main_menu")` with that screen up, then `session(action="load")` of the same save, left
  `UI.CanEndTurn()` false with `blocking_name` NO_ENDTURN_BLOCKING_TYPE, no popup and no leader in any Lua
  context -- every CONTROL_ENDTURN was discarded and the refusal could only say "a screen the harness does not
  model may be open". The exe keeps its leader view open across `Events.ExitToMainMenu()`; the screen's own
  back button, `UI.RequestLeaveLeader()`, closes it (End Turn enabled two seconds later, live). Now
  `H.exit_to_main_menu` leaves an open leader view before exiting (`left_leader_view: true` on the
  session(action="main_menu") reply), and `H.end_turn_send` clears a stale one itself when End Turn is disabled
  with no blocker, no popup and no leader on screen, recording a `stale_leader_view_cleared` event the finish
  digest carries; the diagnosis says `leader_view_up` and that the stale case was tried. Verified live both ways
  on the t200 save (the stale game ended its turn; the exit with Dido on screen left End Turn enabled after the
  reload). `tests/test_stale_leader_view.py` (6).

## 2.6.0 -- quiet turns and lean replies (2026-10-29)

Milestone [2.6.0](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/milestones/20): what costs tokens and attention
every turn without blocking it -- quiet turns that stay quiet through the harness's own screens and my own orders, a
gold-per-turn drop with its cause, automation that ended as a digest line, an alliance cascade as one row, a lean
city-state read, the other servers of a seat and a server behind main reported, and the small reply gaps of five
play sessions (Siam t0-t35, Maya t0-t200) -- eleven issues worked in the milestone's order and closed on GitLab with
a regression test each. Measured live on the Maya t200 save (`Pacal_0200 maya-t200`), 2.5.0 code against this
release, the same reads from a fresh server each: `inspect(what='city_state', id=37, view='full')` 8109 -> 5508
bytes; `turn(action='status')` 2344 -> 2344; `inspect(what='units', view='actions')` with nothing to do 76 -> 273
(the note saying where the units are); `turn(action='briefing', since='turn')` 2810 -> 4674 (the new
`unimproved_resources` warning with six build rows and `changes` against the earlier briefing); the finish reply at
t200 5944 (2.5.0, ended into a leader screen) against 4727 (the turn refused: after the save is reloaded the engine's
End Turn stays disabled with no blocker, an open point in SESSION_HANDOFF). Runtime v313 -> v316, 9 tools, 1950 tests.


Milestone [2.6.0 Quiet turns and lean replies](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/milestones/20): wake
reasons, digest lines and reply sizes -- what costs tokens and attention every turn without blocking it -- worked in
the milestone's order.

- **Quiet turns stay quiet through the harness's own screens and my own orders (GitLab #99).** Every early
  quiet-turn run woke at once (Maya t5-t17): on the ruins and city-state greeting screens the harness closes
  itself (the move's reply carries the reward since 2.3.0), on my own founding a turn late, on the banner of my
  own city strike, and twice on one "enemy spotted" banner. The two screens join `QUIET_POPUPS`; a `city_created`
  of this seat, the result banner of my own strike or founding, and the second copy of a hostiles banner no longer
  wake; `skip_quiet_turns` is described as the count it is. One test.
- **A gold-per-turn drop names its cause (GitLab #78).** 38 -> 16 at Assyria t243 with no word while unit
  maintenance had climbed over the supply cap. The briefing baseline keeps the gold breakdown, and a drop of more
  than a quarter carries `cause` (the expense that grew, with where the supply cap stands). One test.
- **Automation that ended is a digest line (runtime v314; GitLab #77).** A Worker automated at t239 was back in
  `todo.units` at t244 at the same plot and nothing said automation had ended (Assyria). The roster notes which
  units are automated, and a unit noted automated that is not any more at the turn start is an `automation_ended`
  row naming the two reasons the engine has (nothing left to build in reach, a threat) and that re-automating now
  does the same. One test.
- **A city-state alliance cascade is one row (GitLab #82).** Siam took five allies in a turn and the digest and the
  wake reasons listed ten lines, never the delegates (Assyria t251). Two or more alliance notices of one turn (and
  the war declarations the new allies make) become one `city_state_allies` row: the allies lost and gained, who
  took them, the wars declared, and the World Congress delegates change (2 per ally). One test.
- **`inspect(what='city_state', view='full')` says each thing once (runtime v315; GitLab #65).** The read was
  ~12 KB (Assyria t239): every one of 39 units as a gift row, the resource tiles twice, each gold tier's row
  twice. Now `gift_units.units` is the first six (the runtime orders them: an upgrade passed by first, then the
  weakest) with `units_total`, `units_omitted` and the drill-down `args={'all_units': true}`; the resource tiles
  stay under `gift_tiles` and the summary's status says `resource_tiles_in`; a gold tier carries `call` only.
  Sidon at Maya t200: 8.1 KB to 5.4 KB (7.5 KB with all_units). Four tests.
- **Status names the other MCP servers of this seat and a server running older code than main (GitLab
  #61).** Two servers of seat 0 were attached to one solo game on 2026-10-27 and only `ps` said so; a server
  started before a release cut kept its import-time listing ("oneOf below" in a description no code carried).
  `harness/presence.py`: a file beside the action lock, per socket and seat, with a row per server process that
  every guarded call refreshes; `other_clients` on status / finish's status lists the other live ones (pid, client
  label, attached_for_s, last_call_s, code_behind) with a note, and `server_outdated` says the harness's Python
  on disk changed after this server started (files_changed, newest, the restart advice). TOOL_REPLIES and the
  PLAYBOOK say so. Three tests.
- **The small reply gaps of five play sessions (runtime v316; GitLab #126, #132, #107, #113, #118).** Each cost a
  read. Replies: `inspect(what='notifications', since=N)` works (turns after N); `inspect(what='map', view='grid',
  x, y, radius)` is the box around a centre; `inspect(what='city_state', id)` and `inspect(what='civ', id)` default to
  `summary`; the city-state summary carries `ally` (who, `to_become_ally`) and `capital` {x, y}; a priced item says
  `build_turns`; a missing `mission` / `kind` lists the legal values; `propose_deal`'s example has real items; a
  wrong `give_order` step says the four shapes; the orders block counts the open rows; a deal's `effects` carry the
  note that the span is the whole exchange; `reference(section, find=word)` keeps the headings and the matching
  lines of a section too long for one reply. Units: a move refused onto my own unit names it (`blocking_unit`)
  before the fog is blamed; `promote` says `instant` for the heal and hands back `next_promotion` rows when another
  is banked; the promotion chooser's `effect` line is back; a Great Engineer's hurry says `capped_by_item`. Cities:
  the city screen's plots carry resource, feature, improvement, terrain, hills, road, water and a buyable plot its
  `call`; the culture meter says it is border growth; `inspect(what='units', view='actions')` with nothing to do
  says where the units are. Digest: my own unit killed while defending is named from the roster with its plot
  (`your ATLATLIST (36,66)`, not "unit (not visible)"), a damage row carries `hp_before`, a city-state that fell is a
  `city_state_fell` row (who holds its city), `todo.idle_spies` lists an unassigned spy. Briefing: the baseline's
  age is said when it is not the last turn end; `tools_note` is gone; `public_opinion` is absent before any ideology;
  `unconnected_cities` and `unimproved_resources` warnings (the board reads them; a Worker's build row per plot).
  `gift_gold` takes a tier's name or amount, a wrong amount lists the tiers, a short treasury says `gold_short_by`.
  Left as they are: unit and city ids share numbers (the engine's), the greeting swept by a move (#122).

## 2.5.0 -- late game and strategy reads (2026-10-29)

Milestone [2.5.0](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/milestones/19): the eight reads of the late game
and the long-range choices -- a spaceship part as a decision and its blocked capital tile, a kept standing move, the
wonders still open, the culture estimate and a culture-victory warning, trade routes sorted and measured, a league
project's tiers, a Settler's sites -- worked in the milestone's order and closed on GitLab with a regression test.
Shown live on 2026-10-29 on the Maya t200 save (`Pacal_0200 maya-t200`, loaded through a fresh server): every
culture row on this seat carries its estimate ("never at current rates" or the turns), the wonders screen lists
fourteen wonders, the league read carries the World Fair project with its tier thresholds. Runtime v311 -> v313,
nine tools, 1923 tests.

- **A spaceship part is a decision row (GitLab #93).** The one order that wins the game was never a row (Assyria
  t273: the Engine sat in `todo.units` like any unit). A part in the capital gets a `spaceship_part` row with
  `MISSION_SPACESHIP` (and "next turn" when it has no moves); a part elsewhere gets the walk into the capital and
  the mission. Two tests.
- **Buying a spaceship part flags the civilian on the capital's tile (GitLab #80).** The idle Worker on Assur's tile
  refused the part's move, and automating it moved nothing until the turn's end (t272). The purchase reply carries
  `capital_tile` naming the civilian standing there and the move that frees the tile. Two tests.
- **A standing move blocked by my own civilian is kept, not dropped (runtime v311; GitLab #86).** An automated
  Worker walked into the capital the night before the Booster's standing move landed, and the move was dropped
  for good (Assyria t253). One of my own civilians on the destination moves on: the record is kept and tried
  again at the next turn start, the row says who stands there (`blocking_unit`). One test.
- **Which world wonders are still open is readable (runtime v311; GitLab #115).** Wonders built by civs this seat
  had not met were nowhere, and research and Great People went toward wonders already gone (Maya t153-t178). The
  engine announces every world wonder to every player, so the count built anywhere is public: the wonders screen
  lists an unmet civ's wonder as `built_elsewhere`; a research row's building button carries `taken` and a note
  for such a wonder; the item price read says "a world wonder already built elsewhere" instead of "no gold price".
  One test.
- **The culture screen's estimate is always said, and a culture-victory threat is a warning (runtime v312; GitLab
  #88).** Siam's row on me carried no `turns_to_influential` the turn after "Siam only needs 1 more civilization"
  (Assyria t256): the engine's 999 means never at current rates, and the row now says so ("never at current rates"
  while rising, "never (not rising)" otherwise, 0 when already influential). `H.culture_threats` rides on the
  briefing board and the briefing's `warnings` carry `culture_victory_threat` for a met civ one civilization short,
  with its row on this seat. Two tests.
- **Trade-route options come best first, measured and limited (runtime v312; GitLab #74).** A 31-row list in a
  fixed order with no distance, war or danger. Rows are sorted by `sort` (gold by default; science, food,
  production, the `*_them` yields, or `distance` ascending), `limit` keeps the first N (the last row says how many
  follow), and each row carries `distance` (plots), `at_war_with_owner` and `enemies_near_destination` (visible
  enemy combat units within three plots). One test.
- **A league project's process says its tiers and the turns to the next (runtime v313; GitLab #81).** Producing
  `PROCESS_INTERNATIONAL_SPACE_STATION` read "never completes" and the agent crossed tier 2 untold (Assyria t249).
  The reply carries `league_project` (contribution, tier, the next tier's hammers, the turns to it at the city's
  production rate, which the queue read now carries as `production_per_turn`) and a note that the project pays
  by tier and resolves with the session. One test.
- **A Settler's sites are a read (runtime v313; GitLab #106).** Three Settlers were placed from map windows around
  guesses (Maya t18-t54). `inspect(what="unit", id=<settler>, view="targets", mission="MISSION_FOUND")` lists the
  revealed plots within six where a city can be founded, best first by the engine's own site value
  (`Plot:GetFoundValue`, given only where the first ring is fully revealed), with fresh water, river, coast, hills,
  the first ring's resources, the distance to walk and to the nearest city of ours, and `calls` (the move, then
  the founding). Two tests.

## 2.4.0 -- every decision is a row (2026-10-29)

Milestone [2.4.0](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/milestones/18): the twelve early and mid-game
decisions an agent could only reach by guessing a call -- a worker's build on another plot, a move, "go there and
hold", a starving city, a city that can fire, a religion's founding and beliefs, a Great Person on a stacked tile, a
caravan's route and its refusal, a merchant's trade mission, a negotiation, religious defense -- each made an
`actions` / todo row with its target and a refusal that names the rule, worked in the milestone's order and closed
on GitLab with a regression test. Checked live on 2026-10-29 on the hand-started Maya game (t1 -> t5 through a fresh
server): the tactical view's neighbours carried the move rows, a move ordered from one with `then: fortify` was
recorded for the arrival, and the standing move was held beside a barbarian camp with its reason on the row. Runtime
v306 -> v310, nine tools, 1911 tests.

- **A worker's build on another plot is one order (runtime v306; GitLab #102).** `build_plots` listed a mine two
  plots away with no call, and `MISSION_BUILD` with that plot answered "not currently legal" (Maya t31; the agent
  fell back to automation and later lost the Worker). Every build plot row -- the summary's `build_plots`, the
  normal row's `nearby_builds` -- carries `calls`, one complete `MISSION_BUILD` per build with the plot, and a
  build ordered at a plot the unit does not stand on becomes a notebook order (walk there, then build) run now and
  at each turn start, with `remote_build` and a note; a refused walk says the unit must stand there and why. Three
  tests.
- **A move is a row with a plot to choose, the tactical view's neighbours carry the step, and the targets read says
  where destinations come from (runtime v306; GitLab #135).** The `MISSION_MOVE_TO` row carried no plot (Denmark
  t20), the open neighbours no call, and `inspect(what="unit", view="targets", mission="MISSION_MOVE_TO")` refused
  with an empty list. The move row is now the tactical read then `order(to="unit", action="move")` with `x`, `y` to
  choose (a route the same with its mission); every open neighbour and attack in the tactical view carries `call`;
  the targets read's refusal for a move names the tactical view and the order. Three tests.
- **"Go there and hold" is one order (runtime v307; GitLab #105).** A move that arrived with moves left blocked
  the finish until a second fortify row, and a fortify sent at 0 moves was a one-turn HOLD the engine forgot
  (Maya t54-t97). `order(to="unit", action="move", args={x, y, then: "fortify" | "sleep" | "alert" | "hold"})`
  holds once there: now when the unit arrives with moves left, else the turn start that lets it arrive or finds it
  there (`H.set_pending_then`, `H.hold_unit`), with the engine's own swap when the unit cannot take the hold asked
  (a Scout sleeps). The reply's `then` says which and when. Seven tests.
- **A starving city and a city that can fire are todo rows (runtime v307; GitLab #101).** "Palenque is Starving!" and
  "Tikal can fire upon an enemy!" were notification text only (about forty turns of the latter). `todo.starving`
  (cities losing food, with the surplus) and `todo.city_strikes` (cities with a bombard they can fire now and a
  target in range) ride on every status and wake a quiet run; the briefing's decisions carry a `starving` row (the
  city screen, the food focus, the plot to work) and a `city_strike` row (the strikes read, the strike). Two tests.
- **Religion: belief rows carry their effect, the pantheon reply names the belief, question() shows the religion
  to found, the orders take the city's id, and a Prophet's refusal names the rule (runtime v308; GitLab #103).**
  Maya t30-t92: `{belief, name}` rows sent the agent to the rule book for every choice, `order(to="empire",
  action="pantheon")` answered a bare ok, `question()` said "nothing is asked" after MISSION_FOUND_RELIGION, the
  religion order refused `city` (every other city order takes the id), and MISSION_ENHANCE_RELIGION was refused
  with the bare legal list inside another city and on a hill. Every belief row carries `effect`; the pantheon reply
  carries `belief`, `name`, `effect`; `question()` with a religion to found or enhance pending shows the decision,
  its rows and the beliefs on offer; `religion` / `enhance_religion` take `city` as well as `city_x` / `city_y`;
  `H.religion_mission_why` names the condition the Prophet fails (not in a city of yours, the city does not follow
  your religion, no religion founded, one founded already, none left to found). Four tests.
- **The units hint names the hold each unit can take (runtime v308; GitLab #85).** The generic blocking hint named
  MISSION_FORTIFY to a Hwacha, which cannot fortify. Every `todo.units` row carries `hold` (MISSION_FORTIFY, or
  MISSION_SLEEP for siege, mounted, armoured, naval units and civilians) and the hint says so. One test.
- **A Great Person on a stacked tile is the decision (GitLab #91).** Born on the city tile beside the automated
  Worker, a Great Scientist read as "two of my units share a tile" with the Worker to move. The stacked decision's
  rows open with the Great Person's own choices (its actions read: a great work, a bulb, a golden age, a citadel, a
  trade mission clear the stack too), the row names `great_people` and says so. One test.
- **A caravan's route row is the route read then the route order (GitLab #75).** `MISSION_ESTABLISH_TRADE_ROUTE`
  carried no destination and no read; the row is now `inspect(what="options", view="trade_routes", id)` then
  `order(to="unit", action="trade_route")` with the destination (or the city and kind) to choose. One test.
- **A route refusal names the rule and the routes open (runtime v309; GitLab #73).** "route is not currently
  available to this unit" stood alone and stopped a batch (Assyria t239). The refusal carries `reason` (one route
  per origin-destination pair, another city of yours may run one there, out of range, not connected by land / sea)
  and `available`: the routes this unit can take, each with its order. One test.
- **A Great Merchant's trade mission has a target read (runtime v309; GitLab #87).** `MISSION_TRADE` is legal only
  inside a city-state's land, so the plot-by-plot targets read listed nothing for a merchant at home.
  `inspect(what="unit", id, view="targets", mission="MISSION_TRADE")` now lists the met city-states by distance
  with the nearest revealed plot of their land, the engine's own gold and influence for the mission there
  (`Unit:GetTradeGold` / `GetTradeInfluence`), `at_war`, and `calls`: the move onto the plot, then the mission.
  Two tests.
- **Religious defense is a row (runtime v310; GitLab #112).** Tikal and then the holy city converted to Venice's
  Catholicism and nothing but a digest line said so; Venice's Missionaries walked in unlisted; a spread charge was
  spent on a city that already followed the religion; the trade route's `from_religion` read as the origin's
  religion (Maya t107-t134). The board carries `religion` (my religion, each city's majority with the holy city
  flagged and the followers of each, other civs' religious units standing in my land) and the briefing's
  `warnings` get `religion_lost` rows (the holy city first, with what it costs and the Inquisitor / Missionary
  that wins it back) and `religious_unit_in_my_land` rows; a spread row's `yield.target` names the city the charge
  would hit, its majority and followers, and says when it already follows the religion; a mission that acts is
  not offered at 0 moves; the route's religion columns gain `pressure_into_origin` / `pressure_into_destination`
  and a legend. Three tests.
- **A negotiation signs nothing and says so (GitLab #69).** "This deal will work as it stands on the table" read as
  a deal made. The negotiate reply carries `signed: false`, a note, and `next`: the `propose_deal` with the table
  as the AI left it. One test.

## 2.3.0 -- reads tell the truth (2026-10-29)

Milestone [2.3.0](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/milestones/17): the twenty-one findings of the
2026-10-27/28 play sessions where a read contradicted the game or another read, or reported an event a turn late --
worked in the milestone's order, each closed on GitLab with its fix and a regression test. Where the finding was the
engine's own rule (a plantation on jungle needs Bronze Working, Legalism needs Oligarchy, the embassy flag's
direction, a session-fixed delegation), the read now names the rule instead of hiding the fact. Re-checked live on
2026-10-29 through a fresh server on the hand-started Maya game at t1 (runtime v305 installed at the first call):
the map grid's rows keep every column, the index carries `bonus_resources`, unit rows carry `activity`. Runtime
v297 -> v305, nine tools, 1871 tests.

- **The combat preview says what its strengths are, shows both sides' HP, and the summary keeps the modifiers as one
  line a side (runtime v297; GitLab #121).** Grok at Siam t10-t13 read the same `my_strength` 9.6 for a full-health
  and a 10-HP Warrior as a bug and asked where an 8-strength unit's 1.6 came from. The engine's strengths carry
  every modifier and never the wounds (wounds scale the damage dealt, which `expected_damage_*` already include):
  `strength_note` says so, `my_hp` / `their_hp` ride beside the strengths, and the tactical summary turns the
  modifier rows the full view keeps into `modifiers_brief` ("Fortified +20%; vs Barbarians +33%"). Two tests.
- **A refused build names the engine's rule when it is a feature-removal tech (runtime v297; GitLab #130).** A Worker
  on jungle cocoa with Calendar known was refused `BUILD_PLANTATION` with the bare legal list, and the plot never
  appeared among the build plots: CIV5Builds.xml's `BuildFeatures` says a plantation on Jungle removes the jungle as
  part of the build and needs Bronze Working (Forest: Mining, Marsh: Masonry). `H.blocked_builds` lists, for a plot
  with a resource, the builds its resource calls for that the unit cannot start here for such a tech (`blocked_builds`
  on the unit's actions for its own plot, `blocked` on a nearby build plot, which is listed even with nothing legal
  yet), and the `MISSION_BUILD` refusal carries `reason` naming the tech and the research read. Two tests.
- **A unit sees the plot it stands on (runtime v298; GitLab #131).** A garrisoned Archer's own city read `in_sight:
  false` at distance 0 (Siam t4, t31): the tactical view's line-of-sight probe asks `CanSeePlot` of every other
  plot and skipped the unit's own. The own plot is in sight now; its fire line stays unset (a ranged unit cannot
  target its own plot). One test.
- **A trade catalogue's city rows say whose city each id is (runtime v298; GitLab #70).** `us` and `them` carried
  the same ids for Nineveh and Umgungundlovu and their neighbours -- city ids are per player in the engine. Every
  city row carries `player`; `inspect(what="city", id)` reads my own cities only. One test.
- **A wait that lands on my turn carries the digest, and a leader answered mid-round says what comes next (GitLab
  #111).** After `answer(choice="accept")` on an AI's mid-round deal, `turn(action="wait")` handed back the bare
  status: the Atlatlist's bombardment, a lost ally and a new tech were only in a separate digest read (Maya t106,
  t108). The wait carries `digest` and `woke_because` whenever the digest has anything (a quiet wait stays lean),
  and an answer given while the AIs are moving carries `next`, naming `turn(action='wait')` / `turn(action='finish')`
  as the call that brings the new turn with its digest. One test.
- **Grids keep their columns through `plain_text` (GitLab #97).** The markup stripper collapsed runs of spaces and
  trimmed the ends of every string, so the map grid's rows lost their unrevealed columns (12 characters for a 21-plot
  window) and the tactical grid its row separators. Under `grid`, `layers`, `rows` and `cols` a space is a cell: the
  markup still goes, the spaces stay. One test.
- **The map index keeps a natural wonder once seen and lists bonus resources (runtime v299; GitLab #124).** Mt.
  Kailash left `natural_wonders` as soon as the fog closed over it, and cows, stone, bananas and deer a move had
  revealed were missing with no word that the index kept to luxuries and strategics (Siam t10, t16). A natural
  wonder stays listed under the fog from the feature a visible read remembered (the fogged plot's live feature is
  never read); `bonus_resources` lists the food and production resources; `note` says what each list is. One test.
- **An open policy branch lists its locked policies with what they need (runtime v299; GitLab #123).** `adoptable`
  showed Aristocracy and Oligarchy; Legalism, Landed Elite and Monarchy were invisible and their absence read as a
  bug (Siam t14, t21). The engine's tree is the rule: in Brave New World Legalism needs Oligarchy, Landed Elite and
  Monarchy need Legalism (`Policy_PrereqPolicies`); `locked` rows name each policy of an open branch not offered yet
  with `needs`. One test.
- **A move's reply says what the move made happen, and names a leader met on the way (GitLab #122, #125).** A
  scout's ruin reward and a warrior's camp gold arrived only on the next finish, stamped the previous turn (Siam
  t7, t12), and Egypt's first-contact greeting opened under a scout's move with no word until the next status was
  gated on it (t16). Every move reads the event log past the head it saw before the order (the digest's cursor
  does not move) and carries `happened`: the ruin's reward, the camp's gold, a natural wonder, a city-state met
  with its gift, the alerts, and `met_leader` with the leader's words; a first-contact greeting is closed as the
  wait closes one (a real discussion never is). A greeting that opens during the AI round stays a digest
  `leader_message`, which is the record of it. Four tests.
- **A unit row says how it is holding (runtime v301; GitLab #128).** A sleeping Scout read `fortified: false` while
  `MISSION_FORTIFY` was refused as "already holding" -- a scout cannot fortify, it sleeps, and the two reads only
  looked contradictory. Every unit row carries `activity` (the engine's word: AWAKE, HOLD, SLEEP, HEAL, SENTRY,
  INTERCEPT, MISSION) and `holding` (true for any hold, fortified included). The summary's `routine_actions` stays
  the static list it is documented as; the unit's own legal list is the actions view. One test.
- **A founding is never a ruins upgrade, and an upgrade placed from the roster says so (runtime v301; GitLab #100).**
  The Settler that founded Palenque the same turn a Warrior took ruins read "found advanced weapons in the ruins":
  the digest turned every unit spent that turn into the upgrade. Founded settlers and civilians are left out; an
  upgraded unit the engine moved on automation is placed from its last recorded plot and the row says so
  (`plot_from: roster`) and points at `inspect(what='units')` for the new id. Two tests.
- **A league read's delegate counts agree, or say why they differ (runtime v302; GitLab #79).** At Assyria t251 the
  members block said 32 vs 14 while every proposal's text tallied 24 vs 24: the session fixes each delegation when
  it opens (what can be cast, `delegates` and `remaining_votes`), while the text and the next session follow the
  allies of the moment (Siam had just taken five). In a session each member row carries `delegates_now` and a
  `delegates_note` when the two differ. Two tests.
- **A purchase refusal follows the engine's own sentence, and the production read names the item being built
  (runtime v302; GitLab #76).** A buyable spaceship part read "cannot be bought here at all" beside the tooltip's
  "Cannot purchase while another unit is stationed in this City. You do not have enough Gold" (Assyria t249, t251):
  the stacking and the price gap are named first now, with `blocking_units`, before any guess. The production read
  carries `in_production` -- the queue's head with its name, turns, gold price, `buy_blocked` and, for a capped unit
  (a spaceship part, whose queued copy the cap counts), the dequeue-then-purchase recipe -- since the engine keeps
  such an item out of the list while it is queued. One test.
- **The embassy direction flags were swapped (runtime v303; GitLab #136).** `Team:HasEmbassyAtTeam(t)` is "this
  team's embassy stands in t's capital" (the receiver of ALLOW_EMBASSY gets one at the giver), and both the civ
  relationship read and the trade catalogue's open-borders row read it the other way round: at Denmark t25 India
  had bought an embassy in our capital and `our_embassy_with_them` said true. Both reads agree with the deal and
  the opinion text now; the open-borders note follows. One test updated to the engine's meaning.
- **An accepted or sent proposal carries no answer rows (GitLab #68).** `order(to="civ", action="propose_deal")`
  answered `accepted: true, closed: true` with `table.answers` still offering accept / refuse; a proposal sent to
  a human seat the same. The table keeps the items as they stood and loses the rows: there is nothing for this
  seat to answer. One test.
- **A discussion gate carries this screen's own buttons, and names no verdict on a deal (GitLab #72).** Portugal's
  denunciation at Assyria t240 had two buttons; the gate offered `answer(choice="<button_id>")`, accept and refuse.
  When the status carries the discussion, the gate's rows are its buttons and leave, and a plain discussion never
  offers a deal's answers; a deal on the table has no `clear_with` (accept read as a recommendation): the three
  answers are alternatives and the read says what each item does. Two tests.
- **`buy_plot` reports the treasury after the purchase (runtime v304; GitLab #129).** The runtime's read came before
  the purchase landed (`gold_after` 166 beside `gold` 136, Siam t26): the reply carries `gold_before` and reads
  `gold_after` once the treasury moved (a note when it has not yet). Two tests.
- **Faith rows say why they cannot be bought (runtime v305; GitLab #67).** `faith_can_buy: false` stood alone beside
  gold rows that carried `buy_blocked` (Assyria t239-t251: Great Engineers at 670 faith with 1159 in hand, the
  city tile occupied). `faith_blocked` climbs the same ladder: not enough faith (balance of cost, where the button
  exists), one per tile with `blocking_units` (the rule holds for faith purchases too), the engine's own faith
  tooltip (a Great Person's era and policy-branch rule, a Missionary's religion), else refused. One test.
- **The city centre is never an unimproved tile (runtime v305; GitLab #66).** `gift_tile_improvement`'s `why_not`
  listed Colombo's own plot as "jewelry unimproved at (49,18)". The capital's plot is left out of the resource
  tiles it names. One test.
- **A write's arrival block does not warn about the city-state the write just fixed (GitLab #64).** The arrival
  work runs before an order and its expiring-ally rows were attached to the reply as read: a 250-gold gift to
  Colombo answered `friendship 80` and "Colombo, influence 60, 1 turn left: gift_gold to keep it". The row for the
  order's own city-state (its `minor_id` / `player_id`) is dropped with a note. Three tests.

## 2.2.0 -- nothing stalls, crashes or leaks (2026-10-29)

Milestone [2.2.0](https://gitlab.com/Tyler-Meador/civ-v-linux-mcp/-/milestones/16): the seventeen findings of the
2026-10-27/28 play sessions (Claude Code, Grok and Codex on Assyria, Maya, Siam and Denmark) where the game crashed,
the turn could not end, information leaked, or an order said ok and nothing happened -- worked in the milestone's
order, each closed on GitLab with its fix and test. The live check the milestone asked for was played on
2026-10-29: a Maya game started by hand from the setup screen sat on its Dawn of Man splash; the first
`turn(action="status")` of a fresh server pressed it, Palenque was founded, research and production set, and
`turn(action="finish")` reached t1 (the `replaced` queue note and the Random-map key were seen live the same
session). Runtime v288 -> v296, nine tools, 1846 tests.

- **`MISSION_SWAP_UNITS` is no longer advertised (runtime v288; GitLab #71).** Every unit's `actions` and the
  summary's `routine_actions` listed it, because the engine's `CanStartMission` says yes to it for every unit;
  the order itself does nothing in this build (live England t225: the unit sat in `ACTIVITY_MISSION`, nothing
  moved) and the `GAMEMESSAGE_SWAP_UNITS` net message crashed the game. `H.available_unit_actions` skips the
  row with the other global controls, `ROUTINE_ACTIONS` and `KNOWN_MISSIONS` drop the name (so it is never a
  `did_you_mean` either), and `unit_mission` keeps refusing it with the two-move recipe. One test.
- **A game started or loaded by hand plays from its Dawn of Man splash (runtime v288; GitLab #96).** `loadscreen.lua`
  pauses a single-player game with `Game.SetPausePlayer(activePlayer)` until its button is pressed, and only the
  harness's own load pressed it: a hand-started game read `paused: true`, the `paused` gate sent the agent to
  `turn(action="wait")`, and the wait returned at once with the same gate, forever (Maya t0; Claude Code, Grok and
  Codex all hit it). `turn_state` carries `load_screen_pending` (single mode, paused, the pause player this seat;
  `H.pause_player`), the wait presses the splash as `_finish_load` does, every guarded call and `turn(action="status")`
  press it first (`load_screen_cleared: true`, the turn arrives as after a hand-off), and a press that does not take is
  the `load_screen` gate, between `processing` and `paused`, with its own refusal. PLAYBOOK's gate list. Ten tests;
  the runtime entry pin grows by one. Live 2026-10-29: a Maya game started from the setup screen by hand sat on
  the splash (`paused`, `load_screen_pending`); the first `turn(action="status")` of a fresh server pressed it
  (`load_screen_cleared: true`, gate null), Palenque was founded, research and production set, and
  `turn(action="finish")` reached t1.
- **A blocker that is a question is asked and answered without its popup (GitLab #95).** The engine raises
  `ENDTURN_BLOCKING_MAYA_LONG_COUNT` (and the steal-tech, free Great Person, faith Great Person and archaeology
  blockers) without opening the chooser until its notification is clicked, and `question()` / `answer()`
  dispatched on the popup alone: the hint sent the agent from one to the other and back, and the turn could not
  end through the nine tools (Maya t77, t88). `harness.gate.BLOCKER_QUESTIONS` names each blocker's read and
  resolver; with no gate up `question()` serves the read (`pending: true`, `blocker`, the `answers` rows) and
  `answer(choice)` runs the resolver with the choice in its own argument (a stolen tech's `player_id` in `args`);
  a popup on screen still outranks the blocker. The briefing's `blocker` row carries the two calls. Four tests.
- **A Random map's script no longer reaches the seat (runtime v289; GitLab #119).** A game set up with map type
  Random hides the chosen script from its human players; the notebook's game key carried it
  (`H.game_key_facts` read `PreGame.GetMapScript()` whatever `IsRandomMapScript()` said) and the key reaches the seat
  in `notebook(action="assignments")` and in the notebook's file name. The map part of the key is `random` then,
  as the setup read already said; a notebook written under the script's key is adopted once (`Notebook.adopt_matching`,
  the newest file matching the key with its map part a wildcard, never merged). Three tests. Seen live 2026-10-29:
  the hand-started Maya game's settings said `map_script: random`.
- **One vote call commits the whole delegation, and the runtime refuses what cannot count (runtime v290; GitLab #89).**
  Live Assyria t258: 20 of 28 delegates on the embargo answered `votes_cast 20, abstained 8`, and a second call with
  the 8 on Arts Funding answered `votes_cast 8` and counted nowhere -- the engine had committed the delegation, the
  network layer dropped the message. `H.league_cast_votes` now refuses, with `nothing_cast` and `remaining_votes`: a
  spent delegation ("already committed"), a resolution not up for a vote this session (and a direction that is not
  the proposal's), more votes than remain, and rows that leave delegates unassigned unless `abstain=true` is passed
  (an empty list still abstains them all on purpose). A reply that casts says `delegation`, `committed: true` and the
  note. `order(to="league", action="vote", args={votes, abstain?})`; the league read's `vote_note` and the
  PLAYBOOK say the rule. Five tests.
- **A standing move is held when resuming would walk into harm or waste the turn (runtime v291; GitLab #98).**
  The resume ran at the turn start, before the seat saw the turn: a Spearman and then a Scout walked a plot a
  turn around a barbarian camp, arrived in `ongoing` with 0 moves every turn, were bombarded every AI turn and
  died with no turn to react (Maya t34-t38, t54-t62); Settlers and Prophets arrived with 0 moves and lost the
  turn their purpose needed. `H.hold_standing_move`: a hostile combat unit or a camp beside the unit (the
  engine's own "enemy in sight" interrupt, which a Lua-pushed move never gets), or a civilian whose destination
  is within this turn's reach, keeps the record and is not re-issued; `resumed_moves` carries the row as `held`
  with `reason` and `attention`, the unit stands in `todo.units` with its moves and the reason as its `note`
  (a move to the same plot resumes it, another plot redirects it, MISSION_SKIP / COMMAND_CANCEL drops it). The
  MISSION_SKIP refusal on an ongoing unit names COMMAND_CANCEL. No path or turn estimate: `Unit:GeneratePath`
  is not implemented in this build and `GetPathEndTurnPlot` needs the mouse pathfinder. Six tests.
- **A screen that will not close no longer swallows the turn boundary (GitLab #90).** Live Assyria t269: the Great
  Person screen was still up 0.15 s after its button inside the wait's sweep, and the whole `turn(action="finish",
  actions=[...])` reply was `{ok: false, err: "GreatPersonRewardPopup did not close"}` -- no `batch`, no `ended`,
  no digest, while the orders had run and the turn had ended (the model re-sent a policy already adopted). The
  sweep presses once more after a longer settle before giving up; a screen still stuck after the turn ended comes
  back as the boundary (`ok: true, ended: true`, the digest, `popup_stuck`, `woke_because: ["popup_stuck"]`, the
  gate the next call clears); and when `actions` ran, any tuner error out of the finish still hands back `batch`,
  `ended` (read from the state) and `status`. Five tests.
- **An order the engine would hold and never run at 0 moves is refused (runtime v292; GitLab #83, #110).**
  `MISSION_SPACESHIP` from a part that had just arrived with 0 moves answered `ok: true` with the Booster count
  unchanged (Assyria t254): the engine queued it on HOLD, never ran it, and the part dropped out of `todo`. A move
  onto a barbarian ordered at 0 moves answered `queued: true` (Maya t119); the engine kept a mission it never ran
  and the unit sat on HOLD at full moves the next turn, in `todo.units`, `todo.ongoing` and `resumed_moves`
  alike nowhere. `H.NEEDS_MOVES` names the missions that act (the spaceship part, the Great People's one-shots,
  pillage, found, the trade and religion missions, nukes, paradrops, air attacks): at 0 moves `unit_mission`
  refuses them with "order it next turn"; the hold missions (skip, sleep, fortify, alert, heal) still work at 0
  moves. `move_unit` onto an enemy unit or city at 0 moves is refused outright: an attack is never a standing
  move. And `is_stalled_mission` counts ACTIVITY_HOLD with a mission still queued and moves left as stalled, so a
  unit the engine holds that way stands in `todo.units` (the engine raises no blocker for it). Four tests.
- **A city's production queue never loses an item without a word (runtime v293; GitLab #114).** A replacing
  `order(to="city", action="produce")` dropped three queued items and said nothing (Maya t153, t182): the reply
  now carries `replaced` (the items that were queued) and a note naming `append: true`. The dequeue refusal says
  position is 1-based and 1 the current build (the retirement row's note rides on every shape refusal). And a
  queued item the engine drops because the city can no longer build it -- Korea completed the Porcelain Tower
  and Palenque's queued copy vanished, the city idle five turns later (t173-t178) -- is a `production_dropped`
  event in the digest: each seat's queues are snapshotted at its turn end and compared at its next turn start, an
  item gone that the city cannot build any more and did not complete there is reported with the city and the
  reason (it wakes a quiet run). Five tests.
- **A note remembers what its unit ids were (GitLab #63).** The engine reissues ids in creation order, so after a
  reload note 5's "Great Merchant 1343522" named a Mongolian Khan (Assyria t239). `notebook(action="remember")`
  stores the type of every unit the text names by id (`units`, one units read at write time); `recall`, the
  briefing's notes and the finish's notes carry `unit_check` on a note whose id is another type now ("the note
  says GREAT_MERCHANT, that id is a MONGOLIAN_KHAN now") or gone. Assignments already told a reused id apart
  by type and creation turn. One test.
- **A religion to found or enhance stays visible and orderable whatever blocker the engine names (runtime v294;
  GitLab #109).** Live Maya t105: `MISSION_ENHANCE_RELIGION` answered a bare `consumed: true`; the engine named
  PRODUCTION as the blocker, so `question()` and the decisions showed nothing and
  `order(to="empire", action="enhance_religion")` was refused "not pending" until both cities had production. The
  runtime remembers the Prophet's mission (`H.religion_pending`, set by the push, cleared by the choice;
  `H.religion_choice` is that memory or the blocker), `todo.religion` says `found` / `enhance`, the briefing's
  decisions carry a `religion` row with the popup's rows (the two belief reads, then the order), the Prophet's
  mission reply carries `next` and a note naming the calls and which belief is `belief4` (follower) and `belief5`
  (enhancer), the enhance reply names the religion and beliefs, and `REQUIRED_BLOCKER` is empty: no order is
  refused by comparing blocker names any more. Three tests.
- **Notes from a later timeline are listed last, in recall too (GitLab #62).** After the S10 reload at t239 the
  briefing showed notes 6-11 (t241-t278, "the game is over") above note 12 (t238), in id order, and `recall`
  marked nothing. Later-timeline notes now come after this timeline's notes, by turn, in the briefing's and the
  finish's notes and in `notebook(action="recall")` (`later_timeline` on each row and a `later_timeline` count
  and note on the reply; the recall tool reads the turn on screen). One test.
- **The World Congress's call for proposals is a decision before finish refuses, and the league read has a compact
  form (runtime v295; GitLab #117).** Live Maya t197: the status named PRODUCTION; the proposal blocker (a hard
  block) surfaced only when finish was refused, and the read to pick from was 25 KB, every Ban Luxury and Embargo
  choice repeating the resolution's paragraph. `todo.league_proposal` (the league is between sessions and
  `CanPropose`) rides on every status with the proposals left; the briefing's decisions carry a `league_proposal`
  row (the compact read, then propose / repeal); `inspect(what="league", args={detail: "compact"})` keeps every
  id, name and vote row and drops the per-choice paragraphs, the member tooltips and `active_effects`; a vote row
  for a resolution with choices says `choice` takes one of its `choices[].id`. Four tests.
- **A disabled End Turn under a todo blocker is answered with the todo (GitLab #104).** Live Maya t87: one unit
  with moves left, `UI.CanEndTurn()` false, and the refusal sent the agent hunting for "a screen or popup the
  harness does not model". When the todo has units or the blocker is one the todo explains, the refusal says
  "turn has unresolved decisions: ..." with the blocking hint; the engine's facts stay under `engine`. One test.
- **`skip_actions` and a turn claim speak the nine tools (GitLab #84).** The end-turn refusal's `skip_actions` were
  `{tool: "unit_mission", ...}` rows, a 1.x name two clients were handed; they are `order(to="unit",
  action="mission", id, args={mission: MISSION_SKIP})` rows now, through `rows.act`. A turn claim's `tool` names
  the new call too.
- **A finished game's status carries no chores (runtime v296; GitLab #92).** After the Science Victory at Assyria t273
  the status kept `ENDTURN_BLOCKING_LEAGUE_CALL_FOR_PROPOSALS`, its hint and a Crossbowman in `todo.units` beside
  the `game_over` gate. With the game over, `turn_state` reports no blocker, no hint, an empty todo and no
  expiring deals, wars or alerts. One test.

## 2.1.0 -- a listing a judge can read: annotations, descriptions, one `order` schema; the third client measured (2026-10-28)

A minor version: nothing a seat does changes, what a client is shown does. Every one of the nine tools now
carries MCP annotations (the reads `readOnlyHint` and `idempotentHint`; `order`, `batch`, `session` and
`notebook` `destructiveHint`; `openWorldHint` false throughout), every listed parameter a schema `description`,
and every description opens with what the tool is for, says when a sibling is the right call, and names the
reply's and the refusals' shapes. `order` is one flat schema for every client -- `to` an enum, `action` a string
whose description lists the verbs by target -- and the `oneOf` of 2.0.0 with its per-client variants
(`FLAT_CLIENTS`, `CIV5_ORDER_SCHEMA`, `--order-schema`) is gone: the #49 measurement, complete with the Grok row
this release adds, found no client that rendered the `oneOf` faithfully or validated against it, and TDQS counted
its branches as a shadowing cost. Scored by TDQS (https://tdqs.dev, the Glama scorer; four manual calls, the
reports and the `tools/list` sent under `docs/measurements/2026-10-27-tdqs-*`): the 2.0.0 listing 3.4 (B,
description quality 2.8 C), this one **4.6 (A)**: coherence 4.8, description quality 4.5, mean per-tool 4.6,
lowest 4.3, no shadowing risk, the lint down to the nine output-schema notes. From the fresh Grok session that
closed #49: notes written on a turn later than the one on screen ride on the briefing marked `later_timeline`;
an `inspect` refusal for an object that takes an id says where the ids come from; the playbook answers
`city_state(s)`, `deals`, `trade` and `league`. The listing is 21 KB (~5.3k tokens). Lua runtime v287, unchanged.

- **One `order` schema for every client; the `oneOf` and its per-client variants are gone (2026-10-27, night).**
  TDQS's deterministic shadow prefilter counts each `oneOf` branch as invocation cost: `order` cost 14 against
  `answer`'s 3 and was flagged as shadowed by its cheaper sibling on all three reports (the coherence pass
  dismissed the overlap each time, but the flag stayed). The #49 measurement had already shown the `oneOf`
  bought nothing: Codex and Claude Code rendered it wrongly, Grok passed it through and validated nothing, and
  the verbs by target were in `action`'s description all along. `harness/surface/listing.py` now writes one flat
  shape (`to` its enum, `action` the verbs by target) and `harness/mcp_tools/surface.py` applies it once at
  import; `FLAT_CLIENTS`, `variant_for`, `CIV5_ORDER_SCHEMA` / `--order-schema`, the `tools/list` middleware and
  the client-name probe are deleted. Offline `tdqs lint` on the new listing: `order` cost 2, no shadow candidate,
  no warning at all. Scored hosted after the fact: 4.6 (A) overall, no shadowing risk
  (`docs/measurements/2026-10-27-tdqs-*-5-flat.json`). ARCHITECTURE's section keeps the three-client table as
  the record of why.
- **Five descriptions rewritten against the judge's notes: `inspect`, `order`, `question`, `session`, `reference`
  (2026-10-27, night; TDQS 4.2 -> 4.4 A, the five 3.5-4.4 -> 4.6-4.8).** Each now opens with what it is for and
  when its siblings are the right call instead (inspect before and after an order, reference for what things
  do, question for what a popup asks, turn for the turn), is laid out in lines (how to call, the table, the
  selectors, what comes back), names the reply's shape and the refusals' (`choices`, `accepts` + `example`,
  `hint`, the rule the game names) and the side effects the annotations only hint at (a load replaces the game
  on screen for everyone, each finish's autosave overwrites the quick-save slot, an order runs whole or not at
  all). `reference` lists both books' sections and topics and what an unknown one answers. Listing 18.7 KB ->
  21.7 KB, the longest description 1855 characters (the cut is 2000). Third report and listing:
  `docs/measurements/2026-10-27-tdqs-*-3.json`.
- **The listing as TDQS lints it: annotations, parameter descriptions, a purpose sentence and the return shape
  on every tool (2026-10-27, evening; 3.4 B -> 4.2 A).** Each of the nine carries MCP annotations
  (`harness/mcp_tools/surface.py` `ANNOTATIONS`: the reads `readOnlyHint` and `idempotentHint`; `order`, `batch`,
  `session` and `notebook` `destructiveHint`, since an order, a load and a forgotten note cannot be taken back;
  `openWorldHint` false throughout; a `title` each); every listed parameter has a schema `description`
  (`Annotated[..., Field(description=...)]`, kept by `listing.order_schema` in both variants); `session` and
  `notebook` open with what they are for and spell out each action's `args` and reply (`session`: a load replaces
  the unsaved state, save first; `notebook`: `assign` takes `role`, `purpose`, `unit_ids` / `city_ids`); `turn`,
  `order`, `answer` and `batch` say what comes back. The listing grew from 11.9 KB to 18.7 KB (~4.7k tokens),
  every description under the 2000-character client cut. Not done: output schemas (the replies are the old
  reads' replies, too many shapes for one schema). `tests/test_listing_quality.py`; the second TDQS report and
  the `tools/list` sent are `docs/measurements/2026-10-27-tdqs-*-2.json`.
- **#49's Grok row, and Claude Code measured again: the client table complete (2026-10-27, evening).** A
  fresh Grok CLI session (Grok Build 1.0.70, `grok-4.7`, clientInfo `grok-shell-civ5/1.0.70`, the server from
  the repo's `.mcp.json`) played Assyria t238 from the reloaded S10 save with the nine tools alone: the
  briefing, Zurich's 1000-gold gift copied from its full view's row (influence 46 -> 131, allied), the league
  read, a note, the turn ended, t239 reached -- thirteen calls, 74 trips, three refusals (reads by a wrong
  name), and the one deliberately malformed order (`order(to="unit", action="produce")`) sent through to the
  server's refusal (`docs/measurements/2026-10-27-assyria-t238-grok-session.md`, the ledger rows beside it).
  Grok's `search_tool` hands the model the listed schema verbatim, `oneOf` included, and validates nothing;
  it keeps the oneOf variant. Claude Code 2.1.311, measured the same evening, renders the `oneOf` as one wrong
  sentence ("Input constraint: Provide parameters for exactly one of: (to, action)") with the branches' enums
  gone, and the same malformed order reached the server unvalidated: `claude-code` joins `listing.FLAT_CLIENTS`
  beside `codex` (the flat description lists the verbs by target; nothing is lost). The table in
  `docs/ARCHITECTURE.md` has all three rows; #49 closed. What the session met, fixed: a note written on a turn
  later than the one on screen (a save was loaded; the notebook holds the t239-t278 notes) rides on the
  briefing and the finish with `later_timeline: true` and a `notes_later_timeline` sentence (Grok planned
  around a Great Scientist that exists only in a t257 note); an `inspect` refusal for an object that takes an
  id says where the ids come from (`hint`: city-state ids are the `minor: true` rows of `inspect(what="civs")`,
  likewise unit, city, civ) and a plural miss (`city_states`) names the object meant; the playbook
  answers `city_state(s)`, `deals`, `trade`, `league` with the diplomacy section, which now says where
  city-state ids come from and that `votable` rows exist only during a league session.
  `tests/test_grok_t238_session.py`.
## 2.0.0 -- the tool surface: nine tools where 145 were (2026-10-26)

A major version because the listed surface changes wholesale while every old name still answers. The game is
modelled from one seat -- a clock, things to read, things I own to order, what the game asks, my memory, saves
and the seat, the rule book -- as nine tools: `turn`, `inspect`, `order`, `question`, `answer`, `notebook`,
`batch`, `session`, `reference`. Every reply that lists what can be done carries the complete `order()` call to
copy; the 145 one-tool-per-button names of the 1.x releases answer through the retirement map with `renamed`
on the reply, and `CIV5_RETIRED_NAMES=off` lists the nine alone. The listing went from 112 KB (~28k tokens) to
11 KB (~2.8k). Lua runtime v287 (text only since v285's `call` path). The stages are the entries below, newest
first; the model, the vocabulary and the risks are on GitLab #59 (milestone 2.0.0, issues #44 to #58).

**The Glama marks** (https://glama.ai/mcp/servers/ty-meador/civ-v-linux-mcp, TDQS). Scored 2026-10-04 across
144 tools: completeness 5/5, naming consistency 4/5, disambiguation 3/5, tool count 1/5 (B, 3.3/5.0).
**The 2.0.0 listing scored by TDQS itself (hosted report https://tdqs.dev/reports/pkoetitu83, spec 1.2,
2026-10-27, one manual call from the user's account; the `tools/list` reply sent and the report are
`docs/measurements/2026-10-27-tdqs-tools-list.json` / `-report.json`):** overall 3.4 (B); coherence 4.8 (A):
completeness 5, disambiguation 5, naming consistency 4 ("some names are nouns"), tool count 5 for nine tools
where 144 scored 1; description quality 2.8 (C), mean per-tool TDQS 3.3: `inspect` 4.6 (A), `question` 3.8,
`reference` / `answer` / `batch` 3.6 (A), `turn` 3.3 (B), `order` 3.1 (B), `notebook` 2.4 (C), `session` 2.0
(C). Every tool is flagged for the same three things: no MCP annotations (`readOnlyHint` and the rest), no
schema `description` on the parameters (0% coverage everywhere but `order`'s `action`), no output schema;
`order`'s invocation cost (14, the oneOf) makes it a shadow candidate of `answer` (cost 3), which the coherence
pass dismissed as no real overlap. The C tiers read the one-sentence descriptions of `session` and `notebook`
as run-on lists of subcommands with no statement of purpose, no `args` shapes and no return values. The scores after the changes of 2.1.0 are in that section. **Glama's own re-scan of the 2.0.0 listing (#58, read 2026-10-29):** scored 2026-10-28 00:30 across 9 tools, **A 4.4/5.0** -- completeness 5/5, naming consistency 4/5 ("mixes verbs and domain nouns"), disambiguation 5/5, tool count 5/5; against 2026-10-04's 5 / 4 / 3 / 1 (B 3.3) the two marks the milestone set out to move both read 5. The table on #59 carries both rows; milestone 2.0.0 closed with it.

- **Stage 4 of "The tool surface" (GitLab #56), the Codex half, and #49's Codex row (2026-10-26, late
  night).** A fresh Codex CLI session (0.160.0, `gpt-6.1-sol`) on a server listing the nine alone
  (`CIV5_RETIRED_NAMES=off` in its config) played Assyria t247: the briefing, nine ongoing units read, Ur's
  500-gold gift copied from its full view's row (influence 49 -> 89, allied), a note, the turn ended, t248
  reached -- ten calls, 77 trips, no refusal, no name the listing did not carry
  (`docs/measurements/2026-10-26-assyria-t247-codex-session.md`). It reported one listing gap, which is #49's
  Codex measurement: Codex renders a tool's schema as a TypeScript declaration and turned `order`'s `oneOf`
  into a union of the branches alone, so `id`, `args` and `action_id` vanished and `to` / `action` read
  optional (the row carried both and the call ran). `codex` is in `listing.FLAT_CLIENTS` now (clientInfo
  `codex-mcp-client`), and measured again the declaration carries every argument with `to` and `action`
  required; the ARCHITECTURE table has the Claude Code and Codex rows. The instructions say `status.todo (the
  briefing's decisions)`: Codex looked for `status.todo` on the briefing reply and spent one status call. Stage
  4 complete; #56 closed.
- **Stage 4 of "The tool surface" (GitLab #56), the league vote: the UN session at Assyria t244 through the nine
  tools, and what it found (2026-10-26 night).** The session's `votable` rows carried nothing to copy, and the
  vote itself failed: `league_cast_votes` still encoded its list as a Lua source string (`_lua_items`, the
  pre-v285 way) and the call path, which encodes a list itself since runtime v285, delivered a string --
  `league.lua:493: bad argument #1 to 'ipairs'`. Fixed: the votes go as the list they are (the dead `_lua_items`
  / `_lua_table` / `_lua_value` encoders are gone), and `harness/affordances/objects.py` `league_rows` gives
  every votable row `actions` (a yes and a no vote with every remaining delegate; a resolution with voter
  choices one row with the choice to pick) and the reply the vote call, and between sessions every
  `proposable_enact` / `proposable_repeal` row its `call`. Seen live through a fresh server on this code: the two
  rows on each of the two proposals, the vote copied from the Furs row (28 Nay, `votes_cast: 28`), the blocker
  cleared, and at t245 the ban failed 36 to 10 while the International Space Station passed; the proposal
  rows between sessions carry their calls (`docs/measurements/2026-10-26-assyria-t244-league-vote.md`). The
  league read counts as a choice read in the audit (32 replies list what can be done, all through rows).
  Also this turn: t240-t244 played through the nine (the Fur-for-Dye deal from the trade catalog's row, a
  policy and a Worker in one `turn(action="finish", actions=[...])`, three caravans from their options rows);
  `tests/test_league_vote_choice.py` checks the votes reach the wire as a table, `test_affordances` the rows.
- **The words, the last pass: every sentence of the source, not only the ones under known keys (2026-10-26
  night).** `audit.scan` reads every string literal of the harness source that is prose (a docstring, a Lua
  snippet, a bare name -- a handler reference in a row maker or a dispatch table -- are not sites), so a reply
  may carry a sentence under any key (`more`, `gone_note`, a digest summary, the reference book's "where"
  table) and the audit still sees it; the nine tools' own descriptions, which teach the old name beside the
  new call on purpose, are exempt. It found 81 more sentences naming an old tool (`recall()` under the
  notebook's `more`, `overview.idle_trade_units` in the unit-lost digest line, `map_window` in the briefing's
  caps, `wait_for_my_turn` in the seat notes, the compare and reference books' key paths, the game-over hints,
  the standing-order notes...) and two in the runtime (`city_actions.lua`, `comparisons.lua`: the idle-caravan
  aside); all say the new call, runtime v287 is text only (the 331-entry pin holds). The seam is empty under
  the widest rule the audit has had.
- **The words, continued (GitLab #56 follow-up; 2026-10-26 night): every refusal and aside in the nine-tool
  vocabulary, and the notebook found again.** The audit's keys now take in `err` and `note` (`audit.KEYS`): the
  26 refusal sentences and asides that still named an old tool (`accept_deal/refuse_deal` on a held trade table,
  `trade_catalog()` in the deal-item refusals, `available_research` on a free tech, `units()` / `available_unit_actions`
  on a unit order, `wait_for_my_turn` on a paused game, `load_latest / load_save` with no game, the notebook's
  `remember()` / `close_assignment` / `amend_assignment` / `give_order` / `cancel_order`, the standing order's
  `move_unit`, a human seat's `propose_deal` / `incoming_deal`) say the new call, and the survey's seam table stays
  empty under the wider rule. The notebook that answered no notes at t239 was a key that changed form, not a lost
  file: runtime v285 moved `game_key_facts` into the runtime file, where the map pattern's backslash survives, so
  the key's map part became `pangaea` where the inline snippet had made it `Assets_Maps_pangaea` -- every notebook
  written before 2026-10-25 (17 files) sat under the old form. `harness/game_parts/notebook.py` builds both forms
  from the same facts (`game_keys(info)`, `legacy_game_key()`) and `Notebook.adopt(legacy_key)` renames the old
  file to the current key once, when the current key has no file (two files are never merged); the live Assyria
  notebook was merged by hand (the t239 note is note 5, the assignments and orders are back) and the session
  server answered the five notes and both assignments at t240. Tests: `test_notes` (adopt once, never over a
  living file), `test_game_key` (both forms from the facts; `Game.notebook()` adopts).
- **Stage 4 of "The tool surface" (GitLab #56; 2026-10-26 evening), the Claude Code half: t239 from a fresh
  session through the nine tools.** A cleared Claude Code session played Assyria t239 with the nine as listed:
  twenty calls, 122 trips after the runtime install, every order a row copied from a read -- the Great Merchant's
  trade mission at Belgrade (+770 gold; Belgrade became the tenth ally), both empty cities on Research, the Worker
  automated, Portugal's denouncement answered and Shaka's offer refused through the gate, t240 reached
  (`docs/measurements/2026-10-26-assyria-t239-claude-code-session.md`, the ledger beside it). What it met that it
  should not have, fixed here: the `drill_down` row of a `units` actions read named `todo_actions` (it goes
  through `rows.act` now), `how_to_answer` on the leader and trade screens, `leader_screen_note` and the
  frozen-game refusal named `incoming_deal` / `accept_deal` / `respond_discussion` / `dismiss_discussion` (they say
  `question()` / `answer(choice=...)`), and those three keys are in `audit.KEYS`; `turn`'s description says
  `notes='new' / 'all'` (the session passed a sentence and was refused). Open: the notebook answered no notes
  under this game's key although earlier notes exist; widening the audit to `err` / `note` keys finds 27 more
  refusal sentences naming old tools -- the next words item; the league vote (t244) and the Codex session.
- **Stage 5a of "The tool surface" (GitLab #57, milestone 2.0.0; 2026-10-26): the runtime's strings in the
  nine-tool vocabulary, one text-only bump to runtime v286.** Every string literal of `harness/lua/runtime/*.lua`
  that named a retired tool (87 sites in 19 fragments: the blocker hints of `turn.lua`, the refusals of a
  policy, belief, dig, deal or city-state order, the tactical and preview notes, the `how` row of a city-state
  gift) now says the new call -- `inspect(what='options', view='research') then order(to='empire',
  action='research')`, `question() then answer(choice=<tech>)`, `turn(action='wait')` -- and the gift's `how`
  row is written as `order(to="city_state", action="gift_gold", id, args={amount})` by the runtime itself
  (the Python boundary still renders an older runtime's `minor_gold_gift` row). A unit action row's
  `target_tool` (`unit_mission_targets` / `unit_home_options`, an undocumented key) is `target_view`
  (`targets` / `home`), the view of `inspect(what="unit")` that lists the choices; `affordances/units.py`
  maps it back to the read it makes the row from. No `H.*` signature moved: `tests/fixtures/runtime_entries.json`
  pins the 331 entries and the 257 seat slots, and `tests/test_runtime_words.py` holds the runtime to the pin.
  New `harness/surface/runtime_audit.py`, the Lua side of the affordance audit: the string literals of every
  fragment (comments left out) under `audit.named_in`'s rule, a literal that is exactly a vocabulary value
  (`declare_war`, the city-state screen's button) counted as the value; the survey prints its table (empty) and
  the suite asserts it stays so. The city-state screen's buttons are `vocabulary.SCREEN_BUTTONS`, the one
  source for the listing, the action table and `order`'s description. ARCHITECTURE says who installs the runtime
  now: tunerd for a seat-bound connection, the client itself on a plain daemon, both at the next call after an
  edit. Seen live at Assyria t239 (a solo game on a plain daemon, the Claude Code session server): the first
  `turn(action="status")` after the edit installed v286 (392 ledger trips, the chunked shipping) and answered
  in the new words (the blocker hint, the automation notes); the next was the usual 4 trips.
- **Stage 4 of "The tool surface" (GitLab #56, milestone 2.0.0; 2026-10-26), the harness's own half: the
  profile and a turn through the nine alone.** `scripts/play_loop.py --profile` on the S10 save (Assyria t238)
  before the surface (a worktree at the commit before stage 0, the same runtime) and after: 72 trips both times,
  9.1 s against 8.9 s wall (`docs/measurements/2026-10-26-assyria-t238-profile-before-after.md`). New
  `scripts/turn_from_rows.py`: one real stdio server started with `CIV5_RETIRED_NAMES=off`, so only the nine are
  callable, plays a turn from the rows alone -- the briefing's decision rows, their reads, the first `call` each
  read hands back (or the decision's `choose` row filled from the read), a city-state's gift from its `full`
  view's row (`--gift <id>`), the league, then `turn(action="finish", actions=[...])`; `--dry-run` lists the
  orders and ends nothing. Seen live: t238 ended through four calls and 62 trips with a 250-gold gift to Yerevan
  copied from its row, and t239 came back; on t239 a dry run listed a Worker's, a Great Merchant's and two empty
  cities' rows (`docs/measurements/2026-10-26-assyria-t238-nine-only.md` and the transcripts and ledgers beside
  it). A first run failed on the driver's own mistake, `briefing` at the top of `turn` where the tool keeps it
  under `args`, and the validation error named the field before anything ran. Still open on #56: the league vote
  (t244) and the two fresh sessions (Claude Code, Codex), which are the user's.

- **Stage 3c of "The tool surface" (GitLab #55, milestone 2.0.0; 2026-10-26): every row in the nine-tool
  vocabulary, and the surface's invariants in the suite.** `harness/rows.py` is the one leaf that writes a
  `{tool, args}` row, and it now renders the new call: the makers (`harness/gate.py`, `harness/affordances/`)
  still name the old handler and its arguments, `rows.act` / `rows.pick` put the row through the retirement
  map (`forward.new_call`), so a gate's `actions`, a decision's rows, a unit's orders, every `call` / `buy` /
  `read` and every `answers` row reads `order(to="unit", id, action="move", args={x, y})` and never a name the
  listing does not carry; a `choose` name is the new name (`id`, `choice`) and sits where the row's shape puts
  it (`vocabulary.TOP_LEVEL`, the table the registered schemas agree with; `forward.new_call` reads it instead
  of the schema). The gate's words follow: `clear_with`, `read_first`, `alternatives` and `also` are the new
  calls (`gate.worded`), every `why` and the popup hint say them, the discussion gate marks a deal on the table
  (`deal`), and `dispatch.question_read` finds the popup's or screen's own read behind the new rows; the
  ledger's attention resolves a batch row to the old arguments (`attention.action_rows`), so plots and ids are
  still found. A row the Lua runtime hands up by its old name (a city-state gift's `how`) is re-rendered at the
  Python boundary; the runtime itself waits for #57. Tests (`tests/test_tool_surface.py` `InvariantsTests`): the
  listing is the nine and no more; every description under 2000 characters and every word of the vocabulary
  explained in its tool's description; `TOP_LEVEL` equals the registered schemas; every gate's rows, `choose`
  filled, resolve to a listed tool and a valid action on the gate's own question; the 145 map and the action
  table were already checked. The gate, affordance, briefing, todo, parity and discussion tests say the new
  rows; `test_gate`'s row check resolves through the validator instead of the old catalog's schemas.

- **Stage 3b of "The tool surface" (GitLab #54, milestone 2.0.0; 2026-10-26): TOOL_REPLIES, AGENT_INSTALL,
  README, ARCHITECTURE, LIMITATIONS in the nine-tool vocabulary.** `docs/TOOL_REPLIES.md`'s headings are the
  new calls (`## turn(action="finish")`, `## inspect(what="empire")`, ...) with every key unchanged, and
  `reference(book="playbook", section=...)` reaches a section by either name (`harness/guide.py` tries the
  heading, then the old name's call). README names the nine tools and teaches the loop in four lines
  (`turn(action="finish")` -> `question()` / `answer(choice)` -> `inspect` -> `order` -> `notebook`), and
  every feature bullet, AGENT_INSTALL's examples and short loop, ARCHITECTURE (a `Game.` method keeps its
  dotted name; the playbook served by `reference`) and LIMITATIONS say the new words; `docs/ROADMAP.md`
  carries the before / after picture (145 tools, 112 KB, ~28k tokens -> 9 tools, 11 KB, ~2.8k tokens, both
  from `scripts/tool_survey.py`; `survey.listing_sizes()` now measures the listing as listed). The audit's
  rule treats a script's file name (`scripts/finish_turn.py`) as no tool name. Tests: `TheWordsTests` reads
  the five docs with the audit's rule, `test_guide` checks a reply reference's heading is the call of an old
  tool whose description points at it and that both names reach the same section.

- **Stage 3a of "The tool surface" (GitLab #53, milestone 2.0.0; 2026-10-26): the instructions and the playbook
  in the nine-tool vocabulary; `reference("playbook", "orders")` prints the action table.** The server
  instructions are rewritten around the loop (`turn(action="finish")` -> `gate` -> `question` / `answer` ->
  `inspect` -> `order` -> `notebook`), under the 2000-character cut (`tests/test_guide.py`,
  `tests/test_stdio_server.py`). `docs/PLAYBOOK.md` (the `civ5://playbook` resource, `reference(book="playbook")`
  by topic) says the same loop in the new words, with the blocker table as the read and the order that clear
  each blocker, or `question()` / `answer(choice)` for a popup; the headings and topics are unchanged. New
  `harness/surface/table.py`: every order's target, action, required and optional arguments and an example row,
  and every object's views with their selectors, printed from the vocabulary, the retirement map and the forward
  map -- `reference(book="playbook", section="orders")` and the `orders` topic (`harness/guide.py`
  `GENERATED_TOPICS`) serve it, and `tests/test_guide.py` / `tests/test_tool_surface.py` diff the tool's reply
  against the table and check every target / action and object / view has a row. Every `hint` and `tool`
  sentence a reply carries names the new call (`harness/briefing.py`'s todo sentences, the standing-order
  pauses in `harness/orders.py` and `game_parts/unit_orders.py`, the digest's cut, the finish's "call again",
  the game-over hint, the production and queue refusals, the city-state rows); the `play_turn` prompt follows.
  The audit (`harness/surface/audit.py` `named_in`) now counts an old name in prose only as a call form or as a
  bare / backticked word that is not also a word of the sentence, a reply key or a gate name (`WORDS`), and
  never inside a call in the new vocabulary or a quoted value, so the seam reads: no prose site names a
  retired tool. The index lists the reply references (`docs/TOOL_REPLIES.md`'s headings, still the old names
  until #54) by their new call, and `reference(book="playbook", section='turn(action="finish")')` reaches one.
  `inspect`'s `unit` and `city` objects lose their default view: nothing read one unit or city alone (the row
  is in `units` / `cities`), and the listing no longer advertises a view the server refuses. Tests:
  `tests/test_tool_surface.py` `TheWordsTests` (the instructions and the playbook name no retired tool, the
  table from the validator's data), `test_guide` (the `orders` topic, the index), `test_tool_survey` (the audit's
  rule), the hint assertions in `test_briefing`, `test_digest_cap`, `test_finish_turn` follow.

- **Stage 2e of "The tool surface" (GitLab #52, milestone 2.0.0; 2026-10-26): the 145 unregistered;
  `mcp_call.py --list` prints 9.** Every tool module writes `@retired` (harness/mcp_server.py) where
  `@mcp.tool()` stood: the handler is registered -- its schema, guard, ledger and replay wrappers as before --
  and taken off the listing at once, so `tools/list` is the nine tools of 2.0.0 and nothing else (`reference`,
  the ninth, is the one old name that stays listed). An old name or alias reaches its handler through
  `find_tool` and the retirement map with `renamed` on the reply; the call wrapper now runs such a handler as a
  listed one ran -- in the worker thread with the request context (a `finish_turn` by its old name keeps its
  progress notifications) and a bad argument raised as the SDK's error with the signature appended (`_run_handler`
  `strict`). The nine reach the handler they dispatch to by its exact name (`find_tool(exact=True)`), never
  through the map, so they answer whether or not the old names do. New `--retired-names on|off`
  (`CIV5_RETIRED_NAMES`): off, an old name is unknown and `known_tool_names()` suggests no retired name -- the
  state a session that was never shown an old name plays in (stage 4's check); `scripts/check.sh` runs the tests
  marked `new_vocabulary` (pytest marker in pyproject) a second time with the map off. `survey.new_tools()` is
  the listing, `survey.tools()` the old catalog (the 144 retired plus `reference`), `listing_sizes()` the nine.
  One batch fix found by the nine-only turn: a list reply (`units`, `cities`) inside a batch no longer marks the
  batch refused (`run_batch` counted anything but an object with `ok` as a failure). Tests:
  `tests/test_nine_only.py` (the listing is the nine, a turn through the nine alone with nothing `renamed`, an
  old name unknown with the map off and no retired name suggested, the same name answering with the map on);
  the suite's tests that called old names through the server (`test_after_reads`, `test_call_ledger`,
  `test_guide`'s decorator scan, `test_mcp_progress`, `test_mcp_safety`, `test_stdio_server`, `test_tool_surface`,
  `test_tool_survey`, the `tool_names()` scans) follow the listing. Docs: README, AGENT_INSTALL (`--list` prints
  9, `--retired-names`), ARCHITECTURE, `scripts/mcp_session.py`'s usage in the new vocabulary, the measurement
  regenerated. Seen live at Assyria t238 with reads only through fresh stdio servers: `--list` prints the nine,
  `league_status` answers with `renamed: inspect(what="league")`, `how_to_play` answers, and with
  `CIV5_RETIRED_NAMES=off` `units` is "Unknown tool" while `inspect(what="units")` and `turn(action="status")`
  answer.

- **Stage 2d of "The tool surface" (GitLab #51, milestone 2.0.0; 2026-10-26): gate, ledger and the tool sets by
  `(tool, action)`; `--tools compact` and `call` retired; the spectator's action column.** New leaf
  `harness/surface/classes.py`: every set that decides how a call is treated is a `Keys` set of `(tool, action)`
  keys with `*` wildcards -- `MENU`, `ANYTIME`, `WAIT` / `LEDGER_WAIT`, `READ` / `HARMLESS`, `RESPONSE`, `SAVE`,
  `BATCH_EXCLUDED`, `REQUIRED_BLOCKER` -- written in the nine-tool vocabulary (`("turn", "status")` a read,
  `("turn", "finish")` a wait, `("inspect", "*")` every read of the world). A call's key is `of_call(name, args)`
  (a new tool's fixed fields; an old name's or alias's row in the retirement map) and the guard keys the handler
  it wraps by `of_handler(name)`, so `league_status()` and `inspect(what="league")` are one key and no set in
  `harness/mcp_server.py`, `harness/gate.py` (`resolutions_by_key`, was `resolutions_by_tool`) or
  `harness/call_ledger.py` names a bare tool (the ledger's `READ_TOOLS` / `WAIT_TOOLS` and the server's six name
  sets are gone). A ledger row carries `tool` (one of the nine), `action` (the label: `league`, `unit/tactical`,
  `city/produce`, `finish`, an answer's actual choice; none for `question` / `batch`) and `called` (the old name
  or alias the client used), computed by `classes.called_as`; its attention (`harness/attention.py`: `FOCUS`,
  `DEFAULT_RADIUS`, `GRID` by key) is read off the old handler's arguments the call resolves to
  (`dispatch.old_call`), so ids and plots are found under their old names whichever name the client used, while
  `args` stays what the client sent. The spectator (`web/viz/js/world.js` `callLabel`, `panels.js`, `app.js`)
  prints `tool · action` for a new row and the bare tool for an old one; a summary finds the unit or city
  through `refs` and a new call's `args`; `scripts/ledger_report.py` lists reads by the same label. With nine
  listed tools nothing needs hiding: `--tools compact`, `CIV5_TOOLS`, `CORE_TOOLS` and `apply_toolset` are
  gone; `call(tool, args)` is retired -- off the listing into `mcp_server.retire` / `retired_tools()` (the
  retired-handler table #52 fills with the 145), still answering by name through the retirement map with the
  inner call's new name on its reply (`forward.marked` keeps a `renamed` already there; `new_call("call", ...)`
  renders the call it wraps), refusing what is not a batch row. A batch row is classified by key:
  `turn(action="status")` and a save ride in a batch, `turn(action="finish")`, a load, the seat do not. Tests:
  `tests/test_read_tools.py` (the sets by action, an old name and its new call one key, the reads harmless, the
  `Keys` wildcards, the action label, `called_as`), `tests/test_retired_call.py` (replaces
  `test_compact_toolset.py`: `call` off the listing and the flag gone, the inner `renamed`, the catalog and
  describe, the batch refusals, a batch row by key, the guard by key), `test_call_ledger` (rows carry
  tool / action / called, `kind` by action), `test_gate` (the allow-list by key, every gate row's key in the
  vocabulary), `test_attention` and `test_viz_js` (the label and the summary under node) follow. Docs: README,
  AGENT_INSTALL, PLAYBOOK (the compact mode and `call` gone), VISUALIZATION (the row's new keys), ARCHITECTURE
  ("Classification by `(tool, action)`"), the measurement regenerated (the compact listing no longer measured).
  Seen live at Assyria t238 with reads only (cold start of the stack, fresh stdio servers with `CIV5_CALL_LOG`):
  the listing is 152 names without `call`; `inspect(what="league")` and `league_status()` are the same bytes and
  the same ledger key (`inspect · league`, the second with `called: league_status`); `tactical_view(unit_id)` and
  `inspect(what="unit", view="tactical", id)` both log `focus`, `refs {unit_id}` and 19 seen plots;
  `call(tool="league_status")` answers with `renamed: inspect(what="league")` and logs as `batch` called `call`;
  a `do` batch runs `turn(action="status")` and `turn_status` rows and refuses `turn(action="finish")`;
  `question()` says nothing is pending. One fix from it: the alias `summary` was logged as `called: overview`
  (the resolved name); the row now carries the name the client used.

- **Stage 2b of "The tool surface" (GitLab #49, milestone 2.0.0; 2026-10-25), the code: `order`'s schema as a
  `oneOf`, with a flat fallback per client.** `harness/surface/listing.py` writes the `order` tool's listed
  `inputSchema` from the action tables of `vocabulary.py`: `to` an enum, and a `oneOf` with one branch per target
  (`to` fixed by `const`, `action` its enum; `city_state`'s a string since the screen's buttons are an open list) --
  or the flat variant, `action` a string whose description carries the same verbs by target. `variant_for()`
  picks per connected client: `CIV5_ORDER_SCHEMA` / `--order-schema` when set, else `FLAT_CLIENTS` by the
  `clientInfo` name of the handshake (empty until a client is measured), else oneOf. `harness/mcp_tools/surface.py`
  keeps the SDK's own schema as the base and sets the variant before each `tools/list` through an mcp 2.x
  middleware (`mcp.middleware`; a 1.x server shows the environment's variant or oneOf). The server's own refusal
  is unchanged either way. `docs/ARCHITECTURE.md` carries the design and the per-client table, pending the three
  measurements (Claude Code from a fresh session on this server, Codex, the Grok client). Tests
  (`tests/test_tool_surface.py`): the oneOf branches match the vocabulary, the flat prose names every verb, the
  variant by environment then client, and through a client session the listing is oneOf for one client name,
  flat for one in `FLAT_CLIENTS` or under the env, back to oneOf on the next listing, with the malformed pair
  refused by the server.

- **Stage 2c of "The tool surface" (GitLab #50, milestone 2.0.0; 2026-10-25): every old name callable, with
  `renamed` in the reply.** `harness/surface/forward.py` reads the retirement map forward: `old_name()` says which
  catalog name an unlisted name means (itself, or through `ALIASES`, the server's former `TOOL_ALIASES` folded in:
  `summary`, `status`, `state`, `turn_state`, `digest`, `plots_around`, `research`), `new_call()` writes the new
  `{tool, args}` row for an old call's arguments -- the row's fixed words first, a FromArg filled from the old
  argument it names (`choose_goody_hut(goody=X)` -> `answer(choice=X)`), the arguments the new tool takes at its
  top level next, the rest under `args`, the split read from the new tool's own schema -- and `renamed()` renders it
  as a line to copy: `order(to="city", action="produce", id=3, args={"item": "BUILDING_LIBRARY"})`. The refusals'
  `example` row is the same builder on placeholders (moved out of `dispatch`); `harness/surface/schemas.py` is the
  leaf both directions read the registered schemas through. In `harness/mcp_server.py` one `find_tool(name)` says
  what a called name means -- a listed tool itself; an unlisted name (hidden by `--tools compact`, retired from the
  listing, or an alias) through the map to its old handler -- and both the call wrapper and `_run_tool_here` (batch
  rows, `call`) run that handler and put `renamed` on a JSON-object reply (a list reply such as `map_window`'s
  cannot carry it); the nine tools run the old handlers with `renamed=False`, so `inspect(what="league")` stays
  `league_status()` byte for byte, and a *listed* old name answers as it always did. `call(describe=true)` on an
  alias says `renamed` too; `unknown_tool_hint` keeps the aliases for its "Did you mean". Tests
  (`tests/test_tool_surface.py`): every one of the 145 names round-trips -- its sample arguments through
  `forward.new_call` pass the new tool's validation and dispatch back to the same handler with the same arguments
  (the two designed exceptions named: `players` -> `turn_status`, `known_world` -> `briefing`; the four
  `city_state` reads are parts of the composite; the question / answer rows dispatch on the live gate) -- an alias,
  a batch row and `call(describe)` carry `renamed` through the server, a listed name does not, a compact-hidden
  name's reply is the new tool's plus the key, and with the map switched off the nine still answer and the alias is
  unknown again with its hint. Seen live at Assyria t238 with reads only through a fresh stdio server: `summary` and
  `status` answer with `renamed` (`inspect(what="empire")`, `turn(action="status")`), `overview` without, under
  `--tools compact` the hidden `league_status` carries `inspect(what="league")`. `docs/AGENT_INSTALL.md` says once
  that the old names are retired, not removed.

- **Stage 2a of "The tool surface" (GitLab #48, milestone 2.0.0; 2026-10-25): the nine tools dispatch to today's
  functions.** `harness/surface/dispatch.py` reads the retirement map (#50's table, `harness/surface/retirement.py`)
  the other way: `INDEX` says which old names share each `(tool, action)` / `(what, view)` row, `resolve()` renames
  the arguments back (`id` -> `city_id`, `seat` -> `player_id`, `section` -> `topic`; one id becomes the list
  `todo_actions` takes; a selector the row itself fixes, `detail="digest"`, is dropped), tells the old names that
  share a row apart by the argument given (`DISAMBIGUATE`: a city's `governor` by `focus` / `avoid` / `automatic`,
  `great_work` by `their_work_id`, `empire policy` by the `POLICY_BRANCH_` prefix, `turn("status")` is `turn_status`
  and `turn("briefing")` the briefing or, with `detail="digest"`, `turn_digest`, `inspect("city", view="production")`
  with `item` prices it) or by which shape the arguments fit, routes a city-state screen button through
  `city_state_action`, and makes `inspect("city_state", view="full")` a `Composite` of its five reads merged under
  `summary` / `gifts` / `bonuses` / `gift_units` / `gift_tiles`. A call that cannot be routed is a `Refusal` naming
  the shape: the missing or unknown arguments by their new names, `accepts` (the old signature), one `example` row of
  the new tool, or the `choices` (every action of the target, every object of `inspect`). `answer(choice, args)`
  dispatches on the live gate: a fixed word (`accept`, `refuse`, `leave`, `accept_friendship`) needs none; a popup's
  resolver takes the choice in its own argument (`choice_arg`: the retirement rows' FromArg for the answer tools,
  `ORDER_CHOICE_ARG` for the order tools that clear a popup; a `POLICY_BRANCH_` choice unlocks), a leader's button
  number is `respond_discussion`, the tech chooser `set_research`. `harness/mcp_tools/surface.py` registers `turn`,
  `inspect`, `order`, `question`, `answer`, `notebook`, `session` and `batch` beside the 145 (unregistering is #52;
  `harness.surface.survey.tools()` still counts the old catalog, `new_tools()` the nine), each running the old handler
  through `_run_tool_here`, so the guard, the ledger row, the replay of an `action_id` and the reply are exactly what
  they were (`inspect(what="league")` returns `league_status()` byte for byte); `_run_tool_here` now hands the request
  context on, so `turn(action="finish")` keeps its progress notifications. `inspect` and `turn` are flat (`what` /
  `action` enums listed in the description with every view and action from `harness/surface/vocabulary.py`, the
  selectors optional on top: `id`, `view`, `x`, `y`, `radius`, `mission`, `kind`, `detail`, `since`, `limit`, `item`,
  `yield_type`, and `args` for the rest by the old name); `order`, `answer`, `notebook`, `session` take `action` plus
  `args`. `question()` reads the question the gate asks (the popup's read with its `answers`, the leader screen, the
  deal) with `gate` on the reply, or the turn's open decisions when nothing is asked. The ninth, `reference(section,
  book="rules")`, is the old tool grown a `book` (`playbook` serves `how_to_play`). `batch`, `turn` and `session` are
  not batch rows (`BATCH_EXCLUDED`). Tests: `tests/test_tool_surface.py` (13: every old name reached from its row
  with its arguments renamed, the shared rows by their disambiguators, the vocabulary and the index agreeing, the
  malformed refused with the shape and the example, every popup's answer and the leader screen, and through the
  server: the nine registered beside the 145, a merged family byte for byte, an order run with the old arguments,
  the other tools routing, question / answer following the gate). Not yet: `oneOf` on `order` (#49), `renamed` on
  the old names (#50), gate and ledger by `(tool, action)` (#51), unregistering (#52); the nine are hidden under
  `--tools compact` like any non-core tool. Seen live at Assyria t238 with reads only: 153 tools listed,
  `inspect(what="league")` / `inspect(what="units")` byte for byte with the old reads, `turn("status")`, `question()`,
  the `order` refusal with its example, `inspect("options", view="research")` with its `set_research` rows,
  `reference(book="playbook")`.
- **Stage 1c of "The tool surface" (GitLab #47, milestone 2.0.0; 2026-10-25): every choice carries its write.**
  `harness/affordances/` is a package, one module per concern: `decisions` (the briefing's rows), `units` (a unit's
  orders: `action_rows` for one engine action, `unit_actions` for the summary level, `annotate_unit` for a normal / full
  row), `questions` (the answers of #46), `choices` (every `available_*` reply) and `objects` (`units`, `cities`, a
  city-state's screen, a trade catalog, a paused order). Each choice row of a read keeps its keys and gains `call`,
  the complete write that takes it: `available_research` -> `set_research`; `available_production` -> `set_production`
  (not a faith-only item, nor a Venice puppet's purchase-only list) plus `buy` -> `purchase_production` (gold, or
  `yield_type="FAITH"`) when the city can buy it now; `available_policies` -> `choose_policy` per adoptable policy and
  `unlock_policy_branch` per branch with `can_unlock`; `available_beliefs` -> `found_pantheon` / `add_reformation_belief`
  (a founder, follower or enhancer belief is one argument of a religion call, whose rows the gate carries);
  `available_trade_routes` -> `establish_trade_route` by plot and connection type; `available_spy_cities` -> `move_spy`;
  `unit_mission_targets` and `unit_home_options` -> the `unit_mission` that sends the unit there; `available_city_strikes`
  -> `city_ranged_attack`; `gift_unit_options` -> `gift_unit`; `gift_tile_improvement_options` -> `gift_tile_improvement`;
  `city_state_gifts` -> the `minor_gold_gift` row the runtime already wrote as `how`. `available_unit_actions` and the
  normal / full `todo_actions` rows carry `call` beside every engine action (`read` too when it opens a chooser), every
  melee and ranged target and every promotion. `units()` rows carry `actions` (the summary read of the unit's orders),
  `cities()` rows `actions` (`available_production` and `set_production` with `item` to choose); `city_state_actions`
  carries `actions`, one `city_state_action` per button the screen offers now; `trade_catalog` carries the two deal calls
  with `items` to compose and, on each tradeable resource, a one-item `negotiate_deal` that asks their copy or offers ours;
  a conditional order that pauses or is refused up front names its rows (`resume_order` / `cancel_order`,
  `tactical_view`). `rows.rows_in` finds the single rows (`call`, `buy`, `read`) as well as the lists. The audit looks
  for a reply's composing method in every game mixin (not only the one named like the tool module) and counts
  `answered` / `with_object_rows` as row makers, so 28 of the 31 affordance replies carry rows and the three that do
  not only inform (`turn_status`, `city_state_bonuses`, `purchase_cost`). Tests: `tests/test_affordances.py` (every
  choice builder on live-shaped replies with the required arguments given, the object rows, the city-state and trade
  catalog rows, the paused order's rows; the fake-bridge turn now copies `call` rows out of its reads, one choice per
  decision), the normal-level todo_actions test reads the rows, the survey test names the three replies left. Seen
  live at Assyria t238 with reads only: `available_research` three techs each with its `set_research`, Assur's 27
  production items with their `set_production`, `cities()` / `units()` rows with `actions`, `available_policies`'
  `choose_policy` rows, `trade_catalog(2)`'s deal calls and a Horse ask. **Open:** the live turn played from rows
  alone (#47's last box) ends a game turn and waits for the user's go-ahead.
- **Stage 1b of "The tool surface" (GitLab #46, milestone 2.0.0; 2026-10-25): the questions carry their answers as rows.**
  `harness/rows.py` is the leaf that holds the row shape (`act`, `pick`, `is_row`, `rows_in`; `harness/affordances.py`
  re-exports it), so `harness/gate.py` can own its rows without a cycle: every gate now carries `actions` -- the read
  (`read_first`), the call that clears it with its `args` and `choose` naming the arguments left to pick, then the
  alternatives (`game_over` offers `exit_to_main_menu`; the wait gates `wait_for_my_turn(timeout_seconds=600)`) -- and a
  decision popup's rows come from the one resolution table (`popup_rows`: the read with the arguments the popup fixes,
  `available_beliefs(kind="pantheon")` for a pantheon and the founder + follower / follower + enhancer pairs for a
  religion, `available_production` with `city_id` to choose, the resolver with `POPUP_CHOICE_ARGS`, then the `also`
  resolvers with theirs). The promotion popup's read is `todo_actions` now, not `available_unit_actions` with a unit_id
  the popup never names. The ten question-shaped reads carry `answers`, one complete row per button or choice, attached
  where the reply is composed (the game mixins) so `do`, the loop and every client see them: `generic_popup` one
  `answer_popup` per button, `goody_hut_options` / `maya_options` (the choices still open) / `city_capture_options` /
  `free_great_person_options` / `faith_great_person_options` their choosers, `steal_tech_options` one `steal_tech` per
  (victim, tech), `archaeology_options` the dig's plot filled in, `discussion` the enabled response buttons (plus
  `accept_friendship(player_id)` when the leader proposes a Declaration of Friendship) and `dismiss_discussion`, a deal on
  the table `accept_deal` / `refuse_deal` / `dismiss_discussion`, `incoming_deal` accept / refuse when something is on
  the table. The audit treats `rows` and `affordances` alike. Tests: `tests/test_gate.py` resolves every gate's rows (all
  thirteen gate names, the fourteen popups and the generic one) to a registered tool whose required arguments are given
  or to choose; `tests/test_affordances.py` checks every answers builder on live-shaped replies and the mixins' wiring.
  Seen live at Assyria t238 with reads only: `gate` null, `faith_great_person_options.answers` three rows (Scientist,
  Engineer, Prophet), the other eight reads answer `[]` with nothing pending. `docs/TOOL_REPLIES.md` and the playbook's
  gate paragraph say so; the ten tool descriptions name `answers`.
- **Stage 1a of "The tool surface" (GitLab #45, milestone 2.0.0; 2026-10-25): the todo rows carry their calls.** New
  module `harness/affordances.py`, the one place a `{tool, args}` row is written in today's vocabulary (stage 2 swaps the
  words there and nowhere else): `act(tool, **args)` is a complete call, `pick(tool, choose, **args)` one whose `choose`
  arguments the model takes from the read before it. Every `decisions` row of `briefing` and `finish_turn(briefing=true)`
  (units, promotions, cities, research, an incoming deal, a stolen tech, a policy, stacked units, decision popups -- the
  popup rows come from `gate.POPUP_RESOLUTIONS`) and every `opportunities` row (idle trade units, idle spies) now carries
  `actions`: the read as is, then the order, exactly as `do(actions=[...])` and `finish_turn(actions=[...])` take them.
  A unit's one row is its `todo_actions(detail="summary")` read, and the summary's `actions` are the unit's orders
  themselves instead of bare type strings: one `unit_mission` per non-routine mission (AUTOMATE_* included), a build
  through MISSION_BUILD, a command through its own tool (`upgrade_unit`, `disband_unit`, `gift_unit` with `minor_id`
  to choose; other COMMAND_ types make no row -- live t238 an Infantry's COMMAND_GIFT had come out as a unit_mission
  row the engine refuses), a targeted mission (rebase, air strike, paradrop, nuke, a trade unit's new home) as the
  read of its targets then the order with `choose: [x, y]`, one `move_unit` per melee target, one MISSION_RANGE_ATTACK
  per ranged target, one `choose_promotion` per promotion. The prose `tool` sentence stays one release, lifted into
  the briefing's `tools` as before, with `tools_note` marking it retired in 2.0.0. `harness/attention.py` reads the
  rows of any batch-shaped argument (`finish_turn`'s `actions` too, not only `do`'s) through one `action_rows`
  walker. The audit (`harness/surface/audit.py`) counts a reply as carrying rows when its handler calls into the
  module (`row_makers`, `makes_rows`), and `briefing.py` is read only behind `briefing` / `finish_turn`, so the
  survey now says three replies carry rows (`briefing`, `finish_turn`, `todo_actions`) and `turn_status` hands the
  runtime's todo back by name; `docs/measurements/tool_survey.md` regenerated (full listing 110,642 bytes). Tests:
  `tests/test_affordances.py` (10: every row maker, every popup, every action kind, a fake-bridge turn played from
  the todo rows alone through `do`, and a check that the turn's test source types no catalog name but `do`), the
  todo_actions summary tests read rows and measure the saving on a 39-unit live-shaped reply (under 0.7 of normal),
  the survey test turns around. Seen live at Assyria t238 with reads only: an Infantry's and a Worker's summary rows
  (`gift_unit` to choose, `AUTOMATE_BUILD`), the t238 briefing (no decisions, so no `tools`).
- **Stage 0 of "The tool surface" (GitLab #44, milestone 2.0.0; 2026-10-25).** New package `harness/surface/`, one module per concern and nothing dispatching yet: `vocabulary.py` holds the nine tools' words (every `view` of every `what` that `inspect` reads, every `action` on every `to` that `order` gives, the actions of `turn` / `notebook` / `session`, the books of `reference`; `home` on `unit` is the one view #48 did not list, today's `unit_home_options`); `retirement.py` maps each of the 145 old names onto its row with the argument renames (`unit_id` -> `id`) and the `renamed` string a reply will carry (`inspect(what="map", view="window")`), with `check()` saying which names are unmapped, stale or off the vocabulary; `survey.py` computes the catalog by module, the zero-argument reads, the eight shapes of #44 as predicates over the map, what each new tool replaces and the `tools/list` reply's bytes and tokens; `audit.py` scans the harness AST for every `tool` / `hint` / `clear_with` / `read_first` / `also` literal and every `{tool, args}` row. `scripts/tool_survey.py --write` prints `docs/measurements/tool_survey.md`; `tests/test_tool_survey.py` (15) holds the baseline. Measured at 7f38d77: the module and shape tables reproduce #44 exactly; the full listing is 110,343 bytes (~27.6k tokens), `--tools compact` 32,711; the longest description (`finish_turn`, 1,987 chars) is under the 2,000 Claude Code shows, so no client clips today; `known_world` follows #50 to `turn("briefing", since="turn")`, so `turn` replaces 8 and `inspect` 46 against #59's 7 and 47; the seam stage 1 closes is 77 sites, and of the 31 replies that list what can be done only `todo_actions` already carries a row (its `drill_down`).
- **The tool-surface plan lives on GitLab, not in a doc (2026-10-25).** `docs/TOOL_SURFACE.md` is deleted; its content is
  on milestone 2.0.0: the model, the vocabulary, the touch list and the risks on tracking issue #59, the mapping from each
  of the 145 old names on #50, the baseline count on #44, the action and view tables on #48, and one issue per stage item
  (#44-#58) linked in dependency order. `docs/ROADMAP.md`, "The tool surface", keeps the stage table and the pointers.
- **The escape hatches connect like any client (stage 4 of "A seat bound to its channel"; no runtime change; 2026-10-25).**
  A server whose tunerd connection is bound to a seat plays that seat and no other: a different `--seat` (what
  `scripts/mcp_call.py` and `scripts/mcp_session.py` pass as `CIV5_SEAT`) is refused on every tool, naming the binding
  and the fix, instead of being overridden in silence; `set_seat` onto another seat is refused with `bound`, `set_seat()`
  lands on the binding without a detection trip, and a bound server never advertises `set_seat` in a gate; `detect_seat`
  returns the binding; the raw `lua` tool (`--allow-lua`) refuses before any trip. `Game.bound_seat` names the binding.
  `harness.cli`, `mcp_call.py` and `mcp_session.py` share the one client, bound by `CIV5_TUNERD_TOKEN` or unbound:
  nothing bypasses the daemon's table. `tests/test_seat_escape_hatches.py` (9 tests, the real daemon on a scratch
  socket). Seen live at Assyria t238 on a one-seat token table: all eight probes refused or allowed as designed, no
  turn ended, tunerd restored without a table. The two-agent words are written (`docs/AGENT_INSTALL.md`,
  `docs/PLAYBOOK.md`, README "Fair play", `docs/LIMITATIONS.md`); the live two-agent game is the next entry.
- **Two agents on bound sockets (stage 5 of "A seat bound to its channel", the last; no code change; 2026-10-25).**
  **Done 2026-10-25** (seen live the same night): the Alpha/Bravo hotseat (S2a, t229, loaded on a plain daemon after the Assyria game was quick-saved as `Ashurbanipal_0238 pre-stage5`) on a two-seat token table, one process per seat holding only its own token in its environment (`scripts/play_loop.py --seat N`, the `Game` object bound through the one client; the two processes were one OS user on one machine, so the token secrecy was organisational, as the words say it must be): the usual loop unchanged, blockers resolved, a Settler queued, two promotions, seat 0 ended t229-t231 and seat 1 t229-t230 in under a minute (the AI round between humans is short in this game), the tunerd log shows only `connection bound to seat N by token` and no refusal, and every turn end went through `call` on a bound daemon (the live turn through `call` stage 3 left open). From each agent's own process the eight escape-hatch probes landed as stage 4 says: a wrong pinned `--seat` refused naming the binding and the fix, `set_seat` onto the other seat refused with `bound`, `set_seat()` and `--seat auto` on the binding, `cli lua` to `InGame` refused with the named-calls hint, an untokened client refused unbound, the own seat's reads fine, and a seat's `units` read while the other seat is on screen answers `this seat is not active`. Saved as `Alpha-Bravo_0231 two-agents-bound`; the Assyria game reloaded after, tunerd restored without a table.

- **tunerd writes the seat into every call (stage 3 of "A seat bound to its channel"; runtime v285; 2026-10-25).**
  A client names a runtime entry and its arguments as JSON (`{"op": "call", "fn": "tactical_view", "args": [5, 2]}`,
  or `"calls"` for several in one trip) and the daemon writes `return H._call("tactical_view", <seat>, {5, 2}, 2)`
  itself, the seat being the connection's binding (a request naming another seat is refused; a daemon without a
  table takes the request's seat, so a solo game is unchanged). `dispatch.lua` inserts the seat at the entry's own
  slot, from `H._seat_slot`, generated at runtime build from the parameter lists; a name with no slot is refused
  unless it is one of the seat-free facts (`H.reference`, `H.game_facts`, ...). The daemon installs the runtime and
  the popup shim itself (`{"op": "runtime"}`, and before any `call`), from the source on disk, so a bound client
  ships no Lua at all: its `exec` / `query` to `InGame` are refused, and to a screen state (a popup, the leader
  screen) forwarded only while its seat is the active player. Python side: `Game.h(name, *args, pid=)` /
  `Game.hs([...])` replace every composed `return H.x(...)` body (142 rewritten by script), the 48 `InGame` bodies
  composed in `game_parts/*` became named entries (`H.production_check`, `H.purchase_cost`, `H.city_pop_order`,
  `H.end_turn_send`, `H.research_check`, `H.deal_snapshot`, `H.friendship_check`, `H.melee_refusal_facts`, ...),
  `H.diplo_event` / `H.plot_units` / `H.plots_around` take `pid`, `compare.lua_call` became `call_spec`, and the
  encoders and chunk budget moved to `harness/lua_wire.py` (re-exported from `harness.game`). `tests/test_seat_call.py`
  (32 tests): the wire text, the slot table, the dispatcher under Lua 5.1, the bridge's seat rules and free-Lua
  policy, the socket round trip, a static check that no Lua text reaches `InGame` from a game part, and a turn
  (reads, a move, research, production, the end of the turn) played against a bound client through `call` only.
  Seen live at Assyria t238 the same evening: a turn's reads through `call` on a plain daemon, and on a token-table
  daemon a tokened session's reads, an untokened session refused, `cli lua` refused for `InGame`; no turn ended.
  `docs/GAPS.md` "Stage 3 shipped".
- **The seat-argument survey (stage 2 of "A seat bound to its channel"; 2026-10-25).** `scripts/seat_survey.py`
  reads the runtime and the Python that composes Lua and prints where each `H.*` entry takes the acting seat;
  `docs/GAPS.md` ("Stage 2, the survey") holds the table. 207 of 263 entries carry `pid` (90 first, 102 last, 15
  in the middle), looked up as `Players[pid]:GetUnitByID(...)`, so an object id never reaches another seat's
  unit; the exceptions Python reaches are `H.diplo_event` (a write as the active team) and `H.plot_units` /
  `H.plots_around` (a caller-chosen team). Every `Game` method resolves `pid=None` to `Game.seat` and the MCP
  server never passes one, so stage 3 substitutes that one attribute. 137 ad-hoc Lua bodies: 49 front end, 40
  screen buttons and probes, 48 `InGame` bodies to fold into named entries. Docs and a script; no runtime change.
- **tunerd binds a connection to a seat (stage 1 of "A seat bound to its channel"; 2026-10-24).** `python -m
  harness.tunerd --seats FILE` (or `CIV5_TUNERD_SEATS`; `harness/tunerd-seats.example.json`) loads a seat table:
  entries bind a seat to a token or to an OS user's uid. A connection is bound by its peer uid (`SO_PEERCRED`) or
  by a token in its first message, `{"op": "hello", "token": ...}`; `exec` and `query` on a connection bound to
  nothing are refused with the reason (`unbound: true`), `ping` / `events` / `states` / `wait_state` stay open.
  An unknown token, a `hello` later than first, or a token for another seat than the uid's closes the connection.
  `harness/client.py` sends `CIV5_TUNERD_TOKEN` as the first message of every connection (reconnects included,
  not a trip), carries the bound seat as `Civ5.seat`, and treats an older daemon's "unknown op" as no table. The
  token is never in a reply, a refusal, the log or an error; the daemon warns when the table file is readable by
  other users, refuses a malformed table at start, and without a table is the daemon of before. The binding
  reaches `Bridge.handle(req, seat=...)` and nothing uses it yet (stage 3). 21 tests; the real daemon checked on a
  scratch socket with no game; `docs/AGENT_INSTALL.md` has the two-agent paragraph.
- **A "Great Person born" notice names the person and says whether it is still mine (runtime v284; live Assyria
  t238, 2026-10-24).** Two notices at the turn start and no new Great Person in `units()`. The engine's text names
  neither the person nor the city, but the hook's row carries the unit type in d1 (148 UNIT_MUSICIAN, 4
  UNIT_SCIENTIST; d2 is -1) and the engine's `GetNotificationIndex(i)` is that row's id. The digest row now carries
  `unit` and, for the unit of mine of that type born this turn, `unit_id` / `x` / `y` (`of_type_now` when none);
  `notification_log` joins the engine's list to the hook's rows by id and re-reads each Great Person notice now:
  `unit`, the unit while it stands, `of_type_now` (0 live) and `unit_gone` once the hook saw it born and it is not
  among my units any more. The t238 pair was a Great Scientist bulbed and a Great Musician's Great Work, both spent
  the same turn before the quick save (the call ledger's `do` row of 2026-10-15). The join also carries a located
  notice's `x` / `y` / `city_id` / `sites`. Two tests.
- **An assignment's unit says how far it stands from its post, and `review.max_distance` makes that a reason
  (runtime v284; live Assyria t238).** Assignment 4 (role defend, target Nimrud's plot) read on_track with its
  Swordsman three plots away and nothing to say so. Every unit row of a plot-targeted assignment now carries
  `distance` (hex distance, the shorter way round a wrapping map: `H.assignment_facts` carries the map `width`);
  `review.max_distance` (0 for a garrison) turns a longer distance into "SWORDSMAN 335873 is 3 plot(s) from its
  post (18,23), more than review.max_distance 0". Role words stay free: nothing is inferred from "defend". Both
  live garrison assignments were amended with `max_distance: 0`; assignment 4 reads needs_review. One test, one
  assertion.
- **`league_status` says when diplomatic victory is off (runtime v284; live Assyria t238).**
  `votes_needed_for_diplo_victory: 42` stood beside a World Leader resolution reading "Not allowed by this game's
  options". `diplomatic_victory_enabled` (PreGame.IsVictory, as the culture read already does) and, when false,
  `diplo_victory_note`. One test.

## 1.16.0 -- a quiet run that stays quiet, a refusal that names its rule, a game read from its first turn (2026-10-24)

- **choose_policy names an ideology tenet's level gate (runtime v283; live Assyria t208, 2026-10-14).** Universal
  Suffrage (level 2) was refused with the bare "cannot adopt this policy right now" while Avant Garde, Civil Society
  (level 1) and New Deal (level 2) were held. The policy screen opens level-2 slot i once level-1 slot i+1 is
  filled (level 3 the same over level 2), so one more tenet of a level needs two more tenets of the level below
  than the tenets already held at that level. The refusal now reads "a level-2 tenet needs 3 level-1 tenets adopted
  first (two more than the level-2 tenets already held); you hold 2 level-1 and 1 level-2" and carries
  `tenet_rule` {level, held_below, held_at, needed_below}. One test.
- **My own wonder's splash is an announcement, not a decision, and a leader's plain remark no longer wakes a
  quiet run (no runtime change; live Assyria t202-t204, 2026-10-14).** The engine names the active player's
  wonder splash `BUTTONPOPUP_WONDER_COMPLETED_ACTIVE_PLAYER` (wonderpopup.lua handles exactly that type); the
  harness knew only `BUTTONPOPUP_WONDER_COMPLETED`, so the briefing listed Cristo Redentor's splash under
  `decisions` with tool generic_popup, which then found nothing open. The name joins the swept announcements. A
  `leader_message` row in `DIPLO_UI_STATE_BLANK_DISCUSSION` (no buttons: "Very well.", Siam's "Our proposal to the
  World Congress succeeded, with the support of your delegation") is quiet unless its words read like trouble;
  an offer or demand still wakes, as does the status's discussion_pending. Two tests.
- **A Great Prophet that has spread its religion can no longer build a Holy Site, and the order says so (runtime
  v282; live Assyria t189-t190, 2026-10-14).** The Prophet spread Judaism into Belgrade (4 -> 3 charges), walked to
  its Holy Site plot and the build step paused with the generic plot sentence ("a tech, the terrain, a resource or
  an improvement already there") while `Plot:CanBuild` was true on every plot around it: the engine's
  `Unit:CanBuild` is false for a Prophet with a spent charge. `H.order_facts` records `why: spent_spread` with the
  charges, and the pause reason reads "a Great Prophet that has spread its religion can no longer build a
  HOLY_SITE (1 of 4 spread charges used): an engine rule, not this plot; spend its remaining spreads with
  MISSION_SPREAD_RELIGION instead". One test.
- **A fight between other players no longer wakes a quiet run (no runtime change; live Assyria t185-t187,
  2026-10-11).** Portugal and Siam declared war on Shaka and every turn put four `damage` rows in the digest (a
  Portuguese Spearman, Zulu Impis), each ending a `skip_quiet_turns` run with nothing of mine in it. A combat,
  damage, unit_destroyed or unit_hurt row that names its players and names none of mine (`player`,
  `att_player`, `def_player`, or a side whose owner is "you") is quiet; a row naming no player at all still
  wakes, and a `wake_on` word naming the kind always does. One test; PLAYBOOK.
- **An unknown policy name is answered with the policies behind the shown names (runtime v281; live Assyria
  t181, 2026-10-11).** Freedom's first tenet is shown as "Avant Garde" and `choose_policy("POLICY_AVANT_GARDE")`
  was refused with a bare "unknown policy": the enum is POLICY_OPEN_SOCIETY, and only `available_policies`
  (enum beside shown name) told. The refusal now carries `did_you_mean` (every policy whose shown name or enum
  carries the asked words, with both) and a hint to `available_policies`; a name matching nothing stays a bare
  refusal. Verified live through a fresh v281 process at t182 (`did_you_mean: [{Avant Garde, POLICY_OPEN_SOCIETY}]`).
  One test.
- **A renewal offer of the import that gives us our only copy of a luxury says so (runtime v280; live Assyria
  t172, 2026-10-11).** Portugal's renewal of Truffles for our Salt read "we already have this luxury: no extra
  happiness" on the Truffles row, though the one copy we had was this deal's own import and letting it lapse
  loses the happiness. A received luxury row now carries `us_imported` beside `us_have` and reads "our only copy
  of this luxury is an import: renewing the deal that brings it keeps its happiness, a second import adds none"
  when every copy we have is imported; a copy of our own keeps the old wording, none at all reads new. Unit test
  only (the live offer was accepted before the fix).
- **A unit gifted to a city-state is `unit_spent` "gifted to Ormus", not "gone during your own turn with no
  combat" (no runtime change; live Assyria t168, 2026-10-11).** Two Archers and a Spearman sent with `gift_unit`
  came back in the digest with the generic own-turn note; the gift now records the consumed unit like every other
  order that uses one up (`Game._note_spent`: "consumed by your own order: gift_unit: gifted to Ormus"). One test.
- **The production rule reader knows the table's four location columns (runtime v279; live Assyria t163,
  2026-10-11).** Nimrud, on a hill, read the Windmill as "the engine refuses it; this read names no rule":
  `CMP.building_why` tested a `Hill` flag no stock building carries and not `Flat`, the Windmill's ("City must
  not be built on a Hill"). It now names Flat ("needs a city on flat land (this city stands on a hill)"),
  Capital ("needs the capital", the Palace), NearbyTerrainRequired ("needs TERRAIN_DESERT under or next to the
  city", the Solar Plant: the city plot or one of its six neighbours) and ProhibitedCityTerrain ("cannot be
  built in a city on TERRAIN_PLAINS", the Stone Works) -- the columns CIV5Buildings.xml actually uses beside
  Water / River / FreshWater / Mountain. Verified live through a fresh v279 process on Nimrud: the Windmill
  names the hill, the Palace names the capital (after "national wonder already built in another city"), the
  Stone Works names its Marble-or-Stone rule. And Big Ben read "names no rule" at t164 in Assur: it needs the
  Commerce branch opened (`PolicyBranchType`, as the Forbidden Palace needs Patronage and the Hanging Gardens
  Tradition), so the reader now names that ("needs the Commerce policy branch opened"), a game started after a
  wonder's `MaxStartEra`, a building's `ObsoleteTech` already known ("obsolete: Dynamite is known", the Great
  Wall) and `MinAreaSize` (the Colossus, Great Lighthouse and Harbor want a coast on a body of water of 10 plots
  or more). One test.
- **Two more quiet-run wakes with nothing to do are quiet (no runtime change; live Assyria t112-t116 and t162,
  2026-10-11).** "Portugal now Ally of Malacca!" (TXT_KEY_NTFN_MINOR_NOW_BEST_RELATIONS_ALL, a form the
  2026-10-11 list had missed) woke a `skip_quiet_turns` run at t162: `QUIET_ABOUT_OTHERS` now knows the engine's
  four "Ally of" forms about other players ("X now Ally of M!", "X is now the Ally of M.", "X has replaced Y as
  the Ally of M!", "X is no longer the Ally of M!"); my own "Now Ally of M!" / "No longer Ally of M!" (no civ
  before the words) and "Because you are the Ally of M" still wake. And a tech award or Who's Winning table still
  listed in the status's `pending_popups` at a turn start woke the run as `pending_popups` (t112, t115, t116) --
  the status is read before the sweep that closes those screens at the next end_turn -- while the same popup's
  `popup_shown` row was already quiet: the `QUIET_POPUPS` rule applies to that list too (a `wake_on` word naming
  the popup still wakes; any other popup there wakes as before). Seen live the same evening and added: the
  third-party declaration under its own summary ("Portugal and Siam Now Friends!" / "have made a public
  Declaration of Friendship", t164) is quiet, and the Great Person splash (BUTTONPOPUP_GREAT_PERSON_REWARD,
  which the harness closes itself) joins QUIET_POPUPS -- the "Great Person born" notice and the new unit in
  todo.units wake the run by themselves (t164, t165). The lost-alliance form "Siam now Ally of Bratislava!" /
  "more Influence over Bratislava than you" (t165) still wakes, as the test pins. Two tests extended or added.
- **A quiet run no longer wakes on other players' city-state ally changes, their denouncements, a city-state
  quest, "May Purchase With Faith" or "Your Golden Age ends." (2026-10-11; live Assyria t130-t157 read, unit tests).**
  Most wakes of a `skip_quiet_turns` run through the evening were notifications that decide nothing for this seat:
  "Zurich and Portugal now Allies!", "Yerevan has a new Ally!", "Siam has publicly Denounced The Zulus", "Public
  Declaration from Germany" (a Declaration of Friendship between others), "Mombasa desires Ivory", "Sofia wants Ormus
  bullied", "Kiev Seeks a Great General". `Game.QUIET_ABOUT_OTHERS` names the other-player forms; this build's text
  words the same events about me differently ("Influence over Yerevan has increased: they are now Allies!", "now has
  more Influence over Yerevan than you", "has publicly Denounced us!", "publicly denounced YOU"), so a text saying
  "you" / "your" / "us" or "Influence over" (`ABOUT_ME`) still wakes. `QUIET_NOTICES` (quests, the faith-purchase
  notice, the golden age's end, a quest a Great Person of mine completed -- "Malacca Recognizes Your Great
  Scientist!" -- and a city-state's request for units) are quiet whoever they name; a caller's `wake_on` word always
  wakes. One test added (fourteen quiet forms, six that still wake, the wake_on case). Seen live through a fresh
  process at t159-t162: "Ormus wants Sofia bullied" sat in the digest without waking the run, while "Portugal now
  Ally of Malacca!" (a form not in the list) and "Great Person born" still woke it.
- **A Great Work's unit is `unit_spent`, not "gone during your own turn" (2026-10-11; live Assyria t139 read, unit
  test).** `unit_mission(MISSION_CREATE_GREAT_WORK)` returned with the work's name and slot before the consumed-unit
  note every other Great Person mission leaves, so the Great Writer's delayed `unit_destroyed` row carried the
  generic note. The note now reads "consumed by your own order: MISSION_CREATE_GREAT_WORK: Don Quixote in Assur's
  BUILDING_ROYAL_LIBRARY"; a consumed unit with no new work found is noted with the mission alone.
- **A move refused for closed borders honours the engine's rival-territory flag, and a civilian's plot is named
  (runtime v278; live Assyria t135 and t141, 2026-10-11).** `give_order` / `move_unit` refused a Missionary bound
  for the Zulu capital with "no open-borders agreement" while the engine's own `Unit:IsRivalTerritory()` said it
  may enter (Missionaries, Great Prophets and Inquisitors cross closed borders by rule): `H.move_refusal` skips the
  border guard for such a unit. The one-civilian-per-tile guard had exempted every automated unit as "a caravan
  on its route", so a Great Prophet ordered onto an automated Worker's plot went to the engine and came back
  "no path"; now only a trade unit (`Unit:IsTrade()`) passes through, and the refusal names the blocker
  ("destination already holds your WORKER 475160 (automated; it still holds the plot)", `blocking_unit`). Three
  tests changed or added. Engine facts: `Unit:GeneratePath` is NYI in this build (no path pre-check is readable);
  a fogged plot that holds a unit refuses the pathfinder's destination, so a spread target beside a city may need
  another neighbour (t132-t143, La Venta, Yerevan, Sofia, the Zulu capital): the "no path" refusal now says when
  the destination is fogged (`fogged_destination`), without reading what stands there. Verified live through a
  fresh v278 process: the Missionary refused at t141 walked into Zulu territory at t143.
- **quick_save runs under a decision popup (no runtime change; live Assyria t97, 2026-10-11).** Warrior 32770 walked
  into the (15,21) camp and captured Mombasa's Worker: the BUTTONPOPUP_RETURN_CIVILIAN screen came up and the popup
  gate refused `quick_save` with everything else ("popup needs a decision"), though the rare screens are exactly
  what is worth a save before they are answered (`feedback_save_rare_screens`). `SAVE_TOOLS = {"quick_save"}` passes
  the popup check without sweeping anything; paused / not-my-turn still refuse it. The save was taken through
  `harness.cli lua "UI.QuickSave()"` this time and catalogued as S9 `Ashurbanipal_0097 return-civilian` (the quick
  save lives in `Saves/single/quick/`, not `Saves/single/QuickSave.Civ5Save`, a stale England file). Three tests.
- **Three more informational popups are quiet (no runtime change; live t103, t112-t113).** The great-work splash
  (BUTTONPOPUP_GREAT_WORK_COMPLETED_ACTIVE_PLAYER, right after my own MISSION_CREATE_GREAT_WORK) and the
  natural-wonder splash (BUTTONPOPUP_NATURAL_WONDER_REWARD) and the golden-age splash (BUTTONPOPUP_GOLDEN_AGE_REWARD,
  t123) join QUIET_POPUPS; a wonder completed still wakes.
- **A happiness dip inside the comfortable band is quiet (no runtime change; live t106, t109).** A quiet run woke on
  `happiness_drop:22->19` (a city grew) and `21->20` with nothing to do: a drop that still leaves 10 or more wakes
  only when it is 5 or more at once (a luxury lost); any drop below 10 wakes as before (HAPPINESS_COMFORTABLE,
  HAPPINESS_BIG_DROP; PLAYBOOK). One test.
- **A unit my own order consumed is `unit_spent`, not `unit_destroyed`, even when the engine reports it after
  turn_end (no runtime change; live t98, t108).** A Missionary's last spread and a Work Boat's fishing boats
  came as bare `unit_destroyed` rows in the AI round (delayed death) and each woke a quiet run as a loss.
  `Game._note_spent` records a unit the after-read found consumed (unit_mission, a batch's deferred read, an
  upgrade's old id, an order's build that consumed its builder); the narration turns that id's next
  `unit_destroyed` into `unit_spent` with "consumed by your own order: MISSION_SPREAD_RELIGION", once. One test.
- **The expiring-friendship hint stops promising a renewal the engine refuses (runtime v277; live t105-t110).**
  `expiring_friendships[].hint` said "propose_friendship to renew it" while `propose_friendship` answered "already
  friends (declaration still running)": it now says the engine refuses a new declaration while this one runs and
  to propose the turn after it lapses (Siam asked for it itself at t110 and accepted ours the same turn).

- **A production refusal names its rule, and the rule reader knows local resources (runtime v276; live Assyria
  t66-t75, 2026-10-11).** `set_production` refused a second Royal Library in Assur and a second Granary in Nineveh
  with "city cannot build this (missing prereq, already built, or one-per-city)": the refusal now carries the
  rules `compare(kind="production")` names (`H.production_why`: "city cannot build this: already built in this
  city", `why` list), the queue / unit-cap / trade-slot sentences still winning where they apply. And the Circus
  read "the engine refuses it; this read names no rule": `CMP.building_why` reads Building_LocalResourceOrs /
  Building_LocalResourceAnds against `City:IsHasResourceLocal` ("needs an improved RESOURCE_HORSE or
  RESOURCE_IVORY on a tile this city owns (an import does not count)"; the Stable names Horses, Sheep or Cow, and a
  pillaged pasture does not count -- read live through a v276 process at t75). One test.
- **A plundered caravan says so (no runtime change; live Assyria t70-t71).** The caravan to M'banza-Kongo came as
  `unit_destroyed` in the AI round and `unit_lost` at the turn start, beside the game's own "Filthy barbarians
  plundered the trade route" notice, and the unit_lost row still said "most likely its trade route ended and it
  is back home". With a plunder notice in the digest the row says "was plundered: ..." with `plundered: true`
  and the unit_destroyed twin is dropped (one row); without one the old reading stands. One test.

- **A quiet run wakes once per expiring deal and on whole words (no runtime change; live Assyria t65-t68,
  2026-10-11).** The Siam salt deal (ends t68, reoffer t69) sat on every status of its three-turn window and
  woke four `skip_quiet_turns` runs in a row with nothing to do before it ended: a deal, a declaration of
  friendship or a city-state ally about to lapse wakes the run the first time this process sees the row
  (`_expiring_new`, keyed on who / when it ends / the items, never on turns_left); the status lists it every
  turn as before. And "Nimrud has Grown! ... will automatically work the land" woke a run as an ally notice:
  WAKE_WORDS and `wake_on` match at a word start (`_word_hit`; stems keep their forms, "reward" is not war),
  with "allied" / "alliance" added beside "ally". Two tests.

- **A swept popup no longer wakes a quiet run (no runtime change; live Assyria t64, 2026-10-11).** Every
  `popup_shown` row ended a `skip_quiet_turns` run: the tech award and the Who's Winning table came together at
  t64 (turns_skipped 0, todo empty, research continuing from its queue). The three popups the harness closes
  itself with nothing to decide (`QUIET_POPUPS`: TECH_AWARD, WHOS_WINNING, NEW_ERA) are quiet now; any other
  popup still wakes, `wake_on` can name a quiet one, and research left unset wakes as `todo.research_unset`
  as before. One test.

- **Nine things the Assyria game's turns 31-63 showed (runtime v275; live 2026-10-10 late).** (1) Ancient Ruins that
  upgraded the Scout (t37) read as two "took 8 damage" rows and a Scout "gone during your own turn with no combat":
  one `unit_upgraded` row now ("your SCOUT at (18,31) ... became a ARCHER (new id ..., 92 hp kept)"), the inherited
  damage rows dropped. (2) MISSION_RANGE_ATTACK from a unit with no moves (a river crossing spent them, t38) answered
  ok with damage 0: the hard facts (no moves, attacked already, siege not set up, out of range) are refused up front.
  (3) A Worker's build the engine dropped mid-turn (t41, a Spearman two plots away) left the order "building" and the
  end of the turn refused: end_turn re-runs the orders holding a blocking unit before refusing (`orders_rerun`).
  (4) The unseen-turn reply's todo note for a unit under a paused order still said "re-issue move_unit" (t52): it
  carries the same resume_order note as turn_status. (5) resume_order compared the unit's plot with where the step
  was issued from two turns earlier and said "no path" without issuing (t53): a resume forgets the issue plot.
  (6) A build step whose unit stands elsewhere walks back instead of pausing "not on (x,y)" (t53). (7) A destination
  held by one of my own units is waited out for two turns before the order pauses (t55, the Settler crossing the
  Worker's plot). (8) The MISSION_FOUND refusal named no foreign city (t60, Malacca three plots away): `City:GetPlot`
  does not exist, `City:Plot()` does; the pcall had lost every reason. (9) city_ranged_attack on a plot out of range
  said "cannot range strike this turn": it names the distance and the city's range. Tests: test_assyria_t63.py and
  extensions in test_orders / test_combat_narration / test_mcp_safety. Not covered by a test: the resume reset (5),
  verified by reading only.

- **A new game's first turns, read (runtime v274; live Assyria t0-t25).** With the England game over, a fresh solo
  game (Assyria, Prince, Pangaea, Tiny, Quick: `Game.start_single_player(start=False)`, the PreGame speed / size /
  map / era setters on the setup screen, then `OnStart()`) surfaced ten things in twenty-five turns. (1) The founding
  Settler reached the first digest as `unit_spent` "gone during your own turn with no combat" beside `city_created`:
  the roster that names a gone unit is filled at turn starts and none had run at t0. `H.found_check` notes the
  settler first, `city_created` carries the city's `name`, and `_narrate_combat` folds a Settler spent the turn a
  city of mine appeared into that city row (`settler`, summary "your SETTLER founded Nineveh at (20,28)"; read live
  through a fresh process at t24). (2) `available_research` answered `[]` at t0 while the briefing listed research
  as a decision: the engine lets nothing be researched before the first city; the empty answer now says so (`techs`,
  `note`) and the briefing decision carries "settle first". (3) `research.lua` tried `PreReqTech` and `TechPrereq`
  after a missing `PrereqTech`, columns no table has, and the engine logged "Cannot find key" ten times per
  available_research; only `PrereqTech` is read (no lines through a v274 process). (4) "Assur has been founded."
  carried `hostiles: []`: an alert carries the list only when there is one (Nineveh's founding alert at t24 had two
  Brutes to list, so the empty case has unit tests only). (5) A unit whose order paused showed "queued move did not
  resume; re-issue move_unit" beside `order.status: paused` (`note_held_units`: the note now says resume_order /
  cancel_order / a new move_unit). (6) Yesterday's hostiles dedupe pointed a t14 alert at the t13 list (a Brute at
  57 hp on a plot it had left): one list per city per turn. (7) A direct move_unit given to a unit under a paused
  order never resumed at the turn start: `_arrive` skipped every unit with an open order; paused and failed ones
  are mine again. (8) `give_order` healed first and then paused on "move to (13,28)", a mountain: every later move
  step's plot is read when the order is given and one no unit can ever enter (mountain, impassable, off the map)
  refuses it up front; occupants, borders and the fog are left to the step's own turn. (9) `choose_policy` answered
  a bare "cannot adopt this policy right now" for Monarchy: the refusal names the prerequisite policies not yet
  adopted (`needs`), a branch not unlocked, or a policy already held. (10) MISSION_FOUND at (19,28), three plots
  from Assur, was refused as "too close to another city, water, or foreign territory": `H.found_check` carries
  `nearest_city` (named when its plot is revealed to me) with `min_distance` (MIN_CITY_RANGE + 1: distance 3 was
  blocked with the define at 3), `water` and `foreign_owner`, and the refusal reads "Assur is 3 plot(s) away and
  cities need 4" (unit tests; the next refused site reads it live). Twelve tests, three extended.
- **The briefing names the plots a neighbour took (runtime v270; live England t216-t217).** "Ashurbanipal used a
  Great General to steal some of your land!" was the whole notice at t216: no plot, while the map showed Assyria's
  Citadel at (57,40) with the plots beside London -- the unimproved copper tile (57,41) and (58,40) among them -- in
  Assyrian colours. `H.briefing_board` now lists the seat's owned plots (`territory`, "x,y"), the baseline keeps the
  list, and the next briefing's `changes.territory` carries `plots` {was, now}, `lost` (every plot mine at the
  baseline and not now, never cut, each filled in by one extra read made only then -- `H.territory_now`: who holds
  it, the improvement, the resource, fogged by the seat's own map) and `gained` (capped at `limit`,
  `gained_omitted`). A baseline from before this change compares no plots; a quiet turn costs no extra trip. Live
  through a v270 process at t217: the first briefing stored 44 plots, the second was quiet, and `territory_now` on
  the three stolen plots read Assyria on all three, COPPER on (57,41) and CITADEL on the fogged (57,40). Three tests
  (Lua board + reader, composer diff and cap, the scripted game's one extra read). `docs/TOOL_REPLIES.md` briefing.

- **A repair step completes when the plot is mended (runtime v271; live England t219-t221).** A Worker bought at
  t218 was given `move (59,39)` then `build REPAIR`; the farm was fixed in one turn and at t221 the order paused as
  "the unit cannot start REPAIR on (59,39) now", the chop defect of 2026-09-27 over again: `H.order_facts` knew
  when an improvement, a route or a removal was in place, and nothing for BUILD_REPAIR, so `done` never came. A
  repair row now carries `repair` and `pillaged` and is `done` when neither the improvement nor the route on the
  plot is pillaged any more. Verified live through a v271 process at t221: the repaired farm's row read done,
  pillaged false (the Worker had moved on, so no can_build). One Lua test (`test_a_repair_is_done_when_nothing_on_the_plot_is_pillaged`).

- **Four things the Ottoman war showed (runtime v272; live England t222-t225, 2026-10-10 late evening).** The
  Ottomans, Rome, Mongolia and Germany declared war within two turns (the Order bloc; six city-states along), and
  the first war turns found: (1) a `unit_spent` row ("gone during your own turn with no combat") for the Pikeman
  and the Great War Infantry that Rocket Artillery had just killed -- the finish_turn read cut short by a
  war-declaration screen began after the previous batch's turn_end and carried no marker of its own, so the
  classifier assumed my turn. `Game._narrate_combat` now remembers where the last batch stopped
  (`_digest_in_my_turn`) and a unit with a damage row of its own is never "spent". (2) `unit_mission
  MISSION_SWAP_UNITS` answered ok and nothing moved: the engine accepts the mission and does nothing in this
  build (an Infantry with full moves, a fortified Gatling Gun with full moves inside London); a raw MISSION_MOVE_TO
  onto the other combat unit is dropped too, and the GAMEMESSAGE_SWAP_UNITS net message **crashed the game**
  (relaunched; the memory note says never to send it). The mission is now refused up front with the two-move
  workaround (civilians still trade places through move_unit). (3) Rome's open-borders row read not legal both
  ways the turn after its deal ended while the Ottomans' went on the table: neither side held an embassy with Rome
  (its counter-offer asked for one). `trade_catalog.open_borders` now carries `our_embassy_with_them` /
  `their_embassy_with_us` and a `note` naming the Brave New World rule and the missing embassy. (4)
  `amend_assignment` with only a `note` was refused; it now writes the history line and reconciles the assignment
  (the scout the engine moved out of Ottoman land when the open borders ended had nothing to change). Also seen:
  `make_peace` refused by all four ("not the time for negotiation") the turn after each declaration, as expected;
  `available_city_strikes` read `can: false` with every enemy three plots out and the city's own range two (no
  defect); `MISSION_SETUP_FOR_RANGED_ATTACK` is not the name (`did_you_mean` says MISSION_SET_UP_FOR_RANGED_ATTACK).
  Four tests (narration carry-over, note-only amend, the swap refusal, the open-borders note).

- **The end of the England game, read (no runtime change; live t226).** London fell to the Ottomans at t226 (five
  civs and seven city-states at war since t223-t225) and the finish_turn reply said only `game_over`: with no
  winner in the log and `alive` false, it now carries `defeat` {text, last_city {name, x, y, by}} and the hint
  says which city was the last. The same reply had carried the eighteen-unit hostiles list on each of seven
  "London was bombarded" alerts: `_refine_events` keeps one list per city per digest and later rows say
  `hostiles_as_in` (the seq of the row that has it). Two tests. The game is over; `single/Elizabeth_0226 besieged`
  is the last turn, `single/Elizabeth_0214 claude` the state before the war.

- **`trade_catalog.open_borders` tells a deal in force from a missing embassy (runtime v273; live England t214).**
  The v272 note claimed the embassy rule whenever the row was illegal and an embassy was missing; a row is also
  illegal while borders are already open that way, and at t214 every open-borders deal (Rome, the Ottomans,
  Assyria, Portugal) was in force with no embassy on Rome's side. The row now carries `in_force` {we_give,
  they_give} and a note "already in force: ..." in that case, and reads the embassies only otherwise. Verified
  live on the reloaded `Elizabeth_0214 claude` save through a v273 process: all four read "both ways"; the
  MISSION_SWAP_UNITS refusal read live on the Rifleman there too. One test extended.

## 1.15.0 -- an unseen turn handed back, a notebook that follows an upgrade, a refused attack named (2026-10-10)

- **`upgrade_unit` carries the unit's assignments and open order onto the new id (2026-10-10; live England t214; no
  runtime change).** The engine replaces an upgraded unit, and the notebook kept naming the old id: live t206-t214 the
  Musketman -> Rifleman and Longbowman -> Gatling Gun upgrades left assignments 42 and 46 reading "gone ...
  amend_assignment(unit_ids=...) to take it over" for eight turns, with nobody amending. `Game.carry_unit_over(old, new)`
  (notebook mixin) re-points every active assignment naming the old id and the open order on it at the new unit with a
  fresh fingerprint, in one `H.assignment_facts` read (no read when nothing names it), writes a history line
  ("unit 630793 upgraded: now GREAT_WAR_INFANTRY 704524") and drops the order's `issued` record (the old unit's standing
  move died with it; the step is issued afresh, not read as "no progress"). `upgrade_unit`'s reply carries
  `carried_over` {unit, assignments [{id, role}], order}; a notebook problem is reported there, never raised. Live
  through scripts/mcp_call.py at t214: assignments 42 and 46 amended onto their Gatling Gun and Rifleman first, then
  `upgrade_unit(630793)` (Rifleman -> Great War Infantry, 135 gold) answered `carried_over.assignments [{46, defend}]`
  and `assignments()` read 46 `on_track` on 704524. Engine fact seen on the way: the upgraded unit keeps the original's
  `GetGameTurnCreated` (162, the Musketman's), so a fingerprint's `created` does not tell an upgrade apart; the type
  does. Three tests (`test_assignments`: `UpgradeCarriesTheNotebookTests`).
- **`compare(kind="production")` no longer calls the building under construction unbuildable (runtime v269,
  2026-10-09; live England t165).** `CvCity::canConstruct(building, bContinue=false)` refuses a building already in
  the city's queue, so the Windmill London was building read `can_produce: false` with "the engine refuses it; this
  read names no rule". A queued building that `CanConstruct(id, 1)` accepts now reads `can_produce: true` with
  `in_queue` (its 1-based position, as `set_production`'s queue counts it), `turns` (what is left) and a note; a real
  refusal still says so. `CMP.queue_position` reads the order queue the way `set_production`'s refusal does. One
  test (`test_compare`).

- **A turn that began while a leader screen was being answered is handed back, not ended blind (2026-10-09; no
  runtime change).** Live t147 (England): Spain's open-borders renewal came up at the end of t146, `accept_deal`
  answered it, the AI round finished during the answer, and the `finish_turn` the discussion reply asked for ("call
  again") met t147 cold -- it tried to end it, and only the research-unset blocker refused (with research set, the
  turn would have ended unplayed and the reply would have shown t148). `Game.unseen_turn`: my turn, its arrival
  still due (no wait or order of ours met it) and its `turn_start` still undelivered to this seat's digest.
  `finish_turn` on such a turn runs the arrival, takes the digest and returns it unended (`unseen_turn: true`,
  `woke_because: ["turn_unseen", ...what it needs]`, ended=false, a hint); with `skip_quiet_turns` and nothing in it
  needing the caller it counts as one of the quiet turns and ends. `finish_turn(actions=...)` on one runs none of
  the orders (they were reasoned about on the turn before): `batch` lists them as skipped. A loaded game records no
  turn_start and a digest another client already took counts as seen, so neither is handed back. Eight tests
  (`test_unseen_turn`: the hand-back, its reasons, the quiet pass, an opened turn, no turn_start, a bare fake, not
  my turn, the tool's batch).

- **A melee attack the engine drops is reported as a refused attack, not as an occupied plot (2026-10-09; no runtime
  change).** GAPS §0, live t200 (Mongolia): an Infantry in Karakorum, two moves, at war, ordered across the river onto
  a Russian Infantry; `tactical_view` called the step `attack`, the engine did nothing, and `move_unit` answered
  "(29,24) is occupied by another civ's unit; pick an adjacent free plot" -- the hint for a move, and wrong advice
  for an attack, which is a move onto an occupied plot. The pre-read already knows the order was an attack, so the
  refusal now reads "the engine refused the melee attack on Russia INFANTRY at (29,24) from inside a city across a
  river" and names the first closed attack gate this harness can read (no moves, already attacked, a unit that
  cannot attack by moving, embarked without Amphibious, the melee domain sentence, a target that is not adjacent);
  when every readable gate is open it says the rule is not identified and points at tactical_view for the plots to
  attack from. The reply carries `refused_attack` {defender, moves, from_city, river, ...}. The engine's own probe
  stays out of reach: `Unit:CanMoveInto` is nil in this build and `Unit:CanMoveOrAttackInto` reads false for every
  neighbour, empty own plots included (probed live, England t139, at peace). Finding the t200 rule still needs a war.
  Six tests (`test_refused_attack`); a plain move onto a foreign unit keeps the occupancy hint.

- **`explore_frontier` no longer hides the plots a foreign unit or city stands on (2026-10-09, runtime v268; live
  England t138).** The v266 `occupied` rows sorted after every free plot and the list was then cut at `limit`, so on
  any frontier longer than the limit they were gone: at t138 the scout at (63,14) had an Ottoman Rifleman on the
  frontier plot (63,16), two plots away, and Edirne's own plot (64,17) at three, and the two rows sat 59th and 60th
  of 143, out of reach of any limit the tool accepts (100). The cut now keeps the nearest `limit` free plots and,
  after them, every held plot no farther than the farthest free plot shown (at most `limit` of those), so
  frontier[1] is still a plot the explorer can walk to and the plots it must walk around are in the same reply. A
  visible city of another player on a frontier plot is named too, `city` {player_id, name}: move_unit refuses it at
  peace and a human sees the banner, and until now the row said only that a Great General stood there. Read live
  through the tool after the change: twelve free rows, then (63,16) `occupied` RIFLEMAN and (64,17) `occupied`
  GREAT_GENERAL + `city` Edirne. Two tests on a one-row world (`test_displaced_and_wars`); tool docstring.

## 1.14.0 -- the spectator map on a canvas, and two tech-debt sweeps (2026-10-09)

- **The spectator map is a canvas (2026-10-09; canvas migration phases 4 and 5 closed).** The side-by-side the plan
  asked for on a real game ran on two real recordings under `--replay`, the England game's 2026-10-08 recording
  (104x64, t133, 752 units, 77 cities) and the 72 MB 2026-09-30 hotseat one (80x52, 1,386 snapshots), in a real
  Chrome window with a 1540x898 map pane: the SVG page spends 44 ms a frame in a wheel zoom and 68 in a drag at the
  fit on the Large map (worst frames 75 and 132), the canvas page sits on the 16.7 ms frame through every gesture,
  paints a seat view in 33 ms against 135 and the rebuild on a seek backwards in 30 against 195; the heap is the
  same on both (the recording); the seat view at the fit and at 4x reads the same on both and the canvas tip gives
  the SVG's title text under the same points (table in `docs/CANVAS_MIGRATION.md`). So phase 5: `web/viz/js/map.js`
  (the SVG renderer) and the `?renderer=` switch are gone, `index.html` has one `<canvas id="map">`, `app.js`
  builds the `CanvasMap` directly, the CSS lost `svg#map` and the `.off` rule; VISUALIZATION's file table and map
  paragraph say so. New `scripts/viz_bench.mjs`: the measurement driver through the DevTools protocol (`measure`,
  `heap`, `shots`), each page in a fresh tab of a 1920x1080 window in front, page errors on stderr; it replaced the
  browser extension for this because the extension's tab came up 500x37 and hidden under COSMIC and its scripts
  stop at 45 s, and because a heap read across navigations in one tab counts the back/forward-cached previous page
  (about 67 MB a page on the big recording). CANVAS_MIGRATION: status, the real-recording section, the driver
  section, the re-measuring note.
- **Tech-debt sweep, session 2 (2026-10-09, docs only).** `docs/COVERAGE_AUDIT_2026-09-19.md` is marked historical
  and opens with a status table: each of its fourteen ranked gaps and the tool or runtime function that closed it
  (every one has a tool now; GAPS called the file "partly stale" and now points at the table). The three Lua API
  extracts of 2026-09-15 (`lua_api_full.md`, `lua_api_surface.md`, `lua_command_patterns.md`) carry a provenance
  header each: the date, what the list is, which runs of the DLL dump are neighbouring string tables rather than
  methods, and when to open which (probing a method name for `call` or a new read); ARCHITECTURE's repo layout
  names them and the audit. Every backticked repo path in the live docs resolves (two `harness/lua/runtime.lua`
  mentions were pre-v226; the audit's stays, as written). Checked and left: the 146th `@mcp.tool()` is `call`,
  so 145 is the right count everywhere; `_is_int` in `attention.py` and `compare.py` is the same one-liner twice
  and `J` in `cli.py` and `mcp_server.py` are two different formatters on purpose; 21 `H.*` functions are used
  only inside their own Lua file (making them local is a runtime bump for no reader); `test_liveness` leaks its
  socket directory only when a run is interrupted (the cleanups are registered). No code changed, 1475 tests.
- **Tech-debt sweep (2026-10-09, runtime v267).** One bug: the MCP resource `civ5://playbook` read
  `harness/docs/PLAYBOOK.md`, a path that never existed (the module sits one directory deeper than `guide.py`,
  whose `parent.parent` it copied), so every client that asked for it got "not installed"; it reads
  `guide.PLAYBOOK` now, with a test. Dead code out: `dismiss_city_state_greeting` and `dismiss_great_person_reward`
  (SetHide closers nothing called since the sweep closes both screens through their real callbacks),
  `unready_turn`, `events_peek`, `select_unit` (and its test), the `eval` conveniences on TunerClient and Civ5,
  `H.plunder_trade_route` in the Lua (the Python method goes through `unit_mission`; the version bump is for
  that line), `hex.distance` / `hex.toCube` in the page (never called; the Python `hexgrid` is the one in use) and
  the `export` on six page constants nobody imports; `scripts/play_turn.sh` (the pre-`llm_seat_loop.py` one-turn
  driver) and `scripts/turn_brief.py` (read a log nothing writes any more) deleted. Lint: ruff now also runs
  RUF100 (stale noqa), RUF059 (unread unpacked names), SIM115 (unclosed files), PLW1510 (`subprocess.run`
  without `check`), RET503, RUF034 and RUF015, and the code is clean under them: 59 stale `noqa` gone (the
  prose after them kept as plain comments), 19 unread names underscored, five bare `open()` reads closed, the
  spectator server's two fall-through returns explicit, `re.M`/`re.S` spelled out, `removeprefix` where a slice
  did it. The suite's three slowest tests slept for real (two end_turn message tests 6.8 s each, one deal click
  3 s): the fakes zero the settle constants / patch `time.sleep`, the run is 63 s instead of 77. ARCHITECTURE's
  repo layout lists the scripts, docs and `web/` as they are. The spectator server no longer prints a traceback
  when a keep-alive client resets between two requests (a closed tab; in the suite, a collected response object):
  `Handler.handle` swallows the reset `http.server` only expects as a timeout, with a test that resets a socket.
  1475 tests.
- **A canvas migration for the spectator map, planned and measured (2026-10-08).** `docs/CANVAS_MIGRATION.md`:
  why the SVG map's costs scale with the map (a zoom re-rasterises the whole tree, fog and borders re-join every
  plot per snapshot, the per-frame layers are DOM mutations) and the design that inverts them (one visible canvas,
  terrain and fog+borders cached as screen-space bitmaps re-rendered at zoom end, viewport culling, `hex.plotAt`
  hit testing and a tooltip div in place of `<title>`), in five phases with the SVG renderer selectable until
  Chrome parity. Phase 0 done: `scripts/synth_recording.py --size WxH` writes a synthetic recording (generated
  terrain, 600 units, borders, per-seat fog, calls with `seen`/`intent`/`refs`) and the SVG page was measured in
  Chrome at 104x64, 128x80 and 200x120 (table in the plan): a wheel zoom averages 36 / 63 / 113 ms a frame,
  the page's own redraw while pulses are live 21 / 57 / 104, a seat-view switch paints in 110 / 147 / 316 ms,
  56,421 SVG nodes at rest at 200x120. Phase 1 done: `hex.plotAt` (the inverse of `centre`: nearest hex centre,
  wrap-aware), `hex.visibleRange` (a zoom transform's plot window, clipped) and `hex.tracePath` (six corners onto
  any path-like object) with a node test (every plot of a 10x7 map round-trips, points near the corners too, the
  wrap column wraps, the fit transform shows the whole map, a close zoom a window). 1 test (1473).
  Phase 2 done: `web/viz/js/map_canvas.js` is the renderer behind `?renderer=canvas` (the SVG stays the
  default): the same surface as `HexMap`, one visible canvas composed from a terrain cache (hexes, rivers, glyphs,
  resource dots) and a world cache (a seat's fog, the borders) both rendered in screen space over the plots the
  viewport shows, re-rendered when a zoom gesture ends and blitted through the delta while it runs, and a live
  pass (heat and attention under `screen`, dashed intent outlines, cities, units with dashed civilian rings, stroked
  labels) on every redraw; `index.html` carries the canvas and a `#tip` div, `app.js` picks the renderer from the
  query string. Opened in Chrome on the 2026-09-30 replay and the 128x80 synthetic: observer and seat views, a
  wheel zoom to the city level, no console errors. Node test against a stub context: build() on a 20x12 map traces
  240 hexes, a close zoom confines the terrain and fog passes to the window (20 plots), the live pass draws only
  the pieces and attention inside it in the SVG's order and dashes, a mid-gesture frame only blits. 1 test (1474).
  Phase 3 done: hovering the canvas reads what the SVG `<title>` elements say. The live pass indexes the pieces
  it drew by plot, `CanvasMap.tipAt(sx, sy)` inverts the zoom transform and `hex.plotAt` to name the unit whose
  disc holds the point (the nearest of a stack, over the plot and its neighbours) or else the plot, and the pointer
  handler puts that text in the `#tip` div above the pointer (hidden off the map, during a zoom gesture and on
  leave; refreshed on every frame so a new snapshot under a still pointer updates it); `app.js` hands the div
  to the renderer. Chrome on the 2026-09-30 replay: five units and a plot probed on the canvas at 1x read the
  same text as the SVG titles under the same screen points, word for word; at a 4.6x wheel zoom the scout's
  hit disc measures 36x35 px (the drawn disc), the tip hides during the gesture, console clean. The node test
  gains the hit cases (the disc wins over its plot, the plot otherwise, null past the edge). 1474 tests.
  Phase 4 done: the canvas renderer measured beside the SVG one in Chrome, same script, same pane
  (1560x908 at dpr 1), on the three synthetic sizes (table in the plan). Every gesture and the live redraw sit
  on the 16.7 ms frame at every size (the SVG page: 51 / 87 / 148 ms a frame in a wheel zoom, 31 / 35 / 87
  while pulses are live); a seat-view switch paints in 33 ms at every size (SVG 244 / 157 / 347), the rebuild on
  a seek backwards in 33 / 33 / 50 ms (SVG 128 / 283 / 767), heap 7 / 11 / 8 MB (SVG 18 / 10 / 15). Parity: the
  seat view at a 3.7x zoom on 104x64 captured on both renderers under the same wheel ticks, fog levels, border
  tints, the dashed civilian ring, the grey out-of-colour cities and the stroked labels the same; a resize of the
  window refits the canvas and its backing store; console clean. One change from the profile: the fog and
  terrain passes fill hexes eight to a path (`paintHexes`), 2.5x cheaper than one fill per hex and 50x cheaper
  than one path for everything (Chrome's fill cost grows faster than the subpath count, measured 28 / 10 / 11 / 14
  ms for 1 / 8 / 32 / 128 hexes a path at 200x120); translucent strokes (rivers, borders) stay one per hex so
  the seams composite as the SVG's do. The live England game was not up, so that side-by-side is still to do.
  Next is phase 5, the switch. 1474 tests.

- **A seek on the scrubber applies the latest snapshot before the target, not every one on the way, and the
  recording streams in (2026-10-08).** A seek backwards rebuilt the page from the recording's first row and
  applied every row between: on the 2026-09-30 hotseat recording (72 MB; 1,386 snapshots from before the
  snapshot-cadence fix beside 106 other rows) that was 1,386 `setSnapshot`s painting nothing anyone saw, after the
  page had held the whole body as one 72 MB string to split it. `Timeline.plan(from, n)` is what a jump applies
  now: every call, event and status row in order, and of the rows that only replace state -- hello, snapshot, a
  seat's notebook -- the latest one before each call and before the target (a snapshot is the whole world; an
  earlier notebook is the later one's past; a call is painted against the world as it stood at the call, so the
  snapshot before it stays). `Player.seek` uses it in both directions; `step()`, playing in real time, still applies
  every row as it falls due. `feed.recording(since, onRow)` parses the `/recording` body off its byte stream a
  line at a time (`readLines`: lines joined across chunks, a blank line skipped, a half-written last line
  dropped) and hands each row to the timeline as it arrives. Measured under node against the replay server on
  that file: 1,492 rows in 2.6 s, 122 MB of heap, a seek to the end applies 122 rows (18 of the 1,386 snapshots,
  2 hellos, 4 notebooks, 35 calls, 63 events) where it applied 1,492. Seen in Chrome later the same night against
  the replay server: a drag forward to 1:53:52 painted t152 Venice, a drag back to 1:33 rebuilt t151 Mongolia with
  only the first nine calls and the t151 events in the panes, 70-72 MB of heap throughout and no console errors;
  `tests/test_viz_js.py` covers the plan and the reader under node. The page still holds every parsed row (a session's recording since the cadence fix is a few
  MB). The handoff's "undetected submarines show in a seat view" line was stale: done at f08f8fe (1.11.0).
  1 test (1470); `docs/VISUALIZATION.md`.
- **A spectator left running while another game is loaded draws the new map (2026-10-08).** The map was dumped
  once, when the poller attached, and never again: a `load_save` (or a new hotseat) under a running spectator left
  the page's terrain layer showing the old map under the new pieces, for as long as the spectator ran. Both
  spectator queries now name the map -- `mapdump` `key` and `snapshot` `map_key`, "WxH:" and one sum over every
  plot's terrain and relief (flat / hills / mountain: what a game never changes), the snapshot's off the plot
  loop its fog grids already run -- and `Live.step_snapshot` dumps the map again and pushes a new `hello` ahead of
  the first snapshot whose key is not the hello's (a `status` row names both keys; a dump that fails holds that
  snapshot for the next read). The page rebuilds its terrain layer on a hello as it already did; a recording with
  several hellos scrubs as before (`Timeline.plan` keeps the latest before each call). The dump still runs once per
  spectator start. Live t133 (England, read-only through the raw client): dump and snapshot both answered
  `104x64:962744005`, the snapshot in 0.16 s with 752 units. 2 tests (1472); `docs/VISUALIZATION.md`.

## 1.13.0 -- a spectator scrubber, a turn that arrives on its own, and what a human sees in a siege (2026-10-08)

- **Four things a human saw that the seat did not, from Grok's abandoned England game (2026-10-08, runtime
  v265, live t118-t127).** Grok (grok-shell-civ5) played England from t0 to t118 and stopped with London at 68 of
  250 hp inside a ring of twenty Songhai, Spanish and Portuguese units; the seat was picked up through the session
  server and played on to t127.
  - *Peace was there to be asked for.* All three enemies took a white peace on the first `make_peace` call at
    t118, every allied city-state along with them, and for twenty turns of siege no read had said so: a human
    sees the Negotiate Peace button every time they open a leader. `turn_state.wars` (own turn only) lists every
    war with the button's gate -- `peace` {ok, locked_turns, note} from CanChangeWarPeace / GetNumTurnsLockedIntoWar
    -- majors and city-states apart; the briefing's `warnings` carry one `at_war` row per major (`peace_possible`,
    the `make_peace(player_id)` hint or the lock note) and one `at_war_city_states` row.
  - *The gate named the wait while a leader was waiting.* After end_turn the AIs make their offers while my_turn
    is still false, and the gate put turn_not_active before the leader-screen checks, so `gate` said
    wait_for_my_turn, which returned at once with the same screen (Rome's open borders, Spain's co-operation
    question; the reply's own `discussion` block was right). The leader screen and the discussion now outrank
    turn_not_active; the engine-order test moved with them.
  - *The engine moved a unit and nothing said so.* The Great General sleeping in London stood one plot outside
    the city at the next turn start whenever a Caravan shared the city tile at the turn end (bought at t120, built
    at t124; a human sees the unit jump). `H.displaced_compare` runs at ActivePlayerTurnStart before the roster is
    rewritten: a unit of ours on another plot than the turn-end snapshot (or our last order) left it, that was not
    on a standing move or automation at the snapshot (`moving`), is a `unit_displaced` event {unit_id, unit,
    from_x/y, x/y, summary} with `shared_with` naming a trade unit of ours still on the tile it left.
  - *The host vote came alone.* The t118 notice named two proposals; `league_status` at t123 listed only "Choose
    Host" (the engine agreed: a special session, the regular one a turn later). `special_session`,
    `turns_until_session` and a `note` say so.
  - Also seen: a caravan bought this turn cannot take a route until next turn (the refusal said "no moves left"
    and finish_turn held the turn open, as designed); `make_peace` with Spain and Portugal carried their allied
    city-states as THIRD_PARTY_PEACE rows the screen seeded. 8 tests (1468).
  - *Read live afterwards (t127-t133, through the reconnected session server):* the `unit_displaced` row came at
    the t131 start exactly as built -- the General from (60,40) to (59,39), `shared_with` the Caravan built the
    turn before -- and `event:unit_displaced` woke the turn; the gate named accept_deal for Rome's, Persia's and
    Songhai's offers while my_turn was false; the arrival hook (a104091) ran on a new server's first order of a
    turn the old server had opened (`arrival.resumed_moves` on set_production's reply).

- **A frontier plot a foreign unit stands on says so (2026-10-08, runtime v266, live t129-t130).** `explore_frontier`
  put an Ottoman Gatling Gun's plot at the top of the list, then an Ottoman Worker's, and the scout's order paused
  on each ("move_unit would refuse ... holds a Gatling Gun of The Ottomans"); a human sees the unit on the plot.
  A frontier plot that is visible and holds another player's unit carries `occupied` {player_id, unit} and sorts
  after the free plots (still listed and still `reachable`: it is where the fog ends). 1 test (1469).

- **The retired headless deal path is gone from the runtime (2026-10-08, runtime v264).** `deals.lua` still
  shipped `H.propose_deal_headless_reference`, the scratch-deal Add*/UI.DoProposeDeal body that crashed the game
  eight times in 2026-09-16 and was retired the next day, plus the `H.propose_deal` stub that refused in its
  place; neither had a caller. Both are deleted; what the crashes taught (every Add* behind the UI's own
  IsPossibleToTradeItem gate, the Declaration of Friendship item crashing natively against an AI, AddPeaceTreaty
  crashing even paired) stays as a header note pointing at NOTES.md "Phase 3a", and the body is in git history.

- **A command that timed out no longer puts every later reply one command behind (2026-10-08).** The tuner
  client raised on a timeout but kept the connection, and the game still finished the command: its print lines
  and its completion ack arrived later. The next command's first ack was then the old one, so it returned at
  once with the old output (a query answered the previous question's JSON), and its own ack went to the command
  after it, until an idle moment let tunerd's pump drain the stream (between requests, never inside a burst).
  `TunerClient` now counts the ack a timed-out command still owes and reads past it (and the lines before it)
  before sending the next command or the state list; an idle drain that meets it counts it too. An ack that
  still does not come within `RESYNC_GRACE` (5 s) is a wedged game or a stream that cannot be trusted: the
  client raises ConnectionError, tunerd drops the connection and the next request connects afresh. 5 tests
  (1460).

- **A turn no wait of ours opened gets its arrival before its first order (2026-10-08, live t95).** On Codex's
  Portugal game, accept_deal answered a leader at the end of t94 while the AI round still ran, the round went
  on by itself, and t95 opened with no wait_for_my_turn in flight: the turn-start work (standing moves resumed,
  open orders run) had never happened, a worker's standing move stalled and a finished quarry's order stayed
  open. `Game.arrive_if_due(ts)` (the method the leader-answering tools already used, now taking a turn state
  already read) runs before every mutating tool and before end_turn when the turn has not arrived, once per
  turn; what it did rides on that order's reply as `arrival` (the wait's own `orders` / `resumed_moves` /
  `expiring_city_states`), or on end_turn's. The arrival marks itself done as it starts, so a failure in it is
  reported under `arrival.err` rather than silently retried. 3 tests (1450).

- **The spectator page has a scrubber (2026-10-04).** The page holds the whole recording on its own clock
  (`web/viz/js/timeline.js`, `scrub.js`): a bar under the map with play/pause, a speed from 0.5x to 64x, a slider
  whose ticks are the turn boundaries (the hue of the seat whose turn begins, grey for an AI round, click to jump),
  and the turn and elapsed time where the clock stands; Space, ← →, Home and End from the keyboard. A seek forward
  applies the rows between, a seek backwards rebuilds the world from the recording's first row (the viewer's zoom
  is kept), silence longer than 20 s is skipped while playing. Under `--replay` the page starts at the file's
  first row (the `--speed` server flag now defaults to 0 and only paces the stream); live with `--record` the same
  bar scrubs through everything this spectator recorded and a live button rejoins the tail. The server gained
  `GET /recording` (JSON lines, `?since=N`, the stream's seq numbers: a replayed file's rows keep theirs, a seq that
  restarts is renumbered the way `replay()` pushes it, a live recording counts from where this process began
  appending) and `/state` names `mode` and `recording`. Checked in Chrome on the demo recording: drag, keys, 64x,
  the ticks. 5 recording tests, 2 node tests (one lints every page module). Noted open since 1.10.0.

- **A paused order whose unit is gone closes at the turn start (2026-10-04, live t83-t89).** A settler's
  move order paused on a hostile two plots away; the settler then founded Braga by hand, and the order stayed
  listed as paused for six turns (`orders.open` 3, `paused` 1, a hostile that was long dead as its reason):
  the turn-start pass ran active orders only. It now reads the paused ones too and closes any whose unit is
  no longer mine (consumed, killed, captured, upgraded to a new id) the way `decide` says -- failed as
  `unit_gone`, or completed when its build is on the plot; a paused order whose unit is still there is left
  alone, and with no active order no turn claim is taken for it. 2 tests (1441).

- **The ledger's `client` and the claim's `holder_client` are filled for a stdio client too (2026-10-04, live
  t81).** A turn-claim refusal on Codex's Portugal game (seat 0, t81: the session's earlier server process
  held the turn after a client reconnect) carried `holder_client: null, same_client: false`, and not one of
  the 417 ledger rows a Claude Code or `scripts/mcp_session.py` session had written carried `client`: only the
  seat loops' `CIV5_CLIENT` ever labelled a row. `_client_info` read `request_context` off the server object,
  an attribute mcp 2.x does not have, and mcp 2.x spells the initialize field `client_info`, not `clientInfo`.
  The tool manager passes the SDK's per-request Context to `call_tool`: the label is read through it (both
  spellings), and the first one seen is kept for the turn claim, which is written off-request from a worker
  thread. Verified with a fresh stdio server: the row reads `probe/9.9`. 4 tests (1439).

- **A finished game is the wait's answer, with the winner (2026-10-04, live t253).** Russia won a Science
  Victory in the t253 AI round of the Mongolia replay: the engine went to GAMESTATE_OVER, `my_turn` never came
  back, `wait_for_my_turn` ran to its timeout and `finish_turn` answered `timed_out: true` with "still not my
  turn; call finish_turn again" -- under a `game_over` gate. The poll now returns the over state at once;
  `finish_turn` carries `game_over: true`, `woke_because: ["game_over"]`, `victory` {winner, type, text, turn}
  read from the game's own notification ("Catherine has won the game through a Science Victory!") and a hint
  naming `exit_to_main_menu`, whatever the quiet-turn budget. 3 tests (1435).

- **did_you_mean looks at both lists, and a hold on a unit already holding says so (2026-10-04, live t251).**
  The first live `MISSION_FORTIFY_HEAL` after 4e4c11e (a fortified Infantry on the Mongolia replay) answered
  `did_you_mean: ["MISSION_ROUTE_TO"]`: the unit's legal list had one weak match and the `or` between the two
  searches never reached the stock names. The nearest names are now scored over one pool (the unit's legal
  names ahead of the stock ones, ties kept in that order) and only the ones within 0.15 of the best are
  kept, so the answer is FORTIFY and HEAL, not REBASE and AIRLIFT as well. `MISSION_SLEEP` / `FORTIFY` /
  `ALERT` / `HEAL` on a unit whose legal list has `COMMAND_WAKE` and no hold at all (it is fortified, asleep
  or on alert already) carries a `reason`: it needs no new order, never blocks the turn, `COMMAND_WAKE` wakes
  it. 2 tests (1432).

## 1.12.0 -- a turn in one call, refusals that say what to do instead, a ledger that names its client (2026-10-04)

- **Three more refusals from Codex's 73 turns say what to do instead (2026-10-04).** A mission name the engine
  does not have (Codex t45: `MISSION_FORTIFY_HEAL`, which stopped a three-order `do` batch at its first
  order) answered only "unknown mission"; the refusal now carries the unit's `legal_missions` and
  `did_you_mean` -- the nearest real names, the unit's own legal ones first, then every stock MissionTypes
  name (`KNOWN_MISSIONS`) -- and names them in `err`. `MISSION_SLEEP` on a unit that can fortify (t63, a
  Warrior) and `MISSION_FORTIFY` on one that cannot (mounted, armoured, siege, naval, civilians) carry a
  `reason` naming the equivalent order, next to the legal list they already had. And an end refused with
  `NO_ENDTURN_BLOCKING_TYPE` over an empty todo (t35: an Archer's attack move, then "a unit or decision still
  blocks it"; the very next finish_turn went through) is the transient it looks like: `end_turn` grants it the
  one re-send a frozen blocker gets (`_nothing_blocks`), says so in `resent` when that lands, and when it
  still does not, the refusal says the engine named no blocker and to call again -- unless the engine's own
  diagnosis reports a ready or busy unit, which keeps the old wording. unit_mission's description names the
  sleep/fortify rule (1951 chars). 10 tests (1430).

- **Leftover movement is an open decision, not a cost (2026-10-04).** The playbook, TOOL_REPLIES and the
  `skip_actions` hint framed a unit with movement left as a refusal that "costs a round trip", which reads as
  an instruction to reach the end of the turn by the shortest path. They now say what the engine means: the
  unit can still act this turn, `todo.units` is the list of decisions still open, and `skip_actions` is for the
  units the player means to leave, with a real order (a second move, an attack, fortify, sleep) the first
  choice. Wording only; no reply key changed (1420 tests).

- **What Codex's first 73 turns taught (2026-10-04).** Codex (gpt-6.1-sol, single player as Portugal,
  t0-t73 in four sessions) drives the server from its own JavaScript `exec` sandbox -- one script holds
  several `tools.mcp__civ5__*` calls, so a turn is 9-10 MCP calls but one or two model requests, and
  `do` / `finish_turn(actions)` are moot for it; its transcripts are `~/.codex/sessions/*/rollout-*.jsonl`.
  Four things the ledger of its t29-t73 (443 rows) showed, each now fixed:
  - *Its own ghost held the turn.* A new Codex session after a context reset spawns a new server while the
    app keeps the old one alive, so the old process's claim read as a rival and two sessions waited up to
    180 s on themselves. The claim now records the holder's client label (`call_ledger.client()`:
    `CIV5_CLIENT`, else the MCP clientInfo); a refusal whose holder carries the caller's own label carries
    `same_client: true`, `holder_client`, and a sentence saying force=true is the answer at once.
    Different agents at one table carry different labels, so the hint never points at another model, and
    nothing is taken over by itself (`turn_claim.py`, `turn_status.turn_claim`; PLAYBOOK, AGENT_INSTALL).
  - *Units with moves left blocked the end five times in 48 turns* (a one-plot move, an attack), one extra
    round trip each: the rule lived only in the refusal text. finish_turn's description and the playbook's
    batch paragraph now state it, and an end refused for `todo.units` carries `skip_actions` -- the
    `unit_mission MISSION_SKIP` orders for exactly those units, ready as the next `finish_turn(actions=...)`
    -- with a `hint` (`end_turn.skip_actions` under finish_turn, top level under `end_turn`; TOOL_REPLIES).
  - *368 of 443 ledger rows named no turn* (every read and order; only the waits did). A row whose reply
    names none is stamped with the seat's latest known turn plus `turn_inferred: true`.
  - *The report printed an empty reason for every refused finish_turn*: the error is `end_turn.err`.
    `call_ledger.refusal_reason()` reads a refusal's own `err`, else `end_turn.err`, else a batch's first
    refused result, else `hint`.
  Also from the run: `reference` is a 48 KB single read and `known_world` ~22 KB each, the two largest
  replies; `tactical_view` was 42% of all bytes (2.4 per turn, 14 repeats of one unit within a turn). 6 tests.
- **The call ledger says which client made each call (2026-10-03).** A row carried `seat` but nothing
  about the model behind it, so the rows the Codex and Grok seat loops left on 2026-09-30 / 10-01 and the
  Claude Code session's rows could only be told apart by date and seat bookkeeping. Every row now carries
  `client`: `CIV5_CLIENT` from the server's environment when set, else the MCP initialize handshake's
  clientInfo as `name/version` (`call_ledger.client()`, read per call from the session's `client_params`;
  absent outside a request). `scripts/llm_seat_loop.py` exports `CIV5_CLIENT=<agent>/<model>` and a default
  `CIV5_CALL_LOG` (`logs/calls.jsonl`) to the CLI it runs, for CLIs that pass their environment on to the MCP
  servers they spawn. `scripts/ledger_report.py --client codex` keeps one client's rows, and the footer lists
  every label seen with its rows, seats and turn span. The Claude Code `.mcp.json` entry writes the ledger
  since 69253ff (verified live at t242: `/proc/<pid>/environ` of the server shows `CIV5_CALL_LOG`). 3 tests.
- **A turn's closing orders and its end are one call; a move says what it showed; a compact tool list for
  clients that pay for every description (2026-10-03, runtime v263).** The call ledger of the last live sessions
  put the floor of a turn at two calls (`do`, then `finish_turn`) and the median at five to seven, with the
  "move and look" pattern costing three (move_unit, tactical_view, units). `finish_turn(actions=[...])` runs
  the orders exactly as `do` would and ends the turn only when every one was ok; `batch` is on the reply either
  way, with `status` / `gate` and `ended: false` on a refusal. `move_unit`'s read-back asks the runtime for the
  difference in what the team can see around the unit since the order was sent (snapshot in the push's own
  trip, radius 12, IsRevealed / IsVisible only): `revealed` {count, plots, more, sighted} -- `count: 0` is
  "nothing over there". The 144 tools' descriptions and schemas are ~100 KB (~25k tokens) on every request of a
  client that does not defer them: `--tools compact` (env CIV5_TOOLS) lists CORE_TOOLS (24) plus `call(tool,
  args)`, which runs any other tool by name; `call()` is the catalog by domain, `call(tool, describe=true)` one
  tool's reference; batches and a hidden tool sent by its own name still run. Server instructions mention
  finish_turn(actions) and, in compact mode, `call`. 16 tests.
- **A turn that opens under a leader screen still gets its arrival work once the leader is answered (2026-10-03,
  live t221 and t225).** wait_for_my_turn returns at a leader's screen before the turn-start hook (standing moves
  resumed, open orders run), and nothing ran it afterwards: Mongolia's Great Merchant build step (t221) and Great
  Musician walk (t225) each sat out the turn as `stalled_mission` with their orders untouched. `respond_discussion`,
  `accept_deal`, `refuse_deal` and `dismiss_discussion` now run `Game.arrive_if_due()` when the table is free: the
  arrival once per turn and seat, never under a screen, with its `orders` / `resumed_moves` /
  `expiring_city_states` on the reply as the wait would carry them. 2 tests.
- **A queued leader's trade screen is read once its table has filled (2026-10-03, live t228).** An AI's trade screen
  opens a beat before its offer lands: behind England's war screen, Babylon's research agreement came back in
  `next` as screen=trade with no leader and no items, and was dismissed unseen. The hand-over (`queued_next`,
  shared by respond_discussion and the `_with_next` wrapper) re-reads an empty table up to five times at 0.3 s
  and reports the leader and `deal` of the offer; a table still empty after that says so in `next.note`. 2 tests.
- **A remembered route start explains a disappearance only on its own turn (2026-10-03, live t224).** The engine
  recycles unit ids: the Foreign Legion upgraded that turn carried the id of a caravan whose route to Guangzhou
  had started turns earlier, and the digest called the upgrade "your CARAVAN left on its trade route to Guangzhou".
  `H.route_starts` has carried the turn since it was added; the match now requires it. 1 test (1395).
- **finish_turn's digest drops events older than the turn before the one just ended (2026-10-03, live t208).**
  In the two-seat hotseat each seat's event cursor moves only when its own finish_turn takes a digest, and the
  seats had been played through briefing() (its own cursor) for ten turns: Venice's t208 finish_turn handed back
  turn_digest's whole 120-event cap, ~10 KB, from t198 on, and Mongolia's t208 the same with 454 more cut, when
  only the last two turns mattered. Events that predate the turn before the ended one were in that seat's own
  briefings already, so `finish_turn` now trims them from the merged digest (both the normal path and the hotseat
  hand-off timeout path) and says so under `digest.stale` (count, turns, by_kind, hint); turn_digest itself is
  unchanged. 3 tests (1389).
- **make_peace accepts the peace table the engine seeds with the enemy's allied city-states (2026-10-03, live
  t206).** The first turn Russia's and Portugal's Negotiate Peace buttons were lit after fourteen turns of refusals,
  the tables they opened carried the treaty pair plus `THIRD_PARTY_PEACE` rows for their war allies (Almaty;
  Zurich, Riga, Kiev, Jerusalem -- the engine adds them to the treaty itself), and the all-PEACE_TREATY test took
  that for a deal the AI had loaded: "the trade table already holds a deal with this player". A table of the
  treaty pair plus peace with city-states (`minor`) is now the seeded peace table (`_open_trade_screen` and the
  human-seat table alike); the opened table carries `allied_minors`. Both peaces then went through on the spot
  ("Very well."). 3 tests.
- **A one-shot Great Person mission that leaves the unit standing is refused (2026-10-03, live t205-t206).**
  Venice's Great Musician stepped onto Shoshone land with its last move and `MISSION_ONE_SHOT_TOURISM`
  answered ok: the engine had taken the push, recorded HOLD and done nothing (the unit was still there next
  read with the mission on offer; given again at t206 with moves left it was consumed). Like a pillage at 0
  moves, the engine drops the order silently. `unit_mission` (alone or inside `do`) now reads the unit back
  after a concert tour, political treatise, golden age, trade mission, bulb, hurry, Merchant of Venice
  purchase or fleet repair, and a unit still standing is ok=false with `consumed: false` and an `err` naming
  the plot, the moves left and what to do (no moves: give it again next turn before moving; moves left: check
  available_unit_actions and the plot). 1 test.
- **propose_deal places a research agreement / defensive pact / trade agreement once (2026-10-03, live t196).**
  The trade screen's pocket handler for these puts the pair on the table in one press (a row from each side);
  an item of the type asked from the other side pressed it again, and Venice's research agreement with England
  held two pairs and cost 468 gold instead of 234 (the deal is one agreement either way). A second item of a
  symmetric type is now skipped. 2 tests.
- **A refused ranged attack says which test failed (2026-10-03, live t193).** A Keshik rode three plots to
  shoot a Cossack and `MISSION_RANGE_ATTACK` came back only "action is not currently legal": the plot was two
  away by count but out of its line of fire. `unit_mission` now carries `reason` for a refused ranged attack,
  from the engine's own tests in order: no ranged attack, no moves, already attacked, a siege unit not set up,
  out of range (distance and range named), out of the line of fire from the unit's plot (CvPlot::canSeePlot
  with the attack range, the test tactical_view's `fire_los` shows), not visible, no enemy there. 1 test.
- **A hotseat seat's digest arrives at the hand-off, and a digest is capped (2026-10-03, live t192).** One
  session playing both seats ends each turn with `finish_turn`, which times out at once because the other seat
  is on screen -- and a timeout skipped the digest every time, so a seat's event cursor never moved: Mongolia's
  first digest that did complete (a war declaration stopped the wait) carried 350 events from 29 turns, 75 KB,
  past the client's reply limit. `finish_turn` now takes the digest on a timeout when the turn it ended is over
  and the other human seat is on screen (the boundary has passed; solo/LAN timeouts mid-AI-round still wait),
  and `turn_digest` keeps the newest 120 events with `omitted` {count, turns, by_kind, hint} for the rest
  (notification_log / briefing(since="turn") still have them); a quiet-turn run adds `omitted` up. 4 tests.
- **A sleep given with no moves left says it is only a hold (2026-10-03, live t182-t190).** `MISSION_SLEEP` /
  `MISSION_FORTIFY` on a unit that has already moved is recorded by the engine as HOLD, this turn's skip, and the
  unit is back in todo next turn; Venice's idle workers slept at 0 moves woke every turn while the bare `ok` read
  like a lasting sleep. `unit_mission` now carries a `note` when the read-back says HOLD for one of these orders:
  give it again next turn with moves left. 1 test (one assertion widened).
- **accept_deal names the deal it made even with another leader queued (2026-10-03, live t186).** The first
  of two renewals offered at a turn start (China's to Venice, Portugal's to Mongolia) came back with no
  `new_deal` and the stale t186 / 0-left rows, the last of each queue with a correct one: `current_deals` loads
  every deal onto the scratch table, so it refuses while the next leader's offer sits there, and the stamp was
  skipped. The new deal is then inferred from the rows -- it starts this turn and runs their `duration` -- as
  `new_deal` with `inferred` saying why, and the rows are corrected as before. 3 tests (one reshaped).
- **Runtime v262: ranged units are ranged again (2026-10-03, live t185).** The runtime asked
  `Unit:GetRangedCombatStrength()`, which this engine's Lua does not have (a nil method), and every caller guarded
  it with a pcall or an `and`, so a Crossbowman read as "not ranged" everywhere: `units()` rows said `ranged: 0`,
  `tactical_view.unit` / its occupant rows, the briefing's threats and map units carried no `ranged_strength`,
  the new `fire_los` never appeared, and `H.melee_targets` offered a Crossbowman melee previews (its neighbours
  read `attack` instead of "a ranged unit shoots it from here"). `H.ranged_strength` (helpers.lua) now asks
  `GetBaseRangedCombatStrength` (18 for that Crossbowman), keeping the old name as a fallback for test doubles;
  `range` prefers `Unit:Range()` so promotions count. 1 Lua test.
- **Runtime v261: tactical_view is sized to the unit's own sight (2026-10-03, live t183).** The view drew a
  fixed radius of 2 around every unit. The engine's `CvPlot::canSeePlot` (the test `canRangeStrikeAt` makes for
  a ranged unit that does not ignore line of sight, with the attack range in place of the sight range) says what
  this unit itself sees: high ground adds a plot, hills and forest in between block. Live t183 (Venice): a
  Crossbowman on hills saw 31 plots out to 3 and could fire at all of them, one on flat ground 24, a Musketman
  20 -- radius 2 listed 18 either way and never the ring a hill lets a ranged unit shoot into. `unit.sight`
  {range, on_hills, plots, reach} and, for a ranged unit, `unit.fire_los` {range, plots, reach, ignores_los}
  carry that; occupant and city rows say `in_sight` / `in_fire_los` (false = the team sees it, this unit does
  not); with no `radius` given the view reaches as far as the unit sees or shoots (at least 2, at most 5;
  `radius_from` = given / sight / default). Suggested by the user. 4 Lua tests, the Python bounds test updated.
- **propose_friendship waits for the reply screen (2026-10-03, live t182).** Babylon's "That will work. May a
  strong friendship lead to the flourishing of our empires." came up a beat after the ask, so `_friendship_result`
  (which closed the screen only when it was already there) answered accepted=true with no `screen_closed`, `reply`
  was Babylon's t171 line, and the next `finish_turn` was refused with a discussion gate. It now polls for the
  screen (the same ~1.2 s bound dismiss_discussion uses for a queued leader), reads the reply once it is up and
  closes it. 3 tests.
- **A refused purchase carries the engine's sentence (2026-10-03, live t182).** `purchase_production` copied
  reason / cost / balance / blocking_units from `purchase_cost` and dropped `engine_reason`: a Caravan bought the
  moment the last land destination was taken (Venice, after sending its caravan to Guangzhou) answered only "this
  city cannot train or build it" while `purchase_cost` had "You cannot construct this trade unit because there are
  no available land trade routes." The refusal now carries it too. 2 tests.
- **A purchase under a process reports no turns (2026-10-03, live t179).** A Bank bought while Venice ran the
  Research process answered `city_now_building_turns: 2147483647`; the engine's 2^31-1 for a process is now null
  with the "never completes" note `set_production` already prints. 3 tests.
- **Bare icons are spaced from the word before them (2026-10-03, live t175).** The public-opinion hover draws
  one ideology icon per unit of pressure straight after the civ's name, and `plain_text` read it as
  "PortugalIdeology OrderIdeology Order, Russia"; now "Portugal Ideology Order Ideology Order, Russia" (an icon
  before its own word still vanishes, no space is left before punctuation). 4 tests.
- **dismiss_discussion waits for the leader behind a plain remark (2026-10-02, live t174).** England's
  "glad you are friends with Russia" remark on Mongolia's turn start closed with a bare `ok`; Portugal's identical
  remark came up a beat later, so the hand-over `next` was empty and the next `briefing()` was refused with a
  discussion gate. After Back the call now waits for the dialog to close and for anything that comes straight
  back up (about 1.2 s at most), so `still_pending` / `next` / `gate` report the queued leader as the tool
  description promises. 3 tests.
- **Runtime v260: an ideology's free tenets are a policy decision (2026-10-02, live t173).** Mongolia adopted
  Freedom with two free tenets owed: `available_policies` said `free_policies: 0`, `can_adopt_now: false`,
  `choose_policy` answered `can_adopt_another: false` after the first tenet while the second was still due and
  `ENDTURN_BLOCKING_FREE_POLICY` stood. The policy screen enables a tenet button for culture, a free policy OR a
  free tenet (socialpolicypopup.lua) and shows a "Free Tenets" label, so `available_policies` carries
  `free_tenets`, counts them in `can_adopt_now` and says `tenets_only` when nothing else is affordable;
  `turn_status.todo.policy` lists them as `free_tenets`. 1 test.
- **The notebook key follows the seat (2026-10-02, live t173).** `game_key` was cached once per process from the
  first seat's leader and capital, so a session server started on Mongolia and moved to Venice with `set_seat`
  read an empty notebook under `...-Karakorum-...-seat0` while Venice's 35 notes sat under `...-Venice-...-seat0`
  (the briefing baseline and assignments hang off the same key). The key is now cached per seat (`_game_keys`)
  and dropped when a game is loaded or the menu is left; a `_game_key` set from outside stays a fixed key for
  tests. 4 tests (`tests/test_game_key.py`).
- **accept_deal names the deal it made (2026-10-02).** A renewal offer's rows carry the OLD deal's final turn
  (the engine clones the expiring deal onto the scratch table), so `accepted_items` said final_turn t161 /
  turns_left 0 for a deal just signed to run to t186 (live t161 Venice, China's open-borders renewal;
  `current_deals` had the right row). Once the deal count has risen, `accept_deal` reads the new deal off
  current_deals (this counterpart, started this turn) into `new_deal` and puts its end on the rows, the offered
  value staying as `final_turn_offered`, with `renewal: true` and a note when they differed. 4 tests. Live t171 on
  both seats: Russia's open-borders renewal to Venice and Babylon's open borders + 1 gpt renewal to Mongolia each
  came in with rows reading t171 / 0 left and went out as final_turn t196 / 25 left, `final_turn_offered: 171`,
  `new_deal` matching `current_deals`; four fresh deals (two research agreements, a friendship-era luxury swap)
  carried `new_deal` with no correction.
- **Ruff in the check (2026-10-02).** `scripts/check.sh` runs `ruff check` before pytest: pyflakes, bugbear and
  warnings only (`[tool.ruff.lint]` in pyproject; the layout rules stay off, the code is deliberately dense).
  The first pass found no bug in the harness: three bare re-raises now carry `from`, tunerd's duplicate
  `ConnectionError` clause is gone, a docstring with `[\LINK]` is raw, unused imports and loop variables are
  out, and a test lambda binds its loop variable. `ruff` joins the dev group. The stray zero-byte uv temp lock
  file is deleted and ignored; `docs/SESSION_HANDOFF.md` holds the current state only (history in git).
- **Runtime v259: a deal item's giver is the deal's other player (2026-10-01, live t162).** Catherine's
  renewal offer to Mongolia (deal from 1 to 7: our Ivory for open borders and 4 gold per turn) carried England's
  id on her two items, straight from the engine's `GetNextItem` (checked raw through `cli lua`); `incoming_deal`
  and `accept_deal` printed `from: 2` under a screen that said Russia. The trade screen places an item only by
  "ours or not", so `deal_items` now names anything not ours as from the deal's other player, with the raw id
  as `from_engine` only when it differs. 1 test.
- **Runtime v258: a deal already renewed is no expiring-deal warning (2026-10-01, live t161).** China offered
  the renewal of its open-borders swap at Venice's turn start and it was accepted; `current_deals` then holds the
  old deal (ends t161, 0 left) beside the new one (t161 to t186) until the turn ends, and `expiring_deals` /
  the briefing warned "re-offer on t162" about a deal that was already running again. An expiring deal whose
  timed items all appear in a later deal with the same civ now carries `renewed: true`, `renewed_until` (the
  new deal's end) and a hint saying nothing is to be re-offered, no `reoffer_on`; the briefing's warnings skip
  it and a quiet run no longer wakes for it (`turn_status.expiring_deals` still lists it). 3 tests.
- **Runtime v257: a build's name on the tech tree is words, not a Civilopedia link (2026-10-01, live t160).**
  The engine's 27 build descriptions read "Construct a [LINK=IMPROVEMENT_FARM]Farm[\LINK]"; the screen draws
  the tag as a link, and `available_research` / `tech_tree` / `compare` handed it out verbatim (Mongolia t160:
  Refrigeration's "Create [LINK=IMPROVEMENT_OFFSHORE_PLATFORM]Offshore Platform[\LINK]"). Both cleaners -- the
  Lua `plain_text` behind `plain_name`, and the Python `plain_text` every MCP reply passes through -- now drop
  `[LINK=...]` / `[\LINK]` and keep the word. No other Help, Description or Strategy text in the stock database
  carries the tag (counted live). 2 tests.
- **A seat view leaves out the units the game hides from that seat (2026-10-01, live t160).** The game does
  not draw an undetected submarine on a visible plot, but the spectator's seat view did (`docs/VISUALIZATION.md`
  named it as the simplification). The snapshot's unit rows now carry `h`: the human seats whose team the engine's
  own `Unit:IsInvisible(team)` answers true for (never the owner's team, never an ordinary unit, so the key is
  absent on nearly every row); `seatScreen` in the page keeps such a unit off that seat's map, the observer
  still draws it. Read live at t160 (399 units, no submarine yet, 0.10 s, no row changed); the Lua test fakes
  one barbarian submarine seat 0 has not detected. 1339 tests.
- **Announcement screens are closed for the caller, never handed back as a chore (2026-10-01).** A Great
  Person born, a city-state met, a wonder or an era raises a screen with nothing to decide, and the engine
  does nothing while it shows. The sweep ran inside `end_turn` and the wait's polls, but a screen raised at
  the turn's start landed after them and reads never swept: live 2026-09-27 (Codex c42, t116) `finish_turn`
  came back with `gate` announcement_screen and `woke_because` pending_popups / great_person_reward_pending,
  and the agent's next two calls (`wait_for_my_turn`, `briefing` again) only closed it. Now
  `Game.settle_announcements(ts)` runs before every guarded tool (reads included), in `turn_status`, and at
  the wait's arrival (on the late-discussion re-read, the one that sees it): a sweep only when the status
  says a screen may be up (`announcement_pending`: the two screen flags, a recorded popup with no decision
  in it, or `popup_up` with nothing recorded and no decision screen), the state re-read after it, and
  `swept_popups` naming what closed. Another seat's screens are never touched; a decision popup is still
  the agent's. The `announcement_screen` gate now means the close did not take. 17 tests
  (`tests/test_announcement_settle.py`), 1339 in all.
- **Runtime v256: an expiring deal says when it can be renewed (2026-10-01, live t159 Venice).** The
  `expiring_deals` row's hint claimed everything but a resource "renews now"; the China open-borders swap two
  turns from its end was refused as not legal (trade_catalog `open_borders` us/them both false). Open borders,
  a research agreement and a defensive pact stay committed like a resource; only gold per turn goes on a
  fresh table early. The row now carries `reoffer_on` (ends_on + 1) and the hint says so.
- **Runtime v255: a greyed buy button on a production row says why (2026-10-01).** An `available_production`
  row with a `gold` price and `can_buy` false now carries `buy_blocked` {reason, text}, the ladder
  `purchase_cost` climbs, without the second call per row: `gold` (balance of cost, only where the buy button
  exists), `stacking` (one per tile, `blocking_units` with unit_id and type), `unbuyable` (no buy button in
  this city), `engine` (the stock production popup's disabled-row tooltip) or `refused`. Live t156 Karakorum:
  2570 gold, every unit `can_buy: false`, and nothing on the rows said a Worker stood on the city tile.
  A row that can be bought, or has no price (national wonders, projects), carries nothing. `tests/test_buy_blocked.py`.
- **Runtime v254: three greyed buttons get their sentences (2026-10-01, live t153 Venice).** A `units` row
  whose `can_upgrade` is false now carries `upgrade_blocked`, the unit panel's red lines under the disabled
  Upgrade button (unitpanel.lua): `territory`, `city` (an air unit outside one), `gold` (price, gold),
  `resources` (each strategic short, needed / available) and `stacking`, each with the panel's own sentence;
  `unavailable` (with `prereq_tech`) when the target cannot be trained yet -- the panel then shows no button
  at all -- and `moved` when none of those holds. Live: three Warriors read `can_upgrade false` beside 2500
  gold and nothing said the Swordsman needs Iron ("You need 1 Iron to upgrade this Unit."); a Crossbowman's
  Gatling Gun waits on Industrialization. `gift_unit_options` carries the city-state screen's `influence_gain` and
  `travel_turns`, and while a gifted unit is still walking there (`in_transit.arrives_in`) the list is empty
  with `why_empty`; `gift_unit` is refused with that sentence instead of "move adjacent first" (live: the
  second Warrior gifted to Yerevan in one turn), and its reply carries the gain and the travel turns. The
  top bar's unit-supply string is a status alert: `{kind: "unit_supply", deficit, cap, used,
  production_penalty}` while the engine's deficit is nonzero (15 units of 14 supplied with a zero deficit --
  the engine counts military units -- is `overview.unit_supply.remaining -1` and no row, as on screen); a
  cap crossed or a deeper shortfall wakes a quiet-turn run (`unit_supply:<deficit>`).
- **A stale production blocker no longer refuses the turn before the popup sweep (runtime v254, live t153
  Mongolia).** The Great Artist's work raised the Great Work splash; `set_production` then expired Karakorum's
  "ready for a new construction project" notification, while the engine, frozen behind the popup, kept
  `ENDTURN_BLOCKING_PRODUCTION` pointing at it. `end_turn` refused on the blocker with `todo.cities` empty and
  never reached its sweep (the splash was still queued when the status it swept from was read); minutes later
  nothing had changed, and sweeping the popup by hand re-evaluated the blocker to none at once. Now
  `H.stale_blocker` covers PRODUCTION with no empty city and RESEARCH with research set like the UNITS case
  (`turn_status.blocking_stale`, the true hint); the send then meets the popup instead, and `end_turn` sweeps
  what is up, settles, and sends once more (`swept_first`). A popup the sweep cannot close is still a refusal.
- **An idle trade unit is not a stack (runtime v254, live t153 Venice).** `todo.stacked` left out a caravan only
  while it was on its route; a Caravan just bought into Venice read as a civilian stack with the Worker there.
  The engine sold that Caravan into a city already holding a Worker and a caravan while it refused a second
  Worker (and a Musketman beside the garrison) there -- a purchase runs the same one-per-tile check a move
  does, and trade units are outside it. Trade units are now never in a stack row.

## 1.11.0 -- a seat's own fog, a quieter spectator, the trade unit's second gate (2026-10-01)

- **A seat view draws only what that seat's screen shows (2026-09-30, live t152).** The spectator's snapshot
  carries each human seat's fog (`fog[<player id>]`: `v` visible, `f` revealed, `.` never seen, from the seat's
  team, in the same plot loop as the owner grid, so no extra trip; ~4 KB a seat on an 80x52 map). In a seat view
  never-seen plots are near-black and fogged plots dimmed; its team's own units and cities always show, other
  cities and borders only on revealed plots, other units only on visible ones. The observer view is unchanged; a
  recording without the grids falls back to drawing everything. Checked beside the Venice/Mongolia hotseat at
  t152: Venice's screen holds 29 of 394 units and 15 of 57 cities, the grids match the engine's own counts (387
  revealed / 120 visible; Mongolia 722 / 133). The map dump still never reads fog (the Lua test now enforces it
  per query). `scripts/spectator_demo.py` writes the grids too.
- **The spectator's snapshot is read when the world moves and pushed when it changed (2026-10-01).** The
  2026-09-30 hotseat recording was 72 MB, 1386 snapshot rows of ~52 KB at one every 8 s through three hours in
  which the game mostly sat at Venice's open turn; every row was a plot-loop trip on the seats' wire. Now a read
  identical to the last one pushed is dropped (stream and recording carry a snapshot only when something changed),
  and the cadence is 8 s only while the world moves -- a write- or wait-kind call landed, a runtime event fired,
  or the last read differed -- and 40 s (`snapshot_idle_every`) while it is still; a read-kind call stirs nothing. A
  write's settle read is never pre-empted by an overdue cadence read.
- **Runtime v253: the trade unit's second gate (2026-10-01, live t152).** Venice's briefing offered "4 free trade
  route slots: build or buy a Caravan / Cargo Ship" while the engine refused both kinds in its only city with "no
  available land/sea trade routes" -- the rule behind the t139 refusal GAPS had closed with the queue count. Past the
  slot count `CvCity::canTrain` asks `CvPlayerTrade::CanCreateTradeRoute(domain)`: some city of mine must be able to
  start a new route of that kind now (`Player:GetTradeRoutesAvailable()` is not that test; it listed 5 rows). The
  runtime asks the gate itself (`H.trade_unit_gate`: `CanTrain` per city and kind, the engine's own sentence from
  `CanTrainTooltip`); `overview` carries `trade_units_trainable` / `trade_units_refused`; the `trade_note` says
  "nothing to build or buy for these slots" with the engine's sentences (or names the one kind still buildable), the
  briefing opportunity carries `blocked`; `compare(kind='production')` `why` and a refused `set_production` quote the
  sentence instead of "city cannot build this".

## 1.10.0 -- the live visualization: watching the seats think (2026-09-30)

- **A read-only spectator and a d3 page (`docs/VISUALIZATION.md`).** `python -m harness.spectator --ledger
  logs/calls.jsonl` tails the call ledger, reads the runtime's event ring unfiltered and a players/cities/units/
  borders snapshot through the raw client (never `Game.q`, so it cannot re-inject the runtime), watches the
  notebook files on disk, and serves one sequenced stream over SSE with the page at `web/viz/`. The map is dumped
  once and drawn in greyscale; every plot a tool reply handed a model pulses once in the seat's hue and fades
  (targeted reads bright, broad scans dim), acts stay painted until the seat's turn ends, the previous seat's
  footprint stays as a ghost through the other's turn, a heatmap never resets, captions float over the plot and
  fade, and an Observer / Seat N switch cuts between the unfogged world and what one seat's replies contained.
  `--record` writes the stream; `--replay file --speed N` plays it back with no game; `scripts/spectator_demo.py`
  writes a synthetic recording for development.
- **The ledger row carries the call's attention (`harness/attention.py`).** With `CIV5_CALL_LOG` set, each row
  now also has `args` (compact, cut), `excerpt` (a write's or a refusal's reply, cut), `scope` (broad / focus /
  act / wait), `seen` (the plots the reply described: generic x/y walk, `revealed_map`'s vis grid by its window,
  the hex disk of `tactical_view` / `map_window`), `intent` (plots the arguments named, batches included) and
  `refs` (unit / city ids). Computed from the reply already in hand: logging still costs no trips.
  `harness/hexgrid.py` is the odd-r hex maths. 38 new tests (1196).

- **Checked beside a live hotseat (2026-09-30).** The Venice/Mongolia game reloaded at t150 (`load_save("AutoSave_0150
  AD-1600")`) and one full round played through the ledger-writing seat servers (`scripts/mcp_session.py --seat N`
  with `CIV5_CALL_LOG`): Venice's stop-spying answer, a `steal_tech`, `finish_turn`; Mongolia's Declaration of
  Friendship with Russia, a caravan to Funchal, Beshbalik's production, `end_turn`; Venice's t152 embassy deal. Every
  row reached the page in order (the tail is polled: a row can trail the ledger by a beat), the t151 -> t152 cut
  showed as the hard cut, refusals in red, both seat views. Recording `logs/spectate_hotseat_2026-09-30.jsonl`.
- **The page names the leader on a `leader_message`.** The ring row carries `player`, the caption read `from`: "The
  Shoshone: We would like to set up an embassy..." instead of ": We would like..." (live t152).
- **`set_production` takes the chooser's button name.** `set_production(city_id, "Zoo")` and the guess `BUILDING_ZOO`
  both resolve to the one row of the city's `available_production` list whose `name` matches (BNW's Zoo is
  `BUILDING_THEATRE`; the guess got `did_you_mean` of unrelated buildings, live t151 Beshbalik). The reply carries
  `resolved: {asked, item}`; two rows with one name, or none, still refuse as before. Live t152: "Artists' Guild"
  appended to Venice's queue as `BUILDING_ARTISTS_GUILD`, then removed. 4 new tests (1200).

## 1.9.0 -- the game is won, and cheaper unit orders (2026-09-29)

Tag `v1.9.0` = runtime v252 (unchanged since 1.8.0), 144 tools, 1158 tests. No runtime change in either batch:
a server restarted on this package serves both.

- **The last spaceship part says the game is won (live t502, solo China, S7).** `unit_mission MISSION_SPACESHIP` on
  the third Booster in Beijing completed the ship and the engine went straight to GAMESTATE_OVER, where its delayed
  removal of the part unit never runs: the read-back found the Booster standing in the capital with its 2 moves,
  the reply carried no `consumed`, and `spaceship_status` counted the part as `built_not_delivered: 1` beside
  `in_ship: 3`. Now `spaceship_status` reads `complete` once every part is in, `game_over` beside it, and a note on
  the lingering part; the mission reply on a completing part drops the stale position, says `consumed`,
  `ship_complete`, `game_over`, `victory: "science"` and where to go from there (`exit_to_main_menu`). No runtime
  change. `saves/` gains S7 (`Wu Zetian_0502 science-victory-eve`, the turn before that call) and
  `docs/LIMITATIONS.md`'s game-over row names the second stale blocker seen (`ENDTURN_BLOCKING_UNITS`,
  `blocking_stale: true`). `tests/test_science_victory_result.py` (5).
- **A unit order costs one trip less, a batch one trip per order less (no runtime change).** Measured live on the
  Venice/Mongolia hotseat at t151 with the call ledger (`CIV5_CALL_LOG`) and an in-process trace of every tuner
  query. Three things, each a trip: (1) the gate asked the game `discussion_pending()` before every mutating call
  although `H.turn_state` has carried that flag since runtime v214 -- `_refusal_for` now reads the status it
  already holds and asks only when the flag is missing; (2) inside a `do` batch every unit order read its unit
  back on its own (`unit_pos` / `automate_check`, the read that makes a reply say where the unit is and whether
  the order took) -- a batch order now answers an `after_pending` marker and the batch reads every such unit in
  one query at its end, folding each reading into its result (a result remembered for its `action_id` is
  remembered complete, so a replay never shows the marker; a read-back that fails says so in `note` instead of
  passing for a consumed unit); (3) the automate confirmation waited a fixed 0.25 s before its first read, and
  the plain read-back 0.2 s -- a net message lands on the next game frame (six pushes, MISSION_SKIP and
  AUTOMATE_BUILD, each seen on the first read 43-60 ms after the push), so the first read follows at 50 ms and
  polling (0.1 s, 3 s cap) is the fallback. Live t151 (ledger trips / seconds): a lone `unit_mission` 6 / 0.30
  -> 5 / 0.21; a two-order `do` 10 / 0.50 -> 7 / 0.31 (the game-side trips of a lone order are now
  `turn_state`, the push, the read-back). Inside a batch the readings are the state at the batch's end: two
  orders to one unit both report the later state. `tests/test_after_reads.py` (17 tests); 1153 tests.
  Closes the ROADMAP's "unit_mission trips" row.

## 1.8.0 -- the server in parts, how_to_play, gates that name the right tool (2026-09-27)

A long autonomous session on the MCP server: what a fresh agent sees (instructions, descriptions, the tool
list, the gate's `clear_with`), what a live fuzz and a live hotseat round turned up, and the server's layout.
Tag `v1.8.0` = runtime v252, 144 tools, 1136 tests. Three batches, in the order they were written: this one,
the install without a compiler, and the Game class in parts.

- **The trade-unit cap names its rule, and a caravan stays on its route (runtime v252).** The engine trains a
  Caravan / Cargo Ship only while trade units alive plus trade-unit orders queued in any city number fewer than
  the routes possible (`CvPlayerTrade::GetNumTradeRoutesUsed(false)`; the overview's used count is the alive
  half only). `H.trade_unit_count` reads the queues the same way: `overview.trade_units_queued`,
  `free_trade_route_slots` = available - used - queued, a `trade_note` that routes idle units and builds for
  the empty slots, and `compare` / `set_production` saying "N alive + Q queued of P" instead of "names no
  rule" (live t139: Venice "4 of 8" refused; t154: Mongolia 5 of 5 refused, Venice 4 of 8 allowed). The
  engine's route rows name cities, not units, and two caravans from one origin swapped between `trade_routes`
  reads (live t142); the first read that finds a caravan on exactly one open route records the binding in
  `H.route_units` (carried across re-injection) and later reads keep it while the unit is still an automated
  trade unit on that line and the route is the same instance; `unit.matched` is `recorded` / `line` /
  `line_ambiguous`. Tests: `tests/test_trade_route_units.py`, `tests/test_trade_cap_refusal.py`,
  `tests/test_trade_slot_note.py`.
- **`remove_from_queue(city_id, position)`.** The city screen's click on a queued item: nothing dropped one
  item from a production queue (`set_production` replaces the head or appends, and re-setting an item already
  queued is refused "already in this city's production queue (position N)"). The engine call is
  `city:PopOrder(index, 0, 0)`, 0-based, numeric flags (booleans are a Lua error; `Network.SendPopOrder` and
  `Game.CityPopOrder` do not exist in this build); the pop is verified by re-reading the queue, and the
  reply carries `removed` and the `queue` left. Found cleaning up the live check of the trade cap
  (Babylon t24); checked live t151 (Venice: a Worker appended behind Oxford University, removed by position,
  a position past the end refused). 144 tools. Tests: `tests/test_remove_from_queue.py`.
- **A policy that can be adopted is on the checklist (runtime v251).** `todo.policy` {culture, cost, free}
  whenever culture covers the next policy or a free one waits (not during anarchy), whichever blocker the
  engine reports first; the briefing lists it as a `policy` decision and a quiet-turn run wakes on it (live
  t149, Mongolia: PRODUCTION was reported first and the policy surfaced only when the turn end was refused).
- **`scripts/hotseat_rounds.py`**: advance a two-seat hotseat game until someone has to decide (greetings
  clicked through, plain embassy / open-borders swaps accepted with `--accept-swaps`), one fresh server per
  call. The loop one operator used to play both seats of the Venice/Mongolia game.
- **A permanent deal is never "expiring" (runtime v250).** An embassy swap (duration 0) read as ending the
  turn it was signed (live t145: `expiring_deals` listed Babylon's with `turns_left: 0`); only timed items
  count now.
- **`dismiss_discussion` clicks through queued greetings.** A cargo ship reaching a new shore met England,
  Babylon and Portugal at one turn start (live t145, Venice); one Back per call answered `ok: false` with the
  next greeting up. Now every greeting queued behind the first is closed too (`closed_count`, at most 8),
  stopping at a screen that needs an answer, which the reply hands over as `next`.
- **The briefing's idle-caravan row names the unit.** It read `id` off rows that say `unit_id`, so it
  printed `id: null` and `available_trade_routes(unit_id=None)` (live t141); it also carries the runtime's
  hint when the unit is not in a city.
- **`end_turn` re-sends once against a blocker the engine had not re-read.** `set_production` then
  `end_turn` in one batch (live t139, Mongolia) was refused with PRODUCTION named and no empty city: the
  engine re-evaluates the blocker on its next update and discarded CONTROL_ENDTURN against the old one.
  When the named blocker is stale (PRODUCTION with no empty city, RESEARCH with research set, or the UNITS
  case turn_status marks) the turn end is sent once more after a short settle; a real blocker is refused
  after one send as before. The reply says `resent` when that happened. An announcement popup that arrives
  after end_turn's own sweep (live t153: the Great Work splash a moment after the artist's order) is swept
  and the end re-sent the same way.
- **The trade-route cap is named (runtime v249).** `compare(kind="production")` on a caravan or cargo ship
  says "every trade-route slot already has a caravan or cargo ship (4 of 4)" instead of "the engine refuses
  it; this read names no rule" (live t139, Venice). `overview.trade_note` / the briefing's
  `free_trade_route_slots` opportunity say whether to route an idle unit or to build one: `trade_routes_used`
  counts running routes, so a free slot may already have an idle unit waiting for a route.
- **`units()` rows and `tactical_view.unit` say whose land the unit stands on (runtime v248).** `territory`
  {player_id, owner, city_state} when it is another player's; absent on own or unowned land. Live t137
  (Mongolia): "Trespassing in Kiev!" named the city-state and no read said which unit; the map shows the
  border under the unit to a human.
- **`accept_deal` / `refuse_deal` / `dismiss_discussion` hand over the next queued leader.** At a turn
  start several AIs can be waiting in a row (live t136, Mongolia: China, Portugal and Russia); the reply now
  carries `still_pending`, `next` (screen, player, leader, speech, buttons, the deal on the table) and the
  `gate` it raises, as `respond_discussion` already did, so the next order is not a surprise refusal.
- **A deal on the table gates with `accept_deal`, not `respond_discussion`.** `turn_status.trade_state` was
  already there; the `discussion` gate now reads it and names `incoming_deal` first, `accept_deal` /
  `refuse_deal` to settle (live t136: China's open-borders offer waiting at seat 0's hand-off had
  `clear_with: respond_discussion` and no buttons to press). `Game.turn_state` used to pop `trade_state`
  off the status, so the runtime's answer never reached a caller; it stays on now.
- **The AI round is named while a hotseat seat waits (runtime v246).** `turn_status.active_turn_active`
  says whether the seat on screen still holds its turn; when the last human has ended it and the AIs are
  moving, the `other_seat_active` gate says so ("seat 1 has ended its turn and the AIs are moving before seat
  0's begins; an AI round can take minutes") instead of "seat 1 is on screen" for the whole round (live t135:
  five minutes of it).
- **`expiring_deals.hint` says when a resource can be re-offered (runtime v245).** The old hint, "propose_deal
  to renew it before it ends", led straight to a refusal on the deal's last turn: the traded copy stays
  committed until the deal has ended, so the same Ivory was "not spare" (live t135, Mongolia to Russia). The
  hint now says to re-offer a resource the turn after; other items renew at once (wording final in v247). Runtime v244 (the
  `lua-civilian-refusal` branch: a civilian's move onto another own civilian's plot refused up front in
  tactical_view, and a trade unit on its route left out of `todo.stacked`) is merged, now that one player
  runs every server.
- **`harness/mcp_server.py` is a core plus one tool module per domain.** The 2,550-line server is now a
  510-line core (the game handle, seat logic, tool sets, `guarded`, the batch / replay helpers, the call
  wrapper) and ten modules under `harness/mcp_tools/` (turn, batch, notebook, units, cities, policies,
  diplomacy, trade, front_end, reference), cut the way `game_parts/` was. Every tool moved verbatim, registers
  in the same order, and is still an attribute of `harness.mcp_server`, so `mock.patch.object(mcp_server,
  "game", ...)` and `mcp_server.set_research(...)` work as before (the modules reach the patched names as
  `core.game()`). The three tests that scanned the server source scan the tool modules too.
  `python -m harness.mcp_server` runs the importable module, not the `__main__` copy `-m` makes (the tool
  modules import `harness.mcp_server`, so the copy served no tools: caught live by the first stdio client);
  `tests/test_stdio_server.py` now starts the real server over stdio, lists its tools and calls two.
- **`set_production` with an item of no known prefix is a refusal, not a KeyError** (live fuzz: every other
  enum-taking tool already refused readably; this one died with `harness error: KeyError: 'BOGUS'`).
  `_production_order` is the one prefix table for set_production and the purchase tools.
- **Parameters the descriptions left unnamed.** `notification_log` (limit, include_dismissed),
  `unit_mission_targets` (offset / limit), `explore_frontier` (limit), `purchase_cost` /
  `purchase_production` (yield_type "GOLD" | "FAITH", now accepted in any case and with or without the
  YIELD_ prefix; anything else is a plain refusal instead of a KeyError), `found_religion` /
  `enhance_religion` (city_x, city_y, custom_name), `recall` (limit), `choose_maya_bonus` (unit),
  `amend_assignment` (the assign fields).
- **`how_to_play(topic)`: the playbook and the long reply references as a tool.** Claude Code shows a
  model only the first ~2000 characters of a server's instructions and of each tool description; the
  instructions were 5000 (everything after `compare` was lost: batches, action_id, the gate rules, hotseat,
  the turn claim) and seven descriptions were over the cut (`finish_turn` 4200, `briefing` 3800,
  `turn_status`, `propose_deal`, `overview`, `compare`, `give_order`). The instructions are now 1750
  characters with the loop first; those descriptions keep what a turn needs and end with
  `how_to_play("<tool>")`, whose full text moved verbatim to `docs/TOOL_REPLIES.md`; `docs/PLAYBOOK.md` is
  served by topic (`start`, `turn_loop`, `quiet_turns`, `batches`, `verify`, `blockers`, `diplomacy`, `rules`,
  `first_turn`, `all`). The tool needs no game and works at any time (`harness/guide.py`); the `play_turn`
  prompt now starts from `briefing(since="turn")`. `tests/test_guide.py` caps every description and the
  instructions under 2000 characters. 143 tools.
- **`load_save` / `load_latest` work again.** The mixin split moved `LUA_DIR` into `game_parts/` and its
  relative path with it, so the GenericPopup shim was looked for under `game_parts/lua` and every load from
  the main menu failed (live, first cold start after the split). `tests/test_lua_paths.py` pins the folder.
- **The server's read list is the call ledger's.** `harness/mcp_server.py` kept its own hand-copied set of
  read-only tools, and seven reads had fallen off it (`notification_log`, `todo_actions`, `revealed_map`,
  `unit_home_options`, `gift_tile_improvement_options`, `free_great_person_options`, `steal_tech_options`):
  each was treated as an order, so it claimed the turn for the reader's process (a second client of the same
  seat reading `todo_actions` took the turn from the one playing it) and was refused under a popup or a
  leader remark. `READ_TOOLS` is now `call_ledger.READ_TOOLS` plus the two notebook writes that touch nothing
  in the game (`assign`, `amend_assignment`); `tests/test_read_tools.py` keeps a new read from drifting.

### Also in 1.8.0 -- install without a compiler or uv (2026-09-27)

Found by a fresh install on a Steam Deck: SteamOS has no `gcc`, `pip` or `uv`, and the install guide
required all three.

- **The shim ships prebuilt.** `shim/libtuner_recv_fix.so` is committed (`.gitignore` exception) and built
  to need only glibc 2.4: `atoi` is a local digit loop (glibc 2.38 headers turn it into `__isoc23_strtol`)
  and `dlsym` is pinned to its GLIBC_2.0 version, so a binary built on a current box loads on any host.
  Behaviour unchanged.
- **`scripts/check.sh` runs without uv.** It uses `.venv/bin/python` when `uv` is absent (the plain
  `python3 -m venv` + `pip install -e . --group dev` path), and refuses with a pointer to the install guide
  when neither exists.
- **`docs/AGENT_INSTALL.md`**: no compiler requirement, `uv` optional with the pip path spelled out, a
  SteamOS paragraph (read-only root, `~/.local/bin` off PATH in non-interactive shells), stale
  `fastapi`/`uvicorn` and "528 passed" wording gone. Verified on the Deck: venv + pip, 1063 passed.

### Also in 1.8.0 -- tech debt: the Game class in parts (2026-09-27)

- **`harness/game.py` is one mixin per domain.** The 5,800-line `Game` class is now `harness/game.py` (240
  lines: the transport, runtime injection, `q`, the shared poll helpers) plus fourteen modules under
  `harness/game_parts/`, cut the same way as the Lua runtime (front_end, turn, popups, events, reads, cities,
  units, unit_orders, notebook, diplomacy, espionage, deals, policies, trade_routes) and `support.py` for the
  helpers they share. Every method moved verbatim; `from harness.game import Game, lua_str, plain_text, ...`
  is unchanged and `Game.WAKE_KINDS`-style class attributes resolve as before. `scripts/play_loop.py
  --profile` attributes a trip to the public method in either place.
- **One poll loop.** Seven tools that read back an asynchronous order (minor_gold_gift, accept_deal, city
  strikes and attacks through `_with_target_result`, the policy and ideology confirmations,
  establish_trade_route, stage_coup) each carried a copy of the sleep-read-compare loop; they share
  `Game._settle`, which returns the last reading and whether it settled (`tests/test_settle.py`).
- **The guard's refusal chain is a function.** `mcp_server.guarded` was a hundred lines that rebuilt the
  read and response tool sets on every call; they are `READ_TOOLS` / `RESPONSE_TOOLS` at module level and
  the chain is `_refusal_for(g, ts, tool)`, testable without the decorator. The popup `hint` a refusal
  carries comes from gate.py's one resolution table (`popup_hint`): a pending tech or production popup used
  to get the generic `answer_popup` line, which does not clear those.
- **The HTTP/JSON server is gone.** `harness/http_server.py` mirrored the MCP tools by hand for non-MCP
  agents; it had fallen 28 tools behind (no way to clear a goody hut or a city capture), called `Game`
  directly with none of the guard (no action lock, turn claim or refusal chain), and nothing used it. Every
  agent speaks MCP, one server per seat. `fastapi` leaves the dependencies; `seats.json` keeps only what
  `scripts/launch_seat.sh` reads (port, profile, nickname). A live view of the models playing, when it
  comes, reads the call ledger and the runtime's event stream, not a command API.
- **Dev setup names the system packages.** README: `apt install lua5.4 liblua5.4-0` before `uv sync`;
  without luac the runtime lint skips and `scripts/check.sh` refuses to run. 1063 tests.

## 1.6.0 -- the runtime, one file per domain (2026-09-27)

Milestone 1.6.0 (#42): the Lua runtime is one file per game domain. Tag `v1.6.0` = runtime v242. 1000 tests.

- **Errors name the file (#42): runtime v242.** The installer names each chunk by its bare file name. The
  game's Lua prints a chunk name verbatim (live t53: an `=map.lua` chunk read `=turn.lua:379:`, an `@` one kept
  its `@`), so the bare name is what makes an error read `turn.lua:379:` in the game; stock Lua, which the
  tests run, shows the same chunk as `[string "turn.lua"]:379:`, and the tests that pin the name accept both.
- **The runtime is one file per domain (#42): runtime v241.** `harness/lua/runtime.lua` (11,583 lines)
  is now 38 fragments under `harness/lua/runtime/`, loaded in the order `harness/runtime_source.py` `MANIFEST`
  gives, each as its own named Lua chunk, so an error reads `events.lua:57:` and the Lua 5.1 compiler limits
  (200 locals, 60 upvalues per function) apply per file rather than to the whole runtime. What one file shares
  with later ones goes through `H._ns` (`H._ns.short = short` at the owner's end, `local short = H._ns.short`
  at the consumer's top; bodies unchanged); `H.*` and every response shape are as before. `Game.ensure_runtime`
  ships the assembled text as before, then a small installer cuts it into chunks by byte offset and sets
  `H.source_hash` after the last one: a failed load is never current, a corrected retry carries the state and
  duplicates no handler, and a forced reload that fails now retries (it used to stay marked current). The
  digest covers every fragment, so editing, renaming or reordering any of them reloads without a version
  bump. `H.install_hooks()` runs from `install.lua`, the last fragment. The Lua files ship with the package
  (they were missing from the wheel). Tests: the shared Lua support, the fog-cache reload and the
  source-inspection tests load through the loader; `tests/test_runtime_source.py` covers first and repeated
  installation, changed source at the same version, syntax and runtime failures with the corrected retry,
  state carry-over, cache reset, one handler per event after a reload, and the fragment lint (each file
  compiled alone reads only the game API, Lua and `H`; imports match exports; the 5.1 limits). `scripts/check.sh`
  stops when liblua5.4, lupa or luac is missing instead of letting 50 Lua test files skip. Checked live on the Venice/Mongolia hotseat, t52-t53 (2026-09-27): a fresh client re-injected v227 -> v241 in one call (the 56 recorded events, their table, the 18 hook closures, rosters, hp snapshots and known sites all carried); `briefing`, `cities`, `units`, `orders`, `available_research` read as before; `set_research` round-tripped Trapping -> Masonry -> Trapping through `Network.SendResearch`; `ensure_runtime(force=True)` took 59 s and kept every carried field while `_enum_names` and `_ns` were rebuilt; seat 0 ended t52, seat 1 took the turn (`turn_seat` 0 -> 1, events 56 -> 62), set a Caravan and ended, seat 0 got t53 back (`turn_seat` 0, events 67, still 18 hooks). No LAN table was up, so the LAN hand-off was not repeated. Record in `docs/GAPS.md`. 1000 tests. On the branch the steps were numbered v226-v240 in parallel with #32's
  v226-v227 (see the version map); the merge onto 1.5.0 is v241, and #32's `H.order_facts` now lives in
  `assignments.lua`, its `H.resume_moves(pid, skip)` in `movement.lua`. `harness/lua/runtime/README.md` says which file owns what and how to add one.

## 1.5.0 -- conditional orders, and what a turn costs (2026-09-27)

Milestone 1.5.0 (#32, #36): conditional unit orders, and the tracking issue's measurement. Tag `v1.5.0` =
runtime v227. Same save, same player, t48-t51 of the Venice/Mongolia hotseat played twice, each turn in a fresh
process: 8.0 calls a turn with the 1.2.0 tools against 4.25 with these, two refusals against none, 7.4 KB of
replies a turn against 8.2 KB (the briefing carries threats, events, orders and the notes every turn), and the
one thing the old reads missed -- a 10-hp barbarian beside a warrior -- was the first thing the briefing showed.
Full table and method in `docs/NOTES.md`; ledgers in `docs/measurements/`. 983 tests.

- **A call ledger (#36).** With `CIV5_CALL_LOG=/path/calls.jsonl` in the MCP server's environment, every tool
  call appends one JSON row: seat, tool, read / write / wait, reply bytes, tuner trips, seconds, whether the
  answer was a refusal (with its `err` cut to 120 characters), the turn the answer names. Off by default; the
  file is the operator's and nothing from it reaches any seat. `scripts/ledger_report.py` groups the rows into
  turns at each wait that succeeded (a refused `end_turn` leaves the turn open; the `wait_for_my_turn` after an
  `end_turn` belongs to the same turn) and keeps the wait's seconds apart from inspection.
- **A busy lock skips one poll, not the whole wait.** Live t50 of the measurement: seat 1's `end_turn` held the
  per-socket lock past a poll's 10 s acquire timeout and the `TimeoutError` left `wait_for_my_turn`, so seat
  0's 600 s `finish_turn` came back `timed_out` after 24 s with "call again". `action_lock` now raises
  `LockBusy` (a `TimeoutError`, so every other caller is unchanged); the wait loop polls again and, if its own
  deadline passes, names the last busy holder.
- **Conditional unit orders and runtime v226 (#32).** `give_order(unit_id, steps, interrupt, purpose,
  replace_id, start)` (and `POST /give_order`) stores a short sequence for one unit -- `move` (x, y), `build`
  (on the plot the move ends on), `heal` (to a percent), `hold` (fortify / sleep / alert) -- on the seat's
  notebook, runs it at once and then at the start of each of the seat's turns, one step at a time through the
  ordinary `move_unit` / `unit_mission` path, each step at most once per turn. Before every step it re-reads the
  unit (`H.order_facts`: fingerprint, moves, activity, build in progress, every visible hostile within the
  radius, the destination's `move_refusal` and whether an enemy stands on it, whether the build's plot already
  has it and whether the unit could start it) and pauses -- unit back in the model's hands with `pause.reason`
  and `hint`, and its standing move dropped -- on a newly visible hostile within `interrupt.hostile_within`
  (default 2), damage, `hp_below`, an enemy on the destination (an order never attacks), an illegal
  destination, a refused step, a build plot the unit is not on, no progress for a turn, a loaded save, a step
  whose answer the harness never saw (written ahead as `inflight`, never replayed blind), or a direct
  `move_unit` / `unit_mission` to that unit (`order_paused` on that answer). A lost or reused unit fails the
  order. One open order per unit; `H.resume_moves(pid, skip)` leaves units an order owns to the order, which
  runs after it in the turn-start window, under the seat's turn claim (#41). `orders`, `resume_order`
  (acknowledges what paused it and re-checks every step) and `cancel_order` complete the set; `status.orders`,
  a `finish_turn` wake reason `order:<id>:<status>`, the briefing's `orders` section and `order` on todo and
  decision rows show them. Hotseat seats never see each other's orders (per-seat notebook, per-seat window).
  v227: `can_build` asked `Unit:CanBuild` with four arguments, which the binding rejects ("number expected"); the
  pcall read that as "cannot build" and paused a live move-then-build order on arrival (Venice t43). Two
  arguments now, and a call that raises leaves `can_build` unset.
  Checked live t42-t48 on the Venice/Mongolia hotseat, both seats driven: 9 orders on 6 of seat 0's units.
  Move-then-build finished two farms and started a mine (Worker 49155: farm at (69,37) done t47); heal-then-move
  (Scout 67 -> 80% hp, walked to (72,33), held); a water destination refused with nothing stored; a cancel that
  left the unit's own manual move alone; a direct `move_unit` pausing the order; `replace_id`. Pauses, none
  followed by another step: a barbarian Archer at 1 plot (`hostile_within` 1), a barbarian Galley sighted at 2
  plots (twice, a real sighting), a combat unit bought into the destination city (`move_refusal`), the Scout's
  hold (sleep) refused -- which led to the fortify / sleep fallback. Each turn start ran in a new process, so
  every step after t42 was a restart; seat 1's Scout with the same id 24576 was ordered without touching seat 0's
  order, and seat 1 never saw an order. 16 calls issued by orders over 7 turns.

## 1.4.0 -- plans that survive a context reset (2026-09-27)

Milestone 1.4.0 (#33, #34): structured assignments on the notebook and compact comparisons. Tag `v1.4.0` =
runtime v225. The two were used together on one live hotseat turn (2026-09-27, Venice/Mongolia t42, seat 0):
`compare(kind="improvements")` on Worker 49155 sorted by production put the Cow pasture at (69,36) first (the
only row with an `empire_change`, the tile being worked); `assign` gave the worker that job with `done_when`
improvement PASTURE; `briefing(since="turn")` listed it `on_track` with the worker and target plot;
`compare(kind="production")` gave Worker 2 turns / 220 gold, Library 10 turns / +2.5 science, Granary 8 turns
/ +3 food. The test assignment was closed as cancelled; no unit was ordered. 931 tests.

- **Compact comparisons and runtime v225 (#34).** `compare(kind, city_id, unit_id, candidates, plots, sort,
  limit, detail)` (and `GET /compare`) puts a few caller-chosen candidates side by side from one read, with
  `context` (seat, turn, city or unit), `sources` (the getter or table behind each field) and `assumptions`
  (behind each estimate). `production`: up to 8 items in one city with `can_produce` or `why` not (a missing
  tech or building in the city, a resource short, already built, a wonder taken, the civ's own replacement,
  Venice's no-founding trait; `why_unknown` when no rule was found), cost, stored, turns, gold/faith price only
  where the buy button exists with `*_can_buy` and `*_short`, table `effects`, `conditional` per-tile yields
  counted over the city's tiles, `estimated_change` of the city's yields, maintenance (a unit's is "unknown":
  upkeep is empire-wide), `unique_replaces`; a Venice puppet is `purchase_only`, anyone else's refused.
  `research`: status, cost, progress, turns, `missing_prereqs` with `path_beakers` / `path_turns_estimate`,
  unlocks. `improvements`: per plot and build the tile's yields now and after, `empire_change` only while a city
  works the tile, removed feature and chop production, a luxury or strategic `connects`, maintenance, `why` a
  named build is refused; fogged plots are not read. `trade`: the chooser's yields per destination with
  distance and `hazard` (visible hostiles and camps near each end, the not-visible plot count, `danger` never
  "safe"). `limit` cuts rows and `omitted` carries the arguments for the rest. `purchase_cost` no longer calls
  an item with no buy button a gold shortfall (Venice's Settler read "not enough gold (189 of 370)"). Live
  Venice t42, S5 t215 and S1 t266: see `docs/NOTES.md`. 931 tests.
- **Structured assignments and runtime v224 (#33).** `assign(role, purpose, unit_ids, city_ids, target,
  done_when, review, replace_id)`, `assignments(status)`, `amend_assignment`, `close_assignment` (and `POST
  /assign`, `GET /assignments`, `POST /amend_assignment`, `POST /close_assignment`) keep what each unit or
  city is for in the seat's notebook file, beside the prose notes. Units and cities are fingerprinted (type
  and creation turn; name, plot and founding turn), so a reused id reads as the assigned one gone. Targets are
  a plot, a foreign unit or a player. `done_when` is manual, unit_at, city_at, improvement, building or tech.
  `review` is a turn, a hostile within N plots, or hp below a percentage. Every read reconciles against one
  fog-safe `H.assignment_facts` read into `condition_met` (with `evidence`), `needs_review` (with `reasons`:
  unit missing with an upgrade on its last plot named, id reused, city lost, target plot owner changed,
  improvement pillaged, a city within `MIN_CITY_RANGE` of a site, a target unit not where last seen, war or
  elimination, review turn, hostile, low hp) or `on_track`; out-of-sight targets are `stale` / `unknown` with
  the last sighting. `replace_id` closes the old one as `replaced`, so the two never compete. The briefing adds an
  `assignments` section (needing-a-look first, capped at `limit`) and tags an assigned unit's decision row.
  `close_assignment` works off-turn. Live Venice t42 (read-only): see `docs/NOTES.md`. 913 tests.

## 1.3.0 -- compact briefing and tactical view (2026-09-26)

Milestone 1.3.0 (#35, #30, #31): the compact read levels, the one-call turn briefing and the one-unit tactical
view, plus the v223 grid fix found while checking them together. Tag `v1.3.0` = runtime v223. The three reads
were used together on one live hotseat turn (2026-09-26, Venice/Mongolia t42, seat 0): `briefing` gave one
decision (Warrior 40962) with `todo_actions(detail='summary')` as its tool and three barbarian threats with
distance-only assessments; the summary row came back at 1 unit; `tactical_view` on that Warrior and on the
wounded Warrior 16385 beside the barbarian camp showed the coast refusals (needs Optics), the camp's
barbarian as `enemy` with "no moves left", and the three threats as occupants. Seat 1 on the same turn got
only the `other_seat_active` gate. 886 tests.

- **Runtime v223: the tactical grid stops at `radius`.** The grid is a (2r+1)-square box, but hex distance
  makes its corners farther than `radius`; they were drawn from the live map although `occupants` and `fog`
  never counted them, so a hostile could appear as `X` with no occupant row (live Venice t42: (73,41), three
  steps from a Warrior, drawn `__` while `fog.unrevealed` was 0). Cells beyond `radius` are now blank like
  off-map ones and the legend says so. Live t42 after the change: the radius-2 grid has 19 drawn cells = 18
  visible + 1 fogged, radius 3 has 37 = 27 + 9 + 1. 886 tests.

- **`tactical_view` and runtime v222: one unit's surroundings in one read (#31).** A new read (and
  `GET /tactical_view`) around one unit: the six `neighbors` by direction and coordinate from the engine's
  `Map.PlotDirection` (so the wrap seam and the edge rows are the engine's answer; an edge neighbour is
  `off_map`), each with terrain, remembered feature under fog, `river_crossing`, last-seen or live owner,
  visible units and `move`: `attack` (a melee target; its preview is in `targets`), `open` (move_unit would
  send the order: no cost or turns, which the engine cannot give safely), `refused` with `why`, or `enemy`
  with why it is not an attack. `refused` is move_unit's own pre-send checks, moved into `H.move_refusal` and
  shared (fog-safe for the view: a fogged plot's owner is the last-seen one and a city founded in the fog is
  not named). `targets` are `H.melee_targets` / `H.ranged_targets` rows, the same previews
  `available_unit_actions` gives (modifier rows only with `detail="full"`). `occupants` (visible units, hostile
  first, with range for a ranged one) and `cities` (a fogged one is `last_seen`, without hp) cover `radius`
  (1-5, default 2); `fog` counts visible, fogged and unrevealed plots and `unseen_within_2`; `grid` is the
  area as two-letter cells with a `legend`, and `players` names every owner id. `detail="full"` adds every
  revealed plot as `map_window` reads it. Live Venice t42 (80 x 52, wraps): 2,434 PlotDirection neighbours all
  at distance 1 including the seam and edge rows; the river-edge mapping agrees with `IsRiver()` on all 4,160
  plots; for all five units the neighbours agree with `map_window` and the targets and previews with
  `available_unit_actions`; the Scout's water neighbour gave the same refusal text as `move_unit`. 2.1-2.8 KB a
  unit, one call where `map_window` + `available_unit_actions` were two of about the same size. 885 tests.

- **`briefing` and runtime v221: the turn in one compact read (#30).** A new tool (and `GET /briefing`, and
  `finish_turn(briefing=true)`, which returns it in place of `status` and `digest`) answers with the seat,
  turn and gate; a `baseline` saying what it compares against (the seat's previous briefing, kept beside the
  notebook; `comparable=false` with the reason on a first read or after a reload to an earlier turn);
  `decisions` (every unit to order, promotion, empty city, research, incoming deal, stolen tech, popup, and the
  blocker when it is none of those; never cut, one `tools` entry per kind); `warnings` (status alerts,
  expiring deals, friendships and city-state allies, non-blocking stacked tiles); `opportunities` (idle
  caravans and spies, free trade slots); `changes` (empire totals, city pop and production, units new and
  gone, events by kind with the consequential ones listed); the empire totals; notable cities only; units by
  type with damaged and attention rows; visible `threats` (hostile combat units within 4 plots of a city or 2
  of a unit, with a distance-only `assessment`) and nearby barbarian camps; the leader trait text when there is
  no comparable baseline or with since="turn"; and the latest notes. Every list but `decisions` stops at
  `limit` with `omitted` and the tool that shows the rest. Events are read from the runtime's log with the
  briefing's own cursor (`H.briefing_board`), so the briefing and the digest never take events from each
  other. Behind a gate only the gate is returned. Live 2026-09-26: Venice t42 3.4 KB / 9 trips vs the six-call
  recovery's 7.2 KB / 15 trips; S1 t266 2.5 KB vs 29.9 KB; S1 t266 -> t267 through `finish_turn(briefing=true)`
  showed Goshute's finished Walls as a new decision. Details and the table in `docs/NOTES.md`.

- **`todo_actions(detail, limit)` and runtime v220: compact rows with drill-down (#35).** `detail` is
  `summary`, `normal` (the default, unchanged) or `full` (what `full=true` gave). All three are cut in
  `Game.todo_actions` from the same single Lua read, so the tuner cost and the facts do not change with the
  level. A summary row: id, type, x, y, moves, hp / max_hp when damaged, `promotion_ready`, `actions` as bare
  type strings without the everyday orders (listed once in `routine_actions`, counted per unit in
  `routine`), `promotions` (enums), `attack` / `ranged` targets (x, y, unit or city, owner, hp; previews stay
  in normal) and `build_plots` (x, y, builds, resource); `drill_down` names the exact args for the normal
  rows. `limit=N` returns the first N units in todo order and lists the rest in `omitted` (count, ids, args).
  Every reply now carries `detail`, `n` and `returned`; an unknown level, `full=true` with another level, or
  `limit < 1` is refused before any game call. v220 puts `hp` / `max_hp` on a damaged unit's row at every
  level. Live 2026-09-26: S1 t266, all 38 units, 5.7 KB summary vs 26.6 KB normal and 29.1 KB full at 3 trips
  each; Venice t42 hotseat 1.3 vs 3.8 KB. `scripts/measure_reads.py` records bytes, rows, trips and seconds
  per read (the baseline table is in `docs/NOTES.md`). MCP and HTTP (`/todo_actions?detail=&limit=`).

## 1.2.0 -- turn status tells the whole turn (2026-09-26)

The five fixes from the 2026-09-26 hotseat play review (milestone 1.2.0: #37-#41), plus the `gate`, the
rule book, `todo_actions` and the one-query screen reads that landed after 1.1.0. Tag `v1.2.0` = runtime
v219. The new status fields were read together on one live hotseat turn (2026-09-26, Venice/Mongolia t42:
seat 0 on its own turn with `gate: null`, `alerts: []`, `happiness: 8` and a standing-move Warrior in
`todo.ongoing`; seat 1 off-turn with the `other_seat_active` gate and a `happiness` alert at 1); each row
below says where it was checked. 840 tests.

- **Runtime v219: `expiring_deals` and `expiring_friendships` (#38).** City-state alliances already warned
  before they lapsed; deals and declarations of friendship with majors did not (2026-09-26, Mongolia
  t21-42: two embassy-for-gold deals lapsed and the seat learned it from the "expired" notice afterwards;
  a DoF with Catherine had no remaining-turns line on the turn it reads). On this seat's own turn,
  `turn_status` now carries `expiring_deals` -- current deals with `turns_left` <= 3, `{player_id, civ,
  turns_left, ends_on, items}`, items as short "we give / they give" lines -- and
  `expiring_friendships` -- DoFs with met majors ending within 5 turns (`DOF_EXPIRATION_TIME -
  GetDoFCounter`), with `ask_too_soon` when `IsDoFMessageTooSoon` would grey out the renewal. Either one
  wakes `finish_turn(skip_quiet_turns)`. The deal snapshot uses `current_deals`, so it is skipped (field
  left off) whenever the scratch trade table holds items or another seat's proposal is waiting: an offer
  or draft is never cleared or loaded. Unmet civs are not named. `relationship` now reports
  `dof_turns_left` too. Checked live 2026-09-26 on the t42 hotseat (helpers run inline, the v218 runtime left
  in place): seat 1 (Mongolia) listed the Portugal embassy-for-1-gpt deal ending t43 (`turns_left` 1, as
  `current_deals` says) and the Russia DoF at 38 turns (as `war_consequences`); seat 0 listed none of
  seat 1's; the scratch table was empty before and after.

- **Runtime v218: `todo.ongoing` and `going_to` (#37).** A unit the game is already moving used to vanish
  from the turn: `todo` listed a unit only when it needed orders or its standing move had stalled, and
  neither `units()` nor the next status repeated where a queued `move_unit` was taking it (2026-09-26,
  Mongolia t42: the auto-explore scout drifting toward a camp near x=16 was on no list; earlier, Arabia's
  0-move `queued: true` order was never restated). `turn_status.todo.ongoing` now lists every automated
  unit and every unit walking a standing move: `{id, type, x, y, moves, hp, automated, mission_name,
  going_to: {x, y}, attention, note}`. `going_to` is also on `units()` rows and on the `queued: true`
  reply of `move_unit`. These rows never set a blocker and never wake `finish_turn(skip_quiet_turns)` on
  their own; a row's `attention` does (`woke_because` `ongoing:<id>:camp` / `hostile` /
  `destination_unrevealed` / `destination_impassable` / `destination_gone`): a visible barbarian camp on
  or beside the unit, a visible hostile combat unit beside it, or a destination the seat can no longer
  path to. Only plots this seat can see are read; a fogged neighbour is unknown here as on the map. A
  stalled standing move stays in `todo.units` with its re-issue note (now with `going_to`). Orders go
  out as manual missions, which clear the automate type, so a new `move_unit` / `unit_mission` takes an
  automated unit back and no cancel tool was added. Also fixed: a refused `move_unit` cleared the standing
  record under the pre-hotseat key (bare unit id), so the refused destination survived to `going_to` and
  the next turn's resume; it now clears `H.pm_key(unit, seat)`. `H.going_to`, `H.ongoing_attention`;
  tests/test_ongoing_units.py. Checked live 2026-09-26 (hotseat quicksave, t42, seat 0): a Warrior
  ordered at 0 moves came back `queued: true, going_to: {72,36}` and the next status listed it under
  `ongoing` with `attention` = the camp at (74,33) and the 10 hp Barbarian Warrior on it; a Worker
  mid-path carried `going_to` on `units()` and no attention; seat 1's auto-explore Scout at (16,19)
  read `automated` with no attention (nearest revealed camp 3 plots off, fogged). `AUTOMATE_EXPLORE`
  was refused as not legal for seat 0's units (the engine's `CanAutomate`; seat 1's Scout and Spearman
  answered true), an engine rule, not a harness one.

- **Runtime v217: `turn_status.alerts` (#39).** Every status now carries `alerts`, a short list of facts about
  the seat's own empire that `overview` already showed and the loop never read: `{kind: "happiness",
  happiness, unhappy}` when the total is 2 or below or an unhappy tier is set, and `{kind:
  "strategic_deficit", resource, available, deficit, total, used}` for each revealed strategic resource
  with a negative `available` (an unrevealed one stays unknown, as on the top bar). The bare `happiness`
  total and `unhappy` tier ride on every status too. Alerts never add a `blocking_name` and never enter
  `todo`; the figures come from the same reads as `overview` (`H.status_alerts` shares `H.unhappy_tier`
  and `H.strategic_resources`) in the same trip as the rest of the status. `finish_turn(skip_quiet_turns)`
  wakes on an alert only when it worsens against the previous turn this process saw -- `happiness_drop:3->1`,
  `unhappy:unhappy`, `strategic_deficit:IRON:-2` in `woke_because` -- so a steady happiness of 1 through a
  five-turn Circus lets the run continue; the first status after a server start has no baseline and is
  never a drop, and a turn number going backwards (a reloaded save) clears the baseline. Motivated by
  2026-09-26 (Mongolia, seat 1, t41): happiness 1, a Circus queued, `todo` empty, the turn treated as quiet.

- **One client owns a seat's turn (#41).** The action lock made one operation exclusive and said nothing
  about the gaps between operations: two servers pinned to the same `--seat` could both end the turn, and
  on 2026-09-26 (Mongolia, seat 1, t37-42) a second client of the seat ended turns whose `todo` was empty
  while the first still meant to retarget its scout. Now the turn's first mutating command (an order, a
  diplomatic answer, `end_turn`, the end inside `finish_turn`) records its process in a claim file beside
  the lock, one per tuner socket and seat (`harness/turn_claim.py`). `end_turn`, `finish_turn` and every
  order from another process of the same seat answer `ok: false` with `turn_claim` (holder pid, how long
  it has held the turn, seconds since its latest order, when the claim expires) and the `gate`; reads, the
  waits and the notebook still answer, and `turn_status` shows `turn_claim` while a claim is live. The
  claim is for one game turn, so the holder's `skip_quiet_turns` run claims each turn it ends; if a second
  client acts on one of those turns first, the run stops and hands that turn back
  (`woke_because: ["other_client_holds_turn"]`) instead of ending it under them. It expires after 180 s
  without an order from the holder and at once when the holder's process is gone; `force: true` on
  `end_turn`, `finish_turn` or `do` takes it over. A server pinned to the other seat is refused as before
  (`this seat is not active`), claim or not. The CLI and the HTTP server keep their own `Game` with no
  claim (uncontested). `tests/test_turn_claim.py`: the file, two real processes, a crashed holder, the Game
  layer and the MCP layer.
- **`remember(replace_id)` refuses a different tag and returns the previous text (#40).** A replace used to
  match on the id alone and reply with the new note: `remember(replace_id=2)` from a scout stored its text
  over the plan, reported success, and the plan had to be written again (Arabia, seat 1, 2026-09-26). Now a
  non-empty `tag` that differs from the stored tag writes nothing and answers `ok: false` with the `id`,
  `stored_tag` and the tag that was passed; `retag: true` allows the change (`retagged: true` in the reply).
  Every successful replace carries `previous` (id, text, tag, turn) so a mistaken overwrite can be undone by
  writing it back. An empty tag still keeps the stored tag; a bad id still writes nothing and lists the ids.
  MCP `remember` and HTTP `POST /remember` take `retag`. Four tests in `tests/test_notes.py`.
- **The rule book: static help printed once, not on every row (runtime v216).** Every chooser row used
  to carry its hover text: the same Library blurb in every city's `available_production` every turn, the
  Salt hover (`resource_happiness`, `resource_improved_yields`, `resource_help`) on every Salt tile of every
  `map_window`, the tech sentence on every `available_research` row, the promotion effect under every
  button, the belief description, the policy help, the building help on `city_screen`, the standing
  sentence under every unit action. None of it changes during a game. `reference(section)` (MCP tool,
  usable between turns; MCP resources `civ5://reference` and `civ5://reference/{section}`; HTTP
  `GET /reference?section=`) is all of it in one Markdown document, read once from the game's own
  database (`H.reference`, so mods and DLC are honoured), cached per process and written beside the
  notebooks for the human. Sections: terrain, resources, improvements, units, buildings, projects,
  processes, promotions, policies, techs, beliefs, specialists, actions. The rows now carry enums, names
  and live numbers only (cost at this city's rate, turns, purchase price, upgrade target and price, scrap
  gold: the lines the panel computes per unit stay, in `help`). The server `instructions`, the playbook
  and every affected docstring point at the book. The choice was tokens, not bytes: a single-character
  terrain code saves bytes but not tokens ("GRASS" is one token; a glyph is two to four), while the
  repeated hover paragraph was tens of tokens per tile and per row. `revealed_map` remains the
  one-character-per-plot view.
- **Your own Continue screen is pressed for you by whatever you call first.** With `gate` in place the
  hand-off screen was still a chore: an agent that (re)started on it read `hand_off_screen`, and had to
  call `wait_for_my_turn` to press a button a human at that seat would press before anything else.
  `Game.clear_hand_off` presses it (our seat on screen, `hand_off_pending` true; never another seat's) and
  hands back the turn as the wait does, standing orders resumed, marked `hand_off_cleared: true`; every
  guarded tool, `turn_status` and the HTTP `/turn_status` run it before looking at the state. Two presses;
  a screen that stays up is left to the gate, whose `why` now says the press did not take. `finish_turn`
  called while our own hand-off is up waits instead of ending: `my_turn` already reads true under that
  screen, so a `finish_turn` retried after a client timeout that landed on the next turn's Continue screen
  would have ended it blind. `tests/test_gate.py` (`AnyCallPressesOurContinueScreen`).
- **`gate`: every status and every refusal names the one thing that must happen first, and the tool that
  does it** (runtime v215, `harness/gate.py`). Live 2026-09-26, Codex on seat 0 of the two-agent hotseat
  game, after a context reset: `turn_status` read `my_turn=true, paused=true, popup_up=true`, an empty todo
  and no blocker while its own hand-off screen was up -- nothing named the screen or the call that clears it.
  It read the board for four minutes, was refused with `game is paused, processing, or waiting`, replayed
  that refusal through its own `action_id`, and only then called `wait_for_my_turn`, which cleared it at
  once. Earlier the same hour, with the other seat on screen, the status note `set_seat(player_id) changes
  the seat` read as advice: it called `set_seat(1)` and pressed the other player's Continue button through
  raw Lua. Now `turn_status`, `wait_for_my_turn`, `finish_turn`, the HTTP `/turn_status` and every guard
  refusal carry `gate`: `null` when the seat may act, else `{name, why, clear_with, args?, read_first?}`
  computed once, in the order the engine and the guard enforce (no game, game over, other seat active,
  hand-off screen, processing, paused, turn not active, leader screen, discussion, tech choice, decision
  popup, announcement screen). The hand-off screen is a flag of its own now (`hand_off_pending`, read by
  `H.hand_off_up` in the same trip: the PlayerChange context answers `IsHidden() == true` while it is modal
  with its container visible, which is why `screens.PlayerChange` never saw it), and the wait loop uses it
  instead of two more trips. The seat notes and hints no longer offer `set_seat` from a pinned server; an
  auto-seat server hears it only as "if nobody else plays that seat". A refusal at a gate is never
  remembered under an `action_id`, so a retry after the gate clears runs. `tests/test_gate.py`.
- **The wait tools no longer hold the operation lock while they sleep.** Two agents in one hotseat game
  (Codex seat 0, Grok seat 1, 2026-09-26) stalled for most of two turns on `another game operation is
  running; retry`: `mcp_server.guarded` wrapped the whole call, so an inactive seat's `finish_turn(300)`
  held the per-socket flock for five minutes and the active seat could not even read `turn_status`, nor
  clear its own hand-off screen. An orphaned `scripts/mcp_call.py wait_for_my_turn` (a one-shot server the
  caller's shell had stopped watching) did the same for 180 s, and a first call's runtime injection for
  75 s. Now `Game.wait_for_my_turn` / `finish_turn` take `Game.lock` (the server's `action_lock`; a
  no-op for the CLI and HTTP server) around each poll, the end-turn and the digest, and sleep unlocked;
  `guarded` locks a wait tool only for the connect. The holder writes its seat, tool and pid into the
  lock file, and the refusal says what a human at the hand-off screen would know: for another seat's
  call, `it is not your turn while another seat acts` and nothing else (the other player's tool names and
  timings are their cursor, not the game's UI); for your own seat's earlier call, `your own finish_turn,
  pid 198237, has held it for 212 s`. `tests/test_lock_liveness.py` proves it at the Game, lock and MCP
  layers (a contender gets in between polls; each poll is still locked; a second process's refusal names
  your own call and not another seat's). Holders identified from both agents' transcripts
  in `docs/NOTES.md`. Verified live the same morning, Codex (seat 0) vs Grok (seat 1) on the same
  socket: three alternating hand-offs (turns 0-2) with both agents sitting in `finish_turn` at once, the
  waiting seat's `wait_for_my_turn` / `finish_turn` returning 7-8 s after the other's `finish_turn` began,
  and the only refusals the first call's runtime injection, which Grok read and waited out (the message
  then still named the other seat's tool; it no longer does).
- **`set_seat` refuses the other player's seat on a pinned server.** A server started with an explicit
  `--seat N` plays only seat N; `set_seat(other)` answers `this server was started with --seat N and plays
  only that seat; seat M is another player's`. `--seat auto` keeps its freedom (a hotseat save loaded on
  the wrong seat still needs it). Before this the playbook's "never take the other human's seat" was the
  only guard between two agents' information sets.

- **v214** every popup / leader screen's up-or-down in one InGame query, and the loop timed. The open
  ROADMAP row asked where a late `scripts/play_loop.py` turn spends its time; `--profile` (new) attributes
  every tuner round-trip to the loop phase and the `Game` method on the stack. Live S1 t270: 97 s, 278
  trips of ~0.35 s each (the floor: the game services one tuner command per frame or so), and 250 of
  them were screen reads -- `turn_state` was 8 trips (3.1 s: one per popup context through the tuner),
  the popup sweep ~20, and `wait_for_my_turn` did both on every poll (157 trips over a 50 s AI round),
  `end_turn` 93 trips (33 s). The engine's control tree is one tree, so `H.modal_flags()` now reads
  every context's `IsHidden()` from InGame by full path (`H.CONTEXT_PATHS`, 28 screens) and
  `H.turn_state` carries the five flags; `dismiss_pending_popups(ts)` reuses the caller's read. After:
  `turn_state` 1 trip (0.37 s), sweep-with-nothing-up 1, an idle wait poll 2, `end_turn` 8 trips (3.2 s).
  Live t271 (three blockers, a leader approach, 12 idle units): 90 s, with `unit_mission` (~7 trips an
  order: selection retries and confirmation polls) and the bot's candidate walks on top. Paths found the
  hard way: `BulkUI` is transparent (`/InGame/<ID>`; a `/InGame/BulkUI/<x>` path answers with BulkUI
  itself, visible), `LeaderHeadRoot` hangs off the root, and an ID can differ from its file
  (`GreatWorkSplash`, `ChooseIdeology`). Verified live: a `BUTTONPOPUP_TEXT` raised by Lua read as
  `screens.TextPopup = true` and the sweep closed it in its own state. Also fixed: `popup_up` read nil
  instead of false (an `a and b or nil` since v207). `tests/test_screens_one_read.py` (10). 592 tests.

- **v213** `todo_actions` (MCP + HTTP): legal actions for many units in one read. With no `unit_ids` it
  covers every unit in `turn_status.todo.units` plus every promotion-ready unit; with ids, exactly those.
  Each row is `available_unit_actions`' answer plus `id`, `type`, `promotion_ready`; action rows drop their
  `help` unless `full=true` (promotion rows keep name + help). Usable inside `do`. Live S1 t270: 38 units in
  one 0.5 s query, 30 KB compact / 59 KB full, against 0.37 s and ~1.6 KB per unit one at a time; two woken
  units (Paratrooper, Trebuchet) came back as `source: todo, n: 2` with the same rows as the single read.
  Found on the way: the per-unit read is cheap (0.37 s), so the handoff's "~15 min of
  `available_unit_actions` per unit" was a misattribution -- the loop's time goes elsewhere (unmeasured).
  The win is 1 tool call instead of 38 for the model, not minutes. `tests/test_todo_actions.py` (7). 582 tests.

## 1.1.0 -- the LLM-first loop (2026-09-25)

The turn boundary as one call, safe retries, a notebook, batching, and the seat named in every answer.
Tag `v1.1.0` = runtime v212 (v208-v212 landed after 1.0.0: revealed_map and trade-route paths). Every row
below was checked live on 2026-09-25 (S1 t269-t271, the Alpha/Bravo hotseat for set_seat and
exit_to_main_menu). 575 tests. `pytest` now finds `harness` from any invocation (`pythonpath` in
pyproject; before, only `python -m pytest` did).

- **set_seat** (MCP): change the player this server plays, or re-detect it, without a restart. Live
  2026-09-25: a hotseat save loaded under `--seat auto` left the server on its default seat 1 while seat 0
  sat on the hand-off screen; every tool refused with only `active_player: 0`, a 420 s `wait_for_my_turn`
  ran out, and nothing said which seat the server was on. Now `turn_status` carries `seat` (and a
  `seat_note` in hotseat when the seat on screen differs), the "this seat is not active" refusal carries
  `seat` and a `hint` naming set_seat, wait/finish timeouts carry `seat` + `active_player`, and progress
  messages name the seat. Only a seat the engine considers human can be chosen; `set_seat()` with no
  argument re-runs detection (hotseat: the seat on screen when it is human). Refused inside `do`.
- **exit_to_main_menu** (MCP): leave the loaded game for the main menu so load_save / load_latest can open
  another save (they only work from the menu, and nothing on the MCP surface got there before); quick-saves
  first when it is our turn in a solo game. A load now detects an auto seat afresh (the previous game's
  seat may be wrong for this one) and answers with `seat`. Both refused inside `do`.
- **finish_turn default timeout 600** (MCP + HTTP, was 270): verified in Claude Code 2026-09-25 that a
  420 s wait with progress every 5 s returns the server's own timeout, not a client cutoff; the client moves
  a call past 120 s to a background task and reports its result when it lands.
- **finish_turn** (MCP + HTTP): the turn boundary as one call -- end_turn, wait_for_my_turn and turn_digest,
  returning status, digest, turn and the latest notebook notes. Idempotent: when it is already not our turn it
  only waits, so a call retried after a client timeout never ends two turns. `skip_quiet_turns=N` ends up to N
  further turns while nothing needs the player (empty todo, no blocker/popup/expiring ally, nothing eventful
  in the digest: `Game.WAKE_KINDS` / `WAKE_WORDS`, plus the caller's `wake_on` words); the skipped turns'
  digests are merged and `woke_because` names the reason. Live t269-271: one call, 64 s, woke on
  todo.units + a leader message + a lost unit. `scripts/et.sh` is now one finish_turn call.
- **Progress notifications** while waiting: `wait_for_my_turn` and `finish_turn` report MCP progress every
  5 s (and at "ending turn N" / "turn N was quiet"), so a client's idle timeout no longer cuts a long wait
  short; the SDK runs tools in a worker thread, the reporter hops back to the loop with anyio. Verified
  in-process over the memory transport and live over stdio.
- **Notebook** `remember` / `recall` / `forget` (MCP + HTTP, `harness/notes.py`): per-game, per-seat notes
  stored under `$XDG_DATA_HOME/civ5-harness/notes/` (or `$CIV5_NOTES_DIR`), keyed by leader, civ, map
  script, capital and its founding turn (`Game.game_key`; the engine exposes no seed). `replace_id` keeps one
  living plan; the last 8 notes ride along in every finish_turn result. Usable while it is not our turn.
- **do** (MCP): a list of `{tool, args}` orders carried out in sequence with the SDK's own argument
  validation, each result returned; stops at the first `ok: false` and lists the rest as `skipped`
  (`stop_on_refusal=false` runs them all). Waiting, loading, end_turn, lua and do itself are refused inside.
- **action_id** on any tool call (and any `do` order): the call wrapper pops it before validation, keeps the
  raw result in a bounded per-process cache, and answers a repeat with the earlier result plus
  `replayed: true`, so a retry after a transport timeout never acts twice. Live t271: two skips batched,
  the same batch replayed, a direct call replayed. The wrapper now installs at import, once per process.
- **MCP resource + prompt**: `civ5://playbook` serves `docs/PLAYBOOK.md`; the `play_turn` prompt is the loop
  in one paragraph. The server `instructions` now describe the finish_turn loop.
- **docs** PLAYBOOK, README and AGENT_INSTALL describe the one-call loop and the notebook.

- **LICENSE** MIT, with the README noting that the game, its assets and the quoted stock UI Lua stay Firaxis/Take-Two's.
- **docs** `docs/GROK_PLAYBOOK.md` is `docs/PLAYBOOK.md`: mode-neutral, and its blocker table now matches
  `BLOCKING_HINTS` in the runtime (ideology, free great person, Maya, archaeology, reformation, steal-tech
  and league votes all have tools; proposing deals is no longer described as disabled).
- **docs** README rewritten for people (what to expect, ways to play, honest limits) and a new
  `docs/AGENT_INSTALL.md`: the complete install brief an agent follows to get the game, the shim, tunerd
  and the MCP server running on a fresh machine, with a check per step and a report-back script.
- **v212** `revealed_map`: the whole revealed map as character grids, one byte per plot per layer (vis,
  terrain, elevation, river, owner, feature, improvement, resource, route), legends built per reply,
  `layers` and an x0/y0/x1/y1 window for large maps (a Huge map after Satellites is ~10 KB a layer, where
  `known_world` is ~140 B a plot). The `vis` layer is the point: '#' in sight, '~' revealed but fogged,
  whose contents are what was last seen and may be stale. Fog rules are describe_plot's (remembered
  feature or '?', Revealed* improvement/route/owner, no live units or pillage marks under fog). Live S1
  t269: 66x42, 559 revealed / 355 visible, 28 KB for all nine layers.
- **v212** `trade_routes` rows carry the route line: `path` from the origin (fogged plots marked,
  `path_gaps` for unrevealed stretches), read from the plot hover's route list
  (`Player:GetInternationalTradeRoutePlotToolTip`, which plothelptext.lua calls on any revealed plot);
  `unit` is the caravan on the line (ours always; a foreign one only in sight) with `escorted` /
  `escorted_by` (own combat units on its plot, which an enemy must defeat before plundering) and
  `enemies_near_path` (visible enemy combat units within one hex, with their distance to the caravan).
  Caravans that fit only one route are placed first, since routes share plots (live t269: two Addis
  Ababa routes ran the same eleven plots). Found on the way: `Plot:IsTradeRoute()` is the city-connection
  flag, not a caravan line, so it is no longer the gate and `map_window`'s `trade_route` says so.
  Regression: `tests/test_revealed_map.py` (8). 528 tests.
- `docs/LIMITATIONS.md` "Still to be seen live" no longer waits for states already reached (#13 S4 t239,
  #22 S2b t237-238, #15 S5 t215, #23 S6 t215-t216); it now names what actually has regression coverage
  only: war on a city-state syncing over LAN (COVERAGE_AUDIT G-D3), LAN mode since 0.5.0, and the stale
  PRODUCTION blocker after game over (`turn_status.game_over` first). `docs/GAPS.md` section 0 header
  reads v207.
- `tests/test_supervisor.py`: `harness/supervisor.py` had no tests. 25 cases pin every path that must not
  relaunch the game (grace window open, process still up, pid unknown, no `--launch-cmd`, restart cap),
  the one that must, the grace-window reset after a relaunch and after a self-reconnect, `rejoin`'s replay
  per saved lobby kind, and `wait_for_main_menu`'s cold-boot retry. 520 tests.

## 1.0.0 -- release (2026-09-25)

Every row on the 0.5.0 and 1.0.0 tables in `docs/ROADMAP.md` is closed or declared (GitLab #29). Tag
`v1.0.0` = runtime v207. Cut after an unattended `scripts/play_loop.py` pass on a clean S1 load (solo
Shoshone, t266-t268, 38 units, World Congress): three turns ended without a stall, through
ENDTURN_BLOCKING_UNITS and PRODUCTION, one declined leader approach (Haile Selassie), a Caravan route and
three Worker automations; no stale blocker and no orphaned popup appeared. Each late-game turn took the
loop about 15 minutes (it reads `available_unit_actions` per unit), which is the loop's cost, not the
harness's.

- **v207** GitLab #23 closed: `ENDTURN_BLOCKING_UNITS` with an empty todo is a stale reading. The engine does
  not re-evaluate `GetEndTurnBlockingType` while a popup is up (`UI.IsPopupUp()`), so the last ready unit's
  order plus any announcement popup raised on the way -- a city-state met by the unit itself (which is why
  three `Teams:Meet` attempts never reproduced it), a natural wonder, a plain text box -- leaves UNITS on the
  books with `HasReadyUnit()` false (live S6 line t215-t216: Infantry 32771 toward Melbourne past a natural
  wonder, then a `UI.AddPopup` text box with Infantry 73736; both held UNITS until the popup closed). Now
  `turn_status` carries `blocking_stale` and `popup_up` and the hint names the popup instead of "every unit
  in todo.units" over an empty list; `end_turn` refuses on the popup ("popup needs attention (... stale ...)")
  rather than the blocker; and `dismiss_pending_popups` processes an announcement popup the engine waits on
  that nothing draws (record present, context hidden, `UI.IsPopupUp()` true, no screen up) the way its own
  close button would -- guarded, unit-tested, not yet seen live. 495 tests.

## 0.5.0 -- live verification (2026-09-25)

The reads that had only regression coverage, each closed by a live reproduction (GitLab #20-#22), plus the 0.4.0
screens that landed after the 0.3.0 cut (#13 live switch, #15 Venice). Tag `v0.5.0` = runtime v206. #23 (the
CityStateGreeting empty-todo turn-loop defect) stays open until a game state reproduces it: three attempts with the
greeting pending (S2b t237, Doge t215, S6 t214) all ended the turn normally.

- #21 closed live (no runtime change): the golden-age combat modifier row seen on a Persian seat in a golden age
  (S6 `Shah_0214 golden-age`, t214): `available_unit_actions` previews carried "Golden Age Bonus +10" and 70 -> 77
  strength, gone again with the golden age removed. Found on the way: `Players[63]:InitUnit` crashes the game in a
  fresh hotseat where the barbarian player is not alive yet (`docs/GAPS.md`, `saves/README.md`).
- **v206** Policy screen: `available_policies` branch rows say `can_unlock: false` once a branch is open (the
  engine's CanUnlockPolicyBranch stays true) and `unlock_policy_branch` refuses an open branch instead of
  re-sending it. `scripts/play_loop.py` adopts what the screen offers (an Atomic start's free policies were
  none of its static candidates, and re-unlocking Tradition counted as progress five times, live Doge t215)
  and handles ENDTURN_BLOCKING_CHOOSE_IDEOLOGY through `choose_ideology` (Freedom chosen, t215 ended).
- **v205** Venice's puppets live (#15 closed): a one-human hotseat hosted as Venice (S5
  `Doge_0215 venice-puppet`); the Merchant of Venice's `MISSION_BUY_CITY_STATE` bought Wittenberg,
  `available_production` opened the puppet in purchase mode (22 priced rows) and `purchase_production` bought a
  Monument there while `set_production` refused. Fixed on sight: `producing` was the raw TXT_KEY in the puppet
  list and in the refusal (now the printed name; `H.L` survives a missing Locale), and the refusal told Venice to
  annex, which it cannot (now it points at purchase_production).
- **v204** Ideology switch live (#13 closed): eight Great Musician concert tours by Bravo (`unit_mission
  MISSION_ONE_SHOT_TOURISM`, 67 tourism each at Quick speed, legal at war) put Alpha at Popular influence
  under Order; Alpha's t239 read Civil Resistance, 6 unhappiness, `can_switch` with the 2-turn anarchy cost,
  and `change_ideology` moved Autocracy -> Order on the spot (anarchy 2, opinion back to Content). The gold
  hover now carries `anarchy_turns` like the science/culture/faith ones (stock GoldTipHandler). New save S4
  `Alpha-Bravo_0239 ideology-pressure`.
- Release hygiene: `docs/LIMITATIONS.md` (declared engine rules and refused calls, #24), README and
  ARCHITECTURE rewritten for the current tool set (#27), `saves/` library of the reproduction states (#28).
- **v203** Captured civilians: the notice is linked from the destroy side too (the destroy event can arrive
  after the notice), and `move_unit` refreshes the loss roster on arrival. Live S1 t267: one
  `unit_captured` row with the barbarian captor on the tile, and S2b t237-238 the same with Bravo's Infantry as
  captor (#22 closed).
- #20 closed as a declared limitation: stock BNW ships `FIRE_SUPPORT_DISABLED = 1`, so melee fire support
  never fires and the preview's 0 is faithful. #21 rough/open-terrain and flanking rows seen live (S1 t266);
  the golden-age row needs Persia. New save S3 `Pocatello_0266 combat-lab`.

## 0.3.0 -- trade table (2026-09-25)

Everything a human can put on, read from, or answer on the trade table (GitLab #4-#8), each live on the
Alpha/Bravo hotseat or the solo Shoshone save. Tag `v0.3.0` = runtime v202.

- **v202** The leader screen's Demand button: `demand(other, items)` through OnDemand / UI.OnHumanDemand /
  UI.DoDemand, their items only, refused at war or toward a human seat (#6; live t266, Darius refused).
  `trade_catalog.gold.note` explains the Brave New World rule that lump-sum gold needs a Declaration of
  Friendship (gold per turn is not gated).
- **v201** Venice buys in its puppets: `available_production` opens in purchase mode for a puppet when
  the player `MayNotAnnex()`, as the stock production popup does (#15; regression-tested, live check
  needs a Venice seat).
- **v200** Peace with terms through the real screens: `make_peace(other, items)` is `propose_deal` with
  the treaty on both sides; `trade_catalog().peace` is the Negotiate Peace gate with the locked-into-war
  reason (#5; live t237: Silk + Salzburg accepted by the other human seat).
- **v199** Third-party war and peace on the trade table, with the Other Players pocket as
  `trade_catalog.third_party` (#6; live t234). The AI-only Demand button stays open.
- **v198** World Congress vote commitments on the trade table, with the Diplomat requirement (#7; live
  t233).
- **v197** Switch Ideology: the unhappiness hover, the switch cost and the switch itself (#13; the
  enabled button is not yet seen live).
- **v196** Remembered terrain features under fog, a last-seen cache like the stock map's (#19).
- **v195** The Culture Overview swap tab (#12; live t270).
- **v194** Coup odds and grey reasons, the spy potential hover, the faith purchase pull-down (#9, #10, #11).
- **v193** The hovers behind the city screen meters, specialist yields, help on owned buildings, stored
  beakers on every tech (#14, #16, #17, #18).
- The regression suite has a locked `dev` dependency group and a one-line runner, `scripts/check.sh`,
  meant to run before every push; GitLab pipelines are not used (no shared runner minutes) (#25).
- Deals between human seats: `propose_deal`, `incoming_deal`, `accept_deal`, `refuse_deal` on the
  `SimpleDiploTrade` table; `load_save` finds hotseat and network saves (#4; live t227/t228).

## 0.2.0 -- information boundary (2026-09-24)

Nothing new may leak and no read may truncate.

- **v192** No rival tech list behind an embassy; deal city rows are reveal-gated and carry population
  (#1, #2, #8).
- Query chunking budgets escaped bytes, not characters: the tuner truncates at 2048 bytes (#3).
- **v185–v191** The first two-human hotseat: a standing move belongs to one seat, the stacked tile's
  units, the swap a move causes, deals between humans and the leader scene a proposal leaves behind,
  intercepted strikes, clamped previews, captured civilians named.

## 0.1.x -- the solo Shoshone game (2026-09-15 to 2026-09-23)

`RUNTIME_VERSION` v125–v184: the information-parity reads and writes built against a solo Emperor game
(Pocatello, t1–t266), each one opened because it was blocking a real decision and verified live the
same turn. `docs/GAPS.md` and `docs/SESSION_HANDOFF.md` hold the turn-by-turn notes.

## Runtime version map

Recent runtime versions and the commit that introduced each:

| Runtime | Date | Commit | Change |
|---|---|---|---|
| v242 | 2026-09-27 | `542bd5a` | bare chunk names: a game-side Lua error reads `turn.lua:379:` (#42) |
| v241 | 2026-09-27 | `59f2182` | #42 merged onto 1.5.0: the runtime split below, numbered v226-v240 on its branch in parallel with #32's v226-v227 |
| v227 | 2026-09-27 | `3bb6b2d` | `H.order_facts`: `Unit:CanBuild(plot, build)` two-argument form (#32) |
| v226 | 2026-09-27 | `3c0aec0` | `H.order_facts`, `H.resume_moves(pid, skip)`: conditional unit orders (#32) |
| (branch) v240 | 2026-09-27 | `85c5638` | every fragment compiles alone; joined-chunk transition code removed (#42) |
| (branch) v239 | 2026-09-27 | `e99086d` | units.lua, empire.lua compile alone (#42) |
| (branch) v238 | 2026-09-27 | `3c1a251` | map.lua, city_actions.lua, city_views.lua compile alone (#42) |
| (branch) v237 | 2026-09-27 | `5b86d4c` | religion, choices, unit_orders, city_strikes, diplomacy_actions, notifications, policies, diplomacy compile alone (#42) |
| (branch) v236 | 2026-09-27 | `8a5292c` | trade_routes.lua, city_states.lua, war.lua, deals.lua compile alone (#42) |
| (branch) v235 | 2026-09-27 | `4a69e2a` | espionage.lua, overviews.lua, league.lua compile alone (#42) |
| (branch) v234 | 2026-09-27 | `f36378d` | unit_actions.lua, production.lua, research.lua compile alone (#42) |
| (branch) v233 | 2026-09-27 | `bc5ed75` | combat_previews.lua, combat.lua compile alone (#42) |
| (branch) v232 | 2026-09-27 | `c8c9f8d` | movement.lua, tactical.lua compile alone (#42) |
| (branch) v231 | 2026-09-27 | `e1ebeff` | victory.lua, turn.lua compile alone (#42) |
| (branch) v230 | 2026-09-27 | `1c3c395` | reference.lua compiles alone; `H.reference` reports `H.version` (#42) |
| (branch) v229 | 2026-09-27 | `8f21ceb` | assignments.lua, briefing.lua compile alone (#42) |
| (branch) v228 | 2026-09-27 | `87aced0` | comparisons.lua compiles alone (#42) |
| (branch) v227 | 2026-09-27 | `a5b6983` | each fragment loads as its own named chunk; `H._ns` for shared locals (#42) |
| (branch) v226 | 2026-09-27 | `d14391b` | runtime.lua split into 38 fragments under `harness/lua/runtime/`; `H.install_hooks()` runs last (#42) |
| v225 | 2026-09-27 | `61cb931` | `H.compare_production` / `_research` / `_improvements` / `_trade_routes` (#34) |
| v224 | 2026-09-26 | `3e9a7fa` | `H.assignment_facts`, `H.is_upgrade_of`: structured assignments (#33) |
| v223 | 2026-09-26 | `be1eb1b` | tactical grid cells beyond `radius` are blank |
| v222 | 2026-09-26 | `9e64b1d` | `H.tactical_view`, `H.move_refusal` shared with `move_unit` (#31) |
| v221 | 2026-09-26 | `9778f81` | `H.briefing_board`: threats, camps, leader trait, event log with its own cursor (#30) |
| v220 | 2026-09-26 | `7914f48` | `hp` / `max_hp` on damaged `todo_actions` rows; `detail` levels (#35) |
| v219 | 2026-09-26 | `4534fda` | `expiring_deals` / `expiring_friendships` on turn_status (#38) |
| v218 | 2026-09-26 | `38a6608` | `todo.ongoing`: automated units and standing-move destinations (#37) |
| v217 | 2026-09-26 | `1559c74` | `turn_status.alerts`: low happiness, unhappy tier, strategic deficits (#39) |
| v216 | 2026-09-26 | `926bd54` | the rule book: static help once in `reference()`, not on every row |
| v215 | 2026-09-26 | `3bf4f93` | `gate` on every status and refusal |
| v214 | 2026-09-25 | `d0af586` | every popup screen in one query; `play_loop --profile` |
| v213 | 2026-09-25 | `d981a76` | `todo_actions`: legal actions of every unit needing an order in one read |
| v212 | 2026-09-25 | `2910df8` | `revealed_map` grids and trade-route paths |
| v207 | 2026-09-25 | `8ebe0ad` | a stale UNITS blocker is named (#23) |
| v206 | 2026-09-25 | `0ecec22` | open policy branches offer no unlock; play loop reads the policy screen, picks an ideology |
| v205 | 2026-09-25 | `78cb3ff` | Venice's puppets live: localized `producing`, refusal points at purchase_production (#15) |
| v204 | 2026-09-25 | `c410c45` | ideology switch live, gold hover's anarchy line (#13) |
| v203 | 2026-09-25 | `579f8d4` | capture notices linked from the destroy side (#22) |
| v201 | 2026-09-24 | `a6be7be` | Venice buys in its puppets (#15) |
| v200 | 2026-09-24 | `2d1d857` | peace with terms through the real screens (#5) |
| v199 | 2026-09-24 | `e0fef85` | third-party war/peace on the trade table (#6) |
| v198 | 2026-09-24 | `c3dd709` | World Congress vote commitments on the trade table (#7) |
| v197 | 2026-09-24 | `cfaa529` | the Switch Ideology button, its hover and the switch (#13) |
| v196 | 2026-09-24 | `da91929` | remembered terrain features under fog (#19) |
| v195 | 2026-09-24 | `e70930a` | the Culture Overview swap tab (#12) |
| v194 | 2026-09-24 | `6ca1580` | coup odds and grey reasons, the spy potential hover, and the faith purchase pull-down (#9, #10, #11) |
| v193 | 2026-09-24 | `153d0c0` | the hovers behind the city screen and stored beakers on every tech (#14, #16, #17, #18) |
| v192 | 2026-09-24 | `a8b2ce6` | no rival tech list behind an embassy, deal city rows reveal-gated and carry pop (#1, #2, #8) |
| v191 | 2026-09-24 | `8b07491` | intercepted strikes, clamped previews, captured civilians named |
| v187 | 2026-09-24 | `7190cf9` | deals between humans, and the leader scene a proposal leaves behind |
| v185 | 2026-09-24 | `3a5c6f0` | a standing move belongs to one seat |

<details><summary>v125–v184</summary>

| Runtime | Date | Commit | Change |
|---|---|---|---|
| v183–v184 | 2026-09-24 | `e33a166` | the stacked tile's units, and the swap a move causes |
| v182 | 2026-09-23 | `371e10c` | the greyed Gift Improvement button says why |
| v181 | 2026-09-22 | `2de406e` | the trade route screen's religion columns and gold hover |
| v180 | 2026-09-22 | `ce8887a` | World Congress names drop the choice's icon tag |
| v179 | 2026-09-22 | `bc33a3c` | the resource list's bonus stack, and the tile hover |
| v178 | 2026-09-22 | `48945fa` | the Happiness screen's rows, not just the totals |
| v177 | 2026-09-22 | `0b34980` | the tech tree's buttons, not just the paragraph |
| v176 | 2026-09-22 | `47e2603` | the World Congress screen's tooltips, not just the names |
| v175 | 2026-09-22 | `76318e4` | World's Fair progress on the league screen and the production row |
| v174 | 2026-09-22 | `f786ccd` | the city screen's meters, including a tile you cannot afford |
| v173 | 2026-09-21 | `d7c772f` | the Notification Log, not just the panel |
| v172 | 2026-09-21 | `2167b2a` | a finished build says what it changed, including the borders it moved |
| v171 | 2026-09-21 | `c2389d0` | the Change Home City chooser, for caravans and Great Admirals |
| v170 | 2026-09-21 | `81c9dc3` | a gift tier says whether it actually buys the alliance |
| v169 | 2026-09-21 | `dead011` | the production chooser says Zoo, not BUILDING_THEATRE |
| v168 | 2026-09-21 | `1b247f9` | an idle caravan says why it has nowhere to go |
| v167 | 2026-09-21 | `11d7c96` | what the unit-action button says it does |
| v165 | 2026-09-21 | `06b0ec6` | the Gift Improvement button, and the hexes it lights up |
| v164 | 2026-09-21 | `953b724` | say which great work a Great Person became, and where it went |
| v163 | 2026-09-21 | `c6a55e7` | refuse a move onto another player's city instead of letting it rot |
| v162 | 2026-09-21 | `27add30` | an idle spy is as invisible as an idle caravan used to be |
| v161 | 2026-09-21 | `406c756` | a missionary says which faith it carries, and a no-op spread says so |
| v160 | 2026-09-21 | `0c0ebcb` | a negative TurnsLeft is a blank column, not an overdue route |
| v159 | 2026-09-21 | `409367b` | buy_city_plot had the same puppet hole, and now a lint says so |
| v158 | 2026-09-21 | `ca9884b` | a puppet is not ours to run, and the inline-query budget was a guess |
| v157 | 2026-09-20 | `1ef40ec` | a captured-city row pointed at the wrong city |
| v156 | 2026-09-20 | `b57c0d0` | say why the turn will not end, in the engine's words |
| v155 | 2026-09-20 | `093cf6e` | turn_status and unit_mission agreed about stalled units |
| v154 | 2026-09-20 | `f1a4198` | steal_tech takes player_id like every other civ-targeting tool |
| v153 | 2026-09-20 | `bbaf461` | refuse an air strike the engine would ignore |
| v152 | 2026-09-20 | `c4de752` | the promotion chooser as a human reads it |
| v151 | 2026-09-20 | `d98b0b1` | itemised combat modifier rows on every preview |
| v150 | 2026-09-20 | `ac2dcd7` | include melee fire support and cap preview damage |
| v149 | 2026-09-20 | `4a40b14` | air-strike retaliation and ranged combat previews |
| v148 | 2026-09-19 | `79e2670` | tech/production help, nearby build turns, public opinion |
| v147 | 2026-09-19 | `8acb5c2` | incoming trade routes, score breakdown, WLTKD/blockade |
| v146 | 2026-09-19 | `f93bc4e` | worker job turns, CS quest list, plot construction tooltip |
| v145 | 2026-09-19 | `ee5ea13` | Military Overview unit supply and Economic Overview gold rows |
| v144 | 2026-09-19 | `c561ad5` | gold deficit flag and city-screen sell building |
| v143 | 2026-09-19 | `c477c08` | pending steal-tech in todo and on the notice |
| v142 | 2026-09-19 | `5a8943c` | conversion banner, empty-queue vs process, Discuss flags |
| v141 | 2026-09-19 | `436e356` | top-bar science/culture/tourism/faith; combat result holes |
| v140 | 2026-09-19 | `e5ec3dd` | map index, named deal cities, CS unit gift |
| v139 | 2026-09-19 | `53fda00` | remaining information-parity reads |
| v136 | 2026-09-19 | `7325f84` | docs: notes + handoff through t150 |
| v136 | 2026-09-19 | `30e6363` | attack_targets / move_unit: a garrisoned enemy city is fought as the city; result says city_captured |
| v135 | 2026-09-19 | `7846f17` | move_unit: a captured civilian reports captured + the new unit id, not defender_killed |
| v134 | 2026-09-19 | `cad1951` | docs: notes + handoff through t100 |
| v134 | 2026-09-19 | `5e7b5c8` | free_great_person_options / choose: only this civ's own great people |
| v133 | 2026-09-19 | `b1bae90` | unit_mission builds: name the build in progress and its turns left; say when a feature removal runs first |
| v132 | 2026-09-19 | `2192fe0` | disband_unit: say when the refusal is 'no moves left this turn' |
| v131 | 2026-09-19 | `1907dcb` | move_unit / resume_moves: refuse a destination held by a civ we are at peace with |
| v130 | 2026-09-19 | `4ff285a` | available_city_strikes: target hp + expected damage (UpdateCombatOddsCityVsUnit) |
| v129 | 2026-09-19 | `f752d7a` | docs: notes + handoff through t33 |
| v129 | 2026-09-19 | `c47e282` | unit_mission: a refused order keeps the unit's standing move |
| v128 | 2026-09-19 | `9dfbbbe` | docs: notes + handoff through t19 |
| v128 | 2026-09-19 | `6f5d2fc` | religion_overview: rival pantheons as the Beliefs tab lists them |
| v127 | 2026-09-19 | `2959d92` | city_capture_options / choose_city_capture: BUTTONPOPUP_CITY_CAPTURED with unhappiness deltas + warmonger preview |
| v126 | 2026-09-19 | `77a1078` | war_consequences: the declare-war confirmation's warnings as a read |
| v125 | 2026-09-19 | `7d49e36` | docs: notes + handoff through t11 |
| v125 | 2026-09-19 | `8739bcd` | city_state_actions / city_state_action: quests, pledge, tribute, war and peace as the city-state screen does them |
| v124 | 2026-09-19 | `4ff475d` | trade_catalog: a tradeable city's x,y only once its plot is revealed |
| v123 | 2026-09-19 | `2fc3250` | religion_overview: the Religion Overview screen's three tabs, unmet founders masked |
| v121 | 2026-09-19 | `67b3f8e` | attack previews for city assault and ranged shots; enemy-city melee listed and never stored as a standing move |
| v119 | 2026-09-19 | `5345a35` | available_beliefs + add_reformation_belief; found/enhance validate each belief against its slot's available list |
| v118 | 2026-09-19 | `fcf3cb6` | goody_hut_options / choose_goody_hut: Shoshone Pathfinder ruins choice via Network.SendGoodyChoice |
| v117 | 2026-09-19 | `a7ced23` | league_status votable: yes_no flag; luxury bans name the resource and our count |
| v116 | 2026-09-19 | `c1814d7` | incoming_deal: say whether a luxury we would receive is new to us |
| v115 | 2026-09-19 | `979328c` | culture_overview tool; civ_eliminated digest event |
| v87 | 2026-09-18 | `ad98816` | Combat provenance in turn_digest: named attacker/defender, plots, hp; hp-diff fallback across the AI phase |
| v83 | 2026-09-17 | `4ea6311` | unit_mission: refuse MISSION_SKIP on a unit mid multi-turn move |
| v82 | 2026-09-17 | `ba6e6a1` | city_state_gifts: rivals influence list |
| v81 | 2026-09-17 | `9c8d4a5` | incoming_deal: us_owned undoes export-net totals; renewals are not last copies |
| v80 | 2026-09-17 | `499b7b3` | incoming_deal: resource items we would give carry copies/import/export and last_copy |
| v79 | 2026-09-17 | `87804b3` | available_production: faith rows listed before they are affordable, faith_can_buy |
| v78 | 2026-09-17 | `38987ea` | available_production: faith purchase costs and faith-only rows |
| v77 | 2026-09-17 | `e3f469c` | cities: majority religion name |
| v76 | 2026-09-17 | `bd95025` | explore_frontier: reachability respects borders |
| v75 | 2026-09-17 | `892efb2` | generic_popup / answer_popup: drive the game's yes/no confirmations |
| v72 | 2026-09-17 | `455d983` | explore_frontier: reachable flag via flood fill over the revealed map |
| v71 | 2026-09-17 | `469290f` | disband_unit: COMMAND_DELETE with polled confirmation and measured effects |
| v69 | 2026-09-17 | `7f72ec1` | overview: strategic_resources with available/total for revealed resources |
| v67 | 2026-09-17 | `7ff0363` | trade_catalog: per-resource copy counts and last_copy luxury warning |
| v65 | 2026-09-17 | `1621921` | explore_frontier: flag polar map_edge plots |
| v63 | 2026-09-17 | `aa7ccd2` | unit_mission: measured effects for MISSION_SPREAD_RELIGION / REMOVE_HERESY |

</details>
