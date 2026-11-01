"""Affordances as rows (GitLab #45, stage 1a of "The tool surface"): every decision the briefing lists and every
unit the todo_actions summary returns carries `actions: [{tool, args}]`, the very rows do() takes, so a turn is
played from the rows alone -- the test below types no tool name but the batch carrier's.
"""
import ast
import os
import pathlib
import unittest
from unittest import mock

import anyio

from test_set_seat import session
from test_todo_actions import NORMAL, game_answering
from harness import affordances as A
from harness import briefing as B
from harness.call_ledger import kind
from harness import gate
from harness import mcp_server as m
from harness.game import Game
from harness.surface import survey


class RowShapeTests(unittest.TestCase):
    def test_a_row_is_what_do_takes_and_a_pick_names_what_is_left_to_choose(self):
        # the makers name the old handler; the row is the new call (#55)
        self.assertEqual(A.act("set_research", tech="TECH_MINING"), {"tool": "order", "args": {"to": "empire", "action": "research", "args": {"tech": "TECH_MINING"}}})
        row = A.pick("set_production", ["item"], city_id=7)
        self.assertEqual(row, {"tool": "order", "args": {"to": "city", "action": "produce", "id": 7}, "choose": ["item"]})
        self.assertTrue(A.is_row(row))
        self.assertFalse(A.is_row({"tool": "x"}))

    def test_every_decision_kind_opens_with_a_read_and_closes_with_the_order(self):
        for rows in (A.unit_orders(5), A.promotion(5), A.city_production(8), A.research(), A.incoming_deal(),
                     A.steal_tech(), A.policy(), A.idle_trade_unit(9), A.idle_spy(2)):
            self.assertTrue(rows and all(A.is_row(r) for r in rows), rows)
            self.assertNotIn("choose", rows[0], "the first row is a read that runs as is")
        self.assertEqual(A.promotion(5)[1]["args"], {"to": "unit", "action": "promote", "id": 5})
        self.assertEqual(A.idle_spy(None), [])

    def test_stacked_names_the_unit_with_moves_on_each_tile(self):
        tiles = [{"x": 1, "y": 1, "units": [{"id": 6, "moves": 0}, {"id": 5, "moves": 2}]},
                 {"x": 2, "y": 2, "units": [{"id": 7, "moves": 0}]}, {"x": 3, "y": 3}]
        rows = A.stacked(tiles)
        self.assertEqual([r["args"]["id"] for r in rows], [5, 5, 7, 7])
        self.assertEqual(rows[1]["choose"], ["x", "y"])

    def test_popup_rows_are_the_gates_own(self):
        for name, r in gate.POPUP_RESOLUTIONS.items():
            rows = A.popup(name)
            self.assertEqual(rows, gate.popup_rows(name))
            if r.get("read_first"):
                self.assertEqual(rows[0]["tool"], A.act(r["read_first"])["tool"])
            chosen = [a.strip() for a in gate.POPUP_CHOICE_ARGS[name].split(",")]
            clear = A.pick(r["clear_with"], chosen)
            self.assertIn(clear, rows, (name, rows))
            also = [A.pick(a, gate.CLEAR_CHOICE[a]) if gate.CLEAR_CHOICE.get(a) else A.act(a) for a in r.get("also", [])]
            self.assertEqual(rows[-len(also):] if also else [], also)
        self.assertEqual(A.popup("BUTTONPOPUP_RETURN_CIVILIAN"),
                         [A.act("generic_popup"), A.pick("answer_popup", ["button"])])

    def test_every_question_shaped_read_answers_with_complete_rows(self):
        """#46: one row per button or choice, each a complete call (the live-shaped replies of each read)."""
        cases = [
            (A.generic_popup_answers, {"open": True, "text": "Return?", "buttons": [{"id": 1, "text": "Yes"}, {"id": 2, "text": "No"}]},
             [A.act("answer_popup", button=1), A.act("answer_popup", button=2)]),
            (A.generic_popup_answers, {"open": False, "buttons": [{"id": 1}]}, []),
            (A.goody_hut_answers, {"ok": True, "options": [{"goody": "GOODY_GOLD", "description": "Gold"}, {"goody": "GOODY_MAP"}]},
             [A.act("choose_goody_hut", goody="GOODY_GOLD"), A.act("choose_goody_hut", goody="GOODY_MAP")]),
            (A.maya_answers, {"ok": True, "count": 1, "options": [{"unit": "UNIT_SCIENTIST", "available": True},
                                                                 {"unit": "UNIT_ARTIST", "available": False}]},
             [A.act("choose_maya_bonus", unit="UNIT_SCIENTIST")]),
            (A.maya_answers, {"ok": True, "count": 0, "options": [{"unit": "UNIT_SCIENTIST", "available": True}]}, []),
            (A.city_capture_answers, {"ok": True, "options": [{"choice": "puppet"}, {"choice": "annex", "warmonger": "x"}]},
             [A.act("choose_city_capture", choice="puppet"), A.act("choose_city_capture", choice="annex")]),
            (A.steal_tech_answers, {"ok": True, "victims": [{"player_id": 3, "techs": [{"tech": "TECH_SAILING"}, {"tech": "TECH_POTTERY"}]},
                                                             {"player_id": 5, "techs": []}]},
             [A.act("steal_tech", tech="TECH_SAILING", player_id=3), A.act("steal_tech", tech="TECH_POTTERY", player_id=3)]),
            (A.free_great_person_answers, {"ok": True, "count": 2, "options": ["UNIT_SCIENTIST", "UNIT_ENGINEER"]},
             [A.act("choose_free_great_person", unit="UNIT_SCIENTIST"), A.act("choose_free_great_person", unit="UNIT_ENGINEER")]),
            (A.free_great_person_answers, {"ok": True, "count": 0, "options": ["UNIT_SCIENTIST"]}, []),
            (A.faith_great_person_answers, {"ok": True, "options": ["UNIT_PROPHET"], "faith": 900},
             [A.act("choose_faith_great_person", unit="UNIT_PROPHET")]),
            (A.archaeology_answers, {"ok": True, "pending": True, "x": 4, "y": 9, "options": [{"choice": 2, "action": "artifact_player1"},
                                                                                            {"choice": 1, "action": "landmark"}]},
             [A.act("choose_archaeology", choice=2, x=4, y=9), A.act("choose_archaeology", choice=1, x=4, y=9)]),
            (A.archaeology_answers, {"ok": True, "pending": False, "options": []}, []),
            (A.discussion_answers, {"pending": True, "screen": "trade", "buttons": []},
             [A.act("accept_deal"), A.act("refuse_deal"), A.act("dismiss_discussion")]),
            (A.discussion_answers, {"pending": True, "screen": "discussion", "player": 2,
                                    "buttons": [{"id": 1, "text": "Yes", "disabled": False}, {"id": 2, "text": "No", "disabled": True}],
                                    "relationship": {"ok": True, "history": [{"state": "DIPLO_UI_STATE_DISCUSS_WORK_WITH_US", "text": "Friends?"}]}},
             [A.act("respond_discussion", button_id=1), A.act("accept_friendship", player_id=2), A.act("dismiss_discussion")]),
            (A.discussion_answers, {"pending": True, "screen": "greeting"}, [A.act("dismiss_discussion")]),
            (A.discussion_answers, {"pending": False, "screen": None}, []),
            (A.incoming_deal_answers, {"ok": True, "items": [{"type": "GOLD"}], "from": 2, "to": 0},
             [A.act("accept_deal"), A.act("refuse_deal")]),
            (A.incoming_deal_answers, {"ok": True, "pending": False, "items": []}, []),
        ]
        from harness.surface import dispatch as D
        for make, reply, want in cases:
            got = make(reply)
            self.assertEqual(got, want, make.__name__)
            for r in got:   # every answer is a complete call the server resolves (on the question's own gate)
                self.assertEqual(r["tool"], "answer", r)
                self.assertIsInstance(D.resolve("answer", {"choice": r["args"]["choice"]}, r["args"].get("args") or {},
                                                {"name": "discussion", "actions": []} if isinstance(r["args"]["choice"], (int, str)) and r["args"]["choice"] in ("accept", "refuse", "leave", "accept_friendship") or isinstance(r["args"]["choice"], int) else None) if r["args"]["choice"] in ("accept", "refuse", "leave", "accept_friendship") else D.Call("x", {}), D.Call, r)
        self.assertEqual(A.answered({"ok": False, "err": "x"}, A.goody_hut_answers), {"ok": False, "err": "x"})
        self.assertEqual(A.answered({"ok": True, "options": []}, A.goody_hut_answers), {"ok": True, "options": [], "answers": []})

    def test_the_mixins_hand_the_answers_back(self):
        """The reads compose their reply in the game mixins; the rows ride on the reply every caller sees."""
        g = game_answering({"ok": True, "options": [{"goody": "GOODY_CULTURE"}], "unit_id": 7, "x": 1, "y": 2})
        g._goody_popup_unit = lambda: 7
        self.assertEqual(Game.goody_hut_options(g)["answers"], [A.act("choose_goody_hut", goody="GOODY_CULTURE")])
        g = game_answering({"ok": True, "options": [{"choice": "puppet", "warmonger": "[COLOR_RED]bad[ENDCOLOR]"}]})
        r = Game.city_capture_options(g)
        self.assertEqual((r["options"][0]["warmonger"], r["answers"]), ("bad", [A.act("choose_city_capture", choice="puppet")]))
        g = game_answering({"ok": True, "victims": [{"player_id": 3, "techs": [{"tech": "TECH_X"}]}], "n": 1})
        self.assertEqual(Game.steal_tech_options(g)["answers"], [A.act("steal_tech", tech="TECH_X", player_id=3)])
        g = game_answering({"ok": True, "options": ["UNIT_PROPHET"], "faith": 1})
        self.assertEqual(Game.faith_great_person_options(g)["answers"], [A.act("choose_faith_great_person", unit="UNIT_PROPHET")])
        g = game_answering({"ok": True, "count": 1, "options": ["UNIT_ENGINEER"]})
        self.assertEqual(Game.free_great_person_options(g)["answers"], [A.act("choose_free_great_person", unit="UNIT_ENGINEER")])
        g = game_answering({"ok": True, "count": 1, "options": [{"unit": "UNIT_WRITER", "available": True}]})
        self.assertEqual(Game.maya_options(g)["answers"], [A.act("choose_maya_bonus", unit="UNIT_WRITER")])
        g = game_answering({"ok": True, "pending": True, "x": 3, "y": 4, "unit_id": 9, "options": [{"choice": 1, "action": "landmark"}]})
        self.assertEqual(Game.archaeology_options(g)["answers"], [A.act("choose_archaeology", choice=1, x=3, y=4)])
        g = game_answering({"ok": True, "pending": False, "items": []})
        self.assertEqual(Game.incoming_deal(g)["answers"], [])
        g.q = lambda code, timeout=None: {"ok": True, "items": [{"type": "GOLD", "from_us": False}], "from": 2, "to": 0}
        g.relationship = lambda other, pid=None: {"ok": True, "history": []}
        self.assertEqual(Game.incoming_deal(g)["answers"], [A.act("accept_deal"), A.act("refuse_deal")])
        # GitLab #161: the engine holds player 1's proposal but LoadProposedDeal put nothing on the table
        g.q = lambda code, timeout=None: {"ok": True, "items": [], "n": 0, "from": -1, "to": -1, "proposed_by": 1}
        g._pid = lambda pid=None: 0
        r = Game.incoming_deal(g)
        self.assertEqual((r["pending"], r["from"], r["unread"], r["answers"]), (True, 1, True, [A.act("refuse_deal")]))
        self.assertIn("did not load", r["note"])

    def test_unit_actions_cover_every_kind_of_action_row(self):
        u = {"id": 9, "actions": [
            {"type": "MISSION_HEAL", "kind": "mission", "mission": "MISSION_HEAL"},
            {"type": "BUILD_FARM", "kind": "build", "mission": "MISSION_BUILD"},
            {"type": "COMMAND_UPGRADE", "kind": "command"},
            {"type": "COMMAND_GIFT", "kind": "command"}, {"type": "COMMAND_HOTKEY", "kind": "command"},
            {"type": "INTERFACEMODE_PARADROP", "kind": "interface", "mission": "MISSION_PARADROP",
             "target_view": "targets"},
            {"type": "AUTOMATE_BUILD", "kind": "other"},
            {"type": "MISSION_CHANGE_TRADE_UNIT_HOME", "kind": "mission", "mission": "MISSION_CHANGE_TRADE_UNIT_HOME",
             "target_view": "home"}, "junk"],
            "attack_targets": [{"x": 4, "y": 4, "unit": "BRUTE"}], "ranged_targets": [{"x": 5, "y": 5}],
            "promotions": [{"promotion": "PROMOTION_SHOCK_1"}, "PROMOTION_DRILL_1"]}
        rows = A.unit_actions(u)
        self.assertEqual(rows, [
            A.act("unit_mission", unit_id=9, mission="MISSION_HEAL"),
            A.act("unit_mission", unit_id=9, mission="MISSION_BUILD", build="BUILD_FARM"),
            A.act("upgrade_unit", unit_id=9),
            A.pick("gift_unit", ["minor_id"], unit_id=9),
            A.act("unit_mission_targets", unit_id=9, mission="MISSION_PARADROP"),
            A.pick("unit_mission", ["x", "y"], unit_id=9, mission="MISSION_PARADROP"),
            A.act("unit_mission", unit_id=9, mission="AUTOMATE_BUILD"),
            A.act("unit_home_options", unit_id=9),
            A.pick("unit_mission", ["x", "y"], unit_id=9, mission="MISSION_CHANGE_TRADE_UNIT_HOME"),
            A.act("move_unit", unit_id=9, x=4, y=4),
            A.act("unit_mission", unit_id=9, mission="MISSION_RANGE_ATTACK", x=5, y=5),
            A.act("choose_promotion", unit_id=9, promotion="PROMOTION_SHOCK_1"),
            A.act("choose_promotion", unit_id=9, promotion="PROMOTION_DRILL_1"),
        ])
        self.assertEqual(A.unit_actions({"id": 1}), [])

    def test_rows_in_finds_every_actions_list_but_not_the_engine_action_dicts(self):
        reply = {"decisions": [{"kind": "research", "actions": A.research()}],
                 "units": [{"id": 1, "actions": [{"type": "MISSION_HEAL", "kind": "mission"}]}],
                 "opportunities": [{"actions": A.idle_spy(3)}]}
        self.assertEqual([r["tool"] for r in A.rows_in(reply)], ["state", "order", "state", "order"])

    def test_every_row_names_a_listed_tool(self):
        from harness.surface import vocabulary as V
        names = set(V.TOOLS)
        u = {"id": 9, "actions": [{"type": "COMMAND_UPGRADE", "kind": "command"}, {"type": "COMMAND_DELETE", "kind": "command"},
                                  {"type": "INTERFACEMODE_NUKE", "kind": "interface", "mission": "MISSION_NUKE",
                                   "target_view": "targets"}],
             "attack_targets": [{"x": 1, "y": 1}], "ranged_targets": [{"x": 1, "y": 2}], "promotions": ["PROMOTION_X"]}
        rows = (A.unit_orders(1) + A.promotion(1) + A.city_production(1) + A.research() + A.incoming_deal() + A.steal_tech()
                + A.policy() + A.stacked([{"units": [{"id": 1, "moves": 1}]}]) + A.idle_trade_unit(1) + A.idle_spy(1)
                + A.unit_actions(u) + [r for n in [*gate.POPUP_RESOLUTIONS, "BUTTONPOPUP_OTHER"] for r in A.popup(n)])
        self.assertFalse({r["tool"] for r in rows} - names)


