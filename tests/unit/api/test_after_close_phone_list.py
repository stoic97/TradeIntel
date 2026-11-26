"""TICKET-1009: After you closed is a fact added after the phone dial was sized, so on a phone it
sits in the list under chapter 3's dial, in its desktop wedge's own words, and is not a phone
wedge. On desktop it keeps its wedge, last in the chapter.
"""

from __future__ import annotations

import re

import pytest

from services.production.api import scope_map as S
from tests.unit.api import figure_pages as P


@pytest.fixture()
def chapter_three() -> str:
    """Chapter 3 on the demo upload, as a visitor reads it."""
    from fastapi.testclient import TestClient

    from services.production.api.app import create_app
    app = create_app()
    client = TestClient(app)
    P._sign_up(client, app.state.engine, "visitor")
    P._consent(client)
    client.post("/upload/demo", data={"csrf_token": P._token(client, "/upload")}, follow_redirects=False)
    return client.get("/mirror/chapter/3").text


def _split(html: str) -> tuple[str, str]:
    phone, desktop = html.split('<div class="scope scope--desktop">', 1)
    return phone, desktop


def test_after_close_says_it_is_off_the_phone_dial():
    fact = next(f for c in S.CHAPTERS for f in c.facts if f.key == "after-close")
    assert fact.on_phone_dial is False


TITLE = "After you closed"


def _slices(html: str) -> list[str]:
    return re.findall(r'<a class="scope__slice.*?</a>', html, flags=re.DOTALL)


def test_after_close_is_a_row_in_the_phone_list_and_not_a_phone_wedge(chapter_three):
    phone, _ = _split(chapter_three)
    rows = re.findall(r'<li class="scope__list-row".*?</li>', phone, flags=re.DOTALL)
    assert any(TITLE in row for row in rows), "After you closed has no row under the phone dial"
    assert not any(f'aria-label="{TITLE}.' in w for w in _slices(phone)), "After you closed is still a phone wedge"


def test_after_close_keeps_its_desktop_wedge(chapter_three):
    _, desktop = _split(chapter_three)
    assert any(f'aria-label="{TITLE}.' in w for w in _slices(desktop))
    assert "scope__list" not in desktop
