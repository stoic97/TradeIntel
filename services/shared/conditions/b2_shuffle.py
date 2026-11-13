"""B2's shuffle test, in the one place production and research may both reach.

Chapter 3 may say a direction for trades after two straight losses only if this passes on the
trader's own file. Production may not import research (methodology Rule 5), and the Bayesian fit
in research needs packages the server doesn't install, so this is plain numpy.

The rule is in ``framework_v1.yaml`` under ``production_gates``, and a test holds these constants
to it: the null N-B, outcomes shuffled within each day, 10,000 draws, B2's minimum of 30 condition
and 60 comparison trades, one-sided in B2's stated direction, on the two rupee means the sentence
prints.

**The bar corrects for every check tried (TICKET-909).** A finding needs its p adjusted for the
family fixed in advance (``multiplicity.family``: the 18 checks on the core list in the framework,
spec section 5.5a), by Westfall-Young step-down min-p on this same shuffle, at or below 0.05. The
divisor is never counted at run time: a check that can't run for him stays in the family at
p = 1. Today B2 is the only check production runs, so the others sit at 1 and B2's adjusted p is
about its own; the bar tightens by itself as each further check is built onto the same shuffle.

**And it has to point the same way in both halves of his own trading days,** split in date order.
Neither half needs to be significant alone; a gap that reverses between halves is not a finding.

Three levels come back, for the page to say which: a finding; worth watching (p <= 0.05 before the
correction, but not after it, or not in both halves), which is never called a finding; and not
enough trades yet. The groups are the ones ``b2_condition`` defines. There is no 0.25R cutoff:
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

from services.shared.conditions import multiplicity
from services.shared.conditions.b2_condition import Obs

DRAWS = 10000
MIN_CONDITION = 30
MIN_COMPARISON = 60
ALPHA = 0.05
DIRECTION = "<"  # B2's own: the condition's mean below the comparison's
SEED = 20260302  # fixed, so one file always gets one answer. Chosen once, before any real file.


FINDING = "finding"
WORTH_WATCHING = "worth_watching"
NOT_ENOUGH = "not_enough"
NOTHING = "nothing"
CHECK = "B2"


@dataclass(frozen=True)
class ShuffleResult:
    n_condition: int
    n_comparison: int
    difference: float | None  # condition mean less comparison mean
    p: float | None           # before the correction
    p_adjusted: float | None = None  # for the family fixed in advance
    halves: tuple[float | None, float | None] | None = None
    level: str = NOT_ENOUGH
    family_size: int = 0

    @property
    def passes(self) -> bool:
        """A finding: the corrected bar cleared, in B2's direction, in both halves."""
        return self.level == FINDING


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


def halves(obs: Sequence[Obs]) -> tuple[float | None, float | None]:
    """The condition-less-comparison gap in each half of his own trading days, in date order.
    None for a half that holds no condition trade or no comparison trade."""
    days = sorted({o.day for o in obs})
    cut = (len(days) + 1) // 2
    out: list[float | None] = []
    for part in (set(days[:cut]), set(days[cut:])):
        sub = [o for o in obs if o.day in part]
        if not sub:
            out.append(None)
            continue
        r = np.array([o.r for o in sub], dtype=float)
        gap, n_cond, n_comp = _difference(r, *last_two_resolved(sub))
        out.append(gap if n_cond and n_comp else None)
    return out[0], out[1]


def _same_way(both: tuple[float | None, float | None]) -> bool:
    return all(gap is not None and gap < 0 for gap in both)


def shuffle_test(obs: Sequence[Obs], draws: int = DRAWS,
                 checks: tuple[str, ...] | None = None) -> ShuffleResult:
    """Would shuffling each day's outcomes put the condition this far below the comparison,
    corrected for the family of checks, and does it point the same way in both halves?"""
    checks = checks or multiplicity.family()
    if not obs:
        return ShuffleResult(0, 0, None, None, family_size=len(checks))
    r = np.array([o.r for o in obs], dtype=float)
    day = np.array([o.day for o in obs])
    pop, first, second = last_two_resolved(obs)
    observed, n_condition, n_comparison = _difference(r, pop, first, second)
    if n_condition < MIN_CONDITION or n_comparison < MIN_COMPARISON:
        return ShuffleResult(n_condition, n_comparison, None, None, family_size=len(checks))

    rng = np.random.default_rng(SEED)
    null = np.empty(draws)
    for b in range(draws):
        moved = shuffle_within_days(r, day, rng)
        null[b], _, _ = _difference(moved, pop, first, second)
    p = multiplicity.raw_p(observed, null)
    # Every other check in the family can't run in production yet: each stays in at p = 1.
    adjusted = multiplicity.step_down_min_p({CHECK: observed}, {CHECK: null}, checks)[CHECK]
    split = halves(obs)
    if observed < 0 and adjusted <= ALPHA and _same_way(split):
        level = FINDING
    elif observed < 0 and p <= ALPHA:
        level = WORTH_WATCHING
    else:
        level = NOTHING
    return ShuffleResult(n_condition, n_comparison, observed, p, adjusted, split, level,
                         len(checks))
