"""The trades behind a fact, on a page of their own, with filters (TICKET-822).

A fact page with a long list links here (scope_map.see_all_href). Every trade behind the
fact is on this page until a filter narrows it: the handoff's "every trade, never a sample"
holds through the link, and a filter is the trader's own choice. Which trades are behind a
fact is still scope_map's to say, and the groups still come from there.

The same six filters are on every list, so a link from any fact can pick any of them: the
review asked for book, winners and losers, entry price and days to expiry on strike rate
(section 7), book and hour on the clock (section 8), and book and year on chapter 3 (section
16). A filter this history gives no choice on is left off. A value that is not on offer is
ignored, as a stale link should be, rather than refused.

The price bands and expiry buckets describe a list. They are not findings, and no band is
marked out. Premium is not used as R here or anywhere (section 12).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from services.production.api import scope_map as S
from services.production.mirror import loader
from services.production.mirror import metrics as mx

FACTS_WITH_TRADES = frozenset(S.FACTS) - {"unread", "not-told"}

PRICE_BANDS = (
    ("under-50", "Under ₹50", Decimal(0), Decimal(50)),
    ("50-100", "₹50–100", Decimal(50), Decimal(100)),
    ("100-150", "₹100–150", Decimal(100), Decimal(150)),
    ("150-250", "₹150–250", Decimal(150), Decimal(250)),
    ("250-plus", "₹250 and over", Decimal(250), None),
)
"""The price an option was opened at, bought or sold. Below the top of a band, from its bottom."""

EXPIRY_BUCKETS = (
    ("expiry-day", "Expiry day", 0, 0),
    ("1-3", "1–3 days", 1, 3),
    ("4-7", "4–7 days", 4, 7),
    ("8-plus", "8 days or more", 8, None),
)
"""Calendar days from the day a trade was opened to its contract's expiry."""

RESULTS = (
    ("winners", "Winners", "is_win"),
    ("losers", "Losers", "is_loss"),
    ("level", "Finished level", "is_scratch"),
)

Choice = tuple[object, str, str]  # how it sorts, its value in the URL, what the trader reads


def _book(t: mx.Trip, _expiries: dict) -> Choice:
    book = mx.trade_book(t)
    return book, book, book


def _result(t: mx.Trip, _expiries: dict) -> Choice | None:
    for place, (value, label, flag) in enumerate(RESULTS):
        if getattr(t, flag):
            return place, value, label
    return None


def _price(t: mx.Trip, _expiries: dict) -> Choice | None:
    """One option's opening price. A share's price is another scale; a spread has no one price."""
    if not t.is_option or len(t.lines) != 1 or t.lines[0].entry_price is None:
        return None
    opened_at = t.lines[0].entry_price
    for place, (value, label, low, high) in enumerate(PRICE_BANDS):
        if opened_at >= low and (high is None or opened_at < high):
            return place, value, label
    return None


def _days_to_expiry(t: mx.Trip, expiries: dict) -> int | None:
    """A position is read by its first leg, the one opened first."""
    if not t.is_option or not t.lines:
        return None
    expiry: date | None = expiries.get(loader.expiry_key(t.lines[0]))
    return None if expiry is None else (expiry - date.fromisoformat(t.trading_day)).days


def _expiry(t: mx.Trip, expiries: dict) -> Choice | None:
    days = _days_to_expiry(t, expiries)
    if days is None:
        return None
    for place, (value, label, low, high) in enumerate(EXPIRY_BUCKETS):
        if days >= low and (high is None or days <= high):
            return place, value, label
    return None


def _hour(t: mx.Trip, _expiries: dict) -> Choice:
    hour = t.entry_ts.hour
    return hour, str(hour), f"{hour:02d}:00"


def _year(t: mx.Trip, _expiries: dict) -> Choice:
    year = t.trading_day[:4]
    return year, year, year


@dataclass(frozen=True)
class Filter:
    name: str  # its name in the URL
    label: str
    read: Callable[[mx.Trip, dict], Choice | None]


FILTERS = (
    Filter("book", "Book", _book),
    Filter("result", "Winners and losers", _result),
    Filter("price", "Entry price", _price),
    Filter("dte", "Days to expiry", _expiry),
    Filter("hour", "Hour opened", _hour),
    Filter("year", "Year", _year),
)


def listing(key: str, ctx: dict, query: Mapping[str, str], expiries: dict) -> dict:
    """What the trade list draws: the filters as offered, the trades they leave, the counts.

    Each filter offers what the whole list has, not what the other filters left, so a
    choice never disappears from under the trader and any two can be combined. A pair
    with nothing in common says so on the page.
    """
    behind = S.trades_behind(key, ctx)
    drawn, shown = [], list(behind)
    for f in FILTERS:
        read = [(t, f.read(t, expiries)) for t in behind]
        offered = sorted({choice for _, choice in read if choice is not None}, key=lambda c: c[0])
        if len(offered) < 2:
            continue
        wanted = query.get(f.name, "")
        if wanted not in {value for _, value, _ in offered}:
            wanted = ""
        drawn.append({
            "name": f.name,
            "label": f.label,
            "choices": [
                {"value": value, "label": label, "selected": value == wanted}
                for _, value, label in offered
            ],
        })
        if wanted:
            kept = {id(t) for t, choice in read if choice is not None and choice[1] == wanted}
            shown = [t for t in shown if id(t) in kept]
    return {
        "filters": drawn,
        "filtered": len(shown) != len(behind) or any(
            c["selected"] for f in drawn for c in f["choices"]
        ),
        "shown": len(shown),
        "total": len(behind),
        "groups": S.groups(key, ctx, only=shown),
        "clear_href": S.see_all_href(key),
    }

