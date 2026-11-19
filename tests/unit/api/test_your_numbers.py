"""TICKET-988: the Your numbers page - his scoreboard, and his trades by the day he closed
them, by days left to expiry, and by book. Counted rows, never a verdict; every row and tile
opens its trades or its day.

The builder's figures are checked against a made-up record worked out by hand (the working is
in the comments). The page is checked through the route on the demo file.
"""
from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from services.production.api import numbers as N
from services.production.api import report_filter as RF
from services.production.api.app import create_app
from services.production.db.session import make_engine, run_migrations
from services.production.mirror import loader
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s
from tests.helpers.upload import CSRF, sign_up

IST = ZoneInfo("Asia/Kolkata")
D = Decimal


def trip(tid: str, when: str, net: str, symbol: str = "NIFTY", segment: str = "OPT") -> mx.Trip:
    """One closed position leaving at `when` (IST). An option's leg carries its strike, type and
    opening instant, which is what ties it to its contract's expiry (loader.expiry_key)."""
    leave = datetime.fromisoformat(when).replace(tzinfo=IST)
    entry = leave - timedelta(minutes=20)
    option = segment == "OPT"
    line = mx.TradeLine(symbol, segment, "Buy", 1, None, None, D(net),
                        strike=D("24000") if option else None, option_type="CE" if option else None,
                        entry_ts=entry)
    return mx.Trip(
        trip_id=tid, symbol=symbol, trading_day=entry.date().isoformat(),
        entry_ts=entry, exit_ts=leave, holding_seconds=1200, net=D(net), lots=1,
        risk_unit_source=s.RiskUnitSourceV1.PREMIUM_PAID, is_option=option, lines=(line,),
    )


RECORD = [
    trip("t01", "2026-01-30T10:00", "1000"),                       # Fri, expiry 3 Feb: 4 days left
    trip("t02", "2026-01-30T14:00", "-400"),                       # Fri, expiry 30 Jan: expiry day
    trip("t03", "2026-02-01T11:00", "300"),                        # Sun, expiry 3 Feb: 2 days left
    trip("t04", "2026-02-02T10:00", "200", "TATASTEEL", "EQ"),     # Mon, a share: no expiry
    trip("t05", "2026-02-02T15:00", "-1500"),                      # Mon, expiry 3 Feb: 1 day left
    trip("t06", "2026-02-03T11:00", "700"),                        # Tue, expiry 3 Feb: expiry day
    trip("t07", "2026-02-05T13:00", "-100", "TATASTEEL", "EQ"),    # Thu, a share
    trip("t08", "2026-02-09T10:00", "250"),                        # Mon, expiry 24 Feb: 15 days
    trip("t09", "2026-02-09T11:00", "-50"),                        # Mon, expiry 10 Feb: 1 day left
    trip("t10", "2026-02-27T14:00", "900"),                        # Fri, expiry 3 Mar: 4 days left
    trip("t11", "2026-03-02T10:00", "400", "TATASTEEL", "EQ"),     # Mon, a share
    trip("t12", "2026-03-02T12:00", "-600"),                       # Mon, its expiry not read
]
EXPIRY = {"t01": date(2026, 2, 3), "t02": date(2026, 1, 30), "t03": date(2026, 2, 3),
          "t05": date(2026, 2, 3), "t06": date(2026, 2, 3), "t08": date(2026, 2, 24),
          "t09": date(2026, 2, 10), "t10": date(2026, 3, 3)}
EXPIRIES = {loader.expiry_key(t.lines[0]): EXPIRY[t.trip_id] for t in RECORD if t.trip_id in EXPIRY}


@pytest.fixture()
def view() -> dict:
    return N.build(RECORD, EXPIRIES, gross=True)


def row(rows: list[dict], name: str) -> dict:
    return next(r for r in rows if r["name"] == name)


# ---------- the tiles ----------

def test_the_top_line_counts_his_trades_and_says_before_charges(view):
    assert (view["trades"], view["first"], view["last"], view["gross"]) == (12, "2026-01-30", "2026-03-02", True)


