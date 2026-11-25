"""Your day on the market chart.

The day page draws the underlying's 5-minute candles for that trading day, folded at page time
from that one day's 1-minute file (997): this is the one place a page reads bars, and it reads one
day, never a loop over days. His trades sit on it, marked at the underlying's close of the entry
and exit minutes (not at his option's price), numbered in entry order across the day's list. Under
each trade go the figures 999 stored, never worked out here: how far the market went his way, how
far against him, and what he took, in points.

* **One chart per underlying** he opened a trade on that day; with more than one, chips pick it
  (``?u=<underlying>#chart``), the underlying with the most trades first.
* **A day not held** says so ("isn't in yet" for a stock's day not fetched or a day after the
  series; "we don't hold" for a day before it) and the trades show as ever. The page never fetches.
* **Crude on another month's contract** (999's stored reason) gets no marks; the chart still shows,
  because it is the market he watched, and the line under it counts them.
* Drawn with the shared toolkit (``charts``): time labels and the text table. The price labels are
  points, not rupees, so they are written here as counts, not with ``charts.short``.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from markupsafe import Markup

from services.production.api import charts, formatting
from services.production.api.figures import Figure
from services.production.market import sync
from services.production.prices import layer

IST = timezone(timedelta(hours=5, minutes=30))
CRUDE_MONTH_REASON = "contract month differs from the near-month series"
"""999's own reason, word for word (a test holds the two together)."""
NOT_IN = "The market for this day isn't in yet"
NOT_HELD = "We don't hold the market for this day"
CRUDE_LINE = "Trades on the next month's contract are not marked: the chart is this month's future."

WIDTH, HEIGHT = 358, 200
TOP, BOTTOM, LEFT, RIGHT = 10, 22, 4, 50
MARK_TAP = 16  # a mark's tap target, in px
FIVE = 5

_BASE: dict[str, layer.Prices] = {}


def prices() -> layer.Prices:
    """The layer for one request: profiles loaded once per process, today's manifests read fresh."""
    key = str(layer.market_dir())
    if key not in _BASE:
        _BASE[key] = layer.Prices(data_dir=layer.market_dir())
    return _BASE[key].fresh()


@dataclass(frozen=True)
class Candle:
    start: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal


def fold(series, day: date) -> list[Candle]:
    """The day's 1-minute bars as 5-minute candles: open of the first minute of the five, close of
    the last, high and low over them. A five with no bars is a gap, never filled."""
    groups: dict[datetime, list] = {}
    for t in series.minutes(day):
        groups.setdefault(t.replace(minute=t.minute - t.minute % FIVE), []).append(series.bar(t))
    return [Candle(k, bars[0].open, max(b.high for b in bars), min(b.low for b in bars), bars[-1].close)
            for k, bars in sorted(groups.items())]


@dataclass
class Mark:
    number: int
    side: str  # "in" or "out"
    at: datetime
    close: Decimal
    tone: str
    x: float = 0.0
    y: float = 0.0


@dataclass
class Row:
    number: int
    trip_id: str
    instrument: str
    entry: str
    exit: str
    note: str | None
    way: Decimal | None = None
    against: Decimal | None = None
    took: Decimal | None = None
    reason: str | None = None
    entry_close: Decimal | None = None
    exit_close: Decimal | None = None
    underlying: str | None = None
    marks: list[Mark] = field(default_factory=list)


def _minute(ts: datetime) -> datetime:
    return ts.astimezone(IST).replace(tzinfo=None, second=0, microsecond=0)


def _close_at(series, minutes: list[datetime], t: datetime) -> Decimal | None:
    """The close of that minute, or of the last minute before it that has a bar."""
    bar = series.bar(t)
    if bar is not None:
        return bar.close
    earlier = [m for m in minutes if m <= t]
    return series.bar(earlier[-1]).close if earlier else None


def _decimal(text: str | None) -> Decimal | None:
    return None if text is None else Decimal(text)


def _state(series, underlying: str, day: date) -> str | None:
    """The line the chart shows instead of candles, or None when the day is there to draw."""
    stock = underlying not in sync.KEPT_WHOLE
    if series is None:
        return NOT_IN if stock else NOT_HELD
    if isinstance(series, layer.DaySeries):
        if not series.held(day):
            return NOT_IN if stock or day > series.manifest.as_of else NOT_HELD
        return NOT_HELD if series.problem(day) else None
    return None if series.covers(day) else NOT_HELD


