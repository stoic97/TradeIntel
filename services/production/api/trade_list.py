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

import math
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from functools import lru_cache
from urllib.parse import urlencode

from services.production.api import formatting
from services.production.api import scope_map as S
from services.production.ctr.profiles import registry as profiles
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


WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

LEFT_BUCKETS = (
    ("expiry-day", "Expiry day", None, 0),
    ("1", "1 day left", 1, 1),
    ("2-6", "2–6 days left", 2, 6),
    ("7-plus", "7+ days left", 7, None),
)
"""Calendar days from the day a trade was closed to its contract's expiry (TICKET-988). Not the
days-to-expiry filter above, which counts from the day it was opened."""


def days_left(t: mx.Trip, expiries: dict) -> int | None:
    """Days from the close to the contract's expiry, read by the first leg; None with no expiry."""
    if not t.lines:
        return None
    expiry: date | None = expiries.get(loader.expiry_key(t.lines[0]))
    return None if expiry is None else (expiry - t.exit_ts.date()).days


def left_bucket(t: mx.Trip, expiries: dict) -> Choice | None:
    days = days_left(t, expiries)
    if days is None:
        return None
    for place, (value, label, low, high) in enumerate(LEFT_BUCKETS):
        if (low is None or days >= low) and (high is None or days <= high):
            return place, value, label
    return None


def opened_on(t: mx.Trip, _expiries: dict) -> Choice:
    """The weekday he opened it, in the instrument's zone: the decision's day (TICKET-994)."""
    day = t.entry_ts.weekday()
    return day, WEEKDAYS[day].lower(), WEEKDAYS[day]


EXPIRY_DAYS = ((0, "expiry", "Expiry day"), (1, "other", "Other days"))
"""TICKET-994's chips: an option opened on its own contract's expiry, or any other day it was
opened on. What _days_to_expiry can't read (shares, futures, an unread expiry) is in neither."""


def expiry_day_or_not(t: mx.Trip, expiries: dict) -> Choice | None:
    days = _days_to_expiry(t, expiries)
    if days is None:
        return None
    return EXPIRY_DAYS[0] if days == 0 else EXPIRY_DAYS[1]


def closed_day(t: mx.Trip, _expiries: dict) -> Choice:
    """The date he closed it, in the instrument's zone: the calendar's day (TICKET-993)."""
    iso = t.exit_ts.date().isoformat()
    return iso, iso, formatting.day(iso)


def _year(t: mx.Trip, _expiries: dict) -> Choice:
    year = t.trading_day[:4]
    return year, year, year


HALF_OF = "half of its book's days"
"""The lookup's key for each same-day trade's half of its own book's days (TICKET-910). The
other readers find each contract's expiry in the same lookup."""

HALVES = (("first", "First half"), ("second", "Second half"))


def _half(t: mx.Trip, lookup: dict) -> Choice | None:
    half = lookup.get(HALF_OF, {}).get(t.trip_id)
    for place, (value, label) in enumerate(HALVES):
        if half == value:
            return place, value, label
    return None


AFTER_OF = "the last trade's result before each trade"
"""The lookup's key for each trade's group: the result of the last trade that closed before it
opened, the same day. One filter for every fact that groups trades this way (Your size after a
loss, How fast you went back in, Same way again); a fact joins it by adding its key to ``only``."""

AFTERS = (("loss", "After a loss"), ("win", "After a win"),
          ("win-or-level", "After a win or a level trade"))
"""How fast you went back in reads B1's two groups (the founder's ruling of 24 Nov 2026): after a
loss, and after a win or a level trade. Size and Same way again read loss and win only."""


def _after(t: mx.Trip, lookup: dict) -> Choice | None:
    group = lookup.get(AFTER_OF, {}).get(t.trip_id)
    for place, (value, label) in enumerate(AFTERS):
        if group == value:
            return place, value, label
    return None

AFTER_SOURCE = {"size": "size_after"}
"""Whose loss-or-win groups a fact's list reads: its own page's. Size reads size_after; How fast
you went back in and Same way again read next_trades. The two break a same-minute exit tie
differently, so one shared map would open trades a page didn't count."""


