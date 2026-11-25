"""TICKET-1026, the review of 24 Nov 2026 21:19: one date, one figure, on the rendered pages.

Proposed on the ticket: every figure on Your numbers reads same-day trades (gate 1), the
calendar's cells included, so the tile and the cell agree. The day page states the same figure
for its own same-day trades, beside the held positions it lists. Every count opens exactly the
trades it adds up, and the sentence above the figures appears only when it is true.

Every trade here is made up; the expected values are worked by hand in the comments.
"""
from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from html import unescape
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from services.production.api import routes_home as RH
from services.production.api import routes_mirror as RM
from services.production.api import routes_numbers as RN
from services.production.api import scope_facts as SF
from services.production.api.app import create_app
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s
from tests.helpers.upload import CSRF, sign_up

IST = ZoneInfo("Asia/Kolkata")
D = Decimal


def trip(tid: str, opened: str, closed: str, net: str) -> mx.Trip:
    entry = datetime.fromisoformat(opened).replace(tzinfo=IST)
    leave = datetime.fromisoformat(closed).replace(tzinfo=IST)
    return mx.Trip(
        trip_id=tid, symbol="NIFTY", trading_day=entry.date().isoformat(), entry_ts=entry,
        exit_ts=leave, holding_seconds=int((leave - entry).total_seconds()), net=D(net), lots=1,
        risk_unit_source=s.RiskUnitSourceV1.PREMIUM_PAID, is_option=True,
        lines=(mx.TradeLine("NIFTY", "OPT", "Buy", 1, None, None, D(net)),),
    )


# Worked by hand.
#   9 Mar  e +50 (same day)                         a opened 14:00, held to 10 Mar 10:00, +500
#  10 Mar  b +100 (same day)                        c opened 14:00, held to 11 Mar 10:00, -300
#  11 Mar  d -50 (same day)
# Same-day trades by their day: 9 Mar +50, 10 Mar +100 (best), 11 Mar -50 (worst), 1 each.
# Held past the day: a and c, 2 positions, +500 - 300 = +200.
# Winners among same-day trades: e, b -> 2, average +75. Losers: d -> 1, average -50.
# Months (March, same-day trades): +100 -> 1 of 1, over 3 trades.
# The day page for 10 Mar lists what opened that day (b, c): its same-day trades came to +100,
# the figure the tile and the calendar cell give for 10 Mar.
RECORD = [
    trip("e", "2026-03-09T09:40", "2026-03-09T10:00", "50"),
    trip("a", "2026-03-09T14:00", "2026-03-10T10:00", "500"),
    trip("b", "2026-03-10T09:40", "2026-03-10T10:00", "100"),
    trip("c", "2026-03-10T14:00", "2026-03-11T10:00", "-300"),
    trip("d", "2026-03-11T11:00", "2026-03-11T11:20", "-50"),
]
# Every trade closed the day it opened: nothing is held, so no sentence is needed.
NONE_HELD = [RECORD[0], RECORD[2], RECORD[4]]
# Every trade held past its day: there are no same-day trades for a sentence to name.
ALL_HELD = [RECORD[1], RECORD[3]]

TILE = re.compile(r'<div class="numbers__tile">(.*?)</div>', re.DOTALL)
HREF = re.compile(r'href="([^"]*)"')
SHOWN = re.compile(r'class="evidence__caption"><span class="num">(\d+)</span> of ')


def text(html: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html)))


def tile(html: str, label: str) -> str:
    found = [t for t in TILE.findall(html) if label in t]
    assert len(found) == 1, f"{label!r}: {len(found)} tiles carry it"
    return found[0]


def tile_link(html: str, label: str) -> str:
    hrefs = HREF.findall(tile(html, label))
    assert len(hrefs) == 1, f"{label!r}: {hrefs}"
    return unescape(hrefs[0])


@pytest.fixture()
def demo(engine):
    client = sign_up(TestClient(create_app()), engine, "C-1", "visitor")
    client.post("/upload/demo", data={"csrf_token": CSRF.search(client.get("/upload").text).group(1)})
    return client


