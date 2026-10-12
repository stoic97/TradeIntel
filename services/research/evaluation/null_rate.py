"""How often a test announces a leak in a trader who has none (R-Spec §6.2).

This is the number a sceptical trader should ask for first, and the one it is
easiest to flatter ourselves about. Four decisions keep it honest.

**The denominator is evaluable histories only.** A history where the test
cannot reach ``n_min`` condition trades never had the chance to fire, so
counting it would deflate the rate towards zero while telling us nothing. Such
histories are excluded and reported separately with their reason. A sweep that
starves on most of its corpus has not measured a low false-positive rate; it
has measured that the test rarely runs.

**The interval is clustered, and the wider one wins.** The null histories index
into one shared crude series, so two histories covering the same months see the
same price noise and their outcomes are correlated. A binomial interval assumes
they are independent and is therefore too narrow. The block bootstrap resamples
whole calendar clusters with replacement, carrying each cluster's size, so the
effective sample size falls to the number of independent windows. Per TD-017
the authority is whichever of the two is wider.

**At zero events that rule is not enough, so an envelope is reported too.**
The first full sweep found the hole: when every cluster has zero fires, every
resample also has zero, and the bootstrap returns [0%, 0%] — certainty, which
is false. Authority then falls to the binomial by default, and a binomial over
278 histories drawn from 18 calendar windows claims precision the corpus does
not contain. So a third reading is computed: each cluster as one Bernoulli
observation of "did anything in this window fire?". That is the maximally
correlated reading and the conservative end of an envelope whose other end is
the independence assumption. The truth lies between them. Neither is chosen
here.

**No gate reading is chosen at all.** TD-012 is open: §6.2 fixes the band at
[2%, 8%] without saying whether it binds on the point estimate, the interval,
or the envelope. All three are reported under their own names and there is
deliberately no ``passed`` field — a single boolean would quietly make the
CEO's ruling for him.

One asymmetry, stated in the verdict text. A rate *above* the band is a trust
failure: the engine invents leaks. A rate *below* the band is not a pass — a
test that fires on nothing clears this gate for the wrong reason, and is good
news only read beside recall on planted histories.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
from scipy.stats import norm

# R-Spec §6.2: the Class B band.
GATE_LOW = 0.02
GATE_HIGH = 0.08

N_BOOT = 2000
LEVEL = 0.95


@dataclass(frozen=True)
class NullOutcome:
    """One null history's result: whether the test could run, and whether it fired."""

    history_id: str
    cluster: int
    evaluable: bool
    fired: bool
    reason: str = ""


@dataclass(frozen=True)
class NullRate:
    clustering_unit: str
    n_histories: int
    n_evaluable: int
    n_starved: int
    n_fired: int
    n_clusters: int
    n_clusters_fired: int
    rate: float
    binomial_lo: float
    binomial_hi: float
    bootstrap_lo: float
    bootstrap_hi: float
    bootstrap_degenerate: bool
    cluster_lo: float
    cluster_hi: float
    lo: float
    hi: float
    envelope_lo: float
    envelope_hi: float
    interval_source: str
    point_inside: bool
    interval_inside: bool
    envelope_inside: bool
    verdict: str
    starved_reasons: tuple[str, ...] = ()

    def record(self) -> dict[str, object]:
        """The JSON written beside the sweep, so the number carries its own caveats."""
        return {
            "gate": {"low": GATE_LOW, "high": GATE_HIGH, "source": "R-Spec §6.2"},
            "clustering_unit": self.clustering_unit,
            "n_histories": self.n_histories,
            "n_evaluable": self.n_evaluable,
            "n_starved": self.n_starved,
            "n_fired": self.n_fired,
            "n_clusters": self.n_clusters,
            "n_clusters_fired": self.n_clusters_fired,
            "rate": self.rate,
            "interval": {
                "lo": self.lo,
                "hi": self.hi,
                "source": self.interval_source,
                "level": LEVEL,
                "binomial": [self.binomial_lo, self.binomial_hi],
                "block_bootstrap": [self.bootstrap_lo, self.bootstrap_hi],
                "bootstrap_degenerate": self.bootstrap_degenerate,
                "cluster_level": [self.cluster_lo, self.cluster_hi],
                "authority": "the wider of binomial and block bootstrap (TD-017)",
                "envelope": {
                    "independent_hi": self.hi,
                    "clustered_hi": self.cluster_hi,
                    "lo": self.envelope_lo,
                    "hi": self.envelope_hi,
                    "meaning": (
                        "independent_hi assumes every history is its own observation; "
                        "clustered_hi assumes a whole window is one. The truth lies "
                        "between, and at zero events the bootstrap is degenerate so "
                        "only this envelope expresses the real uncertainty."
                    ),
                },
            },
            "readings": {
                "point_inside": self.point_inside,
                "interval_inside": self.interval_inside,
                "envelope_inside": self.envelope_inside,
                "note": "TD-012 open: which reading binds is the kickoff ruling",
            },
            "starved_reasons": list(self.starved_reasons),
            "verdict": self.verdict,
        }


