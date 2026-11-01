"""game_key follows the seat and the loaded game.

Live t173 (2026-10-02, Venice/Mongolia hotseat): the session server started on seat 1 (Mongolia) and was moved
to seat 0 with set_seat. `game_key` was cached once per process from the first seat's leader and capital, so
Venice's `recall` answered an empty notebook under `L19-C20-...-Karakorum-t1-s0-seat0` while her 35 notes sat
under `L38-C43-...-Venice-t0-s0-seat0`. The key is now cached per seat and dropped when a game is loaded.
Since GitLab #168 the key ends in the game's identity (harness/notebook_identity.py) instead of the capital.
"""
import os
import tempfile
import unittest
from unittest import mock

from harness.game import Game
from harness.notebook_identity import game_keys


class SeatKeyedGame(Game):
    """q() answers the game_key read with the seat's own leader and capital and counts the reads."""

    def __init__(self, seat=1):
        self.seat = seat
        self.reads = []

    def q(self, code, *a, **k):
        seat = int(code.split("H.game_key_facts(", 1)[1].split(")", 1)[0])
        self.reads.append(seat)
        caps = {0: ("38", "43", "Venice", 0, "12,30"), 1: ("19", "20", "Karakorum", 1, "40,8")}
        leader, civ, cap, founded, start_plot = caps[seat]
        return {"leader": leader, "civ": civ, "map": "Assets_Maps_continents", "cap": cap, "founded": founded,
                "name": "", "start": 0, "turn": 90, "identity": f"{start_plot}|0:43,1:20|22:5"}


class GameKeyFollowsTheSeat(unittest.TestCase):
    def test_the_key_is_built_from_the_current_seat(self):
        g = SeatKeyedGame(seat=1)
        mongolia = g.game_key()
        self.assertRegex(mongolia, r"^L19-C20-Assets_Maps_continents-s0-g[0-9a-f]{10}$")
        g.seat = 0   # what set_seat does
        venice = g.game_key()
        self.assertRegex(venice, r"^L38-C43-Assets_Maps_continents-s0-g[0-9a-f]{10}$")
        self.assertNotEqual(venice.rsplit("-", 1)[1], mongolia.rsplit("-", 1)[1], "each seat starts on its own plot")
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"CIV5_NOTES_DIR": tmp}):
            self.assertEqual(g.notebook().key, venice + "-seat0")

    def test_each_seat_is_read_once(self):
        g = SeatKeyedGame(seat=1)
        g.game_key(); g.game_key()
        g.seat = 0
        g.game_key(); g.game_key()
        g.seat = 1
        g.game_key()
        self.assertEqual(g.reads, [1, 0], "one read per seat, then the cache")

    def test_a_loaded_game_rebuilds_the_key(self):
        g = SeatKeyedGame(seat=1)
        g.game_key()
        g._game_keys = {}   # what wait_ingame does after a load (and the exit to the main menu)
        g.game_key()
        self.assertEqual(g.reads, [1, 1])

    def test_the_legacy_keys_are_the_capitals_label_in_both_map_forms(self):
        """The key a notebook had before #168 is the capital's label; before runtime v285 its map part was
        `Assets_Maps_<script>` (the inline snippet's pattern lost its backslash). Both come from the same facts."""
        facts = {"leader": "36", "civ": "36", "map": "pangaea", "cap": "Assur", "founded": 0, "name": "", "start": 0,
                 "identity": "20,14|0:36|"}
        keys = game_keys(facts)
        self.assertEqual(keys["legacy"], ["L36-C36-pangaea-Assur-t0-s0", "L36-C36-Assets_Maps_pangaea-Assur-t0-s0"])
        self.assertEqual(game_keys({**facts, "map": "Assets_Maps_pangaea"})["legacy"],
                         ["L36-C36-Assets_Maps_pangaea-Assur-t0-s0"], "already the old form")
        self.assertEqual(game_keys({**facts, "map": ""})["legacy"], ["L36-C36-Assur-t0-s0"])

    def test_a_random_map_game_names_no_script(self):
        """GitLab #119: a game set up with map type Random hides the script from its players; the key said it."""
        facts = {"leader": "36", "civ": "36", "map": "random", "cap": "Sukhothai", "founded": 0, "name": "", "start": 0,
                 "identity": "20,14|0:36|"}
        keys = game_keys(facts)
        self.assertTrue(keys["key"].startswith("L36-C36-random-s0-g"))
        self.assertEqual(keys["legacy"], ["L36-C36-random-Sukhothai-t0-s0"])
        self.assertEqual(keys["pattern"], "L36-C36-*-Sukhothai-t0-s0")
        self.assertNotIn("pattern", game_keys({**facts, "map": "pangaea"}))

    def test_the_key_does_not_change_at_the_founding(self):
        """GitLab #159 (Codex seat 0, t0): the plan remembered before the Settler founded Palenque sat under the
        key with no capital; the key gained `Palenque-t0` a call later and the recovered server read an empty
        notebook. The identity is the seat's starting plot, which the founding does not move (#168)."""
        facts = {"leader": "31", "civ": "33", "map": "continents", "cap": "", "founded": -1, "name": "", "start": 0,
                 "identity": "26,20|0:33,1:5,2:12|"}
        before, after = game_keys(facts), game_keys({**facts, "cap": "Palenque", "founded": 0})
        self.assertEqual(before["key"], after["key"])
        self.assertEqual(before["legacy"], [], "a label key with no capital is every such game's: never adopted")
        self.assertEqual(after["legacy"][0], "L31-C33-continents-Palenque-t0-s0")

    def test_a_read_without_the_identity_is_not_cached(self):
        class NoIdentity(SeatKeyedGame):
            def q(self, code, *a, **k):
                return {**super().q(code), "identity": ""}
        g = NoIdentity(seat=0)
        self.assertFalse(game_keys({"leader": "1", "civ": "1", "identity": ""})["identified"])
        g.game_key(); g.game_key()
        self.assertEqual(g.reads, [0, 0], "read again until the runtime names the identity")

    def test_a_fixed_key_wins(self):
        g = SeatKeyedGame(seat=1)
        g._game_key = "test-game"
        self.assertEqual(g.game_key(), "test-game")
        self.assertEqual(g.reads, [])


if __name__ == "__main__":
    unittest.main()
