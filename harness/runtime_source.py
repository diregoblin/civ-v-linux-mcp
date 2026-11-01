"""The Lua runtime's source: ordered fragments under harness/lua/runtime/, and the Lua that installs them
(GitLab #42).

The runtime used to be one 11.5k-line runtime.lua. It is now a file per game domain, each compiled as its own
named chunk inside the game: a Lua error reads `events.lua:57:`, and the Lua 5.1 compiler limits (200 locals
and 60 upvalues per function) apply per file, not to the whole runtime. What a fragment shares with later
fragments (L, short, info_type, own_active_unit, the network-command helpers, ...) goes through `H._ns`: the
owner exports `H._ns.short = short` at its end, the consumer imports `local short = H._ns.short` at its top,
and MANIFEST is the load ORDER as well as the file list, because an import must run after its export. Nothing
else may be read as a global but the game's API, Lua's builtins and H; tests/test_runtime_source.py checks that
mechanically.

Fragments are joined with a comment line naming the file (`-- @@ events.lua`) into one text that is shipped
to the game and hashed as is; install_lua() is the small Lua driver that cuts that text back into chunks by
byte offset, runs them in order and sets H.source_hash last. game.py compares that hash with the digest of the
source it has, so editing any fragment (or renaming one, or reordering MANIFEST) re-injects the runtime whether
or not RUNTIME_VERSION was bumped. RUNTIME_VERSION itself lives in bootstrap.lua and still goes up with every
runtime change (CHANGELOG.md, #26): a stale MCP server re-injects the version it started with, and the number
is what a live session can read back.

Production and tests both load through snapshot() and install_lua(): there is no second, hand-maintained
monolith. One snapshot is one read of every file, and its digest and its text agree by construction.
"""
from __future__ import annotations

import hashlib
import pathlib
import re
from dataclasses import dataclass, field

RUNTIME_DIR = pathlib.Path(__file__).with_name("lua") / "runtime"

# Load order. A fragment may use the H.* functions of any other (looked up at call time) but only the top-level
# locals of the fragments ABOVE it. The comments name the shared locals a fragment declares for later ones.
MANIFEST: tuple[str, ...] = (
    "bootstrap.lua",          # RUNTIME_VERSION; replaces H, carrying over the allowlist of accumulated state
    "json.lua",               # H.json / H.emit; local esc
    "helpers.lua",            # shared locals: L (also H.L), info_type, short, own_active_unit, info_id, move_denom,
                              #   require_revealed_plot, selected_is, net_unit_message, push_mission, do_command
    "builds.lua",             # a plot build's state: build_turns_left, plot_under_construction, unit_build, dig_sites
    "events.lua",             # event recorder: H.record, cursors, capture attribution, rosters, hp snapshots,
                              #   H.install_hooks (called from install.lua)
    "empire.lua",             # player summary, resources, happiness, gold/science/culture/tourism/faith breakdowns,
                              #   ideology switch; shared locals: plain_text, plain_key
    "units.lua",              # unit list, unit supply, idle trade units and spies, promotions
    "city_views.lua",         # city list and city screen: yields, meters, specialists, hovers
    "city_actions.lua",       # citizen management, plot purchase, annex/raze, sell building; the puppet guards;
                              #   shared local: own_city
    "map.lua",                # plots, the fog cache of remembered features, revealed map and its index, known world
    "diplomacy.lua",          # relationship view
    "policies.lua",           # social policy screen
    "notifications.lua",      # pending notifications
    "diplomacy_actions.lua",  # met-civ list with war/peace facts, enum-name cache (H.enum_name), discussion events
    "city_strikes.lua",       # city ranged attacks, units on a plot
    "unit_orders.lua",        # promotion, upgrade, disband
    "successors.lua",         # the unit that replaced one of mine under a new id (a ruins upgrade during a move)
    "choices.lua",            # popup choosers: steal tech, policy, free great person, goody hut, ideology, Maya, archaeology
    "religion.lua",           # religion overview, faith purchases, beliefs, pantheon and religion founding
    "deals.lua",              # deal items and catalogs, incoming/current deals, peace and third-party catalogs, vote gate
    "war.lua",                # city-capture popup and the consequences of a war declaration
    "city_states.lua",        # quests, gifts, influence actions, tile-improvement gifts, tribute
    "trade_routes.lua",       # route options, yields, paths, establishment and plunder
    "league.lua",             # World Congress: proposals, votes, projects
    "overviews.lua",          # victory progress, global relations, wonders, intrigue, demographics, great works
    "espionage.lua",          # spies, potential and catch modifiers, coups
    "research.lua",           # tech tree, tech unlocks, research choice
    "production.lua",         # production choices
    "great_people.lua",       # Great Person yields, the class missions the engine withholds and why, concert-tour preview
    "unit_actions.lua",       # legal actions and missions per unit, action help, todo_actions
    "combat.lua",             # melee defender and peaceful-occupant facts, combat modifier rows (cm_*), city strike modifiers
    "combat_previews.lua",    # melee and ranged previews and targets, air strikes, interception, attack before/after
    "step_cost.lua",          # what one step to a neighbour costs a unit, zone of control included (#180);
                              #   shared local: step_costs
    "tactical.lua",           # activity names, unit_pos, explore frontier, tactical view
    "movement.lua",           # move_unit / move_refusal, standing moves, unit missions, automate and build checks
    "turn.lua",               # popups, blockers, todo, turn_state, expiring deals, notification log, net players
    "victory.lua",            # culture overview, spaceship status
    "reference.lua",          # the rule book: static database reads
    "briefing.lua",           # briefing board
    "assignments.lua",        # assignment facts
    "comparisons.lua",        # compare_* reads (#34)
    "dispatch.lua",           # H._call: the daemon's entry, inserts the bound seat at the entry's slot
    "install.lua",            # runs last: H.install_hooks()
)

