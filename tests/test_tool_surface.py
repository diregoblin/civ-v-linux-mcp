"""The nine tools (GitLab #48, stage 2a): each `(tool, action)` / `(what, view)` row dispatches to its old handler
with the same arguments, a malformed call is refused naming the shape, and a merged family's reply is the old
reply byte for byte. The old names stay registered beside the nine until #52.
"""
import contextlib
import json
import os
import unittest
from unittest import mock

import anyio

from harness import gate as G
from harness import mcp_server as m
from harness.surface import dispatch as D
from harness.surface import forward as F
from harness.surface import retirement as R
from harness.surface import survey
from harness.surface import vocabulary as V


def sample_args(old: str) -> dict:
    """The old handler's required arguments with placeholder values (by type), under their OLD names."""
    sch = D.schema(old)
    out = {}
    for name in sch.get("required") or []:
        p = (sch.get("properties") or {}).get(name) or {}
        t = p.get("type") or next((x.get("type") for x in p.get("anyOf", []) if x.get("type") != "null"), "string")
        out[name] = {"integer": 7, "number": 7, "boolean": True, "array": [1], "object": {}}.get(t, f"X_{name}")
    return out


def new_args(row: R.Row, old_args: dict) -> dict:
    return {row.renames.get(k, k): v for k, v in old_args.items()}


class EveryRowDispatchesTests(unittest.TestCase):
    """Every old name of the retirement map is reached from its new call with its own arguments."""

    def test_every_old_name_is_reached(self):
        names = {t.name for t in survey.tools()}
        reached, skipped = set(), set()
        for old, row in R.RETIRED.items():
            self.assertIn(old, names)
            fixed = dict(row.fixed)
            if row.tool in ("answer", "question"):
                skipped.add(old)      # answers and questions dispatch on the live gate: AnswerTests, ThroughTheServerTests
                continue
            if any(isinstance(v, R.FromArg) for v in fixed.values()):
                fixed = {k: ("bully_gold" if isinstance(v, R.FromArg) else v) for k, v in fixed.items()}
                args = new_args(row, {k: v for k, v in sample_args(old).items() if k != "action"})
            else:
                args = new_args(row, sample_args(old))
            if old == "turn_digest":
                args["detail"] = "digest"
            if old == "purchase_cost":
                args["item"] = "UNIT_X"
            target = D.resolve(row.tool, fixed, args)
            if isinstance(target, D.Composite):
                self.assertIn(old, {c.tool for c in target.parts.values()}, old)
                reached.add(old)
                continue
            self.assertIsInstance(target, D.Call, (old, target))
            candidates = D.INDEX[row.key]
            if target.tool == old:
                reached.add(old)
            else:
                # a shared row whose default is another old name: the arguments did not say (players, known_world, the
                # governor trio without its field, a great-work swap, the production chooser's default)
                self.assertIn(target.tool, candidates, (old, target))
                self.assertIn(old, {"players", "known_world", "set_avoid_growth", "set_auto_specialists",
                                    "swap_great_works", "set_swappable_great_work", "unlock_policy_branch"}, (old, target))
        self.assertEqual(skipped, {n for n, r in R.RETIRED.items() if r.tool in ("answer", "question")})
        # 145 old names: 10 questions and 13 answers dispatch on the gate, 7 share a row whose default is another name
        self.assertGreaterEqual(len(reached), 145 - 10 - 13 - 7)
        # the shared rows are reached when the arguments say which
        self.assertEqual(D.resolve("order", {"to": "city", "action": "governor"}, {"id": 1, "avoid": True}).tool, "set_avoid_growth")
        self.assertEqual(D.resolve("order", {"to": "city", "action": "governor"}, {"id": 1, "automatic": True}).tool, "set_auto_specialists")
        self.assertEqual(D.resolve("order", {"to": "city", "action": "great_work"}, {"their_work_id": 3}).tool, "swap_great_works")
        self.assertEqual(D.resolve("order", {"to": "empire", "action": "policy"}, {"policy": "POLICY_BRANCH_HONOR"}),
                         D.Call("unlock_policy_branch", {"branch": "POLICY_BRANCH_HONOR"}))
        self.assertEqual(D.resolve("order", {"to": "empire", "action": "policy"}, {"policy": "POLICY_LIBERTY"}).tool, "choose_policy")

    def test_the_arguments_are_renamed_back_and_a_single_id_becomes_the_list_the_old_handler_takes(self):
        self.assertEqual(D.resolve("order", {"to": "city", "action": "produce"}, {"id": 3, "item": "UNIT_X"}),
                         D.Call("set_production", {"city_id": 3, "item": "UNIT_X"}))
        self.assertEqual(D.resolve("state", {"what": "units", "view": "actions"}, {"id": 7}),
                         D.Call("todo_actions", {"unit_ids": [7]}))
        self.assertEqual(D.resolve("state", {"what": "units", "view": "actions"}, {"id": [7, 8], "detail": "summary"}),
                         D.Call("todo_actions", {"unit_ids": [7, 8], "detail": "summary"}))
        self.assertEqual(D.resolve("state", {"what": "unit", "view": "tactical"}, {"id": 5, "radius": 2}),
                         D.Call("tactical_view", {"unit_id": 5, "radius": 2}))
        self.assertEqual(D.resolve("session", {"action": "seat"}, {"seat": 1}), D.Call("set_seat", {"player_id": 1}))
        self.assertEqual(D.resolve("reference", {"book": "playbook"}, {"section": "start"}), D.Call("how_to_play", {"topic": "start"}))
        self.assertEqual(D.resolve("turn", {"action": "briefing"}, {"detail": "digest"}), D.Call("turn_digest", {}))
        self.assertEqual(D.resolve("turn", {"action": "status"}, {}), D.Call("turn_status", {}))
        self.assertEqual(D.resolve("order", {"to": "city_state", "action": "make_peace"}, {"id": 20}),
                         D.Call("city_state_action", {"player_id": 20, "action": "make_peace"}))
        full = D.resolve("state", {"what": "city_state", "view": "full"}, {"id": 20})
        self.assertEqual({k: c.tool for k, c in full.parts.items()}, D.CITY_STATE_FULL)
        self.assertEqual(full.parts["bonuses"].args, {"minor_id": 20})

    def test_the_vocabulary_and_the_index_agree(self):
        for (head, tail), names in D.INDEX.items():
            tool, _, what = head.partition(":")
            if tool == "state":
                self.assertIn(tail, V.VIEWS[what], (head, tail))
            elif tool == "order":
                self.assertTrue(tail in V.ACTIONS[what] or tail.startswith("<"), (head, tail))
            for n in names:
                self.assertEqual(R.RETIRED[n].key, (head, tail))


