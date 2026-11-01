"""The notebook: per-game notes that outlive a session, keyed so two games never share one."""
import json
import os
import tempfile
import unittest
from unittest import mock

from harness.notes import Notebook, notes_dir, safe_key


class NotebookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"CIV5_NOTES_DIR": self.tmp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_unit_ids_in_a_note_are_stored_with_their_type_and_checked_later(self):
        """GitLab #63 (Assyria t239): note 5 named Great Merchant 1343522; on the reloaded timeline that id was a
        Mongolian Khan. The type is kept with the id and the mismatch named when the note comes back."""
        roster = [{"id": 1343522, "type": "GREAT_MERCHANT", "x": 17, "y": 21}, {"id": 106504, "type": "WORKER"}]
        refs = Notebook.unit_refs("Great Merchant 1343522 ran its trade mission at Belgrade from (17,21); t239", roster)
        self.assertEqual(refs, [{"id": 1343522, "type": "GREAT_MERCHANT"}])
        self.assertEqual(Notebook.unit_refs("gold 1343522.5 and turn 239", roster), [], "a decimal and a short number are not ids")
        nb = Notebook("Pocatello-continents", seat=0)
        nb.remember("Great Merchant 1343522 ran its trade mission", turn=239, tag="log", units=refs)
        nb.remember("no unit named here", turn=239)
        notes = nb.recall()["notes"]
        self.assertEqual(notes[0]["units"], refs)
        self.assertNotIn("units", notes[1])
        Notebook.check_unit_refs(notes, roster)
        self.assertNotIn("unit_check", notes[0], "same unit, nothing to say")
        Notebook.check_unit_refs(notes, [{"id": 1343522, "type": "MONGOLIAN_KHAN"}])
        self.assertEqual(notes[0]["unit_check"], ["unit 1343522: the note says GREAT_MERCHANT, that id is a MONGOLIAN_KHAN now "
                                                   "(ids are reissued after a reload; this is a different unit)"])
        Notebook.check_unit_refs(notes, [])
        self.assertIn("is not among my units now", notes[0]["unit_check"][0])
        self.assertNotIn("unit_check", notes[1])
        r = nb.remember("rewritten without ids", turn=240, replace_id=1)
        self.assertNotIn("units", r["note"], "a rewrite drops the old refs")

    def test_remember_recall_forget_roundtrip(self):
        nb = Notebook("Pocatello-continents", seat=0)
        r = nb.remember("Tradition then Rationalism", turn=12, tag="plan")
        self.assertTrue(r["ok"])
        self.assertEqual(r["note"]["id"], 1)
        nb.remember("Askia denounced me", turn=140, tag="threat")
        got = nb.recall()
        self.assertEqual([n["text"] for n in got["notes"]], ["Tradition then Rationalism", "Askia denounced me"])
        self.assertEqual([n["turn"] for n in got["notes"]], [12, 140])
        self.assertEqual(nb.recall(tag="threat")["count"], 1)
        self.assertTrue(nb.forget(1)["ok"])
        self.assertEqual(nb.recall()["count"], 1)
        bad = nb.forget(99)
        self.assertFalse(bad["ok"])
        self.assertEqual(bad["ids"], [2])

    def test_notes_survive_a_new_notebook_object_and_stay_per_game_and_seat(self):
        Notebook("gameA", 0).remember("a0", turn=1)
        Notebook("gameA", 1).remember("a1", turn=1)
        Notebook("gameB", 0).remember("b0", turn=1)
        self.assertEqual([n["text"] for n in Notebook("gameA", 0).recall()["notes"]], ["a0"])
        self.assertEqual([n["text"] for n in Notebook("gameA", 1).recall()["notes"]], ["a1"])
        self.assertEqual([n["text"] for n in Notebook("gameB", 0).recall()["notes"]], ["b0"])
        files = sorted(os.listdir(self.tmp.name))
        self.assertEqual(files, ["gameA-seat0.json", "gameA-seat1.json", "gameB-seat0.json"])

    def test_replace_keeps_one_living_plan(self):
        nb = Notebook("g", 0)
        first = nb.remember("plan v1", turn=1, tag="plan")["note"]["id"]
        r = nb.remember("plan v2", turn=30, replace_id=first)
        self.assertTrue(r["replaced"])
        notes = nb.recall()["notes"]
        self.assertEqual(len(notes), 1)
        self.assertEqual((notes[0]["text"], notes[0]["turn"], notes[0]["tag"]), ("plan v2", 30, "plan"))
        self.assertFalse(nb.remember("x", turn=1, replace_id=42)["ok"])

    def test_replace_same_or_empty_tag_returns_previous(self):
        nb = Notebook("g", 0)
        first = nb.remember("plan v1", turn=1, tag="plan")["note"]["id"]
        r = nb.remember("plan v2", turn=30, tag="plan", replace_id=first)
        self.assertTrue(r["ok"])
        self.assertEqual(r["previous"], {"id": first, "text": "plan v1", "tag": "plan", "turn": 1})
        self.assertNotIn("retagged", r)
        r = nb.remember("plan v3", turn=31, replace_id=first)
        self.assertEqual(r["previous"], {"id": first, "text": "plan v2", "tag": "plan", "turn": 30})
        note = nb.recall()["notes"][0]
        self.assertEqual((note["text"], note["tag"], note["turn"]), ("plan v3", "plan", 31))

    def test_replace_different_tag_refused_and_file_unchanged(self):
        nb = Notebook("g", 0)
        first = nb.remember("plan v1", turn=1, tag="plan")["note"]["id"]
        before = nb.path.read_bytes()
        r = nb.remember("scout saw ruins at 12,4", turn=5, tag="scout", replace_id=first)
        self.assertFalse(r["ok"])
        self.assertEqual((r["id"], r["stored_tag"], r["tag"]), (first, "plan", "scout"))
        self.assertIn("plan", r["err"])
        self.assertEqual(nb.path.read_bytes(), before)
        self.assertEqual(nb.recall()["notes"][0]["text"], "plan v1")

    def test_replace_retag_changes_tag_and_returns_previous(self):
        nb = Notebook("g", 0)
        first = nb.remember("plan v1", turn=1, tag="plan")["note"]["id"]
        r = nb.remember("done: went Tradition", turn=40, tag="history", replace_id=first, retag=True)
        self.assertTrue(r["ok"])
        self.assertTrue(r["retagged"])
        self.assertEqual(r["previous"], {"id": first, "text": "plan v1", "tag": "plan", "turn": 1})
        note = nb.recall()["notes"][0]
        self.assertEqual((note["text"], note["tag"], note["turn"]), ("done: went Tradition", "history", 40))

    def test_replace_bad_id_writes_nothing_and_lists_ids(self):
        nb = Notebook("g", 0)
        a = nb.remember("a", turn=1, tag="plan")["note"]["id"]
        b = nb.remember("b", turn=2, tag="threat")["note"]["id"]
        before = nb.path.read_bytes()
        r = nb.remember("x", turn=3, tag="plan", replace_id=42, retag=True)
        self.assertFalse(r["ok"])
        self.assertEqual(r["ids"], [a, b])
        self.assertNotIn("previous", r)
        self.assertEqual(nb.path.read_bytes(), before)

    def test_empty_and_oversized_notes_are_refused_and_the_book_is_bounded(self):
        nb = Notebook("g", 0)
        self.assertFalse(nb.remember("   ", turn=1)["ok"])
        self.assertFalse(nb.remember("x" * 5000, turn=1)["ok"])
        for i in range(205):
            nb.remember(f"n{i}", turn=i)
        got = nb.recall(limit=500)
        self.assertEqual(got["count"], 200)
        self.assertEqual(got["notes"][0]["text"], "n5")
        self.assertEqual(nb.latest(3), got["notes"][-3:])

    def test_corrupt_file_is_treated_as_empty(self):
        nb = Notebook("g", 0)
        nb.path.parent.mkdir(parents=True, exist_ok=True)
        nb.path.write_text("{not json")
        self.assertEqual(nb.recall()["count"], 0)
        nb.remember("fresh", turn=3)
        self.assertEqual(json.loads(nb.path.read_text())["notes"][0]["text"], "fresh")

    def test_create_writes_the_first_file_and_never_over_a_living_one(self):
        nb = Notebook("L36-C36-pangaea-s0-g0123456789", 0)
        self.assertFalse(nb.exists())
        nb.create({"next_id": 2, "notes": [{"id": 1, "turn": 93, "text": "the old plan"}]})
        self.assertEqual([n["text"] for n in nb.recall()["notes"]], ["the old plan"])
        nb.create(None)
        self.assertEqual(nb.recall()["count"], 1, "the living file wins")
        empty = Notebook("another", 0)
        empty.create()
        self.assertTrue(empty.exists())
        self.assertEqual(empty.recall()["count"], 0)

    def test_keys_are_filesystem_safe_and_dir_follows_xdg(self):
        self.assertEqual(safe_key("Assets\\Maps/continents.lua game/1"), "Assets_Maps_continents.lua_game_1")
        with mock.patch.dict(os.environ, {"CIV5_NOTES_DIR": "", "XDG_DATA_HOME": "/x/data"}):
            self.assertEqual(str(notes_dir()), "/x/data/civ5-harness/notes")


