"""R2's condition: "the next trade after a loss", defined once (TICKET-996).

Written the way ``b2_condition`` is, beside it, so the Mirror and the research library count
one rule (methodology Rule 5 keeps it out of research). Where B2 needs two earlier trades this
needs one:

* **In the population:** a round trip with at least one other trip the **same trading day**
  that **closed strictly before this one opened**. An overlapping trip, still open at this
  entry, never counts, however it later ends. Nothing carries across the day.
* **After a loss / after a win:** the most recent of those earlier trips, by exit time, lost
  or made money. ``Obs.r`` is read for its **sign** only, as B2 reads it.
* **A scratch** (exactly zero) puts the trip in neither group; it is still in the population,
  and counted.

Annex A's R2 reads "prior trip was a loss" against "won or flat". This product fact keeps the
flat one out of both groups, as the ticket's gate says, and counts it on the page.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from services.shared.conditions.b2_condition import Obs


def last_resolved(obs: Sequence[Obs]) -> np.ndarray:
    """Each trip's most recent same-day trip that closed before it opened; -1 for none.
    Times don't move in a shuffle, so this is worked out once."""
    prior = np.full(len(obs), -1, dtype=np.int64)
    by_day: dict[int, list[int]] = {}
    for i, o in enumerate(obs):
        by_day.setdefault(o.day, []).append(i)
    for members in by_day.values():
        for i in members:
            closed = [j for j in members if j != i and obs[j].exit_at < obs[i].entry_at]
            if closed:
                prior[i] = max(closed, key=lambda j: (obs[j].exit_at, j))
    return prior


def groups(r: np.ndarray, prior: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """After a loss, after a win, from each trip's last resolved trip and these outcomes. A
    shuffle calls this on every draw: the groups depend on which trades lost."""
    has = prior >= 0
    sign = np.where(has, r[np.where(has, prior, 0)], 0.0)
    return has & (sign < 0), has & (sign > 0)


def population_and_condition(obs: Sequence[Obs]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The population, and the after-a-loss and after-a-win groups, per trip, in the order given."""
    prior = last_resolved(obs)
    r = np.array([o.r for o in obs], dtype=float)
    after_loss, after_win = groups(r, prior)
    return prior >= 0, after_loss, after_win
