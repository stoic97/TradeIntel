"""TICKET-860: every signed-in page has a way back to Home.

T-001 (6 Nov, round 2, N15): nothing linked to Home, so a trader deep in a fact page had
the browser's back button or the address bar. Home is ``/``. On every signed-in page the
lockup links there, and the page's navigation has a Home entry: the bottom nav's first
tab where a page has the nav, and a slim bar above the page where it has none (a fact
page, the upload, the import review, consent...).

This adds a way out and no way in (handoff 4, two gestures only): nothing here links
into the Scope, and the rail, the path, Previous/Next and the dial are untouched.

The walk is every GET route the app has, not a list somebody keeps: a route added
later without a way home fails here, and so does one whose path parameters this file
does not know how to fill.
"""

from __future__ import annotations

import re
from itertools import product

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import select

from services.production import demo
from services.production.api import scope_map as S
from services.production.api.app import create_app
from services.production.db import models as m
from services.production.db.session import make_session
from tests.unit.api.test_admin_page import every_route
from tests.unit.api.test_upload import sign_up

CSRF = re.compile(r'name="csrf_token"\s+value="([^"]+)"')
LOCKUP_HOME = re.compile(r'<a class="lockup-link[^"]*" href="/"[^>]*>\s*<span class="lockup">')
HOME_ENTRY = re.compile(r'<a class="(?:bottom-nav__item|home-bar__home)" href="/"[^>]*>Home</a>')

SIGNED_OUT = {"/login", "/signup", "/health"}
"""Pages for someone not signed in. The door ("/") is walked signed out below."""
NOT_A_TRADER_PAGE = {"/admin", "/admin/", "/admin/traders/{trader_id}", "/admin/traders/{trader_id}/"}
"""The operator's page: a trader gets the 404 (test_admin_page), and nothing links there."""


@pytest.fixture()
def engine():
    import os

    from services.production.db.session import make_engine, run_migrations

    e = make_engine(os.environ["SCOPE_DB"])
    run_migrations(e)
    return e


@pytest.fixture()
def client(engine):
    """A signed-in trader with a whole record: the synthetic demo file (README rule 1)."""
    c = sign_up(TestClient(create_app()), engine, "H-1", "homeward")
    token = CSRF.search(c.get("/upload").text).group(1)
    assert c.post("/upload/demo", data={"csrf_token": token},
                  follow_redirects=False).status_code == 303
    return c


def params(engine) -> dict[str, list[str]]:
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader).where(m.Trader.login_id == "homeward")).one()
        imp = demo.demo_import(sess, trader)
        journal = sess.scalars(select(m.Journal.id).where(m.Journal.import_id == imp.id)
                               .order_by(m.Journal.id)).first()
        from services.production.mirror import loader
        day = loader.load_for(sess, trader)[0][0].trading_day
    return {
        "import_id": [str(imp.id)],
        "journal_id": [str(journal)],
        "n": [str(c.number) for c in S.CHAPTERS],
        "key": list(S.FACTS),
        "iso": [str(day)],
    }


def signed_in_urls(engine) -> list[str]:
    fill = params(engine)
    urls = []
    for route in every_route(create_app().routes):
        if not isinstance(route, APIRoute) or "GET" not in route.methods:
            continue
        if route.path in SIGNED_OUT | NOT_A_TRADER_PAGE:
            continue
        names = re.findall(r"\{(\w+)\}", route.path)
        missing = [n for n in names if n not in fill]
        assert not missing, f"{route.path}: say here how to fill {missing}"
        for values in product(*(fill[n] for n in names)):
            url = route.path
            for name, value in zip(names, values, strict=True):
                url = url.replace("{" + name + "}", value)
            urls.append(url)
    return urls


def assert_a_way_home(html: str, where: str) -> None:
    assert LOCKUP_HOME.search(html), f"{where}: the lockup does not link to Home"
    assert HOME_ENTRY.search(html), f"{where}: no Home entry in its navigation"


def test_the_walk_reaches_the_report_and_the_pages_around_it(engine, client):
    urls = signed_in_urls(engine)
    for expected in ("/", "/mirror", "/mirror/chapter/1", "/mirror/fact/worst-days",
                     "/journals", "/account", "/upload", "/consent"):
        assert expected in urls, expected
    assert any(u.startswith("/journals/") and u[10:].isdigit() for u in urls)
    assert any(u.endswith("/trades") for u in urls)


def test_every_signed_in_page_links_to_home(engine, client):
    for url in signed_in_urls(engine):
        r = client.get(url)
        assert r.status_code in (200, 404), (url, r.status_code)
        if "text/html" in r.headers.get("content-type", ""):
            assert_a_way_home(r.text, f"{url} -> {r.url.path}")


def test_the_pages_with_no_other_way_out_each_have_a_way_home(engine, client):
    """Named, because these three had no link out at all (T-001, round 2)."""
    with make_session(engine) as sess:
        imp = sess.scalars(select(m.Import.id)).first()
    for url in ("/upload", "/budget", f"/imports/{imp}"):
        r = client.get(url, follow_redirects=False)
        assert r.status_code == 200, url
        assert_a_way_home(r.text, url)


def test_a_trader_before_consent_has_a_way_home_too(engine):
    c = sign_up(TestClient(create_app()), engine, "H-2", "notyet", consent=False)
    for url in ("/consent", "/upload", "/account"):
        assert_a_way_home(c.get(url).text, url)


def test_the_bottom_nav_leads_with_home_and_keeps_its_three_tabs(client):
    tabs = re.findall(r'<a class="bottom-nav__item" href="([^"]+)"[^>]*>([^<]+)</a>',
                      client.get("/journals").text)
    assert tabs == [("/", "Home"), ("/mirror", "Scope"), ("/journals", "Journal"),
                    ("/account", "Account")]


def test_signed_out_the_door_is_unchanged(engine):
    """The door's mark goes back to plusev.in (test_home), and there is no Home to go to."""
    door = TestClient(create_app()).get("/").text
    assert '<a href="https://plusev.in" aria-label="PlusEV">' in door
    assert "home-bar" not in door and "lockup-link" not in door


def test_home_adds_no_way_into_the_scope():
    """Two gestures only (handoff 4): the Home bar and the lockup go to / and nowhere else."""
    from pathlib import Path

    components = Path("services/production/api/templates/_components.html").read_text()
    layout = Path("services/production/api/templates/layout.html").read_text()
    macro = components.split("{% macro home_lockup", 1)[1].split("{%- endmacro %}", 1)[0]
    bar = layout.split('<nav class="home-bar"', 1)[1].split("</nav>", 1)[0]
    assert set(re.findall(r'href="([^"]+)"', macro + bar)) == {"/"}


def test_an_address_with_nothing_at_it_still_has_a_way_home(client):
    """A dead address is the last place to leave a trader without one: the app's Not found
    page, and the Scope's own not-found answers (an unknown chapter, an unknown fact, a fact
    with no list of trades), all say Not found and carry the way back."""
    for url in ("/no-such-page", "/mirror/chapter/9", "/mirror/fact/nope",
                "/mirror/fact/unread/trades"):
        r = client.get(url)
        assert r.status_code == 404, url
        assert "Not found" in r.text, url
        assert_a_way_home(r.text, url)