def _when(t: datetime, day: date) -> str:
    local = t.astimezone(IST)
    return f"{local:%H:%M}" if local.date() == day else f"{formatting.day(local.date().isoformat())} {local:%H:%M}"


def build(prices: layer.Prices, day: date, trips: list, legs: dict[str, tuple[str, str]],
          figures: dict, chosen: str | None) -> dict | None:
    """Everything the chart section draws. None when no trade that day has an underlying."""
    iso = day.isoformat()
    opened = sorted((t for t in trips if t.trading_day == iso), key=lambda t: (t.entry_ts, t.trip_id))
    earlier = sorted((t for t in trips if t.trading_day < iso and t.exit_ts.astimezone(IST).date() == day),
                     key=lambda t: (t.entry_ts, t.trip_id))

    def underlying(t):
        exchange, symbol = legs.get(t.trip_id, (None, None))
        return prices.underlying_of(exchange, symbol) if exchange and symbol else None

    counts = Counter(u for u in (underlying(t) for t in opened) if u)
    if not counts:
        return None
    order = sorted(counts, key=lambda u: (-counts[u], u))
    shown = chosen if chosen in order else order[0]

    rows = []
    for n, t in enumerate(opened + earlier, start=1):
        fig = figures.get(t.trip_id)
        exit_day = t.exit_ts.astimezone(IST).date()
        note = (f"opened {formatting.day(t.trading_day)}" if t in earlier
                else f"closed on {formatting.day(exit_day.isoformat())}" if exit_day != day else None)
        instrument = t.lines[0].instrument if t.lines else t.symbol
        rows.append(Row(
            number=n, trip_id=t.trip_id, instrument=instrument, entry=_when(t.entry_ts, day),
            exit=_when(t.exit_ts, day), note=note, underlying=underlying(t),
            way=_decimal(getattr(fig, "way", None)), against=_decimal(getattr(fig, "against", None)),
            took=_decimal(getattr(fig, "took", None)), reason=getattr(fig, "reason", None)))

    series = prices.series(shown)
    message = _state(series, shown, day)
    view = {"chips": [{"underlying": u, "href": f"?u={u}#chart", "current": u == shown} for u in order]
            if len(order) > 1 else [],
            "underlying": shown, "message": message, "rows": rows, "unmarked": 0,
            "crude_line": CRUDE_LINE, "svg": None, "table": None, "day": None}
    if message:
        return view

    candles = fold(series, day)
    minutes = series.minutes(day)
    by_trip = {t.trip_id: t for t in opened + earlier}
    marks: list[Mark] = []
    for row in rows:
        if row.underlying != shown:
            continue
        if row.reason == CRUDE_MONTH_REASON:
            view["unmarked"] += 1
            continue
        t = by_trip[row.trip_id]
        tone = formatting.tone(t.net)
        if t in opened:
            at = _minute(t.entry_ts)
            row.entry_close = _close_at(series, minutes, at)
            if row.entry_close is not None:
                row.marks.append(Mark(row.number, "in", at, row.entry_close, tone))
        if t.exit_ts.astimezone(IST).date() == day:
            at = _minute(t.exit_ts)
            row.exit_close = _close_at(series, minutes, at)
            if row.exit_close is not None:
                row.marks.append(Mark(row.number, "out", at, row.exit_close, tone))
        marks.extend(row.marks)

    opens, ends = prices.session(shown)
    view["svg"] = _draw(candles, rows, marks, day, opens, ends) if candles else None
    view["day"] = None if not candles else {
        "open": candles[0].open, "high": max(c.high for c in candles),
        "low": min(c.low for c in candles), "close": candles[-1].close}
    view["table"] = charts.text_table(
        [(Figure(r.number, "trade"), r.entry, _points(r.entry_close), r.exit, _points(r.exit_close),
          _points(r.way), _points(r.against), _points(r.took))
         for r in rows if r.underlying == shown and r.reason != CRUDE_MONTH_REASON],
        ("Trade", "Opened", "Market then", "Closed", "Market then", "Went your way", "Against you", "You took"),
        caption=f"{shown}, your trades on the chart, in points")
    return view


def _points(value: Decimal | None):
    return "—" if value is None else Figure(value, "points")


