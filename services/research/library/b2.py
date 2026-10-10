"""B2 - post-loss expectancy, end to end. Annex A.1 is the template for every test.

    population : round trips with >= 2 same-day prior round trips resolved before entry
    condition  : the two most recent resolved trips before entry were losses
    comparison : all other round trips in the population
    outcome    : R
    model      : M1, day-level random intercepts
    direction  : "<"      theta_min: 0.25R      minimum: 30 condition / 60 comparison

Resolved means exited before this entry: an overlapping trip does not count, however
it later ends. Losses do not carry across the day boundary.

The run: zones -> condition -> M1 on the training zone -> M1 on the isolation zone,
prior only -> the statistical core -> the Finding. The isolation fit never sees the
training posterior (section 5.2); it shares only the pre-committed priors.

What this cycle does not do: controls (instrument, vol tercile, session bucket), the
robustness sweeps, BH within the family, economic significance, sign agreement. Each
is a later cycle and is carried as an unevaluated gate.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import numpy as np

from services.research.engine import evidence as ev
from services.research.engine import zones as zn
from services.research.models import m1
from services.research.models.base import FitConfig, FitResult, failing_parameters

TEST_ID = "B2"
DIRECTION = "<"
THETA_MIN = ev.THETA_MIN_R
N_MIN = (30, 60)


@dataclass(frozen=True)
class Obs:
    """One round trip as a test sees it: when it was open, which day, what it made."""

    day: int
    entry_at: float
    exit_at: float
    r: float


def from_synthetic(trips: Iterable[object]) -> list[Obs]:
    return [
        Obs(day=int(t.day), entry_at=float(t.entry_idx), exit_at=float(t.exit_idx), r=float(t.r_multiple))
        for t in trips
    ]


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


@dataclass(frozen=True)
class B2Result:
    core: ev.StatisticalCore
    finding: ev.Finding
    n_condition: int
    n_comparison: int
    n_condition_isolation: int
    train: FitResult
    hold: FitResult
    zones: zn.Zones


def _m1_data(obs: Sequence[Obs], idx: np.ndarray, in_pop: np.ndarray, cond: np.ndarray) -> m1.M1Data:
    sel = idx[in_pop[idx]]
    return m1.M1Data(
        r=np.array([obs[i].r for i in sel]),
        condition=cond[sel].astype(float),
        day=np.array([obs[i].day for i in sel]),
    )


def run(
    obs: Sequence[Obs],
    priors: m1.M1Priors | None = None,
    config: FitConfig | None = None,
) -> B2Result:
    order = sorted(range(len(obs)), key=lambda i: (obs[i].day, obs[i].entry_at))
    obs = [obs[i] for i in order]
    days = np.array([o.day for o in obs])
    zones = zn.split(days)
    in_pop, cond = population_and_condition(obs)

    train_data = _m1_data(obs, zones.training, in_pop, cond)
    hold_data = _m1_data(obs, zones.isolation, in_pop, cond)
    train = m1.fit(train_data, priors, config, keep_samples=True)
    hold = m1.fit(hold_data, priors, config, keep_samples=True)
    assert train.samples is not None and hold.samples is not None

    core = ev.statistical_core(train.samples["theta"], hold.samples["theta"], DIRECTION, THETA_MIN)

    n_condition = int(train_data.condition.sum())
    n_comparison = int(train_data.n_obs - n_condition)
    n_condition_isolation = int(hold_data.condition.sum())
    sigma_r = float(np.std(train_data.r, ddof=1)) if train_data.n_obs > 1 else float("nan")
    theta_bad = "theta" in failing_parameters(train) or "theta" in failing_parameters(hold)

    finding = ev.assess(
        core,
        n_condition=n_condition,
        n_comparison=n_comparison,
        n_condition_isolation=n_condition_isolation,
        sigma_r=sigma_r,
        n_min=N_MIN,
        diagnostics_failed=theta_bad,
    )
    return B2Result(core, finding, n_condition, n_comparison, n_condition_isolation, train, hold, zones)
