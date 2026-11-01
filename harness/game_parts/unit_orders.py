"""Standing orders: give_order and the runner that advances each order at the start of a turn (harness/orders.py holds the step logic)."""
from __future__ import annotations

from collections.abc import Callable

from .. import affordances as AF

from ..client import TunerdError

from .support import plain_text


class UnitOrdersMixin:
    """Standing orders: give_order and the runner that advances each order at the start of a turn (harness/orders.py holds the step logic).

    A part of harness.game.Game (see harness/game_parts/__init__.py); `self` is the whole Game."""

    # ------------------------------------------------------------ conditional orders (#32)
    def order_facts(self, orders: list[dict], extra_builds: list[dict] | None = None,
                    extra_dests: list[dict] | None = None) -> dict:
        """One runtime read of what `orders` need (harness/orders.py `spec`)."""
        from .. import orders as O
        sp = O.spec(orders)
        if extra_builds:
            sp["builds"] = sp.get("builds", []) + extra_builds
        if extra_dests:
            sp["dests"] = sp.get("dests", []) + extra_dests
        facts = self.q(self.h('order_facts', sp))
        return facts if isinstance(facts, dict) else {}

    def give_order(self, unit_id: int, steps, interrupt=None, purpose: str = "", replace_id: int | None = None,
                   start: bool = True) -> dict:
        """Store a conditional order for one of my units (harness/orders.py) and, with `start`, run it at once:
        steps are issued one after another through move_unit / unit_mission until one has to wait (walking,
        building, healing, out of moves) or something pauses the order. A first step that could not be issued
        now (an illegal destination, an unknown build, a unit that cannot build there) refuses the order and
        stores nothing. Hostiles already in sight within the interrupt radius are acknowledged: only new ones
        pause it."""
        from .. import assignments as A
        from .. import orders as O
        try:
            steps = O.normalize_steps(steps)
            intr = O.normalize_interrupt(interrupt)
            purpose = O.clean_purpose(purpose)
            uid = O._int(unit_id, "unit_id")
        except O.OrderError as e:
            return {"ok": False, "err": str(e)}
        probe = {"id": 0, "unit": {"id": uid}, "steps": steps, "step": 0, "interrupt": intr}
        checks = [{"unit_id": uid, "build": s["build"], "x": s.get("x", -1), "y": s.get("y", -1)}
                  for s in steps if s["kind"] == "build"]
        later = [{"unit_id": uid, "x": s["x"], "y": s["y"]} for s in steps[1:] if s["kind"] == "move"]
        facts = self.order_facts([probe], extra_builds=checks, extra_dests=later)
        r = (facts.get("units") or {}).get(str(uid)) or {}
        if r.get("missing") or not r.get("type"):
            return {"ok": False, "err": f"unit {uid} is not mine now (state(what='units') lists my ids)"}
        unknown = [s["build"] for s in steps if s["kind"] == "build"
                   and ((facts.get("builds") or {}).get(f"{uid}:{s['build']}") or {}).get("known") is False]
        if unknown:
            return {"ok": False, "err": f"not a build in this game: {', '.join(unknown)} (state(what='unit', view='actions') names "
                                        "the BUILD_* a unit can start)"}
        # A later move step onto a plot no unit can ever enter would only pause the order when its turn came
        # (live Assyria t16: "heal, move to (13,28), hold" healed first and then paused on a mountain). The plot
        # facts that cannot change are read now; occupants, borders and the fog are left to the step's own turn.
        for i, s in enumerate(steps[1:], 2):
            if s["kind"] != "move":
                continue
            why = ((facts.get("dests") or {}).get(f"{uid}:{s['x']},{s['y']}") or {}).get("refusal") or ""
            if any(w in why for w in ("mountain", "impassable", "off the map")):
                return {"ok": False, "err": f"step {i} ({O.step_label(s)}) can never run: {why}",
                        "hint": "replace that plot (state(what='unit', view='tactical') shows what a move allows)",
                        "actions": [AF.act("tactical_view", unit_id=uid)]}
        for s in steps:
            if s["kind"] == "build" and s.get("x") is None:
                s["x"], s["y"] = r["x"], r["y"]   # no move before it: the build is where the unit stands
        probe["unit"] = A.fingerprint_unit(r)
        acked = [O.hostile_key(h) for h in r.get("hostiles") or [] if (h.get("distance") or 99) <= intr["hostile_within"]]
        probe["acked"] = acked
        turn = facts.get("turn")
        if start:
            d = O.decide(probe, facts, turn)
            if d["do"] in ("pause", "fail") and d.get("kind") in ("destination", "enemy_on_destination", "prerequisite",
                                                                   "unknown_build"):
                return {"ok": False, "err": f"step 1 ({O.step_label(steps[0])}) cannot run now: {d['reason']}",
                        **({"hint": d["hint"]} if d.get("hint") else {})}
        rec = {"unit": probe["unit"], "steps": steps, "interrupt": intr, "acked": acked,
               "seen": {"hp": r.get("hp"), "x": r.get("x"), "y": r.get("y")}}
        if purpose:
            rec["purpose"] = purpose
        nb = self.notebook()
        res = nb.add_order(rec, turn if isinstance(turn, int) else -1, replace_id=replace_id)
        if not res.get("ok"):
            return res
        old = res.get("replaced_order")
        if old and old["unit"]["id"] != uid:
            self._release_standing_move(old)
        o = res["order"]
        out: dict = {"ok": True}
        if res.get("replaced") is not None:
            out["replaced"] = res["replaced"]
        if acked:
            out["acknowledged_hostiles"] = [h for h in r.get("hostiles") or [] if O.hostile_key(h) in acked]
        if start:
            o, did = self._run_order(nb, o, "given", facts)
            if did:
                out["did"] = did
            seen = o.get("seen") or {}
            if seen.get("x") is not None:
                out["at"] = {"x": seen["x"], "y": seen.get("y")}   # where the run left the unit (#182)
        # A unit on automation (a Worker on AUTOMATE_BUILD) keeps it until a move_unit / unit_mission replaces it.
        # An order whose first step could only wait (no moves left this turn, or start=False) issued nothing, and
        # the game's automation then walked the unit away at the next turn start, before the harness ran the
        # order (Grok, Venice/Mongolia 2026-09-27). The order is a claim on the unit: it leaves automation now.
        if not o.get("issued_count") and o.get("status") in O.OPEN and self._stop_automation(uid):
            out["automation_stopped"] = True
        out["order"] = O.row(o)
        return plain_text(out)

    def _stop_automation(self, unit_id: int) -> bool:
        """COMMAND_STOP_AUTOMATION for one of my units the game is automating: True when it was automated and
        the command took, False when it was not automated (nothing sent)."""
        auto = self.q(self.h("unit_is_automated", int(unit_id)))
        if auto is not True:
            return False
        r = self.unit_mission(int(unit_id), "COMMAND_STOP_AUTOMATION")
        return bool(isinstance(r, dict) and r.get("ok"))

    def orders(self, status: str = "open") -> dict:
        """My orders as stored (no game read): open (active and paused), closed, or all."""
        from .. import orders as O
        if status not in ("open", "closed", "all"):
            return {"ok": False, "err": "status must be open, closed or all"}
        nb = self.notebook()
        rows = [O.row(o) for o in nb.orders(status)]
        return plain_text({"ok": True, "game": nb.key, "orders": rows, "count": len(rows)})

    def resume_order(self, order_id: int) -> dict:
        """Hand a paused order back its unit and run it now (an active one just runs now). The hostiles in sight
        and the unit's hp are taken as seen, so only something new pauses it again; every step is re-checked
        against the board first, so a step completed meanwhile is not issued twice."""
        from .. import orders as O
        nb = self.notebook()
        o = next((x for x in nb.orders("all") if x.get("id") == order_id), None)
        if o is None or o.get("status") not in O.OPEN:
            return {"ok": False, "err": f"no open order {order_id}" + (f" (it is {o.get('status')})" if o else ""),
                    "open_ids": [x.get("id") for x in nb.orders("open")]}
        facts = self.order_facts([o])
        u = (facts.get("units") or {}).get(str(o["unit"]["id"])) or {}
        was = o.get("pause")
        turn = facts.get("turn")
        o["status"] = "active"
        o.pop("pause", None)
        o.pop("inflight", None)
        # A resume is a fresh start for the current step: the plot the step was last issued from is forgotten,
        # whatever paused it. Live Assyria t53: the Settler's move had been issued from Assur at t51, paused on a
        # hostile, the unit was walked back into Assur by hand, and the resume read the same plot two turns later
        # as "no progress ... the engine finds no path" without issuing anything (a direct move_unit then walked).
        o.pop("issued", None)
        o.pop("blocked", None)
        if isinstance(turn, int) and isinstance(o.get("updated_turn"), int) and turn < o["updated_turn"]:
            o["updated_turn"] = turn
        if not u.get("missing"):
            o["acked"] = sorted(set(o.get("acked") or []) | {O.hostile_key(h) for h in u.get("hostiles") or []})
            o["seen"] = {"hp": u.get("hp"), "x": u.get("x"), "y": u.get("y")}
        o.setdefault("history", []).append({"turn": turn, "what": "resumed" + (f" after {was['kind']}" if was else "")})
        o, did = self._run_order(nb, o, "resumed", facts)
        out = {"ok": True, "order": O.row(o)}
        if did:
            out["did"] = did
        return plain_text(out)

    def cancel_order(self, order_id: int, note: str = "") -> dict:
        """Close an open order as cancelled. The standing move it had issued is dropped too (the unit stops where
        it is next turn); anything else the unit is doing (a build, fortified) is left as it is."""
        from .. import orders as O
        try:
            note = O.clean_text(note, O.PURPOSE_MAX, "note")
        except O.OrderError as e:
            return {"ok": False, "err": str(e)}
        nb = self.notebook()
        o = next((x for x in nb.orders("all") if x.get("id") == order_id), None)
        if o is None or o.get("status") not in O.OPEN:
            return {"ok": False, "err": f"no open order {order_id}" + (f" (it is {o.get('status')})" if o else ""),
                    "open_ids": [x.get("id") for x in nb.orders("open")]}
        released = self._release_standing_move(o)
        turn = o.get("updated_turn")
        o.update({"status": "cancelled", "closed_turn": turn})
        o.pop("state", None)
        o.setdefault("history", []).append({"turn": turn, "what": "cancelled" + (f": {note}" if note else "")})
        nb.put_order(o)
        out = {"ok": True, "cancelled": order_id, "open": len(nb.orders("open"))}
        if released:
            out["standing_move_dropped"] = released
        return out

    def order_holding(self, unit_id: int) -> int | None:
        """The id of the open order that owns `unit_id` now (stored state, no game read); None when none does."""
        try:
            return next((x["id"] for x in self.notebook().orders("open") if x["unit"]["id"] == int(unit_id)), None)
        except (TunerdError, OSError, ValueError, KeyError, TypeError):
            return None

    def direct_command(self, unit_id: int, tool: str, command: Callable[[], dict]) -> dict:
        """Run a direct command to one of my units (`command`, the move / mission call) under the one-owner rule
        (#32): when it is accepted, the order that held the unit BEFORE it is taken (note_manual_order) and the
        reply says so (`order_paused` / `order_replaced`). An order the command itself creates -- a MISSION_BUILD
        on another plot becomes a walk-then-build order -- is the command's own and stays active (GitLab #182,
        hotseat Celts t18: the remote farm's order 1 was paused by the very reply that created it)."""
        held = self.order_holding(unit_id)
        r = command()
        if held is not None and isinstance(r, dict) and r.get("ok"):
            took = self.note_manual_order(unit_id, tool, order_id=held)
            if took:
                r["order_replaced" if took.get("status") == "replaced" else "order_paused"] = took   # replaced: #143
        return r

    def note_manual_order(self, unit_id: int, tool: str, order_id: int | None = None) -> dict | None:
        """A direct order to a unit an open order owns takes the unit. An active order pauses (never fights the
        command; resume hands the unit back). A paused order had already given the unit up: the direct order
        replaces it, and it closes as `replaced` (GitLab #143, Maya t234: a Musician's paused order kept its old
        destination and the todo's stalled_mission row after a direct move had taken the unit elsewhere).
        `order_id` names the order that held the unit when the command was given (direct_command reads it first);
        an order opened since is left alone. None takes whichever open order holds the unit. The answer names
        what happened; None when no such order is open."""
        try:
            nb = self.notebook()
            o = next((x for x in nb.orders("open") if x["unit"]["id"] == int(unit_id)
                      and (order_id is None or x.get("id") == order_id)), None)
        except (TunerdError, OSError, ValueError, KeyError, TypeError):
            return None
        if o is None:
            return None
        if o.get("status") == "paused":
            turn = o.get("updated_turn")
            o.update({"status": "replaced", "closed_turn": turn, "state": "replaced"})
            o.pop("inflight", None)
            o.setdefault("history", []).append({"turn": turn, "what": f"replaced by a direct {tool}"})
            nb.put_order(o)
            return {"id": o["id"], "status": "replaced",
                    "reason": f"unit {unit_id} was given a direct order ({tool}) while order {o['id']} was paused; the order is closed"}
        o["status"] = "paused"
        o.pop("state", None)
        o["pause"] = {"kind": "manual", "turn": o.get("updated_turn"),
                      "reason": f"unit {unit_id} was given a direct order ({tool}); that command owns it now",
                      "hint": "notebook(action='resume_order') hands the unit back to this order; notebook(action='cancel_order') drops it",
                      "actions": AF.order_pause_rows(o["id"])}
        o.setdefault("history", []).append({"turn": o.get("updated_turn"), "what": f"paused: direct {tool}"})
        nb.put_order(o)
        return {"id": o["id"], "status": "paused", "reason": o["pause"]["reason"], "hint": o["pause"]["hint"],
                "actions": o["pause"]["actions"]}

    def run_orders(self, trigger: str = "turn_start") -> list[dict]:
        """Run every active order once (one read for all of them first). The rows say what each did. A paused
        order is left alone -- unless its unit is gone (consumed founding a city, killed, captured, upgraded to a
        new id): it can never resume, so it closes as `decide` says (live t83: the settler's order outlived Braga
        by six turns, listed as paused on a hostile)."""
        from .. import orders as O
        nb = self.notebook()
        active = nb.orders("active")
        paused = nb.orders("paused")
        if not active and not paused:
            return []
        facts = self.order_facts(active + paused)
        out = []
        retry = [p for p in paused if trigger == "turn_start" and O.retries_at_turn_start(p) and O._unit(p, facts)[0] is not None]
        for o in retry:
            # A destination pause tries again at the turn start by itself (#143): a fresh start for the step, as a
            # resume is; what pauses it again (the same plot still taken, a hostile) pauses it again.
            o["status"] = "active"
            was = o.pop("pause", None) or {}
            for k in ("inflight", "issued", "blocked"):
                o.pop(k, None)
            o.setdefault("history", []).append({"turn": facts.get("turn"), "what": f"retried at turn start after {was.get('kind')}"})
        for o in active + retry + [p for p in paused if O._unit(p, facts)[0] is None and p not in retry]:
            o, did = self._run_order(nb, o, trigger, facts)
            r = O.row(o)
            if did:
                r["did"] = did
            out.append(r)
        return out

    def _release_standing_move(self, o: dict) -> dict | None:
        """Drop the standing move the order's current move step issued (only that one: a destination the unit
        was given some other way is not the order's to clear)."""
        from .. import orders as O
        st = O.current(o)
        if not st or st["kind"] != "move":
            return None
        uid = int(o["unit"]["id"])
        try:
            gone = self.q(self.h("drop_pending_move_at", uid, int(st["x"]), int(st["y"])))
        except TunerdError:
            return None
        return {"x": st["x"], "y": st["y"]} if gone is True else None

    def _order_action(self, tool: str, args: dict) -> dict:
        """One step through the ordinary game-command path: the same Game calls the move_unit / unit_mission
        tools make, with their checks and verification."""
        if tool == "move_unit":
            return self.move_unit(int(args["unit_id"]), int(args["x"]), int(args["y"]))
        if tool == "unit_mission":
            r = self.unit_mission(int(args["unit_id"]), args["mission"], build=args.get("build"))
            # A hold means "stay here": the unit panel offers Fortify or Sleep, never both (Sleep is for units that
            # cannot fortify; live t44 a Scout's MISSION_SLEEP was illegal while MISSION_FORTIFY was listed).
            alt = {"MISSION_FORTIFY": "MISSION_SLEEP", "MISSION_SLEEP": "MISSION_FORTIFY"}.get(args["mission"])
            if alt and not r.get("ok") and alt in (r.get("legal_missions") or []):
                r = self.unit_mission(int(args["unit_id"]), alt)
                if r.get("ok"):
                    r["note"] = f"{args['mission']} is not offered to this unit; {alt} holds it instead"
            return r
        return {"ok": False, "err": f"not an order step: {tool}"}

    def _run_order(self, nb, o: dict, trigger: str, facts: dict | None = None) -> tuple[dict, list[str]]:
        """Carry `o` forward as far as it goes now. Every step is decided on a fresh read (the first may be
        handed in), written ahead as `inflight` before it is issued, and its answer recorded as `last`. Stops
        at the first wait, pause, failure or completion; each step is issued at most once per turn."""
        from .. import orders as O
        did: list[str] = []
        steps = o.get("steps") or []
        for _ in range(2 * len(steps) + 2):
            if facts is None:
                facts = self.order_facts([o])
            turn = facts.get("turn")
            d = O.decide(o, facts, turn)
            facts = None
            if d.get("seen"):
                o["seen"] = d["seen"]
            if isinstance(turn, int):
                o["updated_turn"] = turn
            kind = d["do"]
            if d.get("blocked"):
                o["blocked"] = d["blocked"]   # a destination held by my own unit: since when (decide pauses on the third turn)
            else:
                o.pop("blocked", None)
            hist = o.setdefault("history", [])
            if kind == "next":
                label = O.step_label(O.current(o))
                o.pop("inflight", None)
                did.append(f"{label}: done")
                hist.append({"turn": turn, "what": f"step {o.get('step', 0) + 1} done: {label}"})
                o["step"] = o.get("step", 0) + 1
                if O.current(o) is None:
                    kind = "complete"
                else:
                    o.pop("state", None)
                    nb.put_order(o)
                    continue
            if kind == "complete":
                o.update({"status": "completed", "closed_turn": turn, "state": "completed"})
                if d.get("note"):
                    o["note"] = d["note"]
                    if "consumed building" in d["note"] and hasattr(self, "_note_spent"):
                        self._note_spent((o.get("unit") or {}).get("id"), d["note"])
                hist.append({"turn": turn, "what": "completed" + (f": {d['note']}" if d.get("note") else "")})
                did.append("order complete" + (f" ({d['note']})" if d.get("note") else ""))
            elif kind == "fail":
                o.update({"status": "failed", "closed_turn": turn, "state": "failed",
                          "pause": {"kind": d.get("kind"), "reason": d["reason"], "turn": turn}})
                hist.append({"turn": turn, "what": f"failed: {d['reason']}"})
                did.append(f"failed: {d['reason']}")
            elif kind == "pause":
                self._release_standing_move(o)
                o.update({"status": "paused", "state": "paused"})
                o["pause"] = {k: d[k] for k in ("kind", "reason", "hint", "hostiles") if d.get(k)}
                o["pause"]["turn"] = turn
                o.pop("inflight", None)
                hist.append({"turn": turn, "what": f"paused ({d.get('kind')}): {d['reason']}"})
                did.append(f"paused: {d['reason']}")
                if d.get("kind") in O.DESTINATION_PAUSES:
                    did += self._skip_for_the_turn(o, turn)
            elif kind == "wait":
                o["state"] = d.get("state")
                o["note"] = d.get("note")
            elif kind == "issue":
                me = (d.get("seen") or {})
                o["inflight"] = {"turn": turn, "step": o.get("step", 0), "what": d["what"], "trigger": trigger}
                nb.put_order(o)   # written ahead: a harness that dies mid-call leaves this for the next run to see
                o["issued"] = {"turn": turn, "step": o.get("step", 0), "x": me.get("x"), "y": me.get("y")}
                try:
                    r = self._order_action(d["tool"], d["args"])
                except TunerdError as e:
                    r = {"ok": False, "err": f"the game connection failed while issuing it: {e}", "uncertain": True}
                o.pop("inflight", None)
                o["issued_count"] = o.get("issued_count", 0) + 1
                last = {"turn": turn, "what": d["what"], "ok": bool(r.get("ok"))}
                for k in ("err", "note", "arrived", "queued", "turns_left", "x", "y"):
                    if r.get(k) is not None:
                        last[k] = r[k]
                o["last"] = last
                if not r.get("ok"):
                    kind = "pause"
                    self._release_standing_move(o)
                    o.update({"status": "paused", "state": "paused"})
                    o["pause"] = {"kind": "uncertain" if r.get("uncertain") else "refused", "turn": turn,
                                  "reason": f"{d['what']} was refused: {r.get('err')}",
                                  "hint": "fix what the refusal names and notebook(action='resume_order'), or replace / cancel the order",
                                  "actions": AF.order_pause_rows(o["id"])}
                    hist.append({"turn": turn, "what": f"paused (refused): {r.get('err')}"})
                    did.append(f"{d['what']}: refused ({r.get('err')})")
                else:
                    did.append(f"{d['what']}: issued")
                    hist.append({"turn": turn, "what": f"issued {d['what']}"})
                    if O.current(o)["kind"] == "hold":
                        o["step"] = o.get("step", 0) + 1   # a hold is done once the mission is accepted
                        o.update({"status": "completed", "closed_turn": turn, "state": "completed"})
                        hist.append({"turn": turn, "what": "completed"})
                        did.append("order complete")
                        kind = "complete"
                    else:
                        nb.put_order(o)
                        continue
            if kind in ("pause", "complete", "fail") and not (kind == "complete" and d.get("note")):
                o.pop("note", None)   # the transient wait note goes; a completion's own note stays on the row
            nb.put_order(o)
            return o, did
        o.update({"state": "waiting", "note": "stopped after too many steps in one run; carries on next run"})
        nb.put_order(o)
        return o, did

    def _skip_for_the_turn(self, o: dict, turn) -> list[str]:
        """A destination pause has decided the unit cannot act this turn: skip it (MISSION_SKIP, what the end-turn
        refusal's skip_actions would do) so it never blocks the end turn (#143, Maya t216: a Worker's order paused
        on a Cannon's plot and the finish was refused with ENDTURN_BLOCKING_UNITS on that Worker). The order says
        so (`pause.skipped_turn`) and tries the destination again at the next turn start."""
        uid = (o.get("unit") or {}).get("id")
        if uid is None:
            return []
        try:
            r = self._order_action("unit_mission", {"unit_id": uid, "mission": "MISSION_SKIP"})
        except TunerdError as e:
            r = {"ok": False, "err": str(e)}
        if not r.get("ok"):
            return [f"unit {uid} not skipped: {r.get('err')}"]
        o["pause"]["skipped_turn"] = turn
        o["pause"]["hint"] = ("the unit is skipped for this turn and the order tries the destination again at the next "
                              "turn start; a direct order to the unit replaces this order, notebook(action='cancel_order') drops it")
        return [f"unit {uid} skipped for this turn"]

    def _turn_start_orders(self, ts: dict) -> dict | None:
        """The start of this seat's turn is an order's execution window: claim the turn for this process (another
        client of the seat that holds it keeps its turn, and the orders wait), then run every active order.
        None when there is no open order (no read at all)."""
        from .. import orders as O
        try:
            nb = self.notebook()
            open_ = nb.orders("open")
        except (TunerdError, OSError, ValueError):
            return None
        if not open_:
            return None
        active = [o for o in open_ if o.get("status") == "active" or O.retries_at_turn_start(o)]   # a retry issues too
        out: dict = {}
        if active:
            refused = self._claim_turn(ts, "orders")
            if refused is not None:
                out["not_run"] = "another client of this seat holds the turn; the orders run when it is mine to act"
                out["turn_claim"] = refused.get("turn_claim")
            else:
                try:
                    out["rows"] = self.run_orders("turn_start")
                except TunerdError as e:
                    out["error"] = f"orders not run: {e}"
        else:
            # Paused orders only: nothing is issued (no claim), but one whose unit is gone closes -- run_orders
            # reads the facts and `decide` fails it (live t83: a settler's order outlived the city it founded).
            try:
                out["rows"] = self.run_orders("turn_start")
            except TunerdError as e:
                out["error"] = f"orders not run: {e}"
        ran = {r["id"] for r in out.get("rows") or []}
        out.setdefault("rows", [])
        out["rows"] += [O.row(o) for o in open_ if o.get("id") not in ran]
        # Counted once the orders have run (GitLab #181): one that completed or failed just now is closed.
        return {**O.counts(out["rows"]), **out}