class BriefingRowsTests(unittest.TestCase):
    def test_every_decision_and_opportunity_carries_its_rows_and_the_sentence_is_marked_for_retirement(self):
        from test_briefing import CITY, SUMMARY, status
        todo = {"units": [{"id": 5, "type": "WARRIOR", "x": 1, "y": 1, "moves": 2}], "cities": [{"id": 8192, "name": "Venice"}],
                "promotions": [7], "research_unset": True, "incoming_deal": {"from": 1}, "steal_tech": [{"player_id": 3}],
                "policy": {"culture": 500}}
        ts = status(todo=todo, blocking_name="ENDTURN_BLOCKING_UNITS", pending_popups=[{"name": "BUTTONPOPUP_CHOOSE_GOODY_HUT_REWARD"}])
        summary = {**SUMMARY, "idle_trade_units": [{"unit_id": 44, "type": "CARAVAN", "in_city": "Venice"}],
                   "idle_spies": [{"agent_id": 2, "name": "Marco"}]}
        out, _ = B.build(ts, summary, [CITY], [], {}, {"comparable": False}, None, [], limit=8, include_rules=False)
        for row in out["decisions"] + out["opportunities"]:
            if row["kind"] in ("blocker", "free_trade_route_slots"):
                continue
            self.assertTrue(row.get("actions") and all(A.is_row(r) for r in row["actions"]), row)
            self.assertNotIn("tool", row)
        by_kind = {r["kind"]: r for r in out["decisions"] + out["opportunities"]}
        self.assertEqual(by_kind["unit_orders"]["actions"], A.unit_orders(5))
        self.assertEqual(by_kind["city_production"]["actions"][1]["args"], {"to": "city", "action": "produce", "id": 8192})
        self.assertEqual(by_kind["popup"]["actions"][0]["tool"], "question")
        self.assertEqual(by_kind["idle_trade_unit"]["actions"][0]["args"], {"what": "options", "view": "trade_routes", "id": 44})
        self.assertEqual(by_kind["idle_spy"]["actions"][1]["args"], {"to": "spy", "action": "move", "id": 2})
        self.assertIn("unit_orders", out["tools"], "the sentence stays one release")
        self.assertNotIn("tools_note", out, "the retirement note is gone (GitLab #107)")