def after_groups(key: str, ctx: dict) -> dict:
    if key == "hidden":
        return {i: r.state for r in ctx.get("previous_result", ()) for i in r.record_ids}
    if key == "back-in":
        return ctx["next_trades"].back_in_group_of if "next_trades" in ctx else {}
    source = AFTER_SOURCE.get(key, "next_trades")
    return ctx[source].group_of if source in ctx else {}



NEXT_DAY_OF = "the day each trade's day came after"
NEXT_DAYS = (("best", "After a best day"), ("worst", "After a worst day"), ("other", "Other days"))


def _next_day(t: mx.Trip, lookup: dict) -> Choice | None:
    group = lookup.get(NEXT_DAY_OF, {}).get(t.trip_id)
    for place, (value, label) in enumerate(NEXT_DAYS):
        if group == value:
            return place, value, label
    return None


PREVIOUS_OF = "previous result that day"
"""The lookup's key for each same-day trade's previous result that day (TICKET-919), read from
the record that decided the hiding page's figures, never worked out again here."""

CHOSEN = "opened while earlier ones were down"
"""The lookup's key for the trades the figure from only what was known then counted."""

THENS = (("yes", "Opened while earlier ones were down"), ("no", "The others"))


def _previous_lookup(ctx: dict) -> dict:
    rows = ctx.get("previous_result", ())
    return {PREVIOUS_OF: {i: r.state for r in rows for i in r.record_ids},
            CHOSEN: {i for r in rows for i in r.then_ids}}


def _then(t: mx.Trip, lookup: dict) -> Choice | None:
    if t.trip_id not in lookup.get(PREVIOUS_OF, {}):
        return None
    place = 0 if t.trip_id in lookup.get(CHOSEN, set()) else 1
    value, label = THENS[place]
    return place, value, label


PAGE_SIZE = 100
"""Trades on one page of a list. Every trade is on exactly one page, and the
count line says the whole list: paging splits the list, it never samples it."""

DEFAULT_SORT = "oldest"
SORT_KEYS: dict[str, Callable[[list[mx.Trip]], list[mx.Trip]]] = {
    "newest": lambda ts: sorted(ts, key=lambda t: -t.entry_ts.timestamp()),
    "oldest": lambda ts: list(ts),
    "biggest-loss": lambda ts: sorted(ts, key=lambda t: t.net),
    "biggest-win": lambda ts: sorted(ts, key=lambda t: -t.net),
    "longest-held": lambda ts: sorted(ts, key=lambda t: -t.holding_seconds),
}
"""Each sort is stable over the list's own order (the order the trades were opened), so a tie
goes to the earlier trade."""
SORT_LABELS = {"newest": "Newest", "oldest": "Oldest", "biggest-loss": "Biggest loss",
               "biggest-win": "Biggest win", "longest-held": "Longest held"}
SORT_WORDS = {k: f"{v.lower()} first" for k, v in SORT_LABELS.items()}


# ---------- The shape of your days, on Your numbers: three readers for its taps ----------

DAY_THIRD_OF = "the third of his days by trades"
"""The lookup's key for each trade's third of his days by how many trades he closed that day."""


def _trades_label(lo: int, hi: int | None) -> str:
    if hi is None:
        return f"{lo} or more trades"
    if lo == hi:
        return f"{lo} trade" if lo == 1 else f"{lo} trades"
    return f"{lo}–{hi} trades"


