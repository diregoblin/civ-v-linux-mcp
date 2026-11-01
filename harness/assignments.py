"""Structured assignments on the notebook (#33): what a unit or city is for, kept per game and seat.

A prose note says why; an assignment also says who, where and when it is done, so a model whose context was
reset can pick the plan up without re-deriving it from coordinates: "Warrior 40962 escorts Settler 57344 to
(71,44); done when a city of mine stands there; review at turn 50". Stored in the seat's notebook file
(harness/notes.py) beside the prose notes, which stay as they were.

Everything here is a pure function of the stored assignments and one runtime read (`H.assignment_facts`), so it
is tested without a game:

- `normalize_*` turns tool arguments into the stored shape and says precisely what is wrong when it cannot.
- `spec` lists every entity the active assignments reference, for the one read.
- `fingerprint` records what an assigned unit or city was when it was assigned (type and creation turn, name
  and founding turn): a later read of the same id that disagrees is a different entity, reported as the
  assigned one being gone, never silently attached.
- `reconcile` compares one assignment with the facts: its entities' current condition, whether its completion
  condition is met, and every reason it needs a look. It reports; it never closes, re-targets or orders.

Foreign targets are fog-safe: the read answers with revealed values under fog and a foreign unit only while in
sight, and `reconcile` keeps the last sighting (`seen`) rather than assuming a target moved, died or stayed.
"""
from __future__ import annotations

from typing import Any

from . import hexgrid
from .notes import ADOPTED

ROLE_MAX = 40
PURPOSE_MAX = 500
NOTE_MAX = 300
MAX_ACTIVE = 40
MAX_CLOSED = 60
MAX_REFS = 8
DONE_KINDS = ("manual", "unit_at", "city_at", "improvement", "building", "tech")
REVIEW_KEYS = ("turn", "hostile_within", "hp_below", "max_distance")
OUTCOMES = ("completed", "cancelled")


class AssignmentError(ValueError):
    """A tool argument that cannot be stored; the message says what to pass instead."""


def _int(v: Any, what: str) -> int:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or int(v) != v:
        raise AssignmentError(f"{what} must be an integer, not {v!r}")
    return int(v)


def _xy(d: dict, what: str) -> tuple[int, int]:
    if "x" not in d or "y" not in d:
        raise AssignmentError(f"{what} needs x and y")
    return _int(d["x"], f"{what}.x"), _int(d["y"], f"{what}.y")


def _type(v: Any, prefix: str, what: str) -> str:
    """'farm' / 'FARM' / 'IMPROVEMENT_FARM' -> 'IMPROVEMENT_FARM' (the game's full type name)."""
    if not isinstance(v, str) or not v.strip():
        raise AssignmentError(f"{what} must be a type name such as {prefix}...")
    s = v.strip().upper().replace(" ", "_")
    return s if s.startswith(prefix) else prefix + s


def short(t: str | None) -> str | None:
    """'IMPROVEMENT_FARM' -> 'FARM', as the runtime's rows spell types."""
    if not t:
        return t
    head, _, rest = t.partition("_")
    return rest if rest and head.isupper() else t


# ------------------------------------------------------------------ input
def normalize_ids(v: Any, what: str) -> list[int]:
    if v is None:
        return []
    if not isinstance(v, (list, tuple)):
        v = [v]
    ids = []
    for x in v:
        i = _int(x, what)
        if i not in ids:
            ids.append(i)
    if len(ids) > MAX_REFS:
        raise AssignmentError(f"at most {MAX_REFS} {what} per assignment")
    return ids


def normalize_target(t: Any) -> dict | None:
    """{x, y} a plot (a site, a city, a tile to improve or hold); {unit_id, owner} a foreign unit;
    {player} another civilization or city-state (a diplomatic reminder)."""
    if t is None or t == {}:
        return None
    if not isinstance(t, dict):
        raise AssignmentError("target must be an object: {x, y}, {unit_id, owner} or {player}")
    if "unit_id" in t:
        if "owner" not in t:
            raise AssignmentError("a unit target needs its owner (player id) as well as unit_id")
        return {"kind": "unit", "id": _int(t["unit_id"], "target.unit_id"), "owner": _int(t["owner"], "target.owner")}
    if "player" in t:
        return {"kind": "player", "id": _int(t["player"], "target.player")}
    if "x" in t or "y" in t:
        x, y = _xy(t, "target")
        return {"kind": "plot", "x": x, "y": y}
    raise AssignmentError("target must be {x, y}, {unit_id, owner} or {player}")


