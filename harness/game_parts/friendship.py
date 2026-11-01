"""Declarations of Friendship: asked of an AI on its leader screen, put to a human seat on the trade table."""
from __future__ import annotations

import time

from ..client import TunerdError


class FriendshipMixin:
    """Declarations of Friendship, asked and accepted.

    An AI leader is asked on the Discuss screen and answers there and then; a human seat has no leader screen, so
    the stock game puts the declaration on the PvP trade table (tradelogic.lua's DoF pocket, both sides in one press)
    and that seat answers it on its own turn (GitLab #175).

    A part of harness.game.Game (see harness/game_parts/__init__.py); `self` is the whole Game."""

    def propose_friendship(self, other_player: int, pid: int | None = None) -> dict:
        """Ask a civ for a Declaration of Friendship. An AI: the leader screen's Discuss -> "work together" button
        (discussiondialog.lua OnButton6 in DISCUSS_HUMAN_INVOKED root mode), with its own guards -- not already
        friends, not IsDoFMessageTooSoon -- plus met / not at war / major civ. The AI answers through its
        leader message; the reply reports IsDoF after a short settle (live t345: DoFs with America and Sweden
        expired after their term and there was no way to renew them). A human seat: the declaration is proposed
        as a deal (`pvp`, `pending`, `pending_to`) for that seat to answer(choice="accept" / "refuse")."""
        me = self._pid(pid)
        pre = self.q(self.h("friendship_check", int(other_player), pid=me))
        if not pre.get("ok"):
            return pre
        if pre.get("human"):
            return self._propose_friendship_deal(int(other_player), me)
        # The AI's answer is a reply to OUR ask: flag it harness_initiated so turn_digest does not present it as
        # the AI approaching us (live t346 digest showed "I am happy to accept" / "Sorry, but no" as approaches).
        self._harness_diplo(True)
        try:
            r = self.diplo_event("HUMAN_DISCUSSION_WORK_WITH_US", other_player, 0, 0)
            if not r.get("ok"):
                return r
            time.sleep(0.5)
            return self._friendship_result(other_player, me, pid)
        finally:
            self._harness_diplo(False)

    def _propose_friendship_deal(self, other_player: int, me: int) -> dict:
        """The human seat's way (GitLab #175, three-seat hotseat t6: the leader-screen ask to Indonesia came back
        as Indonesia's dormant AI saying "premature", immediately): the DoF pocket on the PvP table, proposed."""
        r = self.propose_deal(other_player, [{"type": "DECLARATION_OF_FRIENDSHIP"}], pid=me)
        if r.get("ok") and r.get("pvp"):
            r["friendship"] = True
            r["note"] = ("a Declaration of Friendship sent to a human seat as a deal: they see it in question() on their "
                         "turn and answer(choice='accept' / 'refuse'); nothing is decided until then")
        return r

    def _friendship_result(self, other_player: int, me: int, pid: int | None) -> dict:
        post = self.q(self.h("dof_with", int(other_player), pid=me))
        out = {"ok": True, "accepted": bool(post.get("dof"))}
        # The answer is spoken on a leader screen that then drops back to the Discuss menu (our own asks, not
        # a question for us -- live t345 America); close it or every later action reads "decision pending".
        # It takes a beat to come up (live t182, Mongolia: Babylon's "That will work" screen was not there
        # 0.5 s after the ask, so nothing was closed, `reply` was the t171 line and the next finish_turn was
        # refused with a discussion gate): wait for it the way dismiss_discussion waits for a queued leader.
        screen = False
        for _ in range(self._NEXT_LEADER_POLLS):
            if self.discussion_pending():
                screen = True
                break
            time.sleep(0.2)
        try:
            hist = self.relationship(other_player, pid).get("history") or []
            if hist:
                out["reply"] = hist[-1].get("text")
        except TunerdError:
            pass
        if screen:
            out["screen_closed"] = bool(self.dismiss_discussion().get("ok"))
        return out

    def accept_friendship(self, other_player: int) -> dict:
        """Accept a pending `DISCUSS_WORK_WITH_US` Declaration of Friendship proposal (the discussion
        state used for every AI "let's be friends" offer seen live so far). Works whether or not the
        DiscussionDialog is still open -- `discussiondialog.lua`'s own OnButton1 for this state does
        nothing but this same call (`Game.DoFromUIDiploEvent(FROM_UI_DIPLO_EVENT_WORK_WITH_US_RESPONSE,
        player, 1, 0)`; button 2 is decline, same event), so it works standalone too, and live-tested
        working even *after* the dialog had already been declined/closed (2026-09-16, turns 258 and 263 --
        the second time on a dialog that was still fresh, not previously declined, closing out the
        one-off caveat from the first test). Confirm real effect with `Players[pid]:IsDoF(other_player)`
        via `q()` if in doubt -- like every other unguarded `diplo_event`, {ok:true} only means the engine
        call didn't error, not that the AI's own preconditions were met. A human seat's declaration is a deal
        (answer(choice="accept")); H.diplo_event refuses this event for one."""
        return self.diplo_event("WORK_WITH_US_RESPONSE", other_player, 1, 0)
