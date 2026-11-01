"""Religion rows and replies say what they mean (GitLab #103)."""
import json
import os
import unittest
from unittest import mock


import test_mcp_safety as support
from harness import affordances as A
from harness import mcp_server as m
from harness.game_parts.policies import PoliciesMixin
from tests.test_tool_surface import FakeGame, ThroughTheServerTests


class BeliefRowsLuaTests(unittest.TestCase):
    run_lua = support.LuaRuntimeTests.run_lua

    def setUp(self):
        support.LuaRuntimeTests.setUp(self)
        self.run_lua("""
        Locale = { Lookup = function(k) return ({ TXT_SHORT = 'Religious Idols', TXT_DESC = '+1 Culture and +1 Faith from Gold and Silver' })[k] or k end }
        GameInfo = GameInfo or {}
        GameInfo.Beliefs = { [7] = { ID = 7, Type = 'BELIEF_FORMAL_LITURGY', ShortDescription = 'TXT_SHORT', Description = 'TXT_DESC' } }
        GameInfoTypes = { BELIEF_FORMAL_LITURGY = 7 }
        local getter = H.BELIEF_GETTERS.pantheon
        Game[getter] = function() return { 7 } end
        SENT = nil
        Network = { SendFoundPantheon = function(pid, id) SENT = id end }
        H.belief_available = function() return true end
        Players = { [0] = { CanCreatePantheon = function() return true end } }
        """)

    def test_a_belief_row_carries_its_effect_and_the_pantheon_reply_names_the_belief(self):
        self.run_lua("""
        local r = H.available_beliefs('pantheon', 0)
        assert(r.beliefs[1].belief == 'BELIEF_FORMAL_LITURGY' and r.beliefs[1].name == 'Religious Idols', H.json(r))
        assert(r.beliefs[1].effect:find('+1 Culture', 1, true), H.json(r.beliefs[1]))
        local f = H.found_pantheon('BELIEF_FORMAL_LITURGY', 0)
        assert(f.ok and f.belief == 'BELIEF_FORMAL_LITURGY' and f.name == 'Religious Idols' and f.effect:find('Faith', 1, true), H.json(f))
        assert(SENT == 7)
        """)


class BeliefGame(PoliciesMixin):
    """The Python half of state(what="options", view="beliefs"): the runtime answers H.available_beliefs's shape."""

    def __init__(self, kind):
        self.reply = {"ok": True, "kind": kind, "beliefs": [{"belief": "BELIEF_GOD_KING", "name": "God-King", "effect": "+1"}]}

    def h(self, name, *args, pid=None):
        return name, args

    def q(self, call):
        return json.loads(json.dumps(self.reply))


class BeliefOrderRowsTests(unittest.TestCase):
    """GitLab #178 (Celts t6): the pantheon rows came back with name, belief and effect and no `call`. The runtime
    answers {ok, kind, beliefs: [...]} and the rows were given their calls only when the reply was a list."""

    def test_each_pantheon_belief_carries_its_order(self):
        r = BeliefGame("pantheon").available_beliefs("pantheon")
        self.assertEqual(r["beliefs"][0]["call"], {"tool": "order", "args": {"to": "empire", "action": "pantheon",
                                                                              "args": {"belief": "BELIEF_GOD_KING"}}})
        self.assertNotIn("actions", r)

    def test_a_reformation_belief_carries_its_order(self):
        r = BeliefGame("reformation").available_beliefs("reformation")
        self.assertEqual(r["beliefs"][0]["call"]["args"]["action"], "reformation")

    def test_a_belief_that_is_one_argument_names_the_order_that_takes_it(self):
        """No order takes a founder / follower / enhancer / bonus belief alone: the reply says so and carries the
        religion order with what is left to choose, after the reads of the other kinds it needs."""
        founder = BeliefGame("founder").available_beliefs("founder")
        self.assertNotIn("call", founder["beliefs"][0])
        self.assertIn("no order takes a founder belief alone", founder["call_note"])
        self.assertEqual(founder["actions"], [
            {"tool": "state", "args": {"what": "options", "view": "beliefs", "kind": "follower"}},
            {"tool": "order", "args": {"to": "empire", "action": "religion"}, "choose": ["religion", "beliefs", "city_x", "city_y"]}])
        enhancer = BeliefGame("enhancer").available_beliefs("enhancer")
        self.assertEqual([a["args"].get("action") or a["args"]["kind"] for a in enhancer["actions"]], ["follower", "enhance_religion"])
        follower = BeliefGame("follower").available_beliefs("follower")
        self.assertEqual([a["args"].get("action") or a["args"]["kind"] for a in follower["actions"]],
                         ["founder", "religion", "enhancer", "enhance_religion"])
        bonus = BeliefGame("bonus").available_beliefs("bonus")
        self.assertEqual(bonus["actions"][-1]["args"]["action"], "religion")

    def test_a_refusal_is_returned_untouched(self):
        refused = {"ok": False, "err": "kind is one of pantheon, founder, follower, enhancer, bonus, reformation"}
        self.assertEqual(A.belief_rows(dict(refused), "nonsense"), refused)


