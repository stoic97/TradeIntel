"""Deleting your account from the account page.

The consent screen promises deletion, so it has to be a button a trader can press,
and pressing it has to actually empty every location on the data-flow map. The
service is tested on its own; this is the path a person takes.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from services.production.accounts import deletion
from services.production.accounts.file_store import FileStore
from services.production.api.app import create_app
from services.production.db import models as m
from services.production.db.session import make_engine, make_session, run_migrations
from services.shared.schemas import scope_v1 as s

CSRF = re.compile(r'name="csrf_token"\s+value="([^"]+)"')
PASSWORD = "a-long-enough-password"


@pytest.fixture()
def engine():
    import os
    e = make_engine(os.environ["SCOPE_DB"])
    run_migrations(e)
    return e


@pytest.fixture()
def store():
    import os
    from pathlib import Path
    return FileStore(Path(os.environ["SCOPE_FILES"]), os.environ["SCOPE_FILE_KEY"])


@pytest.fixture()
def client(engine, store):
    from services.production.accounts import auth
    with make_session(engine) as sess:
        trader = m.Trader(display_name="R", login_id="rikk",
                          password_hash=auth.hash_password(PASSWORD),
                          created_at=datetime.now(UTC), development_data=True)
        sess.add(trader)
        sess.flush()
        stored = store.put(b"his export\n")
        sess.add(m.RawFile(trader_id=trader.id, sha256=stored.sha256,
                           original_name="t.csv", size=stored.size,
                           stored_path=str(stored.path),
                           uploaded_at=datetime.now(UTC)))
        sess.add(m.ConsentEvent(trader_id=trader.id,
                                purpose=s.ConsentPurpose.DIAGNOSIS, scope="v1",
                                terms_version="0-draft", granted=True,
                                at=datetime.now(UTC), method="web",
                                wording_shown="x" * 100))
        sess.commit()
    c = TestClient(create_app())
    csrf = CSRF.search(c.get("/login").text).group(1)
    c.post("/login", data={"login_id": "rikk", "password": PASSWORD,
                           "csrf_token": csrf}, follow_redirects=False)
    return c


def test_the_page_says_what_goes_and_what_cannot_be_undone(client):
    # Collapsed, because the template wraps these sentences across lines and a
    # raw substring check would be testing where the line breaks fall.
    body = " ".join(client.get("/account/delete").text.lower().split())
    assert "cannot be undone" in body
    assert "informed decisions we have already made about the engine" in body
    assert "30 days" in body


def test_nothing_happens_without_the_box(client, engine):
    response = client.post("/account/delete",
                           data={"csrf_token": CSRF.search(
                               client.get("/account/delete").text).group(1)})
    assert response.status_code == 400
    with make_session(engine) as sess:
        assert sess.scalars(select(m.Trader)).all() != []


def test_nothing_happens_without_the_token(client, engine):
    response = client.post("/account/delete",
                           data={"understood": "yes", "csrf_token": "forged"})
    assert response.status_code == 403
    with make_session(engine) as sess:
        assert sess.scalars(select(m.Trader)).all() != []


def test_pressing_it_empties_every_location(client, engine, store):
    with make_session(engine) as sess:
        trader_id = sess.scalars(select(m.Trader.id)).one()
        digest = sess.scalars(select(m.RawFile.sha256)).one()
    assert store.exists(digest)

    csrf = CSRF.search(client.get("/account/delete").text).group(1)
    response = client.post("/account/delete",
                           data={"understood": "yes", "csrf_token": csrf})
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
    assert anonymous.get("/account/delete",
                         follow_redirects=False).status_code in (302, 303)