def normalize_done(d: Any, target: dict | None) -> dict:
    """The completion condition, checked on every reconcile. Plot conditions default to the target plot."""
    if d is None or d == {} or d == "manual":
        return {"kind": "manual"}
    if isinstance(d, str):
        d = {"kind": d}
    if not isinstance(d, dict) or d.get("kind") not in DONE_KINDS:
        raise AssignmentError(f"done_when.kind must be one of {list(DONE_KINDS)}")
    kind = d["kind"]
    out: dict = {"kind": kind}
    if kind in ("unit_at", "city_at", "improvement"):
        if "x" in d or "y" in d:
            out["x"], out["y"] = _xy(d, "done_when")
        elif target and target.get("kind") == "plot":
            out["x"], out["y"] = target["x"], target["y"]
        else:
            raise AssignmentError(f"done_when {kind} needs x and y (or a plot target)")
        if kind == "unit_at" and d.get("unit_id") is not None:
            out["unit_id"] = _int(d["unit_id"], "done_when.unit_id")
        if kind == "improvement" and d.get("improvement"):
            out["improvement"] = _type(d["improvement"], "IMPROVEMENT_", "done_when.improvement")
    elif kind == "building":
        out["city_id"] = _int(d.get("city_id"), "done_when.city_id")
        out["building"] = _type(d.get("building"), "BUILDING_", "done_when.building")
    elif kind == "tech":
        out["tech"] = _type(d.get("tech"), "TECH_", "done_when.tech")
    return out


def normalize_review(r: Any) -> dict:
    """When to look again even if nothing went wrong: at a turn, when a visible hostile comes within N plots of
    an assigned unit or city, when an assigned unit's hp drops below a percentage, when an assigned unit stands
    more than N plots from the target plot (0: off its plot -- a garrison)."""
    if r is None:
        return {}
    if not isinstance(r, dict):
        raise AssignmentError(f"review must be an object with any of {list(REVIEW_KEYS)}")
    bad = [k for k in r if k not in REVIEW_KEYS]
    if bad:
        raise AssignmentError(f"unknown review key(s) {bad}; use {list(REVIEW_KEYS)}")
    out = {}
    if r.get("turn") is not None:
        out["turn"] = _int(r["turn"], "review.turn")
    if r.get("hostile_within") is not None:
        out["hostile_within"] = max(1, min(_int(r["hostile_within"], "review.hostile_within"), 6))
    if r.get("hp_below") is not None:
        out["hp_below"] = max(1, min(_int(r["hp_below"], "review.hp_below"), 100))
    if r.get("max_distance") is not None:
        out["max_distance"] = max(0, min(_int(r["max_distance"], "review.max_distance"), 30))
    return out


def clean_text(v: Any, limit: int, what: str, required: bool = False) -> str:
    s = " ".join(str(v or "").split())
    if required and not s:
        raise AssignmentError(f"{what} is required: what this is for, in a sentence")
    if len(s) > limit:
        raise AssignmentError(f"{what} longer than {limit} characters")
    return s


