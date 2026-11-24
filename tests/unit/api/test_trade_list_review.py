"""TICKET-1033 review (24 Nov): a page value that is not a plain number opens page 1, never a
500; the chosen sort survives the filter form and "Clear filters"; a filter, a sort and a second
page hold together.

Made-up record: 250 trades, every third a loser of -40, the rest winners of +100, so 166
winners (two pages of 100) and 84 losers.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from services.production.api import scope_facts as SF
from services.production.api import trade_list as TL
from tests.helpers.scope_chapters import trips_from
from tests.helpers.trade_rows import tradebook
from tests.helpers.upload import upload

MANY = trips_from([100 if i % 3 else -40 for i in range(250)])


def listing(**query):
    return TL.listing("risk", SF.record_context(MANY), {k: str(v) for k, v in query.items()}, {})


def test_a_page_that_is_not_a_plain_number_opens_page_one():
    for raw in ("²", "abc", "1.5", "", "-1", "9" * 5000):
        assert listing(page=raw)["page"] == 1, raw


def test_a_filter_a_sort_and_a_second_page_hold_together():
    view = listing(result="winners", sort="newest")
    assert view["shown"] == 166 and view["pages"] == 2
    assert parse_qs(urlparse(view["next_href"]).query) == {
        "result": ["winners"], "sort": ["newest"], "page": ["2"]}
    second = listing(result="winners", sort="newest", page=2)
    assert (second["first"], second["last"]) == (101, 166)


def test_clear_filters_keeps_the_chosen_sort():
    query = parse_qs(urlparse(listing(result="winners", sort="newest")["clear_href"]).query)
    assert query == {"sort": ["newest"]}


def few(client):
    contract = "WIDGETOIL 19 NOV 5000 CALL"
    tail = "INTRADAY,MCX,Commodity,100"
    rows = tuple(
        line for i in range(6) for line in (
            f"2026-08-0{i + 1},10:00:00,{contract},BUY,{tail},10.00,1000.00,Traded",
            f"2026-08-0{i + 1},10:05:00,{contract},SELL,{tail},{'11.00' if i % 2 else '9.50'},{'1100.00' if i % 2 else '950.00'},Traded",
        ))
    assert upload(client, content=tradebook(rows)).status_code == 303


def test_a_bad_page_value_on_the_page_is_not_a_server_error(client, engine):
    few(client)
    assert client.get("/mirror/fact/risk/trades?page=%C2%B2").status_code == 200


def test_the_filter_form_carries_the_chosen_sort(client, engine):
    few(client)
    html = client.get("/mirror/fact/risk/trades?sort=newest").text
    form = re.search(r'<form class="trade-filters".*?</form>', html, re.S).group(0)
    assert re.search(r'<input type="hidden" name="sort" value="newest"\s*/?>', form)
