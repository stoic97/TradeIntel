"""TICKET-841: anyone who opens Scope can sign up. There is no invite any more.

Consent and eligibility stay, and they are what a new account still has to pass. These
tests fix the door being open, what stays shut behind it, and that every account made
through the old door still signs in.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select

from services.production.accounts import auth
from services.production.api import cli
from services.production.api.app import create_app
from services.production.db import models as m
from services.production.db.session import make_engine, make_session, run_migrations

CSRF = re.compile(r'name="csrf_token"\s+value="([^"]+)"')
PASSWORD = "a-long-enough-password"


@pytest.fixture()
def app_env(tmp_path, monkeypatch):
    db_url = f"sqlite:///{tmp_path / 'open.db'}"
    monkeypatch.setenv("SCOPE_DB", db_url)
    monkeypatch.setenv("SCOPE_FILES", str(tmp_path / "files"))
    monkeypatch.setenv("SCOPE_SECRET_KEY", "test-secret-key-at-least-32-chars-long")
    engine = make_engine(db_url)
    run_migrations(engine)
    return db_url, engine


@pytest.fixture()
def client(app_env):
    return TestClient(create_app())


def sign_up(client, login_id="newcomer", password=PASSWORD, display_name="New Comer", **extra):
    csrf = CSRF.search(client.get("/signup").text).group(1)
    return client.post("/signup", data={"login_id": login_id, "display_name": display_name,
                                        "password": password, "csrf_token": csrf, **extra},
                       follow_redirects=False)


def traders(engine) -> list[str]:
    with make_session(engine) as sess:
        return list(sess.scalars(select(m.Trader.login_id)))


# ---------- The door is open ----------


def test_opening_the_site_with_no_invite_offers_sign_up_on_the_page(client):
    page = client.get("/")
    assert page.status_code == 200
    assert '<form method="post" action="/signup"' in page.text
    for name in ("display_name", "login_id", "password", "csrf_token"):
        assert f'name="{name}"' in page.text


def test_the_form_on_the_front_door_works_in_one_step(client, app_env):
    _, engine = app_env
    csrf = CSRF.search(client.get("/").text).group(1)
    response = client.post("/signup", data={"login_id": "door", "display_name": "Door",
                                            "password": PASSWORD, "csrf_token": csrf},
                           follow_redirects=False)
    assert response.status_code == 303
    assert traders(engine) == ["door"]


@pytest.mark.parametrize("path", ["/", "/signup", "/login"])
def test_no_page_on_the_way_in_speaks_of_invitations_or_waiting(client, path):
    said = client.get(path).text.lower()
    for word in ("invit", "waitlist", "request access", "access code"):
        assert word not in said, f"{path} says {word!r}"


def test_a_person_with_an_account_can_still_find_sign_in(client):
    for path in ("/", "/signup"):
        assert 'href="/login"' in client.get(path).text


def test_a_person_without_an_account_can_find_sign_up_from_sign_in(client):
    assert 'href="/signup"' in client.get("/login").text


def test_the_front_door_keeps_its_way_back_to_plusev(client):
    assert 'href="https://plusev.in"' in client.get("/").text


# ---------- After sign-up ----------


def test_signing_up_signs_you_in_and_goes_to_upload(client):
    response = sign_up(client)
    assert response.status_code == 303 and response.headers["location"] == "/upload"
    assert auth.SESSION_COOKIE in response.headers.get("set-cookie", "")
    assert client.get("/account").status_code == 200


def test_consent_still_stands_between_a_new_account_and_upload(client, app_env):
    _, engine = app_env
    sign_up(client)
    response = client.get("/upload", follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/consent"
    with make_session(engine) as sess:
        assert sess.scalars(select(m.ConsentEvent)).all() == []


def test_a_new_account_is_a_real_account(client, app_env):
    _, engine = app_env
    sign_up(client)
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader)).one()
        assert trader.development_data is False
        assert trader.password_hash.startswith("$argon2id$")
        assert PASSWORD not in trader.password_hash


def test_a_new_account_can_sign_out_and_back_in(client):
    sign_up(client)
    client.cookies.clear()
    csrf = CSRF.search(client.get("/login").text).group(1)
    response = client.post("/login", data={"login_id": "newcomer", "password": PASSWORD,
                                           "csrf_token": csrf}, follow_redirects=False)
    assert response.status_code == 303


def test_someone_already_signed_in_is_not_offered_a_second_account(client):
    sign_up(client)
    for path in ("/signup",):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 303 and response.headers["location"] == "/upload"


def test_the_record_of_a_sign_up_does_not_keep_the_login_id(client, app_env):
    """Admin actions outlive a deletion, and a login id is his."""
    _, engine = app_env
    sign_up(client)
    with make_session(engine) as sess:
        row = sess.scalars(select(m.AdminAction).where(m.AdminAction.action == "sign_up")).one()
        assert row.target is None and "newcomer" not in row.actor


# ---------- What sign-up refuses ----------


def test_a_login_id_that_is_taken_is_refused(client, app_env):
    _, engine = app_env
    sign_up(client)
    client.cookies.clear()
    response = sign_up(client, display_name="Someone Else")
    assert response.status_code == 400 and "That login id is taken." in response.text
    assert traders(engine) == ["newcomer"]


def test_a_short_password_is_refused_plainly(client, app_env):
    _, engine = app_env
    response = sign_up(client, password="abc")
    assert response.status_code == 400 and "12" in response.text
    assert traders(engine) == []


@pytest.mark.parametrize(("field", "value"), [
    ("login_id", "   "), ("display_name", "   "),
    ("login_id", "x" * 101), ("display_name", "x" * 201),
])
def test_a_name_that_is_blank_or_too_long_is_refused(client, app_env, field, value):
    _, engine = app_env
    response = sign_up(client, **{field: value})
    assert response.status_code == 400
    assert traders(engine) == []


def test_a_login_id_keeps_no_stray_spaces(client, app_env):
    _, engine = app_env
    sign_up(client, login_id="  spaced  ")
    assert traders(engine) == ["spaced"]


def test_a_post_with_no_csrf_token_is_refused(client, app_env):
    _, engine = app_env
    response = client.post("/signup", data={"login_id": "x", "display_name": "X",
                                            "password": PASSWORD})
    assert response.status_code == 403
    assert traders(engine) == []


def test_a_refused_form_does_not_write_the_password_back(client):
    response = sign_up(client, password="short-pass1")
    assert "short-pass1" not in response.text


# ---------- Removed, not hidden ----------


def test_the_old_invite_address_is_gone(client):
    assert client.get("/invite/ANY").status_code == 404
    assert client.post("/invite/ANY", data={}).status_code in (404, 405)


def test_the_invite_table_and_model_are_gone(app_env):
    _, engine = app_env
    assert "invite_code" not in inspect(engine).get_table_names()
    assert not hasattr(m, "InviteCode")


def test_the_admin_command_is_gone(capsys):
    with pytest.raises(SystemExit):
        cli.main(["invite", "--code", "X"])


def test_no_production_code_mentions_the_gate():
    pattern = re.compile(r"InviteCode|invite_code|/invite/|invite-only|invitation only|"
                         r"redeem_invite|cmd_invite", re.IGNORECASE)
    for path in [*Path("services/production").rglob("*.py"),
                 *Path("services/production").rglob("*.html"), Path("Makefile")]:
        found = pattern.search(path.read_text())
        assert found is None, f"{path} says {found.group(0)!r}"
    assert not Path("services/production/api/templates/invite.html").exists()


# ---------- Accounts made through the old door ----------


def test_an_account_made_through_an_invite_still_signs_in(tmp_path, monkeypatch):
    """Upgrade a database that holds a redeemed invite: the account and its sign-in stay."""
    db_url = f"sqlite:///{tmp_path / 'old.db'}"
    monkeypatch.setenv("SCOPE_DB", db_url)
    monkeypatch.setenv("SCOPE_FILES", str(tmp_path / "files"))
    monkeypatch.setenv("SCOPE_SECRET_KEY", "test-secret-key-at-least-32-chars-long")
    engine = make_engine(db_url)
    run_migrations(engine, "0007")
    now = datetime.now(UTC).isoformat()
    with engine.begin() as conn:
        conn.execute(sa.text(
            "insert into trader (id, display_name, login_id, password_hash, created_at, "
            "development_data) values (7, 'Old', 'old_door', :h, :now, 0)"),
            {"h": auth.hash_password(PASSWORD), "now": now})
        conn.execute(sa.text(
            "insert into invite_code (code, created_at, redeemed_by, redeemed_at) "
            "values ('OLD-1', :now, 7, :now)"), {"now": now})
    run_migrations(engine)

    assert "invite_code" not in inspect(engine).get_table_names()
    assert traders(engine) == ["old_door"]
    client = TestClient(create_app())
    csrf = CSRF.search(client.get("/login").text).group(1)
    response = client.post("/login", data={"login_id": "old_door", "password": PASSWORD,
                                           "csrf_token": csrf}, follow_redirects=False)
    assert response.status_code == 303
    assert client.get("/account").status_code == 200
