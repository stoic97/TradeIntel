"""The B2 condition: "trading on after two straight losses", defined once.

PRD v1.2 section 6.3 and Appendix A require the Mirror and the research library to
count this behaviour with one function, and methodology Rule 5 forbids production
importing research. ``shared`` is the only place that satisfies both, so the
definition lives here and ``services/research/library/b2.py`` imports it.

The definition is unchanged from the pre-registered one in that module
(``framework_v1.yaml``, Annex A.1): the population is round trips with at least two
same-day prior trips **resolved** before entry -- exited before this entry, so an
overlapping trip never counts however it later ends -- and the condition is that the
two most recent of those both closed at a loss. A scratch trade among the two most
recent breaks the run. Losses do not carry across the day boundary.

``Obs.r`` is whatever the caller divides by: the research library passes R, the
Mirror and the Journal pass net rupees. The function reads only the **sign** of that
field, so both callers get the same population and the same condition on the same
trips -- asserted in ``tests/unit/shared/test_b2_condition.py``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Obs:
    """One round trip as a test sees it: when it was open, which day, what it made."""

    day: int
    entry_at: float
    exit_at: float
    r: float


def population_and_condition(obs: Sequence[Obs]) -> tuple[np.ndarray, np.ndarray]:
    """Annex A.1's population and condition, per trip, in the order given."""
    n = len(obs)
    in_pop = np.zeros(n, dtype=bool)
    cond = np.zeros(n, dtype=bool)
    by_day: dict[int, list[int]] = {}
    for i, o in enumerate(obs):
        by_day.setdefault(o.day, []).append(i)
    for members in by_day.values():
        for i in members:
            priors = [j for j in members if j != i and obs[j].exit_at < obs[i].entry_at]
            if len(priors) < 2:
                continue
            in_pop[i] = True
            last_two = sorted(priors, key=lambda j: obs[j].exit_at)[-2:]
            cond[i] = all(obs[j].r < 0 for j in last_two)
    return in_pop, cond
