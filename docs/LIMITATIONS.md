# Declared limitations

What the harness will not do, and why, as of runtime v207 (2026-09-25). Each item was checked against the
engine, not inferred; the check is named. `docs/GAPS.md` keeps the full audit history.

## Engine rules that look like missing features

- **Melee fire support never fires.** Stock Brave New World ships `FIRE_SUPPORT_DISABLED = 1` in
  `GlobalDefines` (base and expansion2), so `Unit:GetFireSupportUnit` returns nothing even with a ranged unit
  adjacent to the defender, in range, with line of sight and attacks left (S1 t266). The preview's
  `fire_support_damage` is a faithful 0; it would light up under a mod that flips the define.
- **Lump-sum gold needs a Declaration of Friendship.** A Brave New World rule for humans and AIs alike;
  gold per turn is not gated. The stock pocket just hides the Gold row; the trade catalog's `gold.note` says why
  (checked S1 t266: of four met civs only the friend traded lump gold either way).
- **Ranged units need line of sight** unless they have Indirect Fire (`CanRangeStrikeAt` false through a
  hill), exactly as the stock game plays it.
- **The golden-age combat row** exists only for a civ whose trait sets `GetTraitGoldenAgeCombatModifier`
  (Persia). Other seats can never show it. Seen live S6 t214 (Persia, "Golden Age Bonus +10").
- **Forced peace lasts through the treaty's final turn.** an order to declare war is refused with "forced peace in
  effect" on the treaty's `final_turn` itself (S2b t236); war is possible from the next turn.
- **The end-turn blocker is frozen while a popup is up.** `GetEndTurnBlockingType` is not re-evaluated
  while `UI.IsPopupUp()`, so the last ready unit's order plus an announcement popup raised on the way (a
  city-state met by that unit, a natural wonder, a text box) leaves `ENDTURN_BLOCKING_UNITS` on the books
  with `HasReadyUnit()` false (S6 line t215-t216, GitLab #23). the status reports it as `blocking_stale`
  with `todo` computed live; `turn(action="finish")` sweeps the popup and the engine re-evaluates at once.

## Engine calls the harness refuses to make

- **Path overlay and movement cost.** `Unit:GeneratePath` throws (not implemented), `GetPathEndTurnPlot`
  needs the mouse pathfinder, and `Plot:MovementCost` crashed the process (t183) even inside `pcall`. The
  harness never invents turns-to-reach; the frontier read reports hex distance over the revealed map,
  the tactical view reports per neighbour what a move would be refused before sending and, for an open step,
  its cost and the zone of control that ends it (read off the engine's movement rules, not Plot:MovementCost),
  and the tile carries its yields, fresh water, routes and resource hover instead. Trade-route lines are a
  different thing and are readable: the trade-routes screen's `path` is the plot hover's route list on every
  revealed plot (runtime v212), with the caravan, its escort and enemies beside the line.
- **Estimates the engine does not compute.** `compare`'s `estimated_change` is city arithmetic from the
  building's table rows and this turn's base yields and modifiers; empire-level modifiers, policies, beliefs
  and happiness effects are not applied, and a unit's share of empire upkeep is reported "unknown". A
  locked tech's `path_turns_estimate` assumes this turn's science throughout. A trade destination's hazard
  is read around both ends only, because the route's path is not known before it is set.
- **Headless deal building.** Every `Add*` on `UI.GetScratchDeal()` outside a real trade session crashed
  the game (eight crashes, 2026-09-16). All deals, peace terms, demands and vote pledges drive the real
  leader and trade screens and read the reply from them.
- **Choosing a puppet's production, buying its plots or managing its citizens.** The engine accepts these
  orders; the stock city screen never offers them. Venice's puppets expose only their purchase list
  (`purchase_only`), as the stock production popup does.
- **Running the gamecore from another seat.** Every read and write is refused unless that seat is active
  (`this seat is not active`), so nothing about another human's pending answer leaks before their turn.

## Information the harness withholds on purpose

The seat sees what a human in that seat sees, and no more: fogged tiles carry last-seen features and
improvements but no live occupants; unmet civs stay masked in demographics and league rows; a rival's tech
list is never listed behind an embassy (only techs ahead of us, as the stock screen shows); deal rows carry
coordinates only for revealed cities; no private AI state (approach, deal valuation) is ever read.

With a seat table on tunerd (`--seats`; `docs/AGENT_INSTALL.md`, "Two agents, one game") the channel itself is
bound: a connection plays the seat its token or OS user names, the daemon writes that seat into every call, and
another seat's map is not readable through the harness at all. Two things stay outside the harness's channel: the
game window on a shared display shows the active seat's map to anyone who can see the screen, and hotseat save
files are plain files of the user running the game. Separate machines, or a LAN game, close both.

## Still to be seen live

The four states this section used to wait for have all been reached: the Switch Ideology button and the
switch with anarchy (GitLab #13, S4 t239), a capture of our civilian by the other human seat (#22, S2b
t237-238), Venice buying in a puppet (#15, S5 t215), and the greeting popup that leaves
`ENDTURN_BLOCKING_UNITS` with an empty todo (#23, S6 line t215-t216). What remains has regression coverage
only:

- **War on a city-state over LAN.** an order to declare war on a minor sends `DoFromUIDiploEvent` where the stock
  screen sends `Network.SendChangeWar` (`docs/COVERAGE_AUDIT_2026-09-19.md`, G-D3). It works on the
  active seat; whether the declaration syncs to the other machines of a LAN game has not been checked.
- **LAN mode since 0.5.0.** Every live row on the 0.5.0 and 1.0.0 tables is a solo or hotseat game.
  `join_lan`, `host_lan`, the second-instance client and the supervisor's rejoin rest on the earlier
  sessions in `docs/NOTES.md`; `tests/test_supervisor.py` covers the supervisor's decisions.
- **Game over.** After the last spaceship part the end-turn blocker keeps reading whatever it read last
  (`ENDTURN_BLOCKING_PRODUCTION` at the t457 win, `ENDTURN_BLOCKING_UNITS` with `blocking_stale: true` at the
  t502 one, `docs/NOTES.md`); the status's `game_over` and the `game_over` gate are the reads to trust, since
  the engine never re-evaluates the blocker once the game has ended. Seen live twice on the same solo game
  (S7 `Wu Zetian_0502 science-victory-eve` is the state one mission order before the win).
