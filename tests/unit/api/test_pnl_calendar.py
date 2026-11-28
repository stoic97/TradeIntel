"""TICKET-993: the P&L calendar on the Your numbers page.

One cell a day, the day he closed the trade, coloured by that day's result through the chart
toolkit; one block a month, newest first; the latest 12 months unless he asks for all; every
traded cell opens its trades. Counted cells only, no sentence. Every trade here is made up and
the expected values are worked by hand in the comments.
"""
from __future__ import annotations

import importlib
import re
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from services.production.api import numbers as N
from services.production.api import trade_list as TL
from services.production.api.app import create_app
from services.production.mirror import metrics as mx
from services.shared.market import closures
from services.shared.schemas import scope_v1 as s
from tests.helpers.upload import CSRF, sign_up

IST = ZoneInfo("Asia/Kolkata")
D = Decimal


def calendar():
    assert hasattr(N, "calendar"), "numbers has no calendar()"
    return N.calendar


def trip(tid: str, opened: str, closed: str, net: str) -> mx.Trip:
    entry = datetime.fromisoformat(opened).replace(tzinfo=IST)
    leave = datetime.fromisoformat(closed).replace(tzinfo=IST)
    return mx.Trip(
        trip_id=tid, symbol="NIFTY", trading_day=entry.date().isoformat(), entry_ts=entry,
        exit_ts=leave, holding_seconds=int((leave - entry).total_seconds()), net=D(net), lots=1,
        risk_unit_source=s.RiskUnitSourceV1.PREMIUM_PAID, is_option=True,
        lines=(mx.TradeLine("NIFTY", "OPT", "Buy", 1, None, None, D(net)),),
    )


# Days are the day he closed. Results by day, worked by hand:
#   30 Jan (Fri)  +1000, -400  -> +600, 2 trades
#    1 Feb (Sun)  +300         -> +300           a Sunday is its own cell
#    2 Feb (Mon)  -1500        -> -1500
#    3 Feb (Tue)  +700         -> +700
#    5 Feb (Thu)  -100, opened 4 Feb: nothing opened on 5 Feb -> its trades through closed_day
#    9 Feb (Mon)  +250, -50    -> +200, 2 trades
#   27 Feb (Fri)  +900, opened 26 Feb: nothing opened on 27 Feb (and it is his best day)
#    2 Mar (Mon)  +400, -600   -> -200, 2 trades
# Months: Jan +600 (2 trades); Feb 300-1500+700-100+200+900 = +500 (7); Mar -200 (2).
# |day results| sorted: 100 200 200 300 600 700 900 1500. The 90th percentile, linear between
# ranks: position 0.9 x 7 = 6.3, so 900 + 0.3 x (1500 - 900) = 1080.
# Tones against 1080 (charts.cell_tone: step = ceil(4|v|/scale), at most 4):
#   +600 -> 3, +300 -> 2, -1500 -> 4 (beyond the scale), +700 -> 3, -100 -> 1, +200 -> 1,
#   +900 -> 4, -200 -> 1.
RECORD = [
    trip("t01", "2026-01-30T09:40", "2026-01-30T10:00", "1000"),
    trip("t02", "2026-01-30T13:40", "2026-01-30T14:00", "-400"),
    trip("t03", "2026-02-01T10:40", "2026-02-01T11:00", "300"),
    trip("t04", "2026-02-02T09:40", "2026-02-02T10:00", "-1500"),
    trip("t05", "2026-02-03T10:40", "2026-02-03T11:00", "700"),
    trip("t06", "2026-02-04T14:00", "2026-02-05T10:00", "-100"),
    trip("t07", "2026-02-09T09:40", "2026-02-09T10:00", "250"),
    trip("t08", "2026-02-09T10:40", "2026-02-09T11:00", "-50"),
    trip("t09", "2026-02-26T14:00", "2026-02-27T10:00", "900"),
    trip("t10", "2026-03-02T09:40", "2026-03-02T10:00", "400"),
    trip("t11", "2026-03-02T11:40", "2026-03-02T12:00", "-600"),
]


def cells(view) -> dict[str, dict]:
    return {c["iso"]: c for m in view["months"] for week in m["weeks"] for c in week if c}


def record_view() -> dict:
    return calendar()(RECORD)


# ---------- 2, 3. a block a month, newest first, seven columns; a day is the exit date ----------

def test_one_block_a_month_newest_first():
    view = record_view()
    assert [m["period"] for m in view["months"]] == ["2026-03", "2026-02", "2026-01"]