MARKER = "-- @@ "                        # boundary line in the assembled text: "-- @@ events.lua"
PRELUDE = "if H then H.version = -1 end\n"   # a changed source reloads even without a version bump
_VERSION_RE = re.compile(r"^local RUNTIME_VERSION = (\d+)$", re.MULTILINE)
_FN_RE = re.compile(r"^function H\.([A-Za-z0-9_]+)\s*\(([^)]*)\)", re.MULTILINE)

# The seat parameter: an entry that takes the acting seat names it `pid`, and tunerd's `call` op inserts the
# connection's seat there (dispatch.lua). The stage-2 survey (docs/GAPS.md, scripts/seat_survey.py) is what
# says every `pid` is the acting seat and never a caller-chosen player in that role.
SEAT_PARAM = "pid"

# Entries with no seat that a client may still call: static tables and facts of the game as a whole, with
# no player in them. Everything else without a `pid` is internal (takes a game object, or a team the caller
# chose) and H._call refuses it. tests/test_runtime_source.py checks the Python side names nothing outside
# this list and the slot table.
SEAT_FREE: tuple[str, ...] = (
    "reference",         # the rule book
    "blocking_name", "blocking_hint", "modal_flags", "hand_off_up",   # UI-state probes of the active screen
    "game_facts",        # turn, game over, the active player: what the screen shows anyone
    "human_seats",       # which seats the engine runs as humans (seat detection)
    "info_types",        # the Type column of a GameInfo table
    "resolution_decision",
    "research_agreement_cost",
    "event_seq_now",     # the recorder's cursor (H.events_since takes the seat)
    "route_start_rows",
)


def seat_slots(fragments: tuple["Fragment", ...]) -> dict[str, int]:
    """name -> 1-based position of the `pid` parameter, for every `function H.<name>(...)` that has one."""
    out: dict[str, int] = {}
    for f in fragments:
        for m in _FN_RE.finditer(f.text):
            params = [p.strip() for p in m.group(2).split(",") if p.strip()]
            if SEAT_PARAM in params:
                out[m.group(1)] = params.index(SEAT_PARAM) + 1
    return out


def entry_names(fragments: tuple["Fragment", ...]) -> set[str]:
    return {m.group(1) for f in fragments for m in _FN_RE.finditer(f.text)}


class RuntimeSourceError(RuntimeError):
    """The runtime source cannot be assembled (a manifest entry is missing, or bootstrap has no version)."""


@dataclass(frozen=True)
class Fragment:
    name: str
    path: pathlib.Path
    text: str      # the file as read (UTF-8), normalised to end with exactly one newline

    @property
    def lines(self) -> int:
        return self.text.count("\n")


