"""Load the real MCX crude 1-minute series into the generator's ``Bars`` shape.

The file crossed from the fund under ADR 002 and is recorded in
``data/market/CROSSINGS.md``. It is gitignored; only its hash lives in the repo
(``CRUDE_1M_SHA256``), and the loader refuses any file that does not match it, so
every synthetic history is traceable to one exact price series (Methodology §2
Rule 1).

Two properties of the file are handled here, each counted, neither hidden:

* **Inconsistent bars.** ~600 of 1.58M bars have high/low that do not contain
  open/close (some with high and low swapped). The raw file is never edited; the
  loaded bar's high and low become the envelope of its four prices, and the count
  is reported in ``LoadReport.repaired_bars``.
* **Stitched rolls.** The series is one continuous contract with monthly rolls
  stitched in, so a few overnight gaps are not market moves (21 Apr 2020 opens
  +79% on the previous close). No day is deleted - the intraday prices are real -
  but a synthetic trader may not carry a position across a gap larger than
  ``MAX_CARRY_GAP``. ``carry_allowed[d]`` is False for such days and for the last
  day.

Timestamps in the file are naive and are IST; they become a trading-day index and
minutes since midnight, as in ``market.Bars``. Real days have a variable number of
bars (short sessions, holidays), so nothing downstream may assume
``market.BARS_PER_DAY`` on real data.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from services.research.evaluation.synthetic.market import Bars

CRUDE_1M_SHA256 = "57e17bc53c728d43129f4c10a5ad1e6fd3dcf1a8b4ca2cc38eba88b51605519d"
MAX_CARRY_GAP = 0.10  # |next open / close - 1| above this blocks overnight carry


@dataclass(frozen=True)
class LoadReport:
    source_sha256: str
    rows: int
    repaired_bars: int
    carry_blocked_days: tuple[date, ...]


@dataclass(frozen=True)
class MarketHistory:
    bars: Bars
    dates: tuple[date, ...]  # dates[d] is the calendar date of trading-day index d
    carry_allowed: np.ndarray  # bool per day: may a position be held into the next day
    report: LoadReport


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_crude_1m(path: str | Path, verify_hash: bool = True) -> MarketHistory:
    path = Path(path)
    digest = _sha256(path)
    if verify_hash and digest != CRUDE_1M_SHA256:
        raise ValueError(
            f"sha256 of {path} is {digest}, not the {CRUDE_1M_SHA256} recorded in "
            "data/market/CROSSINGS.md - refusing a price series that is not the logged one"
        )

    df = pd.read_csv(path, dtype={"timestamp": str})
    ts = pd.to_datetime(df["timestamp"], format="%Y-%m-%d %H:%M:%S")
    if not ts.is_monotonic_increasing or ts.duplicated().any():
        raise ValueError("timestamps must be strictly increasing with no duplicates")

    o, h, lo, c = (df[k].to_numpy(dtype=np.float64) for k in ("open", "high", "low", "close"))
    if (np.minimum.reduce([o, h, lo, c]) <= 0).any():
        raise ValueError("prices must be positive")

    high = np.maximum.reduce([o, h, lo, c])
    low = np.minimum.reduce([o, h, lo, c])
    repaired = int(((high != h) | (low != lo)).sum())

    cal = ts.dt.date.to_numpy()
    dates, day = np.unique(cal, return_inverse=True)
    day = day.astype(np.int64)
    minute = (ts.dt.hour * 60 + ts.dt.minute).to_numpy(dtype=np.int64)

    last_close = np.zeros(len(dates))
    first_open = np.zeros(len(dates))
    last_close[day] = c  # rows are sorted, so the last write per day is its close
    first_open[day[::-1]] = o[::-1]  # and the last write in reverse is its open
    gap = np.abs(first_open[1:] / last_close[:-1] - 1.0)
    carry = np.append(gap <= MAX_CARRY_GAP, False)

    blocked = tuple(dates[i] for i in np.flatnonzero(~carry[:-1]))
    bars = Bars(day=day, minute=minute, open=o, high=high, low=low, close=c)
    report = LoadReport(
        source_sha256=digest, rows=len(df), repaired_bars=repaired, carry_blocked_days=blocked
    )
    return MarketHistory(bars=bars, dates=tuple(dates), carry_allowed=carry, report=report)
