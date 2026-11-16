"""Previous result: the one prior a trade's state is read from (TICKET-919).

The most recent trade that day exited before this one's entry, resolved the way b2_condition
resolves its priors: exited strictly before the entry, so a trade still open never counts
however it ends, and nothing carries across the day boundary. B2's own definition is
pre-registered and is not touched; this reads one prior where B2 reads two. Which trades go in
together (every book, or one) is the caller's: until TICKET-918 rules, the Mirror passes every
book. Plain Python: production may not import research (methodology Rule 5).
"""

from __future__ import annotations

from collections.abc import Sequence

from services.shared.conditions.b2_condition import Obs


def previous_of(obs: Sequence[Obs]) -> list[int | None]:
    """For each trade, in the order given, the index of the last trade that day exited before
    its entry, or None when nothing had."""
    out: list[int | None] = [None] * len(obs)
    by_day: dict[int, list[int]] = {}
    for i, o in enumerate(obs):
        by_day.setdefault(o.day, []).append(i)
    for members in by_day.values():
        for i in members:
            priors = [j for j in members if j != i and obs[j].exit_at < obs[i].entry_at]
            if priors:
                out[i] = max(priors, key=lambda j: (obs[j].exit_at, j))
    return out
