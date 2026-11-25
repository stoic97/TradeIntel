"""TICKET-1050: the shape of your days on Your numbers - every figure opens exactly its trades,
and the lines are decided from his file.

Follow-up to the shape of your days (gates 6 and 9). Every figure in the four blocks opens a list
holding exactly the trades it counts, including the "Other options" cells and the longest hold;
a filter a link chose still narrows the list when his record has only one group of it; the
lines are decided from his record; the session opens come from the instrument profiles. Each
block is read off the rendered page, with his record put behind the routes in place of the demo
file. Every trade here is made up; the expected values are worked by hand in the comments.
"""
from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path
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


def trip(tid: str, opened: str, net: str, closed: str | None = None, segment: str = "OPT",
         symbol: str = "NIFTY") -> mx.Trip:
    entry = datetime.fromisoformat(opened).replace(tzinfo=IST)
    leave = datetime.fromisoformat(closed).replace(tzinfo=IST) if closed else entry.replace(
        minute=min(entry.minute + 5, 59))
    line = mx.TradeLine(symbol, segment, "Buy", 1, None, None, D(net), entry_ts=entry)
    return mx.Trip(trip_id=tid, symbol=symbol, trading_day=entry.date().isoformat(), entry_ts=entry,
                   exit_ts=leave, holding_seconds=int((leave - entry).total_seconds()), net=D(net),
                   lots=1, risk_unit_source=s.RiskUnitSourceV1.PREMIUM_PAID,
                   is_option=segment == "OPT", lines=(line,))


# Three books: NIFTY options (8 trades, under the named-book minimum, so "Other options"),
# Futures (CRUDEOIL), Stocks and ETFs (TATASTEEL). A day is the day he closed.
#   Mon 2 Feb  a1 opt 09:20 -100   a2 fut 09:10 -50   a3 share 10:00 +30       -> -120, 3 trades
#   Tue 3 Feb  b1 opt 09:50 -200   b2 fut 17:05 -100 (MCX evening)              -> -300, 2 trades
#   Wed 4 Feb  c1 opt 11:00 +500   g1 fut opened Tue 22:00, closed Wed -60      -> +440, 2 trades
#   Thu 5 Feb  d1 opt 09:15 -40                                                 ->  -40, 1 trade
#   Fri 6 Feb  e2 share 10:00 +10                                               ->  +10, 1 trade
#   Mon 9 Feb  e1 opt opened Fri 6 Feb 14:00, closed Mon 09:30 +80 (3 days: the longest hold)
#              f1 opt 09:40 -10   f2 opt 10:10 -10   f3 opt 11:10 -10           ->  +50, 4 trades
# Losing days, worst first: 3 Feb -300, 2 Feb -120, 5 Feb -40. The two that made money (4 and
# 9 Feb, +440 and +50) and 6 Feb (+10) are not worst days, though he has fewer than five losing.
RECORD = [
    trip("a1", "2026-02-02T09:20", "-100"),
    trip("a2", "2026-02-02T09:10", "-50", segment="FUT", symbol="CRUDEOIL"),
    trip("a3", "2026-02-02T10:00", "30", segment="EQ", symbol="TATASTEEL"),
    trip("b1", "2026-02-03T09:50", "-200"),
    trip("b2", "2026-02-03T17:05", "-100", segment="FUT", symbol="CRUDEOIL"),
    trip("g1", "2026-02-03T22:00", "-60", closed="2026-02-04T10:00", segment="FUT", symbol="CRUDEOIL"),
    trip("c1", "2026-02-04T11:00", "500"),
    trip("d1", "2026-02-05T09:15", "-40"),
    trip("e2", "2026-02-06T10:00", "10", segment="EQ", symbol="TATASTEEL"),
    trip("e1", "2026-02-06T14:00", "80", closed="2026-02-09T09:30"),
    trip("f1", "2026-02-09T09:40", "-10"),
    trip("f2", "2026-02-09T10:10", "-10"),
    trip("f3", "2026-02-09T11:10", "-10"),
]

