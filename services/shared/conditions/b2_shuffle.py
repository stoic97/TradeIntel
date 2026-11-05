"""B2's shuffle test, in the one place production and research may both reach.

Chapter 3 may say a direction for trades after two straight losses only if this passes on the
trader's own file. Production may not import research (methodology Rule 5), and the Bayesian fit
in research needs packages the server doesn't install, so this is plain numpy.

The rule is in ``framework_v1.yaml`` under ``production_gates``, and a test holds these constants
to it: the null N-B, outcomes shuffled within each day, 2,000 draws, B2's minimum of 30 condition
and 60 comparison trades, and p <= 0.05 one-sided in B2's stated direction, on the two rupee means
the sentence prints. The groups are the ones ``b2_condition`` defines. There is no 0.25R cutoff:
most traders have no R, and that cutoff is a Finding's "big enough", which this isn't.

A result in the other direction keeps the gate closed, however strong. Trades after two losses
doing better than the others isn't this gate opening, and Scope doesn't print a sentence the file
argues against.

The condition is worked out again on every draw, because it depends on which trades lost, and
shuffling only the labels would test something else. A closed result says only that this test
didn't find what it looks for. It isn't a finding about the trader.
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
DIRECTION = "<"  # B2's own: the condition's mean below the comparison's
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
    """Would shuffling each day's outcomes put the condition this far below the comparison?"""
    if not obs:
        return ShuffleResult(0, 0, None, None, False)
    r = np.array([o.r for o in obs], dtype=float)
    day = np.array([o.day for o in obs])
    pop, first, second = last_two_resolved(obs)
    observed, n_condition, n_comparison = _difference(r, pop, first, second)
    if n_condition < MIN_CONDITION or n_comparison < MIN_COMPARISON:
        return ShuffleResult(n_condition, n_comparison, None, None, False)

    rng = np.random.default_rng(SEED)
    as_low = 0
    for _ in range(draws):
        moved = shuffle_within_days(r, day, rng)
        simulated, _, _ = _difference(moved, pop, first, second)
        as_low += simulated <= observed
    p = (as_low + 1) / (draws + 1)
    return ShuffleResult(n_condition, n_comparison, observed, p, p <= ALPHA and observed < 0)
