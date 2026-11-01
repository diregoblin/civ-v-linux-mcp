"""High-level Python API over the game (through tunerd). The only module that speaks Lua.

    from harness.game import Game
    g = Game()                    # connects to tunerd (CIV5_TUNERD_SOCK selects the instance)
    g.host_hotseat(human_seats=[0, 1], nicknames={1: "Claude"})   # hotseat: one instance, seats alternate
    g.join_lan("192.168.1.10", nickname="Claude")                  # LAN: this instance is the LLM's own client
    g.wait_ingame(); g.detect_seat()
    g.summary(1); g.units(1); g.cities(1); g.plots_around(x, y, 3)
    g.move_unit(unit_id, x, y); g.end_turn()

The class is assembled from one mixin per domain under harness/game_parts/ (front_end, turn, popups, events,
reads, cities, units, unit_orders, notebook, diplomacy, espionage, deals, policies, trade_routes); this file
keeps the transport (tunerd, the Lua runtime, q) and the helpers every part shares. `self` is always the whole
Game, so a part may call any other part's methods.
"""
from __future__ import annotations

import contextlib
import time
from dataclasses import dataclass, field

from . import lua_wire, runtime_source
from .client import Civ5, TunerdError
from .tuner import TunerClient
from .game_parts.front_end import FrontEndMixin
from .game_parts.turn import TurnMixin
from .game_parts.popups import PopupsMixin
from .game_parts.events import EventsMixin
from .game_parts.reads import ReadsMixin
from .game_parts.cities import CitiesMixin
from .game_parts.units import UnitsMixin
from .game_parts.unit_orders import UnitOrdersMixin
from .game_parts.notebook import NotebookMixin
from .game_parts.diplomacy import DiplomacyMixin
from .game_parts.friendship import FriendshipMixin
from .game_parts.espionage import EspionageMixin
from .game_parts.deals import DealsMixin
from .game_parts.policies import PoliciesMixin
from .game_parts.trade_routes import TradeRoutesMixin
# The public helpers keep their harness.game names (tests and scripts import them from here).
from .game_parts.support import (LUA_DIR, POPUP_SHIM_LUA, RUNTIME_DIGEST, RUNTIME_VERSION, SEAT_SLOTS,  # noqa: F401
                                 lua_str, lua_str_len, lua_table, plain_text, spread_effects)


class LuaCall(str):
    """A named runtime call, `Game.h("tactical_view", 5, 2, pid=1)`: on the wire it is `{"op": "call", "fn":
    "tactical_view", "args": [5, 2]}` and tunerd writes the seat in; as text it reads `return H.tactical_view(5, 1,
    2)`, the Lua the daemon ends up running, which is what a test double of `q` matches on and what the call
    ledger shows. `calls` is set for a batch (`Game.hs`), rendered `return {H.a(...), H.b(...)}`."""
    fn: str | None
    args: list
    calls: list | None

    def __new__(cls, text: str, fn: str | None, args: list, calls: list | None = None):
        self = super().__new__(cls, text)
        self.fn, self.args, self.calls = fn, list(args), calls
        return self


def _h_args(name: str, args: tuple, seat: int) -> list:
    """The argument list as the runtime sees it: `seat` inserted at the entry's slot (SEAT_SLOTS, generated at
    build) or, for an entry on the seat-free list, nothing inserted. A name on neither list is a programming
    error here, not a refusal from the daemon."""
    slot = SEAT_SLOTS.get(name)
    if slot is None:
        if name not in runtime_source.SEAT_FREE:
            raise ValueError(f"H.{name} is not a runtime entry that takes a seat (nor on the seat-free list)")
        return list(args)
    if len(args) < slot - 1:
        raise ValueError(f"H.{name} takes {slot - 1} argument(s) before the seat, got {len(args)}")
    return [*args[:slot - 1], seat, *args[slot - 1:]]


def _h_expr(name: str, args: tuple, seat: int) -> str:
    return f"H.{name}({', '.join(lua_table(a) for a in _h_args(name, args, seat))})"