# One group of each: every trade closed the same day he opened it, every one after its session's
# first 30 minutes, two trades on each of two days.
#   Mon 2 Feb  h1 NIFTY opt 11:00 +40   h2 share 12:00 -20
#   Tue 3 Feb  h3 NIFTY opt 11:00 -30   h4 share 12:00 +10
# Held overnight: no row has an overnight trade; "Closed the same day" counts h1 and h3 (the
# shares apart). First 30 minutes: none; "The rest" counts all four. One day size: 2 trades a day.
ONE_GROUP = [
    trip("h1", "2026-02-02T11:00", "40"),
    trip("h2", "2026-02-02T12:00", "-20", segment="EQ", symbol="TATASTEEL"),
    trip("h3", "2026-02-03T11:00", "-30"),
    trip("h4", "2026-02-03T12:00", "10", segment="EQ", symbol="TATASTEEL"),
]


def query_of(href: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlparse(href).query).items()}


def kept(href: str, record: list[mx.Trip]) -> list[str]:
    """The trades the list a link opens holds, by id, read through the list itself."""
    ctx = SF.record_context(record)
    view = TL.listing("risk", ctx, query_of(href), {})
    return sorted(ctx["trips"][t["number"] - 1].trip_id for g in view["groups"] for t in g["trades"])


# ---------- 1. every figure opens exactly its trades ----------

def test_the_other_options_cells_open_exactly_their_trades():
    wb = N.worst_books(RECORD)
    other = [c for d in wb["days"] for c in d["cells"] if c["book"] == mx.OTHER_OPTIONS and c["trades"]]
    assert other, "no Other options cell on a worst day"
    for c in other:
        assert c["href"], "an Other options cell with trades has no link"
    by_day = {d["day"]: next(c for c in d["cells"] if c["book"] == mx.OTHER_OPTIONS) for d in wb["days"]}
    assert kept(by_day["2026-02-03"]["href"], RECORD) == ["b1"]
    assert kept(by_day["2026-02-02"]["href"], RECORD) == ["a1"]
    assert kept(by_day["2026-02-05"]["href"], RECORD) == ["d1"]


def test_every_worst_day_cell_and_row_opens_exactly_its_trades():
    for d in N.worst_books(RECORD)["days"]:
        closed = sorted(t.trip_id for t in RECORD if t.exit_ts.date().isoformat() == d["day"])
        assert kept(d["href"], RECORD) == closed
        for c in d["cells"]:
            if c["trades"]:
                assert len(kept(c["href"], RECORD)) == c["trades"], (d["day"], c["book"])


def test_the_longest_hold_opens_only_the_trade_it_is_about():
    o = N.overnight(RECORD)
    assert o["longest"] == 3
    assert kept(o["longest_href"], RECORD) == ["e1"]  # not the whole of 9 Feb (e1 f1 f2 f3)


@pytest.mark.parametrize("block", ["day_trades", "first_half_hour", "overnight"])
def test_every_row_opens_exactly_its_trades(block):
    rows = N.day_trades(RECORD)["thirds"] if block == "day_trades" else getattr(N, block)(RECORD)["rows"]
    for r in rows:
        count = r["trades"]
        if count:
            assert len(kept(r["href"], RECORD)) == count, (block, r.get("label") or r.get("name"))


# ---------- 2. a record with one group of each: a link still narrows ----------

def test_with_one_group_each_link_still_opens_only_its_trades():
    same = next(r for r in N.overnight(ONE_GROUP)["rows"] if r["name"] == "Closed the same day")
    assert same["trades"] == 2 and kept(same["href"], ONE_GROUP) == ["h1", "h3"]  # not the shares
    rest = next(r for r in N.first_half_hour(ONE_GROUP)["rows"] if r["name"] == "The rest")
    assert rest["trades"] == 4 and kept(rest["href"], ONE_GROUP) == ["h1", "h2", "h3", "h4"]
    (third,) = N.day_trades(ONE_GROUP)["thirds"]
    assert third["trades"] == 4 and kept(third["href"], ONE_GROUP) == ["h1", "h2", "h3", "h4"]


def test_a_filter_a_link_chose_shows_on_the_list_even_with_one_choice():
    same = next(r for r in N.overnight(ONE_GROUP)["rows"] if r["name"] == "Closed the same day")
    view = TL.listing("risk", SF.record_context(ONE_GROUP), query_of(same["href"]), {})
    assert view["filtered"] and view["shown"] == 2 and view["total"] == 4


# ---------- 3. the lines are decided from his file ----------

def test_days_that_made_money_are_never_called_worst():
    wb = N.worst_books(RECORD)
    assert [d["day"] for d in wb["days"]] == ["2026-02-03", "2026-02-02", "2026-02-05"]
    assert all(d["net"] < 0 for d in wb["days"]) and wb["count"] == 3


