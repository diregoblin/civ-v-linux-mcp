"""Every runnable example the playbook serves is a call the server takes (GitLab #171).

`reference(book="playbook", section=...)` serves docs/PLAYBOOK.md and the reply references of docs/TOOL_REPLIES.md
(harness/guide.py). Hotseat Maya t26: the `turn(action="finish")` section still taught `skip_actions` as
`{tool: "unit_mission", args: {unit_id, mission}}` and actions run "exactly as `do` would", names outside the
nine-tool contract that the retired-name scan (tests/test_tool_surface.py) passes over because they sit in
quotes. This test reads every call the two files write -- `tool(key=value, ...)` anywhere in the text and every
`{tool: ..., args: ...}` row -- and holds each to the surface: the tool is one of the nine, its fixed words
(action, what / view, to / action, book) are in the vocabulary, and every argument it names is one the call
it resolves to takes. Placeholders (`id`, `<item>`, `N`, `...`) stand for values and are not checked.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path
from typing import Any

from harness.surface import dispatch as D
from harness.surface import retirement as R
from harness.surface import vocabulary as V
from harness.surface.forward import new_signature
from harness.surface.schemas import properties

ROOT = Path(__file__).resolve().parents[1]
DOCS = ("docs/PLAYBOOK.md", "docs/TOOL_REPLIES.md")


class Placeholder:
    """A value the example leaves for the reader to fill (`id`, `<item>`, `N`, `skip_actions`)."""

    def __init__(self, text: str):
        self.text = text

    def __repr__(self) -> str:
        return f"<{self.text}>"


ELLIPSIS = Placeholder("...")


# --- a small reader for the examples' notation: JSON, JS-style bare keys, `key=value` arguments ---------------
class _Reader:
    STOP = ",)]}"

    def __init__(self, text: str, pos: int):
        self.s, self.i = text, pos

    def _ws(self) -> None:
        while self.i < len(self.s) and self.s[self.i] in " \t\n":
            self.i += 1

    def _peek(self) -> str:
        self._ws()
        return self.s[self.i] if self.i < len(self.s) else ""

    def value(self) -> Any:
        c = self._peek()
        if c == "{":
            return self._items("{", "}")
        if c == "[":
            self.i += 1
            out = []
            while self._peek() not in ("]", ""):
                v = self.value()
                if v is not ELLIPSIS:
                    out.append(v)
                if self._peek() == ",":
                    self.i += 1
            self.i += 1
            return out
        if c in "\"'":
            end = self.s.index(c, self.i + 1)
            text, self.i = self.s[self.i + 1:end], end + 1
            return text
        start = self.i
        depth = 0
        while self.i < len(self.s) and (depth or self.s[self.i] not in self.STOP):
            depth += {"(": 1, ")": -1}.get(self.s[self.i], 0)
            self.i += 1
        token = self.s[start:self.i].strip()
        if re.fullmatch(r"-?\d+", token):
            return int(token)
        if token in ("true", "false", "True", "False"):
            return token in ("true", "True")
        return ELLIPSIS if token in ("...", "…", "") else Placeholder(token)

    def _key(self) -> Any:
        if self._peek() in "\"'":
            return self.value()
        m = re.compile(r"[^\s,=:(){}\[\]]*").match(self.s, self.i)
        self.i = m.end()
        return Placeholder(m.group(0))

    def _items(self, open_: str, close: str) -> dict:
        """`{k: v, bare, ...}` or the arguments of a call `(k=v, bare)`."""
        assert self.s[self.i] == open_
        self.i += 1
        out: dict = {}
        while self._peek() not in (close, ""):
            key = self._key()
            if self._peek() in (":", "=") and isinstance(key, (str, Placeholder)):
                self.i += 1
                out[key.text if isinstance(key, Placeholder) else key] = self.value()
            elif isinstance(key, Placeholder) and re.fullmatch(r"\w+", key.text):
                out[key.text] = Placeholder(key.text)       # `{unit_id, mission}`, `answer(choice)`
            self._skip_prose(close)
            if self._peek() == ",":
                self.i += 1
        self.i += 1
        return out

    def _skip_prose(self, close: str) -> None:
        """Words between an item and the next comma (`"UNIT_SCOUT" or "UNIT_WARRIOR"`): not part of the call."""
        while self._peek() not in (",", close, ""):
            if self._peek() in "\"'{[(":
                self.value() if self._peek() != "(" else self._items("(", ")")
            else:
                self.i += 1

    def call_args(self) -> dict:
        return self._items("(", ")")


#: A call written as `name(...)`: the nine, the retired names (an old tool written as a call) and `do`, the batch's
#: name before 2.0.0. Other code in the prose (`Game.GetDealDuration`, `UI.RequestLeaveLeader()`) is dotted.
TOOLISH = set(V.TOOLS) | set(R.RETIRED)
CALL = re.compile(r"(?<![\w.$])([a-z_][a-z0-9_]*)\(")
ROW = re.compile(r"""\{\s*"?tool"?\s*:""")


def _line(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def examples(text: str) -> list[tuple[int, str, dict]]:
    """(line, tool, arguments) of every call and every `{tool, args}` row the text writes."""
    out = []
    for m in CALL.finditer(text):
        if m.group(1) in TOOLISH:
            out.append((_line(text, m.start()), m.group(1), _Reader(text, m.end() - 1).call_args()))
    for m in ROW.finditer(text):
        row = _Reader(text, m.start()).value()
        if isinstance(row.get("tool"), str):
            args = row.get("args") if isinstance(row.get("args"), dict) else {}
            out.append((_line(text, m.start()), row["tool"], dict(args)))
    return out


# --- what the surface takes --------------------------------------------------------------------------------
#: The fixed words checked against the vocabulary here; state's what / view and order's to / action are checked
#: by the call they resolve to.
FIXED_WORDS = {"turn": {"action": V.TURN_ACTIONS}, "notebook": {"action": V.NOTEBOOK_ACTIONS},
               "session": {"action": V.SESSION_ACTIONS}, "reference": {"book": V.BOOKS}}
#: The tools with no fixed words and no `args`: their own arguments are the whole call.
FLAT = {"batch": {"actions", "stop_on_refusal", "force", "action_id"}, "question": set()}


def _words(tool: str, fixed: dict) -> dict | None:
    """The fixed words that name one call (`what` / `view` with its default), or None when the example leaves one
    to the reader (`action=<...>`, `state(what=...)` alone)."""
    need = {"state": ("what",), "order": ("to", "action"), "turn": ("action",), "notebook": ("action",),
            "session": ("action",), "reference": ()}.get(tool)
    if need is None or not all(isinstance(fixed.get(k), str) for k in need):
        return None
    if tool == "state":
        return {"what": fixed["what"], "view": fixed.get("view") or V.DEFAULT_VIEW.get(fixed["what"]) or V.DEFAULT}
    if tool == "reference":
        return {"book": fixed.get("book") if isinstance(fixed.get("book"), str) else "rules"}
    return fixed


def problems(tool: str, args: dict) -> list[str]:
    """Why a call written in the docs would not be taken as written; [] when it would."""
    if tool not in V.TOOLS:
        hint = f" (retired: {R.RETIRED[tool].render()})" if tool in R.RETIRED else ""
        return [f"{tool} is not one of the nine tools{hint}"]
    if tool in FLAT:
        extra = sorted(set(args) - FLAT[tool])
        return [f"{tool} does not take {extra}"] if extra else []
    fixed_names = D.FIXED_FIELDS[tool]
    allowed = set(fixed_names) | set(V.TOP_LEVEL[tool]) | {"action_id"} | ({"args"} if tool in V.TAKES_ARGS else set())
    out = [f"{tool} does not take {k!r} at the top level" for k in args if k not in allowed]
    fixed = {k: args[k] for k in fixed_names if k in args}
    for k, words in FIXED_WORDS.get(tool, {}).items():
        if isinstance(fixed.get(k), str) and fixed[k] not in words:
            out.append(f"{tool} {k}={fixed[k]!r} is not one of {list(words)}")
    words = _words(tool, fixed)
    if words is None or out:
        return out
    if tool == "order" and words["to"] == "city_state" and words["action"] not in V.ACTIONS["city_state"]:
        return out          # one of the city-state screen's own buttons
    rest = {k: v for k, v in args.items() if k not in fixed_names and k not in ("args", "action_id")}
    if isinstance(args.get("args"), dict):
        rest.update(args["args"])
    names = D.INDEX.get(R.Row(tool, words).key)
    if not names:
        return [f"{tool} {words} names no call"]
    if not any(set(D.old_args(n, rest)) <= properties(n) for n in names):
        out.append(f"{tool} {words} does not take {sorted(rest)} "
                   f"(it takes {'; '.join(sorted(new_signature(n) for n in names))})")
    return out


class PlaybookExamplesTests(unittest.TestCase):
    def test_every_example_is_a_call_the_server_takes(self):
        bad, seen = [], 0
        for doc in DOCS:
            for line, tool, args in examples((ROOT / doc).read_text()):
                seen += 1
                bad += [f"{doc}:{line}: {p}" for p in problems(tool, args)]
        self.assertEqual(bad, [])
        self.assertGreater(seen, 150, "the reader finds the examples")

    def test_the_batch_is_called_batch(self):
        """`do` was the batch's name before 2.0.0; the turn(action="finish") section still said "exactly as `do`
        would" (#171). The name is a word too, so only its backticked and call forms count."""
        for doc in DOCS:
            text = (ROOT / doc).read_text()
            self.assertEqual([_line(text, m.start()) for m in re.finditer(r"`do`|`do\(|(?<![\w.])do\(", text)], [], doc)

    def test_the_reader_finds_the_stale_forms(self):
        """What hotseat Maya t26 read (#171) and the shapes the playbook had wrong, each named."""
        def found(text):
            return [(tool, problems(tool, args)) for _, tool, args in examples(text)]
        self.assertEqual(found('`{tool: "unit_mission", args: {unit_id, mission: "MISSION_SKIP"}}`'),
                         [("unit_mission", ['unit_mission is not one of the nine tools (retired: '
                                            'order(to="unit", action="mission"))'])])
        self.assertEqual(found('`turn(action="finish", briefing=true)`')[0][1],
                         ["turn does not take 'briefing' at the top level"])
        self.assertEqual(found('turn(action="finish_turn")')[0][1][0][:30], "turn action='finish_turn' is n")
        refused = found('order(to="empire", action="pantheon", args={"religion": "x"})')[0][1]
        self.assertTrue(refused and "does not take ['religion']" in refused[0], refused)
        self.assertEqual(found('`{"tool": "set_production", "args": {"city_id": 7}, "choose": ["item"]}`')[0][0], "set_production")
        for good in ('`{tool: "order", args: {to: "unit", action: "mission", id: N, args: {mission: "MISSION_SKIP"}}}`',
                     'state(what="options", view="beliefs", kind="pantheon")',
                     'turn(action="finish", args={"skip_quiet_turns": N})',
                     'order(to="city", id=city, action="produce", args={"item": "UNIT_SCOUT" or "UNIT_WARRIOR"})',
                     'answer(choice=<button>)', 'question()', 'batch(actions=[...])'):
            self.assertEqual([p for _, p in found(good)], [[]] * len(found(good)), good)
            self.assertTrue(found(good), good)


if __name__ == "__main__":
    unittest.main()
