"""The notebook: notes, assignments and conditional orders (what a human keeps in their head).

One of the civ5 MCP server's tool modules: every tool here registers on the server in
harness/mcp_server.py, which keeps the game handle, the guard and the tool sets (see its docstring).
"""
from __future__ import annotations

from harness import mcp_server as core
from harness.mcp_server import J, guarded, retired


@retired
@guarded
def remember(text: str, tag: str = "", replace_id: int | None = None, retag: bool = False) -> str:
    """Write a note to my notebook for this game: the plan, a promise, a threat, why I did something
    ("Tradition then Rationalism", "Askia denounced me t140: expect a DoW", "keep 2 archers in Moson Kahni").
    Notes survive session restarts and context loss: they live beside the game (one notebook per game and
    seat, keyed by the game's identity), and the latest ones ride along in every finish_turn result.
    tag groups notes (plan, threat, diplomacy, todo...). replace_id rewrites an existing note in place, so a
    living plan stays one note instead of a trail of superseded ones; the result carries `previous` (the
    text, tag and turn it overwrote). A replace whose tag differs from the stored tag is refused with
    `stored_tag` and writes nothing (the id was probably wrong); an empty tag keeps the stored tag, and
    retag=true allows the change. Usable while it is not my turn."""
    g = core.game()
    return J(g.notebook().remember(text, turn=g.turn_state().get("turn", -1), tag=tag, replace_id=replace_id,
                                   retag=retag, units=g.note_unit_refs(text)))


@retired
@guarded
def recall(tag: str = "", limit: int = 50) -> str:
    """Read my notebook for this game (see remember): every note with its id, the turn it was written on
    and its tag; tag filters, `limit` is the newest N (default 50). The last few also arrive with each
    finish_turn result. Usable while it is not my turn."""
    g = core.game()
    try:
        turn = g.turn_state().get("turn")
    except Exception:  # recall works from the menu and under any screen: the turn is only for the #62 mark
        turn = None
    r = g.notebook().recall(tag=tag, limit=limit, turn=turn if isinstance(turn, int) else None)
    if isinstance(r, dict) and isinstance(r.get("notes"), list):
        r["notes"] = g.notes_with_unit_check(r["notes"])   # #63
    return J(r)


@retired
@guarded
def forget(note_id: int) -> str:
    """Delete one note from my notebook by id (recall lists them)."""
    return J(core.game().notebook().forget(note_id))


@retired
@guarded
def assign(role: str, purpose: str, unit_ids: list[int] | None = None, city_ids: list[int] | None = None,
           target: dict | None = None, done_when: dict | str | None = None, review: dict | None = None,
           replace_id: int | None = None) -> str:
    """Give units or cities a structured assignment in my notebook: what they are for, where, when it is done
    and when to look again. A prose note (remember) says why; an assignment lets a later me -- after a context
    reset, in a new session -- see at once what each unit is doing and whether that still holds.
    role: a short word (escort, settle, improve, defend, explore, diplomacy...). purpose: one sentence.
    unit_ids / city_ids: mine, now; each is fingerprinted (type and creation turn; name and founding turn), so
    if an id later names a different unit the assignment says the assigned one is gone instead of following it.
    target: {x, y} a plot (a city site, a tile to improve, a city to take or hold), {unit_id, owner} a foreign
    unit, or {player} a civ or city-state. done_when (checked on every read; default "manual"): {kind:
    "unit_at"|"city_at"|"improvement", x, y} (x, y default to the target plot; unit_at takes unit_id,
    improvement takes improvement e.g. "FARM"), {kind: "building", city_id, building}, {kind: "tech", tech}.
    review (optional): {turn: N, hostile_within: plots, hp_below: percent, max_distance: plots} -- look again at
    turn N, when a visible hostile comes that close to an assigned unit or city, when an assigned unit's hp drops
    below, when an assigned unit stands farther than that from the target plot (0 for a garrison: off its plot;
    every unit row carries `distance` to a plot target either way).
    replace_id: this replaces that assignment, which is closed as replaced (the two never compete).
    The answer is the stored assignment reconciled right away (see assignments). One game read."""
    g = core.game()
    return J(g.assign(role, purpose, unit_ids=unit_ids, city_ids=city_ids, target=target, done_when=done_when,
                      review=review, replace_id=replace_id))


@retired
@guarded
def assignments(status: str = "active") -> str:
    """My assignments (see assign), each reconciled against what I can see now, in one game read. An active row:
    id, role, purpose, since_turn, `state` -- condition_met (its done_when holds: `evidence` says how;
    close_assignment it), needs_review (`reasons` lists each observation: an assigned unit missing or gone -- an
    upgrade on its last plot is named --, a city no longer mine, the target plot's owner changed or a city now
    too close to a site, a target unit not where last seen, a war or elimination, the review turn, a hostile
    within range, low hp, a unit farther from its target plot than review.max_distance) or on_track --, `units`
    (each with `distance` to a plot target) / `cities` as they are now, `target` as observed (a fogged
    plot or an out-of-sight unit is `known`: stale / unknown with when it was last seen; never assumed gone or
    still there), done_when and review. Nothing is closed, re-targeted or ordered for me.
    status: "active" (default), "closed" (completed, cancelled, replaced), or "all". briefing() carries the
    active ones compactly, needing-a-look first."""
    return J(core.game().assignments(status=status))