def day_thirds(trips: list[mx.Trip]) -> tuple[list[tuple[str, str, int, int | None]], dict[str, Choice]]:
    """His traded days in thirds by how many trades he closed that day, at his own cut points.

    The cut points are the counts on the days a third and two thirds of the way up, his days in
    order of trades. A day at a cut point stays with the days below it, so days with the same
    count are never split; a third left empty by a tie is left out. A day is the day he closed
    (the calendar's day). Returns each third (value, label, fewest, most) and each trade's.
    """
    per_day = Counter(t.exit_ts.date().isoformat() for t in trips)
    if not per_day:
        return [], {}
    counts = sorted(per_day.values())
    n = len(counts)
    low, high = counts[math.ceil(n / 3) - 1], counts[math.ceil(2 * n / 3) - 1]
    bounds: list[tuple[int, int | None]] = [(counts[0], low)]
    if high > low:
        bounds.append((low + 1, high))
    if counts[-1] > high:
        bounds.append((high + 1, None))
    thirds = []
    for lo, hi in bounds:
        value = f"{lo}-plus" if hi is None else str(lo) if lo == hi else f"{lo}-{hi}"
        thirds.append((value, _trades_label(lo, hi), lo, hi))

    def third_of(count: int) -> int:
        return next(i for i, (_, _, lo, hi) in enumerate(thirds) if count >= lo and (hi is None or count <= hi))

    choice: dict[str, Choice] = {}
    for t in trips:
        place = third_of(per_day[t.exit_ts.date().isoformat()])
        choice[t.trip_id] = (place, thirds[place][0], thirds[place][1])
    return thirds, choice


def _day_third(t: mx.Trip, lookup: dict) -> Choice | None:
    return lookup.get(DAY_THIRD_OF, {}).get(t.trip_id)


def is_share(t: mx.Trip) -> bool:
    """A share or an ETF, as trade_book puts it in its own book."""
    return not t.is_option and bool(t.lines) and t.lines[0].segment == "EQ"


@lru_cache(maxsize=1)
def _opens() -> tuple[dict[str, time], time | None]:
    """Each instrument's session start from its profile, and the cash-equity segment's. A symbol
    two profiles give different starts is left without one rather than guessed."""
    starts: dict[str, set[time]] = {}
    shares: set[time] = set()
    for (_exchange, symbol), profile in profiles.load_all(loader.PROFILE_DIR).items():
        if symbol == profiles.SEGMENT_WILDCARD:
            if profile.segment == "EQ":
                shares.add(profile.session_start)
            continue
        starts.setdefault(symbol, set()).add(profile.session_start)
    one = {symbol: next(iter(s)) for symbol, s in starts.items() if len(s) == 1}
    return one, (next(iter(shares)) if len(shares) == 1 else None)


def session_open(t: mx.Trip) -> time | None:
    """When his instrument's session opens (NSE 09:15, MCX 09:00), or None when no profile says."""
    starts, shares = _opens()
    return shares if is_share(t) else starts.get(t.symbol)


OPENING_MINUTES = 30
OPENINGS = ((0, "first-30", "First 30 minutes"), (1, "rest", "The rest"))


def opening(t: mx.Trip, _lookup: dict) -> Choice | None:
    """Opened within 30 minutes of its own session's start, or later. One open a day: an MCX
    evening is the same session going on, not a second open."""
    start = session_open(t)
    if start is None:
        return None
    entry = t.entry_ts
    cut = datetime.combine(entry.date(), start, entry.tzinfo) + timedelta(minutes=OPENING_MINUTES)
    return OPENINGS[0] if entry < cut else OPENINGS[1]


OVERNIGHTS = ((0, "overnight", "Held overnight"), (1, "same-day", "Closed the same day"))


def session_opens(trips: list[mx.Trip]) -> list[dict]:
    """The session opens his trades are read against, each with the exchanges whose profile
    gives it, earliest first: what "the session's open" means on his own record. A share is read
    against the cash-equity profiles, so it names every exchange they cover."""
    by_time: dict[time, set[str]] = {}
    for (exchange, symbol), profile in profiles.load_all(loader.PROFILE_DIR).items():
        wanted = (symbol == profiles.SEGMENT_WILDCARD and profile.segment == "EQ"
                  and any(is_share(t) for t in trips)) or any(
            t.symbol == symbol and not is_share(t) and session_open(t) == profile.session_start for t in trips)
        if wanted:
            by_time.setdefault(profile.session_start, set()).add(exchange)
    return [{"time": f"{start:%H:%M}", "exchanges": sorted(names)} for start, names in sorted(by_time.items())]


def overnight(t: mx.Trip, _lookup: dict) -> Choice | None:
    """Options and futures closed on a later day than they were opened; shares are apart."""
    if is_share(t):
        return None
    return OVERNIGHTS[1] if t.closed_same_day else OVERNIGHTS[0]


