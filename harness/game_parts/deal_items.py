"""The deal items propose_deal takes and the trade screen's gate on each, read off the trade catalog.

Pure: `check_items(catalog, items, demand)` answers from a trade_catalog read alone, before any screen opens, with
the same IsPossibleToTradeItem answers the UI uses to grey out pocket entries, so the caller learns WHY instead
of "it silently did not land". DealsMixin._check_deal_items reads the catalog and asks here.
"""
from __future__ import annotations

#: Every item type propose_deal / negotiate_deal / demand take.
DEAL_ITEM_TYPES = ("GOLD", "GOLD_PER_TURN", "RESOURCES", "OPEN_BORDERS", "DEFENSIVE_PACT",
                   "RESEARCH_AGREEMENT", "TRADE_AGREEMENT", "ALLOW_EMBASSY", "CITIES", "VOTE_COMMITMENT",
                   "THIRD_PARTY_WAR", "THIRD_PARTY_PEACE", "PEACE_TREATY", "DECLARATION_OF_FRIENDSHIP")

#: Items whose pocket handler puts a row from EACH side on the table in one press (tradelogic.lua): one press per
#: deal, whichever side the caller named (live t196: Venice's research agreement asked from both sides held two pairs).
PAIR_ITEM_TYPES = ("DEFENSIVE_PACT", "RESEARCH_AGREEMENT", "TRADE_AGREEMENT", "DECLARATION_OF_FRIENDSHIP")

#: The pocket handler for an item that takes nothing but the side (tradelogic.lua's Pocket*Handler(isUs)).
POCKET_HANDLERS = {"OPEN_BORDERS": "PocketOpenBordersHandler", "DEFENSIVE_PACT": "PocketDefensivePactHandler",
                   "RESEARCH_AGREEMENT": "PocketResearchAgreementHandler", "TRADE_AGREEMENT": "PocketTradeAgreementHandler",
                   "ALLOW_EMBASSY": "PocketAllowEmbassyHandler", "DECLARATION_OF_FRIENDSHIP": "PocketDoFHandler"}

#: The trade catalog's row for each plain yes/no item.
CATALOG_KEYS = {"GOLD": "gold", "GOLD_PER_TURN": "gold_per_turn", "OPEN_BORDERS": "open_borders", "DEFENSIVE_PACT": "defensive_pact",
                "RESEARCH_AGREEMENT": "research_agreement", "TRADE_AGREEMENT": "trade_agreement", "ALLOW_EMBASSY": "embassy",
                "DECLARATION_OF_FRIENDSHIP": "declaration_of_friendship"}