@retired
@guarded
def amend_assignment(assignment_id: int, role: str | None = None, purpose: str | None = None,
                     unit_ids: list[int] | None = None, city_ids: list[int] | None = None,
                     target: dict | None = None, done_when: dict | str | None = None, review: dict | None = None,
                     note: str = "") -> str:
    """Change an active assignment in place: only the fields given change (role, purpose, done_when and review
    as in assign; unit_ids / city_ids replace the list; target={} clears the target; review={} clears the triggers). Use it when a unit was upgraded (new id), a
    site moved, or the review turn passed and the plan still holds. note is kept in the assignment's history.
    The answer is the amended assignment reconciled now, with `previous` values. One game read."""
    changes = {k: v for k, v in (("role", role), ("purpose", purpose), ("unit_ids", unit_ids), ("city_ids", city_ids),
                                 ("target", target), ("done_when", done_when), ("review", review)) if v is not None}
    return J(core.game().amend_assignment(assignment_id, changes, note=note))


@retired
@guarded
def close_assignment(assignment_id: int, outcome: str = "completed", note: str = "") -> str:
    """Close an active assignment: outcome "completed" or "cancelled", with an optional note (why). Closed ones
    leave the briefing and stay readable with assignments(status="closed"). Usable while it is not my turn."""
    return J(core.game().close_assignment(assignment_id, outcome=outcome, note=note))


@retired
@guarded
def give_order(unit_id: int, steps: list[dict | str], interrupt: dict | None = None, purpose: str = "",
               replace_id: int | None = None, start: bool = True) -> str:
    """Give one of my units a short sequence of steps the harness carries out over the coming turns, so a plan
    already chosen does not cost a call every turn. steps (at most 6, in order): {kind: "move", x, y} walk
    there (multi-turn); {kind: "build", build: "FARM"} build it where the previous move ends (x, y name
    another plot); {kind: "heal", hp: 80} heal to at least that percent (default 100); {kind: "hold", mission:
    "fortify"|"sleep"|"alert"} as the last step. Example: move to (12,8) then build FARM; or heal to 80, move
    to (30,14), hold. purpose is a free-text label for the order.
    It runs now (start=true) as far as it can -- a move spends this turn's movement, a build starts -- then at
    the start of each of my turns (finish_turn / wait_for_my_turn carry `orders`), each step at most once per
    turn and the next as soon as one completes, through move_unit / unit_mission. It pauses
    and hands the unit back with `pause.reason` and `hint` when a hostile comes into sight within
    interrupt.hostile_within plots (default 2; 0 off), the unit was damaged (interrupt.damaged, default true)
    or is below interrupt.hp_below, an enemy stands on the destination (an order never attacks), a step is
    refused or makes no progress, a save was loaded, or I give the unit a direct order. An order never declares
    war, attacks, ends the turn or touches another unit; a unit on automation leaves it as soon as the order
    is stored. One open order per unit (replace_id replaces it); a first step that cannot run now refuses the
    order. Stored in my notebook: orders survive a restart, briefing() lists them, resume_order / cancel_order
    finish a paused one. Every interrupt and state: how_to_play("give_order")."""
    return J(core.game().give_order(unit_id, steps, interrupt=interrupt, purpose=purpose, replace_id=replace_id,
                               start=start))


@retired
@guarded
def orders(status: str = "open") -> str:
    """My conditional orders (see give_order) as stored, without reading the game: id, unit, status (active /
    paused; completed, cancelled, replaced, failed once closed), step N of M and `now` (the current step),
    `steps`, `state` (moving, building, healing, no_moves...), `pause` (kind, reason, hint, turn) when it waits
    for me, `last` (the last step issued: turn, what, ok, err / note), `issued_count` (calls it made for me),
    `purpose`. status: "open" (default), "closed" or "all". Usable while it is not my turn."""
    return J(core.game().orders(status=status))


@retired
@guarded
def resume_order(order_id: int) -> str:
    """Hand a paused order its unit back and run it now (an active one just runs now). What paused it -- the
    hostiles in sight, the hp now -- is taken as seen, so only something new pauses it again. Every step is
    re-checked against the board first: a step completed meanwhile is not issued again. To change the plan
    instead, give_order with replace_id."""
    return J(core.game().resume_order(order_id))


@retired
@guarded
def cancel_order(order_id: int, note: str = "") -> str:
    """Close an open order as cancelled (note: why). The standing move it had issued is dropped, so the unit
    stops where it is; a build or fortify already under way is left alone. Usable while it is not my turn."""
    return J(core.game().cancel_order(order_id, note=note))
