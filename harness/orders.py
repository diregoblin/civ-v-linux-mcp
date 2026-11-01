"""Conditional unit orders (#32): a short, model-authored sequence of steps for one unit, run by the harness.

"Move the Worker to (12,8), then build a farm"; "heal to 80%, then walk back to (30,14) and fortify". The model
writes the sequence once; the harness carries out one step after another at the start of each of the seat's
turns (and when the order is given or resumed), and hands control back -- the order paused, with a reason that
says what to do -- the moment anything the order did not plan for happens. Stored in the seat's notebook file
(harness/notes.py) beside the notes and assignments, so an order survives a context reset or a new session.

Everything here is a pure function of the stored order and one runtime read (`H.order_facts`), so it is tested
without a game:

- `normalize_steps` / `normalize_interrupt` turn tool arguments into the stored shape.
- `spec` lists what the active orders need read: their units, the current step's destination or build.
- `decide` looks at one order against the facts and says what happens next: the current step is satisfied, a
  step is to be issued (the `move_unit` / `unit_mission` call and its arguments), the order waits (the unit is
  walking, building, healing, or out of moves), pauses (a reason and what to do), fails (the unit is gone) or
  is complete. Game.run_orders carries it out through the ordinary tool path.

What an order never does: attack (a destination with an enemy on it pauses the order), declare war, end the
turn, or touch anything but its own unit. A refusal, a newly visible hostile within `interrupt.hostile_within`,
damage, low hp, a destination that became illegal or a prerequisite that no longer holds pauses it before
another step is taken; the model resumes (acknowledging what it saw), replaces or cancels it. Each step is
issued at most once per turn, so a step that does not take never loops.
"""
from __future__ import annotations

from typing import Any

from .assignments import AssignmentError, _int, _type, clean_text

MAX_STEPS = 6
MAX_ACTIVE = 30
MAX_CLOSED = 40
PURPOSE_MAX = 300
STEP_KINDS = ("move", "build", "heal", "hold")
HOLD_MISSIONS = {"fortify": "MISSION_FORTIFY", "sleep": "MISSION_SLEEP", "alert": "MISSION_ALERT"}
INTERRUPT_KEYS = ("hostile_within", "hp_below", "damaged")
DEFAULT_INTERRUPT = {"hostile_within": 2, "damaged": True}
OPEN = ("active", "paused")          # statuses that own their unit
#: Pauses that are about the destination, not the unit (GitLab #143): the order has decided the unit cannot act
#: this turn, so the pause skips the unit for the turn (it never blocks the end turn), and the order tries the
#: destination again at the next turn start by itself instead of waiting for a manual resume.
DESTINATION_PAUSES = ("destination", "enemy_on_destination")
RESTING = ("SLEEP_OR_FORTIFY", "HEAL")


class OrderError(AssignmentError):
    """A tool argument that cannot be stored; the message says what to pass instead."""


