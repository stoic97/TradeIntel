"""Moved out of tests/unit/api/test_consent.py by TICKET-945, so that no test file imports another.

Fixtures are not kept here: each fixture that lived in that file is a plain function
below, and the fixture of the same name calls it.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from services.production.api.app import create_app
from services.production.db import models as m
from services.production.db.session import make_engine, make_session, run_migrations

CSRF = re.compile(r'name="csrf_token"\s+value="([^"]+)"')


def consent_app_env(tmp_path, monkeypatch):
    db_url = f"sqlite:///{tmp_path / 'consent.db'}"
    monkeypatch.setenv("SCOPE_DB", db_url)
    monkeypatch.setenv("SCOPE_FILES", str(tmp_path / "files"))
    monkeypatch.setenv("SCOPE_SECRET_KEY", "test-secret-key-at-least-32-chars-long")
    engine = make_engine(db_url)
    run_migrations(engine)
    return engine


def consent_signed_in(app_env):
    engine = app_env
    client = TestClient(create_app())
    csrf = CSRF.search(client.get("/signup").text).group(1)
    client.post("/signup", data={"login_id": "rikk", "display_name": "Rikk",
                                     "password": "a-long-enough-password",
                                     "csrf_token": csrf})
    # Marked BEFORE signing in: sign-in now lands a trader where he has something to
    # do, which for a new account is the upload page and from there the consent
    # screen. A real account is refused the draft text there, which is the gate
    # working -- test_a_real_account_cannot_see_the_draft_text pins that directly.
    with make_session(engine) as sess:
        from sqlalchemy import update
        sess.execute(update(m.Trader).values(development_data=True))
        sess.commit()
    csrf = CSRF.search(client.get("/login").text).group(1)
    client.post("/login", data={"login_id": "rikk",
                                "password": "a-long-enough-password",
                                "csrf_token": csrf})
    return client, engine


def token(client, path="/consent"):
    return CSRF.search(client.get(path).text).group(1)
