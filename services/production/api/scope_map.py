"""The Scope's map: four chapters, twelve facts, and the trades behind each (handoff 4, 5).

The Mirror's nine counted facts, told as a story in four chapters: Home, a chapter,
a fact - two taps to any fact, never more than three. This module is the one place
that order, the names, the links and the trades behind each fact are decided; the
routes look a fact up here and the templates draw what they are given.

Every trade behind a fact is listed, never a sample (handoff 7, the fact page). The
lists are the old Mirror drawers' lists where the Mirror had a drawer, and B3's new
ones (strike rate, longest losing run, busiest day) where it did not.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

from services.production.api import formatting
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s


@dataclass(frozen=True)
class Fact:
    key: str  # its URL and its dwell key (/mirror/fact/<key>)
    title: str  # the Mirror's own heading
    chart: str  # the scope_geometry chart that draws it


@dataclass(frozen=True)
class Chapter:
    number: int
    name: str
    facts: tuple[Fact, ...]
    feedback: bool  # "Does this match your trading?" - chapters 1-3 only


CHAPTERS: tuple[Chapter, ...] = (
    Chapter(
        1,
        "Where your results came from",
        (
            Fact("worst-days", "Your worst trading days", "worst"),
            Fact("share", "Share of your result", "share"),
            Fact("money", "Where the money came from", "money"),
        ),
        feedback=True,
    ),
    Chapter(
        2,
        "Your patterns",
        (
            Fact("hold", "How long you hold", "hold"),
            Fact("strike", "Strike rate", "strike"),
            Fact("run", "Longest losing run", "run"),
            Fact("clock", "The clock", "clock"),
        ),
        feedback=True,
    ),
    Chapter(
        3,
        "Your behaviour",
        (
            Fact("down", "Trading on while already down", "down"),
            Fact("busiest", "Your busiest day", "busy"),
        ),
        feedback=True,
    ),
    Chapter(
        4,
        "What we couldn't read",
        (
            Fact("unread", "What we could not read", "read"),
            Fact("risk", "Trades with a risk figure", "risk"),
            Fact("not-told", "What we have not told you", "notold"),
        ),
        feedback=False,
    ),
)

FACTS: dict[str, Fact] = {f.key: f for c in CHAPTERS for f in c.facts}

OLD_DWELL_LINES = {
    "worst-days": "worst-days",
    "best-worst-trades": "money",
    "two-straight-losses": "down",
    "holding-time": "hold",
    "by-hour": "clock",
}
"""The long Mirror page's dwell keys, and the fact page each is now read on.

Dwell events are keyed by fact page from here on (handoff 9). Events stored before
the Scope keep their old keys; this is how to read the two together.
"""


def chapter(n: int) -> Chapter:
    """Chapter n (1-4). KeyError for any other: the route turns that into a 404."""
    if not 1 <= n <= len(CHAPTERS):
        raise KeyError(n)
    return CHAPTERS[n - 1]


def chapter_of(key: str) -> tuple[Chapter, int]:
    """The chapter a fact sits in, and its place there (0-based, slice order)."""
    for c in CHAPTERS:
        for i, f in enumerate(c.facts):
            if f.key == key:
                return c, i
    raise KeyError(key)


# ---------- Links ----------
# Each carries the kit's ?enter= so the page knows which transition brought it there
# (handoff T6). The motion comes in Phase 3; the links are right from the start.


def _with(path: str, **query) -> str:
    query = {k: v for k, v in query.items() if v is not None}
    return f"{path}?{urlencode(query)}" if query else path


def home_href(tap: int | None = None) -> str:
    """Home; from a chapter's centre, scoping out (tap: the chapter left)."""
    return _with("/mirror", enter="out" if tap else None, tap=tap)


def chapter_href(n: int, *, from_home: bool = False, fact: int | None = None) -> str:
    """A chapter: scoped into from Home, or backed out to from one of its facts."""
    if from_home:
        return _with(f"/mirror/chapter/{n}", enter="in", tap=n)
    return _with(f"/mirror/chapter/{n}", enter="back" if fact else None, fact=fact)


