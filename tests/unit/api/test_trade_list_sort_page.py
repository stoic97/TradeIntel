"""TICKET-1033: the trade lists sort, page by 100, show one dense row per trade, and head their
groups in words.

Every record here is made up. A list still holds every trade behind its fact: paging splits it,
never samples it, and the count line says the whole.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

from services.production.api import scope_facts as SF
from services.production.api import trade_list as TL
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s
from tests.helpers.scope_chapters import trips_from
from tests.helpers.trade_rows import tradebook
from tests.helpers.upload import upload

START = datetime.fromisoformat("2026-09-01T09:15:00+05:30")


def trip(i: int, net: int, held_minutes: int = 10) -> mx.Trip:
    entry = START + timedelta(days=i)
    return mx.Trip(f"t{i}", "WIDGETOIL", entry.date().isoformat(), entry,
                   entry + timedelta(minutes=held_minutes), held_minutes * 60, Decimal(net), 1,
                   s.RiskUnitSourceV1.DECLARED_BUDGET)


class View(dict):
    def __missing__(self, key):
        raise AssertionError(f"the listing has no {key!r}")


def listing(trips, **query):
    return View(TL.listing("risk", SF.record_context(trips), {k: str(v) for k, v in query.items()}, {}))


def order(view) -> list[int]:
    """The trades on the page, by their place in the record (1 is the first trade opened)."""
    return [t["number"] for g in view["groups"] for t in g["trades"]]


# ---------- 1. sort ----------
# Opened in this order: t0 -300, t1 +100, t2 -300, t3 -50, t4 +100.
RECORD = [trip(0, -300, 5), trip(1, 100, 40), trip(2, -300, 40), trip(3, -50, 15), trip(4, 100, 5)]


def test_five_sorts_offered_as_links():
    view = listing(RECORD)
    assert [x["label"] for x in view["sorts"]] == ["Newest", "Oldest", "Biggest loss", "Biggest win",
                                                   "Longest held"]
    assert [x["value"] for x in view["sorts"]] == ["newest", "oldest", "biggest-loss", "biggest-win",
                                                   "longest-held"]
    assert next(x for x in view["sorts"] if x["on"])["value"] == "oldest"  # today's order stays the default


def test_each_sort_with_ties_going_to_the_earlier_trade():
    assert order(listing(RECORD, sort="oldest")) == [1, 2, 3, 4, 5]
    assert order(listing(RECORD, sort="newest")) == [5, 4, 3, 2, 1]
    assert order(listing(RECORD, sort="biggest-loss")) == [1, 3, 4, 2, 5]  # -300 t0, -300 t2, -50, then +100s
    assert order(listing(RECORD, sort="biggest-win")) == [2, 5, 4, 1, 3]   # +100 t1, +100 t4, -50, -300s
    assert order(listing(RECORD, sort="longest-held")) == [2, 3, 4, 1, 5]  # 40 t1, 40 t2, 15, 5 t0, 5 t4


def test_an_unknown_sort_is_ignored_like_a_stale_filter():
    assert order(listing(RECORD, sort="nonsense")) == [1, 2, 3, 4, 5]


# ---------- 2. paging ----------

MANY = trips_from([100 if i % 3 else -40 for i in range(250)])


def test_a_hundred_to_a_page_and_the_count_says_the_whole():
    first, third = listing(MANY), listing(MANY, page=3)
    assert len(order(first)) == 100 and len(order(third)) == 50
    assert (first["shown"], first["total"]) == (250, 250)
    assert (first["first"], first["last"], first["pages"]) == (1, 100, 3)
    assert (third["first"], third["last"]) == (201, 250) and third["next_href"] is None


def test_the_next_link_keeps_the_sort_and_the_filters():
    view = listing(MANY, sort="biggest-loss", result="losers")
    assert view["next_href"] is None  # 84 losers: one page
    view = listing(MANY, sort="newest")
    query = parse_qs(urlparse(view["next_href"]).query)
    assert query == {"sort": ["newest"], "page": ["2"]}
    assert listing(MANY, sort="newest", page=2)["prev_href"] is not None


def test_every_trade_is_on_exactly_one_page():
    pages = [order(listing(MANY, page=p)) for p in (1, 2, 3)]
    flat = [n for p in pages for n in p]
    assert sorted(flat) == list(range(1, 251)) and len(flat) == len(set(flat))


def test_filter_sort_and_page_together():
    losers = [t for t in MANY if t.net < 0]
    view = listing(MANY, result="losers", sort="newest", page=1)
    assert view["shown"] == len(losers) == 84
    assert order(view) == sorted((int(t.trip_id[1:]) + 1 for t in losers), reverse=True)


def test_a_page_past_the_end_shows_the_last_page():
    assert listing(MANY, page=99)["first"] == 201


# ---------- 4. group headings in words ----------

def test_the_risk_list_unfiltered_keeps_its_own_groups():
    assert [g["title"] for g in listing(RECORD)["groups"]] == ["Your declared budget"]


def test_a_filtered_list_is_headed_by_what_is_in_it():
    titles = [g["title"] for g in listing(RECORD, result="losers")["groups"]]
    assert titles == ["Losers"]
    assert "Your declared budget" not in titles


def test_a_sorted_list_is_one_group_headed_in_words():
    assert [g["title"] for g in listing(RECORD, sort="biggest-loss")["groups"]] == ["Biggest loss first"]
    assert [g["title"] for g in listing(RECORD, result="losers", sort="newest")["groups"]] == [
        "Losers · newest first"]


# ---------- 3, 5. the page: a dense row, its weight ----------

def two_thousand(client):
    contract = "WIDGETOIL 19 NOV 5000 CALL"
    tail = "INTRADAY,MCX,Commodity,100"
    rows = tuple(
        line
        for i in range(2000)
        for line in (
            f"2026-{(i // 1400) + 8:02d}-{(i // 50) % 28 + 1:02d},{9 + (i % 50) // 6:02d}:{(i % 6) * 9:02d}:00,{contract},BUY,{tail},10.00,1000.00,Traded",
            f"2026-{(i // 1400) + 8:02d}-{(i // 50) % 28 + 1:02d},{9 + (i % 50) // 6:02d}:{(i % 6) * 9 + 4:02d}:00,{contract},SELL,{tail},{'11.00' if i % 3 else '9.50'},{'1100.00' if i % 3 else '950.00'},Traded",
        )
    )
    assert upload(client, content=tradebook(rows)).status_code == 303


def test_the_list_page_is_light_paged_and_dense(client, engine):
    two_thousand(client)
    html = client.get("/mirror/fact/risk/trades").text
    assert len(html.encode()) < 150_000, len(html.encode())
    assert html.count('<article class="trade trade--dense">') == 100
    assert "Show the next 100" in html
    assert '<details class="trade__more">' in html  # prices and premium behind a tap
    nxt = re.search(r'href="([^"]*page=2[^"]*)"', html).group(1).replace("&amp;", "&")
    assert client.get(nxt).status_code == 200
    assert 'href="?sort=biggest-loss"' in html.replace("&amp;", "&") or "sort=biggest-loss" in html


def test_the_day_page_keeps_its_full_rows(client, engine):
    two_thousand(client)
    day = client.get("/mirror/day/2026-08-01").text
    assert '<details class="trade__more">' not in day and "trade--dense" not in day
