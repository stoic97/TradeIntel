"""/sample: one prepared report of an invented trader, read-only, open to anyone.

No account, no file, nothing stored per visitor. The record is the demo tradebook, read
once through the ordinary pipeline into one account kept for it, and served to everyone.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from services.production.api import routes_sample
from services.production.api import scope_map as SM
from services.production.api.app import create_app
from services.production.db import models as m
from services.production.db.session import make_session
from tests.unit.api.test_read_again import send, words
from tests.unit.api.test_upload import CSRF, client, engine, sign_up  # noqa: F401

BAR = "Sample trader, invented. These aren't your trades."
PAGES = ("/sample", *(f"/sample/chapter/{c.number}" for c in SM.CHAPTERS),
         *(f"/sample/fact/{key}" for key in SM.FACTS))


def visitor() -> TestClient:
    return TestClient(create_app())


def rows(engine) -> dict[str, int]:  # noqa: F811
    with make_session(engine) as sess:
        return {t.name: sess.scalar(select(func.count()).select_from(t))
                for t in m.Base.metadata.sorted_tables}


def see_all(page: str) -> list[str]:
    return re.findall(r'href="(/sample/fact/[\w-]+/trades)"', page)


def test_anyone_can_open_it_with_no_account(engine):  # noqa: F811
    response = visitor().get("/sample", follow_redirects=False)
    assert response.status_code == 200
    assert "−₹" in words(response.text)


def test_every_page_of_it_opens(engine):  # noqa: F811
    v = visitor()
    lists = set()
    for path in PAGES:
        response = v.get(path, follow_redirects=False)
        assert response.status_code == 200, path
        lists.update(see_all(response.text))
    assert lists, "no fact links to its full list of trades"
    for path in sorted(lists):
        assert v.get(path, follow_redirects=False).status_code == 200, path


def test_it_says_on_the_page_that_the_trader_is_invented(engine):  # noqa: F811
    v = visitor()
    for path in PAGES:
        page = v.get(path).text
        main = page[page.index("<main"):]
        assert BAR in words(main[:main.index("</main>")]), path
        assert 'href="/"' in page and "Run this on my trades" in page, path


def test_it_never_sends_a_visitor_into_the_signed_in_report(engine):  # noqa: F811
    v = visitor()
    for path in PAGES:
        assert 'href="/mirror' not in v.get(path).text, path


def test_its_forms_are_off_on_the_server(engine):  # noqa: F811
    v = visitor()
    for path in PAGES:
        assert 'method="post"' not in v.get(path).text.lower(), path
    assert v.post("/sample/chapter/1/feedback", data={"answer": "accurate"}).status_code in (404, 405)


def test_it_carries_no_reading_beacon(engine):  # noqa: F811
    v = visitor()
    for path in PAGES:
        assert "dwell.js" not in v.get(path).text, path


def test_the_record_is_read_once_and_a_visit_stores_nothing(engine):  # noqa: F811
    visitor().get("/sample")
    after_first = rows(engine)
    for v in (visitor(), visitor()):
        for path in PAGES:
            v.get(path)
    assert rows(engine) == after_first
    with make_session(engine) as sess:
        assert sess.scalar(select(func.count()).select_from(m.Trader)
                           .where(m.Trader.login_id == routes_sample.LOGIN_ID)) == 1


def test_a_signed_in_trader_sees_the_sample_not_his_own(client, engine):  # noqa: F811
    send(client)  # his own synthetic file: his option trades come to -100
    mine = words(client.get("/mirror").text)
    assert "₹100" in mine
    before = rows(engine)
    client.get("/sample")
    before = rows(engine)  # the sample's one-time read is not his
    for path in PAGES:
        page = words(client.get(path).text)
        assert BAR in page, path
    assert rows(engine) == before
    assert words(client.get("/mirror").text) == mine


def test_his_own_report_never_shows_the_sample_bar(client):  # noqa: F811
    send(client)
    assert BAR not in words(client.get("/mirror").text)


def test_the_sample_account_cannot_be_signed_into(engine):  # noqa: F811
    v = visitor()
    v.get("/sample")
    csrf = CSRF.search(v.get("/login").text).group(1)
    response = v.post("/login", data={"login_id": routes_sample.LOGIN_ID, "password": "a-long-enough-password",
                                      "csrf_token": csrf}, follow_redirects=False)
    assert response.status_code != 303
    with make_session(engine) as sess:
        sample = sess.scalars(select(m.Trader).where(m.Trader.login_id == routes_sample.LOGIN_ID)).one()
        assert sample.development_data  # never counted as a reader on /admin


def test_no_one_can_sign_up_as_the_sample(engine):  # noqa: F811
    v = visitor()
    csrf = CSRF.search(v.get("/signup").text).group(1)
    v.post("/signup", data={"login_id": routes_sample.LOGIN_ID, "display_name": "x",
                            "password": "a-long-enough-password", "csrf_token": csrf})
    v.get("/sample")
    with make_session(engine) as sess:
        held = sess.scalars(select(m.Trader).where(m.Trader.login_id == routes_sample.LOGIN_ID)).all()
    assert [t.development_data for t in held] == [True]


def test_the_door_offers_it_before_any_account(engine):  # noqa: F811
    page = visitor().get("/").text
    assert 'href="/sample"' in page
    assert "See a sample report, no account needed" in words(page)
