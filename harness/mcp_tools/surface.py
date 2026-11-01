"""The nine tools of milestone 2.0.0 (GitLab #48, stage 2a): the game as a clock, a world of objects, the
questions it asks, my notebook and the session.

One of the civ5 MCP server's tool modules (registered last by harness/mcp_server.py). Each tool routes its
call through `harness.surface.dispatch` onto the old handler and runs it with the server's own runner (by the
handler's exact name, so no `renamed` rides on it), so the old guard, ledger row and reply are exactly what
they were: `state(what="screen", view="league")` returns
`league_status()` byte for byte. `reference(book, section)` is the old `reference` tool grown a `book`
(harness/mcp_tools/reference.py). The 145 old handlers are registered and retired at once (`@retired`, #52): the
listing is these nine, and an old name answers through the retirement map with `renamed` on its reply.
"""
from __future__ import annotations

import json
from typing import Annotated, Any

from mcp.types import ToolAnnotations
from pydantic import Field

from harness.mcp_server import Context

from harness import briefing as B
from harness import gate as G
from harness import mcp_server as core
from harness.client import TunerdError
from harness.mcp_server import J, _remember_result, _replayed, _run_tool_here, mcp
from harness.mcp_tools.batch import run_batch
from harness.surface import dispatch as D
from harness.surface import listing as L
from harness.surface import vocabulary as V


def _run(target: D.Call | D.Composite | D.Refusal, action_id: str | None = None, ctx: Context | None = None) -> str:
    """Run what dispatch resolved: a refusal as is, a composite part by part, a call through the runner (with
    the replay of a retried action_id, as a batch row has it)."""
    if isinstance(target, D.Refusal):
        return J(target.reply())
    if isinstance(target, D.Composite):
        parts = {}
        for key, call in target.parts.items():
            try:
                parts[key] = json.loads(_run_tool_here(call.tool, call.args, renamed=False))
            except ValueError:
                parts[key] = {"ok": False, "err": "not JSON"}
        return J(D.merge_parts(parts, target.all_units))
    r = _replayed(target.tool, action_id) if action_id else None
    if r is None:
        r = _run_tool_here(target.tool, target.args, ctx=ctx, renamed=False)
        if action_id:
            _remember_result(target.tool, action_id, r)
    return r


def _given(**kw: Any) -> dict:
    """The arguments actually passed: empty strings and None are "not given"."""
    out = {}
    for k, v in kw.items():
        if k == "args" and isinstance(v, dict):
            out.update({kk: vv for kk, vv in v.items() if vv is not None})
        elif v is not None and v != "":
            out[k] = v
    return out


def _gate_now() -> tuple[dict, dict | None]:
    """The live turn state and its gate (what `question` shows and `answer` dispatches on)."""
    g = core.game()
    with core.action_lock(core._sock(), seat=g.seat, tool="question"):
        ts = g.turn_state()
    return ts, core._gate(ts, g.seat)


# --- turn ---------------------------------------------------------------------------------------------
def _f(description: str):
    """A parameter's `description` in the listed schema (TDQS and the clients read it)."""
    return Field(description=description)


def turn(action: Annotated[str, _f("status | briefing | finish | end | wait")],
         actions: Annotated[list[dict] | None, _f("finish only: order rows to run before the turn ends, [{tool, args}] as the reads hand them back")] = None,
         since: Annotated[str, _f("briefing: 'previous' (default) compares with my last briefing, 'turn' with the last turn end (after a context reset)")] = "",
         limit: Annotated[int | None, _f("briefing: rows per list of changes and notes (default 8)")] = None,
         detail: Annotated[str, _f("briefing: 'compact' (default) or 'digest' (the event digest alone)")] = "",
         notes: Annotated[str, _f("finish: which notebook notes ride on the reply, 'new' (default) or 'all'")] = "",
         timeout_seconds: Annotated[int | None, _f("finish / wait: seconds to wait for my turn before answering with the state so far (default 600)")] = None,
         args: Annotated[dict | None, _f("finish / end only, by name: skip_quiet_turns (a count: keep ending turns, up to N more, while nothing needs you), wake_on (words that stop a quiet run), autosave (default true), force (take the turn over from another client of my seat), briefing (finish: the new turn as a briefing)")] = None,
         ctx: Context = None) -> str:
    return _run(D.resolve("turn", {"action": action},
                          _given(actions=actions, since=since, limit=limit, detail=detail, notes=notes,
                                 timeout_seconds=timeout_seconds, args=args)), ctx=ctx)