class RefusalTests(unittest.TestCase):
    def test_a_malformed_order_is_refused_naming_the_shape_with_an_example(self):
        r = D.resolve("order", {"to": "city", "action": "produce"}, {"id": 3})
        self.assertIsInstance(r, D.Refusal)
        self.assertIn("needs item", r.err)
        self.assertEqual(r.example, {"tool": "order", "args": {"to": "city", "action": "produce", "id": 1, "args": {"item": "<item>"}}})
        # GitLab #146: a 2.x refusal accepts the 2.x call, never the retired one
        self.assertTrue(r.accepts.startswith('order(to="city", action="produce", id: integer'), r.accepts)
        r = D.resolve("order", {"to": "unit", "action": "move"}, {"id": 3, "x": 1, "y": 2, "speed": 9})
        self.assertIn("does not take speed", r.err)
        r = D.resolve("order", {"to": "unit", "action": "fly"}, {"id": 1})
        self.assertEqual(r.choices, sorted(V.ACTIONS["unit"]))
        r = D.resolve("state", {"what": "nothing"}, {})
        self.assertIn("league", r.choices)
        self.assertEqual(len(r.choices), len(set(r.choices)))
        reply = r.reply()
        self.assertEqual((reply["ok"], "choices" in reply), (False, True))

    def test_an_ambiguous_shared_row_is_refused_with_every_shape(self):
        r = D.resolve("order", {"to": "city", "action": "governor"}, {"id": 1})
        self.assertIsInstance(r, D.Refusal)
        self.assertEqual(len(r.accepts), 3)

    def test_an_example_for_every_old_name_is_a_row_of_the_new_tool(self):
        for old, row in R.RETIRED.items():
            ex = F.example(old)
            self.assertEqual(ex["tool"], row.tool, old)
            self.assertIsInstance(ex["args"], dict)


