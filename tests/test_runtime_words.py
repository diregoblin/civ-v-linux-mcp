"""Stage 5a of "The tool surface" (GitLab #57): the Lua runtime's strings speak the nine tools, and the bump that
carried the words was text only.

The runtime names tools only inside the strings it hands up (a blocker's hint, a refusal, a `how` row), and
those strings reach the model as they are. `harness.surface.runtime_audit` finds them with the Python audit's
own rule; this file pins that the scan is empty, that the rule tells a vocabulary value (`"declare_war"`, the
city-state screen's button) from a tool, and that the entry table the daemon ships (`entry_names`,
`seat_slots`) is the pinned one -- a text-only bump changes no `H.*` signature. A deliberate signature change
regenerates the pin with the one-liner the failing assertion prints.
"""
import json
import pathlib
import shutil
import tempfile
import unittest

from harness import runtime_source
from harness.surface import runtime_audit as RA

ROOT = pathlib.Path(__file__).resolve().parents[1]
PIN = ROOT / "tests" / "fixtures" / "runtime_entries.json"


def pin_now() -> dict:
    fr = runtime_source.read_fragments()
    return {"entries": sorted(runtime_source.entry_names(fr)),
            "seat_slots": dict(sorted(runtime_source.seat_slots(fr).items()))}


class RuntimeStringsTests(unittest.TestCase):
    def test_string_literals_stop_at_a_comment_and_keep_escapes(self):
        line = """x = "a -- b" .. 'c\\'d' -- "not a string" """
        self.assertEqual(RA.string_literals(line), ["a -- b", "c\\'d"])
        self.assertEqual(RA.string_literals("-- a comment with 'quotes'"), [])

    def test_the_names_are_every_retired_tool_but_reference(self):
        self.assertNotIn("reference", RA.names())
        self.assertIn("move_unit", RA.names())

    def test_a_planted_name_is_found_and_a_value_word_is_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = pathlib.Path(tmp)
            for f in runtime_source.read_fragments():
                shutil.copy(runtime_source.RUNTIME_DIR / f.name, d / f.name)
            p = d / "helpers.lua"
            p.write_text(p.read_text() + '\nlocal planted = "see move_unit first"\n'
                                         'if action == "declare_war" then end  -- the button, a value\n'
                                         'local row = { tool = "units" }  -- a word of a sentence: only a call form counts\n')
            sites = RA.scan(directory=d)
        self.assertEqual([(s.file, s.names, s.text) for s in sites], [("helpers.lua", ("move_unit",), "see move_unit first")])
        self.assertGreater(sites[0].line, 1)
        self.assertEqual(RA.summary(sites), [{"file": "helpers.lua", "strings": 1, "names": "move_unit"}])

    def test_the_runtime_names_no_retired_tool(self):
        sites = RA.scan()
        self.assertEqual([(s.file, s.line, s.names, s.text) for s in sites], [])


class TextOnlyBumpTests(unittest.TestCase):
    """The entry table (`function H.<name>(...)` and the seat slot of each) is pinned: #57's bump moved the words
    and nothing the daemon or the Python side calls."""

    def test_the_entry_table_is_the_pinned_one(self):
        pinned = json.loads(PIN.read_text())
        now = pin_now()
        self.assertEqual(now["seat_slots"], pinned["seat_slots"],
                         "an H.* seat slot moved; if that is the change you meant, regenerate the pin: "
                         "PYTHONPATH=. .venv/bin/python -c 'import json, tests.test_runtime_words as t; "
                         "t.PIN.write_text(json.dumps(t.pin_now(), indent=1) + chr(10))'")
        self.assertEqual(now["entries"], pinned["entries"], "an H.* entry was added, renamed or removed; regenerate the pin as above")
        self.assertEqual(len(pinned["entries"]), 369)   # 331 at the v286 pin; +16 through v312; settle_sites (v313, #106); automation_compare (v314, #77); unimproved_resources (v316, #118); leader_view_up + clear_stale_leader_view (v317, #137); builds.lua's five (v321, #165 / #140); ideologies (v325, #145); great_people.lua's five (v326, #142); attach_league_project, vote_echo, choice_details, member_details (v327, #148); foreign_table (v331, #172); friendship_catalog (v332, #175)

    def test_the_bump_is_the_one_that_carried_the_words(self):
        self.assertGreaterEqual(runtime_source.snapshot().version, 286)


if __name__ == "__main__":
    unittest.main()