class ChoiceRowsTests(unittest.TestCase):
    """#47: every `available_*` reply hands each choice back with `call`, the complete write that takes it."""

    def assertComplete(self, rows):
        """Every row is one of the nine and, its `choose` filled, resolves to an old handler with every required
        argument given (the server's own validation)."""
        from harness.surface import dispatch as D
        from harness.surface import vocabulary as V
        for r in rows:
            self.assertIn(r["tool"], V.TOOLS, r)
            args = dict(r["args"])
            for name in r.get("choose") or []:
                top = name in V.TOP_LEVEL[r["tool"]] or name in D.FIXED_FIELDS.get(r["tool"], ())
                (args if top else args.setdefault("args", {}))[name] = 1 if name in ("x", "y", "id", "player_id") else f"<{name}>"
            fixed = {k: args.pop(k) for k in D.FIXED_FIELDS.get(r["tool"], ()) if k in args}
            if isinstance(args.get("args"), dict):
                args = {**args.pop("args"), **args}
            self.assertIsInstance(D.resolve(r["tool"], fixed, args), D.Call, r)

    def test_each_choice_carries_its_write(self):
        research = A.research_rows([{"tech": "TECH_MINING", "cost": 35}, {"name": "no tech key"}])
        self.assertEqual(research[0]["call"], A.act("set_research", tech="TECH_MINING"))
        self.assertNotIn("call", research[1])
        prod = A.production_rows({"ok": True, "items": [{"item": "UNIT_WARRIOR", "can_buy": True}, {"item": "BUILDING_SHRINE"},
                                                       {"item": "UNIT_MISSIONARY", "faith_only": True, "faith_can_buy": True}]}, 7)
        self.assertEqual(prod["items"][0]["call"], A.act("set_production", city_id=7, item="UNIT_WARRIOR"))
        self.assertEqual(prod["items"][0]["buy"], A.act("purchase_production", city_id=7, item="UNIT_WARRIOR"))
        self.assertNotIn("buy", prod["items"][1])
        self.assertNotIn("call", prod["items"][2], "a faith-only item cannot be queued")
        self.assertEqual(prod["items"][2]["buy"]["args"]["args"]["yield_type"], "FAITH")
        venice = A.production_rows({"ok": True, "purchase_only": True, "items": [{"item": "UNIT_WARRIOR", "can_buy": True}]}, 8)
        self.assertEqual(list(venice["items"][0]), ["item", "can_buy", "buy"])
        pol = A.policy_rows({"adoptable": [{"policy": "POLICY_LIBERTY"}], "branches": [{"branch": "POLICY_BRANCH_HONOR", "can_unlock": True},
                                                                                       {"branch": "POLICY_BRANCH_TRADITION", "can_unlock": False}]})
        self.assertEqual(pol["adoptable"][0]["call"], A.act("choose_policy", policy="POLICY_LIBERTY"))
        self.assertEqual(pol["branches"][0]["call"], A.act("unlock_policy_branch", branch="POLICY_BRANCH_HONOR"))
        self.assertNotIn("call", pol["branches"][1])
        def beliefs(kind):    # the runtime's shape (H.available_beliefs): the rows under `beliefs`
            return {"ok": True, "kind": kind, "beliefs": [{"belief": "BELIEF_GOD_OF_THE_SEA"}]}
        self.assertEqual(A.belief_rows(beliefs("pantheon"), "pantheon")["beliefs"][0]["call"],
                         A.act("found_pantheon", belief="BELIEF_GOD_OF_THE_SEA"))
        self.assertEqual(A.belief_rows(beliefs("reformation"), "reformation")["beliefs"][0]["call"]["args"]["action"], "reformation")
        self.assertNotIn("call", A.belief_rows(beliefs("founder"), "founder")["beliefs"][0], "one of several arguments of found_religion")
        routes = A.trade_route_rows([{"x": 3, "y": 4, "trade_connection_type": 0, "kind": "international"}, {"city_name": "none"}], 44)
        self.assertEqual(routes[0]["call"], A.act("establish_trade_route", unit_id=44, dest_x=3, dest_y=4, trade_type=0))
        self.assertNotIn("call", routes[1])
        spies = A.spy_city_rows([{"target_player_id": 2, "city_id": 9, "name": "Sukhothai"}], 1)
        self.assertEqual(spies[0]["call"], A.act("move_spy", agent_id=1, target_player_id=2, target_city_id=9))
        targets = A.mission_target_rows({"ok": True, "unit_id": 5, "mission": "MISSION_PARADROP", "targets": [{"x": 1, "y": 2}]})
        self.assertEqual(targets["targets"][0]["call"], A.act("unit_mission", unit_id=5, mission="MISSION_PARADROP", x=1, y=2))
        strikes = A.strike_rows({"ok": True, "can": True, "targets": [{"x": 6, "y": 6, "unit": "BRUTE"}]}, 8192)
        self.assertEqual(strikes["targets"][0]["call"], A.act("city_ranged_attack", city_id=8192, x=6, y=6))
        gifts = A.gift_unit_rows({"ok": True, "units": [{"id": 3, "type": "WARRIOR"}]}, 20)
        self.assertEqual(gifts["units"][0]["call"], A.act("gift_unit", minor_id=20, unit_id=3))
        tiles = A.gift_tile_rows({"ok": True, "can": True, "plots": [{"x": 1, "y": 1, "improvement": "IMPROVEMENT_FARM"}]}, 20)
        self.assertEqual(tiles["plots"][0]["call"], A.act("gift_tile_improvement", player_id=20, x=1, y=1))
        home = A.home_rows({"ok": True, "unit_id": 44, "mission": "MISSION_CHANGE_TRADE_UNIT_HOME_CITY", "cities": [{"x": 2, "y": 3}]})
        self.assertEqual(home["cities"][0]["call"], A.act("unit_mission", unit_id=44, mission="MISSION_CHANGE_TRADE_UNIT_HOME_CITY", x=2, y=3))
        gold = A.city_state_gift_rows({"ok": True, "gold": 2334, "small": {"amount": 250, "how": {"tool": "minor_gold_gift", "args": {"player_id": 20, "amount": 250}}},
                                       "large": {"amount": 1000, "how": {"tool": "minor_gold_gift", "args": {"player_id": 20, "amount": 1000}}}})
        self.assertEqual(gold["small"]["call"], A.act("minor_gold_gift", player_id=20, amount=250))
        self.assertNotIn("how", gold["large"], "one row per tier: `call` (GitLab #65)")
        self.assertEqual(gold["large"]["call"]["args"], {"to": "city_state", "action": "gift_gold", "id": 20, "args": {"amount": 1000}})
        new = {"tool": "order", "args": {"to": "city_state", "action": "gift_gold", "id": 20, "args": {"amount": 250}}}
        fresh = A.city_state_gift_rows({"ok": True, "small": {"amount": 250, "how": dict(new)}})
        self.assertEqual((fresh["small"].get("how"), fresh["small"]["call"]), (None, new), "the runtime v286 row passes as it is")
        gold = {"small": gold["small"]}   # the rows below are checked complete
        one = A.annotate_unit({"ok": True, "x": 1, "y": 1, "actions": [{"type": "MISSION_SKIP", "kind": "mission"}],
                               "attack_targets": [{"x": 2, "y": 2}]}, unit_id=98304)
        self.assertEqual(one["actions"][0]["call"]["args"]["id"], 98304, "a single unit's read carries the unit asked about")
        self.assertEqual(one["attack_targets"][0]["call"]["args"]["id"], 98304)
        for reply in (research, prod, pol, routes, spies, targets, strikes, gifts, tiles, home, gold):
            self.assertComplete(A.rows_in(reply))
        self.assertEqual(A.research_rows({"ok": False, "err": "x"}), {"ok": False, "err": "x"})
        self.assertEqual(A.production_rows({"ok": False, "err": "no such city"}, 1), {"ok": False, "err": "no such city"})

    def test_rows_in_finds_the_single_rows_too(self):
        reply = {"items": [{"item": "A", "call": A.act("set_production", city_id=1, item="A"), "buy": A.act("purchase_production", city_id=1, item="A")}],
                 "actions": [A.act("available_production", city_id=1)]}
        self.assertEqual([r["tool"] for r in A.rows_in(reply)], ["state", "order", "order"])


