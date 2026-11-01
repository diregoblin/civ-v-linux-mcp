"""Units: movement with its attack and interception previews, missions, promotions, upgrades, the per-unit action reads."""
from __future__ import annotations

from .. import affordances as A

import difflib
import re
import threading
import time

from ..client import TunerdError

from . import combat_result as CR
from .support import ROUTINE_ACTIONS, TODO_DETAIL_LEVELS, _summary_unit_row, spread_effects

# Every MissionTypes name of stock Brave New World, for the nearest-name hint on an unknown mission (live
# 2026-10-03, Codex t45: a guessed MISSION_FORTIFY_HEAL got the bare "unknown mission" and the whole batch
# stopped at it; MISSION_HEAL was the order meant). The unit's own legal list is tried first.
KNOWN_MISSIONS = (
    "MISSION_MOVE_TO", "MISSION_ROUTE_TO", "MISSION_MOVE_TO_UNIT", "MISSION_SKIP",
    "MISSION_SLEEP", "MISSION_ALERT", "MISSION_FORTIFY", "MISSION_GARRISON", "MISSION_SET_UP_FOR_RANGED_ATTACK",
    "MISSION_EMBARK", "MISSION_DISEMBARK", "MISSION_AIRPATROL", "MISSION_HEAL", "MISSION_AIRLIFT", "MISSION_NUKE",
    "MISSION_PARADROP", "MISSION_AIR_ATTACK", "MISSION_RANGE_ATTACK", "MISSION_PILLAGE", "MISSION_FOUND",
    "MISSION_JOIN", "MISSION_CONSTRUCT", "MISSION_DISCOVER", "MISSION_HURRY", "MISSION_TRADE",
    "MISSION_BUY_CITY_STATE", "MISSION_REPAIR_FLEET", "MISSION_SPACESHIP", "MISSION_CULTURE_BOMB",
    "MISSION_FOUND_RELIGION", "MISSION_GOLDEN_AGE", "MISSION_BUILD", "MISSION_LEAD", "MISSION_REBASE",
    "MISSION_SPREAD_RELIGION", "MISSION_REMOVE_HERESY", "MISSION_ESTABLISH_TRADE_ROUTE",
    "MISSION_PLUNDER_TRADE_ROUTE", "MISSION_CREATE_GREAT_WORK", "MISSION_CHANGE_TRADE_UNIT_HOME_CITY",
    "MISSION_SELL_EXOTIC_GOODS", "MISSION_GIVE_POLICIES", "MISSION_ONE_SHOT_TOURISM",
    "MISSION_CHANGE_ADMIRAL_PORT", "AUTOMATE_EXPLORE", "AUTOMATE_BUILD", "COMMAND_DELETE", "COMMAND_WAKE",
)

# An order goes out as a net message and is applied on the next game frame: a read that follows the push by one
# tuner trip already shows it (live t151: MISSION_SKIP and AUTOMATE_BUILD, six pushes, 43-60 ms each). One short
# wait covers a frame that runs long; the 0.2-0.25 s it used to be was most of a plain order's time.
AFTER_READ_DELAY = 0.05
# Great Person missions that spend the unit in one go: afterwards the unit is gone, or nothing happened.
ONE_SHOT_GP_MISSIONS = frozenset({"MISSION_ONE_SHOT_TOURISM", "MISSION_GIVE_POLICIES", "MISSION_GOLDEN_AGE",
                                  "MISSION_TRADE", "MISSION_DISCOVER", "MISSION_HURRY", "MISSION_BUY_CITY_STATE",
                                  "MISSION_REPAIR_FLEET"})


def _automate_landed(chk) -> bool:
    return isinstance(chk, dict) and bool(chk.get("automated") or chk.get("gone"))


# `do` turns this on for the length of a batch, in the thread that runs its orders: a unit order then answers an
# `after_pending` marker (unit_id, mission, kind) instead of spending its own tuner trip on the read-back that
# follows every mission, and the batch reads every such unit in one query at its end (read_after_batch).
# Thread-local so a lone order served on another thread meanwhile still reads its unit back itself.
_DEFER = threading.local()


def defer_after_reads(on: bool) -> None:
    _DEFER.on = bool(on)


def deferring_after_reads() -> bool:
    return bool(getattr(_DEFER, "on", False))



def found_refusal(pre: dict) -> str:
    """Why MISSION_FOUND is refused here, from H.found_check's reasons (live Assyria t24: (19,28) read "too close to
    another city, water, or foreign territory" when Assur stood three plots away and cities need four)."""
    why = []
    nc = pre.get("nearest_city")
    if isinstance(nc, dict):
        need = pre.get("min_distance")
        who = f"{nc['name']} ({nc.get('owner')})" if nc.get("name") and nc.get("owner") not in (None, "you") else nc.get("name") or "a city"
        why.append(f"{who} is {nc.get('distance')} plot(s) away" + (f" and cities need {need}" if need else ""))
    if pre.get("water"):
        why.append("the plot is water")
    if pre.get("foreign_owner"):
        why.append(f"the plot belongs to {pre['foreign_owner']}")
    if not why:
        return "cannot found a city on this plot (too close to another city, water, or foreign territory); move first"
    return "cannot found a city on this plot: " + "; ".join(why) + "; move first"



def _offer_map_window(pos: dict) -> None:
    """A move that uncovered ground carries the read of that ground (GitLab #153): `revealed.map` is the map window
    around the unit's new plot, not the plots themselves."""
    rev = pos.get("revealed")
    if isinstance(rev, dict) and (rev.get("count") or 0) > 0 and pos.get("x") is not None:
        from .. import affordances as A
        rev["map"] = A.act("map_window", x=pos["x"], y=pos["y"], radius=3)

