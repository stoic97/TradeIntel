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
(``/mirror/fact/risk/trades``). A day opens the trades he closed that day (``closed_day``), the
ones its figure adds up: the day page lists the trades opened that day, which can be others.
"Other options" pools several books and has no single filter, so it is plain text.
"""
from __future__ import annotations

import calendar as _calendar
from collections import Counter
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from services.production.api import charts, formatting
from services.production.api import scope_map as SM
from services.production.api import trade_list as TL
from services.production.api.figures import Figure
from services.production.mirror import metrics as mx
from services.shared.market import closures

MINIMUM = mx.BOOK_ROW_MINIMUM
EVERY_TRADE = "risk"
"""The fact whose list is every trade on the record (scope_map.trades_behind)."""
TENTH = Decimal("0.1")


def _trades(**filters) -> str:
    return SM.see_all_href(EVERY_TRADE, **filters)


def closed_day_href(iso: str) -> str:
    """Every trade he closed on this date: the trades a day's figure on this page adds up."""
    return _trades(closed_day=iso)


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
        "best_day": {"value": best[1], "day": best[0], "href": closed_day_href(best[0])},
        "worst_day": {"value": worst[1], "day": worst[0], "href": closed_day_href(worst[0])},
        "months": {"made": sum(1 for c in months if c.net > 0), "of": len(months),
                   "href": _trades()},
        "per_day": {"value": (Decimal(len(trips)) / len(by_day)).quantize(TENTH, ROUND_HALF_UP),
                    "most": busiest[1], "day": busiest[0], "href": closed_day_href(busiest[0])},
    }

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
        "tiles": tiles, "expiry": _rows(expiry_rows),
        "no_expiry": no_expiry, "books": _rows(book_rows),
    }


# ---------- Your calendar (TICKET-993) ----------

MONTHS_SHOWN = 12
"""On All, the latest this many months; "Show all N months" asks for the rest."""
SCALE_AT = Decimal("0.9")
"""A cell's colour is measured against this percentile of the day results in view, so one huge
day doesn't wash every other cell out. Beyond it, a cell takes the strongest step."""
WEEKDAY_LETTERS = ("M", "T", "W", "T", "F", "S", "S")


def _percentile(values: list[Decimal], at: Decimal) -> Decimal:
    """Linear between ranks (numpy's default): with few days, the nearest rank would be the
    largest day, and the scale would be the outlier it exists to set aside."""
    if not values:
        return Decimal(0)
    ordered = sorted(values)
    pos = at * (len(ordered) - 1)
    low = int(pos)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (pos - low) * (ordered[high] - ordered[low])


def _shut() -> frozenset[date]:
    """NSE's closed weekdays: only to grey a day with no trades, never to move one."""
    known = closures.load().get("NSE")
    return known.closed if known else frozenset()


def calendar(trips: list[mx.Trip], *, show_all: bool = False, year_chosen: bool = False) -> dict:
    """His calendar: a block a month, newest first, a cell a day he closed trades on.

    Each day's result and each month's are the running result's own candles (986), so a cell
    and a candle can't disagree; nothing is added up a second way. A day is the day he closed.
    """
    run = mx.running_result(trips)
    days = {c.period: c for c in run.candles["day"]}
    months = list(reversed(run.candles["month"]))
    cut = None
    if not show_all and not year_chosen and len(months) > MONTHS_SHOWN:
        cut = (MONTHS_SHOWN, len(months))
        months = months[:MONTHS_SHOWN]
    shown = {m.period for m in months}
    in_view = [c for p, c in days.items() if p[:7] in shown]
    scale = _percentile([abs(c.net) for c in in_view], SCALE_AT)
    shut = _shut()

    blocks = []
    for m in months:
        year, month = (int(x) for x in m.period.split("-"))
        weeks = []
        for week in _calendar.Calendar(firstweekday=0).monthdatescalendar(year, month):
            row = []
            for d in week:
                if d.month != month:
                    row.append(None)
                    continue
                iso = d.isoformat()
                c = days.get(iso)
                traded = c is not None and c.trades > 0
                href = None
                if traded:
                    href = closed_day_href(iso)
                row.append({
                    "day": d.day, "iso": iso,
                    "net": c.net if traded else None,
                    "trades": c.trades if traded else 0,
                    "tone": charts.cell_tone(c.net if traded else None, scale),
                    "href": href,
                    "closed": not traded and d.weekday() < 5 and d in shut,
                })
            weeks.append(row)
        blocks.append({"period": m.period, "label": date(year, month, 1).strftime("%b %Y"),
                       "net": m.net, "trades": m.trades, "weeks": weeks})

    rows = [[formatting.day(c.period), Figure(c.trades, "trades"), Figure(c.net, "rupees")]
            for c in sorted(in_view, key=lambda c: c.period, reverse=True) if c.trades]
    return {
        "months": blocks, "cut": cut, "all_href": "?months=all#calendar", "scale": scale,
        "letters": WEEKDAY_LETTERS,
        "table": charts.text_table(rows, ["Day", "Trades", "Result"],
                                   caption="Every day you closed a trade, as numbers"),
    }