# ------------------------------------------------------------------ the one read
def spec(assignments: list[dict]) -> dict:
    """Every entity the given assignments reference, as H.assignment_facts takes it."""
    units: dict[int, dict] = {}
    cities: dict[int, dict] = {}
    plots: dict[tuple, dict] = {}
    foreign: dict[tuple, dict] = {}
    players: list[int] = []
    techs: list[str] = []
    radius = 0

    def plot(x: int, y: int, site: bool = False) -> None:
        p = plots.setdefault((x, y), {"x": x, "y": y})
        if site:
            p["site"] = True

    for a in assignments:
        for u in a.get("units") or []:
            row = units.setdefault(u["id"], {"id": u["id"]})
            for k in ("type", "created", "x", "y"):
                if u.get(k) is not None:
                    row[k] = u[k]
        for c in a.get("cities") or []:
            cities.setdefault(c["id"], {"id": c["id"]})
            if c.get("x") is not None:
                plot(c["x"], c["y"])     # read only if the city turns out to be gone
        t = a.get("target") or {}
        if t.get("kind") == "plot":
            plot(t["x"], t["y"], site=(a.get("done_when") or {}).get("kind") == "city_at")
        elif t.get("kind") == "unit":
            seen = a.get("seen") or {}
            row = {"owner": t["owner"], "id": t["id"]}
            if seen.get("x") is not None:
                row["x"], row["y"] = seen["x"], seen["y"]
            foreign[(t["owner"], t["id"])] = row
        elif t.get("kind") == "player" and t["id"] not in players:
            players.append(t["id"])
        d = a.get("done_when") or {}
        if d.get("x") is not None:
            plot(d["x"], d["y"], site=d["kind"] == "city_at")
        if d.get("kind") == "building":
            c = cities.setdefault(d["city_id"], {"id": d["city_id"]})
            c.setdefault("buildings", [])
            if d["building"] not in c["buildings"]:
                c["buildings"].append(d["building"])
        if d.get("kind") == "tech" and d["tech"] not in techs:
            techs.append(d["tech"])
        radius = max(radius, (a.get("review") or {}).get("hostile_within") or 0)
    out: dict = {"units": list(units.values()), "cities": list(cities.values()), "plots": list(plots.values())}
    if foreign:
        out["foreign_units"] = list(foreign.values())
    if players:
        out["players"] = players
    if techs:
        out["techs"] = techs
    if radius:
        out["radius"] = radius
    return out


def fingerprint_unit(row: dict) -> dict:
    return {k: row.get(k) for k in ("id", "type", "created", "x", "y") if row.get(k) is not None}


def fingerprint_city(row: dict) -> dict:
    return {k: row.get(k) for k in ("id", "name", "x", "y", "founded") if row.get(k) is not None}


def check_new_refs(unit_ids: list[int], city_ids: list[int], facts: dict) -> tuple[list[dict], list[dict]]:
    """Fingerprints for the entities of a new or amended assignment; every id must be mine now."""
    units, cities, bad = [], [], []
    for i in unit_ids:
        r = (facts.get("units") or {}).get(str(i)) or {}
        if r.get("missing") or not r.get("type"):
            bad.append(f"unit {i}")
        else:
            units.append(fingerprint_unit(r))
    for i in city_ids:
        r = (facts.get("cities") or {}).get(str(i)) or {}
        if r.get("missing") or not r.get("name"):
            bad.append(f"city {i}")
        else:
            cities.append(fingerprint_city(r))
    if bad:
        raise AssignmentError(f"not mine now: {', '.join(bad)} (state(what='units') / state(what='cities') list my ids)")
    return units, cities


# ------------------------------------------------------------------ reconcile
def _unit_now(ref: dict, facts: dict) -> tuple[dict, list[str]]:
    """The assigned unit as it is now, or why it is not there. A same id with a different type or creation
    turn is a different unit: reported gone, never attached."""
    r = (facts.get("units") or {}).get(str(ref["id"])) or {"missing": True}
    reasons: list[str] = []
    label = f"{ref.get('type') or 'unit'} {ref['id']}"
    reused = (not r.get("missing") and ((ref.get("type") and r.get("type") != ref.get("type"))
                                        or (ref.get("created") is not None and r.get("created") is not None
                                            and r.get("created") != ref.get("created"))))
    if r.get("missing") or reused:
        if reused:
            reasons.append(f"{label} is gone: id {ref['id']} now belongs to a {r.get('type')} created turn "
                           f"{r.get('created')}, not the one assigned (created turn {ref.get('created')})")
        else:
            reasons.append(f"{label} is not among my units: killed, captured, disbanded, consumed (a settler that "
                           "founded a city, a great person used, a caravan on its route) or upgraded (new id)")
        for c in r.get("on_last_plot") or []:
            if c.get("upgrade_of"):
                reasons.append(f"a {c.get('type')} ({c.get('id')}), what a {ref.get('type')} upgrades to, stands on its "
                               f"last plot ({ref.get('x')},{ref.get('y')}): notebook(action='amend', args={{unit_ids: [...]}}) to take it over")
        now = {"id": ref["id"], "type": ref.get("type"), "gone": True}
        if ref.get("x") is not None:
            now["last_x"], now["last_y"] = ref["x"], ref["y"]
        return now, reasons
    now = {k: r.get(k) for k in ("id", "type", "x", "y", "hp", "max_hp", "moves") if r.get(k) is not None}
    if r.get("hostile"):
        now["hostile"] = r["hostile"]
    return now, reasons