turn.__doc__ = (
    "The clock: my seat's turn loop, one action per call.\n"
    "Actions:\n"
    "  status -- whose turn it is, the `gate` (answer it before anything else), what blocks the end. Read-only.\n"
    "  briefing -- my turn in one read: decisions with their `actions` rows, changes, board, threats, notes.\n"
    "  finish -- run `actions` as a batch, end my turn, wait until it is mine again, return the new turn.\n"
    "  end -- end the turn only, no wait.\n"
    "  wait -- block until it is my turn again.\n"
    "Arguments by action: since, limit and detail belong to briefing (since='turn' after a context reset; "
    "detail='digest' is the event digest alone); actions and notes to finish; timeout_seconds to finish and wait; "
    "`args` (skip_quiet_turns, wake_on, autosave, force, briefing) to finish and end.\n"
    "Side effects: finish and end hand the game to the other players, and nothing they do can be undone -- order and "
    "answer everything first; a session save is the way back. finish autosaves to the quick-save slot. A refused row in "
    "`actions` stops the batch and the turn is not ended. Safe to repeat: when it is not my turn, finish only waits. A "
    "second client of my seat is refused with `turn_claim` (args.force takes the turn over).\n"
    "Timeouts: past timeout_seconds (600 by default) the reply says my_turn false, timed_out true and `next` is the call that "
    "resumes the wait; progress notifications go out every 5 s meanwhile, so one long call beats several short ones.\n"
    "Not this tool: question / answer for what the game asks (nothing ends while `gate` is set); state for the board; "
    "batch for orders that leave the turn open; session for saves.\n"
    "Returns: turn, my_turn, `gate`, todo / decisions, digest (what happened meanwhile), notes; game_over with victory / "
    "defeat at the end. A refusal is {ok: false, err, end_turn: {todo, skip_actions}}: what blocks the turn and the rows "
    "that clear it."
)

# --- state --------------------------------------------------------------------------------------------
def state(what: Annotated[str, _f("the object: " + ", ".join(V.VIEWS))],
            id: Annotated[int | list[int] | None, _f("the one object's id (unit, city, civ, city-state or spy; the explorer's unit id for map/frontier and the caravan's for options/trade_routes); a list of unit ids for units/actions")] = None,
            view: Annotated[str, _f("the part of the object, from the list below; the default view when left out")] = "",
            x: Annotated[int | None, _f("map/window and map/grid: the centre plot, with y")] = None,
            y: Annotated[int | None, _f("with x")] = None,
            radius: Annotated[int | None, _f("map/window and map/grid: tiles around x, y; unit/tactical: tiles around the unit")] = None,
            mission: Annotated[str, _f("unit/targets: the mission whose legal targets to list")] = "",
            kind: Annotated[str, _f("options/beliefs: the belief kind; compare: what to compare")] = "",
            detail: Annotated[str, _f("'summary' or 'full' where a view offers both")] = "",
            since: Annotated[str | int | None, _f("notifications: only those after this turn number")] = "",
            limit: Annotated[int | None, _f("how many rows a list returns")] = None,
            item: Annotated[str, _f("city/production: price this one item")] = "",
            yield_type: Annotated[str, _f("city/production with item: the yield to price it in")] = "",
            args: Annotated[dict | None, _f("the rest by the old call's name (compare's fields)")] = None) -> str:
    return _run(D.resolve("state", {"what": what, "view": view},
                          _given(id=id, x=x, y=y, radius=radius, mission=mission, kind=kind, detail=detail,
                                 since=since, limit=limit, item=item, yield_type=yield_type, args=args)))


state.__doc__ = (
    "Read the game as my seat sees it: the empire, units, cities, civs and city-states, the map, the league, spies, the "
    "screens, and the choices open to me (research, policies, beliefs, trade routes). Read-only, no side effect, usable "
    "while it is not my turn. Use it before an order (its rows ARE the orders) and after one to verify; use reference for "
    "what things do, question for what a popup asks, turn for the turn's own state.\n"
    "How to call: `what` names the object, `view` the part of it (left out: the default view), `id` the one object. "
    "Objects and their views:\n"
    + "\n".join(f"  {what}: {', '.join(views)}" for what, views in V.VIEWS.items())
    + "\nSelectors, by view: x, y, radius for map/window and map/grid; radius alone for unit/tactical (centred on the "
    "unit); id for map/frontier (the explorer) and options/trade_routes (the caravan); mission for unit/targets; kind for "
    "options/beliefs and compare; detail ('summary' / 'full') where a view has both; since and limit for lists; item "
    "and yield_type for city/production to price one item; `args` for the rest by the old call's name.\n"
    "Returns: the object as JSON (a list for units, cities, civs; one dict otherwise), with `actions` or `call` rows "
    "wherever something can be done: each row is a complete order() call to copy. A wrong `what` or `view` is refused "
    "with `choices`, and for an object that takes an id, a `hint` saying where the ids come from (unit ids from units, "
    "city-state ids from the `minor: true` rows of civs). Replies are the 1.x reads' replies unchanged."
)

