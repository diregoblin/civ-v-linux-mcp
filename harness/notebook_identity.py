"""Which notebook is this game's (GitLab #168).

A seat's notebook (harness/notes.py) is one file beside the game, named by a key every save of the game shares
and no other game does. Until runtime v330 the key was built from labels a new game reuses -- leader, civ, map
script, the capital's name and the turn it was founded -- so a fresh Maya hotseat game that founded Palenque on
turn 0 opened the previous Maya game's notebook: its notes, a garrison assignment on Warrior 16385 (the same id,
type and creation turn in both games) and a standing order that ran on turn 1 against Worker 40960, an id the new
game handed to its own Worker on turn 20.

The key now ends in the game's identity. The engine names no game id a seat can read: the map and sync seeds of
the debug menu (Network.GetMapRandSeed / GetSynchRandSeed) live in the network layer and were never seen to survive
a reload. The identity is the digest of facts fixed when the map is made and kept in the save (H.game_key_facts):
the seat's own starting plot, the civilization in every major slot and the city-state in every minor slot. Two
games set up alike on a generated map start the seat on different plots; every save of one game reads the same
facts. The capital is no longer part of the key, so the key does not change at the founding either (GitLab #159).

A notebook written under the label key is adopted once, by the game that first opens its identity's notebook, and
only when that game is past its start turn: a seat's first briefing or finish opens the notebook, so a game the
harness plays is first seen on its start turn, and a label-keyed file it finds then can only be an older game's. A game under
way when the harness was upgraded takes its own file over -- also when the file runs past the turn on screen, a
save loaded back (#62: the live Assyria notebook held notes to t278 at t239). What is adopted is quarantined:
every note and active assignment is marked `adopted` until the seat rewrites, amends or closes it, every open
standing order is paused (kind `adopted`: only resume_order runs it), and the briefing baseline and the server's
memo are dropped. Either way the identity's file is written at that first look, so the decision is made once and
a label-keyed file never reaches a game that already has its own notebook.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .notes import ADOPTED, Notebook, notes_dir, safe_key


#: What the map part of every key written before runtime v285 began with: the inline snippet's pattern lost
#: its backslash in transit, so the map was the script's whole path (`Assets\\Maps\\pangaea.lua` ->
#: `Assets_Maps_pangaea`); the runtime file ships the pattern intact and the key says `pangaea`.
LEGACY_MAP_PREFIX = "Assets_Maps_"



def identity(info: dict) -> str:
    """`g` + a digest of the runtime's identity facts, or "" when the read had none (no starting plot)."""
    raw = str(info.get("identity") or "")
    return "g" + hashlib.sha1(raw.encode()).hexdigest()[:10] if raw else ""


def game_keys(info: dict) -> dict:
    """`{key, identified, legacy}` from the runtime's facts (H.game_key_facts). `key` is game name, leader, civ, map
    script, start turn and the identity; `identified` says the identity was there (the key is cached then).
    `legacy` lists the label keys of the same seat written before #168, newest form first: the capital's key and,
    for a named map, its pre-v285 form (LEGACY_MAP_PREFIX). Empty while the seat has no capital: a label key with no
    capital is shared by every game of that leader, civ and map. A Random-map game says `random` where the script's
    name stood before runtime v289 (that name was the leak of GitLab #119): `pattern` is then the label key with the
    map part a wildcard."""
    head = [str(info.get("name") or ""), f"L{info.get('leader')}", f"C{info.get('civ')}"]
    m = str(info.get("map") or "")
    gid = identity(info)
    out: dict = {"key": "-".join(x for x in [*head, m, f"s{info.get('start')}", gid] if x),
                 "identified": bool(gid), "legacy": []}
    cap = str(info.get("cap") or "")
    if not cap:
        return out

    def label(map_part: str) -> str:
        return "-".join(x for x in [*head, map_part, cap, f"t{info.get('founded')}", f"s{info.get('start')}"] if x)
    out["legacy"].append(label(m))
    if m and m != "random" and not m.startswith(LEGACY_MAP_PREFIX):
        out["legacy"].append(label(LEGACY_MAP_PREFIX + m))
    if m == "random":
        out["pattern"] = label("*")
    return out


def _legacy_file(keys: dict, seat: int, own: Path) -> Path | None:
    """The label-keyed file of this seat, if any: the first legacy key with a file, else the newest file matching
    the Random-map pattern."""
    for k in keys.get("legacy") or []:
        p = notes_dir() / f"{safe_key(f'{k}-seat{seat}')}.json"
        if p.exists():
            return p
    pattern = keys.get("pattern")
    if pattern:
        glob = "*".join(safe_key(part) if part else "" for part in f"{pattern}-seat{seat}".split("*"))
        found = [p for p in notes_dir().glob(f"{glob}.json") if p != own]
        if found:
            return max(found, key=lambda p: p.stat().st_mtime)
    return None


def foreign(turn, start) -> str | None:
    """Why a label-keyed notebook cannot be taken for this game's, or None."""
    if not isinstance(turn, int):
        return "the turn on screen is unknown"
    if isinstance(start, int) and turn <= start:
        return (f"the game is on its start turn {turn}: a new game, and a notebook keyed by leader, civ, map and "
                "capital is an older game's")
    return None


def quarantine(data: dict, source: str, turn: int) -> dict:
    """`data` as this game's notebook takes it over: nothing in it is trusted to be this game's. Notes and active
    assignments are marked `adopted`; open standing orders are paused (kind `adopted`); the briefing baseline and
    the memo go."""
    from .orders import OPEN
    for n in data.get("notes") or []:
        if isinstance(n, dict):
            n["adopted"] = True
    for a in data.get("assignments") or []:
        if isinstance(a, dict) and a.get("status") == "active":
            a["adopted"] = True
    for o in data.get("orders") or []:
        if isinstance(o, dict) and o.get("status") in OPEN:
            o["status"] = "paused"
            o["pause"] = {"kind": "adopted", "turn": turn, "reason": ADOPTED,
                          "hint": "check the unit is the one meant, then notebook(action='resume_order'); "
                                  "otherwise notebook(action='cancel_order')"}
            o.setdefault("history", []).append({"turn": turn, "what": f"paused: adopted from {source}"})
    data.pop("briefing", None)
    data.pop("memo", None)
    data["adopted"] = {"from": source, "turn": turn}
    return data


def open_notebook(nb: Notebook, keys: dict, seat: int, turn, start) -> dict:
    """The first look at this identity's notebook (only when `nb` has no file yet): adopt the seat's label-keyed
    file, quarantined, when nothing says it is another game's (`foreign`), and remove it; otherwise leave it where it
    is. Either way `nb` gets its file now. Returns {adopted: source} | {declined: source, why} | {}."""
    if nb.exists():
        return {}
    found = _legacy_file(keys, seat, nb.path)
    data = None
    out: dict = {}
    if found is not None:
        try:
            old = json.loads(found.read_text())
        except (OSError, ValueError):
            old = None
        if isinstance(old, dict):
            why = foreign(turn, start)
            if why:
                out = {"declined": found.stem, "why": why}
            else:
                data = quarantine(old, found.stem, turn)
                out = {"adopted": found.stem}
    nb.create(data)
    if data is not None:
        found.unlink(missing_ok=True)
    return out
