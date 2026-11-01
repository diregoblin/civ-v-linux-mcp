"""The event stream: turn_digest and the combat narration built from the runtime's event records."""
from __future__ import annotations

import re

from ..client import TunerdError

from .support import plain_text

DIGEST_MAX_EVENTS = 120   # a turn's digest is ~5-15 rows; 120 is already several turns' worth (~25 KB worst case)



#: Civilians: a ruins upgrade never happens to them (GitLab #100), whatever vanished beside the alert.
NEVER_UPGRADED = frozenset({"SETTLER", "WORKER", "WORK_BOAT", "MISSIONARY", "INQUISITOR", "CARAVAN", "CARGO_SHIP",
                            "ARCHAEOLOGIST", "PROPHET"})


_ALLY_PATTERNS = (
    ("mine_gained", re.compile(r"^Now Ally of (.+?)!")),
    ("mine_lost", re.compile(r"^No longer Ally of (.+?)!")),
    ("other_gained", re.compile(r"^(.+?) now Ally of (.+?)!")),
    ("other_gained", re.compile(r"^(.+?) is now the Ally of (.+?)\.")),
    ("other_gained", re.compile(r"^(.+?) has replaced (.+?) as the Ally of (.+?)!")),
    ("other_gained", re.compile(r"^(.+?) and (.+?) now Allies!")),
)
_WAR_ON = re.compile(r"^(.+?) (?:has|have) declared war on (.+?)!")


def group_alliance_cascade(events: list[dict]) -> list[dict]:
    """Several city-state alliance notices (and the war declarations that follow an ally) of one turn become one
    `city_state_allies` row with the whole picture (GitLab #82, Assyria t251: Siam took five allies in a turn and
    the digest and the wake reasons listed ten lines, never "-10 delegates"). Two or more notices of a turn are
    grouped; a single one stays as it is."""
    by_turn: dict = {}
    for e in events:
        if e.get("kind") != "notification" or not isinstance(e.get("data"), dict):
            continue
        text = str(e["data"].get("summary") or e["data"].get("text") or "").strip()
        for what, pat in _ALLY_PATTERNS:
            m = pat.match(text)
            if m:
                by_turn.setdefault(e.get("turn"), []).append((e, what, m.groups()))
                break
        else:
            m = _WAR_ON.match(text)
            if m:
                by_turn.setdefault(e.get("turn"), []).append((e, "war", m.groups()))
    drop: set = set()
    out: list[dict] = []
    for turn, rows in by_turn.items():
        ally_rows = [r for r in rows if r[1] != "war"]
        if len(rows) < 2 or not ally_rows:
            continue
        summary: dict = {"gained": [], "lost": [], "others_gained": {}, "wars_declared": []}
        for e, what, groups in rows:
            drop.add(id(e))
            if what == "mine_gained":
                summary["gained"].append(groups[0])
            elif what == "mine_lost":
                summary["lost"].append(groups[0])
            elif what == "other_gained":
                civ, minor = groups[0], groups[-1]
                summary["others_gained"].setdefault(civ, []).append(minor)
            else:
                summary["wars_declared"].append({"by": groups[0], "on": groups[1]})
        delegates = 2 * (len(summary["gained"]) - len(summary["lost"]))
        parts = []
        if summary["lost"]:
            parts.append(f"lost {len(summary['lost'])} city-state all{'y' if len(summary['lost']) == 1 else 'ies'} ({', '.join(summary['lost'])})")
        if summary["gained"]:
            parts.append(f"gained {len(summary['gained'])} ({', '.join(summary['gained'])})")
        for civ, minors in summary["others_gained"].items():
            parts.append(f"{civ} now allied with {', '.join(minors)}")
        if summary["wars_declared"]:
            parts.append(f"{len(summary['wars_declared'])} war declaration(s) by the new allies")
        summary["delegates_change"] = delegates
        summary["summary"] = "; ".join(parts) + (f"; {delegates:+d} World Congress delegates for you (2 per ally)" if delegates else "")
        summary["notices"] = len(rows)
        first = rows[0][0]
        out.append({"kind": "city_state_allies", "turn": turn, "seq": first.get("seq"), "audience": first.get("audience"), "data": summary})
    if not drop:
        return events
    kept = [e for e in events if id(e) not in drop]
    kept.extend(out)
    kept.sort(key=lambda e: (e.get("seq") is None, e.get("seq") or 0))
    return kept

