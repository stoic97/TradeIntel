"""TICKET-1060: Your wins and losses drawn through the chart toolkit, and proven on the rendered
page on a multi-year record.

The rate axis now lives in the toolkit (``charts.rate_scale`` places a rate, ``charts.rate_axis``
draws its gridlines and labels), and both charts on the math page use it: the gap bar places its
two marks with it, the years chart its points and its axis. The page is drawn byte for byte as it
was before the move; the digest below was taken on main before it.

The record is made up, a bought option that closes five minutes after it opens: a winner sold at
11.00 for +100, a loser at 9.50 for -50, before charges. Worked by hand:
  WIDGETOIL options  2024  16 wins, 24 losses: win 40 of 100; break-even 50 / (100 + 50) = 33
                     2025  20 wins, 20 losses: win 50 of 100; break-even 33
                     2026   5 wins,  5 losses: 10 trades, too few
                     whole 41 of 90 = 45.6 -> 46 of 100; needs 33; 13 of 100 above break-even
  Stocks and ETFs    2025  10 trades: a book under 30, so no chart at all
"""
from __future__ import annotations

import ast
import hashlib
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from services.production.api import charts
from tests.helpers.upload import upload

HEADER = Path("data/fixtures/duplicates/clean.csv").read_text(encoding="utf-8").splitlines()[0]
IST = ZoneInfo("Asia/Kolkata")
OPTION = "WIDGETOIL 19 NOV 5000 CALL,{side},INTRADAY,MCX,Commodity,100,{price},{value},Traded"
SHARE = "Widget ETF,{side},DELIVERY,NSE,Equity,10,{price},{value},Traded"