def _draw(candles: list[Candle], rows: list[Row], marks: list[Mark], day: date, opens: time,
          ends: time) -> Markup:
    """The chart: candles, a line from each trade's entry to its exit, and the marks over them."""
    start = datetime.combine(day, opens)
    span = max(1, int((datetime.combine(day, ends) - start).total_seconds() // 60))
    plot_w, plot_h = WIDTH - LEFT - RIGHT, HEIGHT - TOP - BOTTOM
    lo = min([c.low for c in candles] + [mk.close for mk in marks])
    hi = max([c.high for c in candles] + [mk.close for mk in marks])
    pad = (hi - lo) * Decimal("0.08") or Decimal(1)
    lo, hi = lo - pad, hi + pad

    def x(t: datetime) -> float:
        return LEFT + plot_w * min(span, max(0, (t - start).total_seconds() / 60)) / span

    def y(v: Decimal) -> float:
        return TOP + plot_h * float((hi - v) / (hi - lo))

    slot = plot_w * FIVE / span
    body = max(1.0, slot * 0.7)
    out = [(f'<svg class="dc-chart" viewBox="0 0 {WIDTH} {HEIGHT}" width="100%" role="img" '
            f'aria-label="The market that day, in five-minute candles, with your trades on it">')]
    for v in (hi - pad, (hi + lo) / 2, lo + pad):
        out.append(f'<line x1="{LEFT}" x2="{LEFT + plot_w}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="ch-grid"/>'
                   f'<text x="{LEFT + plot_w + 4}" y="{y(v) + 4:.1f}" class="ch-axis">{formatting.count(v)}</text>')
    for c in candles:
        cx = x(c.start) + slot / 2
        kind = "up" if c.close >= c.open else "down"
        top, bottom = y(max(c.open, c.close)), y(min(c.open, c.close))
        out.append(f'<line x1="{cx:.1f}" x2="{cx:.1f}" y1="{y(c.high):.1f}" y2="{y(c.low):.1f}" '
                   f'class="dc-wick dc-wick--{kind}"/>'
                   f'<rect x="{cx - body / 2:.1f}" y="{top:.1f}" width="{body:.1f}" '
                   f'height="{max(1.0, bottom - top):.1f}" class="dc-body dc-body--{kind}"/>')
    for mk in marks:
        mk.x, mk.y = x(mk.at) + slot / 2, y(mk.close)
    _nudge(marks)
    for row in rows:
        if len(row.marks) == 2:
            a, b = row.marks
            out.append(f'<line x1="{a.x:.1f}" y1="{a.y:.1f}" x2="{b.x:.1f}" y2="{b.y:.1f}" '
                       f'class="dc-line dc-line--{a.tone}"/>')
    for mk in marks:
        out.append(f'<a href="#trade-{mk.number}" data-mark="{mk.number}-{mk.side}" '
                   f'data-close="{mk.close.normalize():f}">'
                   f'<circle cx="{mk.x:.1f}" cy="{mk.y:.1f}" r="{MARK_TAP / 2}" class="dc-tap"/>'
                   f'<circle cx="{mk.x:.1f}" cy="{mk.y:.1f}" r="4" class="dc-mark dc-mark--{mk.side} '
                   f'dc-mark--{mk.tone}"/>'
                   f'<text x="{mk.x:.1f}" y="{mk.y - 7:.1f}" class="dc-number" text-anchor="middle">'
                   f'{mk.number}</text></a>')
    hours = [(x(start + timedelta(minutes=m)), opens.hour * 60 + opens.minute + m)
             for m in range(0, span + 1, 60 if span <= 7 * 60 else 120)]
    out.extend(str(label.svg) for label in charts.time_labels(hours, kind="minute", y=HEIGHT - 6, left=LEFT))
    out.append("</svg>")
    return Markup("".join(out))


def _nudge(marks: list[Mark]) -> None:
    """Marks that would sit on one another move apart, never hidden: each is kept a tap apart."""
    placed: list[Mark] = []
    for mk in sorted(marks, key=lambda k: (k.x, k.y)):
        while any(abs(mk.x - p.x) < MARK_TAP / 2 and abs(mk.y - p.y) < MARK_TAP / 2 for p in placed):
            mk.y = max(TOP, mk.y - MARK_TAP / 2)
            if mk.y == TOP:
                mk.x += MARK_TAP / 2
        placed.append(mk)
