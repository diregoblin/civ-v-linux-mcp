"""Units, the map and the popups a unit's move raises.

One of the civ5 MCP server's tool modules: every tool here registers on the server in
harness/mcp_server.py, which keeps the game handle, the guard and the tool sets (see its docstring).
"""
from __future__ import annotations

from harness import mcp_server as core
from harness.mcp_server import J, guarded, retired


@retired
@guarded
def unit_home_options(unit_id: int) -> str:
    """Where a trade unit or a Great Admiral could re-home (the Change Home City / Change Port
    chooser). Both need the unit to be standing in one of my cities; outside one there is no button,
    and the answer says so. `cities` is the engine's own candidate list -- apply one with
    unit_mission(unit_id, mission, x, y) using the `mission` in the reply. Re-homing a caravan nearer a
    richer partner is how a 6-gold route becomes a 12-gold one; see available_trade_routes after. Each city carries `call`, the unit_mission that re-homes there (#47)."""
    return J(core.game().unit_home_options(unit_id))


@retired
@guarded
def units() -> str:
    """My units with position, moves left, hp, strength, current promotions, XP toward the next
    promotion (`xp` / `xp_needed`), and whether they still need orders. `garrisoned` is the Military
    Overview status. `upgrade_to` / `upgrade_gold` / `can_upgrade` are the unit-panel upgrade preview
    when a path exists; `upgrade_blocked` (when can_upgrade is false) is the panel's red lines: reason
    territory / city / gold / resources (each short one) / stacking, unavailable (the target cannot be
    trained yet: `prereq_tech`) or moved. A religious unit carries `religion` (the faith it spreads, which is the one of
    the city it was bought in -- not necessarily yours) and `spreads_left`, as the unit panel names it. A Worker mid-job carries `build` (BUILD_*) and `build_turns_left` as the unit
    panel's "Trading Post (6)" line; `mission_name` names a standing MISSION_* (e.g. ROUTE_TO). `territory`
    {player_id, owner, city_state} is whose land the unit stands on when it is not mine (a unit in a
    city-state's land costs influence each turn); absent on my own or unowned land. Each row carries `actions`: the read that lists its orders (#47)."""
    return J(core.game().units())


@retired
@guarded
def maya_options() -> str:
    """Pending Maya Long Count rewards, including unavailable types and the baktun when chosen; `answers` the
    choose_maya_bonus rows still open."""
    return J(core.game().maya_options())


@retired
@guarded
def choose_maya_bonus(unit: str) -> str:
    """Choose an available UNIT_* from maya_options (unit="UNIT_PROPHET", ...) and verify the reward was
    consumed."""
    return J(core.game().choose_maya_bonus(unit))


@retired
@guarded
def archaeology_options() -> str:
    """Completed dig: artifact origins/era, available art/writing slots, artifact vs landmark
    or writing vs culture choices. Unmet artifact origins are masked. `answers`: the choose_archaeology rows."""
    return J(core.game().archaeology_options())


@retired
@guarded
def choose_archaeology(choice: int, x: int, y: int) -> str:
    """Confirm a choice ID at the completed dig's x,y from archaeology_options. Verifies resolution."""
    return J(core.game().choose_archaeology(choice, x, y))


@retired
@guarded
def unit_mission_targets(unit_id: int, mission: str, offset: int = 0, limit: int = 100) -> str:
    """Legal visible targets for an air strike/sweep, nuke, paradrop, rebase or airlift mission
    listed in available_unit_actions. Paginated: `offset` / `limit` (at most 100 per page; `total` says how
    many exist); use unit_mission to issue the order.
    Air strikes include target details and a combat preview with retaliation, strength and visible
    interceptors. Expected damage taken excludes interception; unseen interceptors may still exist.
    Fogged destinations are excluded because legality could expose hidden occupants. Each target carries `call`, its unit_mission row (#47)."""
    return J(core.game().unit_mission_targets(unit_id, mission, offset, limit))