# --- order ---------------------------------------------------------------------------------------------
def order(to: Annotated[str, _f("the target kind, something I own")],
          action: Annotated[str, _f("the verb; its words depend on `to`")],
          id: Annotated[int | None, _f("which unit, city, civ, city-state or spy; empire and league take none")] = None,
          args: Annotated[dict | None, _f("the action's arguments by name, as the copied row has them; a refusal shows the shape with an example")] = None,
          action_id: Annotated[str | None, _f("a token of my choosing: a retry with the same action_id replays the stored result instead of acting twice")] = None) -> str:
    return _run(D.resolve("order", {"to": to, "action": action}, _given(id=id, args=args)), action_id=action_id)


order.__doc__ = (
    "An order to something I own: `to` the target kind, `id` which one, `action` the verb, `args` its arguments by name. "
    "It changes the game, and most of it cannot be undone (a disbanded unit, a declared war, a purchase). Not a read: "
    "state shows the board and hands back the rows, question / answer settle what a popup asks, turn(action='finish') "
    "ends the turn. to: actions --\n"
    + "\n".join(f"  {to}: {', '.join(a for a in acts if a != V.SCREEN_BUTTON)}"
                + (f" (or a city-state screen button by its name: {', '.join(V.SCREEN_BUTTONS)})"
                   if V.SCREEN_BUTTON in acts else "")
                for to, acts in V.ACTIONS.items())
    + "\nHow: copy the rows a read hands back (`actions`, `call`) as they are; `id` is a unit, city, civ, city-state or spy "
    "id (empire and league take none); `args` holds what the row holds (a plot's x and y, an item's name, a deal's items, "
    "an amount). An order runs whole or not at all. `action_id`: a token of mine; a retry with the same one replays the "
    "stored reply instead of acting twice.\n"
    "Returns {ok: true, ...} with what changed (a unit's new plot and moves left, a city's queue, a deal's answer), or "
    "{ok: false, err, choices / accepts, example}: the verb is not one of the target's (choices lists them), an argument "
    "is missing (accepts names the shape, example a complete call), or the game refuses it (err names the rule, e.g. the "
    "unit has no moves, the city is not mine, another client of my seat holds this turn's claim). Nothing is acted on "
    "when ok is false."
)

# --- question / answer -----------------------------------------------------------------------------------
def question() -> str:
    ts, gate = _gate_now()
    asked = G.screenless_question(ts) if gate is None else None
    read = D.question_read(gate, asked)
    if read is not None:
        try:
            reply = json.loads(_run_tool_here(read.tool, read.args, renamed=False))
        except ValueError:
            reply = {"ok": False, "err": "not JSON"}
        if isinstance(reply, dict):
            reply["gate"] = gate
            if asked in G.BLOCKER_QUESTIONS:
                # The engine raised the blocker without its popup (#95): the question is pending all the same,
                # and `answers` rows are answer(choice=...) calls that dispatch on the blocker.
                reply["pending"] = True
                reply["blocker"] = asked
            elif asked == G.PENDING_DEAL:
                # Another human's proposal (#161): no screen, no blocker, the table read above is the question.
                reply["pending"] = True
                reply.setdefault("from", G.pending_deal_from(ts))
            return J(reply)
        return J({"ok": True, "question": reply, "gate": gate})
    if gate is not None:
        return J({"ok": True, "pending": True, "gate": gate})
    todo = ts.get("todo") if isinstance(ts.get("todo"), dict) else {}
    if todo.get("religion") in ("found", "enhance"):
        # GitLab #103 (Maya t71): after MISSION_FOUND_RELIGION, question() said "nothing is asked". The choice is an
        # order, not an answer: show it with its rows and the beliefs on offer.
        popup = "BUTTONPOPUP_ENHANCE_RELIGION" if todo["religion"] == "enhance" else "BUTTONPOPUP_FOUND_RELIGION"
        kinds = ("follower", "enhancer") if todo["religion"] == "enhance" else ("founder", "follower")
        reply: dict = {"ok": True, "pending": True, "decision": "religion", "choice": todo["religion"], "gate": None,
                       "actions": G.popup_rows(popup),
                       "note": "a religion to " + todo["religion"] + ": an order, not an answer -- the rows above read the beliefs on offer "
                               "and give the order; `beliefs` here are the same reads, taken now"}
        reply["beliefs"] = {}
        for kind in kinds:
            try:
                read = json.loads(_run_tool_here("available_beliefs", {"kind": kind}, renamed=False))
            except ValueError:
                continue
            if isinstance(read, dict):    # the read's religion-order rows (#178) are the decision's `actions` above
                read.pop("actions", None)
                read.pop("call_note", None)
            reply["beliefs"][kind] = read
        return J(reply)
    return J({"ok": True, "pending": False, "decisions": B.decisions(ts, None),
              "note": "nothing is asked; the decisions are the turn's todo (turn(action='briefing') has them in full)"})