def held_days(t: mx.Trip, _lookup: dict) -> Choice | None:
    """How many calendar days an option or a future held overnight was held, as the longest hold
    on Your numbers counts them; a share and a same-day trade have none."""
    if is_share(t) or t.closed_same_day:
        return None
    days = (t.exit_ts.date() - t.entry_ts.date()).days
    return days, str(days), f"{days} day" if days == 1 else f"{days} days"


BOOK_GROUP_OF = "the book each trade is in, as the verdict splits them"
"""The lookup's key for each trade's book as ``mx.book_groups`` names it, "Other options" too."""


def _book_group(t: mx.Trip, lookup: dict) -> Choice | None:
    name = lookup.get(BOOK_GROUP_OF, {}).get(t.trip_id)
    return (0, name, name) if name else None


@dataclass(frozen=True)
class Filter:
    name: str  # its name in the URL
    label: str
    read: Callable[[mx.Trip, dict], Choice | None]
    only: frozenset[str] | None = None  # the facts whose list offers it; None: every list
    quiet: bool = False
    """Offered only when a link has already chosen it (TICKET-993's closed_day): a menu of every
    date he closed a trade on would bury the list, and a calendar cell is the way in."""


FILTERS = (
    Filter("book", "Book", _book),
    Filter("result", "Winners and losers", _result),
    Filter("price", "Entry price", _price),
    Filter("dte", "Days to expiry", _expiry),
    Filter("hour", "Hour opened", _hour),
    Filter("year", "Year", _year),
    # The Your numbers page opens every trade by the day it was closed and by the days its
    # contract had left then (TICKET-988); offered on that list only.
    Filter("opened", "Day opened", opened_on, only=frozenset({"risk"})),
    Filter("days", "Expiry day or not", expiry_day_or_not, only=frozenset({"risk"})),
    Filter("left", "Days left when closed", left_bucket, only=frozenset({"risk"})),
    Filter("closed_day", "Date closed", closed_day, only=frozenset({"risk"}), quiet=True),
    # The shape of your days: his days by how many trades, his first 30 minutes, overnight.
    Filter("day_trades", "Trades that day", _day_third, only=frozenset({"risk"})),
    Filter("opening", "First 30 minutes", opening, only=frozenset({"risk"})),
    Filter("overnight", "Held overnight", overnight, only=frozenset({"risk"})),
    # A worst day's book cell, "Other options" too, and the longest hold open exactly their trades.
    Filter("book_group", "Book", _book_group, only=frozenset({"risk"}), quiet=True),
    Filter("held_days", "Days held", held_days, only=frozenset({"risk"}), quiet=True),
    Filter("half", "Half of the book's days", _half, only=frozenset({"hidden"})),
    Filter("after", "After a loss or a win", _after, only=frozenset({"back-in", "same-way", "hidden"})),
    Filter("next_day", "The day after", _next_day, only=frozenset({"next-day"})),
    Filter("then", "Opened while earlier ones were down", _then, only=frozenset({"hidden"})),
)