@retired
@guarded
def map_window(x: int, y: int, radius: int = 3) -> str:
    """Revealed plots within `radius` of (x, y). vis=true is in sight now and includes yields
    (food/production/gold/science/culture/faith), fresh_water, worked, under_construction, trade_route
    (the plot hover's "Trade Route": a city connection to the capital, not a caravan line; those are
    trade_routes().path), and live units/cities (units have strength/promotions; a city banner has strength, garrison,
    puppet/razing, religion). A resource tile carries `resource` (and `resource_qty`); what a
    resource gives when improved, its happiness and its blurb are in reference("resources"), once, not
    on every tile. A revealed Oil/Aluminum/Coal tile that we cannot yet hook has
    `resource_requires_tech`. A barbarian camp with a city-state kill-camp quest has `cs_quest`.
    vis=false is discovered but fogged (no live units/owners/features/yields). Prefer known_world
    for the full discovered map."""
    return J(core.game().plots_around(x, y, radius))


@retired
@guarded
def explore_frontier(unit_id: int, limit: int = 12) -> str:
    """Where the known map ends for this unit: revealed, passable plots of its domain (sea for a ship, land otherwise) that border unrevealed plots, nearest first. Each has unrevealed_neighbors (how much stepping there reveals), distance (hex distance, not path length), reachable (true when a route exists through the already-revealed map; false = behind land or an unknown strait, listed last), terrain t (a Trireme cannot enter OCEAN), map_edge=true on the polar rows (mostly ice beyond), and `occupied` {player_id, unit} when a visible unit of another player stands there or `city` {player_id, name} when it is another player's city (move_unit would refuse both; such plots sort after the free ones, and the list keeps the ones no farther than the farthest free plot shown). move_unit refuses unrevealed targets, so an explorer picks its next stop from here. frontier_total / unrevealed_plots say how much is left; note explains an empty list. `limit` is how many free plots to list (default 12)."""
    return J(core.game().explore_frontier(unit_id, limit=limit))


@retired
@guarded
def tactical_view(unit_id: int, radius: int | None = None, detail: str = "summary") -> str:
    """One unit's surroundings in one read, for choosing its move or attack. `neighbors` are the six adjacent plots
    by coordinate and direction (NE, E, SE, SW, W, NW; the engine's own adjacency, so map wrap and the edge rows
    need no hex arithmetic), each with terrain, river_crossing, owner, visible units and `move`: attack (a melee
    attack; its preview is in targets), open (move_unit would send the order), refused (move_unit would refuse it,
    `why` says why) or enemy (a visible enemy this unit cannot melee). An open step says its `cost` and the moves
    `left` after it, and `zoc` when an enemy's zone of control ends the move there; no turns-to-reach. `targets` are the unit's melee and ranged targets with the combat previews
    available_unit_actions gives. `occupants` (visible units, hostile first) and `cities` (a fogged one is
    last_seen) cover `radius` (1-5; by default as far as this unit itself sees or shoots, at least 2); `fog` counts
    visible, fogged and unrevealed plots there, and unseen_within_2 is how many plots within two cannot be seen:
    fog can hide units, so nothing is called safe. `unit.sight` is this unit's own line of sight from the engine
    (range, on_hills, plots, reach: high ground adds a plot, hills and forest in between block); a ranged unit's
    `unit.fire_los` is the same test with its attack range, the one a ranged attack must pass (a Crossbowman on a
    hill reaches 3); occupant and city rows say in_sight / in_fire_los. `grid` is a lettered picture of the same
    area; its `legend` comes once per server session, then a one-line `key` names the reference section that holds
    it (how_to_play("tactical_view")); `players` names every owner id in the reply. detail="full" adds `plots` (every revealed
    plot in radius, as map_window reads it) and the previews' modifier rows."""
    return J(core.game().tactical_view(unit_id, radius=radius, detail=detail))


