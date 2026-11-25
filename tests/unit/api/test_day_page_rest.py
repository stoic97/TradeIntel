"""TICKET-1086: the day page and the worst days, the rest of TICKET-1049.

The three run-page sentences of a worst day are each read off the rendered page; the day page
says which order its rings mark, since its dots are drawn as trades closed and a switch is
counted as they were opened; "A trade counts here on the day you opened it." is said only when
his file has a trade that closed on a later day, and never in the too-few-days state.

Every trade here is made up and every figure is worked by hand below. The records are put
behind the routes in place of the demo file's trades.
"""
from __future__ import annotations

import html as html_lib
import re
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from services.production.api.app import create_app
from services.production.mirror import loader
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s
from tests.helpers.upload import CSRF, sign_up

IST = ZoneInfo("Asia/Kolkata")
D = Decimal
COUNTED_ON = "A trade counts here on the day you opened it."
RINGS_SAY = "A ringed dot switched between a call and a put from the trade you opened before it."


def trip(tid: str, opened: str, closed: str, net: int, side: str, quantity: int = 75) -> mx.Trip:
    entry = datetime.fromisoformat(opened).replace(tzinfo=IST)
    leave = datetime.fromisoformat(closed).replace(tzinfo=IST)
    line = mx.TradeLine("NIFTY", "OPT", "Buy", quantity, D(100), D(100), D(net), strike=D(24000),
                        option_type=side, entry_ts=entry)
    return mx.Trip(trip_id=tid, symbol="NIFTY", trading_day=entry.date().isoformat(), entry_ts=entry,
                   exit_ts=leave, holding_seconds=int((leave - entry).total_seconds()), net=D(net),
                   lots=quantity // 75, risk_unit_source=s.RiskUnitSourceV1.PREMIUM_PAID, is_option=True,
                   lines=(line,))


