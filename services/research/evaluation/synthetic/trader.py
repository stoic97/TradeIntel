"""The base trader: a plain, flaw-free policy that the seventeen behaviours modify.

Research Spec v1.0 §12.2: "a base policy with a tunable edge". This is that policy,
and with no behaviours passed in, nothing else. Each trade:

* **Entry.** Each day the number of entry attempts is Poisson(``trades_per_day``);
  attempt minutes are uniform over the day's bars, excluding the last
  ``no_entry_last_min`` minutes. An attempt while a position is open is skipped -
  one position at a time. Entry is at the open of the chosen bar.
* **Direction.** With probability ``skill`` the trader takes the side the price
  actually moves over the next ``skill_horizon`` bars; otherwise a fair coin. The
  edge is therefore real - it comes from the price path, not from adding R to the
  outcome. ``skill=0`` is a zero-edge trader.
* **Risk.** Stop distance = ``stop_atr`` x ATR, where ATR is the mean high-low range
  of the ``atr_bars`` bars *before* the entry bar - point-in-time (§4.3). One R is
  that distance per unit. Target at ``target_r`` R.
* **Exit.** The first of: stop, target, or the close of the bar at the end of a
  log-normal holding time (median ``hold_median_min``), capped at the day's last
  bar. The base trader never carries overnight; S6 adds that later. If one bar
  touches both stop and target, the stop is assumed first (conservative) and the
  trip is flagged ``ambiguous``. A stop gapped through between bars fills at that
  bar's open, so a loss can exceed 1R.

Randomness comes from four independent streams spawned from the seed (entries,
direction, holding, behaviour). Every stream is drawn once per entry attempt,
taken or skipped, so a history run with and without a behaviour stays paired
draw-for-draw - that pairing is what the twin run (§12.2) needs to measure the
true avoidable cost. With no behaviours the trader is exactly the base policy.

**The three hooks (§12.2).** The seventeen planted behaviours reduce to three
mechanisms, each switched on by a condition flag evaluated on what the trader
knew at entry (resolved trips only):

* ``DRIFT`` - with probability ``strength`` the trader takes the side *against*
  the realised move (chasing, revenge entries). The worse result comes from the
  price path, exactly as skill's better result does.
* ``SIZE`` - position size is multiplied by ``strength``. R per unit is untouched;
  money at risk is not.
* ``EXIT`` - winners are cut early: at ``strength`` x the planned holding time, a
  trip that is in profit is closed. Losers run to the planned exit.

``prevalence`` is the probability the behaviour acts when its condition holds.
Each trip records ``flags`` (conditions true at entry) and ``applied`` (behaviours
that acted) - the ground truth that recall is scored against.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import astuple, dataclass, replace
from enum import Enum

import numpy as np

from services.research.evaluation.synthetic.market import Bars

LONG, SHORT = 1, -1


@dataclass(frozen=True)
class TraderConfig:
    trades_per_day: float = 3.0
    skill: float = 0.0
    skill_horizon: int = 30
    stop_atr: float = 3.0
    atr_bars: int = 30
    target_r: float = 2.0
    hold_median_min: float = 45.0
    hold_sigma: float = 0.8
    no_entry_last_min: int = 30


class Mechanism(str, Enum):
    DRIFT = "DRIFT"
    SIZE = "SIZE"
    EXIT = "EXIT"


@dataclass(frozen=True)
class Trip:
    entry_idx: int  # index into Bars
    exit_idx: int
    day: int
    direction: int  # LONG or SHORT
    entry_price: float
    exit_price: float
    stop_price: float
    target_price: float
    risk_per_unit: float  # 1R, in price points
    r_multiple: float
    exit_reason: str  # STOP | TARGET | TIME
    ambiguous: bool
    size: float = 1.0  # units; P&L = r_multiple x risk_per_unit x size
    flags: tuple[str, ...] = ()  # behaviour conditions true at entry
    applied: tuple[str, ...] = ()  # behaviours that acted on this trip


@dataclass(frozen=True)
class EntryState:
    """What the trader knows at the moment of an entry attempt - nothing later."""

    bar: int
    day: int
    history: tuple[Trip, ...]  # every resolved trip, oldest first
    today: tuple[Trip, ...]  # resolved trips of the current day, oldest first
    minute: int = 0  # minutes since midnight IST of the entry bar
    weekday: int = 0  # 0 = Monday
    atr: float = 0.0  # mean high-low of the atr_bars bars before entry
    vol_tercile: int = 1  # 0 low, 1 mid, 2 high: atr against the previous 5 days' bars
    n_planned: int = 0  # length of the history being generated
    regime: str | None = None  # market regime label at the entry bar, where supplied


@dataclass(frozen=True)
class Behaviour:
    test_id: str
    mechanism: Mechanism
    condition: Callable[[EntryState], bool]
    strength: float
    prevalence: float = 1.0


def trips_hash(trips: list[Trip]) -> str:
    h = hashlib.sha256()
    for t in trips:
        h.update(repr(astuple(t)).encode())
    return h.hexdigest()


def _validate(cfg: TraderConfig, seed: int, n_trades: int) -> None:
    if seed < 0:
        raise ValueError("seed must be a non-negative integer")
    if n_trades < 1:
        raise ValueError("n_trades must be at least 1")
    if not 0.0 <= cfg.skill <= 1.0:
        raise ValueError("skill must be in [0, 1]")
    if cfg.trades_per_day <= 0 or cfg.stop_atr <= 0 or cfg.target_r <= 0:
        raise ValueError("trades_per_day, stop_atr and target_r must be positive")


def _day_bounds(bars: Bars) -> tuple[np.ndarray, np.ndarray]:
    """First and one-past-last bar index of each trading day."""
    starts = np.flatnonzero(np.diff(bars.day, prepend=-1))
    ends = np.append(starts[1:], len(bars.day))
    return starts, ends


VOL_LOOKBACK_DAYS = 5


def _vol_cutoffs(rng_hl: np.ndarray, starts: np.ndarray, ends: np.ndarray, n: int) -> np.ndarray:
    """Per day, the 33rd and 67th percentile of bar ATR over the previous 5 days.

    Point-in-time: day d's cutoffs use only bars of days d-5 .. d-1. Day 0 has no
    past, so its cutoffs are NaN and every entry on it is the middle tercile.
    """
    cs = np.concatenate([[0.0], np.cumsum(rng_hl)])
    atr = np.full(len(rng_hl), np.nan)
    atr[n:] = (cs[n:-1] - cs[: -n - 1]) / n
    cut = np.full((len(starts), 2), np.nan)
    for d in range(1, len(starts)):
        lo = starts[max(0, d - VOL_LOOKBACK_DAYS)]
        past = atr[lo : ends[d - 1]]
        past = past[~np.isnan(past)]
        if len(past):
            cut[d] = np.percentile(past, [100 / 3, 200 / 3])
    return cut


def _tercile(atr: float, cut: np.ndarray) -> int:
    if np.isnan(cut[0]):
        return 1
    return int(atr > cut[0]) + int(atr > cut[1])


def _validate_behaviours(behaviours: tuple[Behaviour, ...]) -> None:
    for b in behaviours:
        if not 0.0 <= b.prevalence <= 1.0:
            raise ValueError(f"{b.test_id}: prevalence must be in [0, 1]")
        if b.mechanism is Mechanism.DRIFT and not 0.0 <= b.strength <= 1.0:
            raise ValueError(f"{b.test_id}: DRIFT strength is a probability in [0, 1]")
        if b.mechanism is not Mechanism.DRIFT and b.strength <= 0:
            raise ValueError(f"{b.test_id}: SIZE and EXIT strength must be positive")


def simulate_trader(
    bars: Bars,
    seed: int,
    n_trades: int,
    config: TraderConfig | None = None,
    start_day: int = 0,
    behaviours: tuple[Behaviour, ...] = (),
    weekdays: np.ndarray | None = None,
    regime: np.ndarray | None = None,
) -> list[Trip]:
    """Generate ``n_trades`` trips.

    ``weekdays`` (per trading day, 0 = Monday) comes from the calendar dates of a
    real series; synthetic bars default to Monday..Friday in turn. ``regime`` (per
    bar) is a market regime label, required only by behaviours that read it.
    """
    cfg = config or TraderConfig()
    _validate(cfg, seed, n_trades)
    _validate_behaviours(behaviours)
    entries_rng, direction_rng, hold_rng, behaviour_rng = (
        np.random.Generator(np.random.PCG64(s))
        for s in np.random.SeedSequence(seed).spawn(4)
    )
    starts, ends = _day_bounds(bars)
    rng_hl = bars.high - bars.low
    if weekdays is None:
        weekdays = np.arange(len(starts)) % 5
    if len(weekdays) != len(starts):
        raise ValueError("weekdays must have one entry per trading day")
    if regime is not None and len(regime) != len(bars.day):
        raise ValueError("regime must have one label per bar")
    cutoffs = _vol_cutoffs(rng_hl, starts, ends, cfg.atr_bars) if behaviours else np.empty((0, 2))

    trips: list[Trip] = []
    for d in range(start_day, len(starts)):
        lo, hi = int(starts[d]), int(ends[d])
        last_entry = hi - cfg.no_entry_last_min
        if last_entry <= lo:
            continue
        k = int(entries_rng.poisson(cfg.trades_per_day))
        attempts = np.sort(entries_rng.integers(lo, last_entry, size=k))
        flat_from = lo
        today: list[Trip] = []
        for i in attempts:
            i = int(i)
            # Draws are taken for every attempt, taken or skipped, so streams stay paired.
            coin = direction_rng.random(2)
            z = hold_rng.standard_normal()
            hold = int(np.ceil(cfg.hold_median_min * np.exp(cfg.hold_sigma * z)))
            acts = behaviour_rng.random(2 * len(behaviours))
            if i < flat_from or i < cfg.atr_bars:
                continue
            state = EntryState(bar=i, day=d, history=tuple(trips), today=tuple(today))
            if behaviours:
                atr = float(rng_hl[i - cfg.atr_bars : i].mean())
                state = replace(
                    state,
                    minute=int(bars.minute[i]),
                    weekday=int(weekdays[d]),
                    atr=atr,
                    vol_tercile=_tercile(atr, cutoffs[d]),
                    n_planned=n_trades,
                    regime=None if regime is None else str(regime[i]),
                )
            flags, applied = [], []
            for n, b in enumerate(behaviours):
                if b.condition(state):
                    flags.append(b)
                    if acts[2 * n] < b.prevalence:
                        applied.append((b, acts[2 * n + 1]))
            trip = _one_trip(bars, rng_hl, cfg, i, hi, coin, hold, d, applied)
            trip = replace(
                trip,
                flags=tuple(b.test_id for b in flags),
                applied=tuple(b.test_id for b, _ in applied),
            )
            trips.append(trip)
            today.append(trip)
            flat_from = trip.exit_idx + 1
            if len(trips) == n_trades:
                return trips
    raise ValueError(
        f"history ran out after {len(trips)} of {n_trades} trades - use more days or a later start"
    )


def _one_trip(
    bars: Bars,
    rng_hl: np.ndarray,
    cfg: TraderConfig,
    i: int,
    day_end: int,
    coin: np.ndarray,
    hold: int,
    d: int,
    applied: list[tuple[Behaviour, float]],
) -> Trip:
    entry = float(bars.open[i])
    future = bars.close[min(i + cfg.skill_horizon, day_end - 1)]
    with_move = LONG if future >= entry else SHORT
    if coin[0] < cfg.skill:
        direction = with_move
    else:
        direction = LONG if coin[1] < 0.5 else SHORT

    size, early = 1.0, None
    for b, u in applied:
        if b.mechanism is Mechanism.DRIFT and u < b.strength:
            direction = -with_move
        elif b.mechanism is Mechanism.SIZE:
            size *= b.strength
        elif b.mechanism is Mechanism.EXIT:
            early = b.strength

    atr = float(rng_hl[i - cfg.atr_bars : i].mean())
    risk = cfg.stop_atr * atr
    stop = entry - direction * risk
    target = entry + direction * cfg.target_r * risk

    last = min(i + hold, day_end - 1)
    window = slice(i, last + 1)
    if direction == LONG:
        hit_stop = bars.low[window] <= stop
        hit_tgt = bars.high[window] >= target
    else:
        hit_stop = bars.high[window] >= stop
        hit_tgt = bars.low[window] <= target
    j_stop = int(np.argmax(hit_stop)) if hit_stop.any() else None
    j_tgt = int(np.argmax(hit_tgt)) if hit_tgt.any() else None

    if early is not None:
        e = min(i + int(np.ceil(hold * early)), last) - i
        first_hit = min(x for x in (j_stop, j_tgt, last - i + 1) if x is not None)
        if e < first_hit and direction * (bars.close[i + e] - entry) > 0:
            j_stop = j_tgt = None
            last = i + e

    ambiguous = False
    if j_stop is not None and (j_tgt is None or j_stop <= j_tgt):
        ambiguous = j_stop == j_tgt
        j = i + j_stop
        gap_open = float(bars.open[j])
        exit_price = min(gap_open, stop) if direction == LONG else max(gap_open, stop)
        reason = "STOP"
    elif j_tgt is not None:
        j = i + j_tgt
        exit_price = target
        reason = "TARGET"
    else:
        j = last
        exit_price = float(bars.close[j])
        reason = "TIME"

    r = direction * (exit_price - entry) / risk
    return Trip(
        entry_idx=i,
        exit_idx=j,
        day=d,
        direction=direction,
        entry_price=entry,
        exit_price=exit_price,
        stop_price=stop,
        target_price=target,
        risk_per_unit=risk,
        r_multiple=r,
        exit_reason=reason,
        ambiguous=ambiguous,
        size=size,
    )