@dataclass(frozen=True)
class RuntimeSource:
    """One read of every fragment: the assembled text, its digest and version, and the line map."""
    fragments: tuple[Fragment, ...]
    text: str        # the assembled chunk: what is hashed, and what runs (inside install_chunk())
    digest: str      # sha256 of text
    version: int     # RUNTIME_VERSION from bootstrap.lua
    slots: dict[str, int] = field(default_factory=dict)   # seat_slots(fragments): H._seat_slot as shipped

    def fragment(self, name: str) -> Fragment:
        for f in self.fragments:
            if f.name == name:
                return f
        raise KeyError(name)

    def chunks(self) -> list[tuple[str, int, int]]:
        """The loadstring() chunks of `text`, one per fragment, as (name, first byte, last byte), 1-based and
        inclusive as Lua's string.sub takes them. A chunk is the fragment's body without the marker line, so an
        error's line is the file's own line."""
        out, pos = [], 0
        for f in self.fragments:
            marker = len(f"{MARKER}{f.name}\n".encode())
            start, end = pos + marker, pos + marker + len(f.text.encode("utf-8"))   # body bytes [start, end)
            out.append((f.name, start + 1, end))
            pos = end + 1                                                             # the separating newline
        return out

    def install_lua(self, var: str) -> str:
        """The Lua that installs the runtime from the assembled text held in the global `var` (and clears it):
        force a reload, run every fragment in order as its own chunk, mark the source current last. A chunk
        returning true (bootstrap, when this version is already installed) stops the install. Runs unchanged
        in the game (Lua 5.1) and in the tests (5.4 / lupa).

        The chunk name is the bare file name. The game's Lua prints a chunk name verbatim (live t53, runtime
        v241: a "=map.lua" chunk read `=map.lua:1:`, an "@" one kept its "@"), so the bare name is what makes
        an error read `map.lua:1:` there; stock Lua, which the tests run, shows the same chunk as
        `[string "map.lua"]:1:`."""
        spans = ", ".join(f'{{"{name}", {a}, {b}}}' for name, a, b in self.chunks())
        return (f"local src = {var}; {var} = nil\n"
                "local loadstring = loadstring or load\n"
                f"{PRELUDE}"
                f"for _, c in ipairs({{ {spans} }}) do\n"
                '  local f, err = loadstring(string.sub(src, c[2], c[3]), c[1])\n'
                "  if not f then error(err, 0) end\n"
                "  if f() == true then return end\n"
                "end\n"
                f"{self.seat_tables_lua()}"
                f"H.source_hash = '{self.digest}'\n")

    def seat_tables_lua(self) -> str:
        """`H._seat_slot` and `H._seat_free` (dispatch.lua), generated from the fragments: part of the installer,
        not of the hashed text, since they are a function of it."""
        slot = ", ".join(f'["{k}"]={v}' for k, v in sorted(self.slots.items()))
        free = ", ".join(f'["{k}"]=true' for k in SEAT_FREE)
        return f"H._seat_slot = {{{slot}}}\nH._seat_free = {{{free}}}\n"


def read_fragments(directory: pathlib.Path | None = None, manifest: tuple[str, ...] | None = None) -> tuple[Fragment, ...]:
    """Every manifest entry, in order. Fails before anything is read when one is missing."""
    directory = RUNTIME_DIR if directory is None else directory
    manifest = MANIFEST if manifest is None else manifest
    missing = [name for name in manifest if not (directory / name).is_file()]
    if missing:
        raise RuntimeSourceError(
            f"runtime source incomplete: {', '.join(missing)} missing under {directory} "
            f"(harness/runtime_source.py MANIFEST lists {len(manifest)} fragments)")
    out = []
    for name in manifest:
        text = (directory / name).read_text(encoding="utf-8")
        out.append(Fragment(name, directory / name, text.rstrip("\n") + "\n"))
    return tuple(out)


def assemble(fragments: tuple[Fragment, ...]) -> str:
    return "\n".join(f"{MARKER}{f.name}\n{f.text}" for f in fragments)


def snapshot(directory: pathlib.Path | None = None, manifest: tuple[str, ...] | None = None) -> RuntimeSource:
    """One read of the runtime source (RUNTIME_DIR and MANIFEST unless given: tests point at a copy)."""
    fragments = read_fragments(directory, manifest)
    text = assemble(fragments)
    m = _VERSION_RE.search(fragments[0].text)
    if not m:
        raise RuntimeSourceError(f"{fragments[0].name} declares no `local RUNTIME_VERSION = N`")
    return RuntimeSource(fragments, text, hashlib.sha256(text.encode("utf-8")).hexdigest(), int(m.group(1)),
                         seat_slots(fragments))
