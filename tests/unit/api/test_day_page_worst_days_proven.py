"""TICKET-1049: the day page and the worst days, proven on the rendered page.

Follow-up to the days-you-can-replay ticket. The later-close sentence is read off the day page;
the worst-days page and the chapter 1 card say which day a trade counts on; the rings and "You
switched ..." count switches in one order, the order the trades were opened; a one-day record
draws no empty day navigation; "five" is never printed for fewer than five days; the worst
days' text table and their run-page sentences are read off the page.

Every trade here is made up and every figure is worked by hand below. The records are put
behind the routes in place of the demo file's trades.
"""
from __future__ import annotations

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


def trip(tid: str, opened: str, closed: str, net: int, side: str) -> mx.Trip:
    entry = datetime.fromisoformat(opened).replace(tzinfo=IST)
    leave = datetime.fromisoformat(closed).replace(tzinfo=IST)
    line = mx.TradeLine("NIFTY", "OPT", "Buy", 75, D(100), D(100), D(net), strike=D(24000),
                        option_type=side, entry_ts=entry)
    return mx.Trip(trip_id=tid, symbol="NIFTY", trading_day=entry.date().isoformat(), entry_ts=entry,
                   exit_ts=leave, holding_seconds=int((leave - entry).total_seconds()), net=D(net),
                   lots=1, risk_unit_source=s.RiskUnitSourceV1.PREMIUM_PAID, is_option=True, lines=(line,))


# Two days, an overnight trade between them. Worked by hand:
#   Mon 2 Mar  a1 CE 09:20-09:30 +500   a2 PE 09:31-09:40 -300
#              o1 CE opened 14:00, closed Tue 3 Mar 10:00 -800
#   Tue 3 Mar  b1 PE 09:20-09:30 -100
# By the day he opened (the worst-days page): 2 Mar -600 (a1 a2 o1), 3 Mar -100 (b1).
# By the day he closed (Your numbers):        2 Mar +200 (a1 a2),    3 Mar -900 (o1 b1).
# So the worst day is 2 Mar on the one and 3 Mar on the other: two figures, not one.
OVERNIGHT = [
    trip("a1", "2026-03-02T09:20", "2026-03-02T09:30", 500, "CE"),
    trip("a2", "2026-03-02T09:31", "2026-03-02T09:40", -300, "PE"),
    trip("o1", "2026-03-02T14:00", "2026-03-03T10:00", -800, "CE"),
    trip("b1", "2026-03-03T09:20", "2026-03-03T09:30", -100, "PE"),
]

# One day of overlapping trades:
#   c1 CE opened 09:00, closed 10:00 -100
#   c2 PE opened 09:10, closed 09:20 -100
#   c3 CE opened 09:30, closed 09:40 -100
# In the order opened: CE, PE, CE: two switches (c2 and c3). In the order closed: PE, CE, CE: one.
# Both the rings and the sentence count in the order opened: two, "2 times".
OVERLAP = [
    trip("c1", "2026-03-09T09:00", "2026-03-09T10:00", -100, "CE"),
    trip("c2", "2026-03-09T09:10", "2026-03-09T09:20", -100, "PE"),
    trip("c3", "2026-03-09T09:30", "2026-03-09T09:40", -100, "CE"),
]


@pytest.fixture()
def page_of(engine, monkeypatch):
    """The routes read the given record in place of the demo file's trades."""
    def make(record: list[mx.Trip]):
        client = sign_up(TestClient(create_app()), engine, "D-9", "daysreader")
        client.post("/upload/demo", data={"csrf_token": CSRF.search(client.get("/upload").text).group(1)})
        real = loader.load_for
        monkeypatch.setattr(loader, "load_for", lambda sess, trader: (record, real(sess, trader)[1]))
        return client
    return make


