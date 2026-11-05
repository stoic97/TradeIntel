"""B2's shuffle test, in the one place production and research may both reach.

Chapter 3 may say a direction for trades after two straight losses only if this passes on the
trader's own file. Production may not import research (methodology Rule 5), and the Bayesian fit
in research needs packages the server doesn't install, so this is plain numpy.

What it takes from the framework (``framework_v1.yaml``), unchanged: the null N-B, outcomes
shuffled within each day, 2,000 draws, and B2's minimum of 30 condition and 60 comparison trades.
The groups are the ones ``b2_condition`` defines.

What it had to decide, because the framework states no bar for this null and this isn't one of
its Findings:

* **Two-sided, p <= 0.05.** The framework's level is 5% and its false-positive band on noise is
  2% to 8%. B2's row is one-sided, but the sentence says whichever way the means point, so a
  test of one direction would let the other through untested.
* **Rupees, the two means the sentence prints,** so the sentence and its test can't disagree.
* **No 0.25R cutoff.** Most traders have no R, and the sentence prints both figures, so the size
  is there to be read. That cutoff belongs to a Finding's "big enough", and this isn't a Finding.

The condition is worked out again on every draw, because it depends on which trades lost, and
shuffling only the labels would test something else. A closed result says only that this test
can't separate the two groups. It isn't a finding about the trader.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from services.shared.conditions.b2_condition import Obs

DRAWS = 2000
MIN_CONDITION = 30
MIN_COMPARISON = 60
ALPHA = 0.05
SEED = 20260302  # fixed, so one file always gets one answer. Chosen once, before any real file.


@dataclass(frozen=True)
class ShuffleResult:
    n_condition: int
    n_comparison: int
    difference: float | None  # condition mean less comparison mean
    p: float | None
    passes: bool


def last_two_resolved(obs: Sequence[Obs]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The population's trips, and each one's two most recent resolved trips before entry.

    Times don't move in a shuffle, so this is worked out once. It gives the same population and
    condition as ``b2_condition.population_and_condition``, which a test holds it to.
    """
    by_day: dict[int, list[int]] = {}
    for i, o in enumerate(obs):
        by_day.setdefault(o.day, []).append(i)
    found: list[tuple[int, int, int]] = []
    for members in by_day.values():
        for i in members:
            priors = [j for j in members if j != i and obs[j].exit_at < obs[i].entry_at]
            if len(priors) >= 2:
                last_two = sorted(priors, key=lambda j: obs[j].exit_at)[-2:]
                found.append((i, last_two[0], last_two[1]))
    found.sort()
    table = np.array(found, dtype=np.int64).reshape(-1, 3)
    return table[:, 0], table[:, 1], table[:, 2]


def shuffle_within_days(r: np.ndarray, day: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """The same outcomes, each moved to a random trade on its own day (N-B)."""
    slots = np.argsort(day, kind="stable")
    drawn = np.lexsort((rng.random(len(r)), day))
    moved = np.empty_like(r)
    moved[slots] = r[drawn]
    return moved


def _difference(r: np.ndarray, pop: np.ndarray, first: np.ndarray, second: np.ndarray) -> tuple[float, int, int]:
    cond = (r[first] < 0) & (r[second] < 0)
    n_condition = int(cond.sum())
    n_comparison = len(pop) - n_condition
    if not n_condition or not n_comparison:
        return 0.0, n_condition, n_comparison
    outcomes = r[pop]
    return float(outcomes[cond].mean() - outcomes[~cond].mean()), n_condition, n_comparison


def shuffle_test(obs: Sequence[Obs], draws: int = DRAWS) -> ShuffleResult:
    """Would shuffling each day's outcomes open a gap as wide as the file's own, either way?"""
    if not obs:
        return ShuffleResult(0, 0, None, None, False)
    r = np.array([o.r for o in obs], dtype=float)
    day = np.array([o.day for o in obs])
    pop, first, second = last_two_resolved(obs)
    observed, n_condition, n_comparison = _difference(r, pop, first, second)
    if n_condition < MIN_CONDITION or n_comparison < MIN_COMPARISON:
        return ShuffleResult(n_condition, n_comparison, None, None, False)

    rng = np.random.default_rng(SEED)
    wider = 0
    for _ in range(draws):
        moved = shuffle_within_days(r, day, rng)
        simulated, _, _ = _difference(moved, pop, first, second)
        wider += abs(simulated) >= abs(observed)
    p = (wider + 1) / (draws + 1)
    return ShuffleResult(n_condition, n_comparison, observed, p, p <= ALPHA)