@retired
@guarded
def known_world() -> str:
    """Everything this seat knows: empire, own units/cities, met civs and city-states, notifications, and every revealed plot. Fogged plots have vis=false and omit live occupants; unrevealed tiles are absent."""
    return J(core.game().known_world())


@retired
@guarded
def map_index() -> str:
    """Compact map scan: revealed luxuries/strategics, barb camps, ruins, met foreign cities,
    visible natural wonders, and in-sight world wonders. A camp with a city-state kill-camp quest
    carries `cs_quest` (met CS only). Prefer this over known_world unless you need every plot."""
    return J(core.game().map_index())


@retired
@guarded
def revealed_map(layers: list[str] | None = None, x0: int | None = None, y0: int | None = None,
                 x1: int | None = None, y1: int | None = None) -> str:
    """The whole revealed map at a glance, as character grids: one string per row (north first), one
    character per plot, one grid per layer. Layers: vis ('#' in sight now, '~' revealed but fogged:
    what you see there is what was last seen and may be stale until a unit gets eyes back on it, ' '
    unrevealed), terrain, elevation (hills/mountain), river, owner (borders), feature, improvement,
    resource, route. Each reply carries its own legend (letters are assigned per reply). Fog rules are
    the human's: a fogged plot shows remembered feature/improvement/route/owner, never live units or
    pillage. Pass `layers` to fetch a subset and x0/y0/x1/y1 to window a large map (a Huge map after
    Satellites is about 10 KB per layer). map_window(x, y, r) reads one area in full; map_index lists
    cities, camps and resources with coordinates."""
    return J(core.game().revealed_map(layers=layers, x0=x0, y0=y0, x1=x1, y1=y1))


@retired
@guarded
def generic_popup() -> str:
    """Read the open yes/no confirmation (the game's generic popup): its text and numbered buttons, and `answers`
    (one answer_popup row per button).
    These are BUTTONPOPUP_RETURN_CIVILIAN (keep a captured civilian or return it: returning to a city-state
    gives +30 influence, to an AI a diplomatic bonus), ANNEX_CITY / PUPPET_CITY after a conquest,
    BARBARIAN_RANSOM, MINOR_CIV_ENTER_TERRITORY, CONFIRM_COMMAND and the like. Nothing else moves while one
    is open ("popup needs a decision"). Answer with answer_popup(button)."""
    return J(core.game().generic_popup())


@retired
@guarded
def answer_popup(button: int) -> str:
    """Press one button (1-based id from generic_popup) of the open generic confirmation. Runs the button's
    real handler (e.g. Network.SendReturnCivilian) and closes the window. Returns `discussion_pending`
    because some answers make an AI leader speak next (dismiss_discussion)."""
    return J(core.game().answer_popup(button))


@retired
@guarded
def goody_hut_options() -> str:
    """When turn_status.pending_popups shows BUTTONPOPUP_CHOOSE_GOODY_HUT_REWARD (a Shoshone Pathfinder entered
    ancient ruins): the rewards on offer, each with the popup's own description; `answers` the choose_goody_hut rows."""
    return J(core.game().goody_hut_options())


@retired
@guarded
def choose_goody_hut(goody: str) -> str:
    """Take one ruins reward from goody_hut_options, e.g. goody="GOODY_CULTURE"."""
    return J(core.game().choose_goody_hut(goody))