class ObjectRowsTests(unittest.TestCase):
    def test_units_and_cities_rows_carry_what_can_be_done_with_them(self):
        units = A.with_object_rows([{"id": 5, "type": "WARRIOR"}, {"type": "no id"}], A.unit_rows)
        self.assertEqual(units[0]["actions"], [A.act("todo_actions", unit_ids=[5], detail="summary")])
        self.assertNotIn("actions", units[1])
        cities = A.with_object_rows([{"id": 8192, "name": "Assur"}], A.city_rows)
        self.assertEqual([r["tool"] for r in cities[0]["actions"]], ["state", "order"])
        self.assertEqual(cities[0]["actions"][1], A.pick("set_production", ["item"], city_id=8192))
        self.assertEqual(A.with_object_rows({"ok": False}, A.unit_rows), {"ok": False})

    def test_a_city_state_screen_offers_its_buttons_as_rows(self):
        r = A.city_state_rows({"ok": True, "name": "Sidon", "pledge": {"can": True}, "bully_gold": {"can": False},
                               "bully_unit": {"can": True}, "declare_war": {"can": True}}, 20)
        self.assertEqual(r["actions"], [A.act("city_state_action", player_id=20, action="pledge"),
                                        A.act("city_state_action", player_id=20, action="bully_unit"),
                                        A.act("city_state_action", player_id=20, action="declare_war")])
        war = A.city_state_rows({"ok": True, "at_war": True, "peace": {"can": True}}, 21)
        self.assertEqual(war["actions"], [A.act("city_state_action", player_id=21, action="make_peace")])
        self.assertEqual(A.city_state_rows({"ok": False, "err": "x"}, 1), {"ok": False, "err": "x"})

    def test_a_trade_catalog_offers_the_deal_calls_and_a_one_item_ask_per_resource(self):
        r = A.trade_catalog_rows({"ok": True, "resources": [{"resource": "RESOURCE_SALT", "us": 0, "them": 2},
                                                             {"resource": "RESOURCE_MARBLE", "us": 1, "them": 0},
                                                             {"resource": "RESOURCE_DYE", "us": 0, "them": 0}]}, 2)
        self.assertEqual([(x["tool"], x["args"]["action"]) for x in r["actions"]], [("order", "negotiate"), ("order", "propose_deal")])
        self.assertEqual(r["actions"][0]["choose"], ["items"])
        self.assertEqual(r["resources"][0]["call"]["args"]["args"]["items"], [{"type": "RESOURCES", "resource": "RESOURCE_SALT", "from_us": False, "amount": 1}])
        self.assertEqual(r["resources"][1]["call"]["args"]["args"]["items"][0]["from_us"], True)
        self.assertNotIn("call", r["resources"][2])

    def test_the_league_offers_votes_in_session_and_proposals_between(self):
        """Assyria t244 (#56): the UN session's votable rows carried nothing to copy."""
        r = A.league_rows({"ok": True, "in_session": True, "remaining_votes": 28,
                           "votable": [{"resolution_id": 14, "direction": "enact", "yes_no": True},
                                       {"resolution_id": 15, "direction": "enact", "choices": [{"id": 3}]}]})
        yes, no = r["votable"][0]["actions"]
        self.assertEqual((yes["tool"], yes["args"]["to"], yes["args"]["action"]), ("order", "league", "vote"))
        self.assertEqual(yes["args"]["args"]["votes"], [{"resolution_id": 14, "direction": "enact", "num_votes": 28, "choice": "yes"}])
        self.assertEqual(no["args"]["args"]["votes"][0]["choice"], "no")
        self.assertEqual(r["votable"][1]["actions"][0]["choose"], ["votes"])
        self.assertEqual(r["actions"], [A.pick("league_cast_votes", ["votes"])])
        between = A.league_rows({"ok": True, "in_session": False,
                                 "proposable_enact": [{"resolution_type": "RESOLUTION_ARTS_FUNDING"},
                                                      {"resolution_type": "RESOLUTION_WORLD_RELIGION", "choices": [{"id": 1}]}],
                                 "proposable_repeal": [{"resolution_id": 3}]})
        self.assertEqual(between["proposable_enact"][0]["call"], A.act("league_propose_enact", resolution_type="RESOLUTION_ARTS_FUNDING"))
        self.assertEqual(between["proposable_enact"][1]["call"]["choose"], ["choice"])
        self.assertEqual(between["proposable_repeal"][0]["call"], A.act("league_propose_repeal", resolution_id=3))
        self.assertNotIn("actions", between)
        self.assertEqual(A.league_rows({"ok": False, "err": "x"}), {"ok": False, "err": "x"})

    def test_a_paused_order_names_its_two_calls(self):
        self.assertEqual(A.order_pause_rows(9), [A.act("resume_order", order_id=9), A.act("cancel_order", order_id=9)])