def _city_now(ref: dict, facts: dict) -> tuple[dict, list[str]]:
    r = (facts.get("cities") or {}).get(str(ref["id"])) or {"missing": True}
    same = (not r.get("missing") and (ref.get("founded") is None or r.get("founded") is None
                                       or r.get("founded") == ref.get("founded"))
            and (ref.get("x") is None or (r.get("x"), r.get("y")) == (ref.get("x"), ref.get("y"))))
    if same:
        now = {k: r.get(k) for k in ("id", "name", "pop", "hp", "max_hp") if r.get(k) is not None}
        if r.get("hostile"):
            now["hostile"] = r["hostile"]
        return now, []
    label = f"{ref.get('name') or 'city'} ({ref['id']})"
    reasons = [f"{label} is no longer my city"]
    p = (facts.get("plots") or {}).get(f"{ref.get('x')},{ref.get('y')}") or {}
    if p.get("vis") == "visible":
        c = p.get("city")
        reasons.append(f"its plot ({ref.get('x')},{ref.get('y')}) is in sight: "
                       + (f"{c.get('name')} held by {c.get('owner_name')}" if c else "no city stands there"))
    elif p.get("vis") == "fogged":
        reasons.append(f"its plot ({ref.get('x')},{ref.get('y')}) is fogged; last seen owner: "
                       f"{p.get('owner_name') or 'none'}")
    return {"id": ref["id"], "name": ref.get("name"), "gone": True}, reasons


def _plot_desc(p: dict) -> dict:
    out = {k: p.get(k) for k in ("vis", "owner_name", "improvement", "pillaged") if p.get(k) is not None}
    if p.get("city"):
        out["city"] = {"name": p["city"].get("name"), "owner": p["city"].get("owner_name")}
    return out


def _target_now(a: dict, facts: dict, turn: int | None, seat: int | None) -> tuple[dict | None, list[str], dict | None]:
    """(target as observed now, review reasons, new `seen` record or None to keep the old one)."""
    t = a.get("target")
    if not t:
        return None, [], None
    seen = a.get("seen") or {}
    reasons: list[str] = []
    if t["kind"] == "plot":
        p = (facts.get("plots") or {}).get(f"{t['x']},{t['y']}") or {}
        now: dict = {"kind": "plot", "x": t["x"], "y": t["y"], **_plot_desc(p)}
        if p.get("vis") != "visible":
            now["known"] = "stale" if p.get("vis") == "fogged" else "unknown"
            if seen.get("turn") is not None:
                now["last_seen_turn"] = seen["turn"]
        was_owner, owner = seen.get("owner_name"), p.get("owner_name")
        if seen and p.get("vis") in ("visible", "fogged") and owner != was_owner:
            reasons.append(f"target plot ({t['x']},{t['y']}) owner changed: {was_owner or 'none'} -> {owner or 'none'}"
                           + (" (last seen, fogged)" if p.get("vis") == "fogged" else ""))
        if p.get("pillaged"):
            reasons.append(f"the {p.get('improvement')} on the target plot is pillaged")
        cw = p.get("city_within_range")
        # The founding range counts my own cities too; only my city on the site itself is the goal reached.
        if cw and not (cw.get("distance") == 0 and cw.get("owner") == seat):
            reasons.append(f"site ({t['x']},{t['y']}): {cw.get('name')} ({cw.get('owner_name')}) stands {cw.get('distance')} "
                           f"plot(s) away; no city can be founded within {p.get('found_range')} of another")
        elif p.get("owner") is not None and p.get("owner") != seat and (a.get("done_when") or {}).get("kind") == "city_at":
            reasons.append(f"site ({t['x']},{t['y']}) is inside {p.get('owner_name')}'s borders: a city cannot be founded there")
        new_seen = None
        if p.get("vis") == "visible":
            new_seen = {"turn": turn, **{k: p.get(k) for k in ("owner_name", "improvement") if p.get(k) is not None}}
            if p.get("city"):
                new_seen["city"] = p["city"].get("name")
        return now, reasons, new_seen
    if t["kind"] == "unit":
        f = (facts.get("foreign_units") or {}).get(f"{t['owner']}:{t['id']}") or {}
        if f.get("in_sight"):
            now = {"kind": "unit", "id": t["id"], "owner": t["owner"], "in_sight": True,
                   **{k: f.get(k) for k in ("type", "x", "y", "hp")}}
            return now, [], {"turn": turn, **{k: f.get(k) for k in ("type", "x", "y", "hp")}}
        now = {"kind": "unit", "id": t["id"], "owner": t["owner"], "in_sight": False, "known": "stale" if seen else "unknown"}
        if seen:
            now["last_seen"] = {k: seen.get(k) for k in ("turn", "type", "x", "y", "hp") if seen.get(k) is not None}
            if f.get("last_plot_visible"):
                reasons.append(f"target unit {t['id']} is not on the plot it was last seen on ({seen.get('x')},{seen.get('y')}); "
                               "where it went (or whether it still exists) is not in sight")
        return now, reasons, None
    # player
    pr = (facts.get("players") or {}).get(str(t["id"])) or {}
    now = {"kind": "player", "id": t["id"], **{k: pr.get(k) for k in ("name", "met", "alive", "at_war") if pr.get(k) is not None}}
    if pr.get("met") and pr.get("alive") is False:
        reasons.append(f"{pr.get('name')} has been eliminated")
    if seen.get("at_war") is not None and pr.get("at_war") is not None and seen["at_war"] != pr["at_war"]:
        reasons.append(f"now {'at war' if pr['at_war'] else 'at peace'} with {pr.get('name')} "
                       f"(was {'at war' if seen['at_war'] else 'at peace'})")
    return now, reasons, {"turn": turn, **{k: pr.get(k) for k in ("name", "at_war", "alive") if pr.get(k) is not None}}