def test_average_winner_and_loser_are_the_reports_own(view):
    even = mx.break_even(RECORD)
    # Winners t01 t03 t04 t06 t08 t10 t11: 3750 / 7. Losers t02 t05 t07 t09 t12: 2650 / 5 = 530.
    assert view["tiles"]["winner"]["value"] == even.average_winner == D(3750) / 7
    assert view["tiles"]["winner"]["count"] == 7
    assert view["tiles"]["loser"]["value"] == -even.average_loser == D(-530)
    assert view["tiles"]["loser"]["count"] == 5


def test_best_and_worst_day_are_by_the_day_he_closed(view):
    # By exit day: 30 Jan +600, 1 Feb +300, 2 Feb -1300, 3 Feb +700, 5 Feb -100, 9 Feb +200,
    # 27 Feb +900, 2 Mar -200.
    assert (view["tiles"]["best_day"]["value"], view["tiles"]["best_day"]["day"]) == (D(900), "2026-02-27")
    assert (view["tiles"]["worst_day"]["value"], view["tiles"]["worst_day"]["day"]) == (D(-1300), "2026-02-02")
    # Each opens its day: a trade was opened on both.
    assert view["tiles"]["best_day"]["href"] == "/mirror/day/2026-02-27"
    assert view["tiles"]["worst_day"]["href"] == "/mirror/day/2026-02-02"


def test_months_that_made_money_count_each_months_own_result(view):
    # January +600, February +700 (1300 - 600), March -200 (1100 - 1300): 2 of 3.
    assert (view["tiles"]["months"]["made"], view["tiles"]["months"]["of"]) == (2, 3)


def test_trades_a_day_and_the_busiest_day(view):
    # 12 trades over 8 days closed on: 1.5. Four days had 2; the first was 30 Jan.
    assert view["tiles"]["per_day"]["value"] == D("1.5")
    assert (view["tiles"]["per_day"]["most"], view["tiles"]["per_day"]["day"]) == (2, "2026-01-30")


def test_winners_and_losers_open_their_trades(view):
    assert view["tiles"]["winner"]["href"] == "/mirror/fact/risk/trades?result=winners"
    assert view["tiles"]["loser"]["href"] == "/mirror/fact/risk/trades?result=losers"


# ---------- the rows ----------

def test_by_the_day_he_closed_in_week_order(view):
    # Mon t04 t05 t08 t09 t11 t12 = 200-1500+250-50+400-600 = -1300; Tue t06 +700;
    # Thu t07 -100; Fri t01 t02 t10 = +1500; Sun t03 +300. Sum 1100.
    assert [(r["name"], r["trades"], r["net"]) for r in view["weekdays"]] == [
        ("Monday", 6, D(-1300)), ("Tuesday", 1, D(700)), ("Thursday", 1, D(-100)),
        ("Friday", 3, D(1500)), ("Sunday", 1, D(300)),
    ]
    assert row(view["weekdays"], "Monday")["href"] == "/mirror/fact/risk/trades?closed=monday"


def test_by_days_left_to_expiry_when_he_closed(view):
    # Expiry day t02 t06 = +300; 1 day t05 t09 = -1550; 2-6 days t01 t03 t10 = +2200;
    # 7+ days t08 = +250. Left out: three shares and t12, whose expiry was not read: 4.
    assert [(r["name"], r["trades"], r["net"]) for r in view["expiry"]] == [
        ("Expiry day", 2, D(300)), ("1 day left", 2, D(-1550)),
        ("2–6 days left", 3, D(2200)), ("7+ days left", 1, D(250)),
    ]
    assert view["no_expiry"] == 4
    assert row(view["expiry"], "1 day left")["href"] == "/mirror/fact/risk/trades?left=1"


def test_by_book_adds_up_to_the_record(view):
    assert [(r["name"], r["trades"], r["net"]) for r in view["books"]] == [
        ("Other options", 9, D(600)), ("Stocks and ETFs", 3, D(500)),
    ]
    assert row(view["books"], "Stocks and ETFs")["href"] == (
        "/mirror/fact/risk/trades?book=Stocks+and+ETFs")