def test_a_month_is_seven_columns_monday_first():
    view = record_view()
    feb = next(m for m in view["months"] if m["period"] == "2026-02")
    assert all(len(week) == 7 for week in feb["weeks"])
    assert [c and c["day"] for c in feb["weeks"][0]] == [None] * 6 + [1]  # 1 Feb 2026 is a Sunday
    assert sum(1 for week in feb["weeks"] for c in week if c) == 28  # every calendar day a cell


# TICKET-1026's one-date rule: this record holds two positions past the day (t06 4->5 Feb, t09 26->27 Feb),
# so the calendar reads same-day trades. Worked by hand without t06 and t09:
#   30 Jan +600 (2) · 1 Feb +300 · 2 Feb -1500 · 3 Feb +700 · 9 Feb +200 (2) · 2 Mar -200 (2);
#   5 Feb and 27 Feb are no traded cell. Months: Jan +600 (2); Feb 300-1500+700+200 = -300 (5); Mar -200 (2).
#   |day results| sorted: 200 200 300 600 700 1500; 0.9 x 5 = 4.5, so 700 + 0.5 x (1500 - 700) = 1100.
#   Tones against 1100: +600 -> 3, +300 -> 2, -1500 -> 4, +700 -> 3, +200 -> 1, -200 -> 1.
SAME_DAY = "&same_day=yes"

def test_month_totals_are_the_month_candles_own():
    """Rewritten for TICKET-1026: the months read same-day trades, the same totals as the month
    candles of his same-day trades."""
    view = record_view()
    candles = {c.period: c for c in mx.running_result(mx.same_day_trips(RECORD)).candles["month"]}
    for m in view["months"]:
        assert m["net"] == candles[m["period"]].net and m["trades"] == candles[m["period"]].trades
    assert [(m["net"], m["trades"]) for m in view["months"]] == [(D(-200), 2), (D(-300), 5), (D(600), 2)]


def test_a_day_is_the_day_he_closed_and_a_sunday_is_its_own_cell():
    """Rewritten for TICKET-1026: a Sunday is still its own cell; a day on which only a held
    position closed (5 Feb) is no traded cell."""
    view = record_view()
    c = cells(view)
    assert c["2026-02-01"]["net"] == D(300)
    assert c["2026-02-05"]["net"] is None and c["2026-02-05"]["trades"] == 0
    assert c["2026-02-04"]["net"] is None and c["2026-02-04"]["trades"] == 0
    assert c["2026-01-30"]["trades"] == 2


# ---------- 4. colour ----------

def test_the_scale_is_the_90th_percentile_of_the_days_in_view():
    """Rewritten for TICKET-1026: the 90th percentile of the same-day days, 1100 by hand."""
    view = record_view()
    assert view["scale"] == D(1100)


def test_each_cell_is_toned_by_its_result_against_the_scale():
    """Rewritten for TICKET-1026: tones against the same-day scale of 1100; held-only days are surface."""
    view = record_view()
    c = cells(view)
    want = {"2026-01-30": "gain-3", "2026-02-01": "gain-2", "2026-02-02": "loss-4",
            "2026-02-03": "gain-3", "2026-02-09": "gain-1", "2026-03-02": "loss-1"}
    for iso, tone in want.items():
        assert c[iso]["tone"] == f"ch-cell ch-cell--{tone}", iso
    for iso in ("2026-02-04", "2026-02-05", "2026-02-27"):
        assert c[iso]["tone"] == "ch-cell ch-cell--surface", iso


def test_an_exchange_holiday_with_no_trades_is_greyed_and_nothing_moves():
    shut = sorted(d for d in closures.load()["NSE"].closed if d.weekday() < 5 and d.year == 2026)
    holiday = shut[0]
    day_before = holiday - timedelta(days=1 if holiday.weekday() else 3)
    record = [trip("h1", f"{day_before}T10:00", f"{day_before}T10:20", "50")]
    c = cells(calendar()(record))
    assert c[holiday.isoformat()]["closed"] is True
    assert c[holiday.isoformat()]["trades"] == 0
    assert c[day_before.isoformat()]["closed"] is False


# ---------- 5. how many months ----------