@retired
@guarded
def available_unit_actions(unit_id: int) -> str:
    """Legal unit-panel actions for this unit right now (missions, tile builds on ITS plot, commands,
    promotions). Call this before unit_mission. Move-to is a separate tool (move_unit). Does not select
    the unit or pan the camera. For Workers/Work Boats also returns `nearby_builds`: plots within 2 tiles
    that still need work (unimproved, or pillaged) with the builds legal there -- move_unit onto one, then
    unit_mission(MISSION_BUILD, build=...). `build_info` adds the unit-panel turns and yield_delta for each
    build. A build issued with 0 moves left starts next turn. `ranged_targets` includes combat strength
    and expected damage; air previews include retaliation and a warning about interception.
    Melee previews include `fire_support_damage` in damage taken and its effect on damage dealt.
    `promotions` are the chooser's own rows -- `promotion` (pass this to choose_promotion) and `name`;
    what each does is in reference("promotions"). An action row's `help` is only the line the panel
    computes for this unit (upgrade target and price, scrap gold, golden age length, paradrop range);
    the standing sentence for every action is in reference("actions"). Every action, target and promotion carries `call` (and `read` when it opens a chooser): the row that takes it (#47).
    `missing` (#142): the Great Person missions this unit's class has that the engine withholds here, each with `why`
    (slots filled / total and the buildings that carry one; the nearest plot that qualifies for a concert tour or a
    trade mission). A COMMAND_GIFT row names the city-state whose plot the unit stands on (`owner`, `minor_id`)."""
    return J(core.game().available_unit_actions(unit_id))


@retired
@guarded
def todo_actions(unit_ids: list[int] | None = None, full: bool = False, detail: str = "",
                 limit: int | None = None) -> str:
    """Legal actions for many units in one call. With no `unit_ids`: every unit in `turn_status.todo.units`
    (still needs an order) plus every unit with a promotion waiting; with `unit_ids`: exactly those.
    Each row is what `available_unit_actions` returns for that unit (actions, promotions, nearby_builds,
    attack_targets, ranged_targets, moves, x, y) plus `id`, `type` and `promotion_ready`. Action rows
    drop the computed `help` line (upgrade price, scrap gold) unless `full=true`; the standing text
    for every action and promotion is in reference("actions") / reference("promotions"). One query instead of one per unit: the
    read for a whole turn's units in one call. Refused while it is not our turn unless unit_ids is given.
    `detail`: "normal" (default, the rows above), "full" (same as full=true) or "summary": per unit only id,
    type, x, y, moves, promotion_ready, `actions` as the orders themselves -- {tool, args} rows for do(), one
    per non-routine action, melee target, ranged target and promotion; a row with `choose` names the arguments
    still to pick from the read before it -- minus the everyday ones (move, route, skip, sleep, fortify,
    alert, wake, cancel, delete, automate/stop, remove route -- listed once in `routine_actions`, counted per
    unit in `routine`), `promotions` (enums), `attack` / `ranged` targets (x, y, unit or city, owner, hp; no
    preview) and `build_plots` (x, y, builds, resource).
    `drill_down` gives the exact todo_actions arguments for the normal rows. Same single read at every level;
    a summary of 38 units is a fraction of the normal size. `limit` returns the first N units in todo order
    and lists the rest in `omitted` (count, ids, the args that fetch them). Every reply has `detail`, `n`
    (total units) and `returned`."""
    return J(core.game().todo_actions(unit_ids or None, full, detail=detail or None, limit=limit))


@retired
@guarded
def choose_promotion(unit_id: int, promotion: str) -> str:
    """Choose an earned promotion, using its PROMOTION_ name."""
    return J(core.game().choose_promotion(unit_id, promotion))


@retired
@guarded
def upgrade_unit(unit_id: int) -> str:
    """Upgrade a unit for gold along its upgrade path (e.g. Warrior -> Swordsman). Needs full moves,
    own/allied territory, the gold and any strategic resource. The engine replaces the unit: use the
    returned `unit_id` (new) from now on, not the one passed in; its assignments and open order follow it
    (`carried_over`). available_unit_actions lists COMMAND_UPGRADE when possible."""
    return J(core.game().upgrade_unit(unit_id))


