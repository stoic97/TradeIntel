"""TICKET-994: when you trade, a weekday x hour grid on the Your numbers page.

By when he opened the trade (the weekday and hour of entry, as the trade list's hour filter
reads it), toned by each cell's result through the chart toolkit, hatched under five trades,
expiry days apart behind three chips, every cell opening exactly its trades. It replaces the
page's "By the day you closed the trade" table. Every trade here is made up and the expected
values are worked by hand in the comments.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from services.production.api import numbers as N
from services.production.api import scope_facts as SF
from services.production.api import trade_list as TL
from services.production.api.app import create_app
from services.production.mirror import loader
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s
from tests.helpers.upload import CSRF, sign_up

IST = ZoneInfo("Asia/Kolkata")
D = Decimal


def when():
    assert hasattr(N, "when"), "numbers has no when()"
    return N.when


def trip(tid: str, opened: str, net: str, segment: str = "OPT", symbol: str = "NIFTY") -> mx.Trip:
    entry = datetime.fromisoformat(opened).replace(tzinfo=IST)
    leave = entry + timedelta(minutes=15)
    option = segment == "OPT"
    line = mx.TradeLine(symbol, segment, "Buy", 1, None, None, D(net),
                        strike=D("24000") if option else None, option_type="CE" if option else None,
                        entry_ts=entry)
    return mx.Trip(trip_id=tid, symbol=symbol, trading_day=entry.date().isoformat(), entry_ts=entry,
                   exit_ts=leave, holding_seconds=900, net=D(net), lots=1,
                   risk_unit_source=s.RiskUnitSourceV1.PREMIUM_PAID, is_option=option, lines=(line,))


# By when he opened, worked by hand:
#   Mon 2 Feb 09:xx  m1 +100  m2 -40  m4 +10  m5 +20  m6 -10   -> 5 trades, +80 (not hatched)
#   Mon 2 Feb 14:10  m3 -200                                  -> 1 trade, -200
#   Tue 3 Feb 09:xx  t1 +300  t2 -100   (opened on their expiry) -> 2 trades, +200
#   Wed 4 Feb 10:15  e1 +70, a share                          -> All days only
#   Thu 5 Feb 09:10  u1 -30, an option whose expiry isn't known -> All days only
#   Sun 1 Feb 11:00  s1 +50, a crude future on a Budget Sunday -> All days only
# Monday's options expire on 3 Feb: opened the day before expiry, so Other days.
# Rows: Mon to Fri, and Sunday (a trade opened then). Columns: 9, 10, 11, 14.
# |cell results| sorted: 30 50 70 80 200 200; the 90th percentile, linear: position 4.5, so 200.
# Tones against 200: Mon 9 +80 -> 2; Mon 14 -200 -> 4; Tue 9 +200 -> 4; Wed 10 +70 -> 2;
#   Thu 9 -30 -> 1; Sun 11 +50 -> 1.
RECORD = [
    trip("m1", "2026-02-02T09:30", "100"), trip("m2", "2026-02-02T09:45", "-40"),
    trip("m4", "2026-02-02T09:05", "10"), trip("m5", "2026-02-02T09:55", "20"),
    trip("m6", "2026-02-02T09:15", "-10"), trip("m3", "2026-02-02T14:10", "-200"),
    trip("t1", "2026-02-03T09:20", "300"), trip("t2", "2026-02-03T09:50", "-100"),
    trip("e1", "2026-02-04T10:15", "70", segment="EQ", symbol="TATASTEEL"),
    trip("u1", "2026-02-05T09:10", "-30"),
    trip("s1", "2026-02-01T11:00", "50", segment="FUT", symbol="CRUDEOIL"),
]
EXPIRY = {tid: date(2026, 2, 3) for tid in ("m1", "m2", "m3", "m4", "m5", "m6", "t1", "t2")}
EXPIRIES = {loader.expiry_key(t.lines[0]): EXPIRY[t.trip_id] for t in RECORD if t.trip_id in EXPIRY}


def grid(days: str = "all") -> dict:
    return when()(RECORD, EXPIRIES, days=days)


def cell(view: dict, weekday: str, hour: int) -> dict:
    for block in view["blocks"]:
        for row in block["rows"]:
            if row["weekday"] == weekday:
                for c in row["cells"]:
                    if c["hour"] == hour:
                        return c
    raise KeyError((weekday, hour))


# ---------- 2, 3. by when he opened; rows and columns ----------

def test_rows_are_the_weekdays_and_a_sunday_he_traded_on():
    view = grid()
    assert [r["weekday"] for r in view["blocks"][0]["rows"]] == [
        "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Sunday"]


def test_columns_are_the_hours_with_a_trade():
    assert grid()["blocks"][0]["hours"] == [9, 10, 11, 14]


def test_cell_totals_worked_by_hand():
    view = grid()
    assert (cell(view, "Monday", 9)["trades"], cell(view, "Monday", 9)["net"]) == (5, D(80))
    assert (cell(view, "Monday", 14)["trades"], cell(view, "Monday", 14)["net"]) == (1, D(-200))
    assert (cell(view, "Tuesday", 9)["trades"], cell(view, "Tuesday", 9)["net"]) == (2, D(200))
    assert (cell(view, "Sunday", 11)["trades"], cell(view, "Sunday", 11)["net"]) == (1, D(50))
    assert cell(view, "Friday", 9)["trades"] == 0


# ---------- 4. a cell: its tone, hatched under five ----------

def test_cells_are_toned_against_the_90th_percentile():
    view = grid()
    assert view["scale"] == D(200)
    assert cell(view, "Monday", 9)["tone"] == "ch-cell ch-cell--gain-2"
    assert cell(view, "Monday", 14)["tone"] == "ch-cell ch-cell--loss-4"
    assert cell(view, "Thursday", 9)["tone"] == "ch-cell ch-cell--loss-1"
    assert cell(view, "Friday", 9)["tone"] == "ch-cell ch-cell--surface"


def test_a_cell_under_five_trades_is_hatched():
    view = grid()
    assert cell(view, "Monday", 9)["hatched"] is False
    assert cell(view, "Monday", 14)["hatched"] is True
    assert cell(view, "Friday", 9)["hatched"] is False  # an empty cell isn't hatched, it's empty


# ---------- 5. expiry days apart ----------

def test_expiry_day_is_an_option_opened_on_its_own_expiry():
    view = grid("expiry")
    assert sum(c["trades"] for b in view["blocks"] for r in b["rows"] for c in r["cells"]) == 2
    assert cell(view, "Tuesday", 9)["trades"] == 2


def test_an_option_opened_the_day_before_expiry_is_other_days():
    view = grid("other")
    assert cell(view, "Monday", 9)["trades"] == 5 and cell(view, "Monday", 14)["trades"] == 1
    assert sum(c["trades"] for b in view["blocks"] for r in b["rows"] for c in r["cells"]) == 6


def test_shares_futures_and_unread_expiries_are_under_all_days_only():
    assert grid()["left_out"] == 3
    for days in ("expiry", "other"):
        view = grid(days)
        assert all(r["weekday"] not in ("Wednesday",) or all(c["trades"] == 0 for c in r["cells"])
                   for b in view["blocks"] for r in b["rows"])
        assert "Sunday" not in [r["weekday"] for b in view["blocks"] for r in b["rows"]]


def test_the_chips_are_links_the_server_answers():
    view = grid("expiry")
    assert [(c["label"], c["href"], c["on"]) for c in view["chips"]] == [
        ("All days", "?days=all#when", False), ("Expiry day", "?days=expiry#when", True),
        ("Other days", "?days=other#when", False)]


# ---------- 6. a tap opens exactly the cell's trades ----------

def _listed(href: str) -> int:
    query = {k: v[0] for k, v in parse_qs(urlparse(href).query).items()}
    return TL.listing("risk", SF.record_context(RECORD), query, EXPIRIES)["shown"]


def test_a_cell_opens_exactly_its_trades():
    view = grid()
    href = cell(view, "Monday", 9)["href"]
    assert href.startswith("/mirror/fact/risk/trades?")
    assert parse_qs(urlparse(href).query) == {"opened": ["monday"], "hour": ["9"]}
    assert _listed(href) == 5


def test_a_cell_under_a_chip_opens_with_the_chip_s_rule():
    href = cell(grid("expiry"), "Tuesday", 9)["href"]
    assert parse_qs(urlparse(href).query) == {"opened": ["tuesday"], "hour": ["9"], "days": ["expiry"]}
    assert _listed(href) == 2


def test_an_empty_cell_opens_nothing():
    assert cell(grid(), "Friday", 9)["href"] is None


def test_the_new_filters_are_on_the_map_and_closed_is_gone():
    from services.production.api import factor_map
    names = {f.name for f in TL.FILTERS}
    assert {"opened", "days"} <= names and "closed" not in names
    on_map = {k for f in factor_map.FACTORS for k in f.filters}
    assert {"opened", "days", "closed_day"} <= on_map
    weekday = next(f for f in factor_map.FACTORS if f.name == "Weekday")
    assert weekday.filters == ("opened",)


# ---------- 7. the text table ----------

def test_a_text_table_row_per_cell_with_too_few_under_thirty():
    table = str(grid()["table"])
    assert table.count("<tr>") == 1 + 6
    assert "too few" in table


def test_made_money_shows_from_thirty_trades_in_a_cell():
    many = [trip(f"x{i:02d}", f"2026-02-{2 + 7 * (i % 4):02d}T10:{i:02d}", "10" if i < 12 else "-5")
            for i in range(30)]
    table = str(when()(many, {}, days="all")["table"])
    assert "40 of 100" in table


# ---------- 9. a phone: more than 13 hours split at 15:00 ----------

def test_more_than_thirteen_hours_split_before_and_after_three():
    wide = [trip(f"h{h}", f"2026-02-02T{h:02d}:10", "10") for h in range(9, 24)]
    view = when()(wide, {}, days="all")
    assert [b["hours"] for b in view["blocks"]] == [list(range(9, 15)), list(range(15, 24))]


# ---------- 1, 8. on the page ----------

@pytest.fixture()
def demo(engine):
    client = sign_up(TestClient(create_app()), engine, "W-1", "visitor")
    client.post("/upload/demo", data={"csrf_token": CSRF.search(client.get("/upload").text).group(1)})
    return client


def test_it_replaces_the_weekday_table_after_the_calendar(demo):
    html = demo.get("/numbers").text
    assert "By the day you closed the trade" not in html
    assert '<section class="when" id="when">' in html
    assert "When you trade" in html and "By when you opened the trade." in html
    assert html.index('id="calendar"') < html.index('id="when"') < html.index("By how close to expiry you closed")


def test_no_script_no_verdict_and_the_chips_answer(demo):
    html = demo.get("/numbers").text
    found = re.search(r'<section class="when" id="when">.*?</section>', html, re.DOTALL)
    assert found, "no When you trade section"
    section = found.group(0).lower()
    assert "<script" not in section
    for word in (r"\bbest\b", r"\bworst\b", r"\bgood\b", r"\bbad\b"):
        assert re.search(word, re.sub(r"<[^>]+>", " ", section)) is None, word
    for days in ("all", "expiry", "other"):
        assert demo.get(f"/numbers?days={days}").status_code == 200