def test_a_bar_is_scaled_to_the_largest_row_and_sits_on_its_side(view):
    # Largest |result| among the expiry rows is 2200: it fills its half; 1550 is 35.2% of the track.
    assert (row(view["expiry"], "2–6 days left")["bar_side"], row(view["expiry"], "2–6 days left")["bar_width"]) == ("gain", D("50.0"))
    assert (row(view["expiry"], "1 day left")["bar_side"], row(view["expiry"], "1 day left")["bar_width"]) == ("loss", D("35.2"))


def test_made_money_needs_thirty_trades_in_its_row(view):
    assert all(r["rate"] is None for r in view["weekdays"])  # no row reaches 30


def test_made_money_is_the_reports_win_rate_once_a_row_has_thirty():
    # 12 winners and 18 losers on Mondays: 12 / 30 = 40.0. One fewer trade and it is too few.
    monday = [trip(f"w{i}", f"2026-03-{2 + 7 * (i % 4):02d}T10:{i:02d}", "10") for i in range(12)]
    monday += [trip(f"l{i}", f"2026-03-{2 + 7 * (i % 4):02d}T11:{i:02d}", "-5") for i in range(18)]
    assert N.build(monday, {}, gross=True)["weekdays"][0]["rate"] == D("40.0")
    assert N.build(monday[1:], {}, gross=True)["weekdays"][0]["rate"] is None


# ---------- the page ----------

@pytest.fixture()
def client():
    engine = make_engine(os.environ["SCOPE_DB"])
    run_migrations(engine)
    c = sign_up(TestClient(create_app()), engine, "N-1", "numbersreader")
    token = CSRF.search(c.get("/upload").text).group(1)
    c.post("/upload/demo", data={"csrf_token": token}, follow_redirects=False)
    return c


def test_signed_out_it_sends_him_to_sign_in():
    r = TestClient(create_app()).get("/numbers", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


def test_the_page_reads_top_down(client):
    html = client.get("/numbers").text
    order = ["Your numbers", "Your average winner", "Your average loser", "Best day", "Worst day",
             "Months that made money", "Trades a day", "By the day you closed the trade",
             "By how close to expiry you closed", "By book"]
    at = [html.index(words) for words in order]
    assert at == sorted(at)
    assert "before charges" in html  # the demo has no charges file


def test_it_says_no_verdict(client):
    text = re.sub(r"<[^>]+>", " ", client.get("/numbers").text).lower()
    for word in (r"\bgood\b", r"\bbad\b", r"best book", r"worst book", r"best weekday", r"worst weekday",
                 r"\bwinning\b"):
        assert re.search(word, text) is None, word


def test_every_link_on_it_opens(client):
    html = client.get("/numbers").text
    body = html[html.index("Your numbers"):]
    hrefs = {h.replace("&amp;", "&") for h in re.findall(r'href="([^"#]+)"', body)
             if h.startswith(("/mirror", "/numbers"))}
    assert any(h.startswith("/mirror/fact/risk/trades?closed=") for h in hrefs)
    for href in sorted(hrefs):
        assert client.get(href).status_code == 200, href


def trades_on(html: str) -> int:
    top = re.search(r'class="[^"]*nb-top[^"]*".*?</p>', html, re.S).group(0)
    return int(re.search(r"([\d,]+)\s*</span>\s*trades", re.sub(r"<a [^>]*>|</a>", "", top)).group(1).replace(",", ""))


def test_it_follows_the_report_filter_and_the_filter_comes_back_here(client):
    whole = trades_on(client.get("/numbers").text)
    r = client.get("/mirror/filter", params={"period": "all", "book": "NIFTY options", "next": "/numbers"},
                   follow_redirects=False)
    assert r.headers["location"] == "/numbers"
    narrowed = trades_on(client.get("/numbers").text)
    assert 0 < narrowed < whole
    assert RF.COOKIE in client.cookies
