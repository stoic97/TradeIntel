"""Two facts became one (TICKET-819): every old way in still arrives.

Through the app, on the 40-trip contract history: an old link, a bookmark and a dwell
event written before the merge all read as the merged fact.
"""

from __future__ import annotations

import pytest

from services.production.api import scope_map as S


def test_the_chapter_has_three_facts_and_the_merged_one_is_first():
    assert [f.key for f in S.chapter(2).facts] == ["math", "run", "clock"]
    assert S.FACTS["math"].title == "Your wins and losses"
    assert "hold" not in S.FACTS and "strike" not in S.FACTS


@pytest.mark.parametrize("old", ["hold", "strike"])
def test_an_old_fact_url_redirects(client, old):
    got = client.get(f"/mirror/fact/{old}", follow_redirects=False)
    assert got.status_code == 301
    assert got.headers["location"] == "/mirror/fact/math"


@pytest.mark.parametrize("old", ["hold", "strike"])
def test_an_old_url_keeps_its_query(client, old):
    got = client.get(f"/mirror/fact/{old}?enter=lens", follow_redirects=False)
    assert got.headers["location"] == "/mirror/fact/math?enter=lens"


@pytest.mark.parametrize("old", ["hold", "strike"])
def test_an_old_trade_list_redirects_with_its_filters(client, old):
    got = client.get(f"/mirror/fact/{old}/trades?result=losers", follow_redirects=False)
    assert got.status_code == 301
    assert got.headers["location"] == "/mirror/fact/math/trades?result=losers"


@pytest.mark.parametrize("old", ["hold", "strike"])
def test_following_an_old_url_lands_on_the_merged_fact(client, old):
    got = client.get(f"/mirror/fact/{old}")
    assert got.status_code == 200
    assert "Your wins and losses" in got.text


def test_the_merged_fact_lists_its_trades(client):
    assert client.get("/mirror/fact/math/trades").status_code == 200


def test_an_unknown_fact_is_still_a_404(client):
    assert client.get("/mirror/fact/nope").status_code == 404
    assert client.get("/mirror/fact/nope/trades").status_code == 404


def test_the_dwell_line_on_the_page_is_the_merged_fact(client):
    assert 'data-dwell-line="math"' in client.get("/mirror/fact/math").text


@pytest.mark.parametrize("stored", ["holding-time", "hold", "strike"])
def test_a_stored_dwell_key_reads_as_the_merged_fact(stored):
    """The long page's key and the two fact pages' own keys, as events hold them today."""
    assert S.OLD_DWELL_LINES[stored] == "math"


def test_the_chapter_links_to_the_merged_fact_and_not_the_old_two(client):
    page = client.get(S.chapter_href(2)).text
    assert 'href="/mirror/fact/math?enter=lens"' in page
    assert "/mirror/fact/hold" not in page and "/mirror/fact/strike" not in page