class ProphetRefusalLuaTests(unittest.TestCase):
    run_lua = support.LuaRuntimeTests.run_lua

    def setUp(self):
        support.LuaRuntimeTests.setUp(self)
        self.run_lua("""
        IS_CITY, OWNER, HAS, MAJORITY = true, 0, true, 5
        local city = { GetOwner = function() return OWNER end, GetReligiousMajority = function() return MAJORITY end }
        local plot = { IsCity = function() return IS_CITY end, GetPlotCity = function() return city end }
        local unit = { GetPlot = function() return plot end }
        Players = { [0] = { GetUnitByID = function() return unit end, HasCreatedReligion = function() return HAS end,
                            GetReligionCreatedByPlayer = function() return 5 end } }
        Game.GetNumReligionsStillToFound = function() return 2 end
        """)

    def test_each_condition_is_named(self):
        self.run_lua("""
        IS_CITY = false
        assert(H.religion_mission_why(1, 'MISSION_ENHANCE_RELIGION', 0):find('must stand in one of your cities', 1, true))
        IS_CITY = true; OWNER = 3
        assert(H.religion_mission_why(1, 'MISSION_ENHANCE_RELIGION', 0):find('not yours', 1, true))
        OWNER = 0; MAJORITY = 2
        assert(H.religion_mission_why(1, 'MISSION_ENHANCE_RELIGION', 0):find('must follow your religion', 1, true))
        MAJORITY = 5
        assert(H.religion_mission_why(1, 'MISSION_ENHANCE_RELIGION', 0):find('already enhanced', 1, true))
        HAS = false
        assert(H.religion_mission_why(1, 'MISSION_ENHANCE_RELIGION', 0):find('founded no religion', 1, true))
        assert(H.religion_mission_why(1, 'MISSION_FOUND_RELIGION', 0):find('cannot be founded here now', 1, true))
        HAS = true
        assert(H.religion_mission_why(1, 'MISSION_FOUND_RELIGION', 0):find('founded a religion already', 1, true))
        """)


class ReligionQuestionGame(FakeGame):
    def __init__(self):
        super().__init__()
        self.todo_extra = {}

    def turn_state(self, pid=None):
        ts = super().turn_state(pid)
        ts["todo"] = {**ts["todo"], **self.todo_extra}
        return ts

    def cities(self, pid=None):
        return [{"id": 8192, "name": "Palenque", "x": 34, "y": 62}]


class ReligionQuestionTests(ThroughTheServerTests):
    def setUp(self):
        self.fake = ReligionQuestionGame()
        self.patches = [mock.patch.object(m, "game", lambda: self.fake),
                        mock.patch.dict(os.environ, {"CIV5_TUNERD_SOCK": "/tmp/civ5-test-religion.sock", "CIV5_SEAT": "0"}),
                        mock.patch.object(m, "_seat_rechecked", True),
                        mock.patch.dict(m._RECENT, {}, clear=True)]
        for p in self.patches:
            p.start()

    def test_question_shows_the_religion_to_found_with_its_rows_and_beliefs(self):
        """GitLab #103 (Maya t71): after MISSION_FOUND_RELIGION, question() said "nothing is asked"."""
        self.fake.todo_extra = {"religion": "found"}
        out, = self.run_tools([("question", {})])
        r = json.loads(out)
        self.assertEqual((r["pending"], r["decision"], r["choice"], r["gate"]), (True, "religion", "found", None))
        self.assertEqual(r["actions"][0]["tool"], "state")
        self.assertEqual(sorted(r["beliefs"]), ["follower", "founder"])
        self.assertEqual(r["beliefs"]["founder"]["called"], "available_beliefs")

    def test_the_beliefs_under_the_decision_carry_no_second_set_of_rows(self):
        """#178: a founder / follower read now carries the religion order's rows; under question()'s decision those are
        the decision's own `actions`, so the nested reads keep their beliefs alone."""
        self.fake.todo_extra = {"religion": "found"}
        self.fake.available_beliefs = lambda kind, pid=None: BeliefGame(kind).available_beliefs(kind)
        r = json.loads(self.run_tools([("question", {})])[0])
        self.assertEqual(r["actions"][-1]["args"]["action"], "religion")
        for kind in ("founder", "follower"):
            self.assertEqual(sorted(r["beliefs"][kind]), ["beliefs", "kind", "ok"], kind)

    def test_the_religion_order_takes_the_city_id(self):
        out, = self.run_tools([("order", {"to": "empire", "action": "religion",
                                          "args": {"religion": "RELIGION_TAOISM", "beliefs": ["B1", "B2"], "city": 8192}})])
        r = json.loads(out)
        self.assertTrue(r["ok"], r)
        self.assertIn(("found_religion", ("RELIGION_TAOISM", ["B1", "B2"], 34, 62, "")), [(c[0], c[1]) for c in self.fake.calls])
        out, = self.run_tools([("order", {"to": "empire", "action": "religion", "args": {"religion": "RELIGION_TAOISM", "beliefs": ["B1"], "city": 99}})])
        self.assertIn("no city of mine with id 99", json.loads(out)["err"])


# the inherited ThroughTheServerTests cases are not re-run here
for _name in [n for n in dir(ThroughTheServerTests) if n.startswith("test_")]:
    setattr(ReligionQuestionTests, _name, None)
del _name


if __name__ == "__main__":
    unittest.main()
