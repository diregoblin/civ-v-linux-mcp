"""Per-game memory for the seat: the notes a human player keeps in their head between turns.

An LLM's context is compacted or lost between sessions; a human remembers "I am going Tradition then
Rationalism, Askia will backstab me, keep two archers in Moson Kahni". `Notebook` stores those notes
beside the game (not inside the save: the save format is not ours) keyed by a `game_key` the caller
derives from stable in-game facts, so every save of the same game shares one notebook and a different
game never sees it. Notes carry the turn they were written on; the caller decides which to surface.

Storage: `$CIV5_NOTES_DIR` or `$XDG_DATA_HOME/civ5-harness/notes` (default `~/.local/share/...`),
one JSON file per game key. No game connection is needed to read or write a notebook. The same file keeps the
seat's last turn-briefing snapshot under `briefing` (harness/briefing.py), what the next briefing compares against,
and the structured `assignments` (harness/assignments.py): role, purpose, fingerprinted units and cities, target,
completion condition, review triggers and status, beside the prose notes and independent of them. The conditional
unit `orders` (harness/orders.py: a unit's steps, the current one, its pause reason and last result) live there too.

The key names the game by its identity and the seat (harness/notebook_identity.py, GitLab #168): a notebook
written under an earlier form of the key is taken over there, once, quarantined (`adopted` notes and assignments,
paused orders), and `Notebook.create` writes the identity's first file either way.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

#: What an adopted record says about itself (a note row's `adopted`, an assignment's review reason, an order's
#: pause): taken over from the seat's label-keyed notebook by harness/notebook_identity.py (GitLab #168).
ADOPTED = ("adopted from a notebook written before this game had its own key (GitLab #168): it may be another "
           "game's, or this one's from before the upgrade")


MAX_NOTES = 200
MAX_TEXT = 2000


def notes_dir() -> Path:
    d = os.environ.get("CIV5_NOTES_DIR")
    if d:
        return Path(d)
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return Path(base) / "civ5-harness" / "notes"


def safe_key(key: str) -> str:
    key = re.sub(r"[^A-Za-z0-9._-]+", "_", key.strip()) or "game"
    return key[:120]


def _rev(n: dict) -> int:
    v = n.get("rev", n.get("id", 0))
    return v if isinstance(v, int) else 0


class Notebook:
    def __init__(self, game_key: str, seat: int):
        self.key = safe_key(f"{game_key}-seat{seat}")
        self.path = notes_dir() / f"{self.key}.json"

    def exists(self) -> bool:
        return self.path.exists()

    def create(self, data: dict | None = None) -> None:
        """Write this notebook's first file: `data` (a notebook taken over from an earlier key,
        harness/notebook_identity.py) or an empty one. Never over a file that is already there."""
        if self.path.exists():
            return
        self._save(data if isinstance(data, dict) and isinstance(data.get("notes"), list) else {"next_id": 1, "notes": []})

    # ------------------------------------------------------------ io
    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            data = None
        if not isinstance(data, dict) or not isinstance(data.get("notes"), list):
            data = {"next_id": 1, "notes": []}
        data.setdefault("next_id", max([n.get("id", 0) for n in data["notes"]] + [0]) + 1)
        # `rev` counts writes (a new note or a rewrite); each note keeps the rev of its last write and the
        # hand-off cursor (`notes_seen`) is a rev, so a rewritten note is new again (#43). Notes written
        # before 1.7.0 carry no rev: their id stands in, which orders them the same way.
        data["rev"] = max([int(data.get("rev") or 0)] + [_rev(n) for n in data["notes"]])
        return data

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=0))
        os.replace(tmp, self.path)

    # ------------------------------------------------------------ api
    def remember(self, text: str, turn: int, tag: str = "", replace_id: int | None = None,
                 retag: bool = False, units: list[dict] | None = None) -> dict:
        """Append a note, or with `replace_id` rewrite that note in place. `units` is the type of every unit
        the text names by id, as it was when the note was written ([{id, type}]; GitLab #63): the engine
        reissues ids in creation order, so after a reload the same id can be another unit, and `check_unit_refs`
        says so when the note comes back.

        A replace is guarded: a non-empty `tag` that differs from the stored tag refuses to write (the id
        was probably wrong: a scout note over the plan) unless `retag` is true; an empty tag keeps the stored
        one. Every successful replace returns `previous` (the id, text, tag and turn it overwrote) so a
        mistaken overwrite can be undone by writing the old text back."""
        text = (text or "").strip()
        if not text:
            return {"ok": False, "err": "empty note"}
        if len(text) > MAX_TEXT:
            return {"ok": False, "err": f"note longer than {MAX_TEXT} characters; split it"}
        tag = (tag or "").strip()[:40]
        data = self._load()
        notes = data["notes"]
        if replace_id is not None:
            for n in notes:
                if n.get("id") != replace_id:
                    continue
                stored_tag = n.get("tag", "")
                if tag and tag != stored_tag and not retag:
                    return {"ok": False, "id": replace_id, "stored_tag": stored_tag, "tag": tag,
                            "err": f"note {replace_id} is tagged {stored_tag!r}, not {tag!r}: nothing written. "
                                   f"Pass the right replace_id, an empty tag to keep {stored_tag!r}, "
                                   f"or retag=true to change it"}
                previous = {"id": n.get("id"), "text": n.get("text", ""), "tag": stored_tag, "turn": n.get("turn")}
                data["rev"] += 1
                n.update({"text": text, "turn": turn, "tag": tag or stored_tag, "rev": data["rev"]})
                n.pop("units", None)
                n.pop("adopted", None)   # rewritten by this seat: its own now (#168)
                if units:
                    n["units"] = units
                self._save(data)
                out = {"ok": True, "note": n, "replaced": True, "previous": previous}
                if tag and tag != stored_tag:
                    out["retagged"] = True
                return out
            return {"ok": False, "err": f"no note with id {replace_id}", "ids": [n.get("id") for n in notes]}
        data["rev"] += 1
        note = {"id": data["next_id"], "turn": turn, "tag": tag, "text": text, "rev": data["rev"]}
        if units:
            note["units"] = units
        data["next_id"] += 1
        notes.append(note)
        dropped = 0
        if len(notes) > MAX_NOTES:
            dropped = len(notes) - MAX_NOTES
            del notes[:dropped]
        self._save(data)
        out = {"ok": True, "note": note, "count": len(notes)}
        if dropped:
            out["dropped_oldest"] = dropped
        return out

    def recall(self, tag: str = "", limit: int = 50, turn: int | None = None) -> dict:
        """Every note (the newest `limit`, `tag` filters). With `turn`, notes from a later turn than the one on
        screen are marked `later_timeline`, listed last, and counted under `later_timeline` (GitLab #62)."""
        notes = self._load()["notes"]
        if tag:
            notes = [n for n in notes if n.get("tag") == tag]
        notes = notes[-max(1, limit):]
        notes, later = self._mark_later(notes, turn)
        out = {"ok": True, "notes": notes, "count": len(notes), "game": self.key}
        if later:
            out["later_timeline"] = {"count": later,
                                     "note": f"{later} of these notes were written on turns later than turn {turn} (a save was "
                                             "loaded): they describe a timeline this game has not reached and are listed last; "
                                             "trust the board, not those notes"}
        adopted = self.adopted_line(notes)
        if adopted:
            out["adopted"] = adopted
        return out

    @staticmethod
    def adopted_line(rows: list[dict]) -> str | None:
        """What a reply says beside notes marked `adopted` (GitLab #168), None without any."""
        n = sum(1 for r in rows if isinstance(r, dict) and r.get("adopted"))
        return (f"{n} of these notes are marked adopted: {ADOPTED}; trust the board, then rewrite (replace_id) or "
                "forget each one") if n else None

    def forget(self, note_id: int) -> dict:
        data = self._load()
        before = len(data["notes"])
        data["notes"] = [n for n in data["notes"] if n.get("id") != note_id]
        if len(data["notes"]) == before:
            return {"ok": False, "err": f"no note with id {note_id}", "ids": [n.get("id") for n in data["notes"]]}
        self._save(data)
        return {"ok": True, "forgotten": note_id, "count": len(data["notes"])}

    def latest(self, limit: int = 8) -> list[dict]:
        """The most recent notes, for the turn hand-off: the plan arrives with the turn."""
        return self._load()["notes"][-limit:]

    HAND_OFF_MODES = ("new", "all")

    def hand_off(self, mode: str = "new", limit: int = 8, turn: int | None = None) -> dict:
        """The notes a turn hand-off (finish_turn, briefing) carries (#43): with mode "new" only those
        written or rewritten since the seat's last hand-off, with mode "all" the latest `limit` as before
        1.7.0. Either way the cursor moves to the newest note, so what was shown once is not shown again by
        default; recall() has every note. {notes, total, unshown}: `unshown` counts the notes this answer
        left out (older than the cursor, or beyond `limit`). With `turn` (the turn on screen) a note written on
        a later turn is marked `later_timeline` (a save was loaded: the plan it describes is not this game's
        present), and `later` counts them."""
        if mode not in self.HAND_OFF_MODES:
            raise ValueError(f"notes must be one of {list(self.HAND_OFF_MODES)}, not {mode!r}")
        data = self._load()
        notes = data["notes"]
        seen = int(data.get("notes_seen") or 0)
        limit = max(1, int(limit))
        rows = notes[-limit:] if mode == "all" else [n for n in notes if _rev(n) > seen][-limit:]
        top = max([seen] + [_rev(n) for n in notes])
        if top != seen:
            data["notes_seen"] = top
            self._save(data)
        rows, later = self._mark_later(rows, turn)
        return {"notes": rows, "total": len(notes), "unshown": len(notes) - len(rows), "later": later}

    @staticmethod
    def _mark_later(rows: list[dict], turn: int | None) -> tuple[list[dict], int]:
        """With `turn` (the turn on screen): a note written on a later turn is marked `later_timeline` (a save was
        loaded; its plan is a timeline this game has not reached) and every such note is listed AFTER the notes of
        this timeline, by turn -- not by id, which put a t278 "the game is over" above a t238 note (GitLab #62,
        live Assyria t239). Without `turn` the rows are returned as they are."""
        if turn is None:
            return rows, 0
        current, later = [], []
        for n in rows:
            if isinstance(n.get("turn"), int) and n["turn"] > turn:
                later.append({**n, "later_timeline": True})
            else:
                current.append(n)
        later.sort(key=lambda n: (n.get("turn", 0), n.get("id", 0)))
        return current + later, len(later)

    def hand_off_section(self, mode: str = "new", limit: int = 8, turn: int | None = None) -> dict:
        """hand_off() as the keys a reply merges in: `notes` (the rows, only when there are any),
        `notes_unshown` {count, more} when the answer left some out, and `notes_later_timeline` when `turn` is
        given and a note was written on a later turn than it (a save was loaded)."""
        h = self.hand_off(mode, limit, turn=turn)
        out: dict = {}
        if h["notes"]:
            out["notes"] = h["notes"]
        adopted = self.adopted_line(h["notes"])
        if adopted:
            out["notes_adopted"] = adopted
        if h["later"]:
            out["notes_later_timeline"] = (f"{h['later']} of these notes were written on turns later than turn {turn} "
                                           "(a save was loaded): the plan and the units they describe are a timeline "
                                           "this game has not reached; trust the board, not those notes")
        if h["unshown"]:
            out["notes_unshown"] = {"count": h["unshown"],
                                    "more": "notebook(action='recall') lists every note; notes='all' shows the latest here"}
        return out

    # ------------------------------------------------------------ unit ids in notes (#63)
    UNIT_ID_RE = re.compile(r"(?<![\d.])(\d{4,8})(?![\d.])")

    @classmethod
    def unit_refs(cls, text: str, roster: list[dict]) -> list[dict]:
        """The units a note names by id, with their type now: every 4-8 digit number in `text` that is one of
        my unit ids (`roster` rows carry id and type). Stored on the note so a reload that hands the id to another
        unit can be told apart later (live Assyria t239: note 5's Great Merchant 1343522 was a Mongolian Khan on
        the reloaded timeline)."""
        by_id = {}
        for r in roster if isinstance(roster, list) else []:
            if isinstance(r, dict) and r.get("id") is not None and r.get("type"):
                by_id[int(r["id"])] = str(r["type"])
        out, seen = [], set()
        for m in cls.UNIT_ID_RE.finditer(text or ""):
            i = int(m.group(1))
            if i in by_id and i not in seen:
                seen.add(i)
                out.append({"id": i, "type": by_id[i]})
        return out

    @staticmethod
    def check_unit_refs(notes: list[dict], roster: list[dict]) -> list[dict]:
        """`notes` with `unit_check` on every note whose stored units are not what the ids are now: another type
        (the id was reissued after a reload) or gone. Notes without stored units are left as they are."""
        by_id = {}
        for r in roster if isinstance(roster, list) else []:
            if isinstance(r, dict) and r.get("id") is not None:
                by_id[int(r["id"])] = str(r.get("type") or "")
        for n in notes if isinstance(notes, list) else []:
            if not (isinstance(n, dict) and isinstance(n.get("units"), list)):
                continue
            problems = []
            for u in n["units"]:
                if not (isinstance(u, dict) and u.get("id") is not None):
                    continue
                now = by_id.get(int(u["id"]))
                if now is None:
                    problems.append(f"unit {u['id']} ({u.get('type')}) is not among my units now")
                elif u.get("type") and now != u["type"]:
                    problems.append(f"unit {u['id']}: the note says {u['type']}, that id is a {now} now "
                                    "(ids are reissued after a reload; this is a different unit)")
            if problems:
                n["unit_check"] = problems
        return notes

    # ------------------------------------------------------------ briefing baseline (#30)
    def briefing_baseline(self) -> dict | None:
        """The snapshot the seat's previous briefing left (harness/briefing.py), or None."""
        b = self._load().get("briefing")
        return b if isinstance(b, dict) else None

    def set_briefing_baseline(self, snap: dict) -> None:
        data = self._load()
        data["briefing"] = snap
        self._save(data)

    # ------------------------------------------------------------ the server's own memory (#144)
    # Facts the harness keeps for itself per game and seat, across server processes, under `memo` in the same
    # file: what a quiet-turn run was already woken for, the happiness baseline. Never shown as notes.
    def memo(self, key: str, default=None):
        m = self._load().get("memo")
        return m.get(key, default) if isinstance(m, dict) and key in m else default

    def set_memo(self, key: str, value) -> None:
        data = self._load()
        memo = data.get("memo")
        if not isinstance(memo, dict):
            memo = data["memo"] = {}
        memo[key] = value
        self._save(data)

    # ------------------------------------------------------------ assignments (#33)
    # Stored under `assignments` in the same file; harness/assignments.py holds the logic. Status is active,
    # completed, cancelled or replaced; only active ones are reconciled or shown in a briefing.
    def assignments(self, status: str = "active") -> list[dict]:
        rows = [a for a in self._load().get("assignments") or [] if isinstance(a, dict)]
        if status == "all":
            return rows
        if status == "closed":
            return [a for a in rows if a.get("status") != "active"]
        return [a for a in rows if a.get("status") == status]

    def add_assignment(self, record: dict, turn: int, replace_id: int | None = None) -> dict:
        from .assignments import MAX_ACTIVE, MAX_CLOSED
        data = self._load()
        rows = data.setdefault("assignments", [])
        old = None
        if replace_id is not None:
            old = next((a for a in rows if a.get("id") == replace_id), None)
            if old is None or old.get("status") != "active":
                return {"ok": False, "err": f"no active assignment {replace_id} to replace",
                        "active_ids": [a.get("id") for a in rows if a.get("status") == "active"]}
        active = sum(1 for a in rows if a.get("status") == "active") - (1 if old else 0)
        if active >= MAX_ACTIVE:
            return {"ok": False, "err": f"{MAX_ACTIVE} active assignments already: notebook(action='close') finished or "
                                        "abandoned ones first"}
        nid = data.get("next_assignment_id") or (max([a.get("id", 0) for a in rows] + [0]) + 1)
        record = {**record, "id": nid, "status": "active", "created_turn": turn, "updated_turn": turn}
        record.setdefault("history", []).append({"turn": turn, "what": "created" + (f", replacing {replace_id}" if old else "")})
        if old:
            # The obsolete version never competes with its replacement: closed, pointing at it.
            record["replaces"] = replace_id
            old.update({"status": "replaced", "replaced_by": nid, "closed_turn": turn})
            old.setdefault("history", []).append({"turn": turn, "what": f"replaced by {nid}"})
        rows.append(record)
        data["next_assignment_id"] = nid + 1
        self._prune(data, MAX_CLOSED)
        self._save(data)
        return {"ok": True, "assignment": record, **({"replaced": replace_id} if old else {})}

    def update_assignment(self, assignment_id: int, changes: dict, turn: int, what: str,
                          close: str | None = None) -> dict:
        """Apply `changes` to an active assignment (amend), or close it with status `close`."""
        from .assignments import MAX_CLOSED
        data = self._load()
        rows = data.get("assignments") or []
        a = next((r for r in rows if r.get("id") == assignment_id), None)
        if a is None:
            return {"ok": False, "err": f"no assignment {assignment_id}", "ids": [r.get("id") for r in rows]}
        if a.get("status") != "active":
            out = {"ok": False, "err": f"assignment {assignment_id} is {a.get('status')}, not active"}
            if a.get("replaced_by"):
                out["replaced_by"] = a["replaced_by"]
            return out
        previous = {k: a.get(k) for k in changes}
        a.update(changes)
        a.pop("adopted", None)   # amended or closed by this seat: its own now (#168)
        a["updated_turn"] = turn
        if close:
            a["status"], a["closed_turn"] = close, turn
        hist = a.setdefault("history", [])
        hist.append({"turn": turn, "what": what})
        del hist[:-10]
        self._prune(data, MAX_CLOSED)
        self._save(data)
        return {"ok": True, "assignment": a, **({"previous": previous} if changes else {})}

    def store_observations(self, updates: dict) -> None:
        """What a reconcile saw, per assignment id: the target's latest sighting and the plots the assigned
        units stand on (so a missing unit is looked for where it was last)."""
        if not updates:
            return
        data = self._load()
        for a in data.get("assignments") or []:
            u = updates.get(a.get("id"))
            if not u or a.get("status") != "active":
                continue
            if "seen" in u:
                a["seen"] = u["seen"]
            for uid, x, y in u.get("unit_plots") or []:
                for ref in a.get("units") or []:
                    if ref.get("id") == uid:
                        ref["x"], ref["y"] = x, y
        self._save(data)

    @staticmethod
    def _prune(data: dict, keep_closed: int, key: str = "assignments", open_states: tuple = ("active",)) -> None:
        rows = data.get(key) or []
        closed = [a for a in rows if a.get("status") not in open_states]
        if len(closed) > keep_closed:
            drop = {id(a) for a in closed[:len(closed) - keep_closed]}
            data[key] = [a for a in rows if id(a) not in drop]

    # ------------------------------------------------------------ conditional orders (#32)
    # Stored under `orders`; harness/orders.py holds the logic and Game.run_orders runs them. Status is active or
    # paused (open: the order owns its unit), or completed, cancelled, replaced or failed.
    def orders(self, status: str = "open") -> list[dict]:
        from .orders import OPEN
        rows = [o for o in self._load().get("orders") or [] if isinstance(o, dict)]
        if status == "all":
            return rows
        if status == "open":
            return [o for o in rows if o.get("status") in OPEN]
        if status == "closed":
            return [o for o in rows if o.get("status") not in OPEN]
        return [o for o in rows if o.get("status") == status]

    def add_order(self, record: dict, turn: int, replace_id: int | None = None) -> dict:
        """Store a new active order. One open order per unit: another open order on the same unit refuses unless
        it is the one being replaced (closed as replaced, pointing at the new one)."""
        from .orders import MAX_ACTIVE, MAX_CLOSED, OPEN
        data = self._load()
        rows = data.setdefault("orders", [])
        old = None
        if replace_id is not None:
            old = next((o for o in rows if o.get("id") == replace_id), None)
            if old is None or old.get("status") not in OPEN:
                return {"ok": False, "err": f"no open order {replace_id} to replace",
                        "open_ids": [o.get("id") for o in rows if o.get("status") in OPEN]}
        uid = record["unit"]["id"]
        clash = next((o for o in rows if o.get("status") in OPEN and o is not old and o["unit"]["id"] == uid), None)
        if clash is not None:
            return {"ok": False, "order_id": clash.get("id"),
                    "err": f"unit {uid} already has open order {clash.get('id')}: pass replace_id={clash.get('id')} to "
                           "replace it, or notebook(action='cancel_order') it first (one order owns a unit)"}
        if sum(1 for o in rows if o.get("status") in OPEN) - (1 if old else 0) >= MAX_ACTIVE:
            return {"ok": False, "err": f"{MAX_ACTIVE} open orders already: cancel finished or abandoned ones first"}
        nid = data.get("next_order_id") or (max([o.get("id", 0) for o in rows] + [0]) + 1)
        record = {**record, "id": nid, "status": "active", "step": 0, "created_turn": turn, "updated_turn": turn,
                  "issued_count": 0}
        record.setdefault("history", []).append({"turn": turn, "what": "given" + (f", replacing {replace_id}" if old else "")})
        if old:
            record["replaces"] = replace_id
            old.update({"status": "replaced", "replaced_by": nid, "closed_turn": turn})
            old.setdefault("history", []).append({"turn": turn, "what": f"replaced by {nid}"})
        rows.append(record)
        data["next_order_id"] = nid + 1
        self._prune(data, MAX_CLOSED, "orders", OPEN)
        self._save(data)
        return {"ok": True, "order": record, **({"replaced": replace_id} if old else {}),
                **({"replaced_order": old} if old else {})}

    def put_order(self, order: dict) -> None:
        """Write one order back whole (Game.run_orders changes several fields per step)."""
        from .orders import MAX_CLOSED, OPEN
        data = self._load()
        rows = data.setdefault("orders", [])
        for i, o in enumerate(rows):
            if o.get("id") == order.get("id"):
                hist = order.get("history") or []
                del hist[:-12]
                rows[i] = order
                break
        else:
            rows.append(order)
        self._prune(data, MAX_CLOSED, "orders", OPEN)
        self._save(data)
