"""Your wins and losses, drawn: the gap to break-even as a bar per book, and each book's win rate
against its break-even rate, year by year.

Reads only what the math page already computes (``mx.math_by_book`` on same-day trades): a
book's win rate and the break-even rate ``mx.break_even`` gives it. Nothing new is decided here.

Decided here:

* **Every rate is shown as "N of 100"**, rounded half up as ``formatting.out_of_a_hundred`` does,
  and **the gap is the difference of the two rates as shown**, so the three numbers on a line
  always add up: "46 of 100 · needs 51 of 100 · 5 more winners in every 100".
* **A book or a year is drawn only with 30 or more same-day trades** (``mx.BOOK_ROW_MINIMUM``,
  the math table's own minimum). A thinner year shows its count and "too few".
* **One scale for every book's years**, so books can be read against each other.
* **Counts only.** No adjective, no "improving": a line says where each rate stood.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from markupsafe import Markup, escape

from services.production.api import charts, formatting
from services.production.api.figures import Figure
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s

W = 358          # the kit's chart width; the SVG scales to the card, so a phone never scrolls
BAR_H = 44        # the bar, then its axis labels underneath
YEARS_H = 132
LEFT, RIGHT, TOP, BOTTOM = 8, 34, 10, 22


def _shown(rate) -> int:
    """A rate as "N of 100" shows it: a whole number, rounded half up."""
    return int(Decimal(str(rate)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _rate(value) -> Markup:
    return Markup('<span class="num">{}</span>').format(
        formatting._FIGURE_FILTERS["out_of_a_hundred"](Figure(value, "percent")))


def _count(value: int, noun: str) -> Markup:
    return Markup('<span class="num">{}</span>').format(
        formatting._FIGURE_FILTERS["count"](Figure(value, noun)))


def _gap_words(gap: int) -> Markup:
    if gap > 0:
        return _count(gap, "winners") + Markup(" more {} in every 100").format(
            "winner" if gap == 1 else "winners")
    if gap < 0:
        return _count(-gap, "of 100") + Markup(" of 100 above break-even")
    return Markup("at break-even")


def _counted(row: mx.MathRow) -> bool:
    return (row.state is s.ResultState.COUNTED_FACT and row.win_percent is not None
            and row.break_even_percent is not None)


def _bar_svg(book: str, win: int, need: int) -> Markup:
    x = charts.rate_scale(0, 100, 0, W)  # the bar runs the whole rate scale, 0 to 100 of 100
    lo, hi = sorted((win, need))
    side = "short" if need > win else "above"
    label = f"{book}: you won {win} of 100; break-even needs {need} of 100"
    return charts.rate_chart("wg-bar", W, BAR_H, label, (
        f'<rect x="0" y="10" width="{W}" height="10" rx="2" class="wg-track"/>',
        charts.rate_axis_across(0, 100, 25, x, top=4, bottom=26),
        f'<rect x="{x(lo):.1f}" y="10" width="{x(hi) - x(lo):.1f}" height="10" class="wg-gap wg-gap--{side}"/>',
        f'<line x1="{x(win):.1f}" x2="{x(win):.1f}" y1="4" y2="26" class="wg-win"/>',
        f'<line x1="{x(need):.1f}" x2="{x(need):.1f}" y1="4" y2="26" class="wg-need"/>',
    ))


def _years_svg(book: str, points: list[dict], lo: int, hi: int, tick: int) -> Markup:
    x0, x1, y0, y1 = LEFT, W - RIGHT, TOP, YEARS_H - BOTTOM
    y = charts.rate_scale(lo, hi, y1, y0)  # upward: lo at the foot, hi at the top
    n = len(points)
    xs = [(x0 + x1) / 2] if n == 1 else [x0 + i * (x1 - x0) / (n - 1) for i in range(n)]
    out = [charts.rate_axis(lo, hi, tick, y, left=LEFT, right=RIGHT, width=W)]
    you = [(xs[i], y(p["win"])) for i, p in enumerate(points)]
    even = [(xs[i], y(p["need"])) for i, p in enumerate(points)]
    # A run of counted years draws as one line; a thin year between two breaks it, so no line
    # claims a rate for a year that had too few trades.
    runs, start = [], 0
    for i in range(1, n + 1):
        if i == n or points[i].get("after_thin"):
            runs.append((start, i))
            start = i
    for a, b in runs:
        if b - a < 2:
            continue
        yo, ev = you[a:b], even[a:b]
        band = " ".join(f"{px:.1f},{py:.1f}" for px, py in yo + ev[::-1])
        out.append(f'<polygon points="{band}" class="wg-band"/>')
        out.append(f'<polyline points="{" ".join(f"{px:.1f},{py:.1f}" for px, py in ev)}" class="wg-even"/>')
        out.append(f'<polyline points="{" ".join(f"{px:.1f},{py:.1f}" for px, py in yo)}" class="wg-you"/>')
    for (xe, ye), (xy, yy) in zip(even, you, strict=True):
        out.append(f'<circle cx="{xe:.1f}" cy="{ye:.1f}" r="3" class="wg-even-dot"/>'
                   f'<circle cx="{xy:.1f}" cy="{yy:.1f}" r="3" class="wg-you-dot"/>')
    for i, p in enumerate(points):
        # the outer two labels hang inward, so neither runs past the drawing's edge
        anchor = "" if n == 1 else ' text-anchor="start"' if i == 0 else ' text-anchor="end"' if i == n - 1 else ""
        out.append(f'<text x="{xs[i]:.1f}" y="{YEARS_H - 6}"{anchor} class="ch-axis ch-axis--x">'
                   f'{escape(p["year"])}</text>')
    return charts.rate_chart("wg-years", W, YEARS_H, f"{book}: win rate against break-even, by year", out)


def view(book_math: list) -> dict:
    """What the math page draws above its tables: a bar per book, its years, and the table."""
    bars, years, rows, values = [], [], [], []
    for book in book_math:
        w = book.whole
        if not _counted(w):
            continue
        win, need = _shown(w.win_percent), _shown(w.break_even_percent)
        line = Markup(" · ").join((_rate(w.win_percent), Markup("needs ") + _rate(w.break_even_percent),
                                   _gap_words(need - win)))
        bars.append({"book": w.label, "win": win, "need": need, "gap": need - win,
                     "line": line, "svg": _bar_svg(w.label, win, need),
                     "counts": Markup("Over all ") + _count(w.trades, "trades")
                     + Markup(" same-day {} in this book.").format("trade" if w.trades == 1 else "trades")})
        points, thin = [], []
        gap = False  # a thin year since the last counted one
        for yr in book.years:
            if _counted(yr):
                p = {"year": yr.label, "win": _shown(yr.win_percent), "need": _shown(yr.break_even_percent),
                     "after_thin": gap and bool(points)}
                gap = False
                points.append(p)
                values += [p["win"], p["need"]]
                rows.append((w.label, yr.label, Figure(yr.trades, "trades"),
                             Figure(yr.win_percent, "percent"), Figure(yr.break_even_percent, "percent")))
            else:
                gap = True
                thin.append(Markup("{}: ").format(yr.label) + _count(yr.trades, "trades")
                            + Markup(" {}, too few").format("trade" if yr.trades == 1 else "trades"))
                rows.append((w.label, yr.label, Figure(yr.trades, "trades"), "too few", ""))
        if points:
            drawn = sum(yr.trades for yr in book.years if _counted(yr))
            counts = (Markup("The lines count all of them.") if drawn == w.trades else
                      Markup("The lines count ") + _count(drawn, "trades")
                      + Markup(" of them: the years with 30 or more."))
            years.append({"book": w.label, "points": points, "thin": Markup("; ").join(thin), "counts": counts})
    lo = hi = tick = 0
    if values:
        lo_d, hi_d, tick_d = charts.ticks(Decimal(min(values)), Decimal(max(values)))
        lo, hi, tick = int(lo_d), int(hi_d), int(tick_d)
        for b in years:
            b["svg"] = _years_svg(b["book"], b["points"], lo, hi, tick)
    table = charts.text_table(rows, ("Book", "Year", "Trades", "You win", "Break even at"),
                              caption="Your win rate against break-even, by year") if rows else Markup("")
    return {"bars": bars, "years": years, "lo": lo, "hi": hi, "table": table}


def register(env) -> None:
    """The math page reads ``wins_gap(book_math)`` from every template, as dial.register does."""
    env.globals["wins_gap"] = view
