"""TICKET-1026: Your calendar reads the same trades as the tiles above it (review of 24 Nov 21:19).

When some trades were held past the day, the calendar's cells, month totals and text table count
same-day trades only, like every other figure on Your numbers, and a held position is on its own
line above. A day on which only a held position closed is not a traded cell. With nothing held,
the calendar is as before. Every trade is made up; the figures are worked by hand.
"""
from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from html import unescape
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

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


# Same-day: 9 Mar e +50; 10 Mar b +100; 11 Mar d -50.  March: +100 over 3 trades.
# Held: a (9 -> 10 Mar) +500; c (10 -> 11 Mar) -300; h (11 -> 12 Mar) +40.
# 12 Mar has only h closing, so it is no traded cell. The text table has 3 rows.
RECORD = [
    trip("e", "2026-03-09T09:40", "2026-03-09T10:00", "50"),
    trip("a", "2026-03-09T14:00", "2026-03-10T10:00", "500"),
    trip("b", "2026-03-10T09:40", "2026-03-10T10:00", "100"),
    trip("c", "2026-03-10T14:00", "2026-03-11T10:00", "-300"),
    trip("d", "2026-03-11T11:00", "2026-03-11T11:20", "-50"),
    trip("h", "2026-03-11T14:00", "2026-03-12T10:00", "40"),
]
NONE_HELD = [RECORD[0], RECORD[2], RECORD[4]]


def text(html: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html)))


def page(engine, monkeypatch, record) -> str:
    client = sign_up(TestClient(create_app()), engine, "C-1", "visitor")
    client.post("/upload/demo", data={"csrf_token": CSRF.search(client.get("/upload").text).group(1)})
    real = RM.load_record

    def load(request):
        early, got = real(request)
        if early is not None:
            return early, got
        return None, (record, got[1], SF.record_context(record))

    monkeypatch.setattr(RM, "load_record", load)
    monkeypatch.setattr(RN, "load_record", load)
    return client.get("/numbers").text


def cal(html: str) -> str:
    found = re.search(r'<section class="cal" id="calendar">.*?</section>', html, re.DOTALL)
    assert found, "no calendar on the page"
    return found.group(0)


def test_the_months_total_is_the_same_day_trades(engine, monkeypatch):
    body = text(cal(page(engine, monkeypatch, RECORD)))
    assert "Mar 2026 +₹100 · 3 trades" in body


def test_a_day_when_only_a_held_position_closed_is_no_traded_cell(engine, monkeypatch):
    c = cal(page(engine, monkeypatch, RECORD))
    titles = [unescape(t) for t in re.findall(r"<title>([^<]+)</title>", c)]
    assert titles == ["09 Mar 2026: 1 trade, +₹50", "10 Mar 2026: 1 trade, +₹100",
                      "11 Mar 2026: 1 trade, −₹50"]


@pytest.mark.parametrize("record, want", [(RECORD, "&amp;same_day=yes"), (NONE_HELD, "")])
def test_a_cells_link_reads_same_day_trades_only_when_some_were_held(engine, monkeypatch, record, want):
    c = cal(page(engine, monkeypatch, record))
    hrefs = re.findall(r'<a href="([^"]+)" class="cal__day">', c)
    assert hrefs and all(h.endswith(want) for h in hrefs)
    if not want:
        assert all("same_day" not in h for h in hrefs)