class AnswerTests(unittest.TestCase):
    FREE = {"turn": 24, "active_player": 0, "my_turn": True, "processing": False, "paused": False, "hotseat": False,
            "pending_popups": [], "todo": {"units": [], "research_unset": False}, "blocking_name": "ENDTURN_BLOCKING_UNITS"}

    def gate(self, **ts):
        return G.compute_gate({**self.FREE, **ts}, 0)

    def test_a_fixed_word_needs_no_gate(self):
        self.assertEqual(D.resolve("answer", {"choice": "accept"}, {}, None), D.Call("accept_deal", {}))
        self.assertEqual(D.resolve("answer", {"choice": "leave"}, {}, None), D.Call("dismiss_discussion", {}))
        self.assertEqual(D.resolve("answer", {"choice": "accept_friendship"}, {"player_id": 2}, None),
                         D.Call("accept_friendship", {"player_id": 2}))

    def test_every_popup_the_gate_knows_takes_its_choice(self):
        want = {"BUTTONPOPUP_CHOOSETECH": ("set_research", "tech"), "BUTTONPOPUP_CHOOSEPRODUCTION": ("set_production", "item"),
                "BUTTONPOPUP_CHOOSEPOLICY": ("choose_policy", "policy"), "BUTTONPOPUP_CHOOSE_IDEOLOGY": ("choose_ideology", "branch"),
                "BUTTONPOPUP_CHOOSEUNITPROMOTION": ("choose_promotion", "promotion"), "BUTTONPOPUP_FOUND_PANTHEON": ("found_pantheon", "belief"),
                "BUTTONPOPUP_FOUND_RELIGION": ("found_religion", "religion"), "BUTTONPOPUP_ENHANCE_RELIGION": ("enhance_religion", "religion"),
                "BUTTONPOPUP_CHOOSE_GOODY_HUT_REWARD": ("choose_goody_hut", "goody"), "BUTTONPOPUP_CITY_CAPTURED": ("choose_city_capture", "choice"),
                "BUTTONPOPUP_CHOOSE_FAITH_GREAT_PERSON": ("choose_faith_great_person", "unit"),
                "BUTTONPOPUP_CHOOSE_ARCHAEOLOGY": ("choose_archaeology", "choice"), "BUTTONPOPUP_CHOOSE_MAYA_BONUS": ("choose_maya_bonus", "unit")}
        extra = {"set_production": {"id": 3}, "choose_promotion": {"id": 5}, "found_religion": {"beliefs": ["B1", "B2"], "city_x": 1, "city_y": 2},
                 "enhance_religion": {"belief4": "B4", "belief5": "B5", "city_x": 1, "city_y": 2}, "choose_archaeology": {"x": 4, "y": 9}}
        for popup in G.POPUP_RESOLUTIONS:
            if popup == "BUTTONPOPUP_TECH_TREE":
                continue
            old, arg = want[popup]
            choice = 2 if arg == "choice" and old == "choose_archaeology" else "CHOICE_X"
            r = D.resolve("answer", {"choice": choice}, extra.get(old, {}), self.gate(pending_popups=[{"name": popup}]))
            self.assertIsInstance(r, D.Call, (popup, r))
            self.assertEqual(r.tool, old, popup)
            self.assertEqual(r.args[arg], choice, popup)
            self.assertFalse(set(D.required(old)) - set(r.args), (popup, r))
        r = D.resolve("answer", {"choice": "POLICY_BRANCH_HONOR"}, {}, self.gate(pending_popups=[{"name": "BUTTONPOPUP_CHOOSEPOLICY"}]))
        self.assertEqual(r, D.Call("unlock_policy_branch", {"branch": "POLICY_BRANCH_HONOR"}))
        r = D.resolve("answer", {"choice": 1}, {}, G.popup_gate({"name": "BUTTONPOPUP_RETURN_CIVILIAN"}))
        self.assertEqual(r, D.Call("answer_popup", {"button": 1}))

    def test_a_leader_screen_and_the_tech_chooser(self):
        self.assertEqual(D.resolve("answer", {"choice": 2}, {}, self.gate(discussion_pending=True)),
                         D.Call("respond_discussion", {"button_id": 2}))
        r = D.resolve("answer", {"choice": "yes"}, {}, self.gate(discussion_pending=True))
        self.assertIsInstance(r, D.Refusal)
        self.assertIn("answer", r.choices)
        self.assertEqual(D.resolve("answer", {"choice": "x"}, {}, self.gate(leader_greeting_pending=True)), D.Call("dismiss_discussion", {}))
        self.assertEqual(D.resolve("answer", {"choice": "TECH_MINING"}, {},
                                   self.gate(tech_popup_pending=True, todo={"research_unset": True})), D.Call("set_research", {"tech": "TECH_MINING"}))
        r = D.resolve("answer", {"choice": "TECH_MINING"}, {}, None)
        self.assertIn("nothing is asked", r.err)
        r = D.resolve("answer", {"choice": 1}, {}, self.gate(paused=True))
        self.assertIn("paused", r.err)


    def test_a_blocker_question_without_its_popup_is_answered_on_the_blocker(self):
        """GitLab #95 (Maya t77 / t88): ENDTURN_BLOCKING_MAYA_LONG_COUNT with no popup open -- question() said
        nothing was asked and answer(choice=UNIT_...) refused, so the turn could not end through the nine tools.
        With no gate up, the end-turn blocker names the question; the popup, when it is open, still outranks it."""
        want = {"ENDTURN_BLOCKING_MAYA_LONG_COUNT": ("choose_maya_bonus", "unit", {}),
                "ENDTURN_BLOCKING_STEAL_TECH": ("steal_tech", "tech", {"player_id": 2}),
                "ENDTURN_BLOCKING_FREE_ITEMS": ("choose_free_great_person", "unit", {}),
                "ENDTURN_BLOCKING_FAITH_GREAT_PERSON": ("choose_faith_great_person", "unit", {}),
                "ENDTURN_BLOCKING_CHOOSE_ARCHAEOLOGY": ("choose_archaeology", "choice", {"x": 4, "y": 9})}
        self.assertEqual(set(want), set(G.BLOCKER_QUESTIONS))
        for blocker, (old, arg, extra) in want.items():
            r = D.resolve("answer", {"choice": "CHOICE_X"}, extra, None, blocker)
            self.assertEqual((r.tool, r.args[arg]), (old, "CHOICE_X"), blocker)
            self.assertFalse(set(D.required(old)) - set(r.args), (blocker, r))
            self.assertEqual(D.question_read(None, blocker), D.Call(G.BLOCKER_QUESTIONS[blocker]["read_first"], {}))
            rows = G.blocker_rows(blocker)
            self.assertEqual(rows[0], {"tool": "question", "args": {}})
            self.assertEqual((rows[1]["tool"], rows[1]["choose"][0]), ("answer", "choice"), rows)
        r = D.resolve("answer", {"choice": "UNIT_PROPHET"}, {}, None, "ENDTURN_BLOCKING_UNITS")
        self.assertIn("nothing is asked", r.err)
        self.assertIsNone(D.question_read(None, "ENDTURN_BLOCKING_UNITS"))
        gate = self.gate(pending_popups=[{"name": "BUTTONPOPUP_CHOOSE_GOODY_HUT_REWARD"}])
        r = D.resolve("answer", {"choice": "GOODY_GOLD"}, {}, gate, "ENDTURN_BLOCKING_MAYA_LONG_COUNT")
        self.assertEqual(r.tool, "choose_goody_hut", "a popup on screen outranks the blocker")
        self.assertEqual(G.blocker_question({**self.FREE, "blocking_name": "ENDTURN_BLOCKING_MAYA_LONG_COUNT"}),
                         "ENDTURN_BLOCKING_MAYA_LONG_COUNT")
        self.assertIsNone(G.blocker_question(self.FREE))
        self.assertIsNone(G.blocker_question(None))


