"""TICKET-1026, the review of 25 Nov 2026: the same-day sentence says which figures it covers, and
Home's "Made money ... needed N" reads as out_of_a_hundred_beside writes a rate beside another.

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



# Same-day trades: w1 +100, w2 +100, l1 -101, l2 -101; held: h opened 12 Mar, closed 13 Mar, +40.
# Win rate 2 of 4 = 50.0. Break even = 101 / (100 + 101) * 100 = 50.248...
# Both print "50 of 100" whole, so out_of_a_hundred_beside shows one decimal: 50.0 and 50.2.
TIE = [
    trip("w1", "2026-03-09T09:40", "2026-03-09T10:00", "100"),
    trip("l1", "2026-03-10T09:40", "2026-03-10T10:00", "-101"),
    trip("w2", "2026-03-11T09:40", "2026-03-11T10:00", "100"),
    trip("l2", "2026-03-12T09:40", "2026-03-12T10:00", "-101"),
    trip("h", "2026-03-12T14:00", "2026-03-13T10:00", "40"),
]


def test_the_same_day_sentence_names_the_figures_it_covers(made):
    body = text(made.get("/numbers").text)
    assert "These figures and the calendar read your same-day trades." in body
    assert "Every figure below" not in body


def test_the_same_day_sentence_sits_with_the_tiles_and_not_over_the_tables(made):
    html = made.get("/numbers").text
    said = html.index("read your same-day trades")
    tiles = html.index('class="numbers__grid"')
    assert said < tiles, "the sentence does not lead the tiles"
    for heading in ("By how close to expiry you closed",):
        assert said < html.index(heading)
    between = html[said:tiles]
    assert "<h2" not in between, "a heading sits between the sentence and the tiles"


def test_homes_made_money_and_needed_read_beside_each_other(demo, monkeypatch):
    body = text(drawn_from(demo, monkeypatch, TIE).get("/").text)
    assert "50.0 of 100" in body, body[:600]
    assert "needed 50.2 of 100" in body