def cluster_by_window(representative_day: dict[str, int], width_days: int) -> dict[str, int]:
    """Group histories by the calendar window they trade in.

    The representative day is one integer per history on the shared series'
    day axis — its median traded day. Histories in the same window saw the same
    crude, so they are one observation for interval purposes, not two.
    """
    if width_days <= 0:
        raise ValueError("width_days must be positive")
    return {h: int(day) // int(width_days) for h, day in representative_day.items()}


def wilson_interval(n_fired: int, n: int, level: float = LEVEL) -> tuple[float, float]:
    """Wilson score interval: defined at zero fires, where the normal one is not."""
    if n <= 0:
        raise ValueError("no evaluable histories to form an interval over")
    z = float(norm.ppf(0.5 + level / 2.0))
    p = n_fired / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2.0 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n))
    return max(0.0, centre - half), min(1.0, centre + half)


def _by_cluster(outcomes: Iterable[NullOutcome]) -> dict[int, list[bool]]:
    out: dict[int, list[bool]] = {}
    for o in outcomes:
        if o.evaluable:
            out.setdefault(o.cluster, []).append(o.fired)
    if not out:
        raise ValueError("no evaluable histories to cluster")
    return out


def cluster_bootstrap_interval(
    outcomes: Iterable[NullOutcome],
    *,
    seed: int,
    n_boot: int = N_BOOT,
    level: float = LEVEL,
) -> tuple[float, float]:
    """Resample whole calendar clusters, carrying their sizes, so n varies as it really does."""
    by_cluster = _by_cluster(outcomes)
    keys = sorted(by_cluster)
    fires = np.array([float(sum(by_cluster[k])) for k in keys])
    sizes = np.array([float(len(by_cluster[k])) for k in keys])
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(keys), size=(n_boot, len(keys)))
    rates = fires[draws].sum(axis=1) / sizes[draws].sum(axis=1)
    tail = (1.0 - level) / 2.0
    lo, hi = np.quantile(rates, [tail, 1.0 - tail])
    return float(lo), float(hi)


def cluster_level_interval(
    outcomes: Iterable[NullOutcome], level: float = LEVEL
) -> tuple[float, float, int]:
    """Each window as one observation: did anything in it fire?

    The maximally correlated reading. It is what the bound becomes if histories
    sharing a calendar window are treated as telling us one thing rather than
    many — the conservative end, and the only end that says anything useful when
    the bootstrap degenerates at zero events.
    """
    by_cluster = _by_cluster(outcomes)
    n_fired = sum(1 for fires in by_cluster.values() if any(fires))
    lo, hi = wilson_interval(n_fired, len(by_cluster), level=level)
    return lo, hi, n_fired