# --- through the server: the old reply byte for byte -----------------------------------------------------
    def test_another_humans_deal_is_a_question_without_a_screen(self):
        """GitLab #161 (Codex seat 0, t15): the other human's proposal waited on the table with no screen and no
        blocker; question() said nothing was asked and sent the seat to question(), the deals screen refused. The
        proposal is a screenless question: question() reads the table, accept / refuse answer it, any other
        choice is refused naming the two."""
        self.assertEqual(G.screenless_question({**self.FREE, "pending_deal_from": 1}), G.PENDING_DEAL)
        self.assertEqual(G.screenless_question({**self.FREE, "pending_deal_from": 1, "blocking_name": "ENDTURN_BLOCKING_STEAL_TECH"}),
                         "ENDTURN_BLOCKING_STEAL_TECH", "a blocker question is asked first")
        for ts in (self.FREE, {**self.FREE, "pending_deal_from": None}, {**self.FREE, "pending_deal_from": -1},
                   {**self.FREE, "pending_deal_from": True}):
            self.assertIsNone(G.screenless_question(ts), ts)
        self.assertEqual(D.question_read(None, G.PENDING_DEAL), D.Call("incoming_deal", {}))
        self.assertEqual(D.resolve("answer", {"choice": "accept"}, {}, None, G.PENDING_DEAL), D.Call("accept_deal", {}))
        self.assertEqual(D.resolve("answer", {"choice": "refuse"}, {}, None, G.PENDING_DEAL), D.Call("refuse_deal", {}))
        r = D.resolve("answer", {"choice": 1}, {}, None, G.PENDING_DEAL)
        self.assertIsInstance(r, D.Refusal)
        self.assertIn("another player's deal", r.err)
        self.assertEqual(r.choices, ["accept", "refuse"])
        gate = self.gate(discussion_pending=True, trade_state="TRADE_AI_MAKES_OFFER")
        self.assertEqual(D.question_read(gate, None), D.Call("incoming_deal", {}), "an AI's deal on screen reads the same table")


class FakeGame:
    seat = 0
    settle_announcements = None
    pending_deal_from = None
    lock = contextlib.nullcontext   # the real Game's per-poll lock (mcp_server.game sets it)

    def __init__(self, popups=None):
        self.calls = []
        self.popups = popups or []

    def has_state(self, name):
        return True

    def mode(self):
        return "single"

    blocking = "ENDTURN_BLOCKING_UNITS"

    def turn_state(self, pid=None):
        return {"turn": 9, "active_player": 0, "my_turn": True, "processing": False, "paused": False, "hotseat": False,
                "blocking_name": self.blocking, "todo": {"units": [{"id": 1, "type": "WARRIOR", "x": 1, "y": 1, "moves": 2}]},
                "pending_popups": list(self.popups), "pending_deal_from": self.pending_deal_from}

    def discussion_pending(self):
        return False

    def clear_hand_off(self, ts):
        return ts

    def _goody_popup_unit(self):
        return 7

    def direct_command(self, unit_id, tool, command):
        return command()   # the one-owner rule (Game.direct_command) has no orders to take here

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)

        def fn(*a, **kw):
            self.calls.append((name, a, kw))
            if name == "goody_hut_options":   # the real mixin attaches the answers (harness/affordances); the fake does the same
                from harness import affordances as A
                return A.answered({"ok": True, "unit_id": 7, "options": [{"goody": "GOODY_GOLD"}]}, A.goody_hut_answers)
            if name == "maya_options":
                from harness import affordances as A
                return A.answered({"ok": True, "count": 1, "options": [{"unit": "UNIT_PROPHET", "available": True},
                                                                       {"unit": "UNIT_ARTIST", "available": False}]}, A.maya_answers)
            if name == "league_status":
                return {"ok": True, "host": "me", "resolutions": [{"id": 1}]}
            return {"ok": True, "called": name}
        return fn


class ThroughTheServerTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeGame()
        self.patches = [mock.patch.object(m, "game", lambda: self.fake),
                        mock.patch.dict(os.environ, {"CIV5_TUNERD_SOCK": "/tmp/civ5-test-surface.sock", "CIV5_SEAT": "0"}),
                        mock.patch.object(m, "_seat_rechecked", True),
                        mock.patch.dict(m._RECENT, {}, clear=True)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def run_tools(self, calls, client_name: str = "test-client"):
        """Run the calls through a client session; a call named `None` lists the tools instead (the listing
        lands in the outputs as {name: input_schema})."""
        outs = []

        async def go():
            from mcp import ClientSession
            from mcp.shared.memory import create_client_server_memory_streams
            from mcp.types import Implementation
            async with create_client_server_memory_streams() as (cs, ss):
                async with anyio.create_task_group() as tg:
                    srv = m.mcp._lowlevel_server

                    async def run_server():
                        await srv.run(ss[0], ss[1], srv.create_initialization_options())
                    tg.start_soon(run_server)
                    async with ClientSession(cs[0], cs[1], client_info=Implementation(name=client_name, version="0")) as s:
                        await s.initialize()
                        for name, args in calls:
                            if name is None:
                                r = await s.list_tools()
                                outs.append({t.name: getattr(t, "input_schema", None) or getattr(t, "inputSchema", None) for t in r.tools})
                                continue
                            res = await s.call_tool(name, args)
                            outs.append(res.content[0].text)
                    tg.cancel_scope.cancel()
        anyio.run(go)
        return outs

    def test_the_nine_are_registered_beside_the_old_catalog(self):
        self.assertEqual([t.name for t in survey.new_tools()], ["reference", *[t for t in V.TOOLS if t != "reference"]])
        self.assertEqual(len(survey.tools()), 145)

    def test_a_merged_family_answers_byte_for_byte(self):
        old, new, old2, new2, old3, new3 = self.run_tools([
            ("league_status", {}), ("state", {"what": "league"}),
            ("units", {}), ("state", {"what": "units"}),
            ("turn_status", {}), ("turn", {"action": "status"})])
        self.assertEqual(self.without_renamed(old), new)     # the old name runs through the map now (#52)
        self.assertEqual(self.without_renamed(old2), new2)
        self.assertEqual(json.loads(old3)["turn"], json.loads(new3)["turn"])
        self.assertEqual(sorted(k for k in json.loads(old3) if k != "renamed"), sorted(json.loads(new3)))

    @staticmethod
    def without_renamed(reply: str) -> str:
        d = json.loads(reply)
        d.pop("renamed", None)
        return json.dumps(d, separators=(",", ":"), ensure_ascii=False)

    def test_an_order_runs_the_old_handler_with_the_old_arguments(self):
        out, = self.run_tools([("order", {"to": "unit", "action": "move", "id": 1, "args": {"x": 2, "y": 3}})])
        self.assertTrue(json.loads(out)["ok"], out)
        self.assertIn(("move_unit", (1, 2, 3)), [(c[0], c[1][:3]) for c in self.fake.calls])
        out, = self.run_tools([("order", {"to": "unit", "action": "move", "id": 1})])
        r = json.loads(out)
        self.assertFalse(r["ok"])
        self.assertIn("needs x, y", r["err"])
        self.assertEqual(r["example"]["tool"], "order")

    def test_the_other_tools_route(self):
        outs = self.run_tools([("notebook", {"action": "recall"}), ("recall", {}),
                               ("reference", {"book": "playbook"}), ("how_to_play", {}),
                               ("session", {"action": "save"}),
                               ("batch", {"actions": [{"tool": "order", "args": {"to": "unit", "action": "move", "id": 1, "args": {"x": 1, "y": 1}}},
                                                      {"tool": "move_unit", "args": {"unit_id": 1, "x": 2, "y": 2}}]})])
        self.assertEqual(outs[0], self.without_renamed(outs[1]))
        self.assertEqual(outs[2], outs[3])
        self.assertIn("quick_save", [c[0] for c in self.fake.calls])
        batch = json.loads(outs[5])
        self.assertEqual((batch["ok"], batch["done"]), (True, 2))
        self.assertEqual([c[1][:3] for c in self.fake.calls if c[0] == "move_unit"], [(1, 1, 1), (1, 2, 2)])
        out, = self.run_tools([("batch", {"actions": [{"tool": "turn", "args": {"action": "finish"}}]})])
        self.assertFalse(json.loads(out)["ok"])

    def test_question_and_answer_follow_the_gate(self):
        self.fake.popups = [{"name": "BUTTONPOPUP_CHOOSE_GOODY_HUT_REWARD"}]
        out, = self.run_tools([("question", {})])
        r = json.loads(out)
        self.assertEqual(r["gate"]["popup"], "BUTTONPOPUP_CHOOSE_GOODY_HUT_REWARD")
        self.assertEqual(r["answers"], [{"tool": "answer", "args": {"choice": "GOODY_GOLD"}}])
        out, = self.run_tools([("answer", {"choice": "GOODY_GOLD"})])
        self.assertTrue(json.loads(out)["ok"], out)
        self.assertIn(("choose_goody_hut", "GOODY_GOLD"), [(c[0], c[1][0]) for c in self.fake.calls if c[1]])
        self.fake.popups = []
        out, = self.run_tools([("question", {})])
        r = json.loads(out)
        self.assertEqual((r["pending"], r["decisions"][0]["kind"]), (False, "unit_orders"))
        out, = self.run_tools([("answer", {"choice": "GOODY_GOLD"})])
        self.assertIn("nothing is asked", json.loads(out)["err"])

    def test_the_long_count_is_asked_and_answered_without_its_popup(self):
        """GitLab #95: the blocker alone, no BUTTONPOPUP_CHOOSE_MAYA_BONUS in pending_popups."""
        self.fake.blocking = "ENDTURN_BLOCKING_MAYA_LONG_COUNT"
        out, = self.run_tools([("question", {})])
        r = json.loads(out)
        self.assertEqual((r["pending"], r["blocker"], r["gate"]), (True, "ENDTURN_BLOCKING_MAYA_LONG_COUNT", None))
        self.assertEqual(r["answers"], [{"tool": "answer", "args": {"choice": "UNIT_PROPHET"}}])
        out, = self.run_tools([("answer", {"choice": "UNIT_PROPHET"})])
        self.assertTrue(json.loads(out)["ok"], out)
        self.assertIn(("choose_maya_bonus", "UNIT_PROPHET"), [(c[0], c[1][0]) for c in self.fake.calls if c[1]])
        self.fake.blocking = "ENDTURN_BLOCKING_STEAL_TECH"
        out, = self.run_tools([("answer", {"choice": "TECH_MINING", "args": {"player_id": 2}})])
        self.assertTrue(json.loads(out)["ok"], out)
        self.assertIn(("steal_tech", ("TECH_MINING", 2)), [(c[0], c[1][:2]) for c in self.fake.calls if c[1]])

    def test_a_human_proposal_is_asked_and_answered_without_a_screen(self):
        """GitLab #161: status.pending_deal_from names the other human seat, nothing is on screen."""
        self.fake.pending_deal_from = 1
        out, = self.run_tools([("question", {})])
        r = json.loads(out)
        self.assertEqual((r["pending"], r["called"], r["from"], r["gate"]), (True, "incoming_deal", 1, None))
        self.assertNotIn("blocker", r)
        out, = self.run_tools([("answer", {"choice": 1})])
        r = json.loads(out)
        self.assertFalse(r["ok"])
        self.assertEqual(r["choices"], ["accept", "refuse"])
        out, = self.run_tools([("answer", {"choice": "refuse"})])
        self.assertTrue(json.loads(out)["ok"], out)
        self.assertIn("refuse_deal", [c[0] for c in self.fake.calls])
        self.fake.pending_deal_from = None
        out, = self.run_tools([("question", {})])
        self.assertFalse(json.loads(out)["pending"])

    def test_the_ais_are_moving_hint_rests_on_the_state_after_the_screen_closed(self):
        """GitLab #155 (hotseat seat 1, t7): a first-meeting greeting freezes my_turn to false while it is up, so
        answer(choice='leave') read the pre-answer state as "the AIs are still moving" on the seat's own open turn
        and the wait it named returned at once. The hint comes from a read after the close (#111's case keeps it)."""
        base = dict(self.fake.turn_state())
        screen = {"up": True}
        self.fake.turn_state = lambda pid=None: {**base, "my_turn": not screen["up"], "leader_greeting_pending": screen["up"]}
        self.fake.dismiss_discussion = lambda *a, **k: (screen.update(up=False), {"ok": True, "closed": "greeting"})[1]
        out, = self.run_tools([("answer", {"choice": "leave"})])
        r = json.loads(out)
        self.assertTrue(r["ok"], out)
        self.assertNotIn("next", r, "the seat's own turn went on: no wait is named")
        screen["up"] = True
        self.fake.turn_state = lambda pid=None: {**base, "my_turn": False, "leader_greeting_pending": screen["up"]}
        out, = self.run_tools([("answer", {"choice": "leave"})])
        r = json.loads(out)
        self.assertIn("AIs are still moving", r["next"], "answered during the AI round (#111): the wait is named")

    def test_from_the_main_menu_every_tool_answers_the_no_game_gate(self):
        """GitLab #158 (Codex seat 0, startup): turn(action='briefing') came back as a harness error naming the Lua
        states ("no Lua state named 'InGame'; have [...]") with no gate; status alone knew the main menu."""
        def no_ingame(pid=None):
            raise KeyError("no Lua state named 'InGame'; have ['FrontEnd', 'MainMenu'] (the game is on another screen)")
        self.fake.turn_state = no_ingame
        self.fake.has_state = lambda name: name != "InGame"
        self.fake.front_end_screen = lambda: "MainMenu"
        briefing, units, status = self.run_tools([("turn", {"action": "briefing", "since": "turn"}),
                                                  ("state", {"what": "units"}), ("turn", {"action": "status"})])
        for out in (briefing, units):
            r = json.loads(out)
            self.assertEqual((r["ok"], r["ingame"], r["screen"], r["gate"]["name"]), (False, False, "MainMenu", "no_game"), out)
            self.assertIn("load_latest", r["err"])
            self.assertNotIn("Lua state", r["err"])
        r = json.loads(status)
        self.assertEqual((r["ok"], r["ingame"], r["gate"]["name"]), (True, False, "no_game"))

    def test_an_unlisted_old_name_or_alias_runs_with_renamed(self):
        out, described, batch = self.run_tools([("summary", {}),
                                                ("call", {"tool": "summary", "describe": True}),
                                                ("do", {"actions": [{"tool": "summary", "args": {}}]})])
        r = json.loads(out)
        self.assertEqual((r["ok"], r["renamed"]), (True, 'state(what="empire")'))   # the overview handler ran (its game method is `summary`)
        self.assertEqual(json.loads(described)["renamed"], 'state(what="empire")')
        self.assertEqual(json.loads(batch)["results"][0]["result"]["renamed"], 'state(what="empire")')
        # every old name is off the listing (#52) and reached through the map: the old reply plus the key
        old, new = self.run_tools([("league_status", {}), ("state", {"what": "league"})])
        self.assertEqual(json.loads(old), {**json.loads(new), "renamed": 'state(what="league")'})
        self.assertNotIn("renamed", json.loads(new))
        self.assertIn("league_status", m.retired_tools())

    def test_with_the_map_off_the_nine_still_answer_and_an_alias_is_unknown(self):
        with mock.patch.object(F, "old_name", lambda name: None):
            unknown, new = self.run_tools([("summary", {}), ("state", {"what": "league"})])
        self.assertIn("Unknown tool: summary", unknown)
        self.assertNotIn("overview", unknown, "no retired name is suggested")
        self.assertEqual(json.loads(new)["host"], "me")

    def test_the_listing_shows_order_as_one_flat_shape_for_every_client(self):
        # Measured 2026-10-25 to 2026-10-27 (docs/ARCHITECTURE.md): Codex and Claude Code mangled the oneOf, Grok
        # passed it through and validated nothing; one flat shape since, and TDQS's shadow prefilter is quiet
        for client in ("claude-code", "codex-mcp-client", "grok-shell-civ5/1.0.70", "AcmeClient/1"):
            listing, = self.run_tools([(None, {})], client_name=client)
            order = listing["order"]
            self.assertNotIn("oneOf", order, client)
            self.assertEqual(order["properties"]["to"]["enum"], list(V.ACTIONS), client)
            self.assertEqual(sorted(k for k in ("to", "id", "action", "args", "action_id") if k in order["properties"]),
                             ["action", "action_id", "args", "id", "to"], client)
            self.assertEqual(order["required"], ["to", "action"], client)
            for to in V.ACTIONS:
                self.assertIn(f"{to}: ", order["properties"]["action"]["description"], client)
        listing, out = self.run_tools([(None, {}), ("order", {"to": "unit", "action": "produce", "id": 1})], client_name="claude-code")
        r = json.loads(out)                                             # the server refuses the malformed itself
        self.assertFalse(r["ok"])
        self.assertIn("order:unit has no 'produce'", r["err"])
        self.assertIn("move", r["choices"])


if __name__ == "__main__":
    unittest.main()


class TheWordsTests(unittest.TestCase):
    """Stage 3a (#53): the instructions, the playbook and the generated topics speak the nine tools."""

    RETIRED_FORMS = [n for n in R.RETIRED if n != "reference"]

    def names_in(self, text: str) -> list[str]:
        from harness.surface.audit import named_in
        return named_in(text, self.RETIRED_FORMS)

    def test_the_instructions_name_no_retired_tool_and_fit_the_cut(self):
        text = m.mcp._lowlevel_server.instructions
        self.assertLess(len(text), 2000)
        self.assertEqual(self.names_in(text), [])
        for word in ('turn(action="finish")', "question()", "answer(choice", 'notebook(action="remember")', "batch(actions", 'reference(book="playbook"'):
            self.assertIn(word, text)

    def test_the_playbook_and_the_index_name_no_retired_tool(self):
        from harness import guide
        self.assertEqual(self.names_in(guide.how_to_play("all")), [])
        self.assertEqual(self.names_in(guide.index()), [])
        for topic in guide.PLAYBOOK_TOPICS:
            self.assertEqual(self.names_in(guide.how_to_play(topic)), [], topic)

    def test_the_docs_name_no_retired_tool(self):
        """#54: a reader of README, TOOL_REPLIES, AGENT_INSTALL, ARCHITECTURE and LIMITATIONS meets the nine alone
        (a `Game.` method keeps its dotted name; CHANGELOG, ROADMAP, GAPS, NOTES and the handoff are history)."""
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        for doc in ("README.md", "docs/TOOL_REPLIES.md", "docs/AGENT_INSTALL.md", "docs/ARCHITECTURE.md", "docs/LIMITATIONS.md"):
            text = (root / doc).read_text()
            self.assertEqual(self.names_in(text), [], doc)
        self.assertIn('turn(action="finish")', (root / "README.md").read_text())

    def test_reference_playbook_orders_is_the_validators_table(self):
        from harness.surface import table
        from harness.mcp_tools.reference import reference
        rendered = table.render()
        with mock.patch.object(m, "game", lambda: object()):     # the playbook needs no game; the guard still connects
            self.assertEqual(reference(section="orders", book="playbook"), rendered)
        self.assertIn('| city | produce | `id`, `item` | `append` | `order(to="city", action="produce", id=1, args={"item": "<item>"})` |', rendered)
        self.assertIn('| unit | tactical | `id` | `detail`, `radius` | `state(what="unit", view="tactical", id=1)` |', rendered)
        self.assertIn("a screen button: pledge, revoke_pledge", rendered)
        self.assertIn('| finish | `turn(action="finish")` |', rendered)
        # every target / action and every object / view of the vocabulary has a row
        for to, actions in V.ACTIONS.items():
            for a in actions:
                self.assertTrue(any(r["to"] == to and r["action"] == a for r in table.order_rows()), (to, a))
        for what, views in V.VIEWS.items():
            for v in views:
                self.assertTrue(any(r["what"] == what and r["view"] == v for r in table.inspect_rows()), (what, v))


class InvariantsTests(unittest.TestCase):
    """Stage 3c (#55): the rules that keep the count at nine, as tests."""

    NINE = ("turn", "state", "order", "question", "answer", "notebook", "batch", "session", "reference")

    def test_the_listing_is_the_nine_and_no_more(self):
        self.assertEqual([t.name for t in m.mcp._tool_manager.list_tools() if t.name != "lua"],
                         ["reference", "turn", "state", "order", "question", "answer", "notebook", "batch", "session"])

    def test_every_description_fits_the_cut_and_explains_every_word(self):
        tools = {t.name: t for t in m.mcp._tool_manager.list_tools()}
        for name in self.NINE:
            self.assertLess(len(tools[name].description or ""), 2000, name)
        for word in V.TURN_ACTIONS:
            self.assertIn(word, tools["turn"].description)
        for what, views in V.VIEWS.items():
            self.assertRegex(tools["state"].description, rf"\b{what}\b")
            for view in views:
                self.assertIn(view, tools["state"].description, (what, view))
        for to, actions in V.ACTIONS.items():
            self.assertRegex(tools["order"].description, rf"\b{to}\b")
            for action in actions:
                if action != V.SCREEN_BUTTON:
                    self.assertIn(action, tools["order"].description, (to, action))
        for word in V.NOTEBOOK_ACTIONS:
            self.assertIn(word, tools["notebook"].description)
        for word in V.SESSION_ACTIONS:
            self.assertIn(word, tools["session"].description)
        for word in V.ANSWER_CHOICES:
            self.assertIn(word, tools["answer"].description)

    def test_the_top_level_table_is_the_registered_schema(self):
        tools = {t.name: t for t in m.mcp._tool_manager.list_tools()}
        fixed = {"turn": {"action"}, "state": {"what", "view"}, "order": {"to", "action"}, "answer": {"choice"},
                 "notebook": {"action"}, "session": {"action"}, "reference": {"book"}, "question": set(), "batch": set()}
        for name in self.NINE:
            props = set(tools[name].parameters.get("properties") or {}) - fixed[name] - {"args", "action_id"}
            self.assertEqual(props, set(V.TOP_LEVEL[name]), name)
            self.assertEqual("args" in (tools[name].parameters.get("properties") or {}), name in V.TAKES_ARGS, name)

    def test_every_gate_row_resolves_to_a_listed_tool_and_a_valid_action(self):
        free = {"turn": 3, "active_player": 0, "my_turn": True, "processing": False, "paused": False, "hotseat": True,
                "blocking_name": "NO_ENDTURN_BLOCKING_TYPE", "todo": {}, "pending_popups": []}
        states = [{**free, "ingame": False}, {**free, "game_over": True}, {**free, "active_player": 1},
                  {**free, "active_player": 1, "active_turn_active": False}, {**free, "hand_off_pending": True},
                  {**free, "processing": True}, {**free, "paused": True}, {**free, "leader_greeting_pending": True},
                  {**free, "discussion_pending": True, "trade_state": 1}, {**free, "discussion_pending": True},
                  {**free, "my_turn": False}, {**free, "tech_popup_pending": True, "todo": {"research_unset": True}},
                  {**free, "city_state_greeting_pending": True},
                  *[{**free, "pending_popups": [{"name": p}]} for p in G.POPUP_RESOLUTIONS]]
        seen = 0
        for ts in states:
            gate = G.compute_gate(ts, 0, may_change_seat=True)
            self.assertIsNotNone(gate, ts)
            for key in ("clear_with", "read_first"):
                if gate.get(key):
                    self.assertRegex(gate[key], r"^(turn|state|order|question|answer|notebook|session|batch|reference)\(", key)
            for row in gate["actions"]:
                self.assertIn(row["tool"], self.NINE, row)
                args = dict(row["args"])
                for name in row.get("choose", []):   # a chosen argument sits where the row's shape puts it
                    top = name in V.TOP_LEVEL[row["tool"]] or name in D.FIXED_FIELDS.get(row["tool"], ())
                    (args if top else args.setdefault("args", {}))[name] = self._value(row, name)
                target = self._resolve(row["tool"], args, gate)
                self.assertIsInstance(target, D.Call, (row, target))
                seen += 1
        self.assertGreater(seen, 40)

    @staticmethod
    def _value(row, name):
        return 1 if name in ("x", "y", "id", "player_id", "button_id", "order_id", "choice") else f"<{name}>"

    @staticmethod
    def _resolve(tool, args, gate):
        """What the server does with the row: its fixed fields out, its `args` flattened, `answer` on the gate."""
        fixed = {k: args.pop(k) for k in D.FIXED_FIELDS.get(tool, ()) if k in args}
        if isinstance(args.get("args"), dict):
            args = {**args.pop("args"), **args}
        if tool == "question":
            return D.Call("generic_popup", {})
        return D.resolve(tool, fixed, args, gate=gate)