def plain(fragment: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def main_of(page: str) -> str:
    m = re.search(r"<main.*?</main>", page, re.DOTALL)
    return m.group(0) if m else page


@pytest.fixture()
def page_of(engine, monkeypatch):
    """The routes read the given record in place of the demo file's trades."""
    def make(record: list[mx.Trip]):
        client = sign_up(TestClient(create_app()), engine, "D-9", "daysrest")
        client.post("/upload/demo", data={"csrf_token": CSRF.search(client.get("/upload").text).group(1)})
        real = loader.load_for
        monkeypatch.setattr(loader, "load_for", lambda sess, trader: (record, real(sess, trader)[1]))
        return client
    return make


# ---------- 1. all three run-page sentences of a worst day, on the page ----------

# One day, all NIFTY options, worked by hand, in the order opened:
#   s1 CE 1 lot  09:00-09:05 -100
#   s2 PE 1 lot  09:06-09:10 -100   back in 60 s after s1 closed; a switch (CE -> PE)
#   s3 CE 3 lots 09:11-09:20 -100   back in 60 s after s2 closed; a switch (PE -> CE);
#                                   size 1 -> 3 lots, straight after 2 losses
# Switches: 2 ("2 times"). Size: 75 -> 225, tripled, after two losses. Back in within 2 minutes: 2 of 2.
STORY = [
    trip("s1", "2026-03-16T09:00", "2026-03-16T09:05", -100, "CE"),
    trip("s2", "2026-03-16T09:06", "2026-03-16T09:10", -100, "PE"),
    trip("s3", "2026-03-16T09:11", "2026-03-16T09:20", -100, "CE", quantity=225),
]


def test_all_three_run_page_sentences_of_a_worst_day_are_on_the_page(page_of):
    html = main_of(page_of(STORY).get("/mirror/fact/worst-days").text)
    block = re.search(r'<details class="day-block" id="day-2026-03-16">.*?</details>', html, re.DOTALL)
    assert block, "no block for 16 Mar"
    lines = plain(re.search(r'<div class="run__lines day-block__story">.*?</div>', block.group(0),
                            re.DOTALL).group(0))
    assert "You switched between calls and puts 2 times." in lines
    assert "After two losses you tripled your size (75 → 225)." in lines
    assert "2 of 2 times, you were back in within 2 minutes." in lines


# ---------- 2. the rings say which order they mark ----------

# One day, in the order opened:
#   e1 CE 09:00-09:10   e2 PE 09:05-11:00   e3 CE 09:20-09:30   e4 CE 09:40-09:50
# Opened: CE PE CE CE, so e2 and e3 switched. Dots, as they closed: e1 CE, e3 CE (ringed),
# e4 CE, e2 PE (ringed). e3's ring sits between two calls: the ring is the order opened.
RING = [
    trip("e1", "2026-03-23T09:00", "2026-03-23T09:10", -100, "CE"),
    trip("e2", "2026-03-23T09:05", "2026-03-23T11:00", -100, "PE"),
    trip("e3", "2026-03-23T09:20", "2026-03-23T09:30", -100, "CE"),
    trip("e4", "2026-03-23T09:40", "2026-03-23T09:50", -100, "CE"),
]


def test_a_ring_between_two_calls_is_the_order_opened():
    path = mx.day_path(RING)
    closed = [(p.trip.trip_id, p.side, p.switched) for p in path.points]
    assert closed == [("e1", "CE", False), ("e3", "CE", True), ("e4", "CE", False), ("e2", "PE", True)]


def test_the_day_page_says_which_order_its_rings_mark(page_of):
    text = plain(main_of(page_of(RING).get("/mirror/day/2026-03-23").text))
    assert RINGS_SAY in text


def test_a_day_with_no_ring_says_nothing_about_rings(page_of):
    same_side = [trip("n1", "2026-03-23T09:00", "2026-03-23T09:10", -100, "CE"),
                 trip("n2", "2026-03-23T09:20", "2026-03-23T09:30", -100, "CE")]
    text = plain(main_of(page_of(same_side).get("/mirror/day/2026-03-23").text))
    assert RINGS_SAY not in text


def test_the_docstrings_say_the_order_opened():
    assert "order they were opened" in mx.DayPoint.__doc__
    from services.production.api import day_chart
    assert "order they were opened" in day_chart.__doc__


# ---------- 3. "the day you opened it" is decided from his file ----------

# Every trade closes the day it opened: the day he opened and the day he closed are one day, so
# the sentence would say nothing. Five days, one loss each, so the worst days have no state.
SAME_DAY = [trip(f"d{i}", f"2026-04-0{i}T09:00", f"2026-04-0{i}T09:10", -100 * i, "CE") for i in range(1, 6)]

# The same, with one trade held overnight: now the two days differ, and the sentence is said.
WITH_OVERNIGHT = SAME_DAY + [trip("o1", "2026-04-03T14:00", "2026-04-06T10:00", -50, "PE")]


def test_no_overnight_trade_no_counted_on_line(page_of):
    client = page_of(SAME_DAY)
    for href in ("/mirror/fact/worst-days", "/mirror/chapter/1"):
        assert COUNTED_ON not in plain(main_of(client.get(href).text)), href


def test_an_overnight_trade_brings_the_counted_on_line(page_of):
    client = page_of(WITH_OVERNIGHT)
    assert COUNTED_ON in plain(main_of(client.get("/mirror/fact/worst-days").text))
    html = client.get("/mirror/chapter/1").text
    card = re.search(r'<a class="story-card[^"]*" href="/mirror/fact/worst-days[^"]*">.*?</a>', html, re.DOTALL)
    assert card and COUNTED_ON in plain(card.group(0))


def test_the_counted_on_line_follows_the_grouping_the_worst_days_use():
    # The worst days group each trade by trading_day, the day it was opened.
    worst = mx.five_worst_days(WITH_OVERNIGHT)
    o3 = next(d for d in worst.days if d.trading_day == "2026-04-03")
    assert o3.net == D(-350) and o3.trips == 2  # d3 -300 and o1 -50, both opened 3 Apr
    assert mx.WORST_DAYS_COUNT_ON == "opened"


def test_too_few_days_draws_no_counted_on_line():
    # The worst days' state (too few to count) draws no line, even with an overnight trade.
    from services.production.api import scope_facts as SF
    assert SF._counted_on("not-enough", WITH_OVERNIGHT) is None
    assert SF._counted_on(None, WITH_OVERNIGHT) == COUNTED_ON
    assert SF._counted_on(None, SAME_DAY) is None
