"""Home's "How you got here" card (TICKET-987).

The verdict above it says how much. This card says how: three numbers, then his running
result drawn as candles, the way he reads a price chart, with the trades he took under them.
Chips choose the book and Day / Week / Month; they are links the server answers, so the card
works with no script and a tap keeps him on the card (#how).

It reads ``metrics.running_results`` and decides nothing a second way. The chart is drawn
here as SVG, like the dial, and handed to the template as safe markup; every figure a trader
reads as text goes through ``Figure`` in the template.

Decided here:

* **What opens first:** the first of Day, Week, Month with no more than WINDOW candles, so
  the chart is readable at phone width (63 days opens on weeks; 29 months on months).
* **A view over WINDOW shows the latest WINDOW candles and scales to them,** as a trading
  chart does; ₹0 is kept in range only on a full view. "Lowest" is marked on a full view
  only: on a cut one the lowest candle shown need not be his lowest.
* **A candle opens the day page** (``/mirror/day/<day>``, TICKET-905) of the first trade that
  closed in it: a day candle opens its day; a week or month candle opens its first day,
  because no page lists a week's or a month's days yet.
* **A book gets a chip at NAMED_BOOK_MINIMUM trades**, the report's own line; a smaller one is
  still in "Other options" or its own book on the Your numbers page.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta
from decimal import Decimal

from markupsafe import Markup, escape

from services.production.api import formatting
from services.production.mirror import metrics as mx

WINDOW = 60
"""Candles a phone reads. Over this, the chart shows the latest WINDOW."""

FRAMES = {"d": "day", "w": "week", "m": "month"}
FRAME_NAME = {"day": "Day", "week": "Week", "month": "Month"}
ANCHOR = "how"
LAKH = Decimal(10) ** 5
"""The Indian hundred thousand an axis label counts in."""

# The chart's own drawing box; the SVG stretches to the card.
W, H, LEFT, RIGHT, TOP = 358, 300, 6, 58, 12
PRICE_BOTTOM, VOL_TOP, VOL_BOTTOM = 212, 226, 278


def short(value: Decimal) -> str:
    """An axis label, as a trader's chart writes it: ₹20k, −₹47.5k, ₹1.5L. A tick that is not a
    whole thousand keeps its half, never rounded to the next thousand."""
    if not value:
        return "₹0"
    sign = formatting.MINUS if value < 0 else ""
    a = abs(value)
    if a >= LAKH:
        lakh = a / LAKH
        return f"{sign}₹{lakh.normalize():f}L" if lakh == lakh.to_integral_value() else f"{sign}₹{lakh:.1f}L"
    if a >= 1000:
        k = a / 1000
        return f"{sign}₹{int(k)}k" if k == k.to_integral_value() else f"{sign}₹{k:.1f}k"
    return f"{sign}₹{int(a)}"


def slug(book: str) -> str:
    return book.lower().replace(" ", "-")


def href(book: str, frame: str) -> str:
    letter = next(k for k, v in FRAMES.items() if v == frame)
    return f"/?book={slug(book)}&tf={letter}#{ANCHOR}"


def default_frame(run: mx.RunningResult) -> str:
    return next((f for f in mx.TIMEFRAMES if len(run.candles[f]) <= WINDOW), "month")


def label(period: str, frame: str) -> str:
    if frame == "day":
        return formatting.day(period)
    if frame == "week":
        return f"Week of {formatting.day(period)}"
    year, month = period.split("-")
    return date(int(year), int(month), 1).strftime("%b %Y")


def period_end(period: str, frame: str) -> date:
    if frame == "day":
        return date.fromisoformat(period)
    if frame == "week":
        return date.fromisoformat(period) + timedelta(days=6)
    year, month = (int(p) for p in period.split("-"))
    return date(year + month // 12, month % 12 + 1, 1) - timedelta(days=1)


def _day_of(trips: Iterable[mx.Trip], frame: str) -> dict[str, str]:
    """Each candle's way in: the trading day of the first trade that closed in it. The series'
    own period rule, so a candle and its trades can't disagree."""
    out: dict[str, str] = {}
    for trip in sorted(trips, key=lambda t: (t.exit_ts, t.trip_id)):
        out.setdefault(mx._period(trip.exit_ts.date(), frame), trip.trading_day)
    return out


def _day_closed(trips: Iterable[mx.Trip], exit_day: str | None) -> str | None:
    """The trading day of a trade that closed on this exit date (a mark's day opens there)."""
    if exit_day is None:
        return None
    return next((t.trading_day for t in sorted(trips, key=lambda t: (t.exit_ts, t.trip_id))
                 if t.exit_ts.date().isoformat() == exit_day), None)