def _done(a: dict, facts: dict, units_now: list[dict], seat: int | None) -> str | None:
    """Evidence that the completion condition holds now, or None."""
    d = a.get("done_when") or {}
    kind = d.get("kind")
    if kind == "unit_at":
        ids = [d["unit_id"]] if d.get("unit_id") is not None else [u["id"] for u in units_now]
        for u in units_now:
            if u["id"] in ids and not u.get("gone") and (u.get("x"), u.get("y")) == (d["x"], d["y"]):
                return f"{u.get('type')} {u['id']} stands on ({d['x']},{d['y']})"
    elif kind == "city_at":
        c = ((facts.get("plots") or {}).get(f"{d['x']},{d['y']}") or {}).get("city")
        if c and c.get("owner") == seat:
            return f"my city {c.get('name')} stands on ({d['x']},{d['y']})"
    elif kind == "improvement":
        p = (facts.get("plots") or {}).get(f"{d['x']},{d['y']}") or {}
        want = short(d.get("improvement"))
        if p.get("vis") == "visible" and p.get("improvement") and not p.get("pillaged") \
                and (want is None or p["improvement"] == want):
            return f"{p['improvement']} on ({d['x']},{d['y']})"
    elif kind == "building":
        c = (facts.get("cities") or {}).get(str(d["city_id"])) or {}
        if (c.get("has") or {}).get(d["building"]):
            return f"{c.get('name')} has {short(d['building'])}"
    elif kind == "tech":
        if (facts.get("techs") or {}).get(d["tech"]):
            return f"{short(d['tech'])} researched"
    return None


