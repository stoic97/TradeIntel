"""Deleting your account from the account page.

The consent screen promises deletion, so it has to be a button a trader can press,
and pressing it has to actually empty every location on the data-flow map. The
service is tested on its own; this is the path a person takes.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from services.production.accounts import deletion
from services.production.api.app import create_app
from services.production.db import models as m
from services.production.db.session import make_session
from tests.helpers.deletion_page import (
    CSRF,
    deletion_page_client,
    deletion_page_engine,
    deletion_page_store,
)


@pytest.fixture()
def engine():
    return deletion_page_engine()


@pytest.fixture()
def store():
    return deletion_page_store()


@pytest.fixture()
def client(engine, store):
    return deletion_page_client(engine, store)


def test_the_page_says_what_goes_and_what_cannot_be_undone(client):
    # Collapsed, because the template wraps these sentences across lines and a
    # raw substring check would be testing where the line breaks fall.
    body = " ".join(client.get("/account/delete").text.lower().split())
    assert "cannot be undone" in body
    assert "informed decisions we have already made about the engine" in body
    assert "30 days" in body


def test_nothing_happens_without_the_box(client, engine):
    response = client.post(
        "/account/delete",
        data={"csrf_token": CSRF.search(client.get("/account/delete").text).group(1)},
    )
    assert response.status_code == 400
    with make_session(engine) as sess:
        assert sess.scalars(select(m.Trader)).all() != []


def test_nothing_happens_without_the_token(client, engine):
    response = client.post("/account/delete", data={"understood": "yes", "csrf_token": "forged"})
    assert response.status_code == 403
    with make_session(engine) as sess:
        assert sess.scalars(select(m.Trader)).all() != []


def test_pressing_it_empties_every_location(client, engine, store):
    with make_session(engine) as sess:
        trader_id = sess.scalars(select(m.Trader.id)).one()
        digest = sess.scalars(select(m.RawFile.sha256)).one()
    assert store.exists(digest)

    csrf = CSRF.search(client.get("/account/delete").text).group(1)
    response = client.post("/account/delete", data={"understood": "yes", "csrf_token": csrf})
    assert response.status_code == 200
    assert "deleted" in response.text.lower()

    with make_session(engine) as sess:
        assert deletion.nothing_remains(sess, store, trader_id) == []
        assert sess.scalars(select(m.DeletionRecord)).one().trader_id == trader_id
    assert not store.exists(digest), "the encrypted file is still on disk"


def test_he_is_signed_out_afterwards(client):
    csrf = CSRF.search(client.get("/account/delete").text).group(1)
    client.post("/account/delete", data={"understood": "yes", "csrf_token": csrf})
    assert client.get("/account", follow_redirects=False).status_code in (302, 303)


def test_it_needs_signing_in(engine):
    anonymous = TestClient(create_app())
    assert anonymous.get("/account/delete", follow_redirects=False).status_code in (302, 303)


def test_the_account_page_links_to_delete_everything(client):
    """[TICKET-802] The upload page promises deletion, and nothing led to this page."""
    assert (
        '<a class="settings-row" href="/account/delete"><span class="body">Delete everything</span>'
    ) in client.get("/account").text


def test_the_upload_page_says_where_to_delete_everything(client):
    """[TICKET-802] Amended gate: the promise line says where the control is."""
    page = client.get("/upload").text
    assert "You can delete everything at any time from your Account page." in page
    assert "You can delete it at any time." not in page