def _ticks(lo: Decimal, hi: Decimal) -> tuple[Decimal, Decimal, Decimal]:
    raw = float(hi - lo) / 5 or 1.0
    mag = 10 ** (len(str(int(raw))) - 1)
    tick = Decimal(str(next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)))
    lo = (lo / tick).to_integral_value(rounding="ROUND_FLOOR") * tick
    hi = (hi / tick).to_integral_value(rounding="ROUND_CEILING") * tick
    return lo, hi, tick


def chart(run: mx.RunningResult, frame: str, opens: dict[str, str]) -> Markup:
    """The candles, the trades under them, and the marks, as SVG."""
    every = run.candles[frame]
    cut = len(every) > WINDOW
    cs = every[-WINDOW:]
    lo = min(c.low for c in cs) if cut else min(min(c.low for c in cs), Decimal(0))
    hi = max(c.high for c in cs) if cut else max(max(c.high for c in cs), Decimal(0))
    lo, hi, tick = _ticks(lo, hi)
    span = (hi - lo) or tick
    step = (W - LEFT - RIGHT) / len(cs)
    body = max(1.6, min(14.0, step * 0.64))
    most = max(c.trades for c in cs)

    def y(v: Decimal) -> float:
        return TOP + float((hi - v) / span) * (PRICE_BOTTOM - TOP)

    def vy(n: int) -> float:
        return VOL_BOTTOM - (VOL_BOTTOM - VOL_TOP) * n / most

    noun = frame
    out = [(f'<svg class="hy-chart" viewBox="0 0 {W} {H}" role="img" aria-label="'
            f'{escape(run.book)}: your running result, one candle per {noun}">')]
    v = lo
    while v <= hi:
        out.append(f'<line x1="{LEFT}" x2="{W - RIGHT}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="hy-grid"/>'
                   f'<text x="{W - RIGHT + 6}" y="{y(v) + 4:.1f}" class="hy-axis">{short(v)}</text>')
        v += tick
    if lo <= 0 <= hi:
        out.append(f'<line x1="{LEFT}" x2="{W - RIGHT}" y1="{y(Decimal(0)):.1f}" '
                   f'y2="{y(Decimal(0)):.1f}" class="hy-zero"/>')
    high = run.high.value
    if high > 0 and lo <= high <= hi:
        out.append(f'<line x1="{LEFT}" x2="{W - RIGHT}" y1="{y(high):.1f}" y2="{y(high):.1f}" class="hy-high"/>'
                   f'<text x="{W - RIGHT - 2}" y="{y(high) - 4:.1f}" class="hy-tag" text-anchor="end">'
                   f'Your high {escape(formatting.rupees(high))}</text>')
    low_at = None if cut else min(range(len(cs)), key=lambda i: cs[i].low)
    last_month, last_x = None, -99.0
    for i, c in enumerate(cs):
        cx = LEFT + step * (i + 0.5)
        kind = "up" if c.close >= c.open else "down"
        top_y, bottom_y = sorted((y(c.open), y(c.close)))
        title = (f"{label(c.period, frame)}: opened {formatting.rupees(c.open)}, high {formatting.rupees(c.high)}, "
                 f"low {formatting.rupees(c.low)}, closed {formatting.rupees(c.close)}; "
                 f"{formatting.count(c.trades)} {'trade' if c.trades == 1 else 'trades'}")
        target = f"/mirror/day/{opens[c.period]}"
        out.append(f'<a href="{escape(target)}" class="hy-candle hy-candle--{kind}"><title>{escape(title)}</title>'
                   f'<rect x="{cx - step / 2:.1f}" y="{TOP}" width="{step:.1f}" height="{VOL_BOTTOM - TOP}" class="hy-hit"/>'
                   f'<line x1="{cx:.1f}" x2="{cx:.1f}" y1="{y(c.high):.1f}" y2="{y(c.low):.1f}" class="hy-wick"/>'
                   f'<rect x="{cx - body / 2:.1f}" y="{top_y:.1f}" width="{body:.1f}" '
                   f'height="{max(1.2, bottom_y - top_y):.1f}" class="hy-body"/>'
                   f'<rect x="{cx - body / 2:.1f}" y="{vy(c.trades):.1f}" width="{body:.1f}" '
                   f'height="{VOL_BOTTOM - vy(c.trades):.1f}" class="hy-vol"/></a>')
        if i == low_at and c.low < 0:
            ly = y(c.low)
            right = cx > (W - RIGHT) * 0.6
            out.append(f'<circle cx="{cx:.1f}" cy="{ly:.1f}" r="2.6" class="hy-lowdot"/>'
                       f'<text x="{cx + (-6 if right else 6):.1f}" y="{min(ly + 12, PRICE_BOTTOM - 2):.1f}" '
                       f'class="hy-tag hy-tag--low" text-anchor="{"end" if right else "start"}">'
                       f'Lowest {escape(formatting.rupees(c.low))}</text>')
        month = c.period[:7]
        if month != last_month:
            if frame == "month":
                text = month[:4] if (month.endswith("-01") or i == 0) else None
            else:
                text = month[:4] if month.endswith("-01") else date(int(month[:4]), int(month[5:]), 1).strftime("%b")
            if text and cx - last_x >= 28:
                anchor = ' text-anchor="start"' if cx < 18 else ""
                out.append(f'<text x="{max(cx, LEFT):.1f}" y="{H - 6}" class="hy-axis hy-axis--x"{anchor}>{text}</text>')
                last_x = cx
            last_month = month
    out.append(f'<line x1="{LEFT}" x2="{W - RIGHT}" y1="{VOL_BOTTOM}" y2="{VOL_BOTTOM}" class="hy-grid"/>'
               f'<text x="{W - RIGHT + 6}" y="{VOL_TOP + 8}" class="hy-axis">{formatting.count(most)} trades</text>'
               f'<text x="{W - RIGHT + 6}" y="{VOL_BOTTOM}" class="hy-axis">0</text>')
    last = cs[-1].close
    out.append(f'<rect x="{W - RIGHT + 1}" y="{y(last) - 8:.1f}" width="{RIGHT - 1}" height="16" rx="3" '
               f'class="hy-last hy-last--{formatting.tone(last)}"/>'
               f'<text x="{W - RIGHT + 5}" y="{y(last) + 4:.1f}" class="hy-last-text">{short(last)}</text></svg>')
    return Markup("".join(out))


