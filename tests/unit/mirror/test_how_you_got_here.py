"""TICKET-987: home's "How you got here" card.

After the verdict (how much), this card answers how: three numbers (his result, whether his
win rate covered his sizes, how deep it went), then his running result as candles with the
trades taken under them, by book and by Day / Week / Month. Server links only, no script.
It reads the series and computes nothing of its own. All trades here are made up.
"""
from __future__ import annotations

import importlib
import re
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from services.production.api.app import create_app
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s
from tests.helpers.upload import CSRF, sign_up

IST = ZoneInfo("Asia/Kolkata")
D = Decimal


def card_module():
    return importlib.import_module("services.production.api.how_you_got_here")


def card(html: str) -> str:
    match = re.search(r'<section[^>]*id="how".*?</section>', html, re.S)
    assert match, "no How you got here card on home"
    return match.group(0)


# ---------- On home, through the app (the 40-trade fixture trader) ----------

def test_the_card_sits_after_the_verdict_and_before_the_days(client):
    body = client.get("/").text
    verdict = body.index('class="scope-card on-navy"')
    how = body.index('id="how"')
    days = body.index('<section class="latest">')
    assert verdict < how < days


def test_the_card_reads_top_down_in_its_order(client):
    html = card(client.get("/").text)
    markers = ["How you got here", 'class="hy-books', ">Result<", ">Made money<", ">Biggest drop<",
               'class="hy-readout', "<svg", 'class="hy-frames', "Each candle is your running result",
               "All your numbers"]
    at = [html.index(m) for m in markers]
    assert at == sorted(at), markers


def test_the_card_says_its_span_and_that_the_result_is_before_charges(client):
    html = card(client.get("/").text)
    assert "result before charges" in html  # the fixture's import has no charges
    assert "closed trades only" in html


def test_no_script_in_the_card(client):
    assert "<script" not in card(client.get("/").text)


def test_book_chips_are_all_then_each_book_with_twenty_trades(client):
    html = card(client.get("/").text)
    chips = re.findall(r'<a class="hy-chip[^"]*" href="[^"]*"[^>]*>([^<]+)</a>', html)
    assert chips[0] == "All"
    assert "WIDGETOIL options" in chips  # the fixture's 40 option trades are one book


def test_every_chip_is_a_server_link_that_keeps_the_reader_on_the_card(client):
    html = card(client.get("/").text)
    hrefs = re.findall(r'class="hy-chip[^"]*" href="([^"]+)"', html)
    assert hrefs and all(h.startswith("/?") and h.endswith("#how") for h in hrefs)
    for href in hrefs:
        assert client.get(href.split("#")[0]).status_code == 200


def test_choosing_a_timeframe_and_a_book_is_honoured(client):
    html = card(client.get("/?book=widgetoil-options&tf=m").text)
    assert re.search(r'class="hy-chip hy-chip--on"[^>]*>WIDGETOIL options<', html)
    assert re.search(r'class="hy-chip hy-chip--on"[^>]*>Month<', html)


def test_every_candle_opens_its_trades(client):
    html = card(client.get("/").text)
    targets = set(re.findall(r'<a href="(/mirror/day/\d{4}-\d\d-\d\d)" class="hy-candle', html))
    assert targets
    for href in targets:
        assert client.get(href).status_code == 200
    # "All your numbers" goes to /numbers, which the Your numbers page's own PR adds; it is not
    # resolved here.
    assert 'href="/numbers"' in html


def test_a_rate_is_ink_and_rupees_carry_their_sign(client):
    html = card(client.get("/").text)
    made = re.search(r">Made money<.*?</a>", html, re.S).group(0)
    assert "num--loss" not in made and "num--gain" not in made
    assert " of 100" in made


def test_the_chart_has_its_numbers_as_text_too(client):
    html = card(client.get("/").text)
    assert re.search(r"<details[^>]*>\s*<summary[^>]*>Every \w+ as numbers</summary>", html)
    drawn = len(re.findall(r'class="hy-candle', html))
    rows = len(re.findall(r'<tr class="hy-row"', html))
    assert drawn == rows > 0


def test_the_demo_opens_on_weeks(engine):
    client = sign_up(TestClient(create_app()), engine, "D-1", "visitor")
    token = CSRF.search(client.get("/upload").text).group(1)
    client.post("/upload/demo", data={"csrf_token": token})
    html = card(client.get("/").text)
    # 63 trading days is over the 60 a phone reads; 14 weeks is not.
    assert re.search(r'class="hy-chip hy-chip--on"[^>]*>Week<', html)


# ---------- The view, on made-up records ----------

def trip(i: int, day: datetime, net: str, symbol: str = "NIFTY") -> mx.Trip:
    leave = day.replace(hour=11, tzinfo=IST)
    return mx.Trip(
        trip_id=f"t{i:04d}", symbol=symbol, trading_day=leave.date().isoformat(),
        entry_ts=leave - timedelta(minutes=15), exit_ts=leave, holding_seconds=900,
        net=D(net), lots=1, risk_unit_source=s.RiskUnitSourceV1.PREMIUM_PAID, is_option=True,
        lines=(mx.TradeLine(symbol, "OPT", "Buy", 1, None, None, D(net)),),
    )


def long_record(days: int = 100) -> list[mx.Trip]:
    start = datetime(2026, 1, 5)
    out = []
    for n in range(days):
        net = "300" if n % 3 else "-500"
        out.append(trip(n, start + timedelta(days=n), net))
    return out


class Imp:
    fees_available = False
    export_date = None


def test_a_long_record_opens_on_the_first_timeframe_under_sixty():
    view = card_module().build(long_record(), Imp())
    assert view["frame"] == "week"  # 100 days is over 60; 15 weeks is not


def test_a_cut_view_shows_the_latest_sixty_and_says_so():
    view = card_module().build(long_record(), Imp(), tf="d")
    assert view["frame"] == "day"
    assert len(re.findall(r'class="hy-candle', str(view["chart"]))) == 60
    assert view["cut"] == (60, 100)
    assert "Lowest" not in str(view["chart"])  # on a cut view it would not be his lowest


def test_the_whole_view_keeps_nothing_in_range_and_marks_the_lowest():
    view = card_module().build(long_record(30), Imp(), tf="d")
    assert view["cut"] is None
    assert 'class="hy-zero"' in str(view["chart"])


def test_axis_ticks_show_their_half_thousand():
    short = card_module().short
    assert short(D("-47500")) == "−₹47.5k"
    assert short(D("-20000")) == "−₹20k"
    assert short(D("0")) == "₹0"
    assert short(D("150000")) == "₹1.5L"


def test_a_book_under_twenty_trades_gets_no_chip():
    trips = long_record(30) + [trip(900 + i, datetime(2026, 1, 6 + i), "100", "BANKNIFTY") for i in range(3)]
    view = card_module().build(trips, Imp())
    assert [c["name"] for c in view["books"]] == ["All", "NIFTY options"]


def test_a_record_with_no_candle_says_not_enough_trades_yet():
    view = card_module().build([], Imp())
    assert view["enough"] is False
