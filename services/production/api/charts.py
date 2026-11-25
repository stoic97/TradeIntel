"""One chart toolkit for every Scope chart (TICKET-992).

Pure functions: numbers in, numbers or SVG markup out. No request, no database, no template.
Every chart a trader reads draws its axis labels, ticks, axis, time labels, cell colours,
hatching and text table here, so two charts can't round the same rupee two ways.

Decided here:

* **An axis label** is written as a trader's chart writes it: ₹20k, −₹47.5k, ₹1.2L. A tick that
  isn't a whole thousand keeps its half, never rounded to the next thousand.
* **Ticks** step by 1, 2, 2.5 or 5 times a power of ten, about five of them, never below a
  rupee, and the range widens to whole steps.
* **Colour belongs to rupees alone.** A rupee value is green or red by its sign, in four steps
  by its size; a count or a rate is ink, whatever it is; a zero or an empty cell is the surface.
* **A rate axis** (a win rate, "N of 100") is labelled by its whole number, with no rupee and no
  percent sign; ``rate_scale`` places a rate, so a bar and a line chart of rates share one scale.
* **Hatching** is the kit's own pattern (``chart__hatch``), the one the clock uses for an hour
  with too few trades.
* **Every chart has its figures as text**, in a plain table, each through ``Figure``.

Classes are ``<prefix>-<role>``. The prefix is ``ch`` (styled in ``app.css`` under
``/* charts toolkit */``); the home card (987) passes its own ``hy`` so its markup stays as it was.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

from markupsafe import Markup, escape

from services.production.api import formatting
from services.production.api.figures import Figure, through_figure

LAKH = Decimal(10) ** 5
"""The Indian hundred thousand an axis label counts in."""

THOUSAND = Decimal(10) ** 3
STEPS = (Decimal(1), Decimal(2), Decimal("2.5"), Decimal(5), Decimal(10))
TICKS = 5
"""About this many steps on an axis."""

MIN_GAP = 28
"""Pixels between two time labels at the 358-px drawing width; a closer one is skipped."""

TONE_STEPS = 4
RUPEE_NOUNS = frozenset({"rupees", "rupee"})


# ---------- labels and ticks ----------

def short(value: Decimal) -> str:
    """An axis label, as a trader's chart writes it: ₹20k, −₹47.5k, ₹1.5L."""
    if not value:
        return "₹0"
    sign = formatting.MINUS if value < 0 else ""
    a = abs(value)
    if a >= LAKH:
        lakh = a / LAKH
        return f"{sign}₹{lakh.normalize():f}L" if lakh == lakh.to_integral_value() else f"{sign}₹{lakh:.1f}L"
    if a >= THOUSAND:
        k = a / THOUSAND
        return f"{sign}₹{int(k)}k" if k == k.to_integral_value() else f"{sign}₹{k:.1f}k"
    return f"{sign}₹{int(a)}"


def ticks(lo: Decimal, hi: Decimal) -> tuple[Decimal, Decimal, Decimal]:
    """Round steps covering lo..hi: (new lo, new hi, step). The step is 1, 2, 2.5 or 5 times a
    power of ten, never under a rupee, chosen so about TICKS of them span the range."""
    raw = (Decimal(hi) - Decimal(lo)) / TICKS or Decimal(1)
    mag = Decimal(10) ** max(0, raw.adjusted())
    tick = next(m * mag for m in STEPS if m * mag >= raw)
    lo = (Decimal(lo) / tick).to_integral_value(rounding=ROUND_FLOOR) * tick
    hi = (Decimal(hi) / tick).to_integral_value(rounding=ROUND_CEILING) * tick
    return lo, hi, tick


# ---------- the price axis ----------

