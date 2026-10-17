"""Invite, password, session, CSRF (design section 1, ruling Q3-C).

The door is an invite code; the trader gets a login id and a password from the
founder directly. No email is stored and none is sent, which keeps the data-flow map
to one company.

What these tests fix is not the happy path -- it is the ways an auth layer usually
leaks: a code that works twice, a login message that tells an attacker which half
was wrong, a session that survives logout, a form that accepts a cross-site post, a
cookie readable by script.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from services.production.api.app import create_app
from services.production.db import models as m
from services.production.db.session import make_engine, make_session, run_migrations

CSRF = re.compile(r'name="csrf_token"\s+value="([^"]+)"')


@pytest.fixture()
def app_env(tmp_path, monkeypatch):
    db_url = f"sqlite:///{tmp_path / 'id.db'}"
    monkeypatch.setenv("SCOPE_DB", db_url)
    monkeypatch.setenv("SCOPE_FILES", str(tmp_path / "files"))
    monkeypatch.setenv("SCOPE_SECRET_KEY", "test-secret-key-at-least-32-chars-long")
    engine = make_engine(db_url)
    run_migrations(engine)
    return db_url, engine


@pytest.fixture()
def client(app_env):
    return TestClient(create_app())


def make_invite(engine, code: str = "INVITE-1") -> str:
    from datetime import UTC, datetime
    with make_session(engine) as sess:
        sess.add(m.InviteCode(code=code, created_at=datetime.now(UTC)))
        sess.commit()
    return code


def token(client: TestClient, path: str) -> str:
    page = client.get(path)
    found = CSRF.search(page.text)
    assert found, f"no csrf token on {path}"
    return found.group(1)


def redeem(client, engine, code="INVITE-1", login_id="rikk", password="a-long-enough-password"):
    make_invite(engine, code)
    csrf = token(client, f"/invite/{code}")
    return client.post(
        f"/invite/{code}",
        data={"login_id": login_id, "display_name": "Rikk", "password": password,
              "csrf_token": csrf},
        follow_redirects=False,
    )


def test_an_unknown_code_does_not_offer_an_account(client):
    assert client.get("/invite/NOPE").status_code == 404


def test_redeeming_creates_the_trader_and_marks_the_code(client, app_env):
    _, engine = app_env
    response = redeem(client, engine)
    assert response.status_code in (302, 303)
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader)).one()
        assert trader.login_id == "rikk"
        code = sess.scalars(select(m.InviteCode)).one()
        assert code.redeemed_by == trader.id
        assert code.redeemed_at is not None


def test_a_code_cannot_create_two_accounts(client, app_env):
    _, engine = app_env
    redeem(client, engine)
    second = client.get("/invite/INVITE-1")
    assert second.status_code == 404
    with make_session(engine) as sess:
        assert len(sess.scalars(select(m.Trader)).all()) == 1


def test_the_password_is_stored_as_an_argon2_hash(client, app_env):
    _, engine = app_env
    redeem(client, engine, password="correct-horse-battery")
    with make_session(engine) as sess:
        stored = sess.scalars(select(m.Trader)).one().password_hash
    assert stored.startswith("$argon2id$")
    assert "correct-horse-battery" not in stored


def test_a_short_password_is_refused_plainly(client, app_env):
    _, engine = app_env
    make_invite(engine, "SHORT")
    csrf = token(client, "/invite/SHORT")
    response = client.post("/invite/SHORT", data={
        "login_id": "x", "display_name": "X", "password": "abc", "csrf_token": csrf})
    assert response.status_code == 400
    assert "12" in response.text


def test_login_succeeds_and_the_session_persists(client, app_env):
    _, engine = app_env
    redeem(client, engine)
    csrf = token(client, "/login")
    response = client.post("/login", data={
        "login_id": "rikk", "password": "a-long-enough-password", "csrf_token": csrf},
        follow_redirects=False)
    assert response.status_code in (302, 303)
    assert client.get("/account").status_code == 200


def test_a_wrong_password_does_not_say_which_half_was_wrong(client, app_env):
    """The two failure modes must be indistinguishable to the person posting.

    Checking for the absence of the word "password" would be the wrong test: the
    message legitimately says "login id and password do not match", which is good
    wording. The property that matters is that a wrong password and an unknown login
    id produce the same page, so an attacker learns nothing about which half to keep
    trying. Compared with the CSRF token removed, since it differs per request.
    """
    _, engine = app_env
    redeem(client, engine)

    csrf = token(client, "/login")
    wrong_password = client.post("/login", data={
        "login_id": "rikk", "password": "wrong-but-long-enough", "csrf_token": csrf})

    csrf2 = token(client, "/login")
    unknown_user = client.post("/login", data={
        "login_id": "nobody-at-all", "password": "wrong-but-long-enough",
        "csrf_token": csrf2})

    assert wrong_password.status_code == unknown_user.status_code == 400
    assert CSRF.sub("", wrong_password.text) == CSRF.sub("", unknown_user.text)
    assert client.get("/account", follow_redirects=False).status_code in (302, 303)


def test_an_unknown_login_id_gives_the_same_answer(client, app_env):
    _, engine = app_env
    redeem(client, engine)
    csrf = token(client, "/login")
    unknown = client.post("/login", data={
        "login_id": "nobody", "password": "a-long-enough-password", "csrf_token": csrf})
    csrf2 = token(client, "/login")
    wrong = client.post("/login", data={
        "login_id": "rikk", "password": "also-wrong-but-long", "csrf_token": csrf2})
    assert unknown.status_code == wrong.status_code == 400


def test_a_protected_page_redirects_when_signed_out(client):
    response = client.get("/account", follow_redirects=False)
    assert response.status_code in (302, 303)
    assert "/login" in response.headers["location"]


def test_logout_ends_the_session(client, app_env):
    _, engine = app_env
    redeem(client, engine)
    csrf = token(client, "/login")
    client.post("/login", data={"login_id": "rikk",
                                "password": "a-long-enough-password",
                                "csrf_token": csrf})
    assert client.get("/account").status_code == 200
    csrf_out = token(client, "/account")
    client.post("/logout", data={"csrf_token": csrf_out})
    assert client.get("/account", follow_redirects=False).status_code in (302, 303)


def test_a_post_without_a_csrf_token_is_rejected(client, app_env):
    _, engine = app_env
    redeem(client, engine)
    response = client.post("/login", data={
        "login_id": "rikk", "password": "a-long-enough-password"})
    assert response.status_code == 403


def test_a_forged_csrf_token_is_rejected(client, app_env):
    _, engine = app_env
    redeem(client, engine)
    response = client.post("/login", data={
        "login_id": "rikk", "password": "a-long-enough-password",
        "csrf_token": "not-a-real-token"})
    assert response.status_code == 403


def test_the_session_cookie_is_httponly_and_samesite(client, app_env):
    _, engine = app_env
    redeem(client, engine)
    csrf = token(client, "/login")
    response = client.post("/login", data={
        "login_id": "rikk", "password": "a-long-enough-password", "csrf_token": csrf},
        follow_redirects=False)
    cookie = response.headers.get("set-cookie", "")
    assert "httponly" in cookie.lower()
    assert "samesite=lax" in cookie.lower()
