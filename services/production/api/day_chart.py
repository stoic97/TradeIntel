"""A day's running result, drawn: the one component every page draws a day with.

The day page draws it full width, with its axis, each trade as a dot sized by lots where it
closed, and the best and worst it stood marked. A dot is ringed where it switched between call
and put from the trade opened before it: switches are counted in the order they were opened,
as the "You switched ..." sentence counts them, so a ring can sit between two dots on one side,
and the page says which order the rings mark. Each of
the five worst days draws the same path small, as a line. The path itself is
``metrics.day_path``'s; nothing here is counted, and a sentence says the peak, the trough and
the close in counts, never a cause.
"""
from __future__ import annotations

import re
from datetime import datetime, time
from decimal import Decimal
from functools import lru_cache

from markupsafe import Markup

from services.production.api import charts, formatting
from services.production.api.figures import Figure
from services.production.ctr.profiles import registry as profiles
from services.production.mirror import loader
from services.production.mirror import metrics as mx

W, H = 350, 150  # the fact page's width; tall enough for a day's swing on a phone
LEFT, RIGHT, TOP, BOTTOM = 8, 54, 12, 12  # RIGHT holds the price axis and the close's tag
MINI_W, MINI_H = 120, 32  # as the worst-days block drew its line before


@lru_cache(maxsize=1)
def _closes() -> dict[str, time]:
    """Each symbol's session close from its profile; a symbol two profiles disagree on has none."""
    ends: dict[str, set[time]] = {}
    for (_exchange, symbol), profile in profiles.load_all(loader.PROFILE_DIR).items():
        if symbol != profiles.SEGMENT_WILDCARD:
            ends.setdefault(symbol, set()).add(profile.session_end)
    return {symbol: next(iter(e)) for symbol, e in ends.items() if len(e) == 1}


def _later(p: mx.DayPoint, day: str) -> bool:
    """Closed on a later day than the day the page is."""
    return bool(day) and p.exit_ts.date().isoformat() != day


def _x_of(path: mx.DayPath, w: float):
    """Time across the day. The axis ends at the last close of the day; when a trade closes on a
    later day, it ends at his instrument's session close instead, and that trade is drawn at the
    right edge (marked), so one overnight hold cannot squeeze the day's own dots to the left."""
    start = path.started
    day = _opened_on(path)
    own = [p.exit_ts for p in path.points if not _later(p, day)]
    end = max(own + [start])
    if len(own) < len(path.points):
        close = _closes().get(path.points[0].trip.symbol)
        if close is not None:
            end = max(end, datetime.combine(start.date(), close, start.tzinfo))
    span = (end - start).total_seconds() or 1.0
    inner = w - LEFT - RIGHT

    def x(moment) -> float:
        return LEFT + min((moment - start).total_seconds(), span) / span * inner
    return x


def mini(path: mx.DayPath) -> Markup:
    """The day as a small line, first trade to last, with zero marked: the worst-days block's."""
    values = [0.0, *(float(p.running) for p in path.points)]
    low, high = min(values), max(values)
    spread = (high - low) or 1.0
    steps = max(len(values) - 1, 1)

    def y(v: float) -> str:
        return f"{(high - v) / spread * (MINI_H - 4) + 2:.1f}"

    points = " ".join(f"{i / steps * MINI_W:.1f},{y(v)}" for i, v in enumerate(values))
    return Markup(
        f'<svg class="day-block__line" data-daypath viewBox="0 0 {MINI_W} {MINI_H}" '
        f'width="{MINI_W}" height="{MINI_H}" aria-hidden="true">'
        f'<line class="day-block__zero" x1="0" x2="{MINI_W}" y1="{y(0.0)}" y2="{y(0.0)}"/>'
        f'<polyline class="day-block__run" fill="none" points="{points}"/></svg>'
    )


def _money(value: Decimal, *, signed: bool) -> Markup:
    figure = Figure(value, "rupees")
    return Markup('<span class="num">{}</span>').format(
        formatting._FIGURE_FILTERS["rupees"](figure, signed=signed))


def _opened_on(path: mx.DayPath) -> str:
    """The day the page is: the day he opened these trades (definitions section 1)."""
    return path.points[0].trip.trading_day if path.points else ""


def _when(moment, day: str) -> str:
    """A close on the day itself reads 09:30; a close on a later day carries its date, 5 Mar 09:20."""
    if not day or moment.date().isoformat() == day:
        return moment.strftime("%H:%M")
    return f"{moment.day} {moment:%b %H:%M}"