def fact_href(key: str, *, lens: bool = True) -> str:
    """A fact, shrinking the dial to the lens on the way in."""
    return _with(f"/mirror/fact/{key}", enter="lens" if lens else None)


# ---------- The trades behind each fact ----------


def trades_behind(key: str, ctx: dict) -> list[mx.Trip]:
    """Every trade a fact is counted from, in the order the trader opened them.

    ctx is scope_facts.record_context(). "unread" is rows, not trades, and
    "not-told" has nothing behind it: both list none here.
    """
    trips: list[mx.Trip] = ctx["trips"]
    if key in ("worst-days", "share"):
        days = {d.trading_day for d in ctx["worst_days"].days}
        return [t for t in trips if t.trading_day in days]
    if key == "money":
        ids = {t.trip_id for t in ctx["best"] + ctx["worst"]}
        return [t for t in trips if t.trip_id in ids]
    if key == "down":
        return mx.subset(trips, ctx["two_losses"].condition_trip_ids)
    if key == "run":
        return mx.subset(trips, ctx["run"].trip_ids)
    if key == "busiest":
        return [t for t in trips if t.trading_day == ctx["days"].busiest_day]
    if key in ("hold", "strike", "clock", "risk"):
        return list(trips)
    if key in ("unread", "not-told"):
        return []
    raise KeyError(key)


OUTCOMES = (("Winners", "is_win"), ("Losers", "is_loss"), ("Finished level", "is_scratch"))

RISK_SOURCES = (
    ("Your declared budget", (s.RiskUnitSourceV1.DECLARED_BUDGET,)),
    ("Your stop", (s.RiskUnitSourceV1.DEFINED_STOP,)),
    ("Premium paid", (s.RiskUnitSourceV1.PREMIUM_PAID,)),
    ("Nothing we could use", (s.RiskUnitSourceV1.UNAVAILABLE, s.RiskUnitSourceV1.INFERRED_ATR)),
)
"""As the Mirror's risk table names them; ATR is among "nothing we could use" there too."""


def groups(key: str, ctx: dict) -> list[dict]:
    """The trades behind a fact, grouped as the fact reads them, for the trades macro.

    By how a trade ended for the two facts about outcomes, by the hour it was opened
    for the clock, by what it was measured against for risk; by trading day for the
    rest. A group with no trades is left out.
    """
    shown = trades_behind(key, ctx)
    numbers = {t.trip_id: i for i, t in enumerate(ctx["trips"], start=1)}
    if key in ("hold", "strike"):
        parts = [(title, [t for t in shown if getattr(t, flag)]) for title, flag in OUTCOMES]
    elif key == "clock":
        hours = sorted({t.entry_ts.hour for t in shown})
        parts = [(f"{h:02d}:00", [t for t in shown if t.entry_ts.hour == h]) for h in hours]
    elif key == "risk":
        parts = [
            (title, [t for t in shown if t.risk_unit_source in sources])
            for title, sources in RISK_SOURCES
        ]
    else:
        days = sorted({t.trading_day for t in shown})
        parts = [
            (f"Day {i} · {formatting.day(d)}", [t for t in shown if t.trading_day == d])
            for i, d in enumerate(days, start=1)
        ]
    return [
        {
            "title": title,
            "trade_count": len(trips),
            "net": sum(t.net for t in trips),
            "trades": [trade(t, numbers[t.trip_id]) for t in trips],
        }
        for title, trips in parts
        if trips
    ]


def trade(t: mx.Trip, number: int) -> dict:
    """One trade as the trades macro draws it.

    The fills under it (B5) are not kept yet (handoff D4), so the strip is drawn from
    the first fill to the last - in and out - and the fills table is left off.
    """
    held_minutes = t.holding_seconds // 60
    return {
        "number": number,
        "instrument": t.symbol,
        "day": formatting.day(t.trading_day),
        "time_in": t.entry_ts.strftime("%H:%M"),
        "time_out": t.exit_ts.strftime("%H:%M"),
        "held_minutes": held_minutes,
        "net": t.net,
        "fill_minutes": [0, t.holding_seconds / 60],
        "fills": [],
    }
