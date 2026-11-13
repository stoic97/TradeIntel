"""Did the minute before his entry already agree with the trade, and what came after.

Two counts per trip, both against the underlying's 1-minute bars and both in the trip's own
direction (+1 gains when the underlying rises, -1 when it falls):

* **Before:** the minute that closed just before the entry minute. Its move is its own close
  less its own open, so nothing at or after the entry minute is read.
* **After:** from the close of the entry minute to the close of the minute ``h`` minutes later,
  for each ``h`` in ``HORIZONS``. Measuring from any earlier price would count the minute he
  bought in as skill.

A flat move agrees with neither side. Results are counts out of the trips that could be
measured: never a percentage with a trading word attached, never rupees. Nothing here prices
the behaviour, so there is no saving, avoided cost or per-trade effect to compute: a trader
with no edge who buys in the direction of the last minute reads exactly this way.

**The control.** Each count is recounted ``DRAWS`` times with the measured trips' directions
shuffled among them, and the middle 95% of those recounts is returned beside it as its band.
A count inside its band is not a finding: ``PriorMinute.ships`` is False and the fact shows
its state instead. A trader who only ever trades one way gets a band of width zero and so no
claim, because shuffling one direction can't tell him from chance.

**What the caller supplies.** The direction of each trip and the bars for each underlying
come in from outside: this module decides neither. A bar is labelled by the minute it starts,
in IST, and a trip is lined up only on the exact minutes it needs. Every trip that can't be
measured is counted out with its reason, never dropped.

Plain numpy, and nothing from ``services.research`` (methodology Rule 5).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Protocol
from zoneinfo import ZoneInfo

import numpy as np

IST = ZoneInfo("Asia/Kolkata")
HORIZONS = (5, 15, 30, 60)  # minutes after the entry minute's close
DRAWS = 2000
SEED = 20261112  # fixed, so one history always gets one band. Chosen once, before any real file.
BAND = (2.5, 97.5)  # percentiles of the shuffled counts


class Reason(str, Enum):
    """Why a trip could not be measured."""

    NO_SERIES = "no series for the underlying"
    NOT_COVERED = "the series does not cover the date"
    NO_PRIOR_BAR = "no bar for the minute before entry"
    NO_ENTRY_BAR = "no bar for the entry minute"
    NO_HORIZON_BAR = "no bar at the horizon"
    NO_DIRECTION = "no single direction"


@dataclass(frozen=True)
class Bar:
    open: float
    close: float


class MinuteBars(Protocol):
    """One underlying's 1-minute bars, each labelled by the minute it starts, in IST."""

    def covers(self, day: date) -> bool: ...

    def bar(self, minute: datetime) -> Bar | None: ...


@dataclass(frozen=True)
class BarTable:
    """Bars held in memory: what a test or a fixture hands in."""

    bars: Mapping[datetime, Bar]
    first_day: date
    last_day: date

    def covers(self, day: date) -> bool:
        return self.first_day <= day <= self.last_day

    def bar(self, minute: datetime) -> Bar | None:
        return self.bars.get(minute)


@dataclass(frozen=True)
class Entry:
    """A trip as this count needs it."""

    trip_id: str
    underlying: str | None
    entry_ts: datetime  # timezone-aware
    direction: int | None  # +1, -1, or None when the trip has no single direction


@dataclass(frozen=True)
class Unmeasured:
    trip_id: str
    reason: Reason


@dataclass(frozen=True)
class Count:
    """How many measured trips the market agreed with, and the shuffle control's band."""

    agreed: int
    measured: int
    band: tuple[int, int] | None  # None when nothing was measured

    @property
    def inside_band(self) -> bool:
        """True when the count is what shuffled directions give too, or there's no band."""
        return self.band is None or self.band[0] <= self.agreed <= self.band[1]

    @property
    def above_band(self) -> bool:
        return self.band is not None and self.agreed > self.band[1]


