"""Year and book filters on the report (TICKET-904).

A trader reading today's report should see the book he trades now, not the one he has
mostly left. So the report answers for a chosen period and book: **All, each year his file
holds, or Since your last upload**, and **every book, or one.**

**One filter, applied once, where the record is loaded** (``routes_mirror.load_record``).
Every page then reads the same filtered trades, and every figure is computed from them by
the same code as always: filtering chooses the trades, it never computes a figure a second
way. Each fact's minimum is applied to the filtered trades, so one year of one book that
is too thin shows its "not enough" state rather than a thinner number.

**Decided here, and written in the PR:**

* **A year is a calendar year, of the day the trade opened**, in India time (``trading_day``).
  A trade opened on 31 December and closed in January counts in December's year.
* **Since your last upload** is the days the latest upload added: its day versions marked
  new. It is offered only when there was an upload before it.
* **The report and its dial follow the filter; Home does not.** Home is the door to the
  whole record and says the whole record; the report says, in words, what it is filtered to.
* **An empty combination is shown, not hidden**, with a way back to everything: hiding it
  would read as a book gone missing.

**It survives a page move.** The choice is kept in a cookie, set by ``/mirror/filter`` and
read on every report page, so links stay as they are and nothing resets on the way from a
chapter to a fact. The cookie holds the choice and nothing else; nothing is stored on the
server. The sample (``/sample``) is never filtered.
"""

from __future__ import annotations

from dataclasses import dataclass

from services.production.mirror import metrics as mx

COOKIE = "scope_filter"
ALL = "all"
SINCE = "since-upload"
SINCE_WORDS = "Since your last upload"


@dataclass(frozen=True)
class ReportFilter:
    period: str = ALL     # ALL, a year such as "2026", or SINCE
    book: str | None = None  # a book as the report names it, e.g. "Crude options"

    @property
    def active(self) -> bool:
        return self.period != ALL or self.book is not None

    def encode(self) -> str:
        return f"{self.period}|{self.book or ''}"


def decode(raw: str | None) -> ReportFilter:
    if not raw or "|" not in raw:
        return ReportFilter()
    period, _, book = raw.partition("|")
    return ReportFilter(period or ALL, book or None)


def years(trips: list[mx.Trip]) -> list[str]:
    return sorted({t.trading_day[:4] for t in trips})


def books(trips: list[mx.Trip]) -> list[str]:
    return sorted({mx.trade_book(t) for t in trips})


def valid(f: ReportFilter, trips: list[mx.Trip], new_days: set[str] | None) -> ReportFilter:
    """The filter, with anything his file doesn't hold dropped back to All."""
    period = f.period
    if period not in (ALL, SINCE, *years(trips)) or (period == SINCE and new_days is None):
        period = ALL
    book = f.book if f.book in books(trips) else None
    return ReportFilter(period, book)


def apply(trips: list[mx.Trip], f: ReportFilter, new_days: set[str] | None) -> list[mx.Trip]:
    """The trades the report reads under this filter. Selection only; nothing is computed."""
    out = trips
    if f.period == SINCE:
        out = [t for t in out if t.trading_day in (new_days or set())]
    elif f.period != ALL:
        out = [t for t in out if t.trading_day.startswith(f.period)]
    if f.book is not None:
        out = [t for t in out if mx.trade_book(t) == f.book]
    return out


def words(f: ReportFilter) -> str | None:
    """What a filtered page says it is filtered to, so no figure reads as the whole record."""
    if not f.active:
        return None
    period = {ALL: None, SINCE: "your trades since your last upload"}.get(f.period, f"{f.period} only")
    if f.book and period:
        return f"Showing {period}, in {f.book}."  # the book as the report names it: NIFTY, not nifty
    if f.book:
        return f"Showing {f.book} only."
    return f"Showing {period}."


def bar(f: ReportFilter, trips: list[mx.Trip], new_days: set[str] | None, here: str) -> dict:
    """What the filter bar draws: each period and book with the address that chooses it."""
    def href(period: str, book: str | None) -> str:
        from urllib.parse import urlencode
        return "/mirror/filter?" + urlencode({"period": period, "book": book or "", "next": here})

    periods = [(ALL, "All"), *((y, y) for y in years(trips))]
    if new_days is not None:
        periods.append((SINCE, SINCE_WORDS))
    return {
        "periods": [{"label": label, "href": href(p, f.book), "current": p == f.period}
                    for p, label in periods],
        "books": [{"label": "All books", "href": href(f.period, None), "current": f.book is None},
                  *({"label": b, "href": href(f.period, b), "current": b == f.book}
                    for b in books(trips))],
        "words": words(f),
        "clear": href(ALL, None) if f.active else None,
    }


def by_year(trips: list[mx.Trip]) -> dict[str, list[dict]]:
    """Each book's result in each year of his file: the same sum the books' rows make (the net
    of its trades), year by year, to answer "is it still happening?". Whole history, whatever
    the filter, because it is the view across time. A year with no trades in a book says so."""
    from decimal import Decimal
    out: dict[str, list[dict]] = {}
    for book in books(trips):
        mine = [t for t in trips if mx.trade_book(t) == book]
        out[book] = [{"year": y,
                      "trades": sum(1 for t in mine if t.trading_day.startswith(y)),
                      "net": sum((t.net for t in mine if t.trading_day.startswith(y)), Decimal(0))}
                     for y in years(trips)]
    return out