# ------------------------------------------------------------------ input
def normalize_steps(steps: Any) -> list[dict]:
    """[{kind: move, x, y}, {kind: build, build: FARM}, {kind: heal, hp: 80}, {kind: hold, mission: fortify}].
    A build without x, y builds where the previous move step ends (or where the unit stands when the order is
    given, filled in by the caller). hold ends the order: nothing may follow it."""
    if not isinstance(steps, list) or not steps:
        raise OrderError("steps must be a non-empty list, e.g. [{\"kind\": \"move\", \"x\": 12, \"y\": 8}, "
                         "{\"kind\": \"build\", \"build\": \"FARM\"}]")
    if len(steps) > MAX_STEPS:
        raise OrderError(f"at most {MAX_STEPS} steps per order")
    out: list[dict] = []
    for i, s in enumerate(steps):
        what = f"steps[{i}]"
        if isinstance(s, str):
            s = {"kind": s}
        if not isinstance(s, dict) or s.get("kind") not in STEP_KINDS:
            raise OrderError(f"{what}.kind must be one of {list(STEP_KINDS)}: {{kind: 'move', x, y}}, "
                             "{kind: 'build', build: 'BUILD_FARM'[, x, y]}, {kind: 'heal'}, {kind: 'hold'} -- an order "
                             "never attacks, pillages or founds (give those orders directly), and it is not a batch "
                             "row ({tool, args} is for batch(actions=[...]))")
        kind = s["kind"]
        if out and out[-1]["kind"] == "hold":
            raise OrderError(f"{what}: nothing can follow a hold step (it is where the order ends)")
        if kind == "move":
            if "x" not in s or "y" not in s:
                raise OrderError(f"{what}: a move step needs x and y")
            out.append({"kind": "move", "x": _int(s["x"], f"{what}.x"), "y": _int(s["y"], f"{what}.y")})
        elif kind == "build":
            b = _type(s.get("build"), "BUILD_", f"{what}.build")
            st: dict = {"kind": "build", "build": b}
            if "x" in s or "y" in s:
                st["x"], st["y"] = _int(s.get("x"), f"{what}.x"), _int(s.get("y"), f"{what}.y")
            else:
                prev = next((p for p in reversed(out) if p["kind"] == "move"), None)
                if prev:
                    st["x"], st["y"] = prev["x"], prev["y"]
            out.append(st)
        elif kind == "heal":
            hp = s.get("hp", 100)
            out.append({"kind": "heal", "hp": max(1, min(_int(hp, f"{what}.hp"), 100))})
        else:
            m = str(s.get("mission") or "fortify").strip().lower().removeprefix("mission_")
            if m not in HOLD_MISSIONS:
                raise OrderError(f"{what}.mission must be one of {list(HOLD_MISSIONS)}")
            out.append({"kind": "hold", "mission": m})
    return out


def normalize_interrupt(r: Any) -> dict:
    """Which events pause the order: a visible hostile within `hostile_within` plots of the unit (0 turns it
    off; default 2), the unit's hp below `hp_below` percent (off by default; never during a heal step), and
    `damaged` -- the unit lost hp since the order last looked (default on). A refusal, an enemy on a move
    destination, a destination that became illegal and a prerequisite that no longer holds always pause."""
    if r is None:
        return dict(DEFAULT_INTERRUPT)
    if not isinstance(r, dict):
        raise OrderError(f"interrupt must be an object with any of {list(INTERRUPT_KEYS)}")
    bad = [k for k in r if k not in INTERRUPT_KEYS]
    if bad:
        raise OrderError(f"unknown interrupt key(s) {bad}; use {list(INTERRUPT_KEYS)}")
    out = dict(DEFAULT_INTERRUPT)
    if r.get("hostile_within") is not None:
        out["hostile_within"] = max(0, min(_int(r["hostile_within"], "interrupt.hostile_within"), 6))
    if r.get("hp_below") is not None:
        out["hp_below"] = max(1, min(_int(r["hp_below"], "interrupt.hp_below"), 100))
    if r.get("damaged") is not None:
        if not isinstance(r["damaged"], bool):
            raise OrderError("interrupt.damaged must be true or false")
        out["damaged"] = r["damaged"]
    return out


def clean_purpose(v: Any) -> str:
    return clean_text(v, PURPOSE_MAX, "purpose")


# ------------------------------------------------------------------ the one read
def spec(orders: list[dict]) -> dict:
    """What H.order_facts reads for these orders: each unit as fingerprinted, the current step's destination
    or build, and the widest hostile radius."""
    units, dests, builds = [], [], []
    radius = 0
    for o in orders:
        u = o["unit"]
        units.append({k: u[k] for k in ("id", "type", "created", "x", "y") if u.get(k) is not None})
        radius = max(radius, (o.get("interrupt") or {}).get("hostile_within") or 0)
        st = current(o)
        if st is None:
            continue
        if st["kind"] == "move":
            dests.append({"unit_id": u["id"], "x": st["x"], "y": st["y"]})
        elif st["kind"] == "build" and st.get("x") is not None:
            builds.append({"unit_id": u["id"], "build": st["build"], "x": st["x"], "y": st["y"]})
            dests.append({"unit_id": u["id"], "x": st["x"], "y": st["y"]})   # the walk back when the unit is off the plot
    out: dict = {"units": units}
    if dests:
        out["dests"] = dests
    if builds:
        out["builds"] = builds
    if radius:
        out["radius"] = radius
    return out


