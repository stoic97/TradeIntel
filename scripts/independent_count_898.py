"""TICKET-898: an independent count of the prior-minute figure.

Written from docs/trade_dna_research_spec_v1_0.md s4.7 and the raw 1-minute bars only.
It does not import, and was not written from, services/production/mirror/prior_minute.py
(TICKET-891): the value of a second count is that its mistakes are its own.

  s4.7.2  bars are stamped at the START of their minute; a stamp off the minute is refused.
  s4.7.5  a bar is asked where the price WAS at the edge of a minute, never what it DID inside
          one. Entry t lies in minute m0 (t floored to the minute).
  s4.7.9  the minute before entry is bar m0 - 1, read as its own open to its own close (ruling
          on TICKET-898, D2). The close-to-close reading, close(m0 - 2) to close(m0 - 1), is
          reported beside it as a sensitivity only.
  after   "+N after entry" runs from the close of the entry-minute bar (bar m0) to the close of
          bar m0 + N (ruling on TICKET-898, D1); anything earlier counts seconds before entry.
  s4.7.3  one series per underlying; MCX_CRUDEOIL and MCX_CRUDEOILM share one.
  s4.7.6  no series, a date the series does not cover, or a missing bar makes a trip
          unmeasured. The nearest bar is never used. A count drops a trip only when a bar that
          count needs is missing, and the reason names the bar (ruling D3): the prior count
          needs bar m0 - 1; a +N count needs bar m0 and bar m0 + N.
  s4.7.7  the direction table, written here from the spec's words (not imported).
  s4.7.8  a multi-leg position has no single direction: unmeasured, and counted.

A trip's unmeasured reason is the first check it fails, in this order: direction, series,
coverage, then bars (for a +N count: the entry-minute bar, then the bar at the horizon). A move
of exactly zero is "flat": measured, neither with nor against.

Run locally only; never commit its output for a real trader (README rule 1).
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ONE_MIN = timedelta(minutes=1)
IST = timezone(timedelta(hours=5, minutes=30))
HORIZONS = (5, 15, 30, 60)
LONG, SHORT, NONE = 1, -1, 0

UNDERLYING = {
    "MCX_CRUDEOIL": "CRUDE",
    "MCX_CRUDEOILM": "CRUDE",
    "MCX_GOLD": "GOLD",
    "MCX_GOLDM": "GOLD",
}

WITH, AGAINST, FLAT = "with", "against", "flat"
MEASURED = (WITH, AGAINST, FLAT)
NO_DIRECTION = "no_single_direction"
NO_SERIES = "no_series_for_underlying"
NOT_COVERED = "series_does_not_cover"
MISSING_PRIOR_BAR = "missing_prior_bar"
MISSING_ENTRY_BAR = "missing_entry_minute_bar"
MISSING_HORIZON_BAR = "missing_horizon_bar"


def direction(kind: str, side: str) -> int:
    """s4.7.7. kind: CALL | PUT | FUT | STOCK | MULTI; side: BUY | SELL."""
    kind, side = kind.upper(), side.upper()
    if kind == "MULTI":
        return NONE
    if side not in ("BUY", "SELL"):
        raise ValueError(f"side must be BUY or SELL, got {side!r}")
    bought = side == "BUY"
    if kind in ("FUT", "STOCK", "CALL"):
        return LONG if bought else SHORT
    if kind == "PUT":
        return SHORT if bought else LONG
    raise ValueError(f"unknown kind {kind!r}")


@dataclass(frozen=True)
class Trip:
    trip_id: str
    profile: str
    kind: str
    side: str
    entry: datetime


class Series:
    """1-minute bars keyed by START-of-minute stamp, value (open, close)."""

    def __init__(self, bars: dict[datetime, tuple[float, float]]) -> None:
        if not bars:
            raise ValueError("empty series")
        for stamp in bars:
            if stamp.second or stamp.microsecond:
                raise ValueError(f"bar stamp {stamp} is not on a minute (s4.7.2)")
        self._bars = bars
        self.first_day: date = min(bars).date()
        self.last_day: date = max(bars).date()

    def covers(self, day: date) -> bool:
        return self.first_day <= day <= self.last_day

    def price_at_edge(self, edge: datetime) -> float | None:
        bar = self._bars.get(edge - ONE_MIN)
        return None if bar is None else bar[1]

    def bar(self, stamp: datetime) -> tuple[float, float] | None:
        return self._bars.get(stamp)


def _parse(raw: str) -> datetime:
    stamp = datetime.fromisoformat(raw.strip().replace("T", " "))
    if stamp.tzinfo is not None:
        stamp = stamp.astimezone(IST).replace(tzinfo=None)
    return stamp


def load_series(path: Path) -> Series:
    bars: dict[datetime, tuple[float, float]] = {}
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        cols = {c.lower().strip(): c for c in reader.fieldnames or []}
        stamp_col = next(
            (cols[c] for c in ("datetime", "timestamp", "date_time", "time") if c in cols), None
        )
        date_col = cols.get("date")
        if stamp_col is None and date_col is None:
            raise ValueError(f"no timestamp column in {list(cols)}")
        for row in reader:
            if stamp_col is not None and stamp_col.lower() == "time" and date_col is not None:
                raw = f"{row[date_col]} {row[stamp_col]}"
            elif stamp_col is not None:
                raw = row[stamp_col]
            else:
                raw = row[date_col]  # type: ignore[index]
            stamp = _parse(raw)
            if stamp in bars:
                raise ValueError(f"duplicate bar {stamp}")
            bars[stamp] = (float(row[cols["open"]]), float(row[cols["close"]]))
    return Series(bars)


def load_trips(path: Path) -> list[Trip]:
    """Simple trips CSV: trip_id,profile,kind,side,entry (entry IST)."""
    with open(path, newline="", encoding="utf-8") as fh:
        return [
            Trip(r["trip_id"], r["profile"], r["kind"], r["side"], _parse(r["entry"]))
            for r in csv.DictReader(fh)
        ]


@dataclass
class Tally:
    per_trip: dict[str, str] = field(default_factory=dict)

    def _n(self, outcome: str) -> int:
        return sum(1 for o in self.per_trip.values() if o == outcome)

    @property
    def with_(self) -> int:
        return self._n(WITH)

    @property
    def against(self) -> int:
        return self._n(AGAINST)

    @property
    def flat(self) -> int:
        return self._n(FLAT)

    @property
    def measured(self) -> int:
        return self.with_ + self.against + self.flat

    @property
    def unmeasured(self) -> Counter[str]:
        return Counter(o for o in self.per_trip.values() if o not in MEASURED)


@dataclass
class Result:
    total: int
    prior: Tally
    prior_close_close: Tally
    after: dict[int, Tally]


def _outcome(d: int, move: float) -> str:
    s = (move > 0) - (move < 0)
    if s == 0:
        return FLAT
    return WITH if s == d else AGAINST


def count(
    trips: list[Trip],
    series_by_underlying: dict[str, Series],
    horizons: tuple[int, ...] = HORIZONS,
) -> Result:
    prior, alt = Tally(), Tally()
    after = {h: Tally() for h in horizons}
    for trip in trips:
        tid = trip.trip_id
        if tid in prior.per_trip:
            raise ValueError(f"duplicate trip id {tid}")
        d = direction(trip.kind, trip.side)
        series = series_by_underlying.get(UNDERLYING.get(trip.profile.upper(), ""))
        reason = None
        if d == NONE:
            reason = NO_DIRECTION
        elif series is None:
            reason = NO_SERIES
        elif not series.covers(trip.entry.date()):
            reason = NOT_COVERED
        if reason is not None or series is None:
            for tally in (prior, alt, *after.values()):
                tally.per_trip[tid] = reason or NO_SERIES
            continue
        m0 = trip.entry.replace(second=0, microsecond=0)
        # The minute before entry: bar m0 - 1, its own open to its own close (ruling D2).
        prior_bar = series.bar(m0 - ONE_MIN)
        prior.per_trip[tid] = (
            MISSING_PRIOR_BAR if prior_bar is None else _outcome(d, prior_bar[1] - prior_bar[0])
        )
        # Sensitivity only: close(m0 - 2) to close(m0 - 1), the s4.7.5 close-to-close reading.
        p0 = series.price_at_edge(m0)
        pm1 = series.price_at_edge(m0 - ONE_MIN)
        alt.per_trip[tid] = (
            MISSING_PRIOR_BAR if p0 is None or pm1 is None else _outcome(d, p0 - pm1)
        )
        # After entry: close of the entry-minute bar to the close of bar m0 + h (ruling D1).
        entry_bar = series.bar(m0)
        for h, tally in after.items():
            if entry_bar is None:
                tally.per_trip[tid] = MISSING_ENTRY_BAR
                continue
            later = series.bar(m0 + h * ONE_MIN)
            tally.per_trip[tid] = (
                MISSING_HORIZON_BAR if later is None else _outcome(d, later[1] - entry_bar[1])
            )
    result = Result(len(trips), prior, alt, after)
    for t in (prior, alt, *after.values()):
        assert t.measured + sum(t.unmeasured.values()) == result.total
    return result


def _line(name: str, t: Tally, total: int) -> str:
    share = f"{t.with_ / t.measured:.1%}" if t.measured else "n/a"
    reasons = ", ".join(f"{k}={v}" for k, v in sorted(t.unmeasured.items())) or "-"
    return (
        f"{name:<26} with {t.with_:>6} ({share:>6})  against {t.against:>6}  flat {t.flat:>6}"
        f"  measured {t.measured:>6} of {total}  | unmeasured: {reasons}"
    )


def report(r: Result) -> str:
    lines = ["TICKET-898 independent count (spec s4.7)", _line("prior minute", r.prior, r.total)]
    lines += [_line(f"+{h} after entry", t, r.total) for h, t in sorted(r.after.items())]
    lines.append(_line("sens: close->close", r.prior_close_close, r.total))
    return "\n".join(lines)


def write_per_trip(r: Result, path: Path) -> None:
    keys = sorted(r.prior.per_trip)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["trip_id", "prior", "prior_close_close", *[f"plus_{h}" for h in r.after]])
        for k in keys:
            row = [k, r.prior.per_trip[k], r.prior_close_close.per_trip[k]]
            w.writerow(row + [t.per_trip[k] for t in r.after.values()])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--bars", type=Path, required=True, help="1-minute crude CSV")
    ap.add_argument("--trips", type=Path, required=True, help="trip_id,profile,kind,side,entry")
    ap.add_argument("--per-trip", type=Path, help="write per-trip outcomes (keep OUTSIDE git)")
    a = ap.parse_args()
    r = count(load_trips(a.trips), {"CRUDE": load_series(a.bars)})
    print(report(r))
    if a.per_trip:
        write_per_trip(r, a.per_trip)


if __name__ == "__main__":
    main()