# ---------- When you trade (TICKET-994) ----------

DAYS = (("all", "All days"), ("expiry", "Expiry day"), ("other", "Other days"))
SPLIT_AT = 15
"""Past MAX_COLUMNS hours, the grid splits into the hours before this and from it."""
MAX_COLUMNS = 13
"""The hour columns a phone fits at 24 px each beside the weekday labels, without scrolling."""
CELL_W, CELL_H, LABEL_W, HEAD_H = 24, 22, 34, 14


def when(trips: list[mx.Trip], expiries: dict, *, days: str = "all") -> dict:
    """Weekday x hour, by when he opened the trade, as the trade list's hour filter reads it.

    Each cell is its trades' result, toned against the 90th percentile of the cells in view and
    hatched under the clock's own minimum. No cell is called best or worst; the figures are in
    each cell's tap target and in the text table.
    """
    days = days if days in dict(DAYS) else "all"
    side = {t.trip_id: TL.expiry_day_or_not(t, expiries) for t in trips}
    left_out = sum(1 for choice in side.values() if choice is None)
    shown = trips if days == "all" else [
        t for t in trips if side[t.trip_id] is not None and side[t.trip_id][1] == days]

    cells: dict[tuple[int, int], list[mx.Trip]] = {}
    for t in shown:
        cells.setdefault((t.entry_ts.weekday(), t.entry_ts.hour), []).append(t)
    nets = {k: sum((t.net for t in ts), Decimal(0)) for k, ts in cells.items()}
    scale = _percentile([abs(n) for n in nets.values()], SCALE_AT)
    weekdays = [*range(5), *sorted({d for d, _ in cells if d >= 5})]
    hours = sorted({h for _, h in cells})
    if len(hours) > MAX_COLUMNS:
        splits = [[h for h in hours if h < SPLIT_AT], [h for h in hours if h >= SPLIT_AT]]
    else:
        splits = [hours]

    def cell(day: int, hour: int, column: int, row: int) -> dict:
        ts = cells.get((day, hour), [])
        net = nets.get((day, hour))
        x, y = LABEL_W + CELL_W * column + 1, HEAD_H + CELL_H * row + 1
        hatched = 0 < len(ts) < mx.SMALL_SAMPLE_TRIPS
        chip = {"days": days} if days != "all" else {}
        return {
            "hour": hour, "trades": len(ts), "net": net if ts else None, "x": x, "y": y,
            "tone": charts.cell_tone(net if ts else None, scale), "hatched": hatched,
            "hatch": charts.hatch(x, y, CELL_W - 2, CELL_H - 2) if hatched else None,
            "href": _trades(opened=TL.WEEKDAYS[day].lower(), hour=str(hour), **chip) if ts else None,
        }

    blocks = []
    for part in splits:
        rows = [{"weekday": TL.WEEKDAYS[d], "short": TL.WEEKDAYS[d][:3], "y": HEAD_H + CELL_H * r,
                 "cells": [cell(d, h, c, r) for c, h in enumerate(part)]}
                for r, d in enumerate(weekdays)]
        blocks.append({
            "hours": list(part), "rows": rows,
            "columns": [{"hour": h, "x": LABEL_W + CELL_W * c + CELL_W // 2} for c, h in enumerate(part)],
            "width": LABEL_W + CELL_W * len(part), "height": HEAD_H + CELL_H * len(weekdays),
        })

    table = []
    for d in weekdays:
        for h in hours:
            ts = cells.get((d, h))
            if not ts:
                continue
            rate = mx.strike_rate(ts).rate_percent if len(ts) >= mx.CLOCK_MINIMUM_TRADES else None
            table.append([TL.WEEKDAYS[d], f"{h:02d}:00", Figure(len(ts), "trades"),
                          Figure(nets[(d, h)], "rupees"),
                          Figure(rate, "percent") if rate is not None else "too few"])
    return {
        "days": days, "left_out": left_out, "scale": scale, "blocks": blocks,
        "chips": [{"label": label, "href": f"?days={value}#when", "on": value == days}
                  for value, label in DAYS],
        "cell_w": CELL_W - 2, "cell_h": CELL_H - 2,
        "table": charts.text_table(table, ["Day", "Hour", "Trades", "Result", "Made money"],
                                   caption="Every hour you opened trades in, as numbers"),
    }