def axis(lo: Decimal, hi: Decimal, tick: Decimal, y: Callable[[Decimal], float], *, left: float,
         right: float, width: float, ref: tuple[Decimal, str] | None = None,
         last: Decimal | None = None, p: str = "ch", ref_cls: str | None = None,
         hide_under_last: bool = False) -> tuple[Markup, Markup]:
    """The right-hand price axis, as two layers: what sits behind the marks (gridlines with their
    labels, the ₹0 line when ₹0 is in range, a dashed reference line with its label) and what
    sits in front (the last value's tag, coloured by its sign).

    ``hide_under_last`` drops a gridline's label that the last value's 16 px tag would sit on
    (the gridline itself stays), so the two never print over each other."""
    x0, x1 = left, width - right
    back = []
    v = lo
    under = y(last) if (hide_under_last and last is not None) else None
    while v <= hi:
        label = (f'<text x="{x1 + 6}" y="{y(v) + 4:.1f}" class="{p}-axis">{short(v)}</text>'
                 if under is None or abs(y(v) - under) >= 16 else "")
        back.append(f'<line x1="{x0}" x2="{x1}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="{p}-grid"/>' + label)
        v += tick
    if lo <= 0 <= hi:
        zero = y(Decimal(0))
        back.append(f'<line x1="{x0}" x2="{x1}" y1="{zero:.1f}" y2="{zero:.1f}" class="{p}-zero"/>')
    if ref is not None and lo <= ref[0] <= hi:
        ry = y(ref[0])
        back.append(f'<line x1="{x0}" x2="{x1}" y1="{ry:.1f}" y2="{ry:.1f}" class="{ref_cls or p + "-ref"}"/>'
                    f'<text x="{x1 - 2}" y="{ry - 4:.1f}" class="{p}-tag" text-anchor="end">{escape(ref[1])}</text>')
    front = ""
    if last is not None:
        ly = y(last)
        front = (f'<rect x="{x1 + 1}" y="{ly - 8:.1f}" width="{right - 1}" height="16" rx="3" '
                 f'class="{p}-last {p}-last--{formatting.tone(last)}"/>'
                 f'<text x="{x1 + 5}" y="{ly + 4:.1f}" class="{p}-last-text">{short(last)}</text>')
    return Markup("".join(back)), Markup(front)


# ---------- the rate axis ----------

def rate_scale(lo, hi, start: float, end: float) -> Callable[[object], float]:
    """Where a rate ("N of 100") sits between two edges of a drawing: ``lo`` at ``start``, ``hi``
    at ``end``. Across a bar the edges are 0 and its width; up a chart, the foot then the top.
    A range of one value puts it at ``start``."""
    span = (hi - lo) or 1
    return lambda v: start + (v - lo) * (end - start) / span


def rate_axis(lo, hi, tick, y: Callable[[object], float], *, left: float, right: float,
              width: float, p: str = "ch") -> Markup:
    """The right-hand axis of a chart of rates: a gridline at each tick with its label, written as
    the whole number of 100 it is, with no rupee and no percent sign."""
    x0, x1 = left, width - right
    out = []
    v = lo
    while v <= hi:
        out.append(f'<line x1="{x0}" x2="{x1}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="{p}-grid"/>'
                   f'<text x="{x1 + 6}" y="{y(v) + 4:.1f}" class="{p}-axis">{v}</text>')
        v += tick
    return Markup("".join(out))


def rate_axis_across(lo, hi, tick, x: Callable[[object], float], *, top: float, bottom: float,
                     p: str = "ch") -> Markup:
    """The axis along a bar of rates: a gridline at each tick from ``top`` to ``bottom``, and its
    label under the bar as the whole number of 100 it is. The two edge labels hang inward, so
    neither runs past the drawing."""
    out = []
    v = lo
    while v <= hi:
        anchor = ' text-anchor="start"' if v == lo else ' text-anchor="end"' if v == hi else ""
        out.append(f'<line x1="{x(v):.1f}" x2="{x(v):.1f}" y1="{top}" y2="{bottom}" class="{p}-grid"/>'
                   f'<text x="{x(v):.1f}" y="{bottom + 12}"{anchor} class="{p}-axis {p}-axis--x">{v}</text>')
        v += tick
    return Markup("".join(out))


def rate_chart(cls: str, width: float, height: float, label: str, parts: Iterable) -> Markup:
    """A chart of rates as one drawing: its class, its size, the name a screen reader reads, then
    its parts in order. The drawing scales to its card, so a phone never scrolls it."""
    return Markup(f'<svg class="{cls}" viewBox="0 0 {width} {height}" width="100%" role="img" '
                  f'aria-label="{escape(label)}">' + "".join(str(part) for part in parts) + "</svg>")


# ---------- time labels ----------

@dataclass(frozen=True)
class Label:
    index: int
    """Which point it belongs to, so a chart can draw it beside that point."""
    x: float
    text: str
    svg: Markup


def _month_text(key: str, kind: str, first: bool) -> str | None:
    year, month = key[:4], key[5:7]
    if kind == "year":
        return year if (month == "01" or first) else None
    return year if month == "01" else date(int(year), int(month), 1).strftime("%b")


