"""TICKET-1108: an admin signed in more than 8 hours ago signs in again.

Gate: 1. past 8 hours, /admin (and /admin/traders/..., /admin/fyers/...) sends a signed-in admin
to /login, and after signing in he lands back on the admin page; an expired admin is never a 404.
2. A trader's session life is unchanged (the 30-day cookie). 3. A frozen clock: 7h59 opens, 8h01
does not. 4. /admin stays 404 for anyone not on ADMIN_LOGIN_IDS, signed in or not, at any age.

The clock is ``auth.clock``; each test freezes it. Everyone signs in through the real /login.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from itsdangerous import URLSafeSerializer

from services.production.accounts import auth
from services.production.db import models as m
from services.production.db.session import make_session
from tests.conftest import TEST_SECRET_KEY
from tests.helpers.admin_page import ADMIN, admin_page_app

PASSWORD = "a-long-enough-password"
CSRF = re.compile(r'name="csrf_token"\s+value="([^"]+)"')
T0 = 1_800_000_000
H = 3600
MIN = 60
AFTER_7H59 = 7 * H + 59 * MIN
AFTER_8H01 = 8 * H + 1 * MIN


@pytest.fixture()
def app(monkeypatch):
    return admin_page_app(monkeypatch)


@pytest.fixture()
def clock(monkeypatch):
    now = [T0]
    monkeypatch.setattr(auth, "clock", lambda: now[0], raising=False)
    return now


def add_account(app, login_id: str) -> int:
    with make_session(app.state.engine) as sess:
        trader = m.Trader(display_name=login_id, login_id=login_id,
                          password_hash=auth.hash_password(PASSWORD),
                          created_at=datetime(2026, 3, 2, tzinfo=UTC))
        sess.add(trader)
        sess.commit()
        return trader.id


def sign_in(client: TestClient, login_id: str, next_path: str | None = None):
    form = client.get("/login")
    csrf = CSRF.search(form.text).group(1)
    data = {"login_id": login_id, "password": PASSWORD, "csrf_token": csrf}
    if next_path is not None:
        data["next"] = next_path
    return client.post("/login", data=data)


def signed_in_admin(app, clock) -> tuple[TestClient, int]:
    admin_id = add_account(app, ADMIN)
    client = TestClient(app, follow_redirects=False)
    assert sign_in(client, ADMIN).status_code == 303
    return client, admin_id


ADMIN_PAGES = ["/admin", "/admin/traders/{id}"]


def test_admin_at_7h59_opens_admin(app, clock):
    client, admin_id = signed_in_admin(app, clock)
    clock[0] = T0 + AFTER_7H59
    assert client.get("/admin").status_code == 200
    assert client.get(f"/admin/traders/{admin_id}").status_code == 200


@pytest.mark.parametrize("path", ADMIN_PAGES)
def test_admin_at_8h01_signs_in_again_not_404(app, clock, path):
    client, admin_id = signed_in_admin(app, clock)
    clock[0] = T0 + AFTER_8H01
    path = path.format(id=admin_id)
    response = client.get(path)
    assert response.status_code == 303, "an expired admin is sent to sign in, never a 404"
    assert response.headers["location"] == f"/login?next={path}"


def test_admin_at_8h01_fyers_routes_sign_in_again(app, clock):
    client, _ = signed_in_admin(app, clock)
    clock[0] = T0 + AFTER_8H01
    callback = client.get("/admin/fyers/callback?auth_code=x&state=y")
    connect = client.post("/admin/fyers/connect", data={"csrf_token": "x"})
    paste = client.post("/admin/fyers/paste", data={"address": "x", "csrf_token": "x"})
    for response in (callback, connect, paste):
        assert response.status_code == 303
        assert response.headers["location"] == "/login?next=/admin"


def test_after_signing_in_again_he_lands_on_the_admin_page(app, clock):
    client, _ = signed_in_admin(app, clock)
    clock[0] = T0 + AFTER_8H01
    assert client.get("/admin").status_code == 303
    form = client.get("/login?next=/admin")
    assert 'name="next"' in form.text and 'value="/admin"' in form.text
    assert "Sign in again to open the admin page." in form.text
    again = sign_in(client, ADMIN, next_path="/admin")
    assert again.status_code == 303 and again.headers["location"] == "/admin"
    assert client.get("/admin").status_code == 200


@pytest.mark.parametrize("bad", ["//evil.example/admin", "https://evil.example/admin",
                                 "/adminx", "/account", "/\\evil.example", "admin"])
def test_next_is_only_ever_an_admin_path_on_this_site(app, clock, bad):
    add_account(app, ADMIN)
    client = TestClient(app, follow_redirects=False)
    response = sign_in(client, ADMIN, next_path=bad)
    assert response.status_code == 303
    assert response.headers["location"] != bad


def test_next_is_ignored_for_someone_not_an_admin(app, clock):
    add_account(app, "ordinary")
    client = TestClient(app, follow_redirects=False)
    assert sign_in(client, "ordinary", next_path="/admin").headers["location"] != "/admin"


@pytest.mark.parametrize("age", [1 * H, 9 * H])
def test_non_admin_is_404_on_every_admin_path_at_any_age(app, clock, age):
    add_account(app, ADMIN)
    other_id = add_account(app, "ordinary")
    client = TestClient(app, follow_redirects=False)
    assert sign_in(client, "ordinary").status_code == 303
    clock[0] = T0 + age
    for path in ("/admin", f"/admin/traders/{other_id}", "/admin/fyers/callback"):
        assert client.get(path).status_code == 404, path
    for path in ("/admin/fyers/connect", "/admin/fyers/paste"):
        assert client.post(path, data={"csrf_token": "x"}).status_code == 404, path


def test_signed_out_is_404_on_every_admin_path(app, clock):
    add_account(app, ADMIN)
    client = TestClient(app, follow_redirects=False)
    clock[0] = T0 + 9 * H
    for path in ("/admin", "/admin/traders/1", "/admin/fyers/callback"):
        assert client.get(path).status_code == 404, path


def test_a_trader_page_still_opens_at_8h01(app, clock):
    add_account(app, ADMIN)
    add_account(app, "ordinary")
    client = TestClient(app, follow_redirects=False)
    assert sign_in(client, "ordinary").status_code == 303
    clock[0] = T0 + AFTER_8H01
    assert client.get("/account").status_code == 200


def test_the_session_cookie_still_lives_30_days(app, clock):
    add_account(app, "ordinary")
    client = TestClient(app, follow_redirects=False)
    cookie = sign_in(client, "ordinary").headers["set-cookie"]
    assert "Max-Age=2592000" in cookie


def old_cookie(app, login_id: str) -> str:
    """A cookie sealed before sign-in time existed: no signed-in time in it."""
    with make_session(app.state.engine) as sess:
        trader = sess.query(m.Trader).filter_by(login_id=login_id).one()
        payload = {"t": trader.id, "c": "old-csrf",
                   "a": auth.account_mark(trader.password_hash, TEST_SECRET_KEY)}
    return URLSafeSerializer(TEST_SECRET_KEY, salt=auth.SESSION_SALT).dumps(payload)


def test_an_old_cookie_without_sign_in_time_makes_an_admin_sign_in_once(app, clock):
    add_account(app, ADMIN)
    client = TestClient(app, follow_redirects=False)
    client.cookies.set(auth.SESSION_COOKIE, old_cookie(app, ADMIN))
    response = client.get("/admin")
    assert response.status_code == 303 and response.headers["location"] == "/login?next=/admin"
    assert client.get("/account").status_code == 200, "as a trader he is not signed out"


def test_an_old_cookie_without_sign_in_time_keeps_a_trader_signed_in(app, clock):
    add_account(app, ADMIN)
    add_account(app, "ordinary")
    client = TestClient(app, follow_redirects=False)
    client.cookies.set(auth.SESSION_COOKIE, old_cookie(app, "ordinary"))
    assert client.get("/account").status_code == 200
    assert client.get("/admin").status_code == 404