class EventsMixin:
    """The event stream: turn_digest and the combat narration built from the runtime's event records.

    A part of harness.game.Game (see harness/game_parts/__init__.py); `self` is the whole Game."""

    def turn_digest(self) -> dict:
        """events_since_last plus the notifications panel, without the panel entries the events already
        carry (live t320: all ten notifications came twice, ~5 KB) and with the game's text markup removed."""
        events = self.events_since_last()
        omitted = None
        if len(events) > DIGEST_MAX_EVENTS:
            # A cursor that has not moved for many turns (a seat whose finish_turn never completed, a long
            # idle) would hand back every event since: live t192 that was 350 rows / 75 KB. Keep the newest
            # and say what was cut; notification_log() and briefing(since="turn") still have the rest.
            cut = events[:-DIGEST_MAX_EVENTS]
            events = events[-DIGEST_MAX_EVENTS:]
            turns = [e.get("turn") for e in cut if isinstance(e.get("turn"), int)]
            by_kind: dict[str, int] = {}
            for e in cut:
                by_kind[str(e.get("kind"))] = by_kind.get(str(e.get("kind")), 0) + 1
            omitted = {"count": len(cut), "turns": [min(turns), max(turns)] if turns else None, "by_kind": by_kind,
                       "hint": f"the oldest {len(cut)} events were cut (the digest keeps the newest {DIGEST_MAX_EVENTS}): "
                               "state(what='notifications') has every notice; turn(action='briefing', since='turn') the events of this turn"}
        seen = {e["data"].get("text") for e in events if e.get("kind") == "notification" and isinstance(e.get("data"), dict)}
        notes = [n for n in self.notifications() if n.get("text") not in seen]
        if notes:
            # The panel keeps a notification live for about a turn, so one delivered as an event by the previous
            # digest came back here (live t343: "Washington has made peace with Gandhi!" twice across two
            # digests). Drop any the event log already delivered; keep the ones it never saw (pre-reload).
            try:
                delivered = set(self.q(self.h("delivered_notification_texts")) or [])
                notes = [n for n in notes if n.get("text") not in delivered]
            except (TunerdError, TypeError):
                pass
        # "Shanghai has been converted to another religion!" never says which (live t332: Catholicism;
        # t179 Machu was a follower tie so cities().religion was nil). Lua attach_conversion_banner
        # fills the city-banner tooltip at record time; this is the fallback for events recorded
        # before that hook.
        conv = [e["data"] for e in events if e.get("kind") == "notification" and isinstance(e.get("data"), dict)
                and any(k in str(e["data"].get("text", "")) for k in ("converted to another religion", "has adopted a religion"))]
        if conv:
            try:
                for d in conv:
                    if d.get("religions") is not None:
                        continue
                    banner = self.q(self.h("conversion_banner", d.get("text") or ""))
                    if isinstance(banner, dict):
                        for k in ("city_id", "x", "y", "religion", "majority", "religions", "note"):
                            if k in banner:
                                d[k] = banner[k]
            except TunerdError:
                pass
        # "Steal Technology" names the victim civ but not which tech (live t181: Inca / Sailing).
        steal_notes = [e["data"] for e in events if e.get("kind") == "notification" and isinstance(e.get("data"), dict)
                       and ("steal a technology" in str(e["data"].get("text", "")).lower()
                            or "Steal Technology" in str(e["data"].get("summary", "")))]
        if steal_notes:
            try:
                for d in steal_notes:
                    if d.get("steal_tech") is not None:
                        continue
                    attached = self.q(self.h("steal_tech_note", d.get("text") or "", d.get("summary") or ""))
                    if isinstance(attached, dict):
                        for k in ("steal_tech", "hint"):
                            if k in attached:
                                d[k] = attached[k]
            except TunerdError:
                pass
        out = {"events": events, "notifications": notes}
        if omitted:
            out["omitted"] = omitted
        return plain_text(out)

    def events_since_last(self) -> list[dict]:
        """Recorded game events since the previous call (cursor is kept inside the game's Lua state).

        `unit_destroyed` comes from SerialEventUnitDestroyed, which is a *graphics* event: it also fires
        when the engine merely rebuilds a unit's model -- every unit on an era change (live, t244: all four
        workers "destroyed" on reaching the Industrial era), a caravan starting a route, a unit being
        upgraded. So each of my own `unit_destroyed` events is checked against the live unit list here and
        relabelled `unit_graphics_reset` when the unit still exists, so a caller never mourns a live
        worker. Genuine losses keep `unit_destroyed`."""
        return self._refine_events(self.q(self.h('take_events')))

    def _refine_events(self, events: list[dict]) -> list[dict]:
        """The digest's corrections to raw runtime events, shared by turn_digest and the briefing."""
        events = list(events or [])
        # Leader lines said while the harness itself had the trade screen open (propose_deal /
        # negotiate_deal) are replies to our visit, not the AI approaching us: drop them here so the
        # digest only carries unsolicited diplomacy. relationship()'s history still keeps them.
        events = [e for e in events if not (e.get("kind") == "leader_message" and isinstance(e.get("data"), dict)
                                            and e["data"].get("harness_initiated"))]
        ids = sorted({e["data"]["unit"] for e in events
                      if e.get("kind") == "unit_destroyed" and isinstance(e.get("data"), dict)
                      and e["data"].get("player") == self.seat and isinstance(e["data"].get("unit"), int)})
        if ids:
            alive = self.q(self.h("units_alive", sorted(ids))) or []
            alive = set(alive)
            for e in events:
                if e.get("kind") == "unit_destroyed" and isinstance(e.get("data"), dict) and e["data"].get("unit") in alive:
                    e["kind"] = "unit_graphics_reset"
                    e["data"]["note"] = "unit still exists; the engine only rebuilt its model (era change, route start, upgrade)"
        # A besieged city's alerts each carry the hostiles around it (Lua attaches the list to every "City of X was
        # bombarded" line): live England t226, six bomber hits and a rocket strike on London each listed the same
        # eighteen units. One list per city per digest; the later rows point at it.
        # One list per city per TURN: a turn later the units have moved and fought (live Assyria t14: the "enemy
        # spotted near Assur" alert pointed at the t13 list, a Brute at 57 hp on a plot it had left).
        first_list: dict[tuple, int] = {}
        for e in events:
            d = e.get("data")
            if e.get("kind") != "alert" or not isinstance(d, dict) or not isinstance(d.get("hostiles"), list):
                continue
            key = (str(d.get("city") or ""), e.get("turn"))
            if key in first_list:
                del d["hostiles"]
                d["hostiles_as_in"] = first_list[key]
            else:
                first_list[key] = e.get("seq")
        events = group_alliance_cascade(events)   # GitLab #82
        return self._narrate_combat(events)

    def _narrate_combat(self, events: list[dict]) -> list[dict]:
        """Give every `combat` event a one-line `summary` ("your SCOUT (12,8) was hit by Barbarians WARRIOR
        from (13,8): -38 hp, 62 left") built from the attacker/defender rows the Lua hook captured, and
        drop the `unit_hurt` / `unit_lost` fallback rows (hp compared across the AI phase) for units a
        `combat` event already explains, so only *unexplained* losses remain."""
        def side(s: dict | None, raw_player) -> str:
            s = s or {}
            owner = s.get("owner") or f"player {raw_player}"
            name = f"{'your' if owner == 'you' else owner} {s.get('unit', 'unit (not visible)')}"
            return f"{name} ({s['x']},{s['y']})" if "x" in s else name

        def outcome(s: dict | None, dmg) -> str:
            s = s or {}
            if s.get("killed"):
                return f"-{dmg} hp, killed"
            return f"-{dmg} hp, {s['hp']} left" if "hp" in s else f"-{dmg} hp"

        # A unit of mine that disappears during MY OWN turn without a combat event was spent by my own
        # order (great person used, unit upgraded into a new id, settler founded, disband) -- live t314 the
        # digest read like four losses after one DISCOVER and three upgrades. Only a disappearance during
        # the other players' turns, or one a combat explains, stays `unit_destroyed`.
        markers = [e.get("kind") for e in events if e.get("kind") in ("turn_start", "turn_end")]
        # Where the batch starts: inside my turn, or in the other players' round. A batch with no marker
        # continues where the previous one left off (live England t224: the second finish_turn read, cut by a
        # war-declaration screen, began after the turn_end of the first and held the Pikeman's death by Rocket
        # Artillery -- "gone during your own turn with no combat"). Before the first batch, my turn.
        remembered = getattr(self, "_digest_in_my_turn", True)
        in_my_turn = remembered if not markers else markers[0] == "turn_end"
        fought = {d.get(k) for e in events if e.get("kind") == "combat" and isinstance(d := e.get("data"), dict)
                  for k in ("att_unit", "def_unit")}
        # Quick combat: the hit arrives as a damage row, not a combat row; a unit it names was in a fight
        # (kept apart from `fought`, whose damage rows are dropped as retold by a combat row).
        hit = {d.get("unit_id") for e in events if e.get("kind") == "damage" and isinstance(d := e.get("data"), dict)
               and (d.get("side") or {}).get("owner") == "you"}
        # A civilian taken is not a unit killed. The capture notice (Lua attach_capture) names the unit id
        # and tile; the bare `unit_destroyed` row for that id becomes `unit_captured` with the notice's
        # words, and the hp-compare fallback for it is dropped (live 2026-09-24 t217: Bravo's Settler came
        # as three unrelated rows).
        captured = {d.get("unit_id"): d for e in events if e.get("kind") == "notification"
                    and isinstance(d := e.get("data"), dict) and isinstance(d.get("unit_id"), int)
                    and " was captured by " in str(d.get("text", ""))}
        for e in events:
            d = e.get("data")
            if e.get("kind") == "unit_destroyed" and isinstance(d, dict) and d.get("unit") in captured:
                n = captured[d["unit"]]
                e["kind"] = "unit_captured"
                where = f" at ({n['x']},{n['y']})" if "x" in n and "y" in n else ""
                by = str(n.get("text", "")).split(" was captured by ", 1)[1].split("!", 1)[0]
                d["summary"] = f"your {n.get('unit') or d.get('unit_type') or 'unit'}{where} was captured by {by}"
                for k in ("captor", "nearest_revealed_camp", "hint"):
                    if k in n:
                        d[k] = n[k]
                fought.add(d["unit"])
        starts = None
        for e in events:
            if e.get("kind") == "turn_start":
                in_my_turn = True
            elif e.get("kind") == "turn_end":
                in_my_turn = False
            elif (e.get("kind") == "unit_destroyed" and isinstance(e.get("data"), dict)
                  and e["data"].get("player") == self.seat
                  and e["data"].get("unit") in (getattr(self, "_spent_by_order", None) or {})):
                # Consumed by my own order (Game._note_spent): the engine's delayed death reports it after
                # turn_end, where the window below would call it a loss.
                what = self._spent_by_order.pop(e["data"]["unit"])
                e["kind"] = "unit_spent"
                e["data"]["note"] = f"consumed by your own order: {what}"
                e["data"]["summary"] = f"your unit {e['data']['unit']} was consumed by your own order: {what}"
            elif (e.get("kind") == "unit_destroyed" and in_my_turn and isinstance(e.get("data"), dict)
                  and e["data"].get("player") == self.seat and e["data"].get("unit") not in fought
                  and e["data"].get("unit") not in hit):
                if starts is None:
                    try:
                        rows = self.q(self.h("route_start_rows")) or []
                    except TunerdError:
                        rows = []
                    starts = {}
                    for r in rows:
                        if isinstance(r, dict):
                            starts.setdefault(r.get("unit_id"), []).append(r)
                # The engine recycles unit ids: a route start remembered for caravan 720907 turns ago matched the
                # Foreign Legion that later carried the same id and was upgraded (live t224, Mongolia: "your CARAVAN
                # left on its trade route to Guangzhou" for an Infantry upgrade). A start explains a disappearance
                # only on the turn it was recorded.
                r = next((r for r in starts.get(e["data"].get("unit"), [])
                          if r.get("turn") is None or e.get("turn") is None or r.get("turn") == e.get("turn")), None)
                if r is not None:
                    e["kind"] = "trade_route_started"
                    e["data"]["summary"] = f"your {r.get('unit')} left on its trade route to {r.get('to')}"
                    continue
                e["kind"] = "unit_spent"
                e["data"]["note"] = "gone during your own turn with no combat: used up, upgraded (new unit id) or disbanded by your order"
        self._digest_in_my_turn = in_my_turn
        # A Settler that vanished the turn a city of mine appeared founded it (live Assyria t0: the digest read
        # "gone during your own turn with no combat" for the Settler beside city_created for Assur). The city row
        # names the settler; the spent row goes.
        founded_ids: set = set()
        cities_new = [e for e in events if e.get("kind") == "city_created" and isinstance(e.get("data"), dict)
                      and e["data"].get("player") == self.seat and "settler" not in e["data"]]
        for e in events:
            d = e.get("data")
            if e.get("kind") != "unit_spent" or not isinstance(d, dict) or d.get("unit_type") != "SETTLER":
                continue
            c = next((c for c in cities_new if c.get("turn") is None or e.get("turn") is None or c.get("turn") == e.get("turn")), None)
            if c is None:
                continue
            cities_new.remove(c)
            cd = c["data"]
            cd["settler"] = d.get("unit")
            where = f" at ({cd['x']},{cd['y']})" if "x" in cd and "y" in cd else ""
            cd["summary"] = f"your SETTLER founded {cd.get('name') or 'a city'}{where}"
            founded_ids.add(d.get("unit"))
        # Ancient Ruins that upgrade a unit ("Your Unit equips itself with advanced weapons found in the ruins!")
        # replace it with a new unit of the next type, same plot, same wounds: the engine fires a unit_destroyed for
        # the old id and SerialEventUnitSetDamage for the new one as it inherits the damage (live Assyria t37: the
        # Scout at (18,31) became an Archer and the digest read "took 8 damage" twice and "gone during your own turn
        # with no combat"). The spent row becomes the upgrade; the inherited-damage rows go.
        inherited: set = set()
        if any(e.get("kind") == "alert" and "advanced weapons" in str((e.get("data") or {}).get("text", ""))
               for e in events if isinstance(e.get("data"), dict)):
            for e in events:
                d = e.get("data")
                if e.get("kind") != "unit_spent" or not isinstance(d, dict) or "x" not in d or "y" not in d:
                    continue
                if d.get("unit") in founded_ids or d.get("unit_type") in NEVER_UPGRADED \
                        or str(d.get("unit_type") or "").startswith("GREAT_"):
                    # GitLab #100 (Maya t0): the Settler that founded Palenque the same turn a Warrior took ruins read
                    # "found advanced weapons in the ruins". Ruins upgrade military units only.
                    continue
                reborn = [f for f in events
                          if f.get("kind") == "damage" and isinstance(fd := f.get("data"), dict)
                          and fd.get("unit_id") != d.get("unit")
                          and (s := fd.get("side") or {}).get("owner") == "you"
                          and (s.get("x"), s.get("y")) == (d["x"], d["y"])
                          and (f.get("turn") is None or e.get("turn") is None or f.get("turn") == e.get("turn"))
                          and isinstance(s.get("max_hp"), int) and s.get("hp") == s["max_hp"] - (fd.get("dmg") or 0)]
                e["kind"] = "unit_upgraded"
                d.pop("note", None)
                d["how"] = "ruins"
                was = d.get("unit_type") or "unit"
                if d.get("new_unit") is not None:
                    # GitLab #169 (Maya t5): the order's read-back found the successor (successors.lua) and put it on
                    # this row with the ruins plot; the row says who moved the unit there, never a guess.
                    who = {"order": "your move", "standing_move": "its standing move"}.get(d.get("moved_by"))
                    how = f" ({who} took it there)" if who else ""
                    d["summary"] = (f"your {was} found advanced weapons in the ruins at ({d['x']},{d['y']}){how} and "
                                    f"became a {d.get('new_type') or 'stronger unit'} (new id {d['new_unit']})")
                    inherited.update(id(f) for f in reborn)
                elif reborn:
                    s = reborn[0]["data"]["side"]
                    d["new_unit"], d["new_type"] = reborn[0]["data"].get("unit_id"), s.get("unit")
                    d["hp"] = s.get("hp")
                    d["summary"] = (f"your {was} at ({d['x']},{d['y']}) found advanced weapons in the ruins and became "
                                    f"a {s.get('unit')} (new id {d['new_unit']}, {s.get('hp')} hp kept)")
                    inherited.update(id(f) for f in reborn)
                else:
                    # #100's fallback: the unit was gone from the map inside the destroy hook, so the plot is the roster's
                    # last note of it. Automation is named only when the roster saw it moving on its own (#169: a manual
                    # move read "it moved on automation since").
                    since = ("it was moving on its own (automated or a standing move) since" if d.get("moving")
                             else "it moved since")
                    where = (f"last recorded at ({d['x']},{d['y']}); {since}, the ruins plot is where the new unit stands"
                             if d.get("plot_from") == "roster" else f"at ({d['x']},{d['y']})")
                    d["summary"] = (f"your {was} {where} found advanced weapons in the ruins and became "
                                    f"a stronger unit (state(what='units') lists the new id at that plot)")

        explained: set[int] = set(captured)
        for e in events:
            d = e.get("data")
            if e.get("kind") != "combat" or not isinstance(d, dict):
                continue
            att, dfn = d.get("attacker"), d.get("defender")
            for who, key in ((att, "att_unit"), (dfn, "def_unit")):
                if isinstance(who, dict) and who.get("owner") == "you":
                    explained.add(d.get(key))
            verb = "shot" if isinstance(att, dict) and att.get("ranged") else "attacked"
            d["summary"] = (f"{side(att, d.get('att_player'))} {verb} {side(dfn, d.get('def_player'))}: "
                            f"defender {outcome(dfn, d.get('def_dmg'))}; attacker {outcome(att, d.get('att_dmg'))}")
        # Quick combat (always on in multiplayer) fires no combat sim: the fight arrives as one `damage` row
        # per visible unit, followed by the game's own banner as an `alert` row that says who attacked whom.
        for e in events:
            d = e.get("data")
            if e.get("kind") != "damage" or not isinstance(d, dict):
                continue
            s = d.get("side") or {}
            if s.get("owner") == "you":
                explained.add(d.get("unit_id"))
            d["summary"] = f"{side(s, d.get('player'))} took {d.get('dmg')} damage: {outcome(s, d.get('dmg'))}"
        for e in events:
            d = e.get("data")
            if e.get("kind") == "civ_eliminated" and isinstance(d, dict):
                d["summary"] = (f"{d.get('civ')} ({d.get('leader')}) has been eliminated: its deals, friendships and "
                                f"votes are gone")
        # One disappearance, two rows (live t335: a caravan home from its route came as unit_lost, which explains
        # it, and unit_spent): keep the explained one.
        lost_ids = {e["data"].get("unit_id") for e in events if e.get("kind") == "unit_lost" and isinstance(e.get("data"), dict)}
        # Live Assyria t70-t71: "Filthy barbarians plundered the trade route you established between Assur and
        # M'banza-Kongo" sat in the same digest as the caravan's unit_lost row, which still said "most likely its
        # trade route ended and it is back home". The notification names the fact: the row carries it.
        plundered = [e["data"].get("text") for e in events if e.get("kind") == "notification" and isinstance(e.get("data"), dict)
                     and "plundered" in str(e["data"].get("text", "")).lower()
                     and "trade route" in str(e["data"].get("text", "")).lower()]
        out = []
        for e in events:
            d = e.get("data")
            if e.get("kind") == "unit_spent" and isinstance(d, dict) and (d.get("unit") in lost_ids or d.get("unit") in founded_ids):
                continue
            if e.get("kind") == "unit_destroyed" and isinstance(d, dict) and d.get("unit") in lost_ids \
                    and d.get("unit_type") in ("CARAVAN", "CARGO_SHIP"):
                # The AI round took it (a plunder) or its route ended there; the unit_lost row at the turn start
                # tells which, so this row is the same fact twice (GitLab #148: a route's end came as both).
                continue
            if e.get("kind") == "damage" and isinstance(d, dict) and d.get("unit_id") in fought:
                continue  # animations on: the combat row above already tells it
            if id(e) in inherited:
                continue  # the wounds a ruins upgrade carried over, told by the unit_upgraded row
            if e.get("kind") in ("unit_hurt", "unit_lost") and isinstance(d, dict):
                if d.get("unit_id") in explained:
                    continue
                if e["kind"] == "unit_hurt":
                    d["summary"] = (f"your {d.get('unit')} ({d.get('x')},{d.get('y')}) lost {d.get('hp_before', 0) - d.get('hp', 0)} hp "
                                    f"between turns ({d.get('hp')} left) with no combat seen -- look around it with state(what='map', view='window', x, y)")
                elif d.get("unit") in ("CARAVAN", "CARGO_SHIP") and plundered:
                    d["plundered"] = True
                    d["summary"] = (f"your {d.get('unit')} last at ({d.get('x')},{d.get('y')}) was plundered: {plundered[0]} "
                                    f"The unit is gone; its route slot is free again (state(what='city', id, view='production') lists a new one)")
                elif d.get("unit") in ("CARAVAN", "CARGO_SHIP"):
                    # live t324: a route ran out and the caravan came home to its city under a new unit id
                    d["summary"] = (f"your {d.get('unit')} last at ({d.get('x')},{d.get('y')}) is gone with no combat seen: "
                                    f"most likely its trade route ended and it is back home under a new id "
                                    f"(state(what='empire').idle_trade_units); a plundered route shows up as a notification")
                else:
                    d["summary"] = (f"your {d.get('unit')} last at ({d.get('x')},{d.get('y')}) is gone "
                                    f"(had {d.get('hp_before')} hp) with no combat seen")
            out.append(e)
        return out