def current(o: dict) -> dict | None:
    steps = o.get("steps") or []
    i = o.get("step", 0)
    return steps[i] if 0 <= i < len(steps) else None


def step_label(st: dict | None) -> str:
    if st is None:
        return "done"
    k = st["kind"]
    if k == "move":
        return f"move to ({st['x']},{st['y']})"
    if k == "build":
        where = f" at ({st['x']},{st['y']})" if st.get("x") is not None else ""
        return f"build {st['build'].removeprefix('BUILD_')}{where}"
    if k == "heal":
        return f"heal to {st['hp']}%"
    return f"hold ({st['mission']})"


def hostile_key(h: dict) -> str:
    return f"{h.get('owner_id', h.get('owner'))}:{h.get('id')}"


def _unit(o: dict, facts: dict) -> tuple[dict | None, str | None]:
    """The order's unit as it is now, or why it is gone (a reused id is a different unit)."""
    ref = o["unit"]
    r = (facts.get("units") or {}).get(str(ref["id"])) or {"missing": True}
    label = f"{ref.get('type') or 'unit'} {ref['id']}"
    if r.get("missing"):
        why = (f"{label} is not among my units: killed, captured, disbanded, consumed or upgraded (new id)")
        up = [c for c in r.get("on_last_plot") or [] if c.get("upgrade_of")]
        if up:
            why += (f"; a {up[0].get('type')} ({up[0].get('id')}) stands on its last plot -- give it a new order "
                    f"(notebook(action='give_order', args={{replace_id: {o.get('id')}}}))")
        return None, why
    if (ref.get("type") and r.get("type") != ref.get("type")) or (
            ref.get("created") is not None and r.get("created") is not None and r.get("created") != ref.get("created")):
        return None, (f"{label} is gone: id {ref['id']} now belongs to a {r.get('type')} created turn {r.get('created')}")
    return r, None