# --- a turn played from the rows alone -----------------------------------------------------------------
PRODUCTION = {"ok": True, "items": [{"item": "UNIT_WARRIOR", "kind": "unit", "turns": 5}]}
RESEARCH = [{"tech": "TECH_MINING", "cost": 35, "name": "Mining"}]


class FakeGame:
    """The fake bridge: reads answer with live-shaped replies, writes are recorded."""
    seat = 0
    settle_announcements = None   # the guard's optional sweep of announcement screens: none to sweep

    def __init__(self):
        self.writes = []
        self._units = game_answering(NORMAL)

    def has_state(self, name):
        return True

    def mode(self):
        return "single"

    def turn_state(self, pid=None):
        todo = {"units": [{"id": u["id"], "type": u["type"], "x": u["x"], "y": u["y"], "moves": u["moves"]}
                          for u in NORMAL["units"]],
                "cities": [{"id": 8192, "name": "Venice"}], "promotions": [11], "research_unset": True}
        return {"turn": 270, "active_player": 0, "my_turn": True, "processing": False, "paused": False,
                "hotseat": False, "mode": "single", "blocking_name": "ENDTURN_BLOCKING_UNITS", "todo": todo,
                "pending_popups": []}

    def discussion_pending(self):
        return False

    def clear_hand_off(self, ts):
        return ts

    def todo_actions(self, unit_ids=None, full=False, detail=None, limit=None):
        return Game.todo_actions(self._units, unit_ids, full, detail=detail, limit=limit)

    def available_production(self, city_id):
        return PRODUCTION

    def available_research(self):
        return RESEARCH

    def direct_command(self, unit_id, tool, command):
        return command()   # the one-owner rule (Game.direct_command) has no orders to take here

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)

        def write(*a, **kw):
            self.writes.append((name, a, kw))
            return {"ok": True}
        return write


