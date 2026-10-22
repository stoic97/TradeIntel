"""Consent as a ledger, not a tick-box (thesis 19.3, PRD 10).

One row per consent event, each purpose separable, the exact wording stored on the
row, and a withdrawal written as a new row rather than an edit. The ledger is the
trader's own to read.

The ninth test is the one that matters most and is easiest to lose: it asserts the
screen actually contains every element PRD section 10 requires. A consent screen
that omits what deletion cannot undo is not a smaller promise, it is a different one.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from services.production.accounts import consent as cs
from services.production.api.app import create_app
from services.production.db import models as m
from services.production.db.session import make_engine, make_session, run_migrations
from services.shared.schemas import scope_v1 as s

CSRF = re.compile(r'name="csrf_token"\s+value="([^"]+)"')


@pytest.fixture()
def app_env(tmp_path, monkeypatch):
    db_url = f"sqlite:///{tmp_path / 'consent.db'}"
    monkeypatch.setenv("SCOPE_DB", db_url)
    monkeypatch.setenv("SCOPE_FILES", str(tmp_path / "files"))
    monkeypatch.setenv("SCOPE_SECRET_KEY", "test-secret-key-at-least-32-chars-long")
    engine = make_engine(db_url)
    run_migrations(engine)
    return engine


@pytest.fixture()
def signed_in(app_env):
    from datetime import UTC, datetime
    engine = app_env
    with make_session(engine) as sess:
        sess.add(m.InviteCode(code="C-1", created_at=datetime.now(UTC)))
        sess.commit()
    client = TestClient(create_app())
    csrf = CSRF.search(client.get("/invite/C-1").text).group(1)
    client.post("/invite/C-1", data={"login_id": "rikk", "display_name": "Rikk",
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


def test_a_trader_without_consent_is_sent_to_the_consent_screen(signed_in):
    client, _ = signed_in
    response = client.get("/upload", follow_redirects=False)
    assert response.status_code in (302, 303)
    assert "/consent" in response.headers["location"]


def test_the_screen_offers_each_v1_purpose_separately(signed_in):
    client, _ = signed_in
    body = client.get("/consent").text
    assert 'name="diagnosis"' in body
    assert 'name="engine_testing"' in body


def test_granting_writes_one_row_per_purpose_with_its_wording(signed_in):
    client, engine = signed_in
    client.post("/consent", data={"diagnosis": "yes", "engine_testing": "yes",
                                  "csrf_token": token(client)})
    with make_session(engine) as sess:
        events = sess.scalars(select(m.ConsentEvent)).all()
    purposes = {e.purpose for e in events}
    assert purposes == {s.ConsentPurpose.DIAGNOSIS, s.ConsentPurpose.ENGINE_TESTING}
    assert all(e.granted for e in events)
    assert all(len(e.wording_shown) > 80 for e in events), "the row stores what he read"
    assert all(e.terms_version for e in events)


def test_refusing_engine_testing_still_allows_the_product(signed_in):
    client, engine = signed_in
    client.post("/consent", data={"diagnosis": "yes", "csrf_token": token(client)})
    assert client.get("/upload").status_code == 200
    with make_session(engine) as sess:
        events = sess.scalars(select(m.ConsentEvent)).all()
    assert {e.purpose for e in events} == {s.ConsentPurpose.DIAGNOSIS}


def test_refusing_diagnosis_leaves_the_product_closed(signed_in):
    client, _ = signed_in
    response = client.post("/consent", data={"engine_testing": "yes",
                                             "csrf_token": token(client)})
    assert response.status_code == 400
    assert client.get("/upload", follow_redirects=False).status_code in (302, 303)


def test_the_trader_can_read_his_own_ledger(signed_in):
    client, _ = signed_in
    client.post("/consent", data={"diagnosis": "yes", "engine_testing": "yes",
                                  "csrf_token": token(client)})
    body = client.get("/settings/consent").text
    assert "diagnosis" in body.lower()
    assert "engine testing" in body.lower() or "engine_testing" in body.lower()


def test_withdrawing_writes_a_new_row_and_never_edits(signed_in):
    client, engine = signed_in
    client.post("/consent", data={"diagnosis": "yes", "engine_testing": "yes",
                                  "csrf_token": token(client)})
    csrf = token(client, "/settings/consent")
    client.post("/settings/consent/withdraw",
                data={"purpose": "engine_testing", "csrf_token": csrf})
    with make_session(engine) as sess:
        events = sess.scalars(
            select(m.ConsentEvent).where(
                m.ConsentEvent.purpose == s.ConsentPurpose.ENGINE_TESTING
            ).order_by(m.ConsentEvent.id)
        ).all()
    assert len(events) == 2, "the grant stays; the withdrawal is a new row"
    assert events[0].granted is True and events[1].granted is False


def test_withdrawing_diagnosis_closes_the_upload_path(signed_in):
    client, _ = signed_in
    client.post("/consent", data={"diagnosis": "yes", "csrf_token": token(client)})
    csrf = token(client, "/settings/consent")
    client.post("/settings/consent/withdraw",
                data={"purpose": "diagnosis", "csrf_token": csrf})
    assert client.get("/upload", follow_redirects=False).status_code in (302, 303)


def test_the_text_contains_everything_prd_section_10_requires(signed_in):
    client, _ = signed_in
    body = client.get("/consent").text.lower()
    assert "the file" in body and "journal" in body, "what we store"
    # "Until you delete it" and nothing more: a dormancy sweep was promised once and
    # nothing implemented it, so the sentence came out (launch runbook, part C1).
    assert "until you delete it" in body, "for how long"
    assert "24 months" not in body, "a promise nothing implements"
    assert "no third party" in body or "nobody else" in body, "who can access it"
    assert "backup" in body and "30 days" in body, "what deletion covers"
    assert "cannot be undone" in body, "what deletion cannot undo"


def test_a_draft_consent_version_is_refused_for_a_real_account():
    assert cs.CURRENT.version.endswith("draft")
    with pytest.raises(cs.UnreviewedConsentText):
        cs.require_reviewed(cs.CURRENT, development_data=False)
    cs.require_reviewed(cs.CURRENT, development_data=True)


def test_a_real_account_cannot_see_the_draft_text(app_env):
    """The gate, from the outside: a partner account is refused the unreviewed text.

    PRD section 10 publishes the consent text only after the data-flow map is
    verified and the deletion runbook has been run, and counsel's sign-off gates
    accepting tradebooks at all. An unreviewed promise is one nobody has checked we
    can keep, so the page refuses rather than showing it.

    This test used to assert a 500 and call it "refused, loudly". It was loud: the
    exception reached the browser as "Internal Server Error", with a traceback in
    the log and nothing at all for the person reading the screen. It was found by
    walking the app, not by any test, because this test was the thing asserting it.
    The gate has not moved. What it returns is now a page that says why.

    Every account created through an invite is development_data=False, so this is
    the path a real partner takes, not an edge case.
    """
    from datetime import UTC, datetime
    engine = app_env
    with make_session(engine) as sess:
        sess.add(m.InviteCode(code="REAL-1", created_at=datetime.now(UTC)))
        sess.commit()
    client = TestClient(create_app(), raise_server_exceptions=False)
    csrf = CSRF.search(client.get("/invite/REAL-1").text).group(1)
    client.post("/invite/REAL-1", data={"login_id": "real", "display_name": "Real",
                                        "password": "a-long-enough-password",
                                        "csrf_token": csrf})
    csrf = CSRF.search(client.get("/login").text).group(1)
    client.post("/login", data={"login_id": "real",
                                "password": "a-long-enough-password",
                                "csrf_token": csrf}, follow_redirects=False)

    response = client.get("/consent")
    assert response.status_code == 503, "refused, and refused legibly"
    body = response.text.lower()
    assert "not open yet" in body
    assert "internal server error" not in body
    assert "traceback" not in body
    assert "cannot upload" in body, "it has to say what the person cannot do"

    # The draft wording must not leak through the refusal.
    assert "what deletion cannot undo" not in body

    # And the POST is closed the same way, so a form replayed from a cached page
    # cannot record consent to text the account was never allowed to read.
    assert client.post("/consent", data={"diagnosis": "yes"}).status_code in (403, 503)
    with make_session(engine) as sess:
        assert sess.scalars(select(m.ConsentEvent)).all() == []