class UnitsMixin:
    """Units: movement with its attack and interception previews, missions, promotions, upgrades, the per-unit action reads.

    A part of harness.game.Game (see harness/game_parts/__init__.py); `self` is the whole Game."""

    # ------------------------------------------------------------ actions
    HOLDS = ("fortify", "sleep", "alert", "hold")

    def move_unit(self, unit_id: int, x: int, y: int, pid: int | None = None, settle_timeout: float = 1.0,
                  then: str | None = None) -> dict:
        """move-to; when a visible enemy stands on the destination the move is a melee attack, and the
        result carries `attack`: both sides' hp before/after and who died (the unit's x/y do not change
        on an attack unless it kills and advances, so a bare move result read like nothing happened --
        live 2026-09-18). `then` (GitLab #105): fortify / sleep / alert / hold once there -- this turn when the
        unit arrives with moves left, else the turn it arrives (or the next turn start when it arrived with none):
        one order for "go there and hold", and the unit does not block the finish on arrival."""
        if then is not None and then not in self.HOLDS:
            return {"ok": False, "err": f"then must be one of {list(self.HOLDS)}, not {then!r}"}
        r = self._with_attack_result(
            unit_id, x, y, lambda: self._move_unit(unit_id, x, y, pid, settle_timeout), pid)
        if then is None or not isinstance(r, dict) or not r.get("ok") or r.get("attack"):
            return r
        return self._then_hold(r, unit_id, then, pid)

    def _then_hold(self, r: dict, unit_id: int, then: str, pid: int | None) -> dict:
        """The hold after a move: now when the unit stands there with moves left, else recorded on the standing
        move so the turn start that finds it there (or lets it arrive) gives it."""
        mission = {"fortify": "MISSION_FORTIFY", "hold": "MISSION_FORTIFY", "sleep": "MISSION_SLEEP", "alert": "MISSION_ALERT"}[then]
        if r.get("arrived") and (r.get("moves") or 0) > 0:
            hold = self.unit_mission(unit_id, mission, pid=pid)
            if not hold.get("ok") and mission != "MISSION_SLEEP" and "MISSION_SLEEP" in (hold.get("legal_missions") or []):
                hold = self.unit_mission(unit_id, "MISSION_SLEEP", pid=pid)
                mission = "MISSION_SLEEP"
            elif not hold.get("ok") and mission == "MISSION_SLEEP" and "MISSION_FORTIFY" in (hold.get("legal_missions") or []):
                hold = self.unit_mission(unit_id, "MISSION_FORTIFY", pid=pid)
                mission = "MISSION_FORTIFY"
            r["then"] = {"mission": mission, "ok": bool(hold.get("ok")), "when": "now"}
            if not hold.get("ok"):
                r["then"]["err"] = hold.get("err")
            return r
        try:
            rec = self.q(self.h("set_pending_then", int(unit_id), then, pid=pid))
        except TunerdError as e:
            r["then"] = {"mission": mission, "ok": False, "err": str(e)}
            return r
        when = "on arrival (the turn start that lets it arrive)" if not r.get("arrived") else "next turn start (it arrived with no moves left; a hold at 0 moves is a one-turn HOLD the engine forgets)"
        r["then"] = {"mission": mission, "ok": bool(isinstance(rec, dict) and rec.get("ok")), "when": when}
        return r

    def _remote_build(self, unit_id: int, build: str, x: int, y: int, pid: int | None = None) -> dict | None:
        """MISSION_BUILD with a plot that is not the unit's own (GitLab #102, Maya t31: "action is not currently
        legal" and a fallback to automation): the build applies to the tile the Worker stands on, so the order
        becomes a notebook order -- walk there, then build -- run now and at each turn start until done. None when
        the plot is the unit's own (the plain build runs)."""
        try:
            pos = self.q(self.h("unit_pos", int(unit_id), False, pid=pid))
        except TunerdError:
            return None
        if not isinstance(pos, dict) or not pos.get("ok"):
            return None
        if (pos.get("x"), pos.get("y")) == (x, y):
            return None
        give = getattr(self, "give_order", None)
        if give is None:
            return {"ok": False, "err": f"the unit must stand on ({x},{y}) to build there: order(to='unit', action='move', "
                                        f"args={{x: {x}, y: {y}}}) first, then MISSION_BUILD with build alone"}
        # A direct order takes the unit from an order that holds it (#32): the walk-then-build order replaces it
        # (one order per unit) rather than being refused by it.
        holding = getattr(self, "order_holding", None)
        replace_id = holding(int(unit_id)) if holding is not None else None
        try:
            r = give(int(unit_id), [{"kind": "move", "x": x, "y": y}, {"kind": "build", "build": build}],
                     purpose=f"build {build} at ({x},{y})", replace_id=replace_id)
        except Exception as e:  # the order module's own refusal (an illegal destination, an unknown build)
            return {"ok": False, "err": f"the unit must stand on ({x},{y}) to build there, and the walk-then-build order "
                                        f"was refused: {e}", "x": pos.get("x"), "y": pos.get("y")}
        if not isinstance(r, dict) or not r.get("ok"):
            return {"ok": False, "err": f"the unit must stand on ({x},{y}) to build there, and the walk-then-build order "
                                        f"was refused: {(r or {}).get('err') if isinstance(r, dict) else r}",
                    "x": pos.get("x"), "y": pos.get("y")}
        # The tile the order's run left the unit on, not the one it started from (GitLab #182: the note said (7,24)
        # beside last.arrived at (8,23)).
        at = r.get("at") if isinstance(r.get("at"), dict) else pos
        if (at.get("x"), at.get("y")) == (x, y):
            lead = (f"the unit walked to ({x},{y}): a notebook order starts {build} there, now when it has moves left, "
                    "else at the next turn start")
        else:
            lead = (f"the unit is at ({at.get('x')},{at.get('y')}): a notebook order walks it to ({x},{y}) and starts "
                    f"{build} there, this turn as far as its moves reach and at each turn start after")
        r["note"] = lead + " (notebook(action='orders') shows it; notebook(action='cancel_order') drops it)"
        r["remote_build"] = {"build": build, "x": x, "y": y}
        return r

    #: The popups a move can raise whose record IS the reward (events.lua records them when queued, before any sweep).
    _MOVE_POPUPS = {"BUTTONPOPUP_GOODY_HUT_REWARD": "ruins", "BUTTONPOPUP_BARBARIAN_CAMP_REWARD": "camp_cleared",
                    "BUTTONPOPUP_NATURAL_WONDER_REWARD": "natural_wonder", "BUTTONPOPUP_CITY_STATE_GREETING": "city_state_met"}

    def _attach_move_events(self, r: dict, seq0: int, pid: int | None = None) -> None:
        """`happened`: what the order made happen, read from the event log past `seq0` without moving the digest's
        cursor (GitLab #122, Siam t7 / t12: a ruin's reward and a cleared camp's 16 gold arrived only on the next
        finish, stamped the previous turn). A leader met on the way (#125, Siam t16: Egypt's greeting opened under
        the move and gated the next call) is closed as the wait closes a first-contact greeting, and named here."""
        try:
            events = self.q(self.h("events_since", int(seq0), pid=pid))
        except (TunerdError, TypeError, ValueError):
            return
        if not isinstance(events, list):
            return
        happened: list[dict] = []
        met = None
        for e in events:
            if not isinstance(e, dict):
                continue
            kind, data = e.get("kind"), e.get("data") if isinstance(e.get("data"), dict) else {}
            if kind == "popup_shown" and data.get("name") in self._MOVE_POPUPS:
                row = {"kind": self._MOVE_POPUPS[data["name"]]}
                row.update({k: v for k, v in data.items() if k not in ("type", "name") and v is not None})
                happened.append(row)
            elif kind == "alert" and data.get("text"):
                happened.append({"kind": "alert", "text": data["text"]})
            elif kind == "leader_message":
                met = {"kind": "met_leader", **{k: v for k, v in data.items() if k in ("player", "state", "text") and v is not None}}
        if met is not None:
            try:
                sc = self._screens()
                if sc.get("leader_greeting_pending") and not sc.get("discussion_pending"):
                    self.dismiss_leader_greeting()
                    met["screen"] = "the greeting was closed for you (nothing to decide); the leader's words are in state(what='civ', id).history"
            except (TunerdError, AttributeError, TypeError):
                pass
            happened.append(met)
        if happened:
            r["happened"] = happened

    def _with_attack_result(self, unit_id: int, x: int, y: int, act, pid: int | None = None) -> dict:
        """Run `act()` and, when a visible enemy stands on (x, y), attach `attack`: both sides' hp
        before/after and who died.

        Shared by move_unit (a melee attack is a right-click onto the enemy) and unit_mission's
        move-shaped missions -- an **air strike is MISSION_MOVE_TO onto the target plot**, and until
        this was shared it returned only the bomber's own x/y/moves. Live t182: a Bomber killed an
        Inca Composite Bowman outright and took 11 damage, and the tool said
        `{"ok":true,"x":50,"y":24,"moves":0}` -- the pilot at the screen watches the damage numbers,
        the LLM had to wait for the next turn_digest to learn it had hit anything."""
        pre = self.q(self.h('attack_before', unit_id, x, y, pid=pid))
        air = (pre or {}).get("air") if isinstance(pre, dict) else None
        if isinstance(pre, dict) and pre.get("attack") and air and not air.get("can_strike"):
            # An air unit does not walk toward a target: the engine answers an illegal strike by doing
            # nothing at all, so issuing it returned ok with both sides' hp unchanged. Live t184: a
            # Fighter at (49,19) sent at Cusco (42,23), nine plots away against a range of eight.
            rng = air.get("range")
            return {"ok": False, "err": "this air unit cannot strike that plot right now"
                                        + (f" (its range is {rng})" if rng else "")
                                        + "; available_unit_actions(unit_id).ranged_targets and "
                                          "unit_mission_targets list the plots it can actually reach",
                    "x": x, "y": y, "range": rng}
        # The event log's head before the order rides on the pre-read (`seq`, runtime v300): what the move makes
        # happen (a ruin's reward, a camp's gold, a natural wonder, a city-state or a leader met) is read back from
        # there and rides on the reply (#122, #125). An older runtime's pre-read has no seq: the air strike's
        # interception read then takes the one trip it always did.
        seq0 = pre.get("seq") if isinstance(pre, dict) and isinstance(pre.get("seq"), int) else None
        if seq0 is None and isinstance(pre, dict) and pre.get("attack") and air:
            try:
                seq0 = self.q(self.h("event_seq_now"))
            except TunerdError:
                seq0 = None
        r = act()
        if seq0 is not None and isinstance(r, dict) and r.get("ok"):
            self._attach_move_events(r, seq0, pid)
        if isinstance(pre, dict) and pre.get("attack") and not pre.get("city") and not air and not r.get("ok") \
                and str(r.get("err", "")).startswith("unit did not move"):
            # The destination held a visible enemy, so the order was a melee attack, and the engine dropped it.
            # The occupancy hint ("occupied by another civ's unit; pick an adjacent free plot") is the wrong
            # advice for an attack (live t200, Mongolia: an Infantry in Karakorum ordered across a river onto a
            # Russian Infantry read "occupied" twice). Say the attack was refused, with every fact we can read.
            self._refused_attack(r, pre, unit_id, x, y, pid)
        if isinstance(pre, dict) and pre.get("attack") and r.get("ok"):
            time.sleep(0.3)
            if pre.get("city"):
                post = self.q(self.h('city_attack_after', unit_id, x, y, pid=pid))
            else:
                post = self.q(self.h('attack_after', unit_id, pre['def_player'], pre['def_unit'], pid=pid))
            r["attack"] = CR.attack_block(pre, post)
            if air:
                self._attach_interception(r["attack"], seq0, pre, unit_id, x, y, pid)
            dtype = (pre.get("defender") or {}).get("unit")
            if r["attack"].get("defender_killed") and dtype:
                new_id = self.q(self.h('captured_at', x, y, str(dtype), pid=pid))
                if isinstance(new_id, int):
                    CR.mark_captured(r["attack"], new_id)
            # A target two plots away is walked toward first; when the moves run out on the way nobody
            # fought, and unchanged hp on both sides read like a fight both survived (live t327).
            if r.get("arrived") is False and CR.nothing_happened(r["attack"]):
                r["attack"] = CR.no_combat_block(r["attack"])
        return r

    def _refused_attack(self, r: dict, pre: dict, unit_id: int, x: int, y: int, pid: int | None = None) -> None:
        """Reword a refused melee attack in place: what the unit tried to fight and which of the engine's own
        attack gates reads closed (CvUnit::canMoveInto with MOVEFLAG_ATTACK: out of attacks, a unit that cannot
        attack by moving, embarked without Amphibious, the domain mismatch melee_domain_refusal names). The
        engine's own legality probe is not reachable from Lua in this build (Unit:CanMoveInto is nil;
        Unit:CanMoveOrAttackInto reads false for every neighbour, empty own plots included -- probed live
        England t139), so when every readable gate is open the rule is reported as not identified; the one
        case seen live (t200) was a river crossing out of a city. Never says "occupied": that is a move's
        refusal, and a melee attack is exactly a move onto an occupied plot."""
        d = pre.get("defender") if isinstance(pre.get("defender"), dict) else {}
        who = " ".join(str(v) for v in (d.get("owner"), d.get("unit")) if v) or "the enemy unit"
        facts: dict = {}
        try:
            f = self.q(self.h("melee_refusal_facts", int(unit_id), int(x), int(y), pid=pid))
            if isinstance(f, dict):
                facts = f
        except (TunerdError, AttributeError):
            facts = {}
        why = None
        if facts.get("domain"):
            why = str(facts["domain"])
        elif (facts.get("moves") or 0) <= 0 and "moves" in facts:
            why = "the unit has no moves left this turn"
        elif facts.get("out_of_attacks"):
            why = "the unit has already attacked this turn"
        elif facts.get("cannot_attack"):
            why = "this unit cannot attack by moving (the engine's IsCanAttackWithMove is false for it)"
        elif facts.get("embarked") and not facts.get("amphibious"):
            why = "the unit is embarked and lacks Amphibious: disembark first"
        elif facts.get("adjacent") is False:
            why = (f"({x},{y}) is not adjacent: the unit walks toward it first and the engine found no path "
                   "(state(what='unit', id, view='tactical') shows the plots it can step to)")
        where = []
        if facts.get("from_city"):
            where.append("from inside a city")
        if facts.get("river"):
            where.append("across a river")
        err = f"the engine refused the melee attack on {who} at ({x},{y})"
        if where:
            err += " " + " ".join(where)
        if why:
            err += ": " + why
        else:
            err += ("; every attack gate this harness can read is open (moves, attacks left, embarkation, "
                    "domain), so the engine's rule is not identified -- the one case seen live was a river "
                    "crossing out of a city. Attack from another plot, or shoot it with a ranged unit "
                    "(state(what='unit', id, view='tactical') lists the plots this unit can attack from)")
        r["err"] = err
        r["refused_attack"] = {"defender": d, **{k: v for k, v in facts.items() if k != "adjacent"}}

    def _attach_interception(self, a: dict, seq0, pre: dict, unit_id: int, x: int, y: int, pid: int | None = None) -> None:
        """An air strike can be intercepted on the way in. The pilot sees the interceptor fire and the damage
        it did; the result only said my_hp / my_unit_killed, which read as if the strike itself had gone wrong
        (live 2026-09-24: a Bomber lost to an AA gun). The engine's banner for a strike is just "Your Bomber
        bombarded an enemy Infantry! (87 damage)" -- no interception line -- so the interception is read the
        way the stock panel counts it: a visible interceptor that fired is out of interceptions for the turn
        and drops out of GetInterceptorCount (1 before, 0 after, live). The unit the engine would send up is
        named when it was in sight before the strike. When the aircraft died another of ours asks; failing
        that, a dead aircraft beside an untouched target still means it never got to strike. Banner texts
        that do name an interception ("was intercepted by" / "was shot down by") are honoured too."""
        before = pre.get("interception") if isinstance(pre.get("interception"), dict) else {}
        after: dict = {}
        try:
            after = self.q(self.h("interception_after", unit_id, x, y, pre.get("def_player", -1),
                                  pre.get("def_unit", -1), pid=pid)) or {}
        except TunerdError:
            after = {}
        if isinstance(before.get("count"), int):
            a["visible_interceptors_before"] = before["count"]
        fired = (isinstance(before.get("count"), int) and isinstance(after.get("count"), int)
                 and after["count"] < before["count"])
        texts: list = []
        if isinstance(seq0, int):
            try:
                texts = self.q(self.h('alerts_since', seq0, pid=pid)) or []
            except TunerdError:
                texts = []
        hits = [t for t in texts if isinstance(t, str) and ("was intercepted by" in t or "was shot down by" in t)]
        unhurt = (a.get("def_hp") is not None and a.get("def_hp") == a.get("defender_hp_before")
                  and not a.get("defender_killed"))
        killed_on_the_way = bool(a.get("my_unit_killed") and unhurt)
        if not (fired or hits or killed_on_the_way):
            return
        a["intercepted"] = True
        if isinstance(before.get("best"), dict):
            a["interceptor"] = {k: v for k, v in before["best"].items() if k != "player"}
        elif hits:
            m = re.search(r"by an enemy (.+?)!", hits[0])
            if m:
                a["interceptor"] = {"unit": m.group(1)}
        if hits:
            a["interception"] = hits[0] if len(hits) == 1 else hits
        if a.get("my_unit_killed"):
            a["shot_down"] = True
            if unhurt:
                a["note"] = "shot down by an interceptor before it could strike: the target is unhurt"
            else:
                a["note"] = ("intercepted on the way in and destroyed: the interception and the target's air defence "
                             "together used up its hp; the strike still landed (see def_hp)")
        else:
            a["note"] = ("intercepted on the way in and still struck; my_hp includes the interception damage, "
                         "which the preview's expected_damage_taken excluded")

    def _move_unit(self, unit_id: int, x: int, y: int, pid: int | None = None, settle_timeout: float = 1.0) -> dict:
        """Issue a move-to for a unit through the game's network path (selection list +
        GAMEMESSAGE_PUSH_MISSION, see harness/lua/runtime/helpers.lua net_unit_message).

        The order is applied on a later game update -- the unit's x/y read back in the same Lua
        call is still the pre-move plot -- so poll briefly for GetX/GetY or MovesLeft to change
        before returning. If the engine has not advanced within the timeout, report the pre-move
        reading honestly."""
        r = self._order(self.h('move_unit', unit_id, x, y, pid=pid))
        if not r.get("ok"):
            return r
        deadline = time.monotonic() + settle_timeout
        cur = r
        while time.monotonic() < deadline:
            time.sleep(0.15)
            # reveal=true: `revealed` is what the move showed (how many new plots, the notable ones, units/cities
            # that came into sight; count 0 means nothing new), so "move and see what is there" needs no second
            # read; the new ground itself is the map window the row offers (GitLab #153).
            cur = self.q(self.h('unit_pos', unit_id, True, pid=pid))
            if not cur.get("ok"):
                return cur
            if (cur["x"], cur["y"]) != (r["x"], r["y"]) or cur["moves"] != r["moves"]:
                _offer_map_window(cur)
                # Say whether it got there: activity MISSION alone left "moved (24,23)->(24,29), asked for
                # (25,30)" to be worked out by the caller (live t325).
                cur["arrived"] = (cur["x"], cur["y"]) == (x, y)
                if not cur["arrived"]:
                    cur["destination"] = {"x": x, "y": y}
                    if cur.get("activity") == 6:
                        cur["note"] = "still on its way: the order carries on next turn (order(to='unit', action='move') again to change it)"
                elif r.get("swap_candidates"):
                    # One of ours stood on the destination: if it is now on the plot we left, the
                    # engine swapped the two (live t252, Workers at Goshute). Say so -- the other
                    # unit moved too, and spent its moves doing it.
                    ids = [c["id"] for c in r["swap_candidates"] if isinstance(c, dict) and "id" in c]
                    sw = self.q(self.h("swapped_unit", ids, r["x"], r["y"], pid=pid))
                    if isinstance(sw, dict) and sw.get("unit"):
                        cur["swapped_with"] = sw["unit"]
                        cur["note"] = (f"swapped places with {sw['unit'].get('type')} {sw['unit'].get('id')}, "
                                       f"which is now at ({r['x']},{r['y']}) with {sw['unit'].get('moves')} moves")
                # The loss roster is snapshotted at turn start/end; a unit we moved and then lost during our own
                # turn would otherwise be placed where the turn began (live S1 t267). Refresh it here, cheaply.
                try:
                    self.q(self.h("note_unit_by_id", unit_id, pid=pid))
                except TunerdError:
                    pass
                return cur
        # Nothing changed within settle_timeout. A unit with no moves left keeps the order queued for
        # next turn (activity MISSION); otherwise the engine dropped it silently -- no path to that
        # plot (unexplored/impassable terrain in the way, another civ's closed borders, a unit in the
        # way) -- and reporting ok:true here sent callers on with a unit that never moved (live t252).
        if cur.get("ok") and (cur.get("activity") == 6 or (r.get("moves") or 0) <= 0):
            cur.pop("revealed", None)   # it has not moved yet: nothing was shown
            cur["queued"] = True
            # #37: say where it is going; the next turn_status repeats it under todo.ongoing.
            cur["going_to"] = {"x": int(x), "y": int(y)}
            cur["note"] = (cur.get("note") + "; " if cur.get("note") else "") + \
                "standing move: resumes at the start of each of my turns until the unit arrives (todo.ongoing)"
            return cur
        out = {"ok": False, "err": "unit did not move: the engine found no path to that plot (unexplored or impassable "
                                   "terrain in the way, a closed border, or a unit blocking it); try a nearer plot",
               "x": r.get("x"), "y": r.get("y"), "moves": r.get("moves")}
        # A fogged destination that holds a unit is refused by the pathfinder exactly like a visible one, and the
        # banner shows nothing there (live Assyria t132-t143: a Missionary's plot beside La Venta, Yerevan, Sofia and
        # the Zulu capital, each time a city-state's or Shaka's unit standing in the fog; the next neighbour worked).
        # Say that the fog may hide the blocker without reading what is there.
        try:
            vis = self.q(self.h("plot_visible", int(x), int(y), pid=pid))
            if vis in (False, "false", 0):
                out["err"] += ("; the destination is fogged, so a unit you cannot see may hold it: "
                               "a plot next to it often works")
                out["fogged_destination"] = True
            else:
                # GitLab #113 (Maya t106): the destination held my own Caravan and the refusal blamed the fog. A
                # visible plot's units are read; whatever that read does, the refusal still reaches the caller.
                try:
                    at = self.q(self.h("plot_units", int(x), int(y), pid=pid))
                    me = self._pid(pid)
                    mine = [u for u in (at.get("units") or []) if isinstance(u, dict) and u.get("owner") == me] if isinstance(at, dict) else []
                except Exception:
                    mine = []
                if mine:
                    out["err"] += (f"; the destination already holds your {mine[0].get('type')} ({mine[0].get('id')}): one "
                                   "civilian and one military unit per tile, pick a neighbour")
                    out["blocking_unit"] = mine[0]
        except (TunerdError, ValueError, TypeError):
            pass
        # H.move_unit already stored this destination as a standing order; a refused move must not leave it for
        # resume_moves to re-push next turn (live t76: a Worker refused onto another Worker's plot kept (48,15)).
        try:
            # Keyed per seat since the hotseat fix (H.pm_key), not by the bare id: the old form cleared nothing
            # and the refused destination came back as going_to / a resumed order the next turn.
            self.q(self.h("drop_pending_move", int(unit_id), pid=pid))
        except TunerdError:
            pass
        try:
            mine = self._unit_rows(pid)
            me = next((u for u in mine if u.get("id") == unit_id), None)
            hint = (me and self._blocker_hint(me, x, y, mine)) or self._foreign_occupant_hint(x, y)
            if hint:
                out["err"] = "unit did not move: " + hint
        except TunerdError:
            pass
        return out

    def _unit_rows(self, pid: int | None = None) -> list[dict]:
        """units() filtered to well-formed rows (hint helpers must never break the call they decorate)."""
        rows = self.units(pid)
        return [u for u in rows if isinstance(u, dict)] if isinstance(rows, list) else []

    def _foreign_occupant_hint(self, x: int, y: int) -> str | None:
        """Another civ's unit visible on the destination (map_window's own visibility rules). Live t414: a
        Missionary's path to a plot next to Quebec City failed turn after turn -- the city-state's Infantry and
        Anti-Aircraft Gun stood on both target plots, and the error said only 'no path'."""
        try:
            w = self.plots_around(x, y, 0)
        except TunerdError:
            return None
        plots = w.get("plots", w) if isinstance(w, dict) else w
        for p in plots if isinstance(plots, list) else []:
            if isinstance(p, dict) and (p.get("x"), p.get("y")) == (x, y):
                others = [u for u in p.get("units") or [] if isinstance(u, dict) and u.get("owner") != self.seat]
                if others:
                    names = ", ".join(str(u.get("type")) for u in others)
                    return f"({x},{y}) is occupied by another civ's unit ({names}); pick an adjacent free plot"
        return None

    @staticmethod
    def _blocker_hint(me: dict, x: int, y: int, mine) -> str | None:
        """One unit per plot per class (combat / civilian) and domain, cities included (live t333: a Worker on
        Shanghai's plot kept a Missionary out). Name my own blocker when there is one."""
        cls = lambda u: (u.get("strength") or 0) > 0
        for u in mine:
            # caravans/cargo ships on a route are automated and pass through; an idle one home in a city does
            # block (live t449: a returned Caravan on Beijing's plot kept an SS Booster out of the capital)
            if (u.get("id") != me.get("id") and (u.get("x"), u.get("y")) == (x, y) and not u.get("automated")
                    and cls(u) == cls(me) and u.get("domain") == me.get("domain")):
                trade = u.get("type") in ("CARAVAN", "CARGO_SHIP")
                return (f"your {u.get('type')} (unit {u.get('id')}) already holds ({x},{y}) and only one "
                        f"{'combat' if cls(me) else 'civilian'} unit fits per plot: "
                        + ("send it on a trade route (order(to='unit', action='trade_route')) or move it" if trade else
                           "move it, or pick an adjacent plot")
                        + (" (a missionary/prophet can spread from next to the city)" if me.get("type") in
                           ("MISSIONARY", "PROPHET", "INQUISITOR") else ""))
        return None

    def unit_mission(self, unit_id: int, mission: str, x: int = -1, y: int = -1, data2: int = 0,
                     build: str | None = None, pid: int | None = None) -> dict:
        """See _unit_mission. A mission the engine calls illegal comes back with the unit's legal ones
        (live t328: MISSION_FORTIFY on a Cannon -- siege units cannot fortify, MISSION_SLEEP is the answer)."""
        if mission == "MISSION_BUILD" and build and isinstance(x, int) and isinstance(y, int) and x >= 0 and y >= 0:
            remote = self._remote_build(unit_id, build, x, y, pid)
            if remote is not None:
                return remote
        # Great-person missions whose payoff is an empire number: measure it (live t333: a political treatise
        # answered only consumed:true; culture had gone 1218 -> 1874).
        gp_stat = {"MISSION_GIVE_POLICIES": "culture", "MISSION_TRADE": "gold",
                   "MISSION_GOLDEN_AGE": "golden_age_turns",
                   # live t379: a 5106-science bulb took Computers from 9 turns to 2 -- say so
                   "MISSION_DISCOVER": "research_turns_left"}.get(mission)
        before = research_before = None
        if gp_stat:
            try:
                summ0 = self.summary(pid)
                before, research_before = summ0.get(gp_stat), summ0.get("research")
            except (TunerdError, AttributeError):
                before = None
        hurry0 = self._hurry_city_production(unit_id, None, pid) if mission == "MISSION_HURRY" else None
        tour0 = self._concert_tour_preview(unit_id, pid) if mission == "MISSION_ONE_SHOT_TOURISM" else None
        if tour0 and tour0.get("legal_here") is False:
            # GitLab #142 (Maya t232): the tour plays to the owner of the plot the Musician stands on; sent from home
            # soil the engine accepts the push and nothing happens. The actions read's `missing` row names the nearest plot.
            return {"ok": False, "err": "MISSION_ONE_SHOT_TOURISM needs a plot owned by another major civ (the tour plays to "
                                        f"its owner); the unit stands on {tour0.get('here')} land -- state(what='unit', id, "
                                        "view='actions').missing names the nearest plot that qualifies"}
        pillage_gold0 = None
        pillage_plot0 = None
        if mission in ("MISSION_PILLAGE", "MISSION_PILLAGE_ROUTE"):
            # The engine accepts a pillage order from a unit with no moves left and then does nothing:
            # the plot stays improved, the unit goes to HOLD, and the old reply said ok with
            # gold_gained 0 (live 2026-09-24 t219: Infantry walked two tiles onto a quarry and "pillaged"
            # it). The stock button is greyed at 0 moves; refuse the same way and say when to retry.
            try:
                pillage_plot0 = self.q(self.h("pillage_plot_facts", int(unit_id), pid=pid))
            except (TunerdError, AttributeError):
                pillage_plot0 = None
            if isinstance(pillage_plot0, dict) and (pillage_plot0.get("moves") or 0) <= 0:
                return {"ok": False, "err": "the unit has no moves left this turn, so the engine would drop the pillage "
                                            "order; pillage next turn (or before moving)",
                        "x": pillage_plot0.get("x"), "y": pillage_plot0.get("y"), "moves": 0}
            try:
                pillage_gold0 = self.summary(pid).get("gold")
            except (TunerdError, AttributeError):
                pillage_gold0 = None
        r = self._unit_mission(unit_id, mission, x, y, data2, build, pid)
        if tour0 and isinstance(r, dict) and r.get("consumed"):
            # live t232: the reply was {ok, consumed} -- no tourism figure, no receiving civ
            r["effect"] = {k: tour0.get(k) for k in ("tourism", "others_percent") if tour0.get(k) is not None}
            r["effect"]["to_civ"] = (tour0.get("to") or {}).get("civ")
            r["effect"]["to_id"] = (tour0.get("to") or {}).get("id")
            self._note_spent(unit_id, f"{mission}: {tour0.get('tourism')} tourism to {r['effect']['to_civ']}")
        if hurry0 and isinstance(r, dict) and r.get("ok"):
            # live t437: an Engineer hurrying Hubble answered only consumed:true
            after = self._hurry_city_production(None, hurry0.get("city_id"), pid)
            if after:
                r["effect"] = {"city": hurry0.get("city"), "production": hurry0.get("production"),
                               "turns_before": hurry0.get("turns"), "turns_after": after.get("turns"),
                               "progress_before": hurry0.get("progress"), "progress_after": after.get("progress"),
                               "cost": after.get("cost")}
                if after.get("production") != hurry0.get("production"):
                    r["effect"]["completed"] = hurry0.get("production")
                    r["effect"]["now_building"] = after.get("production")
        if gp_stat and before is not None and isinstance(r, dict) and r.get("ok"):
            try:
                summ = self.summary(pid)
                r["effect"] = {gp_stat + "_before": before, gp_stat + "_after": summ.get(gp_stat)}
                # A bulb that finishes the current tech moves research on: turns_left 6 -> 8 read like a loss
                # (live t419, Penicillin done, Ecology next). Name the research on both sides.
                if gp_stat == "research_turns_left":
                    r["effect"]["research_before"] = research_before
                    r["effect"]["research_after"] = summ.get("research")
            except (TunerdError, AttributeError):
                pass
        if mission in ("MISSION_PILLAGE", "MISSION_PILLAGE_ROUTE") and isinstance(r, dict) and r.get("ok") \
                and pillage_gold0 is not None:
            # Stock combat banner shows the gold; digest used to be the only place it landed.
            try:
                gold1 = pillage_gold0
                for _ in range(8):
                    time.sleep(0.25)
                    gold1 = self.summary(pid).get("gold")
                    if gold1 != pillage_gold0:
                        break
                r["effect"] = {"gold_before": pillage_gold0, "gold_after": gold1,
                               "gold_gained": (gold1 or 0) - (pillage_gold0 or 0)}
                # Say whether the plot actually changed, not just the treasury: a pillaged route, farm or
                # camp yields no gold at all, and the gold line alone read like "nothing happened".
                if isinstance(pillage_plot0, dict):
                    after = self.q(self.h("plot_pillage_state", int(pillage_plot0["x"]), int(pillage_plot0["y"]), pid=pid)) or {}
                    r["effect"]["improvement_pillaged"] = bool(after.get("improvement")) and not pillage_plot0.get("improvement")
                    r["effect"]["route_pillaged"] = bool(after.get("route")) and not pillage_plot0.get("route")
                    if not (r["effect"]["improvement_pillaged"] or r["effect"]["route_pillaged"]):
                        r["effect"]["note"] = "nothing on the plot was pillaged"
            except (TunerdError, AttributeError):
                pass
        if mission in ("MISSION_ENHANCE_RELIGION", "MISSION_FOUND_RELIGION") and isinstance(r, dict) and r.get("ok"):
            # The Prophet is spent and the belief choice is open (#109, live Maya t105: a bare consumed:true, then
            # the order refused as "not pending" behind the PRODUCTION blocker). Hand back the choice's rows.
            from .. import gate as G
            popup = "BUTTONPOPUP_ENHANCE_RELIGION" if mission == "MISSION_ENHANCE_RELIGION" else "BUTTONPOPUP_FOUND_RELIGION"
            r["next"] = G.popup_rows(popup)
            r["note"] = (("now choose the two beliefs: state(what='options', view='beliefs') with kind follower, then "
                          "kind enhancer, and order(to='empire', action='enhance_religion', args={religion, belief4 (the "
                          "follower belief), belief5 (the enhancer belief), city_x, city_y of the holy city}); the choice "
                          "stays open until made, whatever blocker status names")
                         if mission == "MISSION_ENHANCE_RELIGION" else
                         ("now found it: state(what='options', view='beliefs') with kind founder, then kind follower, and "
                          "order(to='empire', action='religion', args={religion, beliefs: [founder, follower], city_x, "
                          "city_y}); the choice stays open until made, whatever blocker status names"))
        if mission == "MISSION_SPACESHIP" and isinstance(r, dict) and r.get("ok"):
            # Live t424: adding the Cockpit answered only consumed:true -- show the ship after.
            try:
                ship = self.spaceship_status(pid)
                r["spaceship"] = {p["part"]: f"{p['in_ship']}/{p['needed']}" for p in ship.get("parts", [])}
                if ship.get("complete"):
                    # Live t502: the last Booster completed the ship and the engine went straight to
                    # GAMESTATE_OVER, where its delayed removal of the part unit never runs: the read-back found
                    # the unit standing in the capital with its 2 moves and the reply carried no `consumed`.
                    # The part is spent all the same; say what the order did instead of where the unit stands.
                    for k in ("x", "y", "moves", "activity", "activity_name", "buildtype"):
                        r.pop(k, None)
                    r["consumed"] = True
                    r["ship_complete"] = True
                    if ship.get("game_over"):
                        r["game_over"] = True
                        r["victory"] = "science"
                        r["note"] = ("the ship is complete: Science Victory, the game is over (turn(action='status') carries the "
                                     "game_over gate; session(action='main_menu') leaves it)")
            except (TunerdError, AttributeError, KeyError):
                pass
        if isinstance(r, dict) and r.get("err") == "action is not currently legal":
            if mission in ("MISSION_ENHANCE_RELIGION", "MISSION_FOUND_RELIGION"):
                # GitLab #103 (Maya t89, t92): a Prophet refused inside another city and on a hill with the bare list.
                try:
                    why = self.q(self.h("religion_mission_why", int(unit_id), mission, pid=pid))
                except (TunerdError, AttributeError):
                    why = None
                if isinstance(why, str) and why:
                    r["reason"] = why
            if mission == "MISSION_BUILD" and build:
                # GitLab #130: a plantation on jungle cocoa needs Bronze Working (the jungle is removed as part of
                # the build); the bare legal list said nothing. Name the engine's rule when the runtime can.
                try:
                    why = self.q(self.h("build_refusal_why", int(unit_id), build, pid=pid))
                except (TunerdError, AttributeError):
                    why = None
                if isinstance(why, str) and why:
                    r["reason"] = why
            if mission == "MISSION_RANGE_ATTACK":
                # Live t193: a Keshik rode three plots to shoot and got the bare refusal -- the plot was in range
                # by count but not in its line of fire. Say which test failed, so the next order is the right one.
                why = self._range_attack_reason(unit_id, x, y, pid)
                if why:
                    r["reason"] = why
            try:
                acts = self.available_unit_actions(unit_id, pid)
                r["legal_missions"] = [a.get("mission") or a.get("type") for a in acts.get("actions", [])]
                # Live t330: a freshly built Infantry in a garrisoned city could only move/swap -- two combat
                # units on one plot until one leaves. Say so instead of leaving the caller to guess.
                mine = self._unit_rows(pid)
                me = next((u for u in mine if u.get("id") == unit_id), None)
                if me and (me.get("strength") or 0) > 0:
                    mates = [u["id"] for u in mine if u.get("id") != unit_id and (u.get("strength") or 0) > 0
                             and (u.get("x"), u.get("y")) == (me.get("x"), me.get("y")) and u.get("domain") == me.get("domain")]
                    if mates:
                        r["reason"] = (f"stacked with your combat unit(s) {mates} on ({me['x']},{me['y']}): only one may stay; "
                                       f"move this one (or that one) to another plot first")
                # Live 2026-10-03 (Codex t63): MISSION_SLEEP on a Warrior answered only the legal list. The engine's
                # Sleep is Fortify for a unit that can fortify, and Fortify does not exist for one that cannot
                # (no defensive bonus: mounted, armoured, siege, naval; civilians). Name the equivalent order.
                if "reason" not in r:
                    if mission == "MISSION_SLEEP" and "MISSION_FORTIFY" in r["legal_missions"]:
                        r["reason"] = ("a unit that can fortify never sleeps (its Sleep button is Fortify): MISSION_FORTIFY "
                                       "holds it the same way, MISSION_ALERT wakes it when an enemy comes into view")
                    elif mission == "MISSION_FORTIFY" and "MISSION_SLEEP" in r["legal_missions"]:
                        r["reason"] = ("this unit cannot fortify (no defensive bonus: mounted, armoured, siege and naval "
                                       "units, and civilians): MISSION_SLEEP holds it until it is woken")
                    elif (mission in ("MISSION_SLEEP", "MISSION_FORTIFY", "MISSION_ALERT", "MISSION_HEAL")
                          and "COMMAND_WAKE" in r["legal_missions"]
                          and not {"MISSION_SLEEP", "MISSION_FORTIFY"} & set(r["legal_missions"])):
                        # Live t251: MISSION_SLEEP on an Infantry already fortified answered only the legal list,
                        # which had COMMAND_WAKE and no hold at all -- the unit is holding already.
                        r["reason"] = ("this unit is already holding (fortified, asleep or on alert): it needs no new "
                                       "order and never blocks the turn; COMMAND_WAKE wakes it, a move or attack "
                                       "takes it out of the hold by itself")
            except TunerdError:
                pass
        if isinstance(r, dict) and not r.get("ok") and str(r.get("err") or "").startswith("unknown mission"):
            # A guessed name (MISSION_FORTIFY_HEAL, live Codex t45) stops a whole batch: name the unit's legal
            # missions and the nearest real names, the legal ones first, so the retry is the right order.
            legal: list[str] = []
            try:
                acts = self.available_unit_actions(unit_id, pid)
                legal = [n for n in (a.get("mission") or a.get("type") for a in acts.get("actions", [])) if n]
            except (TunerdError, AttributeError):
                legal = []
            r["legal_missions"] = legal
            # One pool, the unit's legal names ahead of the stock ones: live t251 (Mongolia, a fortified Infantry)
            # an `or` between the two lists answered MISSION_FORTIFY_HEAL with MISSION_ROUTE_TO alone, because
            # the legal list had one weak match and the stock names (MISSION_FORTIFY, MISSION_HEAL) were never
            # consulted.
            pool = list(legal) + [n for n in KNOWN_MISSIONS if n not in legal]
            sm = difflib.SequenceMatcher(None, "", str(mission))
            scored = []
            for name in pool:
                sm.set_seq1(name)
                scored.append((sm.ratio(), name))
            scored.sort(key=lambda t: -t[0])   # stable: a legal name stays ahead of a stock name it ties with
            best = scored[0][0] if scored else 0.0
            # The names near the best one, not every name past a floor: MISSION_FORTIFY_HEAL is FORTIFY (0.86)
            # and HEAL (0.75), not REBASE (0.65) and AIRLIFT (0.63) as well.
            near = [name for score, name in scored if score >= 0.6 and score >= best - 0.15][:4]
            if near:
                r["did_you_mean"] = near
                r["err"] = f"{r['err']}; nearest real names: {', '.join(near)}"
        return r

    def _range_attack_reason(self, unit_id: int, x: int, y: int, pid: int | None = None,
                             hard_only: bool = False) -> str | None:
        """Why MISSION_RANGE_ATTACK on (x, y) is not legal for this unit: the engine's own tests in order --
        no ranged attack, no moves, already attacked, a siege unit not set up, the plot out of range, out of the
        unit's line of fire (CvPlot::canSeePlot with the attack range, the test tactical_view's fire_los shows),
        or no visible enemy there. None when the probe cannot run (the refusal then stays bare). hard_only stops
        after the range test: the facts the engine does not check when it accepts the mission."""
        try:
            f = self.q(self.h("ranged_refusal_facts", int(unit_id), int(x), int(y), pid=pid))
        except (TunerdError, AttributeError):
            return None
        if not isinstance(f, dict):
            return None
        rng = f.get("range") or 0
        if rng <= 0:
            return "this unit has no ranged attack (a melee attack is order(to='unit', action='move') onto the enemy's plot)"
        if not f.get("plot"):
            return f"({x},{y}) is not a plot on this map"
        if (f.get("moves") or 0) <= 0:
            return ("the unit has no moves left this turn (a move spent them; crossing a river ends a unit's movement): "
                    "it fires next turn")
        if f.get("out_of_attacks"):
            return "the unit has already attacked this turn"
        if f.get("needs_setup"):
            return "a siege unit must set up before it fires (MISSION_SETUP_FOR_RANGED_ATTACK), which takes a turn"
        d = f.get("distance")
        if isinstance(d, int) and d > rng:
            return (f"({x},{y}) is {d} plots from the unit at ({f.get('x')},{f.get('y')}) and its range is {rng}: "
                    "move within range first (state(what='unit', id, view='tactical') lists the plots in its fire_los)")
        if hard_only:
            return None
        if f.get("los") is False and not f.get("ignores_los"):
            return (f"({x},{y}) is within range {rng} but not in the unit's line of fire from ({f.get('x')},{f.get('y')}): "
                    "hills or forest in between block the shot (the tactical view's in_fire_los); fire from another plot")
        if not f.get("visible"):
            return f"({x},{y}) is not visible to the unit"
        if not f.get("enemy"):
            return f"no enemy unit or city on ({x},{y}) (a target must be at war with you and visible)"
        return None

    def _hurry_city_production(self, unit_id: int | None, city_id: int | None, pid: int | None = None) -> dict | None:
        """Production of the city on `unit_id`'s plot (or city `city_id`): what it builds, turns, stored hammers."""
        try:
            r = self.q(self.h("hurry_city_production_facts", None if unit_id is None else int(unit_id),
                              None if city_id is None else int(city_id), pid=pid))
        except TunerdError:
            return None
        return r if isinstance(r, dict) and r.get("city_id") is not None else None

    def _unit_mission(self, unit_id: int, mission: str, x: int = -1, y: int = -1, data2: int = 0,
                      build: str | None = None, pid: int | None = None) -> dict:
        """Push a mission by name through the game's network path (selection list +
        GAMEMESSAGE_PUSH_MISSION, see harness/lua/runtime/helpers.lua net_unit_message).

        e.g. MISSION_FOUND, MISSION_FORTIFY, MISSION_SLEEP, MISSION_SKIP, MISSION_MOVE_TO (x, y).
        `data2` is accepted for call-site compatibility and ignored: extra mission data is `build`
        for MISSION_BUILD, or x/y for movement-shaped missions.

        MISSION_BUILD: pass the improvement via `build=` (e.g. build="BUILD_FARM"), NOT x/y --
        the BuildTypes id travels as the mission's first data word. The build always applies to the
        unit's own tile.

        The message does not report whether the mission stuck, and it is applied on a later game
        update. For MISSION_BUILD this polls until GetBuildType() shows the build (or the plot has
        already changed for an instant build) before reporting success."""
        _ = data2
        push = lambda: self._order(self.h("unit_mission", unit_id, mission, x, y, build or None, pid=pid))
        religious = mission in ("MISSION_SPREAD_RELIGION", "MISSION_REMOVE_HERESY")
        before = self.q(self.h('religion_target', unit_id, pid=pid)) if religious else None
        if religious and before.get("ok") and not before.get("city"):
            return {"ok": False, "err": "no city on or adjacent to the unit's plot; move next to (or into) the target city first"}
        # A Great Person is a once-in-many-turns resource and MISSION_CREATE_GREAT_WORK answered with a
        # bare {ok, consumed}: which work, in which city's which building, was left for the caller to
        # find by diffing culture_works (live t215: "Martin Fierro" went into Te-Moak's Amphitheater).
        # The game shows a popup naming it. Snapshot the slots and report the one that filled.
        works_before = (self.q(self.h('great_work_index', pid=pid)) or {}
                        ) if mission == "MISSION_CREATE_GREAT_WORK" else None
        found_pre = None
        if mission == "MISSION_FOUND":
            # PushMission(MISSION_FOUND) "succeeds" with no moves left and no city (live t283), so check
            # first and confirm the city afterwards instead of trusting the accept.
            found_pre = self.q(self.h('found_check', unit_id, -1, -1, pid=pid))
            if found_pre.get("ok") and found_pre.get("unit_exists"):
                if found_pre.get("city"):
                    return {"ok": False, "err": "there is already a city on this plot"}
                if (found_pre.get("moves") or 0) <= 0:
                    return {"ok": False, "err": "the settler has no moves left this turn (a standing move just spent "
                                                "them); MISSION_FOUND needs at least one move -- found next turn",
                            "x": found_pre.get("x"), "y": found_pre.get("y"), "moves": 0}
                if not found_pre.get("can_found"):
                    return {"ok": False, "err": found_refusal(found_pre), "x": found_pre.get("x"), "y": found_pre.get("y"),
                            **{k: found_pre[k] for k in ("nearest_city", "min_distance", "water", "foreign_owner") if k in found_pre}}
        if mission == "MISSION_RANGE_ATTACK" and x >= 0 and y >= 0:
            # The engine accepts a pushed ranged attack from a unit with no moves left and does nothing (live
            # Assyria t38: an Archer that had crossed a river answered ok with the target unchanged). The hard facts
            # -- no moves, attacked already, a siege unit not set up, the plot out of range -- refuse it up front;
            # line of fire, visibility and the target's owner stay the engine's call (its refusal gets the reason).
            why = self._range_attack_reason(unit_id, x, y, pid, hard_only=True)
            if why:
                return {"ok": False, "err": "action is not currently legal", "reason": why}
        if mission in ("MISSION_RANGE_ATTACK", "MISSION_NUKE", "MISSION_PARADROP") and x >= 0 and y >= 0:
            r = self._with_target_result(x, y, push, pid)
        elif mission in ("MISSION_MOVE_TO", "MISSION_MOVE_UNIT_TO") and x >= 0 and y >= 0:
            # An air strike is issued exactly like a move onto the target plot, so this is the
            # attack path for every air unit. attack_before answers "no enemy there" for an
            # ordinary move, and then this costs nothing extra.
            r = self._with_attack_result(unit_id, x, y, push, pid)
        else:
            r = push()
        if not r.get("ok"):
            return r
        if r.get("automate_pending") is not None:
            if deferring_after_reads():
                return {"ok": True, "after_pending": {"unit_id": unit_id, "mission": mission, "kind": "automate"}}
            # The command lands on the next game frame (live t151, six pushes: automated on the first read every
            # time, 43-60 ms after the push), so the first read follows at once and polling is the fallback.
            check = lambda: self.q(self.h('automate_check', unit_id, pid=pid))
            chk = check()
            if not _automate_landed(chk):
                chk, _ = self._settle(check, _automate_landed, timeout=3.0, poll=0.1, initial=chk)
            return self._apply_automate_after(mission, chk)
        if r.get("command_pending"):
            # Verify: a delete must make the unit disappear; other commands report the unit's state after.
            for _ in range(12):
                time.sleep(0.25)
                pos = self.q(self.h('unit_pos', unit_id, pid=pid))
                gone = not (isinstance(pos, dict) and pos.get("ok"))
                if mission == "COMMAND_DELETE":
                    if gone:
                        return {"ok": True, "command": mission, "unit_gone": True}
                elif not gone:
                    return {"ok": True, "command": mission, **{k: v for k, v in pos.items() if k != "ok"}}
            return {"ok": False, "err": f"{mission} was sent but no effect was seen within 3 s"}
        if build and r.get("pending"):
            before = r.pop("before", None)
            r.pop("pending", None)
            chk = None
            for _ in range(12):
                time.sleep(0.25)
                chk = self.q(self.h("build_check", unit_id, r.get("x", -1), r.get("y", -1), before or None, pid=pid))
                if chk.get("started") or chk.get("completed"):
                    break
            if chk and chk.get("completed"):
                done = {"ok": True, "buildtype": -1, "completed": True, "moves": chk.get("moves")}
                for k in ("improvement", "claimed_plots", "unit_consumed"):
                    if chk.get(k) is not None:
                        done[k] = chk[k]
                if chk.get("claimed_plots"):
                    # Naming the civ we took tiles from is the part a human sees as a diplomatic
                    # incident, not just a border move.
                    taken = sorted({r.get("taken_from_name") or str(r.get("taken_from"))
                                    for r in chk["claimed_plots"]
                                    if isinstance(r, dict) and r.get("taken_from") is not None})
                    done["note"] = (f"claimed {len(chk['claimed_plots'])} tile(s)"
                                    + (", taken from " + ", ".join(taken) if taken else ""))
                return done
            if chk and chk.get("started"):
                out = {"ok": True, "buildtype": chk.get("buildtype"), "build": chk.get("build"),
                       "turns_left": chk.get("turns_left"), "moves": chk.get("moves")}
                if chk.get("replaced_improvement"):
                    # A dig clears what stood on the plot the moment it starts (#140, live t218: a Trading Post).
                    out["replaced_improvement"] = chk["replaced_improvement"]
                    out["note"] = f"the {chk['replaced_improvement']} on the plot is gone: the build replaces it"
                if r.get("build_id") is not None and chk.get("buildtype") != r.get("build_id"):
                    # The engine clears a feature the ordered improvement removes as its own build first, then
                    # carries on with the order (live: Spices plantation on marsh t71 -> REMOVE_MARSH, finished
                    # as a plantation t79 without a new order; Silk/forest-hill mine t79 -> REMOVE_FOREST).
                    if str(chk.get("build") or "").startswith("BUILD_REMOVE_"):
                        out["note"] = (f"{chk.get('build')} runs first ({chk.get('turns_left')} turns); the ordered "
                                       "build follows on its own, no new order needed")
                    else:
                        out["note"] = (f"the unit is working on {chk.get('build')}, not the ordered build "
                                       f"(id {r.get('build_id')})")
                return out
            return {"ok": False, "err": "MISSION_BUILD was sent but the unit did not start the build within 3 s "
                                        "(neither the unit's build type nor the plot's build progress shows it, and "
                                        "the plot is unchanged)"}
        if works_before is not None:
            for _ in range(8):
                time.sleep(0.25)
                after = self.q(self.h('great_work_index', pid=pid)) or {}
                new = [w for k, w in after.items() if k not in works_before]
                if new:
                    r["great_work"] = new[0]
                    # This branch returns before the consumed-unit note below: the Great Writer's delayed
                    # unit_destroyed row still read "gone during your own turn with no combat" (live Assyria
                    # t139, 2026-10-11, "Don Quixote" in Assur's Royal Library).
                    w = new[0] if isinstance(new[0], dict) else {}
                    self._note_spent(unit_id, f"{mission}: {w.get('name')} in {w.get('city')}'s {w.get('building')}")
                    return r
            r["note"] = ("no new great work appeared; the slot may have been taken this turn -- "
                         "state(what='screen', view='culture_works') shows every slot and which are empty")
            if r.get("consumed"):
                self._note_spent(unit_id, mission)
            return r
        if found_pre is not None and found_pre.get("unit_exists"):
            fx, fy = found_pre.get("x", -1), found_pre.get("y", -1)
            post = None
            for _ in range(8):
                time.sleep(0.25)
                post = self.q(self.h('found_check', unit_id, fx, fy, pid=pid))
                if post.get("city"):
                    break
            if post and post.get("city"):
                r["city"] = post["city"]
                r["consumed"] = not post.get("unit_exists")
            else:
                r["ok"] = False
                r["err"] = "MISSION_FOUND was accepted but no city appeared on the settler's plot"
            return r
        if religious and before.get("ok"):
            # Measure the conversion instead of trusting the accept: followers/majority in the target
            # city before vs after, and how many spreads the unit has left (0 = it is consumed).
            time.sleep(0.3)
            after = self.q(self.h('religion_target', unit_id, pid=pid))
            if not after.get("ok"):
                # Last charge consumed the unit: re-read the same city by plot instead.
                after = self.q(self.h("city_religion_at", before.get("x", -1), before.get("y", -1),
                                      before.get("unit_religion", -1), pid=pid))
                if after.get("ok"):
                    after["spreads_left"] = 0
                r["consumed"] = True
            eff = spread_effects(before, after)
            if eff.get("gained_followers") is False and (after.get("spreads_left") == before.get("spreads_left")):
                r["ok"] = False
                r["err"] = "mission accepted but nothing changed (no charge used, no new followers) -- is the unit adjacent to or inside the city, with moves left?"
            r["effects"] = eff
        if build is not None:
            if r.get("buildtype", -1) != -1 or r.get("completed"):
                return r
            time.sleep(0.3)
            chk = self.q(self.h('unit_pos', unit_id, pid=pid))
            if chk.get("ok") and chk.get("buildtype", -1) == -1:
                return {"ok": False, "err": "mission accepted but did not start a build (bad build type for this tile/unit?)"}
            return r
        # Report the unit's state after the mission so the caller need not re-read units(): a Great
        # Person mission (MISSION_GIVE_POLICIES / CREATE_GREAT_WORK / BUILD_ACADEMY...) consumes the
        # unit, and otherwise moves/position tell whether the order actually took. Inside a batch the read
        # is deferred to one query for every order of the batch (read_after_batch).
        if deferring_after_reads():
            r["after_pending"] = {"unit_id": unit_id, "mission": mission, "kind": "pos"}
            return r
        time.sleep(AFTER_READ_DELAY)
        after = self.q(self.h('unit_pos', unit_id, pid=pid))
        return self._apply_unit_after(r, mission, after, unit_id)

    def _concert_tour_preview(self, unit_id: int, pid: int | None) -> dict | None:
        """What a concert tour from the unit's plot would do (great_people.lua): tourism, the receiving civ, the share
        the other civs get; `legal_here` false with `here` when the plot's owner is not another major civ. None when
        the read fails (the mission then runs unmeasured, as before)."""
        try:
            r = self.q(self.h('concert_tour_preview', int(unit_id), pid=pid))
        except (TunerdError, AttributeError):
            return None
        return r if isinstance(r, dict) and r.get("ok") else None

    def _note_spent(self, unit_id, what) -> None:
        """Remember a unit my own order consumed, for the digest. The engine reports a consumed unit's
        destruction only at the turn end (delayed death), after `turn_end`, where the digest could not tell
        it from a loss: live Assyria t98 and t108 (2026-10-11), a Missionary's last spread and a Work Boat's
        fishing boats came as bare unit_destroyed rows and each woke a quiet run."""
        if isinstance(unit_id, int) and not isinstance(unit_id, bool):
            self.__dict__.setdefault("_spent_by_order", {})[unit_id] = str(what)

    def _apply_unit_after(self, r: dict, mission: str, after: dict, unit_id: int | None = None) -> dict:
        """Fold a unit_pos reading taken after `mission` into its result `r`."""
        if isinstance(after, dict) and after.get("ok"):
            r.update({k: after[k] for k in ("x", "y", "moves", "activity", "activity_name") if k in after})
            # A route the engine drops ("Route to cancelled!": no path, or nothing left to build on it) leaves the
            # worker AWAKE; the bare ok:true read like it was on its way (live t96, Agaidika -> capital).
            if mission == "MISSION_ROUTE_TO" and after.get("activity_name") == "AWAKE" and after.get("buildtype", -1) == -1:
                r["ok"] = False
                r["err"] = ("the engine dropped the route (no path to that plot, or no road left to build on the way); "
                            "move the worker onto each missing plot and use BUILD_ROAD")
            # A sleep or fortify given to a unit with no moves left is recorded as HOLD (this turn's skip), not as
            # SLEEP_OR_FORTIFY: the unit is back in todo next turn (live t182-t190, Venice's idle workers slept at
            # 0 moves woke every turn; slept with moves left they stayed asleep).
            if mission in ("MISSION_SLEEP", "MISSION_FORTIFY", "MISSION_ALERT") and after.get("activity_name") == "HOLD":
                r["note"] = ("recorded as HOLD, a skip for this turn only (the unit had no moves left): it wakes next "
                             "turn; give the order again then, with moves left, for a lasting sleep")
            # A one-shot Great Person mission spends the unit; one that leaves it standing did nothing. The
            # engine accepts the push and records HOLD, like a pillage at 0 moves (live t205: a Great Musician
            # moved onto Shoshone land with its last move, MISSION_ONE_SHOT_TOURISM answered ok, and the unit
            # was still there with the mission on offer -- no tourism happened).
            if mission in ONE_SHOT_GP_MISSIONS and r.get("ok", True):
                r["ok"] = False
                r["consumed"] = False
                moves = after.get("moves")
                why = ("it had no moves left this turn" if moves == 0 else
                       "the engine did not carry it out (not in a plot where it is legal, or the unit is busy)")
                r["err"] = (f"{mission} was sent but the unit still stands at ({after.get('x')}, {after.get('y')}) "
                            f"with {moves} moves: {why}; "
                            + ("give the mission again next turn before moving" if moves == 0 else
                               "check state(what='unit', id, view='actions') and the unit's plot, then try again"))
        else:
            r["consumed"] = True
            self._note_spent(unit_id, mission)
        return r

    @staticmethod
    def _apply_automate_after(mission: str, chk: dict) -> dict:
        """The result of an AUTOMATE_* order from the automate_check reading that followed it."""
        if _automate_landed(chk):
            return {"ok": True, **{k: v for k, v in chk.items() if k != "ok"}}
        return {"ok": False, "err": f"{mission} was sent but the unit is not automated after 3 s"}

    def read_after_batch(self, pending: list[dict], pid: int | None = None) -> list[dict]:
        """The read-backs a batch deferred (`after_pending` markers: unit_id, mission, kind), in one tuner trip:
        one unit_pos / automate_check per marker, in order. An automate that has not landed by then (the last
        order of the batch, pushed a moment ago) is re-read on its own until it has, up to 3 s."""
        if not pending:
            return []
        p = self._pid(pid)
        fn = {"automate": "automate_check", "pos": "unit_pos"}
        calls = [(fn.get(m.get("kind"), "unit_pos"), int(m["unit_id"])) for m in pending]
        time.sleep(AFTER_READ_DELAY)
        rows = self.q(self.hs(calls, pid=p))
        rows = list(rows) if isinstance(rows, list) else []
        rows += [{}] * (len(pending) - len(rows))
        for i, m in enumerate(pending):
            if m.get("kind") == "automate" and not _automate_landed(rows[i]):
                rows[i], _ = self._settle(lambda uid=m["unit_id"]: self.q(self.h('automate_check', int(uid), pid=p)),
                                          _automate_landed, timeout=3.0, poll=0.1, initial=rows[i])
        return rows

    def apply_after(self, r: dict, marker: dict, after: dict) -> dict:
        """Finish a batch order's result `r` from the reading its marker asked for."""
        if marker.get("kind") == "automate":
            out = self._apply_automate_after(marker.get("mission", "AUTOMATE"), after if isinstance(after, dict) else {})
            r.pop("after_pending", None)
            r.update(out)
            return r
        r.pop("after_pending", None)
        return self._apply_unit_after(r, marker.get("mission", ""), after, marker.get("unit_id"))

    def _with_target_result(self, x: int, y: int, act, pid: int | None = None, settle: float = 2.0) -> dict:
        """Run an attack `act()` against plot (x, y) and attach what happened to the target: `target_before`,
        `target_after` (units/city on the plot with hp), `damage_dealt`, `killed`. The engine applies the
        attack asynchronously (a net message), so this polls until the plot's occupants change or `settle`
        seconds pass -- an unchanged reading is reported as-is, never guessed at."""
        before = self.plot_units(x, y, pid)
        r = act()
        if not r.get("ok"):
            return r
        r["target_before"] = before
        after, _ = self._settle(lambda: self.plot_units(x, y, pid), lambda a: a != before, timeout=settle, initial=before)
        r["target_after"] = after
        bu = {u["id"]: u for u in before.get("units", [])}
        au = {u["id"]: u for u in after.get("units", [])}
        if bu:
            killed_rows = [u for i, u in bu.items() if i not in au and u.get("owner") != self._pid(pid)]
            killed = [u.get("type") for u in killed_rows]
            dmg = [bu[i]["hp"] - au[i]["hp"] for i in bu if i in au]
            if killed:
                r["killed"] = killed
                # A kill used to omit damage_dealt (city strike that finishes a unit). The
                # remaining hp on the vanished defender is what the combat banner shows.
                dmg.extend(u.get("hp") or 0 for u in killed_rows)
            if dmg:
                r["damage_dealt"] = max(dmg)
        if before.get("city") and after.get("city"):
            r["city_damage_dealt"] = before["city"]["hp"] - after["city"]["hp"]
        if after == before:
            r["note"] = "target unchanged after the attack settled; it may not have been visible, or the attack did not resolve"
        return r

    def choose_promotion(self, unit_id: int, promotion: str, pid: int | None = None) -> dict:
        """Pick a promotion for a unit with ENDTURN_BLOCKING_UNIT_PROMOTION, e.g. PROMOTION_SHOCK_1.
        Sent as the unit panel's DO_COMMAND; confirmed by polling the unit's level/promotion (<= 3 s)."""
        r = self._order(self.h('choose_promotion', unit_id, promotion, pid=pid))
        if not r.get("ok") or not r.get("pending"):
            return r
        r.pop("pending", None)
        pr_id = r.pop("promotion_id", -1)
        chk = None
        for _ in range(12):
            time.sleep(0.25)
            chk = self.q(self.h('promotion_check', unit_id, pr_id, pid=pid))
            if not chk.get("ok") or chk.get("has") or (chk.get("level") or 0) > (r.get("level_before") or 0):
                break
        if chk and chk.get("ok"):
            r.update({k: chk.get(k) for k in ("level", "has", "hp", "promotion_ready")})
        # PROMOTION_INSTA_HEAL is spent on the spot, never held: the level-up is the proof it applied
        # (live 2026-09-18: 42 -> 92 hp, level 2, reported as a failure).
        applied = bool(chk and (chk.get("has") or (chk.get("level") or 0) > (r.get("level_before") or 0)))
        if not applied:
            r["ok"] = False
            r["err"] = "COMMAND_PROMOTION was sent but the unit does not have the promotion after 3 s"
            return r
        if chk and not chk.get("has"):
            # GitLab #107 (Maya t15): has=false after an instant heal read as a failure.
            r["instant"] = True
            r["note"] = "an instant promotion (the heal) is spent on the spot and never held: has=false is expected, the level rose"
        if chk and chk.get("promotion_ready"):
            # GitLab #118 (Maya t165-t200): a gifted unit with two banked promotions; the second pick had no rows and
            # the next finish was refused on the promotion blocker.
            try:
                more = self.todo_actions([unit_id], pid=pid)
                rows = next((u.get("promotions") for u in (more.get("units") or []) if u.get("id") == unit_id), None)
            except Exception:
                rows = None
            r["next_promotion"] = {"note": "another promotion is banked on this unit: pick again before the turn ends",
                                   **({"promotions": rows} if rows else {})}
        return r

    def upgrade_unit(self, unit_id: int, pid: int | None = None) -> dict:
        """Upgrade a unit for gold along its upgrade path (Warrior -> Swordsman ...). The engine
        replaces the unit: the result's `unit_id` is the NEW id, `old_unit_id` the one passed in.
        Sent as the unit panel's DO_COMMAND; confirmed by polling the plot for the new unit (<= 3 s).
        `carried_over` names the assignments and the open order moved onto the new id (carry_unit_over)."""
        r = self._order(self.h('upgrade_unit', unit_id, pid=pid))
        if not r.get("ok") or not r.get("pending"):
            return r
        r.pop("pending", None)
        ut, old_type = r.pop("target_type_id", -1), r.pop("old_type_id", -1)
        chk = None
        for _ in range(12):
            time.sleep(0.25)
            chk = self.q(self.h('upgrade_unit_check', unit_id, r.get('x', -1), r.get('y', -1), ut, old_type, pid=pid))
            if chk.get("unit_id") is not None:
                break
        if chk:
            r.update({"unit_id": chk.get("unit_id"), "type": chk.get("type"), "gold": chk.get("gold"),
                      "old_still_exists": chk.get("old_still_exists")})
            if chk.get("unit_id") is not None and not chk.get("old_still_exists"):
                self._note_spent(unit_id, f"upgraded to {chk.get('type')} (new id {chk.get('unit_id')})")
        if not (chk and chk.get("unit_id") is not None):
            r["ok"] = False
            r["err"] = "COMMAND_UPGRADE was sent but no upgraded unit appeared on the plot within 3 s"
            return r
        # The notebook follows the unit: its assignments and its open order name the new id from here on
        # (live England t206-t214: two upgraded units read "gone" in their assignments for eight turns).
        try:
            carried = self.carry_unit_over(unit_id, chk["unit_id"])
        except Exception as e:   # a notebook problem never loses the upgrade's reply
            carried = {"err": f"{type(e).__name__}: {e}"}
        if carried:
            r["carried_over"] = carried
        return r

    def disband_unit(self, unit_id: int, pid: int | None = None) -> dict:
        """Disband a unit (COMMAND_DELETE). Irreversible; frees maintenance and strategic resources.
        The engine deletes the unit on its next tick, so the result is confirmed by polling (<= 3 s)."""
        r = self._order(self.h('disband_unit', int(unit_id), pid=pid))
        if not r.get("ok") or not r.get("pending"):
            return r
        before = r.pop("before", None)
        r.pop("pending", None)
        chk = None
        for _ in range(12):
            time.sleep(0.25)
            chk = self.q(self.h('disband_unit_check', int(unit_id), pid=pid))
            if chk.get("gone"):
                break
        after = {"units": chk.get("units"), "strategic": chk.get("strategic")} if chk else None
        r["ok"] = bool(chk and chk.get("gone"))
        if not r["ok"]:
            r["err"] = "COMMAND_DELETE was sent but the unit still exists after 3 s"
        r["effects"] = {"before": before, "after": after}
        return r

    def unit_mission_targets(self, unit_id: int, mission: str, offset: int = 0, limit: int = 100,
                             pid: int | None = None) -> dict:
        return A.mission_target_rows(self.q(self.h('unit_mission_targets', int(unit_id), mission, int(offset), int(limit), pid=pid)))

    def available_unit_actions(self, unit_id: int, pid: int | None = None) -> dict:
        """Currently legal unit-panel actions for this unit (missions, builds, commands, promotions).

        Selection-free: uses CanStartMission/CanBuild/CanDoCommand so catalog reads do not
        UI.SelectUnit (that call flips the live 2D/3D map view).
        """
        return A.annotate_unit(self.q(self.h('available_unit_actions', unit_id, pid=pid)), unit_id=unit_id)

    def todo_actions(self, unit_ids: list[int] | None = None, full: bool = False, pid: int | None = None,
                     detail: str | None = None, limit: int | None = None) -> dict:
        """Legal actions for many units in one read: every unit still needing orders plus every unit with a
        promotion waiting when `unit_ids` is empty, else exactly those. One tuner query instead of one per
        unit (live S1 t270: 38 units, one available_unit_actions round-trip each).

        `detail` (#35): "normal" (the default, the rows as before), "full" (= `full=True`: the computed help
        line on every action row) or "summary" (see `_summary_unit_row`: one short row per unit plus the exact
        arguments that fetch the rest). Every level is cut from the same one Lua read, so the facts and the
        tuner cost are identical; only the reply's size differs. `limit` returns the first N units (todo order)
        and lists the rest under `omitted` with the arguments that fetch them -- a unit is never dropped
        silently. Every reply carries `detail`, `n` (total) and `returned`."""
        level = detail or ("full" if full else "normal")
        if level not in TODO_DETAIL_LEVELS:
            return {"ok": False, "err": f"detail must be one of {', '.join(TODO_DETAIL_LEVELS)}, not {detail!r}"}
        if full and level != "full":
            return {"ok": False, "err": f"full=true asks for detail='full' but detail={detail!r} was passed; pass one"}
        if limit is not None and int(limit) < 1:
            return {"ok": False, "err": "limit must be 1 or more (leave it out for every unit)"}
        ids = [int(i) for i in unit_ids] if unit_ids else None
        r = self.q(self.h('todo_actions', ids, bool(level == 'full'), pid=pid),
                   timeout=180)
        if not isinstance(r, dict) or not r.get("ok"):
            return r
        rows = r.get("units") or []
        r["detail"] = level
        if limit is not None and len(rows) > int(limit):
            rest = rows[int(limit):]
            rows = rows[:int(limit)]
            rest_ids = [u.get("id") for u in rest]
            r["omitted"] = {"count": len(rest_ids), "ids": rest_ids,
                            "args": {"unit_ids": rest_ids, "detail": level}}
        if level == "summary":
            rows = [_summary_unit_row(u) for u in rows]
            r["routine_actions"] = list(ROUTINE_ACTIONS)
            r["drill_down"] = {**A.act("todo_actions", unit_ids=[u.get("id") for u in rows], detail="normal"),
                               "note": "any subset of these ids; detail='full' adds the computed help lines"}
        else:
            rows = [A.annotate_unit(u) for u in rows]   # `call` beside every action, target and promotion (#47)
        r["units"] = rows
        r["returned"] = len(rows)
        if ids is None and not rows:
            # GitLab #126 (Siam t10): an empty list with source todo while two units existed, and no word on where
            # the units are.
            r["note"] = ("no unit awaits orders this turn (units on standing moves or automated are in todo.ongoing); "
                         "every unit: state(what='units'); one unit's actions: state(what='unit', id, view='actions')")
        return r
