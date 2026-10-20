"""The risk budget declaration (PRD 5.5, TD-028).

> "How much are you willing to lose on a single trade?" rupees or % of capital
> "Has that been your number for the whole history you uploaded? If it changed,
>  from when?"

The second question is the one most products would skip, and it is the one that
makes the first answer usable: a budget without an effective date tells you nothing
about the trades it is supposed to divide.

Three rules with teeth. A percentage without the capital amount is refused, because
a percentage of nothing has no rupee value and every trip measured against it would
be silently wrong. Declarations are never edited - a new number is a new row, and
October's trips keep October's. And a declaration effective before it was declared
is RETROSPECTIVE, recorded as such, because a number remembered is not a number
committed to.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from services.production.api.app import create_app
from services.production.api.routes_budget import _today
from services.production.db import models as m
from services.production.db.session import make_engine, make_session, run_migrations

CSRF = re.compile(r'name="csrf_token"\s+value="([^"]+)"')


@pytest.fixture()
def engine():
    import os
    e = make_engine(os.environ["SCOPE_DB"])
    run_migrations(e)
    return e


@pytest.fixture()
def client(engine):
    from services.production.accounts import auth
    from services.shared.schemas import scope_v1 as s
    with make_session(engine) as sess:
        trader = m.Trader(display_name="F", login_id="fx",
                          password_hash=auth.hash_password("a-long-enough-password"),
                          created_at=datetime.now(UTC), development_data=True)
        sess.add(trader)
        sess.flush()
        sess.add(m.ConsentEvent(trader_id=trader.id, purpose=s.ConsentPurpose.DIAGNOSIS,
                                scope="v1", terms_version="0-draft", granted=True,
                                at=datetime.now(UTC), method="web",
                                wording_shown="x" * 100))
        sess.commit()
    c = TestClient(create_app())
    csrf = CSRF.search(c.get("/login").text).group(1)
    c.post("/login", data={"login_id": "fx", "password": "a-long-enough-password",
                           "csrf_token": csrf}, follow_redirects=False)
    return c


def token(client, path="/budget"):
    return CSRF.search(client.get(path).text).group(1)


def test_the_form_asks_both_questions(client):
    body = client.get("/budget").text.lower()
    assert "willing to lose on a single trade" in body
    assert "whole history" in body or "if it changed" in body


def test_a_rupee_declaration_is_stored(client, engine):
    client.post("/budget", data={"value": "3000", "unit": "INR",
                                 "effective_from": "2026-09-01",
                                 "csrf_token": token(client)})
    with make_session(engine) as sess:
        stored = sess.scalars(select(m.RiskBudgetDeclaration)).one()
    assert str(stored.value) == "3000"
    assert stored.unit == "INR"
    assert stored.effective_from == "2026-09-01"


def test_a_percentage_without_capital_is_refused(client, engine):
    response = client.post("/budget", data={"value": "2", "unit": "PCT",
                                            "effective_from": "2026-09-01",
                                            "csrf_token": token(client)})
    assert response.status_code == 400
    assert "capital" in response.text.lower()
    with make_session(engine) as sess:
        assert sess.scalars(select(m.RiskBudgetDeclaration)).all() == []


def test_a_percentage_with_capital_is_stored(client, engine):
    client.post("/budget", data={"value": "2", "unit": "PCT",
                                 "capital_amount": "150000",
                                 "effective_from": "2026-09-01",
                                 "csrf_token": token(client)})
    with make_session(engine) as sess:
        stored = sess.scalars(select(m.RiskBudgetDeclaration)).one()
    assert stored.unit == "PCT"
    assert str(stored.capital_amount) == "150000"


def test_a_declaration_effective_in_the_past_is_marked_retrospective(client, engine):
    client.post("/budget", data={"value": "3000", "unit": "INR",
                                 "effective_from": "2026-01-01",
                                 "csrf_token": token(client)})
    with make_session(engine) as sess:
        assert sess.scalars(select(m.RiskBudgetDeclaration)).one().retrospective is True


def test_a_declaration_effective_today_is_not_retrospective(client, engine):
    today = _today().isoformat()
    client.post("/budget", data={"value": "3000", "unit": "INR",
                                 "effective_from": today,
                                 "csrf_token": token(client)})
    with make_session(engine) as sess:
        assert sess.scalars(select(m.RiskBudgetDeclaration)).one().retrospective is False


def test_a_new_number_is_a_new_row_not_an_edit(client, engine):
    client.post("/budget", data={"value": "3000", "unit": "INR",
                                 "effective_from": "2026-09-01",
                                 "csrf_token": token(client)})
    client.post("/budget", data={"value": "5000", "unit": "INR",
                                 "effective_from": "2026-10-01",
                                 "csrf_token": token(client)})
    with make_session(engine) as sess:
        rows = sess.scalars(select(m.RiskBudgetDeclaration)
                            .order_by(m.RiskBudgetDeclaration.id)).all()
    assert len(rows) == 2, "October's trips must keep October's number"
    assert [str(r.value) for r in rows] == ["3000", "5000"]


def test_the_history_is_shown(client):
    client.post("/budget", data={"value": "3000", "unit": "INR",
                                 "effective_from": "2026-09-01",
                                 "csrf_token": token(client)})
    client.post("/budget", data={"value": "5000", "unit": "INR",
                                 "effective_from": "2026-10-01",
                                 "csrf_token": token(client)})
    body = client.get("/budget").text
    assert "3,000" in body or "3000" in body
    assert "5,000" in body or "5000" in body
    assert "2026-09-01" in body


def test_a_zero_or_negative_budget_is_refused(client, engine):
    for bad in ("0", "-500"):
        response = client.post("/budget", data={"value": bad, "unit": "INR",
                                                "effective_from": "2026-09-01",
                                                "csrf_token": token(client)})
        assert response.status_code == 400
    with make_session(engine) as sess:
        assert sess.scalars(select(m.RiskBudgetDeclaration)).all() == []


def test_a_future_effective_date_is_refused(client, engine):
    """A budget for trades he has not taken is not a declaration about this history."""
    ahead = (_today() + timedelta(days=30)).isoformat()
    response = client.post("/budget", data={"value": "3000", "unit": "INR",
                                            "effective_from": ahead,
                                            "csrf_token": token(client)})
    assert response.status_code == 400
    with make_session(engine) as sess:
        assert sess.scalars(select(m.RiskBudgetDeclaration)).all() == []


def test_the_budget_needs_consent(engine):
    from services.production.accounts import auth
    with make_session(engine) as sess:
        sess.add(m.Trader(display_name="N", login_id="noconsent",
                          password_hash=auth.hash_password("a-long-enough-password"),
                          created_at=datetime.now(UTC), development_data=True))
        sess.commit()
    c = TestClient(create_app())
    csrf = CSRF.search(c.get("/login").text).group(1)
    c.post("/login", data={"login_id": "noconsent",
                           "password": "a-long-enough-password",
                           "csrf_token": csrf}, follow_redirects=False)
    assert c.get("/budget", follow_redirects=False).status_code in (302, 303)