def reconcile(a: dict, facts: dict, turn: int | None, seat: int | None) -> tuple[dict, dict]:
    """(row, updates): the assignment as it stands now, and what to store back (the target's latest sighting,
    the assigned units' last plots). `state` is condition_met (the done_when holds: close_assignment it),
    needs_review (every `reasons` line says why) or on_track."""
    units_now, reasons = [], []
    for ref in a.get("units") or []:
        now, why = _unit_now(ref, facts)
        units_now.append(now)
        reasons += why
    cities_now = []
    for ref in a.get("cities") or []:
        now, why = _city_now(ref, facts)
        cities_now.append(now)
        reasons += why
    target_now, why, new_seen = _target_now(a, facts, turn, seat)
    reasons += why
    review = a.get("review") or {}
    t = a.get("target") or {}
    if t.get("kind") == "plot":
        # Every unit row says how far it stands from the target plot; the review flags it only when asked (live
        # Assyria t238: a garrison two plots off its city read on_track with nothing to say so).
        width = facts.get("width") if isinstance(facts.get("width"), int) else None
        for u in units_now:
            if not u.get("gone") and isinstance(u.get("x"), int) and isinstance(u.get("y"), int):
                u["distance"] = hexgrid.distance(u["x"], u["y"], t["x"], t["y"], width)
                if review.get("max_distance") is not None and u["distance"] > review["max_distance"]:
                    reasons.append(f"{u.get('type')} {u['id']} is {u['distance']} plot(s) from its post ({t['x']},{t['y']}), "
                                   f"more than review.max_distance {review['max_distance']}")
    if review.get("turn") is not None and isinstance(turn, int) and turn >= review["turn"]:
        reasons.append(f"review turn {review['turn']} reached")
    if review.get("hostile_within"):
        for e in units_now + cities_now:
            h = e.get("hostile")
            # The read uses the widest radius any assignment asked for; this one's own applies here.
            if h and isinstance(h.get("distance"), int) and h["distance"] <= review["hostile_within"]:
                reasons.append(f"hostile {h.get('unit')} ({h.get('owner')}) {h.get('distance')} plot(s) from "
                               f"{e.get('type') or e.get('name')} {e.get('id')}")
    if review.get("hp_below"):
        for u in units_now:
            if isinstance(u.get("hp"), int) and isinstance(u.get("max_hp"), int) and u["max_hp"] > 0 \
                    and u["hp"] * 100 < review["hp_below"] * u["max_hp"]:
                reasons.append(f"{u.get('type')} {u['id']} at {u['hp']}/{u['max_hp']} hp, below {review['hp_below']}%")
    if a.get("adopted"):
        reasons.append(f"{ADOPTED}: notebook(action='amend') it to keep it, or close it")
    evidence = _done(a, facts, units_now, seat)
    state = "condition_met" if evidence else ("needs_review" if reasons else "on_track")
    row: dict = {"id": a["id"], "role": a.get("role"), "purpose": a.get("purpose"), "state": state,
                 "since_turn": a.get("created_turn")}
    if evidence:
        row["evidence"] = evidence
    if reasons:
        row["reasons"] = reasons
    if units_now:
        row["units"] = units_now
    if cities_now:
        row["cities"] = cities_now
    if target_now:
        row["target"] = target_now
    d = a.get("done_when") or {"kind": "manual"}
    row["done_when"] = d
    if review:
        row["review"] = review
    # Hostile rows are for the reasons line; the entity rows stay short.
    for e in units_now + cities_now:
        e.pop("hostile", None)
    updates: dict = {}
    if new_seen is not None:
        updates["seen"] = new_seen
    moved = []
    for ref, now in zip(a.get("units") or [], units_now):
        if not now.get("gone") and (now.get("x"), now.get("y")) != (ref.get("x"), ref.get("y")):
            moved.append((ref["id"], now.get("x"), now.get("y")))
    if moved:
        updates["unit_plots"] = moved
    return row, updates


def compact(row: dict, purpose_max: int = 160) -> dict:
    """The briefing's row: purpose beside each entity's condition, not the whole record."""
    out = {k: row[k] for k in ("id", "role", "state") if k in row}
    p = row.get("purpose") or ""
    out["purpose"] = p if len(p) <= purpose_max else p[:purpose_max - 3] + "..."
    for k in ("evidence", "reasons"):
        if row.get(k):
            out[k] = row[k]
    if row.get("units"):
        out["units"] = [{k: u[k] for k in ("id", "type", "x", "y", "hp", "distance", "gone") if k in u} for u in row["units"]]
    if row.get("cities"):
        out["cities"] = [{k: c[k] for k in ("id", "name", "gone") if k in c} for c in row["cities"]]
    t = row.get("target")
    if t:
        out["target"] = {k: t[k] for k in ("kind", "x", "y", "id", "name", "in_sight", "known", "owner_name", "city",
                                          "improvement") if k in t}
    return out


STATE_ORDER = {"condition_met": 0, "needs_review": 1, "on_track": 2}


def briefing_section(rows: list[dict], limit: int) -> dict:
    """Active assignments for the briefing: the ones needing a look first; on-track ones fill up to `limit`."""
    rows = sorted(rows, key=lambda r: (STATE_ORDER.get(r.get("state"), 3), r.get("id", 0)))
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["state"]] = counts.get(r["state"], 0) + 1
    out: dict = {"active": len(rows), "by_state": counts, "rows": [compact(r) for r in rows[:max(0, limit)]]}
    if len(rows) > limit:
        out["omitted"] = len(rows) - max(0, limit)
        out["more"] = "notebook(action='assignments') lists every active assignment with its full record"
    return out
