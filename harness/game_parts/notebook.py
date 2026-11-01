"""The notebook: notes, the briefing and assignments (harness/notes.py, briefing.py, assignments.py hold the logic)."""
from __future__ import annotations

from ..notebook_identity import game_keys, open_notebook
from .support import plain_text


class NotebookMixin:
    """The notebook: notes, the briefing and assignments (harness/notes.py, briefing.py, assignments.py hold the logic).

    A part of harness.game.Game (see harness/game_parts/__init__.py); `self` is the whole Game."""

    # ------------------------------------------------------------ notebook
    def game_key(self) -> str:
        """A name for this game that every save of it shares and no other game does: leader, civ, map script, start
        turn and the game's identity (harness/notebook_identity.py, GitLab #168). Cached per seat (`_game_keys`):
        the identity is the seat's own starting plot, so a server moved by set_seat onto the other hotseat seat
        must not keep the first seat's key -- live t173 (2026-10-02) a session server that started on Mongolia
        and was moved to Venice read an empty notebook under Mongolia's key while Venice's 35 notes sat under
        hers. The cache is dropped when a game is loaded (wait_ingame). `_game_key` set from outside is a fixed
        key (tests, simulations)."""
        fixed = getattr(self, "_game_key", None)
        if fixed:
            return fixed
        return self._keys()["key"]

    def _keys(self) -> dict:
        """The seat's keys, cached once the read carried the identity (read again until it does)."""
        keys = getattr(self, "_game_keys", None)
        if not isinstance(keys, dict):
            keys = self._game_keys = {}
        if not (keys.get(self.seat) or {}).get("identified"):
            keys[self.seat] = game_keys(self._key_facts())
        return keys[self.seat]

    def _key_facts(self) -> dict:
        info = self.q(self.h("game_key_facts"))
        return info if isinstance(info, dict) else {}

    def note_unit_refs(self, text: str) -> list[dict]:
        """The units `text` names by id, with their type now (one units read; never raises): stored on the note so
        a reload that reissues the id can be told apart (GitLab #63)."""
        from ..notes import Notebook
        try:
            return Notebook.unit_refs(text, self._unit_rows())
        except Exception:
            return []

    def notes_with_unit_check(self, notes: list[dict]) -> list[dict]:
        """`notes` with `unit_check` where a stored unit id is another type or gone now (one units read, only when
        some note stored units; never raises)."""
        from ..notes import Notebook
        if not any(isinstance(n, dict) and n.get("units") for n in notes if n):
            return notes
        try:
            return Notebook.check_unit_refs(notes, self._unit_rows())
        except Exception:
            return notes

    def notebook(self):
        """This game's and seat's notebook. The first look at an identity's notebook decides, once, whether the
        seat's notebook from before #168 is this game's (harness/notebook_identity.py open_notebook), on a fresh
        read of the turn."""
        from ..notes import Notebook
        nb = Notebook(self.game_key(), self.seat)
        if not getattr(self, "_game_key", None) and not nb.exists():
            info = self._key_facts()
            keys = game_keys(info)
            if keys["identified"]:
                open_notebook(nb, keys, self.seat, info.get("turn"), info.get("start"))
        return nb

    # ------------------------------------------------------------ the server's own memory (#144)
    # A per-seat fact that must outlive this process (Notebook.memo): a seat played one finish per process
    # (scripts/mcp_session.py, a seat loop) forgot every turn what it had already been woken for. Read from the
    # file each time, so two processes of one seat see each other's writes; a game without a notebook (the main
    # menu, a fake game in a test) keeps the fact for the process only.
    def memo(self, key: str, default=None):
        try:
            return self.notebook().memo(key, default)
        except Exception:  # no notebook here: the fact lives in this process, as the hand-off's order read does
            return self.__dict__.setdefault("_memo_local", {}).setdefault(self.seat, {}).get(key, default)

    def set_memo(self, key: str, value) -> None:
        self.__dict__.setdefault("_memo_local", {}).setdefault(self.seat, {})[key] = value
        try:
            self.notebook().set_memo(key, value)
        except Exception:  # see memo
            pass

    # ------------------------------------------------------------ briefing (#30)
    BRIEFING_SINCE = ("previous", "turn")

    def briefing(self, since: str = "previous", limit: int = 8, ts: dict | None = None,
                 notes: str = "auto", detail: str = "compact") -> dict:
        """This seat's turn in one compact read: mandatory decisions (never cut), warnings, opportunities,
        changes since the seat's previous briefing (empire totals, cities, units, events), the board
        (empire, notable cities, units needing a look, visible threats), the seat's notes and, without a
        comparable baseline, the civilization's own rules. Built from turn_state, summary, cities, units and
        one runtime read (H.briefing_board); five tuner trips, six on a turn a plot of mine changed hands.

        notes (#43): "new" carries only the notes written since the seat's last hand-off (finish_turn or
        briefing) with `notes_unshown` counting the rest, "all" the latest `limit`; "auto" is "all" for
        since="turn" (the recovery read) and "new" otherwise. detail: "compact" threat rows (unit, hp,
        position, nearest own unit and city, assessment; a threat the previous briefing listed only marked
        `seen`) or "full" (every field of the board's row).

        Events come from the game's event log after the previous briefing's cursor, not from the digest's
        cursor: turn_digest / finish_turn and the briefing each see every event once. since="turn" (or no
        comparable baseline) shows everything after this seat's last turn_end instead -- the recovery read
        after a context reset. The baseline lives beside the notebook, per game and seat, and is replaced by
        every briefing. The caller checks the gate first: this reads the board."""
        from .. import briefing as B
        from ..notes import Notebook
        if since not in self.BRIEFING_SINCE:
            return {"ok": False, "err": f"since must be one of {list(self.BRIEFING_SINCE)}, not {since!r}"}
        if detail not in B.THREAT_DETAIL:
            return {"ok": False, "err": f"detail must be one of {list(B.THREAT_DETAIL)}, not {detail!r}"}
        if notes not in ("auto",) + Notebook.HAND_OFF_MODES:
            return {"ok": False, "err": f"notes must be one of {['auto', *Notebook.HAND_OFF_MODES]}, not {notes!r}"}
        if notes == "auto":
            notes = "all" if since == "turn" else "new"
        limit = max(0, min(int(limit), 50))
        ts = ts if isinstance(ts, dict) else self.turn_state()
        nb = self.notebook()
        prev = nb.briefing_baseline()
        turn = ts.get("turn")
        # The comparability of `prev` needs the log head; the cursor it chooses needs the comparability.
        # Decide the cursor from the turn check alone, then confirm the log did not restart underneath it.
        base = B.baseline_state(prev, turn, None)
        since_seq = prev.get("event_seq") if since == "previous" and base.get("comparable") else -1
        if not isinstance(since_seq, int):
            since_seq = -1
        board = self.q(self.h('briefing_board', since_seq)) or {}
        base = B.baseline_state(prev, turn, board.get("event_seq"))
        if since_seq != -1 and base.get("events_restarted"):
            board = self.q(self.h('briefing_board', -1)) or {}
        # Markup off before the composer shortens a line (a cut "[ICON_..." is no longer a tag to strip).
        events = plain_text(self._refine_events(board.get("events") or []))
        base["events_since"] = ("previous briefing" if since_seq != -1 and not base.get("events_restarted")
                                else "this seat's last turn end")
        summary = self.summary()
        cities = self.cities()
        units = self.units()
        out, snap = B.build(ts, summary if isinstance(summary, dict) else {}, cities if isinstance(cities, list) else [],
                            units if isinstance(units, list) else [], board, base, prev, events, limit,
                            include_rules=not base.get("comparable") or since == "turn", detail=detail)
        lost = ((out.get("changes") or {}).get("territory") or {}).get("lost")
        if lost:
            # Land I held at the baseline and do not now (a Citadel, a city lost): one extra read, only then,
            # says who holds each plot and what stood on it -- what the map's border change shows a human.
            try:
                plots = [[r["x"], r["y"]] for r in lost]
                rows = self.q(self.h('territory_now', plots))
                by_key = {(r.get("x"), r.get("y")): r for r in rows if isinstance(r, dict)} if isinstance(rows, list) else {}
                for r in lost:
                    r.update({k: v for k, v in (by_key.get((r["x"], r["y"])) or {}).items() if k not in ("x", "y")})
            except Exception as e:  # the plot read must never cost the briefing
                out["changes"]["territory"]["lost_error"] = f"{type(e).__name__}: {e}"
        nb.set_briefing_baseline(snap)
        try:
            out.update(nb.hand_off_section(notes, max(1, limit), turn=out.get("turn")))
            if out.get("notes") and isinstance(units, list):
                Notebook.check_unit_refs(out["notes"], units)   # #63: a reissued id is named, no extra read
        except Exception as e:  # a notebook problem must not lose the briefing
            out["notes_error"] = f"{type(e).__name__}: {e}"
        try:
            section, by_unit = self._assignment_section(nb, limit)
        except Exception as e:  # the plan read must never cost the turn's briefing
            section, by_unit = {"error": f"{type(e).__name__}: {e}"}, {}
        if section:
            out["assignments"] = section
            for row in out.get("decisions") or []:
                if row.get("kind") == "unit_orders" and row.get("id") in by_unit:
                    row["assignment"] = by_unit[row["id"]]
        from .. import orders as O
        open_orders = nb.orders("open")   # the stored state: no game read
        if open_orders:
            out["orders"] = O.briefing_section(open_orders, limit)
            by_unit_order = {o["unit"]["id"]: o for o in open_orders}
            for row in out.get("decisions") or []:
                o = by_unit_order.get(row.get("id")) if row.get("kind") == "unit_orders" else None
                if o:
                    row["order"] = {"id": o["id"], "status": o["status"],
                                    **({"reason": o["pause"]["reason"]} if o.get("pause") else {})}
        out["ok"] = True
        return plain_text(out)

    # ------------------------------------------------------------ assignments (#33)
    def assignment_facts(self, records: list[dict]) -> dict:
        """One runtime read of everything `records` reference (harness/assignments.py `spec`)."""
        from .. import assignments as A
        facts = self.q(self.h('assignment_facts', A.spec(records)))
        return facts if isinstance(facts, dict) else {}

    def _reconciled(self, nb, records: list[dict]) -> tuple[list[dict], int | None]:
        """Every record reconciled against one read; what it saw is stored back on the notebook."""
        from .. import assignments as A
        if not records:
            return [], None
        facts = self.assignment_facts(records)
        turn = facts.get("turn")
        rows, updates = [], {}
        for a in records:
            row, upd = A.reconcile(a, facts, turn, self.seat)
            rows.append(row)
            if upd:
                updates[a["id"]] = upd
        nb.store_observations(updates)
        return rows, turn

    def _assignment_section(self, nb, limit: int) -> tuple[dict | None, dict]:
        """(the briefing's `assignments`, {unit id: {id, role}} for the decision rows); None without any."""
        from .. import assignments as A
        rows, _ = self._reconciled(nb, nb.assignments("active"))
        if not rows:
            return None, {}
        by_unit = {}
        for r in rows:
            for u in r.get("units") or []:
                if not u.get("gone"):
                    by_unit.setdefault(u["id"], {"id": r["id"], "role": r.get("role")})
        return A.briefing_section(rows, limit), by_unit

    def assign(self, role: str, purpose: str, unit_ids=None, city_ids=None, target=None, done_when=None,
               review=None, replace_id: int | None = None) -> dict:
        """Store a structured assignment (harness/assignments.py): who, what for, where, when it is done and
        when to look again. Every unit and city must be mine now; each is fingerprinted (type and creation
        turn, name and founding turn) so a reused id later reads as the assigned one gone. replace_id closes
        that assignment as replaced by this one. Returns the stored record and how it reconciles right now."""
        from .. import assignments as A
        try:
            rec = {"role": A.clean_text(role, A.ROLE_MAX, "role", required=True),
                   "purpose": A.clean_text(purpose, A.PURPOSE_MAX, "purpose", required=True)}
            uids, cids = A.normalize_ids(unit_ids, "unit_ids"), A.normalize_ids(city_ids, "city_ids")
            rec["target"] = A.normalize_target(target)
            rec["done_when"] = A.normalize_done(done_when, rec["target"])
            rec["review"] = A.normalize_review(review)
            probe = {**rec, "units": [{"id": i} for i in uids], "cities": [{"id": i} for i in cids]}
            facts = self.assignment_facts([probe])
            rec["units"], rec["cities"] = A.check_new_refs(uids, cids, facts)
        except A.AssignmentError as e:
            return {"ok": False, "err": str(e)}
        if not rec["units"] and not rec["cities"] and not rec["target"]:
            return {"ok": False, "err": "an assignment needs at least one of unit_ids, city_ids or target "
                                        "(a plan with none of them is a note: notebook(action='remember'))"}
        turn = facts.get("turn")
        row, upd = A.reconcile({**rec, "id": 0}, facts, turn, self.seat)
        if upd.get("seen"):
            rec["seen"] = upd["seen"]
        nb = self.notebook()
        res = nb.add_assignment(rec, turn if isinstance(turn, int) else -1, replace_id=replace_id)
        if not res.get("ok"):
            return res
        row["id"] = res["assignment"]["id"]
        row["since_turn"] = res["assignment"]["created_turn"]
        out = {"ok": True, "assignment": row}
        if res.get("replaced") is not None:
            out["replaced"] = res["replaced"]
        return out

    AMENDABLE = ("role", "purpose", "unit_ids", "city_ids", "target", "done_when", "review")

    def amend_assignment(self, assignment_id: int, changes: dict, note: str = "") -> dict:
        """Change fields of an active assignment in place (only the keys in `changes`; target={} clears the
        target). New unit / city ids are fingerprinted as in assign. The result carries `previous`."""
        from .. import assignments as A
        nb = self.notebook()
        cur = next((a for a in nb.assignments("all") if a.get("id") == assignment_id), None)
        if cur is None or cur.get("status") != "active":
            return nb.update_assignment(assignment_id, {}, -1, "amend")   # the same refusal, with ids / replaced_by
        bad = [k for k in changes if k not in self.AMENDABLE]
        if bad or (not changes and not note):
            return {"ok": False, "err": f"amend one or more of {list(self.AMENDABLE)}, or give a note"
                                        + (f"; not {bad}" if bad else "")}
        if not changes:
            # A note alone is a history line (live England t223: "the engine moved the scout out of Ottoman land"
            # had no field to change and was refused). The assignment is reconciled as any amend is.
            facts = self.assignment_facts([cur])
            turn = facts.get("turn")
            res = nb.update_assignment(assignment_id, {}, turn if isinstance(turn, int) else -1,
                                       f"note: {A.clean_text(note, A.NOTE_MAX, 'note')}")
            if not res.get("ok"):
                return res
            row, _upd = A.reconcile(res["assignment"], facts, turn, self.seat)
            return {"ok": True, "assignment": row, "previous": {}}
        try:
            new: dict = {}
            if "role" in changes:
                new["role"] = A.clean_text(changes["role"], A.ROLE_MAX, "role", required=True)
            if "purpose" in changes:
                new["purpose"] = A.clean_text(changes["purpose"], A.PURPOSE_MAX, "purpose", required=True)
            if "target" in changes:
                new["target"] = A.normalize_target(changes["target"])
                new["seen"] = None
            target = new.get("target", cur.get("target")) if "target" in changes else cur.get("target")
            if "done_when" in changes:
                new["done_when"] = A.normalize_done(changes["done_when"], target)
            if "review" in changes:
                new["review"] = A.normalize_review(changes["review"])
            uids = A.normalize_ids(changes["unit_ids"], "unit_ids") if "unit_ids" in changes else None
            cids = A.normalize_ids(changes["city_ids"], "city_ids") if "city_ids" in changes else None
            probe = {**cur, **new}
            if uids is not None:
                probe["units"] = [{"id": i} for i in uids]
            if cids is not None:
                probe["cities"] = [{"id": i} for i in cids]
            facts = self.assignment_facts([probe])
            nu, nc = A.check_new_refs(uids or [], cids or [], facts)
            if uids is not None:
                new["units"] = nu
            if cids is not None:
                new["cities"] = nc
        except A.AssignmentError as e:
            return {"ok": False, "err": str(e)}
        merged = {**cur, **new}
        if not merged.get("units") and not merged.get("cities") and not merged.get("target"):
            return {"ok": False, "err": "that would leave no unit, city or target: notebook(action='close') it instead"}
        turn = facts.get("turn")
        row, upd = A.reconcile(merged, facts, turn, self.seat)
        if upd.get("seen") and "target" in changes:
            new["seen"] = upd["seen"]
        what = "amended " + ", ".join(sorted(changes)) + (f": {A.clean_text(note, A.NOTE_MAX, 'note')}" if note else "")
        res = nb.update_assignment(assignment_id, new, turn if isinstance(turn, int) else -1, what)
        if not res.get("ok"):
            return res
        prev = res.get("previous") or {}
        return {"ok": True, "assignment": row, "previous": {k: v for k, v in prev.items() if k != "seen"}}

    def carry_unit_over(self, old_id: int, new_id: int, why: str = "upgraded") -> dict:
        """A unit the engine replaced with a new id (an upgrade: the same plot, the same job) keeps what the
        notebook says about it: every active assignment naming `old_id` and the open order on it are re-pointed
        at `new_id` with a fresh fingerprint, in one read -- no read when nothing names it. Live England
        t206-t214: the Musketman -> Rifleman and Longbowman -> Gatling Gun upgrades left assignments 42 and 46
        reading "gone ... amend_assignment(unit_ids=...) to take it over" for eight turns. Returns {} when
        nothing named the unit, else `unit` (the new fingerprint), `assignments` [{id, role}] and `order` (id);
        a read that cannot find the new unit answers `err` and leaves the records as they were."""
        from .. import assignments as A
        old_id, new_id = int(old_id), int(new_id)
        nb = self.notebook()
        hits = [a for a in nb.assignments("active") if any(u.get("id") == old_id for u in a.get("units") or [])]
        orders = [o for o in nb.orders("open") if (o.get("unit") or {}).get("id") == old_id]
        if not hits and not orders:
            return {}
        facts = self.assignment_facts([{"id": 0, "units": [{"id": new_id}]}])
        r = (facts.get("units") or {}).get(str(new_id)) or {}
        if r.get("missing") or not r.get("type"):
            return {"err": f"unit {new_id} is not mine now: assignments {[a['id'] for a in hits]} and orders "
                           f"{[o['id'] for o in orders]} still name {old_id} (notebook(action='amend') / notebook(action='give_order') to move them)"}
        fp = A.fingerprint_unit(r)
        turn = facts.get("turn")
        turn = turn if isinstance(turn, int) else -1
        what = f"unit {old_id} {why}: now {fp.get('type')} {new_id}"
        out: dict = {"unit": fp}
        moved = []
        for a in hits:
            units = [fp if u.get("id") == old_id else u for u in a.get("units") or []]
            if nb.update_assignment(a["id"], {"units": units}, turn, what).get("ok"):
                moved.append({"id": a["id"], "role": a.get("role")})
        if moved:
            out["assignments"] = moved
        for o in orders:
            o["unit"] = fp
            o.pop("issued", None)   # the standing move died with the old unit; the step is issued afresh
            o["updated_turn"] = turn
            o.setdefault("history", []).append({"turn": turn, "what": what})
            nb.put_order(o)
            out["order"] = o["id"]
        return out

    def close_assignment(self, assignment_id: int, outcome: str = "completed", note: str = "") -> dict:
        """Close an active assignment as completed or cancelled. No game read beyond the turn number."""
        from .. import assignments as A
        if outcome not in A.OUTCOMES:
            return {"ok": False, "err": f"outcome must be one of {list(A.OUTCOMES)}"}
        try:
            note = A.clean_text(note, A.NOTE_MAX, "note")
        except A.AssignmentError as e:
            return {"ok": False, "err": str(e)}
        turn = self.turn_state().get("turn", -1)
        res = self.notebook().update_assignment(assignment_id, {"outcome_note": note} if note else {}, turn,
                                                outcome + (f": {note}" if note else ""), close=outcome)
        if res.get("ok"):
            a = res["assignment"]
            return {"ok": True, "closed": assignment_id, "status": a["status"], "turn": turn,
                    "active": len(self.notebook().assignments("active"))}
        return res

    def assignments(self, status: str = "active") -> dict:
        """Active assignments reconciled against the board now (one read), or the stored closed ones."""
        nb = self.notebook()
        if status not in ("active", "closed", "all"):
            return {"ok": False, "err": "status must be active, closed or all"}
        out: dict = {"ok": True, "game": nb.key}
        if status in ("active", "all"):
            rows, turn = self._reconciled(nb, nb.assignments("active"))
            out["turn"] = turn
            out["active"] = rows
        if status in ("closed", "all"):
            out["closed"] = [{k: a.get(k) for k in ("id", "role", "purpose", "status", "created_turn", "closed_turn",
                                                    "replaced_by", "replaces", "outcome_note") if a.get(k) is not None}
                             for a in nb.assignments("closed")]
        return plain_text(out)