def plain(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def main_of(html: str) -> str:
    return html.split("<main", 1)[1].split("</main>", 1)[0]


# ---------- 2. the later-close sentence, on the rendered day page ----------

def test_the_day_page_says_how_many_closed_on_a_later_day(page_of):
    """Rewritten for TICKET-1026's one-date rule: Your numbers counts same-day trades, so the day page
    names the held trade and states the same-day figure Your numbers gives that day.
    2 Mar by hand: a1 +500 and a2 -300 are same-day, +200; o1 (-800) closed on 3 Mar and is held apart."""
    text = plain(page_of(OVERNIGHT).get("/mirror/day/2026-03-02").text).replace(" ,", ",")
    assert "1 of them closed on a later day and is held apart." in text
    assert "Your same-day trades this day came to +₹200, the figure Your numbers gives this day." in text
    assert "Your numbers counts each trade on the day it closed." not in text


def test_a_day_with_no_later_close_says_nothing_about_it(page_of):
    assert "closed on a later day" not in plain(page_of(OVERNIGHT).get("/mirror/day/2026-03-03").text)


# ---------- 3. the worst days say which day a trade counts on ----------

COUNTED_ON = "A trade counts here on the day you opened it."


def test_the_worst_days_page_says_a_trade_counts_on_the_day_it_was_opened(page_of):
    client = page_of(OVERNIGHT)
    text = plain(main_of(client.get("/mirror/fact/worst-days").text))
    assert COUNTED_ON in text
    numbers = plain(main_of(client.get("/numbers").text))
    # The two worst days differ on this record: the line is what tells them apart.
    assert "02 Mar 2026" in text and "03 Mar 2026" in numbers


def test_the_chapter_card_says_it_too(page_of):
    html = page_of(OVERNIGHT).get("/mirror/chapter/1").text
    card = re.search(r'<a class="story-card[^"]*" href="/mirror/fact/worst-days[^"]*">.*?</a>', html, re.DOTALL)
    assert card, "no worst-days card in chapter 1"
    assert COUNTED_ON in plain(card.group(0))


# ---------- 4. switches in one order ----------

def test_the_rings_and_the_sentence_count_switches_in_the_order_opened():
    path, story = mx.day_path(OVERLAP), mx.day_story(OVERLAP)
    assert sum(p.switched for p in path.points) == story.flips == 2
    assert {p.trip.trip_id for p in path.points if p.switched} == {"c2", "c3"}


def test_on_the_pages_the_rings_and_the_sentence_agree(page_of):
    client = page_of(OVERLAP)
    day = client.get("/mirror/day/2026-03-09").text
    assert day.count("daychart__dot--switched") == 2
    worst = plain(main_of(client.get("/mirror/fact/worst-days").text))
    assert "You switched between calls and puts 2 times." in worst


# ---------- 5. a one-day record, and fewer than five days ----------

def test_a_one_day_record_draws_no_empty_day_navigation(page_of):
    html = page_of(OVERLAP).get("/mirror/day/2026-03-09").text
    assert 'class="body-small day-nav"' not in html


def test_fewer_than_five_days_are_never_called_five(page_of):
    client = page_of(OVERNIGHT)
    for href in ("/mirror/fact/worst-days", "/mirror/chapter/1"):
        text = plain(main_of(client.get(href).text)).lower()
        assert "five days" not in text and "five worst" not in text, href  # "the five marks" is the ladder's
    text = plain(main_of(client.get("/mirror/fact/worst-days").text))
    assert "Your 2 worst days:" in text  # the share line this record draws (it has a losing day)


# ---------- 6. the text table and the run-page sentences, on the page ----------

def test_the_worst_days_text_table_on_the_page(page_of):
    html = main_of(page_of(OVERNIGHT).get("/mirror/fact/worst-days").text)
    table = re.search(r"<table[^>]*>\s*<caption>Your days, worst to best</caption>.*?</table>", html, re.DOTALL)
    assert table, "no text table of the days"
    rows = [plain(r) for r in re.findall(r"<tr>(.*?)</tr>", table.group(0), re.DOTALL)][1:]
    # Worst first by the day opened: 2 Mar -600 (running -600), 3 Mar -100 (running -700).
    assert rows == ["02 Mar 2026 −₹600 −₹600", "03 Mar 2026 −₹100 −₹700"]


def test_a_worst_days_run_page_sentences_on_the_page(page_of):
    html = main_of(page_of(OVERLAP).get("/mirror/fact/worst-days").text)
    block = re.search(r'<details class="day-block" id="day-2026-03-09">.*?</details>', html, re.DOTALL)
    assert block, "no block for 9 Mar"
    lines = plain(re.search(r'<div class="run__lines day-block__story">.*?</div>', block.group(0), re.DOTALL).group(0))
    assert lines.startswith("You switched between calls and puts 2 times.")
