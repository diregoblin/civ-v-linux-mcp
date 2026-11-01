"""A notebook belongs to one game and seat (GitLab #168).

Fresh three-seat hotseat, seat 0 Maya, 2026-10-30: the key was leader, civ, map, capital and founding turn, so
the new game that founded Palenque on turn 0 opened the previous Maya game's notebook -- its notes, a Tikal
garrison assignment on Warrior 16385 (the same id, type and creation turn in both games), a briefing baseline
from turn 31, and a standing order on Worker 40960 that ran on turn 1. The key now ends in the game's identity
(the seat's starting plot and the slots' civilizations); a notebook from before the change is adopted only by a
game under way, quarantined.
"""
import json
import os
import tempfile
import unittest
from unittest import mock

from harness import assignments as A
from harness.game import Game
from harness.notebook_identity import foreign, game_keys
from harness.notes import Notebook, notes_dir

LABEL = "L31-C33-continents-Palenque-t0-s0"   # the key both Maya games had before #168


class MayaGame(Game):
    """A Maya/Palenque hotseat on continents: the seats differ only by their starting plots, two games only by
    theirs (identical unit ids, capital and founding turn). q() answers the key read and counts it."""

    def __init__(self, seat=0, starts=("26,20", "40,8", "12,30"), turn=0):
        self.seat = seat
        self.starts = starts
        self.turn = turn
        self.reads = 0

    def q(self, code, *a, **k):
        seat = int(code.split("H.game_key_facts(", 1)[1].split(")", 1)[0])
        self.reads += 1
        return {"leader": "31", "civ": "33", "map": "continents", "cap": "Palenque", "founded": 0, "name": "",
                "start": 0, "turn": self.turn, "identity": f"{self.starts[seat]}|0:33,1:5,2:12|22:4,23:9"}


def order_record():
    return {"unit": {"id": 40960, "type": "UNIT_WORKER", "created": 30}, "purpose": "quarry",
            "steps": [{"kind": "build", "build": "QUARRY", "x": 18, "y": 12}]}


def assignment_record():
    return {"role": "garrison", "purpose": "hold Tikal", "units": [{"id": 16385, "type": "UNIT_WARRIOR", "created": 0}],
            "cities": [], "target": None, "done_when": {"kind": "manual"}, "review": {}}