def opened(year: int, i: int) -> datetime:
    """The i-th trade of a year: four a day from 4 Aug, twenty minutes apart."""
    day = datetime(year, 8, 4, 9, 30, tzinfo=IST) + timedelta(days=(i // 4) * 7 // 5)
    return day + timedelta(minutes=20 * (i % 4))


def option_year(year: int, wins: int, losses: int) -> list[str]:
    rows = []
    for i, win in enumerate([True] * wins + [False] * losses):
        t, out = opened(year, i), "11.00" if win else "9.50"
        rows += [
            f"{t:%Y-%m-%d,%H:%M:%S}," + OPTION.format(side="BUY", price="10.00", value="1000.00"),
            f"{t + timedelta(minutes=5):%Y-%m-%d,%H:%M:%S},"
            + OPTION.format(side="SELL", price=out, value=f"{float(out) * 100:.2f}"),
        ]
    return rows


def share_year(year: int, n: int) -> list[str]:
    rows = []
    for i in range(n):
        t = opened(year, i) + timedelta(minutes=2)
        rows += [
            f"{t:%Y-%m-%d,%H:%M:%S}," + SHARE.format(side="BUY", price="100.00", value="1000.00"),
            f"{t + timedelta(minutes=5):%Y-%m-%d,%H:%M:%S}," + SHARE.format(side="SELL", price="101.00", value="1010.00"),
        ]
    return rows


ROWS = option_year(2024, 16, 24) + option_year(2025, 20, 20) + option_year(2026, 5, 5) + share_year(2025, 10)


def math_page(client) -> str:
    assert upload(client, content=("\n".join([HEADER, *ROWS]) + "\n").encode()).status_code == 303
    html = client.get("/mirror/fact/math").text
    found = re.search(r'<section class="wins-gap".*?</section>', html, re.DOTALL)
    assert found, "no wins-gap section on the math page"
    return found.group(0)


def years_svg(section: str) -> str:
    return re.search(r'<svg class="wg-years".*?</svg>', section, re.DOTALL).group(0)


def plain(markup: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", markup).split())


def calls(node) -> set[str]:
    return {f"{n.func.value.id}.{n.func.attr}" for n in ast.walk(node)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)}


# ---------- 1. the rate axis lives in the toolkit, and both charts use it ----------

def test_the_toolkit_places_a_rate_between_two_edges():
    across = charts.rate_scale(0, 100, 0, 358)
    assert (across(0), across(50), across(100)) == (0, 179, 358)
    up = charts.rate_scale(30, 50, 110, 10)  # a rate axis runs upward: 30 at the foot, 50 at the top
    assert (up(30), up(40), up(50)) == (110, 60, 10)
    assert charts.rate_scale(40, 40, 0, 10)(40) == 0  # one value: no division by nothing


def test_the_rate_axis_writes_each_tick_as_a_whole_of_100_with_its_gridline():
    svg = str(charts.rate_axis(30, 50, 10, charts.rate_scale(30, 50, 110, 10), left=8, right=34, width=358))
    assert re.findall(r'class="ch-axis">([^<]+)<', svg) == ["30", "40", "50"]
    assert svg.count('class="ch-grid"') == 3
    assert "₹" not in svg and "%" not in svg
    assert '<line x1="8" x2="324" y1="60.0" y2="60.0" class="ch-grid"/>' in svg


def test_the_rate_axis_draws_only_classes_the_toolkit_styles():
    css = Path("services/production/api/static/css/app.css").read_text(encoding="utf-8")
    block = css.split("/* charts toolkit */", 1)[1].split("\n/*", 1)[0]
    svg = str(charts.rate_axis(0, 100, 25, charts.rate_scale(0, 100, 100, 0), left=0, right=30, width=200))
    for cls in {one for c in re.findall(r'class="([^"]+)"', svg) for one in c.split()}:
        assert f".{cls}" in block, cls


def test_both_charts_on_the_page_draw_through_the_toolkit():
    source = Path("services/production/api/wins_gap.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert {"charts.rate_scale", "charts.rate_axis", "charts.ticks", "charts.text_table"} <= calls(tree)
    for name in ("_bar_svg", "_years_svg"):
        fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
        assert "charts.rate_scale" in calls(fn), name
        assert not any(isinstance(n, ast.FunctionDef) and n is not fn for n in ast.walk(fn)), (
            f"{name} keeps a scale of its own")
    assert 'class="ch-grid"' not in source  # the axis is drawn by the toolkit, not written here


# ---------- 3. on the rendered page, a multi-year record ----------

def test_the_page_draws_both_lines_the_shaded_gap_and_too_few(client, engine):
    section = math_page(client)
    years = years_svg(section)
    assert years.count('class="wg-you"') == 1 and years.count('class="wg-even"') == 1
    assert years.count('class="wg-band"') == 1
    assert re.findall(r'class="ch-axis ch-axis--x">([^<]+)<', years) == ["2024", "2025"]
    assert re.findall(r'class="ch-axis">([^<]+)<', years) == ["30", "35", "40", "45", "50"]
    assert "%" not in plain(years) and "₹" not in plain(years)  # no sign in what the chart says
    text = plain(section)
    assert "WIDGETOIL options 46 of 100 · needs 33 of 100 · 13 of 100 above break-even" in text
    assert "2026: 10 trades, too few" in text


def test_a_book_under_thirty_same_day_trades_gets_no_chart(client, engine):
    section = math_page(client)
    assert section.count('<svg class="wg-bar"') == 1 and section.count('<svg class="wg-years"') == 1
    assert "Stocks and ETFs" not in section and "Widget ETF" not in section


def test_the_first_and_last_year_labels_hang_inside_the_drawing(client, engine):
    years = years_svg(math_page(client))
    assert '<text x="8.0" y="126" text-anchor="start" class="ch-axis ch-axis--x">2024</text>' in years
    assert '<text x="324.0" y="126" text-anchor="end" class="ch-axis ch-axis--x">2025</text>' in years


# Taken on main at 037410b, before the charts moved into the toolkit: the section draws the same.
BEFORE = "07af43108373175f03dbb2a77b2f67f417e31c897ef34dad57711509a6714c4e"


def test_the_section_is_drawn_byte_for_byte_as_before(client, engine):
    assert hashlib.sha256(math_page(client).encode()).hexdigest() == BEFORE