def build(trips: list[mx.Trip], imp, book: str | None = None, tf: str | None = None) -> dict:
    """Everything the card draws, decided here; the template computes nothing."""
    gross = not getattr(imp, "fees_available", False)
    runs = mx.running_results(trips)
    by_name = {"All": trips} | dict(mx.book_groups(trips))
    named = sorted((r for r in runs[1:] if r.trades >= mx.NAMED_BOOK_MINIMUM and r.book != mx.OTHER_OPTIONS),
                   key=lambda r: (-r.trades, r.book))
    other = [r for r in runs[1:] if r.book == mx.OTHER_OPTIONS and r.trades >= mx.NAMED_BOOK_MINIMUM]
    shown = [runs[0], *named, *other]
    run = next((r for r in shown if slug(r.book) == book), shown[0])
    frame = FRAMES.get(tf or "") or default_frame(run)
    view = {
        "anchor": ANCHOR,
        "gross": gross,
        "books": [{"name": r.book, "href": href(r.book, frame), "on": r is run} for r in shown],
        "frames": [{"name": FRAME_NAME[f], "href": href(run.book, f), "on": f == frame} for f in mx.TIMEFRAMES],
        "frame": frame,
        "enough": bool(run.candles[frame]),
        "run": run,
    }
    if not view["enough"]:
        return view

    mine = by_name[run.book]
    every = run.candles[frame]
    shown_candles = every[-WINDOW:]
    opens = _day_of(mine, frame)
    last = shown_candles[-1]
    export = getattr(imp, "export_date", None)
    so_far = bool(export) and frame != "day" and period_end(last.period, frame) > date.fromisoformat(export)
    view.update({
        "first_day": min(t.trading_day for t in mine),
        "last_day": max(t.exit_ts.date() for t in mine).isoformat(),
        "trades": run.trades,
        "total": run.total,
        "strike": run.strike.rate_percent,
        "even": run.even.percent,
        "drop": run.drop.value,
        "high": run.high.value,
        "drop_day": _day_closed(mine, run.drop.to_day),
        "last": last,
        "last_label": label(last.period, frame),
        "last_words": f"this {frame} so far" if so_far else f"the last {frame}",
        "cut": (len(shown_candles), len(every)) if len(every) > WINDOW else None,
        "chart": chart(run, frame, opens),
        "rows": [{"label": label(c.period, frame), "candle": c, "opens": f"/mirror/day/{opens[c.period]}"}
                 for c in reversed(shown_candles)],
    })
    return view
