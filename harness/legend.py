"""The tactical view's legend, said once (GitLab #152).

The legend of `state(what="unit", view="tactical")` is prose that never changes between reads, and a seat read it
on every move check (about two thousand characters a time, four times in a Grok seat's opening turns). It lives in
docs/TOOL_REPLIES.md as the view's reply reference, where `reference(book="playbook", section=...)` serves it. A
server process attaches the whole text to its first tactical reply (`legend`) and a one-line `key` to every reply
after that, with the section's name so a reader who lost the first reply can ask for it again.
"""
from __future__ import annotations

from . import guide

#: The reply reference's heading in docs/TOOL_REPLIES.md, and the section name a reader passes to reference().
TOPIC = 'state(what="unit", view="tactical")'

#: The one-line key: enough to read the grid and the `move` column without the legend (a city is the cell's ground, GitLab
#: #177; an open step's cost, GitLab #180).
KEY = ("cell = ground+occupant: M mountain ~ water H hills F forest . open C city _ unrevealed | @ this unit X hostile "
       "u yours o other ? fogged; move: attack / open (cost, left, zoc) / refused (why) / enemy; "
       f"the legend: reference(book='playbook', section='{TOPIC}')")


def text() -> str:
    """The legend as the reply reference holds it (the heading dropped), or the key when docs/ is not installed."""
    body = guide.reply_topic(TOPIC)
    if not body:
        return KEY
    lines = body.strip().splitlines()
    return "\n".join(lines[1:]).strip() if lines and lines[0].startswith("## ") else body.strip()


def attach(reply: dict, seen: set[str]) -> dict:
    """`legend` the first time a process answers a tactical read, `key` after; `seen` is the process's memory."""
    if TOPIC in seen:
        reply["key"] = KEY
    else:
        seen.add(TOPIC)
        reply["legend"] = text()
    return reply