def time_labels(points: Sequence[tuple[float, object]], *, kind: str, y: float, left: float = 6,
                gap: float = MIN_GAP, p: str = "ch") -> list[Label]:
    """Labels under a time axis, skipping any closer than ``gap`` to the one before.

    ``points`` are (x, key) in order. ``kind``:
    * ``month``: key an ISO date or period; the first point of each month, its short name,
      January as its year;
    * ``year``: the first point, and each January, as the year;
    * ``minute``: key minutes since midnight, every point, as 09:15;
    * ``offset``: key minutes after an event, every point, as 0, 5 … 30.
    """
    out: list[Label] = []
    last_month, last_x = None, -99.0
    for i, (x, key) in enumerate(points):
        if kind in ("month", "year"):
            month = str(key)[:7]
            if month == last_month:
                continue
            last_month = month
            text = _month_text(month, kind, i == 0)
        elif kind == "minute":
            text = f"{int(key) // 60:02d}:{int(key) % 60:02d}"
        elif kind == "offset":
            text = str(int(key))
        else:
            raise ValueError(f"unknown time label kind {kind!r}")
        if text and x - last_x >= gap:
            anchor = ' text-anchor="start"' if x < 18 else ""
            svg = Markup(f'<text x="{max(x, left):.1f}" y="{y}" class="{p}-axis {p}-axis--x"{anchor}>{text}</text>')
            out.append(Label(i, x, text, svg))
            last_x = x
    return out


# ---------- cells ----------

def _rupees(value) -> Decimal | None:
    """The value as rupees, or None when it isn't rupees (a count, a rate) and must stay ink."""
    if isinstance(value, Figure):
        return Decimal(value.value) if value.noun in RUPEE_NOUNS else None
    if isinstance(value, Decimal):
        return value
    return None


def cell_tone(value, scale: Decimal, p: str = "ch") -> str:
    """A heatmap or calendar cell's classes. Rupees are green or red by sign, in up to four steps
    of strength by size against ``scale``; zero or empty is the surface; anything that isn't
    rupees, a count or a rate, is ink."""
    if value is None or (isinstance(value, Figure) and value.value is None):
        return f"{p}-cell {p}-cell--surface"
    rupees = _rupees(value)
    if rupees is None:
        return f"{p}-cell {p}-cell--ink"
    if rupees == 0:
        return f"{p}-cell {p}-cell--surface"
    scale = abs(Decimal(scale))
    share = abs(rupees) / scale if scale else Decimal(TONE_STEPS)
    step = min(TONE_STEPS, max(1, int((share * TONE_STEPS).to_integral_value(rounding=ROUND_CEILING))))
    return f"{p}-cell {p}-cell--{'gain' if rupees > 0 else 'loss'}-{step}"


def hatch(x: float, y: float, w: float, h: float) -> Markup:
    """A group under the minimum, hatched with the kit's pattern, as the clock hatches an hour."""
    return Markup(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" class="chart__hatch"/>')


# ---------- the chart as text ----------

_WRITE = {
    "rupees": through_figure(formatting.rupees),
    "rupee": through_figure(formatting.rupees),
    "percent": through_figure(formatting.out_of_a_hundred),
}
_COUNT = through_figure(formatting.count)


def _cell(value) -> str:
    if isinstance(value, Figure):
        write = _WRITE.get(value.noun, _COUNT)
        return f'<td class="table__num num">{escape(write(value))}</td>'
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        raise TypeError(f"a number in a chart's table must be a Figure: {value!r}")
    return f"<td>{escape(value)}</td>"


def text_table(rows: Iterable[Sequence], headings: Sequence[str], *, caption: str | None = None,
               p: str = "ch") -> Markup:
    """A chart's figures as a plain table, for a screen reader and for anyone who reads numbers
    rather than shapes. Text cells are labels; every number is a Figure."""
    out = [f'<table class="table {p}-table">']
    if caption:
        out.append(f"<caption>{escape(caption)}</caption>")
    out.append("<thead><tr>" + "".join(f"<th>{escape(h)}</th>" for h in headings) + "</tr></thead><tbody>")
    for row in rows:
        out.append("<tr>" + "".join(_cell(v) for v in row) + "</tr>")
    out.append("</tbody></table>")
    return Markup("".join(out))
