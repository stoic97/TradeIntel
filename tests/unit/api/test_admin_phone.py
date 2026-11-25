"""TICKET-1023: /admin on a 390 px phone.

Checked in a browser at 390 px on made-up traders: every table already sits in its own sideways
scroller, the trader column and the header row stay in view, nothing outside a scroller runs off
the screen, and the way back and the way to sign out are both reachable. Nothing needed fixing, so
these tests are guards: they pin what makes that true, so a later change cannot undo it quietly.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.helpers.admin_page import add_trader, admin_client, admin_page_app, admin_page_engine

CSS = Path("services/production/api/static/css/app.css").read_text(encoding="utf-8")


@pytest.fixture()
def app(monkeypatch):
    return admin_page_app(monkeypatch)


@pytest.fixture()
def html(app):
    engine = admin_page_engine(app)
    add_trader(engine, "first", name="First Madeup")
    add_trader(engine, "second", name="Second Madeup")
    return admin_client(app, engine).get("/admin?columns=all").text


def _rule(selector: str) -> str:
    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    assert match, selector
    return match.group(1)


def test_every_table_on_the_page_scrolls_sideways_in_its_own_box(html):
    tables = len(re.findall(r"<table\b", html))
    boxed = len(re.findall(r'<div class="admin__scroll[^"]*">\s*<table\b', html))
    assert tables >= 2 and boxed == tables
    assert "overflow-x: auto" in _rule(".admin__scroll")


def test_the_trader_column_and_the_header_row_stay_in_view(html):
    assert re.search(r'<th class="admin__who">', html)
    assert len(re.findall(r'<td class="admin__who">', html)) >= 3  # the admin and two traders
    who = _rule(".admin__who")
    assert "position: sticky" in who and "left: 0" in who and "background" in who
    head = _rule(".admin__traders thead th")
    assert "position: sticky" in head and "top: 0" in head


def test_the_way_back_and_the_way_to_sign_out_are_on_the_page(html):
    assert re.search(r'<a [^>]*href="/"[^>]*>Home</a>', html)
    assert re.search(r'<a [^>]*href="/account"[^>]*>Account, to sign out</a>', html)


def test_the_page_itself_never_scrolls_sideways():
    assert "max-width: 100%" in _rule(".admin__scroll")
    assert "min-width: 0" in _rule(".screen.screen--admin > .screen__body.admin")