def fill(row: dict, read_reply) -> dict:
    """A `choose` argument takes the first value under the same key anywhere in the read's reply; it sits at
    the top of the row when the tool takes it there, under `args` otherwise (harness/rows.py)."""
    from harness.surface import dispatch as D
    from harness.surface import vocabulary as V
    args = dict(row["args"])
    for key in row.get("choose") or []:
        stack = [read_reply]
        while stack:
            v = stack.pop()
            if isinstance(v, dict):
                if key in v:
                    top = key in V.TOP_LEVEL[row["tool"]] or key in D.FIXED_FIELDS.get(row["tool"], ())
                    (args if top else args.setdefault("args", {}))[key] = v[key]
                    break
                stack.extend(v.values())
            elif isinstance(v, list):
                stack.extend(v)
    return {"tool": row["tool"], "args": args}


class TurnFromRowsTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeGame()
        self.patches = [mock.patch.object(m, "game", lambda: self.fake),
                        mock.patch.dict(os.environ, {"CIV5_TUNERD_SOCK": "/tmp/civ5-test-rows.sock", "CIV5_SEAT": "0"}),
                        mock.patch.object(m, "_seat_rechecked", True),
                        mock.patch.dict(m._RECENT, {}, clear=True)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def _do(self, rows):
        return anyio.run(session, [(BATCH, {"actions": rows})])[0]["results"]

    def test_a_turn_plays_from_the_todo_rows_alone(self):
        decisions = B.decisions(self.fake.turn_state(), [{"id": 8192, "name": "Venice"}])
        reads = [row for d in decisions for row in d["actions"] if "choose" not in row]
        results = self._do(reads)
        self.assertFalse([r for r in results if isinstance(r["result"], dict) and r["result"].get("ok") is False], results)
        replies = {i: r["result"] for i, r in enumerate(results)}
        orders = []
        for d in decisions:
            own_reads = [i for i, r in enumerate(reads) if r in d["actions"]]
            read_reply = replies[own_reads[0]] if own_reads else {}
            # a unit's read hands back the unit's own rows (its complete orders are played, its further reads and
            # half-chosen rows are not); every other read hands back each choice with `call` (#47): the first is
            # taken, as a player would pick one; a decision whose read carries no call fills its `choose` row
            complete = [r for r in A.rows_in(read_reply) if "choose" not in r and kind(r["tool"]) == "write"]
            if d["kind"] in ("unit_orders", "promotion"):
                orders.extend(complete)
            elif complete:
                orders.append(complete[0])
            else:
                orders.extend(fill(r, read_reply) for r in d["actions"] if "choose" in r)
        results = self._do(orders)
        self.assertTrue(all(r["result"]["ok"] for r in results), results)
        tools = {name for name, _a, _kw in self.fake.writes}
        args = {name: (a, kw) for name, a, kw in self.fake.writes}
        self.assertEqual(args["set_research"][0], ("TECH_MINING",))
        self.assertEqual(args["set_production"][0][0], 8192)
        self.assertIn("UNIT_WARRIOR", args["set_production"][0])
        self.assertEqual([w[0] for w in self.fake.writes].count("set_production"), 1, "one choice per decision")
        self.assertIn("choose_promotion", tools)
        self.assertIn("move_unit", tools, "the warrior's melee target became a move_unit row")
        self.assertIn("unit_mission", tools, "the warrior's MISSION_HEAL became a unit_mission row")
        self.assertNotIn("unit_mission_targets", tools, "a read never lands among the writes")

    def test_the_turn_above_types_no_tool_name_but_the_batch_carrier(self):
        """Outside its assertions, the test above names no catalog tool: every call it makes came from a reply."""
        tree = ast.parse(pathlib.Path(__file__).read_text())
        fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                  and n.name == "test_a_turn_plays_from_the_todo_rows_alone")
        typed = set()
        for stmt in fn.body:
            call = stmt.value if isinstance(stmt, ast.Expr) else None
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr.startswith("assert"):
                continue
            typed |= {n.value for n in ast.walk(stmt) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        names = {t.name for t in survey.tools()}
        self.assertEqual(typed & names, set())
        self.assertEqual(BATCH, "do")


BATCH = "do"


if __name__ == "__main__":
    unittest.main()