def test_a_record_with_no_losing_day_has_no_worst_days_block():
    winners = [t for t in RECORD if t.net > 0]
    assert N.worst_books(winners)["shown"] is False


# ---------- 4. the session opens come from the instrument profiles ----------

def test_the_session_opens_are_read_from_the_profiles():
    # CRUDEOIL's profile opens MCX at 09:00; NIFTY's opens NSE at 09:15; a share is read from the
    # cash-equity profiles, NSE's and BSE's, both 09:15.
    opens = N.first_half_hour(RECORD)["opens"]
    assert opens == [{"time": "09:00", "exchanges": ["MCX"]}, {"time": "09:15", "exchanges": ["BSE", "NSE"]}]


def test_the_template_types_no_session_time():
    text = Path("services/production/api/templates/_opening.html").read_text(encoding="utf-8")
    assert not re.search(r"\b\d{2}:\d{2}\b", text)


# ---------- 5. each block on the rendered page ----------

@pytest.fixture()
def page_of(engine, monkeypatch):
    """The routes read the given record in place of the demo file's trades (the demo upload
    gives a real import for the page's header)."""
    def make(record: list[mx.Trip]):
        client = sign_up(TestClient(create_app()), engine, "S-2", "shapes")
        client.post("/upload/demo", data={"csrf_token": CSRF.search(client.get("/upload").text).group(1)})
        real = loader.load_for
        monkeypatch.setattr(loader, "load_for", lambda sess, trader: (record, real(sess, trader)[1]))
        return client
    return make


def section(html: str, sid: str) -> str:
    found = re.search(rf'<section class="[^"]*" id="{sid}">.*?</section>', html, re.DOTALL)
    assert found, sid
    return found.group(0)


def plain(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def hrefs(html: str) -> list[str]:
    return [h.replace("&amp;", "&") for h in re.findall(r'href="([^"]+)"', html)]


def listed_on_page(client, href: str) -> int:
    return client.get(href).text.count('<article class="trade">')


def test_the_worst_days_block_on_the_page(page_of):
    client = page_of(RECORD)
    block = section(client.get("/numbers").text, "worst-books")
    # Every book he traded lost on 3 Feb (b1, b2) and on 5 Feb (d1 alone); 2 Feb's share made money.
    assert "On your 3 worst days, every book you traded lost on 2." in plain(block)
    links = hrefs(block)
    assert len(links) == 3 + 6  # three days; book cells with trades: 3 Feb two, 2 Feb three, 5 Feb one
    for href in links:
        assert listed_on_page(client, href) >= 1, href
    assert listed_on_page(client, links[0]) == 2  # 3 Feb: b1 and b2


def test_one_worst_day_reads_in_the_singular(page_of):
    record = [t for t in RECORD if t.trip_id not in {"a1", "a2", "d1"}]  # only 3 Feb loses
    block = section(page_of(record).get("/numbers").text, "worst-books")
    assert "On your 1 worst day, every book you traded lost on 1." in plain(block)


def test_the_day_trades_block_on_the_page(page_of):
    client = page_of(RECORD)
    block = section(client.get("/numbers").text, "day-trades")
    # Days by trades closed: 1, 1, 2, 2, 3, 4 (5 Feb and 6 Feb one each). Thirds cut at 1 and 2.
    assert "Your days in three groups" in plain(block)
    for href in hrefs(block):
        assert listed_on_page(client, href) >= 1, href


def test_two_groups_are_not_called_three(page_of):
    block = section(page_of(ONE_GROUP).get("/numbers").text, "day-trades")
    assert "three groups" not in plain(block)


def test_the_opening_block_on_the_page(page_of):
    client = page_of(RECORD)
    block = section(client.get("/numbers").text, "opening")
    assert "09:00 on MCX, 09:15 on BSE and NSE" in plain(block)
    # First 30 minutes: a2 09:10 (MCX, open 09:00); a1 09:20, d1 09:15, f1 09:40 (NSE, before
    # 09:45): 4. The rest: 9.
    first, rest = hrefs(block)
    assert (listed_on_page(client, first), listed_on_page(client, rest)) == (4, 9)


def test_the_overnight_block_on_the_page(page_of):
    client = page_of(RECORD)
    block = section(client.get("/numbers").text, "overnight")
    text = plain(block)
    assert "The longest was held 3 days" in text and "2 trades in shares are counted apart." in text
    links = hrefs(block)
    longest = next(h for h in links if "held_days=" in h)
    assert listed_on_page(client, longest) == 1
