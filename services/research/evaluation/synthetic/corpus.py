"""Corpus A: the planted grid and the two noise classes (Research Spec v1.0 §12.2).

* **The grid.** 17 behaviours x 3 effect sizes (theta_min, 2 theta_min, 4 theta_min,
  in each test's own unit) x 3 history lengths (100, 300, 1,000 trips) = 153 cells,
  x 8 seeds = 1,224 histories. Each is generated twice from the same seed - with
  the behaviour and without it (the twin) - and the difference is its truth.
* **Clean nulls** (400): zero edge, no behaviour, independent trades on a seeded
  random-walk market. The floor.
* **Adversarial nulls** (600): zero edge, no behaviour, on the real crude series -
  volatility clustering, regime switches, heavy tails, gaps - with a trade rate
  that drifts over the history and a different trading style per trader. The
  gates are read on this class.

**From planted size to generator strength.** The spec fixes each test's effect in
its own unit; the generator needs a mechanism strength. Where the mapping is exact
(a size multiplier, a stop moved by x R, a log-normal CV) it is used directly.
Where it is not, it comes from the pilot measurements below, taken on the crude
series on 6 Oct 2026 (3,000-trip runs, seed 5). A cell whose size the mechanism
cannot reach is planted at the mechanism's limit and marked ``reached=False``, so
recall is never scored against a size that was not planted. Every history also
carries the twin's measured avoidable cost, which is the truth an Avoidable Loss
estimate is checked against - not the nominal size.

**S5** plants on ``standin_regime`` until the fund's regime labels cross as data
(ADR 002). **B12**'s unit is net R per day; it is planted as a per-trip drift on
the rest of the day, assuming about one trip remains after a bad start.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from itertools import pairwise

import numpy as np

from services.research.evaluation.synthetic import behaviours as bh
from services.research.evaluation.synthetic.crude import LoadReport, MarketHistory
from services.research.evaluation.synthetic.market import Bars, MarketConfig, generate_bars
from services.research.evaluation.synthetic.trader import (
    Behaviour,
    TraderConfig,
    Trip,
    simulate_trader,
    volatility_cutoffs,
)

GRID_VERSION = "corpus_a_v1"
LENGTHS = (100, 300, 1000)
MULTIPLES = (1, 2, 4)  # x theta_min
SEEDS_PER_CELL = 8
N_CLEAN, N_ADVERSARIAL = 400, 600

# Pilot measurements on the crude series (see module docstring).
DRIFT_R_AT_P1 = 0.78  # a DRIFT trip taken against the move at p = 1 loses 0.78R vs the rest
CARRY_R_PER_P = 5.7  # a carried trip loses ~5.7R per unit of wrong-side probability
B1_RATIO_AT_P0 = 0.90  # post-loss / post-win latency ratio, falling ~linearly to 0 at p = 1
E5_FLOOR_RATIO = 0.59  # lowest winner/loser duration ratio EXIT reaches (f = 0.01, p = 1)
E5_THETA_FRACTION = 0.05  # early fraction that reaches the 0.67 ratio (theta_min)


@dataclass(frozen=True)
class Planting:
    behaviours: tuple[Behaviour, ...]
    nominal: float  # the planted size in the test's unit
    unit: str
    reached: bool  # False: planted at the mechanism's limit, below the nominal size


@dataclass(frozen=True)
class Cell:
    index: int
    test_id: str
    multiple: int
    n_trades: int


@dataclass(frozen=True)
class SyntheticHistory:
    kind: str  # "planted" | "clean_null" | "adversarial_null"
    seed: int
    n_trades: int
    trips: tuple[Trip, ...]
    cell: Cell | None = None
    planting: Planting | None = None
    twin: tuple[Trip, ...] = ()  # the same seed without the behaviour
    truth: dict[str, float] = field(default_factory=dict)
    # The market the trips index into, when it is not the shared series: a clean
    # null trades its own random walk, so its bars, dates and prices are its own.
    market: Market | None = field(default=None, compare=False, repr=False)


def _drift(factory: Callable[..., Behaviour], theta: float, **kw: object) -> Planting:
    p = theta / DRIFT_R_AT_P1
    return Planting((factory(min(p, 1.0), **kw),), theta, "R", p <= 1.0)


def _plant(test_id: str, k: int) -> Planting:
    """The behaviours that plant ``test_id`` at k x theta_min (Annex A units)."""
    if test_id in ("B2", "B5", "S1", "S10", "S11"):
        factory = {
            "B2": bh.b2_post_loss_expectancy,
            "B5": bh.b5_sequence_decay,
            "S1": bh.s1_session_expectancy,
            "S10": bh.s10_event_trading,
            "S11": bh.s11_edge_decay,
        }[test_id]
        return _drift(factory, 0.25 * k)
    if test_id == "S5":
        return _drift(bh.s5_regime_expectancy, 0.25 * k, label="stress")
    if test_id == "B12":
        planting = _drift(bh.b12_bad_start_day, 0.5 * k)
        return Planting(planting.behaviours, 0.5 * k, "R per day", planting.reached)
    if test_id == "R8":
        p = 0.25 * k / DRIFT_R_AT_P1
        both = (bh.r8_high_vol_size(1.25**k), bh.r8_high_vol_drift(min(p, 1.0)))
        return Planting(both, math.log(1.25) * k, "log size; R", p <= 1.0)
    if test_id == "R2":
        return Planting((bh.r2_post_loss_size_up(1.25**k),), math.log(1.25) * k, "log size", True)
    if test_id == "R1":
        cv = 0.6 * k
        sigma = math.sqrt(math.log(1 + cv**2))
        return Planting((bh.r1_size_dispersion(sigma),), cv, "CV of size", True)
    if test_id in ("R7", "E4'"):
        factory = bh.r7_stop_moved if test_id == "R7" else bh.e4p_late_loss_accrual
        return Planting((factory(0.25 * k),), 0.25 * k, "extra R beyond the stop", True)
    if test_id == "R11":
        return Planting((bh.r11_adds_to_losers(0.5 * k),), 0.25 * k, "extra R at the stop", True)
    if test_id == "E2":
        giveback = 1 - 0.75**k
        return Planting((bh.e2_gives_back_winners(giveback),), 1 - giveback, "capture", True)
    if test_id == "E5":
        ratio = 0.67**k
        reached = ratio >= E5_FLOOR_RATIO
        fraction = E5_THETA_FRACTION if k == 1 else 0.01
        return Planting((bh.e5_holding_asymmetry(fraction),), ratio, "duration ratio", reached)
    if test_id == "B1":
        ratio = 0.67**k
        p = 1 - ratio / B1_RATIO_AT_P0
        return Planting((bh.b1_post_loss_latency(1, prevalence=p),), ratio, "latency ratio", True)
    if test_id == "S6":
        p = 0.25 * k / CARRY_R_PER_P
        return Planting((bh.s6_overnight_carry(p, prevalence=0.5),), 0.25 * k, "R", True)
    raise ValueError(f"unknown test {test_id}")


# Research Spec v1.0 §9 core library, less S12 (its truth is the noise class).
TEST_IDS = (
    *("B1", "B2", "B5", "B12"),
    *("R1", "R2", "R7", "R8", "R11"),
    *("E2", "E4'", "E5"),
    *("S1", "S5", "S6", "S10", "S11"),
)


def grid() -> list[Cell]:
    cells = [(t, k, n) for t in TEST_IDS for k in MULTIPLES for n in LENGTHS]
    return [Cell(i, t, k, n) for i, (t, k, n) in enumerate(cells)]


def planted_seed(cell: Cell, replicate: int) -> int:
    return 1_000_000 + cell.index * 100 + replicate


def null_seed(kind: str, i: int) -> int:
    return (2_000_000 if kind == "clean_null" else 3_000_000) + i


def standin_regime(bars: Bars) -> np.ndarray:
    """A point-in-time stand-in for the fund's regime labels, used only to plant S5.

    A day is "stress" when the previous day's high-low range was above the median
    of the 20 days before it, "calm" otherwise; every bar takes its day's label.
    """
    starts = np.flatnonzero(np.diff(bars.day, prepend=-1))
    rng_day = np.maximum.reduceat(bars.high, starts) - np.minimum.reduceat(bars.low, starts)
    label = np.full(len(starts), "calm", dtype=object)
    for d in range(21, len(starts)):
        if rng_day[d - 1] > np.median(rng_day[d - 21 : d - 1]):
            label[d] = "stress"
    return label[np.searchsorted(bars.day[starts], bars.day)]


EXPIRY_DAY = 19


def contract_expiry(d: date) -> date:
    """The MCX CRUDEOIL future a trip on date ``d`` is given (a convention, see export).

    Expires on the 19th: of ``d``'s month when ``d`` is on or before the 19th,
    otherwise of the next month.
    """
    if d.day <= EXPIRY_DAY:
        return d.replace(day=EXPIRY_DAY)
    first_next = (d.replace(day=1) + timedelta(days=32)).replace(day=1)
    return first_next.replace(day=EXPIRY_DAY)


def _carry_allowed(history: MarketHistory) -> np.ndarray:
    """The series' own carry rule, plus: never carry a position across its contract's expiry.

    A trip keeps its entry contract (export), so holding it into a day that belongs to
    the next contract would exit after the contract had expired.
    """
    dates = history.dates
    same = [contract_expiry(a) == contract_expiry(b) for a, b in pairwise(dates)]
    return np.asarray(history.carry_allowed, dtype=bool) & np.append(np.array(same, bool), False)


@dataclass(frozen=True)
class Market:
    """One price series plus everything the generator precomputes from it once."""

    history: MarketHistory
    weekdays: np.ndarray
    regime: np.ndarray
    cutoffs: np.ndarray
    carry_allowed: np.ndarray

    @classmethod
    def of(cls, history: MarketHistory) -> Market:
        return cls(
            history=history,
            weekdays=np.array([d.weekday() for d in history.dates]),
            regime=standin_regime(history.bars),
            cutoffs=volatility_cutoffs(history.bars),
            carry_allowed=_carry_allowed(history),
        )

    @property
    def n_days(self) -> int:
        return len(self.history.dates)


def _start_day(rng: np.random.Generator, market: Market, n_trades: int) -> int:
    need = n_trades // 2 + 60  # ~2+ trips a day, with room for carry and slow traders
    if need >= market.n_days:
        raise ValueError(f"the series is too short for a {n_trades}-trip history")
    return int(rng.integers(0, market.n_days - need))


def _simulate(
    market: Market,
    seed: int,
    n: int,
    cfg: TraderConfig,
    start: int,
    behaviours: tuple[Behaviour, ...],
) -> tuple[Trip, ...]:
    h = market.history
    trips = simulate_trader(
        h.bars,
        seed,
        n,
        config=cfg,
        start_day=start,
        behaviours=behaviours,
        weekdays=market.weekdays,
        regime=market.regime,
        carry_allowed=market.carry_allowed,
        vol_cutoffs=market.cutoffs,
    )
    return tuple(trips)


def _money(trips: tuple[Trip, ...]) -> float:
    return sum(t.r_multiple * t.size for t in trips)


def planted_history(market: Market, cell: Cell, replicate: int) -> SyntheticHistory:
    seed = planted_seed(cell, replicate)
    start = _start_day(np.random.default_rng(seed), market, cell.n_trades)
    planting = _plant(cell.test_id, cell.multiple)
    cfg = TraderConfig()
    trips = _simulate(market, seed, cell.n_trades, cfg, start, planting.behaviours)
    twin = _simulate(market, seed, cell.n_trades, cfg, start, ())
    truth = {
        "avoidable_cost_r": _money(twin) - _money(trips),
        "n_flagged": float(sum(bool(t.flags) for t in trips)),
        "n_applied": float(sum(bool(t.applied) for t in trips)),
        "start_day": float(start),
    }
    return SyntheticHistory("planted", seed, cell.n_trades, trips, cell, planting, twin, truth)


def _null_config(rng: np.random.Generator) -> TraderConfig:
    """A different, plausible trading style per adversarial null trader."""
    return TraderConfig(
        trades_per_day=float(rng.uniform(1.5, 6.0)),
        stop_atr=float(rng.uniform(2.0, 5.0)),
        target_r=float(rng.uniform(1.0, 3.0)),
        hold_median_min=float(rng.uniform(15.0, 120.0)),
        rate_wave=float(rng.uniform(0.3, 0.8)),
        rate_period_days=float(rng.uniform(40.0, 250.0)),
        rate_phase=float(rng.uniform(0.0, 2 * np.pi)),
    )


def adversarial_null(market: Market, i: int) -> SyntheticHistory:
    seed = null_seed("adversarial_null", i)
    n = LENGTHS[i % len(LENGTHS)]
    rng = np.random.default_rng(seed)
    cfg = _null_config(rng)
    start = _start_day(rng, market, n)
    trips = _simulate(market, seed, n, cfg, start, ())
    return SyntheticHistory("adversarial_null", seed, n, trips, truth={"start_day": float(start)})


def synthetic_market(seed: int, n_days: int, clustering: bool = False) -> Market:
    """A seeded random-walk market with calendar dates, weekdays Monday to Friday."""
    bars = generate_bars(seed, n_days, MarketConfig(vol_clustering=clustering))
    dates: list[date] = []
    d = date(2020, 1, 6)  # a Monday
    while len(dates) < n_days:
        if d.weekday() < 5:
            dates.append(d)
        d += timedelta(days=1)
    carry = np.arange(n_days) < n_days - 1
    report = LoadReport(
        source_sha256="synthetic", rows=len(bars.close), repaired_bars=0, carry_blocked_days=()
    )
    history = MarketHistory(bars=bars, dates=tuple(dates), carry_allowed=carry, report=report)
    return Market.of(history)


def clean_null(i: int) -> SyntheticHistory:
    seed = null_seed("clean_null", i)
    n = LENGTHS[i % len(LENGTHS)]
    market = synthetic_market(seed, n // 2 + 120)
    trips = _simulate(market, seed, n, TraderConfig(), 0, ())
    return SyntheticHistory("clean_null", seed, n, trips, market=market)