question.__doc__ = (
    "What the game is asking right now, so answer() can settle it. Read-only; takes nothing. Use it whenever a reply's "
    "`gate` is not null or turn(action='status') says discussion_pending; use state for the board and reference for the "
    "rules. It shows one of: a decision popup (a tech, a production item, a policy, a promotion, a belief, a ruins reward, "
    "a captured city's fate, a Great Person's use, a dig), the leader on screen with their words and the deal on the "
    "table, another human seat's proposal waiting on the trade table, or nothing pending.\n"
    "Returns the popup's own read -- the question in words plus `answers` rows, each a complete answer() call to copy "
    "(the item's name or button number, and the args the popup needs) -- with `gate` on the reply; a leader screen "
    "returns the leader, the speech, the buttons and the deal's items; when nothing is asked, {pending: false, "
    "decisions: [...]} lists the turn's open decisions instead. Several leaders can queue at a turn start: answering one "
    "returns the next under `next`."
)


def answer(choice: Annotated[str | int, _f("the `answers` row's choice: an item name, a button number, or accept / refuse / leave / accept_friendship")],
           args: Annotated[dict | None, _f("what the popup needs beyond the choice: unit_id, x and y, player_id, beliefs, city")] = None,
           action_id: Annotated[str | None, _f("a token of my choosing: a retry with the same action_id replays the stored result")] = None) -> str:
    gate = blocker = None
    ts: dict = {}
    if not (isinstance(choice, str) and choice in D.fixed_answers()):
        ts, gate = _gate_now()
        blocker = G.screenless_question(ts) if gate is None else None
    out = _run(D.resolve("answer", {"choice": choice}, _given(args=args), gate, blocker), action_id=action_id)
    if (gate or {}).get("name") in ("discussion", "leader_screen") or (isinstance(choice, str) and choice in D.fixed_answers()):
        # A leader answered during the AI round (GitLab #111): say which call resumes the wait and brings the digest,
        # so the agent does not read the bare status and lose the turn's events.
        try:
            reply = json.loads(out)
        except ValueError:
            return out
        if isinstance(reply, dict) and reply.get("ok") is not False and "next" not in reply and _ais_moving_after(reply):
            reply["next"] = ("the AIs are still moving: turn(action='wait') or turn(action='finish') resumes the wait and "
                             "hands the new turn back with its digest (finish ends nothing when it is not your turn)")
            out = J(reply)
    return out


def _ais_moving_after(reply: dict) -> bool:
    """Whether the AI round is still running once the leader screen is answered: a fresh read, never the state
    taken before the answer (GitLab #155, hotseat t7: a first-meeting greeting freezes my_turn to false while it
    is up, so the pre-answer state read as "the AIs are moving" on the seat's own open turn and the wait it was
    sent to returned at once). Another leader queued behind this one (`still_pending`) is not the round either."""
    if reply.get("still_pending"):
        return False
    g = core.game()
    try:
        with core._op(g):
            st = g.turn_state()
    except (TunerdError, OSError, ValueError, KeyError):
        return False
    if st.get("leader_greeting_pending") or st.get("discussion_pending"):
        return False
    return bool(not st.get("my_turn") or st.get("active_player") != g.seat)


