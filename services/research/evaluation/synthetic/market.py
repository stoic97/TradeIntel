"""Synthetic market layer: seeded one-minute bars for one instrument.

Research Spec v1.0 §12.2 puts the fund's MCX crude history under the generator.
This module is the seeded stand-in used by fast unit tests; the real crude series
(data/market/, logged in CROSSINGS.md) is loaded into the same ``Bars`` shape, so
the rest of the generator never knows which one it is trading on.

Time is a trading-day index plus minutes since midnight IST. Calendar dates and
timezone-aware timestamps are attached only when histories are written out as
CTR, so this layer has no wall clock in it (Methodology §2 Rule 2).

Determinism: same seed + same numpy (pinned by uv.lock) -> same bytes. A numpy
version change can alter the stream and is a charged change (ADR 004).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np

SESSION_OPEN_MIN = 9 * 60  # 09:00 IST
SESSION_CLOSE_MIN = 23 * 60 + 30  # 23:30 IST
BARS_PER_DAY = SESSION_CLOSE_MIN - SESSION_OPEN_MIN


@dataclass(frozen=True)
class MarketConfig:
    """Shape of the synthetic path. Defaults are round numbers, not calibrated."""

    start_price: float = 6000.0
    bar_vol: float = 0.0006  # per-minute log-return sd; ~1.8% a day
    overnight_vol: float = 0.008  # gap between one day's close and the next open
    vol_clustering: bool = False  # GARCH(1,1) when True (adversarial null class)
    garch_alpha: float = 0.08
    garch_beta: float = 0.90
    wick: float = 0.3  # high/low extension, as a fraction of bar_vol


@dataclass(frozen=True)
class Bars:
    day: np.ndarray  # trading-day index, 0..n_days-1
    minute: np.ndarray  # minutes since midnight IST
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray

    def content_hash(self) -> str:
        h = hashlib.sha256()
        for arr in (self.day, self.minute, self.open, self.high, self.low, self.close):
            h.update(np.ascontiguousarray(arr).tobytes())
        return h.hexdigest()


def _bar_vols(z: np.ndarray, cfg: MarketConfig) -> np.ndarray:
    """Per-bar volatility: constant, or GARCH(1,1) with the same long-run level."""
    n = len(z)
    if not cfg.vol_clustering:
        return np.full(n, cfg.bar_vol)
    omega = cfg.bar_vol**2 * (1.0 - cfg.garch_alpha - cfg.garch_beta)
    var = np.empty(n)
    var[0] = cfg.bar_vol**2
    for i in range(1, n):
        var[i] = omega + cfg.garch_alpha * var[i - 1] * z[i - 1] ** 2 + cfg.garch_beta * var[i - 1]
    return np.sqrt(var)


def generate_bars(seed: int, n_days: int, config: MarketConfig | None = None) -> Bars:
    if seed < 0:
        raise ValueError("seed must be a non-negative integer")
    if n_days < 1:
        raise ValueError("n_days must be at least 1")
    cfg = config or MarketConfig()
    rng = np.random.Generator(np.random.PCG64(seed))

    n = n_days * BARS_PER_DAY
    z = rng.standard_normal(n)
    vol = _bar_vols(z, cfg)
    ret = vol * z

    # The first bar of each day after the first carries the overnight gap.
    day = np.repeat(np.arange(n_days, dtype=np.int64), BARS_PER_DAY)
    day_start = np.arange(1, n_days) * BARS_PER_DAY
    ret[day_start] += cfg.overnight_vol * rng.standard_normal(n_days - 1)

    close = cfg.start_price * np.exp(np.cumsum(ret))
    open_ = np.empty(n)
    open_[0] = cfg.start_price
    open_[1:] = close[:-1]

    wick = cfg.wick * vol * np.abs(rng.standard_normal((2, n)))
    high = np.maximum(open_, close) * np.exp(wick[0])
    low = np.minimum(open_, close) * np.exp(-wick[1])

    minute = np.tile(np.arange(SESSION_OPEN_MIN, SESSION_CLOSE_MIN, dtype=np.int64), n_days)
    return Bars(day=day, minute=minute, open=open_, high=high, low=low, close=close)