def drawn_from(demo, monkeypatch, record):
    real = RM.load_record

    def load(request):
        early, got = real(request)
        if early is not None:
            return early, got
        _trips, imp, _context = got
        return None, (record, imp, SF.record_context(record))

    for module in (RM, RN):
        monkeypatch.setattr(module, "load_record", load)
    real_load_for = RH.loader.load_for

    def load_for(sess, trader):  # Home reads the record straight from the loader
        _trips, imp = real_load_for(sess, trader)
        return record, imp

    monkeypatch.setattr(RH.loader, "load_for", load_for)
    return demo


@pytest.fixture()
def made(demo, monkeypatch):
    return drawn_from(demo, monkeypatch, RECORD)


# ---------- 1. one date, one figure: tile, calendar cell and day page ----------

def test_ten_march_is_one_figure_on_the_tile_the_calendar_and_the_day_page(made):
    html = made.get("/numbers").text
    assert "+₹100" in text(tile(html, "Best day")) and "10 Mar 2026" in text(tile(html, "Best day"))
    cell = re.search(r"<title>10 Mar 2026: ([^<]+)</title>", html)
    assert cell, "no calendar cell for 10 Mar"
    assert unescape(cell.group(1)) == "1 trade, +₹100"
    day = text(made.get("/mirror/day/2026-03-10").text)
    assert "Your same-day trades this day came to +₹100" in day


def test_a_calendar_cell_opens_the_trades_it_counts(made):
    html = made.get("/numbers").text
    cells = re.findall(r'<a href="([^"]+)" class="cal__day"><title>10 Mar 2026', html)
    assert len(cells) == 1
    page = made.get(unescape(cells[0]))
    assert page.status_code == 200
    assert SHOWN.search(page.text).group(1) == "1"


# ---------- 2. the sentence above the figures says what they count, and only when true ----------

def test_the_sentence_names_same_day_trades_and_the_held_line(made):
    body = text(made.get("/numbers").text)
    assert "same-day trades" in body
    assert "Held past the day: 2 positions, +₹200" in body


def test_no_same_day_sentence_when_no_trade_closed_the_day_it_opened(demo, monkeypatch):
    body = text(drawn_from(demo, monkeypatch, ALL_HELD).get("/numbers").text)
    assert "same-day trades" not in body


def test_no_sentence_when_nothing_was_held(demo, monkeypatch):
    body = text(drawn_from(demo, monkeypatch, NONE_HELD).get("/numbers").text)
    assert "same-day trades" not in body and "Held past the day" not in body


def test_homes_needed_line_names_same_day_trades_only_when_held_positions_exist(demo, monkeypatch):
    held = text(drawn_from(demo, monkeypatch, RECORD).get("/").text)
    assert "same-day trades" in held
    none = text(drawn_from(demo, monkeypatch, NONE_HELD).get("/").text)
    assert "same-day trades" not in none


# ---------- 3. average winner, average loser and months open exactly what they count ----------

@pytest.mark.parametrize("label, count", [
    ("Your average winner", 2), ("Your average loser", 1), ("Months that made money", 3)])
def test_each_tile_opens_exactly_the_trades_it_counts(made, label, count):
    html = made.get("/numbers").text
    page = made.get(tile_link(html, label))
    assert page.status_code == 200
    assert SHOWN.search(page.text).group(1) == str(count)


# ---------- 4. the held line is not labelled "Result" ----------

def test_homes_whole_record_figure_is_labelled_as_the_whole_record(made):
    html = made.get("/").text
    kpi = re.search(r'<a class="hy-kpi"[^>]*><span class="hy-kpi__label">([^<]+)</span>'
                    r'<span class="hy-kpi__fig[^"]*">[^<]*</span><span class="hy-kpi__note">[^"]*?Held past the day',
                    html)
    assert kpi, "no KPI carries the held line"
    assert kpi.group(1) == "Whole record"