answer.__doc__ = (
    "Answer what the game is asking: settle the one popup, leader screen or deal that question() shows, and nothing "
    "else. `choice` is the `answers` row's choice: an item's name (a TECH_, UNIT_, BUILDING_, POLICY_, PROMOTION_, "
    "BELIEF_ or goody name; liberate / annex / puppet / raze; a dig's choice number), a popup's or leader screen's button "
    "number, or on a leader screen accept / refuse (the deal on the table), leave (close it), accept_friendship. `args` "
    "carries the rest the popup needs (a promotion's unit_id, a dig's x and y, a stolen tech's player_id, a religion's "
    "beliefs and city). Dispatches on the gate: question() shows which question is up and hands back the rows to copy. "
    "It acts on the game as the popup's own button would -- an accepted deal, a razed city, a chosen tech cannot be "
    "taken back; a choice the popup does not offer, or an answer when nothing is asked, is refused with {ok: false, err, "
    "choices} and nothing happens. action_id: a retry with the same token replays the stored reply instead of answering "
    "twice. Not this tool: a decision with no popup up (research, production, a policy) is order; what a choice means is "
    "reference. Returns {ok, ...} with the popup's outcome and the gate that follows (still_pending and `next` when "
    "another leader waits; `next` also names the call that resumes the AIs' round when they are still moving), or the "
    "refusal."
)

# --- notebook / session / batch ------------------------------------------------------------------------
def notebook(action: Annotated[str, _f(" | ".join(V.NOTEBOOK_ACTIONS))],
             args: Annotated[dict | None, _f("the action's arguments by name: text / tag / replace_id, note_id, role and purpose with unit_ids / city_ids, assignment_id, unit_id and steps, order_id")] = None,
             action_id: Annotated[str | None, _f("a token of my choosing: a retry with the same action_id replays the stored result")] = None) -> str:
    return _run(D.resolve("notebook", {"action": action}, _given(args=args)), action_id=action_id)


notebook.__doc__ = (
    "My memory, kept beside the game per seat and surviving a context reset or a restart: free-text notes, assignments "
    "(what a unit or city is for) and standing orders (a unit's plan the harness carries out over the coming turns). Use "
    "it for what future-me must know; the game itself holds no plan. Notes and assignments move nothing; a standing "
    "order does: give_order and resume_order run its first steps NOW (a move spends this turn's movement, a build "
    "starts) and carry on at the start of each of my turns. action, with its args --\n"
    "  remember {text, tag?, replace_id?}: write a note (returns it with its id; new notes ride on the next briefing / "
    "finish); recall {tag?, limit?}: list notes; forget {note_id}: delete a note for good.\n"
    "  assign {role, purpose, unit_ids? / city_ids?}: give units or cities a purpose that shows in their state rows; "
    "assignments: list them; amend {assignment_id, purpose? / role?}; close {assignment_id}.\n"
    "  give_order {unit_id, steps, interrupt?, purpose?, replace_id?}: steps is a list of at most 6, in order -- "
    "{kind: 'move', x, y}, {kind: 'build', build: 'FARM'}, {kind: 'heal', hp: 80}, {kind: 'hold', mission: 'fortify' | "
    "'sleep' | 'alert'} (last) -- each step runs at most once per turn and the next starts as soon as one completes "
    "(a move that arrives starts its build the same turn); it never attacks, declares war or ends the turn, and pauses "
    "with a reason when a hostile comes near, the unit is hurt or a step is refused; one open order per unit "
    "(replace_id replaces it). orders: the plans with their status; cancel_order / resume_order {order_id}.\n"
    "Not this tool: a one-off move is order(to='unit'); a popup is answer; the board is state. Usable while it is not my "
    "turn. Returns {ok: true, ...} with the row written or the rows listed, or {ok: false, err, accepts, example} (an "
    "unknown action or a missing argument; nothing is written). A note written on a turn later than the one on screen "
    "(a save was loaded) comes back marked later_timeline."
)


def session(action: Annotated[str, _f(" | ".join(V.SESSION_ACTIONS))],
            args: Annotated[dict | None, _f("load: {filename} (a save's name without the single/ prefix); seat: {seat} (0 or 1)")] = None) -> str:
    return _run(D.resolve("session", {"action": action}, _given(args=args)))


