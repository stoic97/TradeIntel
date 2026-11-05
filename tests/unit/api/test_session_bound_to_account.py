"""TICKET-849: a session belongs to one account, not to a number.

A trader id can be used again once its account has gone, so a session has to say more
than the id. Nothing here depends on how ids are handed out.
"""

from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient
from itsdangerous import URLSafeSerializer
from sqlalchemy import select, update

from services.production.accounts import auth
from services.production.accounts.file_store import generate_key
from services.production.api.app import create_app
from services.production.db import models as m
from services.production.db.session import make_engine, make_session, run_migrations

CSRF = re.compile(r'name="csrf_token"\s+value="([^"]+)"')
PASSWORD = "a-long-enough-password"
KEY = "test-secret-key-at-least-32-chars-long"


@pytest.fixture()
def engine(tmp_path, monkeypatch):
    db_url = f"sqlite:///{tmp_path / 'session.db'}"
    monkeypatch.setenv("SCOPE_DB", db_url)
    monkeypatch.setenv("SCOPE_FILES", str(tmp_path / "files"))
    monkeypatch.setenv("SCOPE_SECRET_KEY", KEY)
    monkeypatch.setenv("SCOPE_FILE_KEY", generate_key())
    built = make_engine(db_url)
    run_migrations(built)
    return built


def sign_up(login_id: str) -> TestClient:
    client = TestClient(create_app())
    csrf = CSRF.search(client.get("/signup").text).group(1)
    client.post("/signup", data={"login_id": login_id, "display_name": login_id,
                                 "password": PASSWORD, "csrf_token": csrf},
                follow_redirects=False)
    return client


def delete_account(client: TestClient) -> None:
    csrf = CSRF.search(client.get("/account/delete").text).group(1)
    assert client.post("/account/delete", data={"understood": "yes", "csrf_token": csrf},
                       follow_redirects=False).status_code == 200


def holding(cookie: str) -> TestClient:
    client = TestClient(create_app())
    client.cookies.set(auth.SESSION_COOKIE, cookie)
    return client


def test_a_session_works_for_its_own_account(engine):
    client = sign_up("own")
    assert "Signed in as own." in " ".join(client.get("/account").text.split())


def test_an_old_session_does_not_open_a_later_account_on_the_same_id(engine):
    first = sign_up("first")
    old_cookie = first.cookies.get(auth.SESSION_COOKIE)
    delete_account(first)
    second = sign_up("second")
    with make_session(engine) as sess:
        assert sess.scalars(select(m.Trader.id)).all() == [1], "the id must really be the same"

    old = holding(old_cookie)
    response = old.get("/account", follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/login"
    assert "second" not in response.text
    assert "Signed in as second." in " ".join(second.get("/account").text.split())


def test_an_old_session_cannot_delete_a_later_account(engine):
    first = sign_up("first")
    old_cookie = first.cookies.get(auth.SESSION_COOKIE)
    old_page = CSRF.search(first.get("/account/delete").text).group(1)
    delete_account(first)
    sign_up("second")

    holding(old_cookie).post("/account/delete", data={"understood": "yes", "csrf_token": old_page},
                             follow_redirects=False)
    with make_session(engine) as sess:
        assert sess.scalars(select(m.Trader.login_id)).all() == ["second"]


def test_a_session_for_a_deleted_account_is_signed_out(engine):
    client = sign_up("gone")
    cookie = client.cookies.get(auth.SESSION_COOKIE)
    delete_account(client)
    assert holding(cookie).get("/account", follow_redirects=False).headers["location"] == "/login"


def test_a_new_password_ends_older_sessions(engine):
    client = sign_up("reset")
    with make_session(engine) as sess:
        sess.execute(update(m.Trader).values(password_hash=auth.hash_password("another-long-password")))
        sess.commit()
    assert client.get("/account", follow_redirects=False).headers["location"] == "/login"


def test_a_session_from_before_this_change_has_to_sign_in_again(engine):
    client = sign_up("earlier")
    with make_session(engine) as sess:
        trader_id = sess.scalars(select(m.Trader.id)).one()
    earlier = auth.seal_session(auth.Session(trader_id=trader_id, csrf_secret="x"), KEY)
    assert holding(earlier).get("/account", follow_redirects=False).headers["location"] == "/login"
    assert client.get("/account").status_code == 200


def test_signing_in_again_gives_a_working_session(engine):
    first = sign_up("again")
    first.cookies.clear()
    csrf = CSRF.search(first.get("/login").text).group(1)
    first.post("/login", data={"login_id": "again", "password": PASSWORD, "csrf_token": csrf},
               follow_redirects=False)
    assert first.get("/account").status_code == 200


def test_someone_holding_an_old_session_can_still_sign_in(engine):
    first = sign_up("returning")
    old_cookie = first.cookies.get(auth.SESSION_COOKIE)
    delete_account(first)
    sign_up("returning")
    client = holding(old_cookie)
    csrf = CSRF.search(client.get("/login").text).group(1)
    response = client.post("/login", data={"login_id": "returning", "password": PASSWORD,
                                           "csrf_token": csrf}, follow_redirects=False)
    assert response.status_code == 303
    assert "Signed in as returning." in " ".join(client.get("/account").text.split())


def test_the_cookie_carries_no_part_of_the_password_hash(engine):
    """A signed cookie can be read by whoever holds it, so what it carries is a mark."""
    client = sign_up("readable")
    with make_session(engine) as sess:
        stored = sess.scalars(select(m.Trader.password_hash)).one()
    carried = URLSafeSerializer(KEY, salt=auth.SESSION_SALT).loads(
        client.cookies.get(auth.SESSION_COOKIE))
    assert carried["a"] == auth.account_mark(stored, KEY)
    assert stored not in json.dumps(carried) and "argon" not in json.dumps(carried)


def test_two_accounts_on_one_password_carry_different_marks(engine):
    one, two = auth.hash_password(PASSWORD), auth.hash_password(PASSWORD)
    assert auth.account_mark(one, KEY) != auth.account_mark(two, KEY)


def test_the_mark_depends_on_the_servers_key(engine):
    stored = auth.hash_password(PASSWORD)
    assert auth.account_mark(stored, KEY) != auth.account_mark(stored, KEY + "x")
