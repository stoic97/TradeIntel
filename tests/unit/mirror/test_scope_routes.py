"""The Scope's routes (handoff 5): who may open a chapter or a fact, and what an odd URL gets.

The pages themselves are tested in tests/unit/api/test_scope_chapters.py; this is the
route around them, through the app, with the 40-trade fixture trader signed in. The
fact pages are in tests/unit/api/test_scope_facts.py.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from services.production.api import scope_map as S
from services.production.api.app import create_app


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_each_chapter_opens(client, n):
    r = client.get(f"/mirror/chapter/{n}")
    assert r.status_code == 200
    assert f"CHAPTER {n} OF 4" in r.text
    assert r.text.count('<a class="story-card') == len(S.chapter(n).facts)


@pytest.mark.parametrize("n", ["0", "5", "x"])
def test_there_is_no_fifth_chapter(client, n):
    assert client.get(f"/mirror/chapter/{n}").status_code in (404, 422)


def test_signed_out_goes_to_sign_in(engine):
    r = TestClient(create_app()).get("/mirror/chapter/1", follow_redirects=False)
    assert (r.status_code, r.headers["location"]) == (303, "/login")


@pytest.mark.parametrize(
    ("query", "cls"),
    [
        ("?enter=in&tap=2", "vt-in vt-tap-2"),
        ("?enter=back&fact=1", "vt-back"),
        ("", None),
        ("?enter=in&tap=9", None),  # a tap that is no chapter
        ('?enter="><script>', None),  # anything else is no class at all
    ],
)
def test_the_page_is_told_how_it_was_entered(client, query, cls):
    html = client.get(f"/mirror/chapter/2{query}").text
    head = html[: html.index("<head>")]
    if cls:
        assert f'<html lang="en" class="{cls}">' in head
    else:
        assert '<html lang="en">' in head
    assert "<script>" not in head


def test_the_long_mirror_page_still_opens_until_scope_home_replaces_it(client):
    assert client.get("/mirror").status_code == 200


@pytest.mark.parametrize("key", list(S.FACTS))
def test_each_fact_opens(client, key):
    r = client.get(S.fact_href(key))
    assert r.status_code == 200
    assert f'aria-current="page">{S.FACTS[key].title}</span>'.replace("'", "&#39;") in r.text
    assert '<html lang="en" class="vt-lens">' in r.text


def test_an_unknown_fact_is_not_found(client):
    assert client.get("/mirror/fact/edge").status_code == 404


def test_a_fact_lists_every_trade_behind_it_from_the_database(client):
    """The fixture's 40 trades, through the loader: every one on the strike-rate page."""
    assert client.get("/mirror/fact/strike").text.count('<article class="trade">') == 40


def test_what_we_could_not_read_reads_the_import_rows(client):
    r = client.get("/mirror/fact/unread")
    assert r.status_code == 200
    assert "The rows behind this" in r.text
    assert "Computed from import" in r.text


def test_a_fact_is_signed_in_only(engine):
    r = TestClient(create_app()).get("/mirror/fact/share", follow_redirects=False)
    assert (r.status_code, r.headers["location"]) == (303, "/login")