def _verdict(
    rate: float,
    lo: float,
    hi: float,
    *,
    cluster_hi: float,
    n_evaluable: int,
    n_clusters: int,
    degenerate: bool,
) -> str:
    caveat = ""
    if degenerate and n_clusters < n_evaluable:
        caveat = (
            f" The interval assumes {n_evaluable} independent histories, but they sit in "
            f"{n_clusters} calendar windows and at zero events the bootstrap cannot say so; "
            f"treating a window as one observation puts the bound at {cluster_hi:.1%}, so the "
            "true bound lies between the two."
        )
    if rate < GATE_LOW:
        return (
            f"below the band: fires on {rate:.1%} of nulls, under the {GATE_LOW:.0%} floor. "
            "Not a pass — read it beside recall on planted histories, because a test that "
            "fires on nothing clears this gate for the wrong reason." + caveat
        )
    if rate > GATE_HIGH:
        return (
            f"above the band: fires on {rate:.1%} of nulls, over the {GATE_HIGH:.0%} ceiling. "
            "The engine invents leaks at this rate and must not be shown to a trader." + caveat
        )
    contained = lo >= GATE_LOW and hi <= GATE_HIGH
    envelope_ok = cluster_hi <= GATE_HIGH
    return (
        f"inside the band at {rate:.1%}; the interval [{lo:.1%}, {hi:.1%}] is "
        f"{'also inside' if contained else 'not contained'}, and the clustered bound "
        f"{'holds' if envelope_ok else f'reaches {cluster_hi:.1%}, past the ceiling'} "
        "(TD-012: which reading binds is the kickoff ruling)." + caveat
    )


def assess(
    outcomes: Iterable[NullOutcome],
    *,
    clustering_unit: str,
    seed: int,
    n_boot: int = N_BOOT,
    level: float = LEVEL,
) -> NullRate:
    """The false-positive rate with every interval its clustering allows.

    ``clustering_unit`` is required and must say what one independent observation
    is (SR-007). A rate that cannot name its clustering unit is not a rate.
    """
    if not clustering_unit or not clustering_unit.strip():
        raise ValueError("clustering_unit must name what one independent observation is")

    items = list(outcomes)
    evaluable = [o for o in items if o.evaluable]
    starved = [o for o in items if not o.evaluable]
    if any(o.fired for o in starved):
        raise ValueError("a history that could not be evaluated cannot have fired")
    if not evaluable:
        raise ValueError(
            "no evaluable histories: every null starved before the test could fire, "
            "so no false-positive rate exists to report"
        )

    n_evaluable = len(evaluable)
    n_fired = sum(1 for o in evaluable if o.fired)
    rate = n_fired / n_evaluable
    n_clusters = len({o.cluster for o in evaluable})

    b_lo, b_hi = wilson_interval(n_fired, n_evaluable, level=level)
    k_lo, k_hi = cluster_bootstrap_interval(evaluable, seed=seed, n_boot=n_boot, level=level)
    c_lo, c_hi, n_clusters_fired = cluster_level_interval(evaluable, level=level)
    degenerate = k_lo == k_hi

    if (k_hi - k_lo) >= (b_hi - b_lo):
        lo, hi, source = k_lo, k_hi, "block bootstrap"
    else:
        lo, hi, source = b_lo, b_hi, "binomial"

    env_lo, env_hi = min(lo, c_lo), max(hi, c_hi)
    return NullRate(
        clustering_unit=clustering_unit,
        n_histories=len(items),
        n_evaluable=n_evaluable,
        n_starved=len(starved),
        n_fired=n_fired,
        n_clusters=n_clusters,
        n_clusters_fired=n_clusters_fired,
        rate=float(rate),
        binomial_lo=b_lo,
        binomial_hi=b_hi,
        bootstrap_lo=k_lo,
        bootstrap_hi=k_hi,
        bootstrap_degenerate=bool(degenerate),
        cluster_lo=c_lo,
        cluster_hi=c_hi,
        lo=lo,
        hi=hi,
        envelope_lo=env_lo,
        envelope_hi=env_hi,
        interval_source=source,
        point_inside=bool(GATE_LOW <= rate <= GATE_HIGH),
        interval_inside=bool(lo >= GATE_LOW and hi <= GATE_HIGH),
        envelope_inside=bool(env_lo >= GATE_LOW and env_hi <= GATE_HIGH),
        verdict=_verdict(
            rate, lo, hi,
            cluster_hi=c_hi,
            n_evaluable=n_evaluable,
            n_clusters=n_clusters,
            degenerate=degenerate,
        ),
        starved_reasons=tuple(sorted({o.reason for o in starved if o.reason})),
    )
