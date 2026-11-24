"""The "Where the money went" page, as its template draws it (TICKET-995).

The figures are decided in ``charges.waterfall``; this words and draws them. The chart is
server-drawn SVG through the chart toolkit (992): its ticks, its axis and its rupee labels, so
it rounds a rupee the way every other chart does. Each bar is a link to the trades behind it.

Decided here:

* **The jolt line** ("Your average winner is ₹A. Each trade pays ₹C in charges.") shows only
  with 30 or more trades in the waterfall (``mx.CLOCK_MINIMUM_TRADES``, the report's own
  minimum). Both figures are over the same trades, the waterfall's: its charges over its
  trades, and ``mx.break_even``'s average winner over those trades. A trade left out of the
  waterfall is in neither.
* **Nothing says what he would have made** without charges. The bars show what happened, in
  order: before charges, each charge, after charges.
"""
from __future__ import annotations

from decimal import Decimal

from markupsafe import Markup, escape

from services.production.api import charts, formatting
from services.production.api import scope_map as S
from services.production.charges import waterfall as W
from services.production.mirror import metrics as mx

KEY = "charges"
JOLT_MINIMUM = mx.CLOCK_MINIMUM_TRADES
"""Trades a waterfall needs before "each trade pays" is said: a rate's own minimum."""

CHART_W, CHART_H, LEFT, RIGHT, TOP, BOTTOM = 358, 220, 6, 58, 10, 210


def step_href(key: str) -> str:
    return S.see_all_href(KEY, charge=key)


def chart(wf: W.Waterfall) -> Markup:
    """Before charges, each charge stepping down, after charges: one bar each."""
    bars: list[tuple[str, Decimal, Decimal, str, str]] = []  # name, from, to, kind, href
    bars.append(("Before charges", Decimal(0), wf.before, "total", S.see_all_href(KEY)))
    level = wf.before
    for s in wf.steps:
        bars.append((s.name, level, level - s.amount, "step", step_href(s.key)))
        level -= s.amount
    bars.append(("After charges", Decimal(0), wf.after, "total", S.see_all_href(KEY)))
    lo = min([Decimal(0)] + [min(a, b) for _, a, b, _, _ in bars])
    hi = max([Decimal(0)] + [max(a, b) for _, a, b, _, _ in bars])
    lo, hi, tick = charts.ticks(lo, hi)
    span = (hi - lo) or tick

    def y(v: Decimal) -> float:
        return TOP + float((hi - v) / span) * (BOTTOM - TOP)

    behind, in_front = charts.axis(lo, hi, tick, y, left=LEFT, right=RIGHT, width=CHART_W,
                                   last=wf.after)
    step = (CHART_W - LEFT - RIGHT) / len(bars)
    out = [(f'<svg class="wf-chart" viewBox="0 0 {CHART_W} {CHART_H}" role="img" '
            f'aria-label="Where the money went: before charges, each charge, after charges">'),
           behind]
    for i, (name, a, b, kind, href) in enumerate(bars):
        top, bottom = sorted((y(a), y(b)))
        x = LEFT + step * i + step * 0.15
        tone = formatting.tone(b) if kind == "total" else "loss"
        amount = b if kind == "total" else b - a
        title = f"{name}: {formatting.rupees(amount)}"
        out.append(f'<a href="{escape(href)}" class="wf-bar wf-bar--{kind} wf-bar--{tone}">'
                   f'<title>{escape(title)}</title>'
                   f'<rect x="{x:.1f}" y="{top:.1f}" width="{step * 0.7:.1f}" '
                   f'height="{max(1.2, bottom - top):.1f}"/></a>')
    out.append(in_front + Markup("</svg>"))
    return Markup("".join(out))


def view(wf: W.Waterfall, ctx: dict) -> dict:
    """Everything the page draws; the template computes nothing."""
    if not wf.included:
        return {"waterfall": wf, "rows": [], "jolt": None, "left_out": wf.left_out}
    jolt = None
    if len(wf.included) >= JOLT_MINIMUM:
        # Both figures over the waterfall's own trades: the line compares them.
        priced = set(wf.included)
        winner = mx.break_even([t for t in ctx["trips"] if t.trip_id in priced]).average_winner
        jolt = {"winner": winner, "per_trade": wf.per_trade}
    return {
        "waterfall": wf,
        "before": wf.before,
        "after": wf.after,
        "rows": [{"name": s.name, "amount": s.amount, "stepped": -s.amount,
                  "href": step_href(s.key), "trades": len(s.trip_ids)} for s in wf.steps],
        "svg": chart(wf),  # the page's own; "chart" is the card's, from CHARTS
        "jolt": jolt,
        "left_out": wf.left_out,
        "included": len(wf.included),
        "all_href": S.see_all_href(KEY),
    }