def write_everything(nb: Notebook, turn: int) -> None:
    """What a seat leaves in its notebook over a game: a note, an assignment, a standing order, a briefing
    baseline and the server's memo."""
    nb.remember("Recovery: Seat 0 Maya founded Palenque (24,11) t0", turn=turn, tag="plan")
    nb.add_assignment(assignment_record(), turn)
    nb.add_order(order_record(), turn)
    nb.set_briefing_baseline({"turn": turn, "event_seq": 5})
    nb.set_memo("woken", [1, 2])


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"CIV5_NOTES_DIR": self.tmp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def assertEmptyNotebook(self, nb: Notebook):
        self.assertEqual(nb.recall()["count"], 0)
        self.assertEqual(nb.assignments("all"), [])
        self.assertEqual(nb.orders("all"), [])
        self.assertIsNone(nb.briefing_baseline())
        self.assertIsNone(nb.memo("woken"))

    def test_two_games_set_up_alike_never_share_a_notebook(self):
        """The acceptance check of #168: two Maya/Palenque games with identical unit ids and founding turn;
        neither sees the other's notes, assignments, standing orders or briefing baseline, on any of three seats."""
        first = MayaGame(turn=38)
        for seat in (0, 1, 2):
            first.seat = seat
            write_everything(first.notebook(), 38)
        second = MayaGame(starts=("24,11", "33,17", "9,4"), turn=0)
        for seat in (0, 1, 2):
            second.seat = seat
            nb = second.notebook()
            self.assertEmptyNotebook(nb)
            nb.remember(f"seat {seat}'s own plan", turn=0)
        for seat in (0, 1, 2):
            first.seat = second.seat = seat
            self.assertEqual(len(first.notebook().recall()["notes"]), 1)
            self.assertEqual([n["text"] for n in second.notebook().recall()["notes"]], [f"seat {seat}'s own plan"])
        self.assertEqual(len(os.listdir(self.tmp.name)), 6, "one file per game and seat")

    def test_the_seats_of_one_game_are_apart(self):
        g = MayaGame(turn=3)
        write_everything(g.notebook(), 3)
        for seat in (1, 2):
            g.seat = seat
            self.assertEmptyNotebook(g.notebook())

    def test_a_reload_of_the_same_game_keeps_its_notebook(self):
        """A new server process on the same game (the key cache is empty), and a save loaded back to an earlier
        turn: the same notebook, with the later timeline's notes marked as before (#62)."""
        g = MayaGame(turn=38)
        write_everything(g.notebook(), 38)
        again = MayaGame(turn=20)
        nb = again.notebook()
        self.assertEqual(nb.key, g.notebook().key)
        self.assertEqual(len(nb.orders("open")), 1)
        self.assertEqual(nb.memo("woken"), [1, 2])
        self.assertTrue(nb.recall(turn=20)["notes"][0]["later_timeline"])
        self.assertNotIn("adopted", nb.recall(turn=20))

    def test_a_fresh_game_never_adopts_the_label_keyed_notebook(self):
        """The defect itself: the previous Maya game's notebook sits under the label key; the new game opens its
        own on turn 0 and the old file stays where it is. The decision is made once: a later process of the new
        game (turn 39, past its start) still has only its own notebook."""
        old = Notebook(LABEL, 0)
        write_everything(old, 38)
        g = MayaGame(turn=0)
        nb = g.notebook()
        self.assertEmptyNotebook(nb)
        self.assertTrue(old.exists(), "another game's notebook is left as it is")
        later = MayaGame(turn=39)
        self.assertEmptyNotebook(later.notebook())
        self.assertTrue(old.exists())

    def test_a_label_keyed_notebook_past_the_turn_on_screen_is_adopted_as_a_later_timeline(self):
        """A game under way whose save was loaded back (#62, live Assyria: notes to t278 at t239) keeps its
        notebook through the upgrade: adopted, and the later notes marked later_timeline as before."""
        write_everything(Notebook(LABEL, 0), 38)
        nb = MayaGame(turn=20).notebook()
        (note,) = nb.recall(turn=20)["notes"]
        self.assertTrue(note["adopted"] and note["later_timeline"])
        self.assertEqual(nb.orders("open")[0]["status"], "paused")
        self.assertIsNone(foreign(20, 0))
        self.assertIn("start turn 0", foreign(0, 0))

    def test_a_game_under_way_adopts_its_label_keyed_notebook_quarantined(self):
        """The upgrade of a game in progress: the seat's notebook from before #168 is taken over once and the old
        file goes. Nothing in it is trusted: notes and assignments are marked adopted, the standing order is
        paused, the briefing baseline and the memo are dropped."""
        old = Notebook(LABEL, 0)
        write_everything(old, 40)
        g = MayaGame(turn=45)
        nb = g.notebook()
        self.assertFalse(old.exists())
        self.assertEqual(json.loads(nb.path.read_text())["adopted"], {"from": f"{LABEL}-seat0", "turn": 45})
        notes = nb.recall()
        self.assertTrue(notes["notes"][0]["adopted"])
        self.assertIn("adopted", notes)
        self.assertIn("notes_adopted", nb.hand_off_section("all", 8, turn=45))
        (o,) = nb.orders("open")
        self.assertEqual((o["status"], o["pause"]["kind"]), ("paused", "adopted"), "an adopted order never runs by itself")
        self.assertEqual(nb.orders("active"), [])
        (a,) = nb.assignments("active")
        row, _ = A.reconcile(a, {"units": {"16385": {"type": "UNIT_WARRIOR", "created": 0, "x": 26, "y": 20}}}, 45, 0)
        self.assertEqual(row["state"], "needs_review")
        self.assertTrue(any("adopted" in r for r in row["reasons"]))
        self.assertIsNone(nb.briefing_baseline())
        self.assertIsNone(nb.memo("woken"))

    def test_the_seats_word_lifts_the_adopted_mark(self):
        write_everything(Notebook(LABEL, 0), 40)
        nb = MayaGame(turn=45).notebook()
        nb.remember("the plan, checked against the board", turn=45, replace_id=1)
        self.assertNotIn("adopted", nb.recall()["notes"][0])
        self.assertNotIn("adopted", nb.recall())
        nb.update_assignment(1, {}, 45, "note: still Tikal's garrison")
        self.assertNotIn("adopted", nb.assignments("active")[0])

    def test_the_older_label_forms_are_adopted_too(self):
        """The pre-v285 map form (`Assets_Maps_continents`) and a Random-map game's script key (#119) are the
        same game's label keys; a Random-map pattern never takes another leader's file."""
        Notebook("L31-C33-Assets_Maps_continents-Palenque-t0-s0", 0).remember("pre-v285 plan", turn=40)
        self.assertTrue(MayaGame(turn=45).notebook().recall()["notes"][0]["adopted"])

        class RandomMaya(MayaGame):
            def q(self, code, *a, **k):
                return {**super().q(code), "map": "random"}
        Notebook("L31-C33-Fractal-Palenque-t0-s0", 1).remember("the script's key", turn=40)
        Notebook("L19-C20-Fractal-Karakorum-t1-s0", 1).remember("another game", turn=40)
        g = RandomMaya(seat=1, turn=45)
        self.assertEqual([n["text"] for n in g.notebook().recall()["notes"]], ["the script's key"])
        self.assertTrue((notes_dir() / "L19-C20-Fractal-Karakorum-t1-s0-seat1.json").exists())

    def test_the_first_look_reads_the_turn_once(self):
        g = MayaGame(turn=5)
        g.notebook(); g.notebook(); g.notebook()
        self.assertEqual(g.reads, 2, "the key once, the turn at the first look; the file decides after that")

    def test_no_identity_no_adoption(self):
        write_everything(Notebook(LABEL, 0), 40)
        self.assertFalse(game_keys({"cap": "Palenque", "identity": ""})["identified"])

        class Unidentified(MayaGame):
            def q(self, code, *a, **k):
                return {**super().q(code), "identity": ""}
        self.assertEqual(Unidentified(turn=45).notebook().recall()["count"], 0)
        self.assertTrue(Notebook(LABEL, 0).exists())


