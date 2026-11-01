"""Every `available_*` reply with its writes as rows (GitLab #47).

Each choice row of a read keeps its keys and gains `call`: the write that takes that choice, complete, so the
model copies it into `do(actions=[...])` as is. A purchasable item also carries `buy`. The reply's own shape
(a list of rows, or a dict holding them) does not change; a refusal is returned untouched.
"""
from __future__ import annotations

from typing import Any, Callable

from .. import gate
from ..rows import act


def _each(rows: Any, make: Callable[[dict], dict | None]) -> Any:
    """`call` on every dict row of `rows` for which `make` gives a row."""
    for r in rows if isinstance(rows, list) else []:
        if isinstance(r, dict):
            row = make(r)
            if row is not None:
                r["call"] = row
    return rows


def _ok(reply: Any) -> bool:
    return isinstance(reply, dict) and reply.get("ok", True) is not False


def research_rows(rows: Any) -> Any:
    """available_research: each tech with its `set_research`."""
    return _each(rows, lambda r: act("set_research", tech=r["tech"]) if r.get("tech") else None)


def production_rows(reply: Any, city_id: int) -> Any:
    """available_production: each item with its `set_production` (not a faith-only item, which cannot be queued)
    and, when the city may buy it now, `buy` (gold, or faith for the faith tab's rows)."""
    rows = reply.get("items") if isinstance(reply, dict) else reply
    if not isinstance(rows, list) or (isinstance(reply, dict) and not _ok(reply)):
        return reply
    for r in rows:
        if not isinstance(r, dict) or not r.get("item"):
            continue
        if not r.get("faith_only") and not (isinstance(reply, dict) and reply.get("purchase_only")):
            r["call"] = act("set_production", city_id=city_id, item=r["item"])
        if r.get("can_buy"):
            r["buy"] = act("purchase_production", city_id=city_id, item=r["item"])
        elif r.get("faith_can_buy"):
            r["buy"] = act("purchase_production", city_id=city_id, item=r["item"], yield_type="FAITH")
    return reply


def policy_rows(reply: Any) -> Any:
    """available_policies: each adoptable policy with its `choose_policy`, each branch that can be unlocked with its
    `unlock_policy_branch`."""
    if not _ok(reply):
        return reply
    _each(reply.get("adoptable"), lambda r: act("choose_policy", policy=r["policy"]) if r.get("policy") else None)
    _each(reply.get("branches"),
          lambda r: act("unlock_policy_branch", branch=r["branch"]) if r.get("branch") and r.get("can_unlock") else None)
    if reply.get("ideology_choice_open"):   # GitLab #145: the choice the engine asks for, one call per ideology
        _each(reply.get("ideologies"), lambda r: act("choose_ideology", branch=r["branch"]) if r.get("branch") else None)
    return reply


#: The belief kinds one belief answers by itself: each row carries its call.
BELIEF_TOOLS = {"pantheon": "found_pantheon", "reformation": "add_reformation_belief"}
#: The kinds whose belief is one argument of a religion order: no order takes one such belief alone, so the
#: reply carries the rows of the popup(s) that take it -- the reads of the other kinds, then the order with what
#: it leaves to choose (gate.popup_rows) -- and `call_note` names the argument the belief is.
BELIEF_POPUPS = {"founder": ("BUTTONPOPUP_FOUND_RELIGION",), "bonus": ("BUTTONPOPUP_FOUND_RELIGION",),
                 "follower": ("BUTTONPOPUP_FOUND_RELIGION", "BUTTONPOPUP_ENHANCE_RELIGION"),
                 "enhancer": ("BUTTONPOPUP_ENHANCE_RELIGION",)}
BELIEF_NOTES = {
    "founder": "no order takes a founder belief alone: it is one of the `beliefs` of the founding order, beside a follower belief",
    "bonus": "no order takes a bonus belief alone: it is one more of the `beliefs` of the founding order",
    "follower": "no order takes a follower belief alone: it is one of the `beliefs` when founding, `belief4` when enhancing",
    "enhancer": "no order takes an enhancer belief alone: it is `belief5` of the enhancing order, beside a follower `belief4`",
}


def belief_rows(reply: Any, kind: str) -> Any:
    """available_beliefs(kind) -- `{ok, kind, beliefs: [...]}` -- with its writes (GitLab #178: the rows came back
    bare because the calls were put on the dict's rows only when the reply was a list, which it never is). A
    pantheon or reformation belief row carries its `call`; for a founder / follower / enhancer / bonus belief the
    reply carries the religion order's rows as `actions` and `call_note`. A refusal is returned untouched."""
    if not _ok(reply):
        return reply
    tool = BELIEF_TOOLS.get(kind)
    if tool is not None:
        _each(reply.get("beliefs"), lambda r: act(tool, belief=r["belief"]) if r.get("belief") else None)
    elif kind in BELIEF_POPUPS:
        this_read = {"what": "options", "view": "beliefs", "kind": kind}
        reply["call_note"] = BELIEF_NOTES[kind]
        reply["actions"] = [row for popup in BELIEF_POPUPS[kind] for row in gate.popup_rows(popup)
                            if row["args"] != this_read]
    return reply


