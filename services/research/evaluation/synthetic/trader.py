"""The base trader: a plain, flaw-free policy that the seventeen behaviours modify.

Research Spec v1.0 §12.2: "a base policy with a tunable edge". This is that policy,
and nothing else - no behaviour is planted here. Each trade:

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

Randomness comes from three independent streams spawned from the seed (entries,
direction, holding). The behaviours added in cycle 3 change decisions, not the
streams, so a history run with and without a behaviour stays paired draw-for-draw
- that pairing is what the twin run (§12.2) needs to measure true avoidable cost.
"""

from __future__ import annotations

import hashlib
from dataclasses import astuple, dataclass

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


def simulate_trader(
    bars: Bars,
    seed: int,
    n_trades: int,
    config: TraderConfig | None = None,
    start_day: int = 0,
) -> list[Trip]:
    cfg = config or TraderConfig()
    _validate(cfg, seed, n_trades)
    entries_rng, direction_rng, hold_rng = (
        np.random.Generator(np.random.PCG64(s))
        for s in np.random.SeedSequence(seed).spawn(3)
    )
    starts, ends = _day_bounds(bars)
    rng_hl = bars.high - bars.low

    trips: list[Trip] = []
    for d in range(start_day, len(starts)):
        lo, hi = int(starts[d]), int(ends[d])
        last_entry = hi - cfg.no_entry_last_min
        if last_entry <= lo:
            continue
        k = int(entries_rng.poisson(cfg.trades_per_day))
        attempts = np.sort(entries_rng.integers(lo, last_entry, size=k))
        flat_from = lo
        for i in attempts:
            i = int(i)
            # Draws are taken for every attempt, taken or skipped, so streams stay paired.
            coin = direction_rng.random(2)
            z = hold_rng.standard_normal()
            hold = int(np.ceil(cfg.hold_median_min * np.exp(cfg.hold_sigma * z)))
            if i < flat_from or i < cfg.atr_bars:
                continue
            trip = _one_trip(bars, rng_hl, cfg, i, hi, coin, hold, d)
            trips.append(trip)
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
) -> Trip:
    entry = float(bars.open[i])
    if coin[0] < cfg.skill:
        future = bars.close[min(i + cfg.skill_horizon, day_end - 1)]
        direction = LONG if future >= entry else SHORT
    else:
        direction = LONG if coin[1] < 0.5 else SHORT

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
    )
