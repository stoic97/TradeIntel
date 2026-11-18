"""The finding bar: corrected for every check in a family fixed in advance (TICKET-909).

Ruled 12 Nov 2026 (research seat): Westfall-Young step-down min-p, on the within-day
shuffle every check already runs, with Holm as the fallback for a check that can't share
that shuffle. The rule is in ``framework_v1.yaml`` under ``multiplicity.finding_bar`` and in
the research spec, section 5.5a.

* **The family is fixed in advance, never counted at run time:** the core list's checks, by
  id, read from the framework (``family``), so a trader with fewer eligible checks does not
  get an easier bar. A check that can't run for him, below its minimum or not built yet,
  stays in the family with p = 1.
* **One shuffle, every check.** Each draw computes every eligible check's statistic on the
  same shuffled book, which keeps the real correlation between checks; that is why this
  wastes no power where Bonferroni would.
* **Step-down min-p.** Sort the observed p-values. For the k-th smallest, the adjusted p is
  the share of draws where the smallest null p among the checks not yet rejected is at or
  below the observed one, made monotone. This holds the familywise error at 5% whatever
  the correlation, and is never weaker than Holm.
* **p = (b + 1) / (N + 1)**, never 0.

A check whose null is not this shuffle is corrected by ``holm`` with the same m.

Plain numpy, and the framework is read through ``shared.prereg``: production may import
this, research may import this, and this imports neither.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from services.shared.prereg import reader

EDGE_MAP = "C1"
"""The Edge Map's cell family sits beside the core list (spec section 9), not in it."""


def family(framework: reader.Framework | None = None) -> tuple[str, ...]:
    """The checks the bar corrects for: the core list, from the pre-registered framework."""
    framework = framework or reader.load()
    return tuple(t.id for t in framework.tests if t.id != EDGE_MAP)


def raw_p(observed: float, null: np.ndarray) -> float:
    """One-sided, below: how often a shuffle came out at or below what was observed."""
    return (1 + int(np.count_nonzero(null <= observed))) / (len(null) + 1)


def _null_p(null: np.ndarray) -> np.ndarray:
    """Each draw's own p against the rest of its null: how extreme that draw was."""
    order = np.sort(null)
    at_or_below = np.searchsorted(order, null, side="right")
    return at_or_below / len(null)


def step_down_min_p(observed: Mapping[str, float | None],
                    null: Mapping[str, np.ndarray],
                    checks: tuple[str, ...]) -> dict[str, float]:
    """Adjusted p for every check in ``checks``. A check with no observed statistic (None,
    or missing) can't run for this trader: it stays in the family at p = 1.

    Every eligible check's ``null`` holds the same N draws, in the same order: draw b of
    one check is draw b of every other, which is what carries their correlation.
    """
    eligible = [c for c in checks if observed.get(c) is not None]
    adjusted = {c: 1.0 for c in checks}
    if not eligible:
        return adjusted
    draws = {len(null[c]) for c in eligible}
    if len(draws) != 1:
        raise ValueError("every check must be measured on the same draws")
    n = draws.pop()
    raw = {c: raw_p(observed[c], null[c]) for c in eligible}
    per_draw = np.vstack([_null_p(null[c]) for c in eligible])  # checks x draws
    position = {c: i for i, c in enumerate(eligible)}
    ordered = sorted(eligible, key=lambda c: (raw[c], c))
    running = 0.0
    for k, check in enumerate(ordered):
        still = [position[c] for c in ordered[k:]]
        smallest = per_draw[still].min(axis=0)
        q = (1 + int(np.count_nonzero(smallest <= raw[check]))) / (n + 1)
        running = max(running, q)
        adjusted[check] = min(1.0, running)
    return adjusted


def holm(raw: Mapping[str, float | None], checks: tuple[str, ...]) -> dict[str, float]:
    """Holm's step-down on the whole family, for a check that can't share the shuffle."""
    m = len(checks)
    adjusted = {c: 1.0 for c in checks}
    ordered = sorted((c for c in checks if raw.get(c) is not None), key=lambda c: raw[c])
    running = 0.0
    for i, check in enumerate(ordered):
        running = max(running, min(1.0, (m - i) * raw[check]))
        adjusted[check] = running
    return adjusted


def bonferroni(p: float, checks: tuple[str, ...]) -> float:
    """For comparison only: the bar the ruling turned down as too strict."""
    return min(1.0, p * len(checks))