def _long(months: int) -> list[mx.Trip]:
    out = []
    for k in range(months):
        y, m = 2025 + (k // 12), k % 12 + 1
        out.append(trip(f"l{k:02d}", f"{y}-{m:02d}-10T10:00", f"{y}-{m:02d}-10T10:20", "100"))
    return out


def test_all_shows_the_latest_twelve_months_and_offers_the_rest():
    v = calendar()(_long(14))
    assert len(v["months"]) == 12 and v["months"][0]["period"] == "2026-02"
    assert v["cut"] == (12, 14)
    assert v["all_href"] == "?months=all#calendar"


def test_show_all_shows_every_month():
    v = calendar()(_long(14), show_all=True)
    assert len(v["months"]) == 14 and v["cut"] is None


def test_a_chosen_year_shows_that_years_months():
    v = calendar()(_long(14), year_chosen=True)
    assert len(v["months"]) == 14 and v["cut"] is None


# ---------- 6. every traded cell opens its trades ----------

def test_a_day_with_a_trade_opened_still_opens_the_trades_closed_that_day():
    """Rewritten for TICKET-1026: the cell opens the same-day trades closed that day, the ones it counts."""
    view = record_view()
    assert cells(view)["2026-02-03"]["href"] == "/mirror/fact/risk/trades?closed_day=2026-02-03" + SAME_DAY


def test_a_day_with_no_trades_opens_nothing():
    view = record_view()
    assert cells(view)["2026-02-04"]["href"] is None


def test_the_best_and_worst_day_tiles_take_the_same_link():
    """Rewritten for TICKET-1026: best day 3 Feb +700, worst 2 Feb -1500 among same-day days; each
    tile takes its cell's link."""
    v = N.build(RECORD, {}, gross=True)
    assert v["tiles"]["best_day"]["day"] == "2026-02-03"
    assert v["tiles"]["best_day"]["href"] == "/mirror/fact/risk/trades?closed_day=2026-02-03" + SAME_DAY
    assert v["tiles"]["worst_day"]["href"] == "/mirror/fact/risk/trades?closed_day=2026-02-02" + SAME_DAY


def test_closed_day_is_a_filter_on_the_map():
    from services.production.api import factor_map
    assert any(f.name == "closed_day" for f in TL.FILTERS)
    assert any("closed_day" in f.filters for f in factor_map.FACTORS)


# ---------- 9. the screen reader's table ----------

def test_a_text_table_row_for_every_traded_day():
    """Rewritten for TICKET-1026: the heading and the six same-day traded days."""
    view = record_view()
    table = str(view["table"])
    assert table.count("<tr>") == 1 + 6
    assert "−₹1,500" in table


# ---------- 1, 7, 8. on the page ----------

@pytest.fixture()
def demo(engine):
    client = sign_up(TestClient(create_app()), engine, "C-1", "visitor")
    client.post("/upload/demo", data={"csrf_token": CSRF.search(client.get("/upload").text).group(1)})
    return client


def test_the_calendar_sits_after_the_tiles_and_before_the_weekday_table(demo):
    html = demo.get("/numbers").text
    assert '<section class="cal" id="calendar">' in html
    assert "Your calendar" in html
    # The weekday table it sat before became "When you trade" (TICKET-994).
    assert html.index("numbers__grid") < html.index('id="calendar"') < html.index('id="when"')


def test_no_script_and_no_sentence_about_the_days(demo):
    html = demo.get("/numbers").text
    found = re.search(r'<section class="cal" id="calendar">.*?</section>', html, re.DOTALL)
    assert found, "no calendar section on the page"
    section = found.group(0)
    assert "<script" not in section
    for word in ("streak", "good month", "bad day", "best month", "worst month"):
        assert word not in section.lower()


def test_show_all_is_answered_by_the_server(demo):
    assert demo.get("/numbers?months=all").status_code == 200


def test_the_module_keeps_the_calendar_to_itself():
    src = importlib.import_module("services.production.api.numbers").__file__
    text = Path(src).read_text(encoding="utf-8")
    assert "def calendar(" in text
    template = Path("services/production/api/templates/_calendar.html")
    assert template.exists(), "no templates/_calendar.html"
    assert 'id="calendar"' in template.read_text(encoding="utf-8")


def test_the_best_day_tile_reads_same_day_trades_and_opens_its_day():
    # TICKET-1026: the tiles read same-day trades, so t09 (opened 26 Feb, closed 27 Feb) is held
    # past the day and in no tile. Same-day days: 30 Jan +600 and 3 Feb +700, so the best day is
    # 3 Feb. Each tile opens the trades closed that day that closed the day they opened.
    v = N.build(RECORD, {}, gross=True)
    assert v["tiles"]["best_day"]["day"] == "2026-02-03"
    assert v["tiles"]["best_day"]["href"] == "/mirror/fact/risk/trades?closed_day=2026-02-03&same_day=yes"
    assert v["tiles"]["worst_day"]["href"] == "/mirror/fact/risk/trades?closed_day=2026-02-02&same_day=yes"
