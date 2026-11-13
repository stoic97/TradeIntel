"""Blind replay (TICKET-924): his real entries mixed with random moments, result hidden.

Each card shows the market up to a past moment and nothing after it, and asks one thing:
take it or skip it. Then the reveal: whether it was one of his own entries, and what the
market did next, in points before charges. Hindsight is impossible by design, so the
score measures whether his selection carries any information at all.

**What the draw guarantees.**

* **Old trades only.** A recent chart is remembered, and memory contaminates the test.
  ``OLD_AFTER_DAYS`` is the cutoff, written here and on the page.
* **Matched on count and on month.** For every real entry drawn, one random moment is
  drawn on the same underlying in the same calendar month, at a minute with a full
  window before it and its horizon after it, and away from any of his real entries. Each
  random moment takes the direction of one of the real entries drawn, shuffled, so the
  directions match too.
* **Nothing before the reveal depends on what came after the moment.** A card holds only
  bars that started before the moment's minute. The outcome is worked out separately, at
  the reveal, from the bars after it.
* **Seeded.** ``SEED`` and the trader's own key decide the draw, so the same history
  always deals the same cards.

**What the score may say: counts against a control, nothing more.** How many calls he
made, how many went his way, and the band a coin flip would give on that many calls. No
composite score, no rating, no "skill", no rupee figure. Points are the underlying's,
labelled before charges.

**Not open to a real trader until the pre-registration is signed** (``PREREG_SIGNED``):
the rule for what the score may claim is written in ``docs/phase0/blind-replay-prereg.md``
and is the research seat's to sign before anyone plays on a real file.

Bars come in through ``prior_minute.MinuteBars``, one series per underlying, and the
direction of a trade from ``services.shared.option_direction``'s table. Nothing here
imports research.
"""

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from math import comb

from services.production.mirror.prior_minute import IST, Bar, MinuteBars
from services.shared import option_direction as od
from services.shared.schemas.ctr_v1 import Direction, OptionType

OLD_AFTER_DAYS = 180
"""A trade is old enough once this many days have passed: about two quarters, past the
weeks a trader remembers a chart for. Stated on the page."""
CARDS = 10            # at most: half his own entries, half random moments
WINDOW_MINUTES = 60   # the market shown before the moment
HORIZON_MINUTES = 15  # what "next" means at the reveal
KEEP_AWAY_MINUTES = 30  # a random moment is at least this far from any of his entries
SEED = 20261113
PREREG_SIGNED = False
"""The research seat signs docs/phase0/blind-replay-prereg.md before a real trader plays."""


@dataclass(frozen=True)
class Entry:
    trip_id: str
    underlying: str
    entry_ts: datetime
    direction: int | None  # +1 long the underlying, -1 short, None no single direction


@dataclass(frozen=True)
class Card:
    """What a card shows before the reveal, and nothing else."""

    number: int
    underlying: str
    moment: datetime     # the minute he decides at; nothing from it on is shown
    direction: int       # the side he would take
    shown: tuple[Bar, ...]


@dataclass(frozen=True)
class Dealt:
    card: Card
    real: bool           # kept apart from the card: the reveal reads it, the card never does
    trip_id: str | None


@dataclass(frozen=True)
class Reveal:
    real: bool
    points: float        # the underlying's move from the last shown close to the horizon,
    agreed: bool         # in the card's direction, before charges


@dataclass(frozen=True)
class Score:
    calls: int
    right: int
    band: tuple[int, int]   # what a coin flip gives on this many calls, 95% two-sided
    took: int
    took_points: float      # on the cards he took, in his direction, before charges


def direction_of(trip) -> int | None:
    """Long +1, short -1, or None, by the shared rule's table, read from the trade's legs."""
    if len(trip.lines) != 1:
        return None
    line = trip.lines[0]
    side = Direction.LONG if line.side.lower().startswith("b") else Direction.SHORT
    kind = OptionType(line.option_type) if line.segment == "OPT" and line.option_type else None
    answer = od.TABLE[(kind, side)]
    return {od.Underlying.LONG: 1, od.Underlying.SHORT: -1}.get(answer)


def _minute(ts: datetime) -> datetime:
    return ts.astimezone(IST).replace(second=0, microsecond=0)


def _window(bars: MinuteBars, moment: datetime) -> tuple[Bar, ...] | None:
    """The bars of the WINDOW_MINUTES minutes before the moment, all present, or None."""
    out = []
    for back in range(WINDOW_MINUTES, 0, -1):
        bar = bars.bar(moment - timedelta(minutes=back))
        if bar is None:
            return None
        out.append(bar)
    return tuple(out)