@dataclass(frozen=True)
class PriorMinute:
    total: int
    before: Count
    after: dict[int, Count]
    unmeasured: tuple[Unmeasured, ...]  # left out of every count, with the reason
    # Left out of one count only, because a bar that count needs is missing; the reason names it.
    unmeasured_before: tuple[Unmeasured, ...] = ()
    unmeasured_after: dict[int, tuple[Unmeasured, ...]] = field(default_factory=dict)
    seed: int = SEED
    draws: int = DRAWS

    @property
    def ships(self) -> bool:
        """The claim is that the minute before agreed more often than chance would."""
        return self.before.above_band

    def unmeasured_by_reason(self) -> dict[Reason, int]:
        return dict(Counter(u.reason for u in self.unmeasured))


def _minute(ts: datetime) -> datetime:
    return ts.astimezone(IST).replace(second=0, microsecond=0)


def _sign(move: float) -> int:
    return (move > 0) - (move < 0)


def _counted(signs: list[int], directions: list[int], rng: np.random.Generator, draws: int) -> Count:
    """The agreeing count, and the band from recounting with the directions shuffled."""
    if not signs:
        return Count(0, 0, None)
    s = np.array(signs, dtype=np.int8)
    d = np.array(directions, dtype=np.int8)
    shuffled = rng.permuted(np.tile(d, (draws, 1)), axis=1)
    recounts = (shuffled * s > 0).sum(axis=1)
    low, high = np.percentile(recounts, BAND)
    return Count(int((s * d > 0).sum()), len(signs), (int(np.floor(low)), int(np.ceil(high))))


def count(entries: Sequence[Entry], series: Mapping[str, MinuteBars], *,
          seed: int = SEED, draws: int = DRAWS) -> PriorMinute:
    """Count each trip before and after its entry minute, beside its shuffle control."""
    unmeasured: list[Unmeasured] = []
    before_out: list[Unmeasured] = []
    before_signs: list[int] = []
    before_dirs: list[int] = []
    after_signs: dict[int, list[int]] = {h: [] for h in HORIZONS}
    after_dirs: dict[int, list[int]] = {h: [] for h in HORIZONS}
    after_out: dict[int, list[Unmeasured]] = {h: [] for h in HORIZONS}

    for e in entries:
        bars = series.get(e.underlying) if e.underlying else None
        minute = _minute(e.entry_ts)
        if bars is None:
            unmeasured.append(Unmeasured(e.trip_id, Reason.NO_SERIES))
            continue
        if not bars.covers(minute.date()):
            unmeasured.append(Unmeasured(e.trip_id, Reason.NOT_COVERED))
            continue
        if e.direction not in (1, -1):
            unmeasured.append(Unmeasured(e.trip_id, Reason.NO_DIRECTION))
            continue
        # Each count asks only for the bars it reads (ruling on TICKET-898, D3): the before
        # count the bar ahead of the entry minute; each after count the entry-minute bar and the
        # bar ``h`` minutes later. A trip missing one of them is left out of that count alone.
        previous, entered = bars.bar(minute - timedelta(minutes=1)), bars.bar(minute)
        if previous is None:
            before_out.append(Unmeasured(e.trip_id, Reason.NO_PRIOR_BAR))
        else:
            before_signs.append(_sign(previous.close - previous.open))
            before_dirs.append(e.direction)
        for h in HORIZONS:
            if entered is None:
                after_out[h].append(Unmeasured(e.trip_id, Reason.NO_ENTRY_BAR))
                continue
            later = bars.bar(minute + timedelta(minutes=h))
            if later is None:
                after_out[h].append(Unmeasured(e.trip_id, Reason.NO_HORIZON_BAR))
                continue
            after_signs[h].append(_sign(later.close - entered.close))
            after_dirs[h].append(e.direction)

    rng = np.random.default_rng(seed)  # one generator, drawn in a fixed order
    before = _counted(before_signs, before_dirs, rng, draws)
    after = {h: _counted(after_signs[h], after_dirs[h], rng, draws) for h in HORIZONS}
    return PriorMinute(total=len(entries), before=before, after=after,
                       unmeasured=tuple(unmeasured), unmeasured_before=tuple(before_out),
                       unmeasured_after={h: tuple(after_out[h]) for h in HORIZONS},
                       seed=seed, draws=draws)