if __name__ == "__main__":
    unittest.main()


class HandOffTests(unittest.TestCase):
    """#43: a hand-off carries only what was written since the last one; recall() keeps everything."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.dict(os.environ, {"CIV5_NOTES_DIR": self.tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_new_notes_ride_once_then_only_a_count(self):
        nb = Notebook("g", 0)
        nb.remember("Tradition first", turn=1, tag="plan")
        nb.remember("brute NE of Venice", turn=2, tag="threat")
        first = nb.hand_off()
        self.assertEqual([n["text"] for n in first["notes"]], ["Tradition first", "brute NE of Venice"])
        self.assertEqual((first["total"], first["unshown"]), (2, 0))
        again = nb.hand_off()
        self.assertEqual(again["notes"], [], "shown once: not again by default")
        self.assertEqual((again["total"], again["unshown"]), (2, 2))
        nb.remember("Library done", turn=3)
        third = nb.hand_off()
        self.assertEqual([n["text"] for n in third["notes"]], ["Library done"])
        self.assertEqual(third["unshown"], 2)
        self.assertEqual([n["text"] for n in nb.recall()["notes"]],
                         ["Tradition first", "brute NE of Venice", "Library done"], "recall keeps every note")

    def test_a_rewritten_note_is_new_again_and_all_is_the_old_behaviour(self):
        nb = Notebook("g", 0)
        pid = nb.remember("plan v1", turn=1, tag="plan")["note"]["id"]
        nb.remember("scout north", turn=1, tag="todo")
        nb.hand_off()
        nb.remember("plan v2", turn=4, replace_id=pid)
        h = nb.hand_off()
        self.assertEqual([n["text"] for n in h["notes"]], ["plan v2"])
        self.assertEqual(nb.hand_off()["notes"], [])
        every = nb.hand_off("all")
        self.assertEqual([n["text"] for n in every["notes"]], ["plan v2", "scout north"], "the stored order, as latest()")
        self.assertEqual(every["unshown"], 0)
        self.assertEqual(nb.hand_off("all", limit=1)["unshown"], 1)
        with self.assertRaises(ValueError):
            nb.hand_off("some")

    def test_notes_written_before_the_cursor_existed_are_new_once(self):
        nb = Notebook("g", 0)
        nb.path.parent.mkdir(parents=True, exist_ok=True)
        nb.path.write_text(json.dumps({"next_id": 3, "notes": [{"id": 1, "turn": 5, "tag": "", "text": "old a"},
                                                                {"id": 2, "turn": 9, "tag": "", "text": "old b"}]}))
        self.assertEqual([n["text"] for n in nb.hand_off()["notes"]], ["old a", "old b"])
        self.assertEqual(nb.hand_off()["notes"], [])
        r = nb.remember("new c", turn=10)
        self.assertEqual(r["note"]["rev"], 3, "revisions continue above the ids that stood in for them")
        self.assertEqual([n["text"] for n in nb.hand_off()["notes"]], ["new c"])

    def test_section_shape(self):
        nb = Notebook("g", 0)
        self.assertEqual(nb.hand_off_section(), {})
        nb.remember("a", turn=1)
        self.assertEqual([n["text"] for n in nb.hand_off_section()["notes"]], ["a"])
        sec = nb.hand_off_section()
        self.assertNotIn("notes", sec)
        self.assertEqual(sec["notes_unshown"]["count"], 1)
        self.assertIn("notebook(action='recall')", sec["notes_unshown"]["more"])