def _has_horizon(bars: MinuteBars, moment: datetime) -> bool:
    return bars.bar(moment + timedelta(minutes=HORIZON_MINUTES)) is not None


def eligible(entries: list[Entry], series: dict[str, MinuteBars], today: date) -> list[Entry]:
    """His entries old enough, with one direction, and bars around them."""
    cutoff = today - timedelta(days=OLD_AFTER_DAYS)
    out = []
    for e in entries:
        bars = series.get(e.underlying)
        moment = _minute(e.entry_ts)
        if (e.direction in (1, -1) and moment.date() <= cutoff and bars is not None
                and bars.covers(moment.date()) and _window(bars, moment) is not None
                and _has_horizon(bars, moment)):
            out.append(e)
    return out


def _month_minutes(bars: MinuteBars, year: int, month: int, minutes: list[datetime]) -> list[datetime]:
    return [m for m in minutes if (m.year, m.month) == (year, month)]


def deal(entries: list[Entry], series: dict[str, MinuteBars], today: date, *, key: str = "",
         candidates: dict[str, list[datetime]] | None = None) -> list[Dealt]:
    """The cards: up to CARDS // 2 of his old entries and as many random moments, matched on
    underlying, month and direction, shuffled. ``candidates`` lists each underlying's
    minutes to draw from (every bar's start, in the series' own order)."""
    rng = random.Random(f"{SEED}:{key}")
    pool = eligible(entries, series, today)
    real = rng.sample(pool, min(len(pool), CARDS // 2))
    near: dict[str, list[datetime]] = defaultdict(list)
    for e in entries:
        near[e.underlying].append(_minute(e.entry_ts))
    directions = [e.direction for e in real]
    rng.shuffle(directions)
    dealt: list[tuple[datetime, str, int, bool, str | None]] = []
    for e, direction in zip(real, directions, strict=True):
        bars = series[e.underlying]
        moment = _minute(e.entry_ts)
        options = [m for m in _month_minutes(bars, moment.year, moment.month,
                                             (candidates or {}).get(e.underlying, []))
                   if m.date() <= today - timedelta(days=OLD_AFTER_DAYS)]
        rng.shuffle(options)
        random_moment = next(
            (m for m in options
             if all(abs((m - n).total_seconds()) >= KEEP_AWAY_MINUTES * 60
                    for n in near[e.underlying])
             and _window(bars, m) is not None and _has_horizon(bars, m)), None)
        if random_moment is None:
            continue  # no random moment to match it: the real one is left out too
        dealt.append((moment, e.underlying, e.direction, True, e.trip_id))
        dealt.append((random_moment, e.underlying, direction, False, None))
    rng.shuffle(dealt)
    return [Dealt(Card(i + 1, u, m, d, _window(series[u], m)), real_, tid)
            for i, (m, u, d, real_, tid) in enumerate(dealt)]


def reveal(dealt: Dealt, series: dict[str, MinuteBars]) -> Reveal:
    """What happened next, from the last close he saw to the close HORIZON_MINUTES later."""
    bars = series[dealt.card.underlying]
    later = bars.bar(dealt.card.moment + timedelta(minutes=HORIZON_MINUTES))
    points = (later.close - dealt.card.shown[-1].close) * dealt.card.direction
    return Reveal(dealt.real, points, points > 0)


def coin_band(n: int, cover: float = 0.95) -> tuple[int, int]:
    """The middle ``cover`` of right calls a coin flip gives on n calls, by the binomial."""
    if n == 0:
        return (0, 0)
    tail = (1 - cover) / 2
    cdf, low, high = 0.0, 0, n
    for k in range(n + 1):
        cdf += comb(n, k) / 2 ** n
        if cdf >= tail:
            low = k
            break
    cdf = 0.0
    for k in range(n + 1):
        cdf += comb(n, k) / 2 ** n
        if cdf >= 1 - tail:
            high = k
            break
    return (low, high)


def score(dealt: list[Dealt], calls: str, series: dict[str, MinuteBars]) -> Score:
    """Calls are one letter a card, T for take and S for skip. A call is right when he took a
    card that went his way, or skipped one that didn't."""
    right = took = 0
    took_points = 0.0
    for d, call in zip(dealt, calls, strict=False):
        r = reveal(d, series)
        if call == "T":
            took += 1
            took_points += r.points
            right += r.agreed
        elif call == "S":
            right += not r.agreed
    n = len([c for c in calls[:len(dealt)] if c in "TS"])
    return Score(n, right, coin_band(n), took, took_points)