class IdentityFactsInLua(unittest.TestCase):
    """H.game_key_facts in the shipped runtime: the identity string from stubbed players."""

    def setUp(self):
        from harness import runtime_source
        from test_query_chunking import LuaClient
        from test_runtime_source import FAKE_GAME, lua_5_1
        self.lua = lua_5_1()
        if self.lua is None:
            self.skipTest("this lupa build has no Lua 5.1 / LuaJIT runtime")
        self.lua.execute(FAKE_GAME)
        src = runtime_source.snapshot()
        self.lua.globals()["__H_SRC"] = src.text
        self.lua.execute(src.install_lua("__H_SRC"))
        self.g = Game.__new__(Game)
        self.g.c = LuaClient(self.lua)
        self.g.seat = 0
        self.g.ensure_runtime = lambda: None

    def facts(self, start_x):
        self.lua.execute(f"""
        GameDefines = {{MAX_CIV_PLAYERS = 63}}
        Game.GetStartTurn = function() return 0 end
        local function player(civ, minor, x, alive)
          return {{GetStartingPlot = function() return x and {{GetX = function() return x end, GetY = function() return 20 end}} end,
                  IsEverAlive = function() return alive end, IsMinorCiv = function() return minor end,
                  GetCivilizationType = function() return civ end, GetMinorCivType = function() return civ + 100 end,
                  GetCapitalCity = function() return nil end, GetLeaderType = function() return 31 end}}
        end
        Players = {{[0] = player(33, false, {start_x}, true), [1] = player(5, false, 40, true),
                   [2] = player(-1, false, nil, false), [22] = player(4, true, 30, true)}}
        """)
        return self.g.q(self.g.h("game_key_facts"))

    def test_the_identity_is_the_seats_start_and_the_slots(self):
        f = self.facts(26)
        self.assertEqual(f["identity"], "26,20|0:33,1:5|22:104")
        self.assertEqual(f["turn"], 12)
        self.assertEqual(self.facts(26)["identity"], f["identity"], "the same game reads the same identity")
        self.assertNotEqual(self.facts(24)["identity"], f["identity"], "another start is another game")
        self.assertTrue(game_keys({"identity": f["identity"]})["identified"])


if __name__ == "__main__":
    unittest.main()