def listing(key: str, ctx: dict, query: Mapping[str, str], expiries: dict) -> dict:
    """What the trade list draws: the filters as offered, the trades they leave, the counts.

    Each filter offers what the whole list has, not what the other filters left, so a
    choice never disappears from under the trader and any two can be combined. A pair
    with nothing in common says so on the page.
    """
    behind = S.trades_behind(key, ctx)
    drawn, shown = [], list(behind)
    lookup = {**expiries, HALF_OF: mx.half_of(behind), DAY_THIRD_OF: day_thirds(behind)[1],
              BOOK_GROUP_OF: {t.trip_id: name for name, ts in mx.book_groups(behind) for t in ts},
              AFTER_OF: after_groups(key, ctx),
              NEXT_DAY_OF: ctx["day_after"].group_of if "day_after" in ctx else {},
              **_previous_lookup(ctx)}
    for f in FILTERS:
        if f.only is not None and key not in f.only:
            continue
        if f.quiet and not query.get(f.name):
            continue
        read = [(t, f.read(t, lookup)) for t in behind]
        offered = sorted({choice for _, choice in read if choice is not None}, key=lambda c: c[0])
        if f.quiet:
            offered = [c for c in offered if c[1] == query.get(f.name)]
            if not offered:
                continue
        if len(offered) < 2 and not f.quiet and not query.get(f.name):
            continue  # one choice narrows nothing, unless a link asked for it: then it still does
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
    chosen = {f["name"]: c for f in drawn for c in f["choices"] if c["selected"]}
    sort = query.get("sort", DEFAULT_SORT)
    if sort not in SORT_KEYS:
        sort = DEFAULT_SORT
    pages = max(1, -(-len(shown) // PAGE_SIZE))
    raw_page = query.get("page", "1")
    # Only plain ASCII digits of a sensible length are a page; "²", "1.5", a 5,000-digit number
    # or anything else opens page 1, as a stale filter does, never a server error.
    raw_page = str(raw_page)
    page = min(max(int(raw_page), 1), pages) if raw_page.isascii() and raw_page.isdigit() and len(raw_page) <= 6 else 1
    start = (page - 1) * PAGE_SIZE

    def href(**changes) -> str:
        params = {name: c["value"] for name, c in chosen.items()}
        params.update({"sort": sort if sort != DEFAULT_SORT else None, "page": page if page > 1 else None})
        params.update(changes)
        kept = {k: v for k, v in params.items() if v not in (None, "")}
        return "?" + urlencode(kept) if kept else "?"

    # A filtered risk list was opened from another page (Your numbers, the calendar, a process
    # line): its risk-measure groups would say nothing about what is in it, so it reads as one
    # group named by its filters. Any sort but the default reads as one group too, since a
    # sort across groups is no longer the groups' order.
    flat = sort != DEFAULT_SORT or (key == "risk" and bool(chosen))
    if flat:
        numbers = {t.trip_id: i for i, t in enumerate(ctx["trips"], start=1)}
        ordered = SORT_KEYS[sort](shown)
        words = [c["label"] for c in chosen.values()]
        if sort != DEFAULT_SORT:
            words.append(SORT_WORDS[sort])
        title = " · ".join(words)
        groups = [{
            "title": title[:1].upper() + title[1:],
            "trade_count": len(ordered),
            "net": sum((t.net for t in ordered), Decimal(0)),
            "trades": [S.trade(t, numbers[t.trip_id]) for t in ordered[start:start + PAGE_SIZE]],
        }] if ordered else []
    else:
        groups = _page_of(S.groups(key, ctx, only=shown), start)
    return {
        "filters": drawn,
        "filtered": len(shown) != len(behind) or any(
            c["selected"] for f in drawn for c in f["choices"]
        ),
        "shown": len(shown),
        "total": len(behind),
        "groups": groups,
        "clear_href": S.see_all_href(key, **({"sort": sort} if sort != DEFAULT_SORT else {})),
        "sort": sort if sort != DEFAULT_SORT else "",  # the filter form carries it, so a filter keeps the sort
        "sorts": [{"value": v, "label": SORT_LABELS[v], "on": v == sort,
                   "href": href(sort=v if v != DEFAULT_SORT else None, page=None)} for v in SORT_KEYS],
        "page": page,
        "pages": pages,
        "first": start + 1 if shown else 0,
        "last": min(start + PAGE_SIZE, len(shown)),
        "next_href": href(page=page + 1) if page < pages else None,
        "prev_href": href(page=page - 1 if page > 2 else None) if page > 1 else None,
    }


def _page_of(groups: list[dict], start: int) -> list[dict]:
    """One page of a grouped list: the groups' trades in order, a hundred of them. A group split
    across pages keeps its whole count and result in its heading and says it continues."""
    out, seen = [], 0
    for g in groups:
        n = len(g["trades"])
        lo, hi = max(start - seen, 0), min(start + PAGE_SIZE - seen, n)
        if lo < hi:
            part = dict(g, trades=g["trades"][lo:hi])
            if lo > 0:
                part["title"] = f"{g['title']} (continued)"
            out.append(part)
        seen += n
    return out

