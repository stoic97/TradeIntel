"""TICKET-1087: the rest of Your wins and losses, drawn.

1. The gap bar draws through the toolkit's drawing path as the year chart does: the toolkit wraps
   both drawings (``charts.rate_chart``) and draws both axes (``charts.rate_axis`` up the years
   chart, ``charts.rate_axis_across`` along the bar), so the bar is no longer hand-written SVG
   around a borrowed scale.
3. The headline rate and the drawn lines say what they count. The bar's rate is the whole book's
   (the math table's own row, so it stays); the lines leave out a year with too few trades. The
   page now says both counts in words beside the figures.

The record is the made-up one TICKET-1060's test uses, a bought option that closes five minutes
after it opens: a winner sold at 11.00 for +100, a loser at 9.50 for -50, before charges.
Worked by hand:
  WIDGETOIL options  2024  16 wins, 24 losses  40 trades  counted
                     2025  20 wins, 20 losses  40 trades  counted
                     2026   5 wins,  5 losses  10 trades  too few (under 30)
                     whole 90 same-day trades: 41 of 90 = 45.6 -> 46 of 100
                     the lines: 2024 and 2025 only, 40 + 40 = 80 trades
  Stocks and ETFs    2025  10 trades: a book under 30, so no chart at all
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from services.production.api import charts
from tests.helpers.upload import upload

HEADER = Path("data/fixtures/duplicates/clean.csv").read_text(encoding="utf-8").splitlines()[0]
OPTION = "WIDGETOIL 19 NOV 5000 CALL,{side},INTRADAY,MCX,Commodity,100,{price},{value},Traded"
SHARE = "Widget ETF,{side},DELIVERY,NSE,Equity,10,{price},{value},Traded"


def _opened(year: int, i: int) -> tuple[str, str]:
    """The i-th trade of a year: four a day from 4 Aug, twenty minutes apart; open and close."""
    day = 4 + (i // 4) * 7 // 5
    minute = 30 + 20 * (i % 4)
    hh, mm = 9 + minute // 60, minute % 60
    return f"{year}-08-{day:02d},{hh:02d}:{mm:02d}:00", f"{year}-08-{day:02d},{hh:02d}:{mm + 5:02d}:00"


def _option_year(year: int, wins: int, losses: int) -> list[str]:
    rows = []
    for i, win in enumerate([True] * wins + [False] * losses):
        t_open, t_close = _opened(year, i)
        out = "11.00" if win else "9.50"
        rows += [f"{t_open}," + OPTION.format(side="BUY", price="10.00", value="1000.00"),
                 f"{t_close}," + OPTION.format(side="SELL", price=out, value=f"{float(out) * 100:.2f}")]
    return rows


def _share_year(year: int, n: int) -> list[str]:
    rows = []
    for i in range(n):
        t_open, t_close = _opened(year, i)
        t_open, t_close = t_open[:-2] + "02", t_close[:-2] + "02"
        rows += [f"{t_open}," + SHARE.format(side="BUY", price="100.00", value="1000.00"),
                 f"{t_close}," + SHARE.format(side="SELL", price="101.00", value="1010.00")]
    return rows


ROWS = _option_year(2024, 16, 24) + _option_year(2025, 20, 20) + _option_year(2026, 5, 5) + _share_year(2025, 10)


def _section(client) -> str:
    assert upload(client, content=("\n".join([HEADER, *ROWS]) + "\n").encode()).status_code == 303
    html = client.get("/mirror/fact/math").text
    found = re.search(r'<section class="wins-gap".*?</section>', html, re.DOTALL)
    assert found, "no wins-gap section on the math page"
    return found.group(0)


def _plain(markup: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", markup).split())


def _calls(node) -> set[str]:
    return {f"{n.func.value.id}.{n.func.attr}" for n in ast.walk(node)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)}


# ---------- 1. one drawing path for both charts ----------

def test_the_toolkit_draws_a_rate_axis_along_a_bar():
    x = charts.rate_scale(0, 100, 0, 358)
    svg = str(charts.rate_axis_across(0, 100, 25, x, top=4, bottom=26))
    assert re.findall(r'class="ch-axis ch-axis--x"[^>]*>([^<]+)<', svg) == ["0", "25", "50", "75", "100"]
    assert svg.count('class="ch-grid"') == 5
    assert '<line x1="179.0" x2="179.0" y1="4" y2="26" class="ch-grid"/>' in svg
    assert 'text-anchor="start" class="ch-axis ch-axis--x">0<' in svg  # the edge labels hang inward
    assert 'text-anchor="end" class="ch-axis ch-axis--x">100<' in svg
    assert "₹" not in svg and "%" not in svg


def test_the_toolkit_wraps_a_chart_with_its_name():
    svg = str(charts.rate_chart("wg-bar", 358, 44, "A & B", ["<rect/>"]))
    assert svg == ('<svg class="wg-bar" viewBox="0 0 358 44" width="100%" role="img" aria-label="A &amp; B">'
                   "<rect/></svg>")


def test_the_bar_and_the_years_chart_take_the_same_drawing_path():
    tree = ast.parse(Path("services/production/api/wins_gap.py").read_text(encoding="utf-8"))
    fns = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    bar, years = _calls(fns["_bar_svg"]), _calls(fns["_years_svg"])
    assert {"charts.rate_scale", "charts.rate_chart", "charts.rate_axis_across"} <= bar
    assert {"charts.rate_scale", "charts.rate_chart", "charts.rate_axis"} <= years
    for name in ("_bar_svg", "_years_svg"):
        source = ast.get_source_segment(Path("services/production/api/wins_gap.py").read_text(encoding="utf-8"),
                                        fns[name])
        assert "<svg" not in source, f"{name} writes its own <svg>"


def test_the_bar_on_the_page_carries_its_axis(client, engine):
    bar = re.search(r'<svg class="wg-bar".*?</svg>', _section(client), re.DOTALL).group(0)
    assert re.findall(r'class="ch-axis ch-axis--x"[^>]*>([^<]+)<', bar) == ["0", "25", "50", "75", "100"]
    assert bar.count('class="wg-win"') == 1 and bar.count('class="wg-need"') == 1


# ---------- 3. what each figure counts, said beside it ----------

def test_the_page_says_what_the_rate_and_the_lines_each_count(client, engine):
    text = _plain(_section(client))
    assert "WIDGETOIL options 46 of 100 · needs 33 of 100 · 13 of 100 above break-even" in text
    assert "Over all 90 same-day trades in this book." in text
    assert "The lines count 80 of them: only years with 30 or more trades." in text
