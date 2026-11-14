"""Opening a chapter marks it read on Scope home, for that trader alone [TICKET-823]."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import select

from services.production.accounts import auth
from services.production.api.app import create_app
from services.production.db import models as m
from services.production.db.session import make_session

CSRF = re.compile(r'name="csrf_token"\s+value="([^"]+)"')


def rows(engine) -> list[m.DwellEvent]:
    with make_session(engine) as sess:
        return list(sess.scalars(select(m.DwellEvent).where(m.DwellEvent.surface == "scope_chapter")))


def test_a_first_visit_starts_at_chapter_1(client):
    body = client.get("/mirror").text
    assert ">Continue: Your worst trading days<" in body  # TICKET-903: Continue names the page
    assert "home__chapter--read" not in body


def test_opening_a_chapter_marks_it_read(client):
    client.get("/mirror/chapter/1")
    body = client.get("/mirror").text
    assert ">Continue: Your worst trading days<" in body  # TICKET-903: opening a chapter reads no page
    assert body.count("home__chapter--read") == 1
    assert 'class="scope__opened"' in body


def test_a_chapter_that_does_not_exist_marks_nothing(client, engine):
    assert client.get("/mirror/chapter/9").status_code == 404
    assert rows(engine) == []


def test_opening_it_twice_is_one_row(client, engine):
    client.get("/mirror/chapter/2")
    client.get("/mirror/chapter/2")
    assert len(rows(engine)) == 1


def test_the_key_carries_no_figures(client, engine):
    """The events table never holds a digit in a key (routes_events), so neither does this."""
    client.get("/mirror/chapter/3")
    assert not any(ch.isdigit() for ch in rows(engine)[0].key)


def test_one_traders_reading_does_not_mark_anothers(client, engine):
    client.get("/mirror/chapter/1")
    with make_session(engine) as sess:
        sess.add(m.Trader(display_name="Other", login_id="other",
                          password_hash=auth.hash_password("a-long-enough-password"),
                          created_at=datetime.now(UTC), development_data=True))
        sess.commit()
    other = TestClient(create_app())
    csrf = CSRF.search(other.get("/login").text).group(1)
    other.post("/login", data={"login_id": "other", "password": "a-long-enough-password", "csrf_token": csrf},
               follow_redirects=False)
    assert "home__chapter--read" not in other.get("/mirror").text