def trade_route_rows(rows: Any, unit_id: int) -> Any:
    """available_trade_routes: each destination with its `establish_trade_route` (by plot and connection type)."""
    def make(r: dict) -> dict | None:
        if r.get("x") is None or r.get("y") is None:
            return None
        args = {"unit_id": unit_id, "dest_x": r["x"], "dest_y": r["y"]}
        if r.get("trade_connection_type") is not None:
            args["trade_type"] = r["trade_connection_type"]
        return act("establish_trade_route", **args)
    return _each(rows, make)


def spy_city_rows(rows: Any, agent_id: int) -> Any:
    """available_spy_cities: each city with its `move_spy`."""
    return _each(rows, lambda r: act("move_spy", agent_id=agent_id, target_player_id=r["target_player_id"],
                                     target_city_id=r["city_id"])
                 if r.get("target_player_id") is not None and r.get("city_id") is not None else None)


def mission_target_rows(reply: Any) -> Any:
    """unit_mission_targets: each target with the `unit_mission` that sends the unit there."""
    if not _ok(reply) or reply.get("unit_id") is None or not reply.get("mission"):
        return reply
    uid, mission = reply["unit_id"], reply["mission"]
    if mission in ("MISSION_TRADE", "MISSION_FOUND"):
        # the merchant walks onto the city-state's land first (#87), the settler onto its site (#106): the move, then the mission
        for r in reply.get("targets") or []:
            if isinstance(r, dict) and r.get("x") is not None and r.get("y") is not None:
                r["calls"] = [act("move_unit", unit_id=uid, x=r["x"], y=r["y"]), act("unit_mission", unit_id=uid, mission=mission)]
        return reply
    _each(reply.get("targets"), lambda r: act("unit_mission", unit_id=uid, mission=mission, x=r["x"], y=r["y"])
          if r.get("x") is not None and r.get("y") is not None else None)
    return reply


def strike_rows(reply: Any, city_id: int) -> Any:
    """available_city_strikes: each target with its `city_ranged_attack`."""
    if not _ok(reply):
        return reply
    _each(reply.get("targets"), lambda r: act("city_ranged_attack", city_id=city_id, x=r["x"], y=r["y"])
          if r.get("x") is not None and r.get("y") is not None else None)
    return reply


def gift_unit_rows(reply: Any, minor_id: int) -> Any:
    """gift_unit_options: each unit that may be given with its `gift_unit`."""
    if not _ok(reply):
        return reply
    _each(reply.get("units"), lambda r: act("gift_unit", minor_id=minor_id, unit_id=r["id"]) if r.get("id") is not None else None)
    return reply


def gift_tile_rows(reply: Any, minor_id: int) -> Any:
    """gift_tile_improvement_options: each plot with its `gift_tile_improvement`."""
    if not _ok(reply):
        return reply
    _each(reply.get("plots"), lambda r: act("gift_tile_improvement", player_id=minor_id, x=r["x"], y=r["y"])
          if r.get("x") is not None and r.get("y") is not None else None)
    return reply


def home_rows(reply: Any) -> Any:
    """unit_home_options: each city with the `unit_mission` that makes it the unit's home."""
    if not _ok(reply) or reply.get("unit_id") is None or not reply.get("mission"):
        return reply
    uid, mission = reply["unit_id"], reply["mission"]
    _each(reply.get("cities"), lambda r: act("unit_mission", unit_id=uid, mission=mission, x=r["x"], y=r["y"])
          if r.get("x") is not None and r.get("y") is not None else None)
    return reply


def city_state_gift_rows(reply: Any) -> Any:
    """city_state_gifts: each gold tier (`small`, `medium`, `large` -- the live keys, Assyria t238) carries `call`,
    the gift row the runtime writes as `how` (the new call since runtime v286; an older runtime's `minor_gold_gift`
    row is rendered as the new call here). `how` itself is dropped: the two were the same row (GitLab #65)."""
    if not _ok(reply):
        return reply

    def rendered(r):
        how = r.pop("how", None)
        if not (isinstance(how, dict) and isinstance(how.get("tool"), str)):
            return None
        return dict(act(how["tool"], **(how.get("args") or {})))
    for value in list(reply.values()):
        if isinstance(value, dict) and isinstance(value.get("how"), dict):
            _each([value], rendered)
        elif isinstance(value, list):
            _each(value, rendered)
    return reply
