"""Your numbers (TICKET-988): his scoreboard, and his trades by the day he closed them, by days
left to expiry, and by book.

**Counted rows, never a verdict.** Each row is how many trades, how many of a hundred made
money, and what they came to. Nothing here says a day, a bucket or a book is good or bad, and
nothing is ranked or marked out. A sentence like that is a finding and has to pass the finding
bar on a ticket of its own.

**One formula each, all of them the report's.** Win rate is ``strike_rate`` (scratches in
neither), the averages are ``break_even``'s, the books are ``book_groups`` (the verdict's own
split), and the months are the running result's month candles. A row's "made money" needs
``BOOK_ROW_MINIMUM`` trades; below it the row says too few and still shows its count and result.

**Days are the day he closed**, in the instrument's zone, as the running result counts them.
Days left to expiry are calendar days from that day to the contract's expiry, read the way
the trade list reads it (``trade_list.left_bucket``), so a row and the list it opens agree.

**Every row opens its trades.** Rows open the list of every trade with the matching filter
(``/mirror/fact/risk/trades``); a day opens its day page when a trade was opened that day.
"Other options" pools several books and has no single filter, so it is plain text.
"""
from __future__ import annotations

from collections import Counter
from decimal import ROUND_HALF_UP, Decimal

from services.production.api import scope_map as SM
from services.production.api import trade_list as TL
from services.production.mirror import metrics as mx

MINIMUM = mx.BOOK_ROW_MINIMUM
EVERY_TRADE = "risk"
"""The fact whose list is every trade on the record (scope_map.trades_behind)."""
TENTH = Decimal("0.1")


def _trades(**filters) -> str:
    return SM.see_all_href(EVERY_TRADE, **filters)


def _side(net: Decimal) -> str:
    return "gain" if net > 0 else "loss" if net < 0 else "zero"


def _rows(groups: list[tuple[str, list[mx.Trip], str | None]]) -> list[dict]:
    """A row per group: its trades, its win rate from MINIMUM trades, its result, and its bar,
    scaled to the largest result among the rows so each fills its half of the track."""
    nets = [sum((t.net for t in trips), Decimal(0)) for _, trips, _ in groups]
    scale = max((abs(n) for n in nets), default=Decimal(0))
    rows = []
    for (name, trips, href), net in zip(groups, nets, strict=True):
        rate = mx.strike_rate(trips).rate_percent if len(trips) >= MINIMUM else None
        width = (abs(net) / scale * 50).quantize(TENTH, ROUND_HALF_UP) if scale else Decimal(0)
        rows.append({"name": name, "href": href if trips else None, "trades": len(trips),
                     "rate": rate, "net": net, "bar_side": _side(net), "bar_width": width})
    return rows


def build(trips: list[mx.Trip], expiries: dict, *, gross: bool) -> dict:
    """Everything the page draws; the template computes nothing."""
    ordered = sorted(trips, key=lambda t: (t.exit_ts, t.trip_id))
    opened_on = {t.trading_day for t in trips}

    def day_href(iso: str) -> str | None:
        return f"/mirror/day/{iso}" if iso in opened_on else None

    by_day: dict[str, Decimal] = {}
    per_day: Counter[str] = Counter()
    for t in ordered:  # in date order, so a tie goes to the earlier day
        day = t.exit_ts.date().isoformat()
        by_day[day] = by_day.get(day, Decimal(0)) + t.net
        per_day[day] += 1
    best = max(by_day.items(), key=lambda kv: kv[1])
    worst = min(by_day.items(), key=lambda kv: kv[1])
    busiest = max(per_day.items(), key=lambda kv: kv[1])
    strike, even = mx.strike_rate(trips), mx.break_even(trips)
    months = mx.running_result(trips).candles["month"]

    tiles = {
        "winner": {"value": even.average_winner, "count": strike.wins,
                   "href": _trades(result="winners")},
        "loser": {"value": None if even.average_loser is None else -even.average_loser,
                  "count": strike.losses, "href": _trades(result="losers")},
        "best_day": {"value": best[1], "day": best[0], "href": day_href(best[0])},
        "worst_day": {"value": worst[1], "day": worst[0], "href": day_href(worst[0])},
        "months": {"made": sum(1 for c in months if c.net > 0), "of": len(months),
                   "href": _trades()},
        "per_day": {"value": (Decimal(len(trips)) / len(by_day)).quantize(TENTH, ROUND_HALF_UP),
                    "most": busiest[1], "day": busiest[0], "href": day_href(busiest[0])},
    }

    weekdays: dict[int, list[mx.Trip]] = {}
    for t in ordered:
        weekdays.setdefault(t.exit_ts.weekday(), []).append(t)
    weekday_rows = [(TL.WEEKDAYS[d], weekdays[d], _trades(closed=TL.WEEKDAYS[d].lower()))
                    for d in sorted(weekdays)]

    left: dict[str, list[mx.Trip]] = {value: [] for value, _, _, _ in TL.LEFT_BUCKETS}
    no_expiry = 0
    for t in ordered:
        bucket = TL.left_bucket(t, expiries)
        if bucket is None:
            no_expiry += 1
        else:
            left[bucket[1]].append(t)
    expiry_rows = [(label, left[value], _trades(left=value)) for value, label, _, _ in TL.LEFT_BUCKETS]

    book_rows = [(name, ts, None if name == mx.OTHER_OPTIONS else _trades(book=name))
                 for name, ts in mx.book_groups(trips)]

    return {
        "trades": len(trips), "first": ordered[0].exit_ts.date().isoformat(),
        "last": ordered[-1].exit_ts.date().isoformat(), "gross": gross, "minimum": MINIMUM,
        "tiles": tiles, "weekdays": _rows(weekday_rows), "expiry": _rows(expiry_rows),
        "no_expiry": no_expiry, "books": _rows(book_rows),
    }