@dataclass
class Game(FrontEndMixin, TurnMixin, PopupsMixin, EventsMixin, ReadsMixin, CitiesMixin, UnitsMixin,
           UnitOrdersMixin, NotebookMixin, DiplomacyMixin, FriendshipMixin, EspionageMixin, DealsMixin, PoliciesMixin,
           TradeRoutesMixin):
    """One player's hands on the game through tunerd. The fields below are the whole state; everything else
    is a read or an order sent to the Lua runtime (H.*) and read back."""
    sock_path: str | None = None
    c: Civ5 = field(init=False)
    seat: int = 0                       # player id the LLM controls (LAN: detect_seat() = the local player)
    _runtime_ok: bool = field(default=False, init=False)
    _last_event_seq: int = field(default=0, init=False)
    _mode: str | None = field(default=None, init=False)

    # A context-manager factory taken around each operation of the wait loops (one poll, the end-turn,
    # the digest), released while they sleep. The MCP server sets its per-socket action_lock here;
    # the CLI and tests run unlocked.
    lock = contextlib.nullcontext

    # `claim(turn, tool, force) -> dict`, raising turn_claim.ClaimRefused when another client of this seat
    # owns the turn (GitLab #41). The MCP server sets the per-socket, per-seat file claim here; the CLI,
    # the CLI and tests leave it None, and the turn is nobody's to contest.
    claim = None

    def __post_init__(self):
        self.c = Civ5(self.sock_path) if self.sock_path else Civ5()
        if self.c.seat is not None:
            self.seat = self.c.seat   # a seat-bound connection: the daemon's binding is the seat, not a flag

    @property
    def bound_seat(self) -> int | None:
        """The seat tunerd bound this connection to (a daemon with a seat table; "A seat bound to its channel",
        stage 4): the one seat this process may play. None on a daemon without a table, where `seat` is a flag."""
        return getattr(self.c, "seat", None)

    # ------------------------------------------------------------ plumbing
    def states(self) -> dict[int, str]:
        return self.c.states()

    def has_state(self, name: str) -> bool:
        return name in self.c.states().values()

    def lua(self, state: int | str, code: str, timeout: float | None = None) -> list[str]:
        return self.c.exec(state, code, timeout=timeout)

    def h(self, name: str, *args, pid: int | None = None) -> LuaCall:
        """A call of the runtime entry `H.<name>` for this seat: the arguments are the entry's own, without the
        seat, which is inserted at the entry's slot (by the daemon on the wire, here only for the rendering).
        Run it with `q`: `self.q(self.h("tactical_view", unit_id, 2, pid=pid))`."""
        seat = self._pid(pid)
        return LuaCall("return " + _h_expr(name, args, seat), name, list(args))

    def hs(self, calls: list[tuple], pid: int | None = None) -> LuaCall:
        """Several entries in one trip: `calls` is a list of (name, *args); the reply is the list of their values
        in order, holes where one returned nil (a composed `return {H.a(), H.b()}` read the same)."""
        seat = self._pid(pid)
        exprs = [_h_expr(c[0], tuple(c[1:]), seat) for c in calls]
        return LuaCall("return {" + ", ".join(exprs) + "}", None, [], [[c[0], list(c[1:])] for c in calls])

    def q(self, code: str, timeout: float | None = None):
        """Run `code` (must `return` a value) in InGame and get JSON back.

        A `LuaCall` (from `h` / `hs`) goes to tunerd as a named call and the daemon writes the Lua with the
        seat it knows; that is the only shape a seat-bound connection may send to InGame, so free text is
        refused here before the trip. A test double without `call_fn` gets the rendered text through `query`.

        Free text that would not fit inline is shipped in string chunks first: the tuner truncates a
        command at TunerClient.COMMAND_MAX and the game then reports a bare "Syntax Error" quoting
        the cut-off source (live t319, purchase_cost's body plus the query wrapper; again at t193,
        where two lines added to set_production's puppet guard took the wrapped command from 2003
        bytes to 2093). The budget counts the wrapper query() puts around the body, because that is
        what the tuner measures -- a flat body limit is only ever right by luck. The per-call global
        name keeps two clients from interleaving."""
        self.ensure_runtime()
        if isinstance(code, LuaCall) and hasattr(self.c, "call_fn"):
            if code.calls is not None:
                return self.c.calls(code.calls, seat=self.seat, timeout=timeout)
            return self.c.call_fn(code.fn, code.args, seat=self.seat, timeout=timeout)
        if getattr(self.c, "seat", None) is not None:
            raise TunerdError("a seat-bound connection sends named runtime calls (Game.h), not Lua text: "
                              f"{code[:60]!r}")
        if self.q_fits_inline(code):
            return self.c.query("InGame", code, timeout=timeout)
        self._q_seq += 1
        var = f"__H_Q{self._q_seq}_{id(self) % 100000}"
        self.c.exec("InGame", f"{var} = ''")
        for cmd in self.append_commands(var, code):
            self.c.exec("InGame", cmd)
        return self.c.query("InGame", lua_wire.shipped_query(var), timeout=timeout)

    # Headroom under the tuner's command limit for the `CMD:<state>:` framing execute() adds and the
    # trailing NUL, and for a body whose formatted length we measure after substitution.
    Q_MARGIN = lua_wire.Q_MARGIN

    _q_seq = 0

    @classmethod
    def q_inline_max(cls) -> int:
        """Largest *ASCII* body that still fits inline: a character estimate for source-level checks.
        The live decision is `q_fits_inline`, which measures encoded bytes."""
        return TunerClient.COMMAND_MAX - TunerClient.query_overhead() - cls.Q_MARGIN

    # The chunking lives in harness/lua_wire.py (tunerd ships a long call the same way); these names stay
    # for the callers and tests that know them here.
    command_budget = staticmethod(lua_wire.command_budget)
    q_fits_inline = staticmethod(lua_wire.query_fits_inline)
    string_chunks = staticmethod(lua_wire.string_chunks)
    append_commands = staticmethod(lua_wire.append_commands)

    def _order(self, code: str, tries: int = 6, delay: float = 0.2):
        """Run a unit order that goes through the selection list (harness/lua/runtime/helpers.lua net_unit_message).

        The Lua side selects the unit and, when the selection has not landed yet in the same call,
        answers `select_pending`; re-issue the identical call once the engine has had a frame."""
        r = self.q(code)
        n = 0
        while isinstance(r, dict) and r.get("select_pending") and n < tries:
            n += 1
            time.sleep(delay)
            r = self.q(code)
        if isinstance(r, dict) and r.get("select_pending"):
            r = dict(r, err="could not select the unit for the order (UI.GetHeadSelectedUnit never became it)")
        return r

    # The tuner truncates a command at COMMAND_MAX bytes, so big sources are shipped in escaped
    # string chunks into a global and compiled with loadstring(). See `string_chunks`.

    def ship_string(self, state: int | str, src: str) -> str:
        """Put `src` into a fresh global of `state`, in escaped byte-budgeted pieces; returns the global's name.
        The caller consumes and clears it (load_lua, the runtime installer)."""
        # A per-load global: two processes reloading a bumped runtime at once (live t394, et.sh's wait loop and
        # a direct call) shared __H_SRC -- one reset it mid-way and the other's append failed on a nil global.
        # The counter keeps two strings of one load apart (the runtime text and its installer).
        import os
        self._ship_seq = getattr(self, "_ship_seq", 0) + 1
        var = f"__H_SRC_{os.getpid()}_{id(self) % 100000}_{self._ship_seq}"
        self.c.exec(state, f"{var} = ''")
        for cmd in self.append_commands(var, src):
            self.c.exec(state, cmd)
        return var

    def load_lua(self, state: int | str, src: str, name: str = "chunk") -> None:
        var = self.ship_string(state, src)
        self.c.exec(state, f"local f, err = loadstring({var}, {lua_str(name)}); {var} = nil; "
                           f"if not f then error(err, 0) end; f()", timeout=30)

    def ensure_runtime(self, force: bool = False) -> None:
        if self._runtime_ok and not force:
            return
        if getattr(self.c, "seat", None) is not None:
            # A seat-bound connection ships no Lua: tunerd installs the runtime (and the popup shim) itself,
            # from the source on disk, and is the one installer for every client of the game.
            self.c.runtime(force=force)
            self._runtime_ok = True
            self._popup_shim_ok = True
            return
        src = runtime_source.snapshot()
        # A truncated/failed earlier injection leaves a partial H behind with no source_hash: the hash is set
        # by the last line of the chunk, so it is only there when every definition ran. A changed source
        # (any fragment) has another digest and reloads even when RUNTIME_VERSION was not bumped.
        if not force:
            out = self.c.exec("InGame", f"print(type(H) == 'table' and H.source_hash == '{src.digest}' and type(H.turn_state) == 'function')")
            if out and out[0] == "true":
                self._runtime_ok = True
                return
        self._runtime_ok = False   # not current until every chunk has run: a failed force-reload retries
        var = self.ship_string("InGame", src.text)
        self.load_lua("InGame", src.install_lua(var), "harness_runtime_install")   # errors read `events.lua:57:`
        self._runtime_ok = True
        self._popup_shim_ok = False
        self.ensure_popup_shim()

    def _wait_until(self, pred, timeout: float, poll: float = 0.25) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if pred():
                return True
            time.sleep(poll)
        return bool(pred())

    def _settle(self, read, done, timeout: float = 3.0, poll: float = 0.25, initial=None):
        """Sleep `poll` seconds, then `read()`, until `done(value)` or `timeout` seconds pass. The engine
        applies most orders asynchronously (a net message), so a tool reads back what changed instead of
        trusting the send. Returns (last_value, settled): the last reading is reported as-is, never
        guessed at, and `initial` stands in for a reading that never happened. The first read waits one
        poll on purpose: a read at t=0 is a tuner trip that almost always shows the pre-order state."""
        deadline = time.monotonic() + timeout
        value = initial
        while time.monotonic() < deadline:
            time.sleep(poll)
            value = read()
            if done(value):
                return value, True
        return value, False

    # ------------------------------------------------------------ misc
    def _pid(self, pid: int | None) -> int:
        return self.seat if pid is None else pid
