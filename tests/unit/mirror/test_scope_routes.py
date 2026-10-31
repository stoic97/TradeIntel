"""The Scope's routes (handoff 5): who may open a chapter, and what an odd URL gets.

The pages themselves are tested in tests/unit/api/test_scope_chapters.py; this is the
route around them, through the app, with the 40-trade fixture trader signed in.
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