session.__doc__ = (
    "Saves, loads and the seat of this game session: keep a state before a risky turn, open another save, leave a "
    "finished game, say which hotseat seat this server plays. It never plays a turn; use turn for that. Side effects: "
    "a load replaces the game on screen for everyone on it, and a hotseat game loads paused until turn(action='wait'); "
    "the notebook is per game and seat, so it follows a save of the same game and is not touched by a load. "
    "action -- save: a quick save of the game on screen into the one quick-save slot (each finished turn's autosave "
    "overwrites that slot, so copy a save you want kept); load {filename}: open that save (a name as the game lists it, "
    "without the single/ prefix; the refusal lists the legal ones), replacing the unsaved state, so save first; "
    "load_latest: open the newest save, whichever game it is; main_menu: leave the game for the main menu (the "
    "game_over gate's way out); seat {seat}: which human seat (0 or 1) this server plays in a hotseat game -- a server "
    "pinned with --seat refuses a change onto the other human seat, and never move onto the seat on screen.\n"
    "Returns {ok: true, saved / loaded, turn, seat, screen} or {ok: false, err} naming why (an unknown filename with the "
    "list, a seat that is someone else's, a game operation already running). In a game with other people ask the human "
    "before loading."
)


def batch(actions: Annotated[list[dict], _f("the rows to run in order, [{tool, args}], as every read hands them back")],
          stop_on_refusal: Annotated[bool, _f("stop at the first refused row (default true); false runs them all")] = True,
          force: Annotated[bool, _f("take over this turn's claim when another client of my seat holds it (default false: the first row is then refused with turn_claim)")] = False) -> str:
    return J(run_batch(actions, stop_on_refusal=stop_on_refusal, force=force))


batch.__doc__ = (
    "Many orders in one call, in order, with the turn left open: actions is a list of {tool, args} rows -- the rows "
    "every read hands back (`actions`, `call`): order, answer and notebook rows alike -- each run as that call and "
    "answered under `results`. The first refusal stops the rest by default, since the state the later rows were "
    "reasoned about is no longer certain (stop_on_refusal=false runs them all); the rows not run come back under "
    "`skipped`. force=true takes over this turn's claim when another client of my seat holds it (otherwise the first "
    "row is refused with `turn_claim`). Not inside: the turn's wait / finish / end, a load, the seat, the exit, a batch. "
    "Each row changes the game as its order would and cannot be undone; a row's own action_id replays. Use it for "
    "several orders already decided; use order for one, and turn(action='finish', actions=[...]) when the same rows "
    "should end the turn afterwards. Returns {ok, done, results: [one reply per row], skipped?, hint?}: ok is false "
    "when any row was refused."
)


def _safe(fn):
    """A harness bug comes back as a readable JSON error, as `guarded` does for the old tools (the nine run the
    old handlers through the runner, which guards them; this covers the routing itself)."""
    import functools

    @functools.wraps(fn)
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except Exception as e:
            return J({"ok": False, "err": f"harness error: {type(e).__name__}: {e}", "tool": fn.__name__})
    return wrapper


#: What each tool does to the world, as MCP annotations on the listing (TDQS lint, 2026-10-27): the reads are
#: read-only and idempotent; an order, a batch, a load and a forgotten note cannot be taken back; nothing here
#: reaches beyond the game on this machine.
ANNOTATIONS: dict[str, ToolAnnotations] = {
    "turn": ToolAnnotations(title="The clock", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
    "state": ToolAnnotations(title="Read the world", readOnlyHint=True, idempotentHint=True, openWorldHint=False),
    "order": ToolAnnotations(title="Order what I own", readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False),
    "question": ToolAnnotations(title="What the game asks", readOnlyHint=True, idempotentHint=True, openWorldHint=False),
    "answer": ToolAnnotations(title="Answer the game", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
    "notebook": ToolAnnotations(title="My notebook", readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False),
    "batch": ToolAnnotations(title="Many orders", readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False),
    "session": ToolAnnotations(title="Saves, loads, the seat", readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False),
    "reference": ToolAnnotations(title="The rule book and the playbook", readOnlyHint=True, idempotentHint=True, openWorldHint=False),
}

for _name in V.TOOLS:
    if _name != "reference":          # the old `reference` tool, grown a `book`, is the ninth (mcp_tools/reference.py)
        mcp.tool(annotations=ANNOTATIONS[_name])(_safe(globals()[_name]))
del _name


# --- the listing (#49): order's schema, one shape for every client -----------------------------------------
_order_tool = mcp._tool_manager.get_tool("order")
_order_tool.parameters = L.order_schema(_order_tool.parameters)   # `to` its enum, `action` the verbs by target
del _order_tool