def check_items(catalog: dict, items: list[dict], demand: bool = False) -> dict:
    """{ok: true} when every item can go on the table as asked, else the first refusal with the screen's reason.
    `demand`: the leader screen's Demand button (GitLab #6). tradelogic.lua hides OUR pocket in
    DIPLO_UI_STATE_HUMAN_DEMAND, so only their items may go on the table, and leaderheadroot.lua greys the button
    at war (the same OnShowHide that greys Trade), so a demand is never a peace deal."""
    cat_res = {r["resource"]: r for r in catalog.get("resources", [])}
    peace = catalog.get("peace") or {}
    if demand:
        if catalog.get("at_war") or peace.get("at_war"):
            return {"ok": False, "err": "at war with this player: the Demand button is disabled (Negotiate Peace is the only table; see order(to='civ', action='peace'))"}
        for it in items:
            if not isinstance(it, dict):
                return {"ok": False, "err": f"each item must be an object like {{\"type\": ..., \"from_us\": false}}, got {it!r}"}
            if it.get("type") == "PEACE_TREATY":
                return {"ok": False, "err": "a demand carries no peace treaty (not at war)"}
            if it.get("from_us", True):
                return {"ok": False, "err": f"a demand lists only what THEY hand over (from_us: false); {it.get('type')} was marked as ours -- "
                                            "the screen hides our own pocket in demand mode"}
    if peace.get("at_war") and not peace.get("ok"):
        # At war the screens seed a peace treaty on both sides of any table (tradelogic.lua OnOpenPlayerDealScreen;
        # the engine after HUMAN_NEGOTIATE_PEACE), so every deal is a peace deal and the leader screen's Negotiate
        # Peace gate applies to all of it (GitLab #5).
        return {"ok": False, "err": "at war with this player and peace cannot be negotiated right now"
                                    + (f": {peace['note']}" if peace.get("note") else ""), "peace": peace}
    for it in items:
        if not isinstance(it, dict):
            return {"ok": False, "err": f"each item must be an object like {{\"type\": ..., \"from_us\": ...}}, got {it!r}"}
        t = it.get("type")
        if t not in DEAL_ITEM_TYPES:
            return {"ok": False, "err": f"unsupported item type {t!r}; supported: {list(DEAL_ITEM_TYPES)}"}
        side = "us" if it.get("from_us", True) else "them"
        me_them = "me" if side == "us" else "them"
        i_they = "I" if side == "us" else "they"
        amount = it.get("amount")
        if t in ("GOLD", "GOLD_PER_TURN", "RESOURCES") and amount is not None:
            # The trade screen clamps a typed amount to what the side has before the engine sees it
            # (tradelogic.lua ChangeGoldAmount / ChangeGoldPerTurnAmount / ChangeResourceAmount). Refuse
            # out-of-range amounts here instead of letting them reach ChangeGoldTrade & co.
            if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
                return {"ok": False, "err": f"{t} amount must be a positive whole number, got {amount!r}"}
            if t in ("GOLD", "GOLD_PER_TURN"):
                avail = (catalog.get(CATALOG_KEYS[t]) or {}).get(f"{side}_available")
                if isinstance(avail, (int, float)) and amount > avail:
                    return {"ok": False, "err": f"{t} amount {amount} exceeds what {i_they} can put on the table right now ({int(avail)})",
                            "available": int(avail)}
        if t == "RESOURCES":
            r = it.get("resource", "")
            r = r if r.startswith("RESOURCE_") else "RESOURCE_" + r
            entry = cat_res.get(r)
            if not entry or not entry.get(side):
                return {"ok": False, "err": f"{r} cannot be traded from {me_them} to this player right now "
                                            f"(the receiving side already has it, or {i_they} have no spare copy of it)",
                        "tradeable_resources": [{"resource": k, "from_me": v.get("us"), "from_them": v.get("them")} for k, v in cat_res.items()]}
            avail = entry.get(f"{side}_available")
            if amount is not None and isinstance(avail, (int, float)) and amount > avail:
                return {"ok": False, "err": f"{r} amount {amount} exceeds the {int(avail)} copies {i_they} can trade", "available": int(avail)}
        elif t == "CITIES":
            # OnChooseCity -> deal:AddCityTrade(player, id) is unconditional in tradelogic.lua; the real UI
            # only offers cities that pass IsPossibleToTradeItem(TRADE_ITEM_CITIES, x, y). Same gate here.
            cities = (catalog.get("cities") or {}).get(side) or []
            city_id = it.get("city_id")
            if isinstance(city_id, bool) or not isinstance(city_id, int):
                return {"ok": False, "err": "CITIES needs an integer city_id (see state(what='cities') / state(what='civ', view='trade_catalog').cities)",
                        "tradeable_cities": cities}
            if city_id not in {c.get("id") for c in cities}:
                return {"ok": False, "err": f"city {city_id} is not tradeable from {me_them} to this player right now "
                                            "(not owned by that side, or the game does not allow trading it)",
                        "tradeable_cities": cities}
        elif t == "PEACE_TREATY":
            # No pocket button exists for this: the treaty is on the table the moment a screen opens while at
            # war, and cannot be put there at peace. Listing it only states the intent (make_peace does).
            if not peace.get("at_war"):
                return {"ok": False, "err": "PEACE_TREATY: not at war with this player", "peace": peace}
        elif t == "DECLARATION_OF_FRIENDSHIP":
            # The pocket row exists on the PvP table only (GitLab #175); an AI is asked on its leader screen, and the
            # engine's legality query for this item against an AI crashed the game, so the catalog never makes it.
            row = catalog.get("declaration_of_friendship")
            if not isinstance(row, dict) or row.get("ai"):
                return {"ok": False, "err": "a Declaration of Friendship goes on the trade table between human seats only; "
                                            "an AI leader is asked with order(to='civ', action='friendship')"}
            if not row.get(side):
                return {"ok": False, "err": "DECLARATION_OF_FRIENDSHIP is greyed out on the trade screen"
                                            + (f": {row['note']}" if row.get("note") else ""),
                        "catalog": {"declaration_of_friendship": row}}
        elif t in ("THIRD_PARTY_WAR", "THIRD_PARTY_PEACE"):
            # The Other Players pocket (tradelogic.lua ShowOtherPlayerChooser) greys out every leader that fails
            # IsPossibleToTradeItem(from, to, type, team); LeaderSelected -> AddThirdPartyWar/Peace is then
            # unconditional. trade_catalog().third_party is that list with the screen's reasons (GitLab #6).
            kind = "war" if t == "THIRD_PARTY_WAR" else "peace"
            rows = ((catalog.get("third_party") or {}).get(kind) or {}).get(side) or []
            who = it.get("other")
            if isinstance(who, bool) or not isinstance(who, int):
                return {"ok": False, "err": f"{t} needs an integer `other` player id (see state(what='civ', view='trade_catalog').third_party.{kind})",
                        "third_party": rows}
            row = next((r for r in rows if r.get("player") == who), None)
            if row is None:
                return {"ok": False, "err": f"player {who} is not on the Other Players list for this deal (unmet by one side, or one of the two parties)",
                        "third_party": rows}
            if not row.get("ok"):
                return {"ok": False, "err": f"{t} against {row.get('name') or who} from {me_them} is greyed out on the trade screen"
                                            + (f": {row['note']}" if row.get("note") else ""),
                        "third_party": rows}
        elif t == "VOTE_COMMITMENT":
            # The Pocket Votes list (tradelogic.lua RefreshPocketVotes) only offers (proposal, choice) pairs
            # that pass IsPossibleToTradeItem for that direction; trade_catalog().vote_commitments is that
            # list. OnChoosePocketVote -> AddVoteCommitment is unconditional, so the gate lives here (GitLab #7).
            votes = catalog.get("vote_commitments") or []
            rid, cid, repeal = it.get("resolution_id"), it.get("choice_id"), bool(it.get("repeal", False))
            if any(isinstance(v, bool) or not isinstance(v, int) for v in (rid, cid)):
                return {"ok": False, "err": "VOTE_COMMITMENT needs integer resolution_id and choice_id "
                                            "(see state(what='civ', view='trade_catalog').vote_commitments / state(what='league'))",
                        "tradeable_votes": votes}
            match = next((v for v in votes if v.get("resolution_id") == rid and v.get("choice_id") == cid
                          and bool(v.get("repeal")) == repeal), None)
            if not match or not match.get(side):
                return {"ok": False, "err": f"that vote commitment cannot be traded from {me_them} to this player right now "
                                            "(no such pending proposal/choice, or the World Congress does not allow it)",
                        "tradeable_votes": votes}
        else:
            key = CATALOG_KEYS[t]
            flag = catalog.get(key)
            if isinstance(flag, dict) and not flag.get(side):
                return {"ok": False, "err": f"{t} from {me_them} is not legal with this player right now (see state(what='civ', view='trade_catalog'))",
                        "catalog": {key: flag}}
    return {"ok": True}
