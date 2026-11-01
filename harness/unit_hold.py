"""What a hold order left the unit doing, in words (GitLab #176).

The engine has one activity for sleep and fortify (ACTIVITY_SLEEP); a fortify is that activity plus a count
(`GetFortifyTurns`) that grows by one at each of the unit's turn starts, up to MAX_FORTIFY_TURNS, worth
FORTIFY_MODIFIER_PER_TURN percent each (BNW: 2 turns of 20%). A unit that moved this turn starts its count at the
next turn start. No hold spends moves, and a unit in any hold is not IsReadyToMove, which is the end-turn list
(`todo.units`) -- so "SLEEP_OR_FORTIFY, moves 1" read like an order that had not taken (Celts t7). `describe` turns
the read-back's `hold` facts (H.unit_hold_state) into the reply's `hold` block: what the unit is doing now, the
bonus now and when it is full, whether the end-turn list still names it, and what its moves left mean.
"""
from __future__ import annotations

#: The orders whose reply carries the `hold` block: the holds, a skip, and the command that ends a hold.
HOLD_ORDERS = frozenset({"MISSION_FORTIFY", "MISSION_SLEEP", "MISSION_ALERT", "MISSION_SKIP", "MISSION_HEAL",
                         "MISSION_GARRISON", "COMMAND_WAKE"})


def _turns(n: int) -> str:
    return f"{n} turn" + ("" if n == 1 else "s")


def _fortify(facts: dict) -> tuple[str, str, dict]:
    """(state, summary, extra keys) of a unit asleep that can fortify: fortified now, or fortifying from next turn."""
    turns = facts.get("fortify_turns") or 0
    mx = facts.get("fortify_max") if isinstance(facts.get("fortify_max"), int) else None
    pct = facts.get("fortify_pct") if isinstance(facts.get("fortify_pct"), int) else None
    full = f" (+{pct * mx}%)" if pct and mx else ""
    if turns > 0:
        now = f" (+{pct * turns}% defence)" if pct else ""
        left = (mx - turns) if mx else 0
        rest = (f"; full strength{full} in {_turns(left)}" if left > 0 else "; at full strength")
        return "fortified", f"fortified{now}{rest}", {"fortified": True, "fortify_turns": turns}
    start = f" (+{pct}%)" if pct else ""
    full_in = f", full strength{full} in {_turns(mx)}" if mx else ""
    return ("fortifying",
            f"fortifying: not fortified yet; the bonus starts at its next turn start{start}{full_in} "
            "(a unit that moved this turn starts counting next turn)",
            {"fortified": False, "fortify_turns": 0, **({"full_in": mx} if mx else {})})


def describe(mission: str, after: dict | None) -> dict | None:
    """The reply's `hold` block for `mission` from its unit_pos read-back (`hold` facts, `moves`); None when the order
    is not a hold or the runtime gave no facts (an older runtime)."""
    facts = after.get("hold") if isinstance(after, dict) else None
    if mission not in HOLD_ORDERS or not isinstance(facts, dict) or not facts.get("activity"):
        return None
    activity = str(facts["activity"])
    out: dict = {"activity": activity}
    if activity == "SLEEP" and facts.get("fortifyable"):
        state, summary, extra = _fortify(facts)
        out.update(extra)
    elif activity == "SLEEP":
        state, summary = "asleep", "asleep: no defence bonus (this unit cannot fortify)"
    elif activity == "SENTRY":
        state, summary = "alert", "on alert: it wakes when an enemy comes into sight"
    elif activity == "HEAL":
        state, summary = "healing", "healing: it rests here until healed"
    elif activity == "HOLD":
        state, summary = "skipping", "skipping this turn only: it is back on the end-turn list next turn"
    elif activity == "AWAKE":
        state, summary = "awake", "awake: it waits for an order"
    else:
        state, summary = activity.lower(), activity.lower()
    out["state"] = state
    needs = facts.get("needs_orders")
    if isinstance(needs, bool):
        out["needs_orders"] = needs
        summary += ("; the end-turn list still names it (todo.units)" if needs
                    else "; off the end-turn list, it does not hold up the finish")
        if not needs and state not in ("skipping", "awake"):
            summary += "; it stays so until woken (COMMAND_WAKE) or given another order"
    out["summary"] = summary
    moves = after.get("moves")
    if isinstance(moves, (int, float)) and moves > 0 and state != "awake":
        lost = " (and the fortify starts over)" if state in ("fortified", "fortifying") else ""
        out["moves"] = (f"{moves:g} move{'s' if moves != 1 else ''} left: a hold spends none; they stay usable this "
                        f"turn, and a move or attack takes the unit out of the hold{lost}")
    return out
