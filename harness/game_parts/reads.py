"""Empire-wide reads: overview, units, cities, map windows, tactical view, comparisons, the reference and notifications."""
from __future__ import annotations

from .. import affordances as A

from ..client import TunerdError
from .support import plain_text


class ReadsMixin:
    """Empire-wide reads: overview, units, cities, map windows, tactical view, comparisons, the reference and notifications.

    A part of harness.game.Game (see harness/game_parts/__init__.py); `self` is the whole Game."""

    def summary(self, pid: int | None = None) -> dict:
        r = self.q(self.h('player_summary', pid=pid))
        # A slot with no trade unit in it earns nothing and nothing else says so (live t354: Railroad raised
        # the cap 6 -> 7). used counts caravans/cargo ships alive, idle or not (the engine's
        # GetNumTradeRoutesUsed(true)); the training gate also counts trade units queued in any city
        # (trade_units_queued, runtime v252; live t139 Venice "4 of 8" refused), so free = cap - used - queued.
        # An idle unit holds one of the used slots: it is routed, never a reason to skip building.
        if isinstance(r, dict) and isinstance(r.get("trade_routes_available"), int) and isinstance(r.get("trade_routes_used"), int):
            queued = r["trade_units_queued"] if isinstance(r.get("trade_units_queued"), int) else 0
            free = r["trade_routes_available"] - r["trade_routes_used"] - queued
            idle = len(r.get("idle_trade_units") or [])
            notes = []
            if idle:
                notes.append(f"{idle} idle caravan(s) / cargo ship(s) hold a slot each while earning nothing: give them "
                             "routes (state(what='options', view='trade_routes', id) then order(to='unit', action='trade_route'))")
            # Past the slot count the engine trains a trade unit only while some city could start a new route of its
            # kind (runtime v253 trade_units_trainable / trade_units_refused; live t152: Venice 4 of 8 free, nothing
            # queued, "no available land/sea trade routes" for both). A summary from an older runtime has no gate.
            gate = r.get("trade_units_trainable") if isinstance(r.get("trade_units_trainable"), dict) else None
            refused = r.get("trade_units_refused") if isinstance(r.get("trade_units_refused"), dict) else {}
            kinds = (("caravan", "Caravan"), ("cargo_ship", "Cargo Ship"))
            if free > 0:
                r["free_trade_route_slots"] = free
                blocked = [] if gate is None else [(key, name) for key, name in kinds if gate.get(key) is not True]
                if len(blocked) < len(kinds):
                    can = " / ".join(name for key, name in kinds if (key, name) not in blocked)
                    note = f"{free} slot(s) have no trade unit yet: build or buy a {can} for each"
                    if queued:
                        note += f" ({queued} already in production)"
                    for key, name in blocked:
                        note += f" (not a {name}: {refused.get(key) or 'the engine refuses it in every city'})"
                    notes.append(note)
                else:
                    why = "; ".join(f"{name}: {refused[key]}" for key, name in kinds if refused.get(key)) \
                        or "no city can train a Caravan or Cargo Ship now"
                    r["trade_units_blocked"] = why
                    notes.append(f"{free} slot(s) have no trade unit, and the engine lets no city train one now ({why}): "
                                 "past the slot count a trade unit is trainable only while one of my cities could start a "
                                 "new route of its kind; a route ending, a city coming in range (Harbor / Caravansary extend "
                                 "it) or a new city met changes that -- nothing to build or buy for these slots")
            elif queued:
                notes.append(f"{queued} trade unit(s) in production fill the last slot(s): the engine trains no more "
                             "until a slot opens")
            if notes:
                r["trade_note"] = "; ".join(notes)
        # An unassigned spy is the espionage version of the idle caravan above: it costs nothing and
        # earns nothing, and after the notification that announced it the game never mentions it again.
        if isinstance(r, dict) and r.get("idle_spies"):
            r["spy_note"] = ("unassigned spies do nothing: state(what='options', view='spy_cities', id=<agent>) then "
                             "order(to='spy', action='move') to steal tech / rig a city-state election / defend a city")
        return r

    def units(self, pid: int | None = None) -> list[dict]:
        """Every unit I own; each row carries `actions`, the read that lists its orders (#47)."""
        return A.with_object_rows(self.q(self.h('units', pid=pid)), A.unit_rows)

    def cities(self, pid: int | None = None) -> list[dict]:
        rows = self.q(self.h('cities', pid=pid))
        for c in rows if isinstance(rows, list) else []:
            if isinstance(c, dict):
                self._normalize_production_turns(c)
        return A.with_object_rows(rows, A.city_rows)

    def city_screen(self, city_id: int, pid: int | None = None) -> dict:
        """City-view contents for one of my cities: buildings, specialists + GP meters, worked tiles,
        production queue, citizen focus, avoid-growth, buyable plots (and the red price of a tile
        this city cannot afford), and the corner meters (food, production, culture-to-border,
        gold/science/faith/tourism). cities() is the banner list."""
        r = self.q(self.h('city_screen', int(city_id), pid=pid))
        if isinstance(r, dict):
            self._normalize_production_turns(r)
        return r

    @staticmethod
    def _normalize_production_turns(row: dict) -> dict:
        """INT_MAX turns means empty queue or a process. Only a process is 'never completes'
        (live t179: Goshute's empty queue was labelled as Wealth/Research)."""
        turns = row.get("production_turns")
        if isinstance(turns, int) and turns >= 2**31 - 1:
            row["production_turns"] = None
            prod = (row.get("production") or "").strip()
            if not row.get("production_note") and prod and not row.get("needs_production"):
                row["production_note"] = "ongoing process: converts production every turn, never completes"
        return row

    def great_person_progress(self, pid: int | None = None) -> dict:
        return self.q(self.h('great_person_progress', pid=pid))

    def demographics(self, pid: int | None = None) -> dict:
        return self.q(self.h('demographics', pid=pid))

    def culture_works(self, pid: int | None = None) -> dict:
        return self.q(self.h('culture_works', pid=pid))

    def set_swappable_great_work(self, work_class: str, work_id: int = -1, pid: int | None = None) -> dict:
        """The swap tab's pull-down for one class (writing / art / artifact): put one of our works up for
        swapping, or -1 to clear the spot (Network.SendSetSwappableGreatWork)."""
        return self.q(self.h('set_swappable_great_work', work_class, int(work_id), pid=pid))

    def swap_great_works(self, their_work_id: int, pid: int | None = None) -> dict:
        """The Swap button: exchange our put-up work of the same class for `their_work_id`, an offer
        listed in culture_works().swap.theirs (Network.SendSwapGreatWorks)."""
        return self.q(self.h('swap_great_works', int(their_work_id), pid=pid))

    def domination_progress(self, pid: int | None = None) -> dict:
        return self.q(self.h('domination_progress', pid=pid))

    def wonder_overview(self, pid: int | None = None) -> dict:
        return self.q(self.h('wonder_overview', pid=pid))

    def plots_around(self, x: int, y: int, r: int = 3) -> list[dict]:
        if not 0 <= r <= 12:
            raise ValueError("radius must be between 0 and 12")
        return self.q(self.h("plots_around", x, y, r))

    def explore_frontier(self, unit_id: int, pid: int | None = None, limit: int = 12) -> dict:
        """Where the known map ends for one unit: revealed, passable plots of its domain (water for a
        ship, land otherwise, both when embarked) that touch unrevealed plots, nearest first. The fog
        edge a human sees on the minimap; nothing beyond it is read."""
        if not 1 <= int(limit) <= 100:
            raise ValueError("limit must be between 1 and 100")
        return self.q(self.h('explore_frontier', int(unit_id), int(limit), pid=pid))

    TACTICAL_DETAILS = ("summary", "full")

    def tactical_view(self, unit_id: int, radius: int | None = None, detail: str = "summary", pid: int | None = None) -> dict:
        """One bounded read around one unit (#31): its six neighbours by coordinate with what move_unit would do
        there (the same checks move_unit makes), an open step's cost and the zone of control that ends it (GitLab #180;
        no turns-to-reach, which the engine cannot give safely), river crossings, visible occupants and known cities within `radius`, fog counts, the unit's attack targets with
        the existing combat previews, and a lettered grid (its legend once per process, GitLab #152). detail="full" adds every revealed plot
        in radius as map_window reads it and keeps the previews' modifier rows.
        radius=None (runtime v261) lets the unit's own sight set it: as far as the engine's canSeePlot reaches for
        this unit (or its ranged attack), at least 2, at most 5 -- a Crossbowman on a hill gets 3."""
        if radius is not None and not 1 <= int(radius) <= 5:
            raise ValueError("radius must be between 1 and 5")
        if detail not in self.TACTICAL_DETAILS:
            raise ValueError(f"detail must be one of {self.TACTICAL_DETAILS}")
        r = None if radius is None else int(radius)
        out = self.q(self.h('tactical_view', int(unit_id), r, detail, pid=pid))
        if isinstance(out, dict) and isinstance(out.get("neighbors"), list):
            # GitLab #135: every open neighbour (and an attack) carries the order that steps there.
            from .. import affordances as A
            from .. import legend
            for n in out["neighbors"]:
                if isinstance(n, dict) and n.get("move") in ("open", "attack") and n.get("x") is not None:
                    n["call"] = A.act("move_unit", unit_id=int(unit_id), x=n["x"], y=n["y"])
            # GitLab #152: the legend once per process, a one-line key after (harness/legend.py).
            if not hasattr(self, "_legends_said"):
                self._legends_said: set[str] = set()
            legend.attach(out, self._legends_said)
        return out

    def compare(self, kind: str, city_id: int | None = None, unit_id: int | None = None,
                candidates: list[str] | None = None, plots: list[list[int]] | None = None, sort: str | None = None,
                limit: int | None = None, detail: str = "summary", pid: int | None = None) -> dict:
        """A few caller-chosen candidates side by side from one read (#34; harness/compare.py): production items in
        one city, techs, worker builds on plots, or a caravan's trade destinations. Engine answers, table effects,
        estimates and their assumptions are separate fields; every field names its source."""
        from .. import compare as C
        err = C.validate(kind, city_id=city_id, unit_id=unit_id, candidates=candidates, plots=plots, sort=sort,
                         limit=limit, detail=detail)
        if err:
            return {"ok": False, "err": err}
        seat = self._pid(pid)
        raw = self.q(self.h(*C.call_spec(kind, city_id=city_id, unit_id=unit_id, candidates=candidates, plots=plots,
                                          detail=detail), pid=seat), timeout=120)
        args = {"pid": seat, "city_id": city_id, "unit_id": unit_id, "candidates": list(candidates or [])}
        return C.shape(kind, raw, args, detail=detail, limit=limit, sort=sort)

    def known_world(self, pid: int | None = None) -> dict:
        """Everything this seat currently knows: own empire/units/cities, met civs
        (including city-states), notifications, and every revealed plot.

        Each plot has vis=true (in sight now) or vis=false (discovered, currently
        fogged). Fogged plots omit units, owners, improvements, cities, and features.
        Unrevealed tiles are omitted entirely.
        """
        return self.q(self.h('known_world', pid=pid))

    def map_index(self, pid: int | None = None) -> dict:
        """Compact map scan: revealed luxuries/strategics, camps, ruins, met foreign
        cities, visible natural wonders, and in-sight world wonders. Prefer this over
        known_world when you do not need every plot."""
        return self.q(self.h('map_index', pid=pid))

    REVEALED_MAP_LAYERS = ("vis", "terrain", "elevation", "river", "owner", "feature", "improvement", "resource", "route")

    def revealed_map(self, layers: list[str] | None = None, x0: int | None = None, y0: int | None = None,
                     x1: int | None = None, y1: int | None = None, pid: int | None = None) -> dict:
        """The revealed map as character grids, one byte per plot per layer (a Huge map after Satellites
        is ~10 KB a layer). `vis` separates plots in sight ('#') from revealed-but-fogged ('~'), whose
        contents are what was last seen and may be stale. Fog rules match describe_plot: a fogged
        feature is the remembered one or '?', improvement/route/owner are the engine's Revealed* values,
        live occupants and pillage marks appear on visible plots only. Legends are built per reply."""
        if layers is not None:
            bad = [l for l in layers if l not in self.REVEALED_MAP_LAYERS]
            if bad:
                return {"ok": False, "err": f"unknown layer(s) {bad}", "layers": list(self.REVEALED_MAP_LAYERS)}
        box = [None if v is None else int(v) for v in (x0, y0, x1, y1)]
        return self.q(self.h('revealed_map', list(layers) if layers else None, *box, pid=pid), timeout=120)

    # ------------------------------------------------------------ reference (the rule book)
    def reference(self) -> dict:
        """The static rule book: every help sentence the stock UI shows for units, buildings, techs,
        policies, promotions, beliefs, resources, terrain, improvements, specialists and unit actions,
        read from this game's database (H.reference) once per process and cached -- the words never
        change mid-game. Since v216 no other read repeats them (harness/reference.py)."""
        cached = getattr(self, "_reference", None)
        if cached is None:
            cached = self.q(self.h('reference'), timeout=240)
            if not isinstance(cached, dict):
                return {"ok": False, "err": f"unexpected reference reply {cached!r}"}
            if not cached.get("ok"):
                return cached
            self._reference = cached
        return cached

    def reference_markdown(self, section: str | None = None) -> str | dict:
        """The rule book as Markdown, whole or one section; a dict is a refusal (unknown section, or the
        game could not be read). The whole book is also written beside the notebooks for the human."""
        from ..reference import SECTIONS, render_markdown
        if section is not None and section not in SECTIONS:
            return {"ok": False, "err": f"unknown reference section {section!r}", "sections": list(SECTIONS)}
        data = self.reference()
        if not data.get("ok"):
            return data
        text = render_markdown(plain_text(data), section)
        if section is None:
            self._save_reference(text)
        return text

    def _save_reference(self, text: str) -> None:
        """A copy for humans at $XDG_DATA_HOME/civ5-harness/reference/<game>.md (same root as the
        notebooks). Best effort: a failed copy never fails the read."""
        if getattr(self, "_reference_saved", False):
            return
        try:
            from ..notes import notes_dir, safe_key
            path = notes_dir().parent / "reference" / (safe_key(self.game_key()) + ".md")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
            self._reference_saved = True
            self.reference_path = str(path)
        except Exception:  # the disk copy is a convenience
            pass

    def notifications(self, pid: int | None = None) -> list[dict]:
        return self.q(self.h('notifications', pid=pid))

    def notification_log(self, limit: int = 40, include_dismissed: bool = True,
                         pid: int | None = None, since: int | None = None) -> dict:
        """The Notification Log popup: everything the gamecore still holds, newest first, dismissed
        entries included. `notifications()` is only the ones the panel is still showing, so anything
        read once and dismissed had nowhere to be read again."""
        r = self.q(self.h("notification_log", int(limit), bool(include_dismissed), pid=pid))
        r = plain_text(r)
        if since is not None and isinstance(r, dict):
            for k, v in list(r.items()):
                if isinstance(v, list) and v and all(isinstance(x, dict) for x in v) and any("turn" in x for x in v):
                    kept = [x for x in v if not isinstance(x.get("turn"), int) or x["turn"] > since]
                    r[k], r["since"], r["dropped_before_since"] = kept, since, len(v) - len(kept)
        return r

    def spaceship_status(self, pid: int | None = None) -> dict:
        """Space race: Apollo done, each part's needed / in-ship / built-not-delivered count and prerequisite tech,
        and met rivals that finished Apollo with their part count (the Victory Progress screen)."""
        out = self.q(self.h('spaceship_status', pid=pid))
        parts = out.get("parts") if isinstance(out, dict) else None
        if parts and all((p.get("in_ship") or 0) >= (p.get("needed") or 1) for p in parts):
            # Live t502: with the last part added the game is over at once, and the engine's delayed removal of
            # that part unit never runs -- the roster still counted it as built_not_delivered beside a full ship.
            out["complete"] = True
            try:
                gs = self.q(self.h("game_facts"))
                out["game_over"] = bool(isinstance(gs, dict) and gs.get("over"))
            except TunerdError:
                pass
            if out.get("game_over") and any(p.get("built_not_delivered") for p in parts):
                out["note"] = ("the ship is complete and the game is over; a part still counted as built_not_delivered "
                               "is the last one added, which the engine only removes on a turn slice that never comes "
                               "after the win")
        return out

    def culture_overview(self, pid: int | None = None) -> dict:
        """Culture Overview screen: per met major civ, influential_on/needed for a culture victory, tourism, and
        its influence level/percent/tourism-per-turn/trend on each other major (unmet ones as "unknown")."""
        return self.q(self.h('culture_overview', pid=pid))

    def available_production(self, city_id: int, pid: int | None = None) -> dict:
        """Units/buildings/projects/processes this city can put at the head of its queue right now."""
        return A.production_rows(self.q(self.h('available_production', city_id, pid=pid)), city_id)

    # ------------------------------------------------------------ more actions (added after a live crash
    # from an unguarded raw lua() probe for city_ranged_attack -- these follow the game's own validated
    # call paths, see docs/NOTES.md for the Lua source each one is derived from)
    def plot_units(self, x: int, y: int, pid: int | None = None) -> dict:
        """Units (and city) on one plot as my team sees it right now -- {visible, units:[{id,owner,type,hp}], city?}."""
        return self.q(self.h("plot_units", x, y, pid=pid))