def _pct(u: dict) -> int | None:
    hp, mx = u.get("hp"), u.get("max_hp")
    if not isinstance(hp, (int, float)) or not isinstance(mx, (int, float)) or mx <= 0:
        return None
    return int(hp * 100 // mx)


def decide(o: dict, facts: dict, turn: int | None) -> dict:
    """What happens to order `o` now. One of:
    {do: complete} | {do: next} (the current step holds; move on) | {do: fail, reason} |
    {do: pause, kind, reason, hint} | {do: wait, state, note} | {do: issue, tool, args, what}.
    Also carries `seen`: facts worth storing (hp, plot) whatever the decision."""
    st = current(o)
    if st is None:
        return {"do": "complete"}
    u, gone = _unit(o, facts)
    if u is None:
        # A Great Person's improvement (Academy, Customs House, Manufactory, Citadel, Holy Site...) consumes the
        # unit the turn it is built: the build is on the plot and its builder is gone. That is the order done,
        # not failed (Grok, Venice/Mongolia 2026-09-27: "failed" after the build answered ok:true).
        if st["kind"] == "build" and st.get("x") is not None:
            b = (facts.get("builds") or {}).get(f"{o['unit']['id']}:{st['build']}") or {}
            if b.get("done"):
                return {"do": "complete", "note": f"{step_label(st)} is in place and the unit was consumed building it"}
            if b.get("consumes_unit") and o.get("state") == "building":
                # An Archaeologist's dig consumes the unit when it completes and leaves no improvement of the
                # build's own (the choice that follows makes the landmark or takes the artifact): the order was
                # last seen building this very step, and the builder is gone (GitLab #140, live Maya t235).
                return {"do": "complete", "note": f"{step_label(st)} completed and the unit was consumed building it"}
        return {"do": "fail", "kind": "unit_gone", "reason": gone}
    seen = {"hp": u.get("hp"), "x": u.get("x"), "y": u.get("y")}
    base = {"seen": seen}
    last_turn = o.get("updated_turn")
    if isinstance(turn, int) and isinstance(last_turn, int) and turn < last_turn:
        return {**base, "do": "pause", "kind": "turn_went_back",
                "reason": f"the game is at turn {turn} but this order last ran on turn {last_turn}: a save was loaded",
                "hint": "check the unit, then notebook(action='resume_order') (it re-checks every step against the board) or notebook(action='cancel_order')"}
    at = (u.get("x"), u.get("y"))
    satisfied = _satisfied(st, u, facts)
    inflight = o.get("inflight")
    if inflight:
        if satisfied:
            return {**base, "do": "next", "cleared_inflight": True}
        return {**base, "do": "pause", "kind": "uncertain",
                "reason": f"the harness stopped while issuing '{inflight.get('what')}' on turn {inflight.get('turn')} "
                          "and never saw the answer; it is not replayed blind",
                "hint": "look at the unit (state(what='unit', id, view='tactical')), then notebook(action='resume_order') or notebook(action='cancel_order')"}
    if satisfied:
        return {**base, "do": "next"}
    # Interruptions, before any step is issued.
    intr = o.get("interrupt") or {}
    acked = set(o.get("acked") or [])
    new = [h for h in u.get("hostiles") or []
           if (h.get("distance") or 99) <= (intr.get("hostile_within") or 0) and hostile_key(h) not in acked]
    if new:
        h = new[0]
        return {**base, "do": "pause", "kind": "hostile", "hostiles": new,
                "reason": f"a hostile {h.get('unit')} ({h.get('owner')}) is in sight {h.get('distance')} plot(s) away "
                          f"at ({h.get('x')},{h.get('y')})",
                "hint": "decide with state(what='unit', id, view='tactical'); notebook(action='resume_order') carries on (and "
                        "ignores the hostiles seen now), notebook(action='cancel_order') drops the order"}
    pct = _pct(u)
    last_hp = (o.get("seen") or {}).get("hp")
    if intr.get("damaged") and isinstance(last_hp, (int, float)) and isinstance(u.get("hp"), (int, float)) \
            and u["hp"] < last_hp:
        return {**base, "do": "pause", "kind": "damaged",
                "reason": f"the unit lost hp since the order last looked ({last_hp} -> {u['hp']})",
                "hint": "see turn(action='briefing', detail='digest') / state(what='unit', id, view='tactical') for who hit it; notebook(action='resume_order') or replace the order"}
    if intr.get("hp_below") and st["kind"] != "heal" and pct is not None and pct < intr["hp_below"]:
        return {**base, "do": "pause", "kind": "low_hp",
                "reason": f"hp is {pct}%, below the order's {intr['hp_below']}%",
                "hint": "replace the order with a heal step first, or notebook(action='resume_order') to carry on anyway"}
    issued_now = (o.get("issued") or {}).get("turn") == turn and (o.get("issued") or {}).get("step") == o.get("step")
    moves = u.get("moves") or 0
    k = st["kind"]
    if k == "move":
        return _walk(o, u, st["x"], st["y"], facts, turn, base, step_label(st), at, moves, issued_now)
    if k == "build":
        if st.get("x") is None:
            return {**base, "do": "pause", "kind": "prerequisite",
                    "reason": f"the unit is at ({at[0]},{at[1]}), not on its build plot where the build was ordered",
                    "hint": "notebook(action='resume_order') after moving it there, or replace the order with a move step first"}
        if at != (st["x"], st["y"]):
            # Off its build plot (a direct move took it away, or it never got there): walk back, as the move step
            # before it would (live Assyria t53: the Worker was walked into Assur by hand while a Spearman stood two
            # plots from its pasture, and the resume paused it "not on (15,27)" instead of sending it back).
            return _walk(o, u, st["x"], st["y"], facts, turn, base,
                         f"walk to ({st['x']},{st['y']}) for {st['build'].removeprefix('BUILD_')}", at, moves, issued_now)
        b = (facts.get("builds") or {}).get(f"{u['id']}:{st['build']}") or {}
        if b and not b.get("known", True):
            return {**base, "do": "fail", "kind": "unknown_build", "reason": f"{st['build']} is not a build in this game"}
        if u.get("build"):
            same = u["build"] == st["build"]
            return {**base, "do": "wait", "state": "building",
                    "note": f"working on {u['build'].removeprefix('BUILD_')}" + ("" if same else
                            " first (the engine clears the plot for the ordered build; it follows on its own)")}
        if issued_now:
            return {**base, "do": "pause", "kind": "not_started",
                    "reason": f"{st['build']} was issued this turn but the unit is not building it",
                    "hint": "state(what='unit', id, view='actions') lists the builds it can start here"}
        if b.get("can_build") is False:
            return {**base, "do": "pause", "kind": "prerequisite", "reason": build_blocked_reason(b, st["build"], at),
                    "hint": "state(what='unit', id, view='actions') lists what it can build; replace or cancel the order"}
        if moves <= 0:
            return {**base, "do": "wait", "state": "no_moves", "note": "no moves left this turn; the build starts next turn"}
        return {**base, "do": "issue", "tool": "unit_mission",
                "args": {"unit_id": u["id"], "mission": "MISSION_BUILD", "build": st["build"]}, "what": step_label(st)}
    if k == "heal":
        if u.get("activity") in RESTING or issued_now:
            return {**base, "do": "wait", "state": "healing", "note": f"healing: {pct}% of {st['hp']}%"}
        if moves <= 0:
            return {**base, "do": "wait", "state": "no_moves", "note": "no moves left this turn; healing starts next turn"}
        return {**base, "do": "issue", "tool": "unit_mission", "args": {"unit_id": u["id"], "mission": "MISSION_HEAL"},
                "what": step_label(st)}
    # hold
    if moves <= 0 and not issued_now:
        return {**base, "do": "wait", "state": "no_moves", "note": "no moves left this turn; it fortifies next turn"}
    return {**base, "do": "issue", "tool": "unit_mission",
            "args": {"unit_id": u["id"], "mission": HOLD_MISSIONS[st["mission"]]}, "what": step_label(st)}


def build_blocked_reason(b: dict, build: str, at: tuple) -> str:
    """Why the engine refuses this build here, as far as the facts say. `why` names a rule the engine does not
    print: "spent_spread" is a Great Prophet that has used a spread charge, which can no longer build a Holy Site
    (Unit:CanBuild false on every plot while Plot:CanBuild stays true; live Assyria t189-t190, 3 of 4 spreads left)."""
    name = build.removeprefix("BUILD_")
    if b.get("why") == "spent_spread":
        left, mx = b.get("spreads_left"), b.get("spreads_max")
        used = f" ({mx - left} of {mx} spread charges used)" if isinstance(left, int) and isinstance(mx, int) else ""
        return (f"a Great Prophet that has spread its religion can no longer build a {name}{used}: "
                "an engine rule, not this plot; spend its remaining spreads with MISSION_SPREAD_RELIGION instead")
    return (f"the unit cannot start {name} on ({at[0]},{at[1]}) now "
            "(a tech, the terrain, a resource or an improvement already there)")


OWN_UNIT_BLOCK_TURNS = 2   # a destination one of my own units holds is waited out this many turns before the order pauses


def _walk(o: dict, u: dict, x: int, y: int, facts: dict, turn, base: dict, what: str, at: tuple, moves, issued_now: bool) -> dict:
    """The decision for getting the unit to (x, y): a move step, or a build step whose unit stands elsewhere."""
    d = (facts.get("dests") or {}).get(f"{u['id']}:{x},{y}") or {}
    if d.get("enemy"):
        return {**base, "do": "pause", "kind": "enemy_on_destination",
                "reason": f"an enemy stands on ({x},{y}); an order never attacks",
                "hint": "attack it yourself with order(to='unit', action='move'), or replace the order with another destination"}
    if d.get("refusal"):
        why = str(d["refusal"])
        if "one of your" in why:
            # My own unit on the plot is a passing thing more often than not (live Assyria t55: the Settler walking
            # north stood on the Worker's pasture plot for one turn, and the order paused with "replace the order").
            # Wait it out; a unit of mine that stays there pauses the order after OWN_UNIT_BLOCK_TURNS turns.
            since = (o.get("blocked") or {})
            first = since.get("turn") if (since.get("x"), since.get("y")) == (x, y) and isinstance(since.get("turn"), int) else turn
            if isinstance(turn, int) and isinstance(first, int) and turn - first >= OWN_UNIT_BLOCK_TURNS:
                return {**base, "do": "pause", "kind": "destination",
                        "reason": f"a move to ({x},{y}) would be refused now: {why} (one of mine has stood there since turn {first})",
                        "hint": "move that unit off the plot and notebook(action='resume_order'), or replace the order with another plot"}
            return {**base, "do": "wait", "state": "blocked", "blocked": {"x": x, "y": y, "turn": first},
                    "note": f"({x},{y}) holds one of my own units this turn; the order tries again next turn"}
        return {**base, "do": "pause", "kind": "destination",
                "reason": f"a move to ({x},{y}) would be refused now: {why}",
                "hint": "replace the order with a reachable plot (state(what='unit', id, view='tactical') shows what a move allows)"}
    if issued_now:
        return {**base, "do": "wait", "state": "moving" if moves <= 0 or u.get("going_to") else "stopped",
                "note": "on its way: the move goes on at the start of my next turn" if moves <= 0 or u.get("going_to")
                else "the move was issued this turn and the unit stopped short; the order tries again next turn"}
    prev = o.get("issued") or {}
    if prev.get("step") == o.get("step") and (prev.get("x"), prev.get("y")) == at and prev.get("turn") != turn:
        return {**base, "do": "pause", "kind": "no_progress",
                "reason": f"no progress toward ({x},{y}) since turn {prev.get('turn')}: the engine finds no path",
                "hint": "pick another plot (replace the order) or clear what blocks it"}
    if moves <= 0:
        return {**base, "do": "wait", "state": "no_moves", "note": "no moves left this turn; the move starts next turn"}
    return {**base, "do": "issue", "tool": "move_unit", "args": {"unit_id": u["id"], "x": x, "y": y}, "what": what}


def _satisfied(st: dict, u: dict, facts: dict) -> bool:
    k = st["kind"]
    if k == "move":
        return (u.get("x"), u.get("y")) == (st["x"], st["y"])
    if k == "build":
        b = (facts.get("builds") or {}).get(f"{u['id']}:{st['build']}") or {}
        return bool(b.get("done"))
    if k == "heal":
        pct = _pct(u)
        return pct is not None and pct >= st["hp"]
    return False    # a hold step is done when its mission is accepted (Game records that)


# ------------------------------------------------------------------ output
def retries_at_turn_start(o: dict) -> bool:
    """Whether a paused order tries again by itself at the turn start (a destination pause, #143)."""
    return o.get("status") == "paused" and (o.get("pause") or {}).get("kind") in DESTINATION_PAUSES


def row(o: dict) -> dict:
    """An order as orders() and the briefing show it."""
    st = current(o)
    out = {"id": o.get("id"), "unit": {k: o["unit"].get(k) for k in ("id", "type")}, "status": o.get("status"),
           "step": (o.get("step", 0) + 1) if st else len(o.get("steps") or []),
           "of": len(o.get("steps") or []), "now": step_label(st),
           "steps": [step_label(s) for s in o.get("steps") or []]}
    for k in ("state", "note", "purpose", "pause", "last", "issued_count", "created_turn", "closed_turn", "replaced_by"):
        if o.get(k) not in (None, "", []):
            out[k] = o[k]
    return out


def counts(rows: list[dict]) -> dict:
    """The counts over the rows an `orders` block returns, read from each row's status as it stands after the run:
    `open` the active and paused ones, `closed` the rest (completed, failed, cancelled, replaced: shown once, as
    what happened; only when there are any), `paused` the open ones waiting on an answer. GitLab #113 (Maya t150)
    and #181 (hotseat Maya t26: the finish counted before running, so the order that completed in that very run
    still read `open: 1`)."""
    out = {"open": sum(1 for r in rows if r.get("status") in OPEN),
           "closed": sum(1 for r in rows if r.get("status") not in OPEN),
           "paused": sum(1 for r in rows if r.get("status") == "paused")}
    if not out["closed"]:
        del out["closed"]
    return out


def briefing_section(orders: list[dict], limit: int) -> dict:
    """The briefing's `orders`: paused ones first (they want an answer), then active."""
    rows = sorted((row(o) for o in orders), key=lambda r: (r.get("status") != "paused", r.get("id") or 0))
    out = {**counts(rows),
           "rows": [{k: r[k] for k in ("id", "unit", "status", "now", "state", "pause") if k in r} for r in rows[:max(1, limit)]]}
    if len(rows) > limit:
        out["more"] = len(rows) - limit
        out["hint"] = "notebook(action='orders') lists every one"
    return out
