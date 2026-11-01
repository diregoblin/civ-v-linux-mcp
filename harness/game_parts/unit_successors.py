"""A unit my own order saw the engine replace under a new id (GitLab #169).

Live Maya t5: a Scout's move onto adjacent Ancient Ruins answered `{"ok": false, "err": "no such unit"}` -- the ruins
had made it a Mayan Atlatlist with a new id on the ruins plot, and the move's read-back found the old id gone. The
move had happened; a caller that believed the refusal retried it into a second "no such unit". Here the read-back
that finds the mover gone asks the runtime for the unit that replaced it (successors.lua: one of my units created
this turn, of a type the old one upgrades or ruins-upgrades to, on the destination or within reach), and the reply
is the move's success with `successor`; the notebook's assignments and open order follow the new id as after an
upgrade (`carry_unit_over`). When no single successor can be named the reply says the move ran and the unit is gone
(`identity: "unknown"`), never a refusal. A later order to the old id (a retry) is refused, naming the successor.
"""
from __future__ import annotations

from ..client import TunerdError
from ..rows import act

#: The error the runtime gives an order to an id that is not on my unit list.
NO_SUCH_UNIT = "no such unit"


def _successor_row(s: dict) -> dict:
    return {k: s[k] for k in ("id", "type", "x", "y", "moves", "hp") if s.get(k) is not None}


class UnitSuccessorsMixin:
    """The successor of a unit an order saw vanish. A part of harness.game.Game (see harness/game_parts/__init__.py);
    `self` is the whole Game."""

    def _vanished_mover(self, unit_id: int, sent: dict, x: int, y: int, pid: int | None = None) -> dict:
        """The reply to a move the engine took (`sent` is H.move_unit's answer: the start plot, type and moves) whose
        unit is no longer on the map at the read-back."""
        start = {"x": sent.get("x"), "y": sent.get("y")}
        reach = sent.get("max_moves") or sent.get("moves") or 3
        try:
            found = self.q(self.h("move_successor", int(unit_id), sent.get("type"), sent.get("x"), sent.get("y"),
                                  int(x), int(y), reach, pid=pid))
        except TunerdError:
            found = None
        found = found if isinstance(found, dict) else {}
        out: dict = {"ok": True, "unit_id": unit_id, "moved_from": start, "unit_gone": True}
        s = found.get("successor")
        if isinstance(s, dict) and s.get("id") is not None:
            row = _successor_row(s)
            out.update({"x": row.get("x"), "y": row.get("y"), "arrived": (row.get("x"), row.get("y")) == (x, y),
                        "successor": row})
            out["note"] = (f"the move ran: {sent.get('type') or 'the unit'} {unit_id} entered the ruins at "
                           f"({row.get('x')},{row.get('y')}) and the engine replaced it with {row.get('type')} "
                           f"{row['id']} (a ruins upgrade); {unit_id} no longer exists, order {row['id']} from here on")
            out["actions"] = [act("tactical_view", unit_id=row["id"])]
            self._note_spent(unit_id, f"upgraded in the ruins to {row.get('type')} (new id {row['id']})")
            try:
                carried = self.carry_unit_over(unit_id, row["id"], why="upgraded in the ruins")
            except Exception as e:   # a notebook problem never loses the move's reply
                carried = {"err": f"{type(e).__name__}: {e}"}
            if carried:
                out["carried_over"] = carried
            return out
        out["identity"] = "unknown"
        cands = [_successor_row(c) for c in found.get("candidates") or [] if isinstance(c, dict)]
        if cands:
            out["candidates"] = cands
        out["note"] = (f"the move was sent and unit {unit_id} is no longer on the map: most likely ruins on the way "
                       "replaced it with a stronger unit under a new id"
                       + (" (one of `candidates`)" if cands else "")
                       + "; state(what='units') lists my units -- do not repeat the move")
        out["actions"] = [act("units")]
        return out

    def _refusal_names_successor(self, r: dict, unit_id: int, pid: int | None = None) -> dict:
        """An order to an id that is gone (a retried move, a briefing older than a ruins upgrade): when the runtime
        knows the unit that replaced it, the refusal names it and the read that shows it."""
        if not isinstance(r, dict) or r.get("ok") or r.get("err") != NO_SUCH_UNIT:
            return r
        try:
            found = self.q(self.h("successor_of", int(unit_id), pid=pid))
        except TunerdError:
            return r
        s = found.get("successor") if isinstance(found, dict) else None
        if not isinstance(s, dict) or s.get("id") is None:
            return r
        row = _successor_row(s)
        r["successor"] = row
        r["err"] = (f"no such unit: {unit_id} is gone -- the ruins at ({row.get('x')},{row.get('y')}) made it "
                    f"{row.get('type')} {row['id']} (turn {s.get('turn')}); nothing was sent, order {row['id']} instead")
        r["actions"] = [act("tactical_view", unit_id=row["id"])]
        return r
