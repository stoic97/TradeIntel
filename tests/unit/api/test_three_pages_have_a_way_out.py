"""TICKET-861: /upload, /budget and an old upload's page each have a link out, above the title."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from services.production.api.app import create_app
from services.production.db import models as m
from services.production.db.session import make_session
from services.production.journal import constants as k

CSRF = re.compile(r'name="csrf_token"\s+value="([^"]+)"')
LINK = '<a class="link link--back" href="/">‹ Home</a>'


def token(client, path: str) -> str:
    return CSRF.search(client.get(path).text).group(1)


@pytest.fixture()
def app():
    return create_app()


@pytest.fixture()
def client(app):
    client = TestClient(app, follow_redirects=False)
    client.post("/signup", data={"login_id": "visitor", "display_name": "Visitor",
                                 "password": "a-long-enough-password",
                                 "csrf_token": token(client, "/signup")})
    client.post("/consent", data={"diagnosis": "yes", "engine_testing": "yes",
                                  "csrf_token": token(client, "/consent")})
    client.post("/upload/demo", data={"csrf_token": token(client, "/upload")})
    return client


def paths(app) -> list[str]:
    with make_session(app.state.engine) as sess:
        return ["/upload", "/budget", f"/imports/{sess.scalars(select(m.Import.id)).first()}"]


def test_each_page_has_one_link_home_above_its_title(app, client):
    for path in paths(app):
        page = client.get(path).text
        assert page.count(LINK) == 1, path
        assert page.index(LINK) < page.index('class="title"'), path


def test_a_refused_upload_keeps_it(client):
    refused = client.post("/upload", data={"csrf_token": token(client, "/upload")},
                          files={"file": ("a.csv", b"x" * (k.MAX_UPLOAD_BYTES + 1), "text/csv")})
    assert refused.status_code == 400
    assert LINK in refused.text


def test_a_refused_number_keeps_it(client):
    refused = client.post("/budget", data={"csrf_token": token(client, "/budget"), "value": "no",
                                           "unit": "INR", "effective_from": "2024-01-01"})
    assert refused.status_code == 400
    assert LINK in refused.text


def test_other_pages_are_left_alone(client):
    for path in ("/account", "/journals", "/mirror"):
        assert LINK not in client.get(path).text, path