def _said(path: mx.DayPath) -> Markup:
    """"Up ₹500 at 09:30 at best; down ₹800 at 10:00 at worst; finished −₹700." Counts only."""
    parts: list[Markup] = []
    if path.peak is not None:
        parts.append(Markup("up {} at {} at best").format(
            _money(path.peak.running, signed=False), _when(path.peak.exit_ts, _opened_on(path))))
    if path.trough is not None:
        parts.append(Markup("down {} at {} at worst").format(
            _money(-path.trough.running, signed=False), _when(path.trough.exit_ts, _opened_on(path))))
    parts.append(Markup("finished {}").format(_money(path.close, signed=True)))
    sentence = Markup("; ").join(parts) + Markup(".")
    return Markup(str(sentence)[0].upper()) + Markup(str(sentence)[1:])


def _instrument(t: mx.Trip) -> str:
    return t.lines[0].instrument if t.lines else t.symbol


def view(path: mx.DayPath, w: float = W, h: float = H) -> dict:
    """The day page's chart, its sentence, and its text table for a screen reader."""
    values = [Decimal(0), *(p.running for p in path.points)]
    lo, hi, tick = charts.ticks(min(values), max(values))
    span = (hi - lo) or Decimal(1)

    def y(v: Decimal) -> float:
        return TOP + float((hi - Decimal(v)) / span) * (h - TOP - BOTTOM)

    day = _opened_on(path)
    x = _x_of(path, w)
    ref = (path.peak.running, f"best {_when(path.peak.exit_ts, day)}") if path.peak is not None else None
    back, front = charts.axis(lo, hi, tick, y, left=LEFT, right=RIGHT, width=w, ref=ref,
                              last=path.close)
    tag_y = y(path.close)  # an axis label the close's tag would sit on is left out
    back = Markup(re.sub(
        r'<text x="[^"]+" y="([^"]+)" class="ch-axis">[^<]*</text>',
        lambda m: "" if abs(float(m.group(1)) - 4 - tag_y) < 12 else m.group(0), str(back)))
    line = [f"{x(path.started):.1f},{y(Decimal(0)):.1f}"]
    line += [f"{x(p.exit_ts):.1f},{y(p.running):.1f}" for p in path.points]
    most = max([p.lots for p in path.points] + [1])
    dots = []
    for p in path.points:
        tone = "gain" if p.trip.net > 0 else "loss" if p.trip.net < 0 else "level"
        cls = f"daychart__dot daychart__dot--{tone}" + (" daychart__dot--switched" if p.switched else "")
        r = 2.5 + 2.5 * (max(p.lots, 1) / most)
        dots.append(f'<circle class="{cls}" cx="{x(p.exit_ts):.1f}" cy="{y(p.running):.1f}" r="{r:.1f}"/>')
        if _later(p, day):  # closed on a later day: drawn at the edge, and said when
            ex, ey = x(p.exit_ts), y(p.running)
            dots.append(f'<g class="daychart__later"><title>closed {_when(p.exit_ts, day)}</title>'
                        f'<path d="M{ex - 3:.1f},{ey - r - 7:.1f} L{ex:.1f},{ey - r - 3:.1f} '
                        f'L{ex + 3:.1f},{ey - r - 7:.1f}"/></g>')  # a caret above, clear of the close's tag
    trough = ""
    if path.trough is not None:
        ty = y(path.trough.running)
        trough = (f'<line x1="{LEFT}" x2="{w - RIGHT}" y1="{ty:.1f}" y2="{ty:.1f}" class="ch-ref"/>'
                  f'<text x="{w - RIGHT - 2}" y="{ty + 12:.1f}" class="ch-tag" text-anchor="end">'
                  f'worst {_when(path.trough.exit_ts, day)}</text>')
    svg = Markup(
        f'<svg class="daychart" data-daypath viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
        f'role="img" aria-label="Your running result through the day, trade by trade">'
        f"{back}{trough}"
        f'<polyline class="daychart__run" fill="none" points="{" ".join(line)}"/>'
        f'{"".join(dots)}{front}</svg>'
    )
    rows = [
        (_when(p.exit_ts, day), _instrument(p.trip), Figure(p.trip.net, "rupees"),
         Figure(p.running, "rupees"))
        for p in path.points
    ]
    table = charts.text_table(rows, ("Closed", "Trade", "Result", "Running result"),
                              caption="The day, trade by trade, as each closed")
    closed_later = sum(1 for p in path.points if day and p.exit_ts.date().isoformat() != day)
    return {"svg": svg, "said": _said(path), "table": table, "closed_later": closed_later,
            "switched": sum(p.switched for p in path.points)}