@retired
@guarded
def disband_unit(unit_id: int) -> str:
    """Disband (delete) one of my units -- the unit panel's Disband button. Irreversible. Frees its gold
    maintenance and any strategic resource it consumes (e.g. an obsolete Swordsman holding Iron). Returns
    `effects.before/after` with unit count and strategic_resources so the freed resource is measured."""
    return J(core.game().disband_unit(unit_id))


@retired
@guarded
def move_unit(unit_id: int, x: int, y: int, then: str | None = None) -> str:
    """Order one of my units to move to plot (x, y) (multi-turn paths allowed, like a right-click).
    Selects the unit like the unit panel does (orders go through the game's network path).
    A unit on a conditional order (give_order) is taken back: the order pauses (`order_paused`).
    then="fortify" | "sleep" | "alert" | "hold": hold once there -- this turn when it arrives with moves left,
    else the turn it arrives (#105: "go there and hold" is one order, and the unit does not block the finish)."""
    g = core.game()
    # fakes keep the three-argument shape
    return J(_took_back(g, unit_id, "move_unit",
                        lambda: g.move_unit(unit_id, x, y, then=then) if then else g.move_unit(unit_id, x, y)))


def _took_back(g, unit_id: int, tool: str, command) -> dict:
    """A direct command to a unit an order owns takes it from that order (#32), never from one the command itself
    creates (#182): Game.direct_command holds the rule. A test double without it just runs the command."""
    direct = getattr(g, "direct_command", None)
    return direct(unit_id, tool, command) if direct is not None else command()


@retired
@guarded
def unit_mission(unit_id: int, mission: str, x: int = -1, y: int = -1, build: str = "") -> str:
    """Give a unit a mission: MISSION_FOUND (settle here), MISSION_FORTIFY, MISSION_SLEEP, MISSION_SKIP, MISSION_HEAL
    (fortify until healed), MISSION_ALERT, MISSION_RANGE_ATTACK (x,y), MISSION_PILLAGE (result includes gold_gained),
    MISSION_EMBARK/DISEMBARK... A unit that can fortify is refused MISSION_SLEEP (use MISSION_FORTIFY); one that
    cannot (mounted, siege, naval, civilians) is refused MISSION_FORTIFY (use MISSION_SLEEP). A refusal carries
    `legal_missions`, a `reason` when one is known, and `did_you_mean` after a name the engine does not have.
    An **air strike is MISSION_MOVE_TO onto the target plot** (that is how the game issues it); like a
    melee move onto an enemy, the result then carries `attack` with both sides' hp before/after and who died.
    An intercepted strike says so: `attack.intercepted`, `interceptor`, `shot_down` (from the game's own banner).
    MISSION_BUILD: pass the improvement in `build`, e.g. build="BUILD_FARM" (do NOT put it in x/y --
    those are for movement-shaped missions). Builds on the unit's own tile.
    MISSION_SPREAD_RELIGION / MISSION_REMOVE_HERESY: the unit must be inside or adjacent to the target city;
    the result's `effects` reports that city's followers/majority before and after, spreads_left, and (for a
    city-state) influence before/after, so no follow-up read is needed to know whether the spread worked.
    MISSION_CREATE_GREAT_WORK: the reply's `great_work` names the work and the city/building slot it filled.
    AUTOMATE_EXPLORE / AUTOMATE_BUILD (the unit panel's automation buttons, when available_unit_actions lists
    them) hand the unit to the game's own automation; it then never blocks end_turn. The reply has automated=true,
    and the unit is listed under turn_status.todo.ongoing until a new move_unit / unit_mission takes it back.
    Selects the unit like the unit panel does (orders go through the game's network path).
    A unit on a conditional order (give_order) is taken back: the order pauses (`order_paused`)."""
    if mission.startswith("BUILD_") and not build:
        # available_unit_actions lists builds by their BUILD_* type; take that name as given
        mission, build = "MISSION_BUILD", mission
    g = core.game()
    return J(_took_back(g, unit_id, "unit_mission", lambda: g.unit_mission(unit_id, mission, x, y, build=(build or None))))
