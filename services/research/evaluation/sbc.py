"""Simulation-based calibration — and a detector built so that it can fail.

Section 6.4, after Talts et al. 2018: draw a parameter vector from the prior, simulate
data from it, fit, and record the rank of the true value among the posterior draws.
Over many replications those ranks must be uniform. If the posterior is too narrow the
truth falls outside its bulk and ranks pile at both ends; if it is biased, they skew.

**The bound on what this proves, in the spec's words.** SBC licenses that the
inference machinery recovers parameters *under our own assumed model*. It does not
license that the model is right — a wrong model can pass SBC beautifully. M-SIM is the
other gate, and a model that passes SBC and fails M-SIM is a model whose intervals lie.

**Ranks come from thinned draws.** Posterior draws are autocorrelated, so a rank over
4,000 correlated draws is not a rank over 4,000 independent ones and the uniformity
test would be reading dependence it does not model. Thinning to a fixed count is the
standard remedy and the count is pre-registered per run, never tuned to a result.

**The gate is applied per parameter, and failures are counted.** Dropping a
replication silently biases the very test being run. Worse, dropping a whole
replication because one parameter failed conditions the surviving sample on an
unrelated parameter: measured 10 Oct 2026, a third of replications were refused on
``tau_day``, whose scale is unidentifiable when the prior draws it near zero, while
``theta`` mixed cleanly in every one of them - and the survivors were exactly the
replications with a larger true day effect. So each parameter contributes its rank
when its own r_hat and bulk ess pass, every exclusion is counted against that
parameter, and the record carries a completion rate per parameter beside its verdict.
Divergences remain fit-level: a diverged fit fails every parameter.

``MIN_COMPLETION`` is **arbitrary**. Below it the surviving subset is biased enough
that a uniform rank histogram would not mean much; 0.9 is a judgement, carried with
TD-020's ruling rather than presented as derived.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy import stats

from services.research.models.base import FitResult, failing_parameters

# Reused rather than duplicated: one place names the library versions a measurement
# was taken with.
from services.research.models.benchmark import environment

N_BINS = 20
ALPHA = 0.01  # pre-registered: the chi-square level the rank histogram must clear
MIN_COMPLETION = 0.9  # arbitrary; see the module docstring


@dataclass(frozen=True)
class Uniformity:
    uniform: bool
    chi_square: float
    p_value: float
    n_bins: int
    n_ranks: int
    detail: str


def rank_of(draws: np.ndarray, truth: float) -> int:
    """How many posterior draws fall below the truth. 0 .. len(draws)."""
    return int(np.sum(np.asarray(draws) < truth))


def thin(draws: np.ndarray, n_thin: int) -> np.ndarray:
    """``n_thin`` draws spread evenly across the sample, to break autocorrelation."""
    flat = np.asarray(draws).ravel()
    if n_thin < 2:
        raise ValueError("n_thin must be at least 2")
    if n_thin > flat.size:
        raise ValueError(f"cannot thin {flat.size} draws down to {n_thin}")
    return flat[np.linspace(0, flat.size - 1, n_thin).astype(int)]


def uniformity(
    ranks: np.ndarray | Sequence[int],
    n_draws: int,
    n_bins: int = N_BINS,
    alpha: float = ALPHA,
) -> Uniformity:
    """Chi-square test that the ranks are uniform on 0 .. n_draws."""
    values = np.asarray(ranks)
    if values.size == 0:
        raise ValueError("no ranks to test")
    if values.min() < 0 or values.max() > n_draws:
        raise ValueError(
            f"a rank must lie in [0, {n_draws}]; got [{values.min()}, {values.max()}]"
        )
    counts, _ = np.histogram(values, bins=np.linspace(0, n_draws + 1, n_bins + 1))
    expected = values.size / n_bins
    chi_square = float((((counts - expected) ** 2) / expected).sum())
    p_value = float(stats.chi2.sf(chi_square, n_bins - 1))
    passed = p_value >= alpha
    return Uniformity(
        uniform=passed,
        chi_square=chi_square,
        p_value=p_value,
        n_bins=n_bins,
        n_ranks=int(values.size),
        detail=(
            f"chi2={chi_square:.1f} on {n_bins - 1} df over {values.size} ranks, "
            f"p={p_value:.4g}, {'uniform' if passed else 'NOT uniform'} at alpha={alpha}"
        ),
    )


@dataclass(frozen=True)
class SBCResult:
    model: str
    spec_digest: str
    n_replications: int
    n_thin: int
    ranks: dict[str, list[int]] = field(default_factory=dict)
    excluded: dict[str, int] = field(default_factory=dict)
    diverged_replications: int = 0
    refused_replications: int = 0
    seconds: float = 0.0

    def verdicts(self) -> dict[str, Uniformity]:
        return {p: uniformity(r, self.n_thin) for p, r in self.ranks.items() if r}

    def completion(self) -> dict[str, float]:
        if not self.n_replications:
            return {}
        return {p: len(r) / self.n_replications for p, r in self.ranks.items()}

    def record(self) -> dict[str, Any]:
        verdicts = self.verdicts()
        completion = self.completion()
        enough = all(c >= MIN_COMPLETION for c in completion.values()) if completion else False
        return {
            "model": self.model,
            "spec_digest": self.spec_digest,
            "n_replications": self.n_replications,
            "n_thin": self.n_thin,
            "n_bins": N_BINS,
            "alpha": ALPHA,
            "min_completion": MIN_COMPLETION,
            "diverged_replications": self.diverged_replications,
            "refused_replications": self.refused_replications,
            "excluded_by_parameter": dict(sorted(self.excluded.items())),
            "completion": {p: round(c, 4) for p, c in sorted(completion.items())},
            "seconds": round(self.seconds, 2),
            "passed": bool(verdicts) and enough and all(v.uniform for v in verdicts.values()),
            "uniformity": {
                p: {
                    "uniform": v.uniform,
                    "chi_square": round(v.chi_square, 3),
                    "p_value": v.p_value,
                    "n_ranks": v.n_ranks,
                }
                for p, v in verdicts.items()
            },
            "ranks": {p: [int(r) for r in rs] for p, rs in self.ranks.items()},
            "environment": environment(),
            "bound": (
                "SBC licenses that the machinery recovers parameters under our own "
                "assumed model. It does not license that the model is right - a wrong "
                "model can pass SBC beautifully (section 6.4). M-SIM is the other gate."
            ),
        }


def run(
    *,
    n_replications: int,
    n_thin: int,
    fit: Callable[[Any, int], FitResult],
    prior_draw: Callable[[np.random.Generator], dict[str, float]],
    simulate: Callable[[dict[str, float], np.random.Generator], Any],
    params: Sequence[str],
    seed: int,
    model: str = "m1",
    progress_every: int = 0,
) -> SBCResult:
    """Draw, simulate, fit, rank - ``n_replications`` times, gating per parameter.

    The invariant, asserted by the caller's tests: for every parameter, the ranks it
    contributed plus the times it was excluded equal ``n_replications``. Nothing is
    lost without being counted against the parameter that lost it.
    """
    rng = np.random.default_rng(seed)
    ranks: dict[str, list[int]] = {p: [] for p in params}
    excluded: dict[str, int] = dict.fromkeys(params, 0)
    diverged = refused = 0
    spec_digest = ""
    started = time.perf_counter()

    for i in range(n_replications):
        truth = prior_draw(rng)
        data = simulate(truth, rng)
        try:
            result = fit(data, seed + i)
        except Exception:  # noqa: BLE001 - a refused replication is data, not a crash
            refused += 1
            for p in params:
                excluded[p] += 1
            continue
        if result.samples is None:
            raise ValueError("SBC needs the posterior draws: fit with keep_samples=True")
        spec_digest = result.spec_digest
        failing = failing_parameters(result)
        if result.divergences > 0:
            diverged += 1
        for p in params:
            if p in failing:
                excluded[p] += 1
            else:
                ranks[p].append(rank_of(thin(result.samples[p], n_thin), truth[p]))
        if progress_every and (i + 1) % progress_every == 0:
            done = len(ranks[params[0]])
            print(
                f"  {i + 1:5d} / {n_replications}  ({time.perf_counter() - started:5.0f} s)"
                f"  {params[0]} completed {done}",
                flush=True,
            )

    return SBCResult(
        model=model,
        spec_digest=spec_digest,
        n_replications=n_replications,
        n_thin=n_thin,
        ranks=ranks,
        excluded=excluded,
        diverged_replications=diverged,
        refused_replications=refused,
        seconds=time.perf_counter() - started,
    )
