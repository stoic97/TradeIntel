"""Home, signed in (handoff 5, screen 20): the headline card, latest Journals, upload.

Through the app, with the 40-trade fixture trader signed in.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import select

from services.production.accounts import auth
from services.production.api.app import create_app
from services.production.db import models as m
from services.production.db.session import make_session
from services.shared.schemas import scope_v1 as s
from tests.unit.mirror.conftest import CSRF


def test_home_opens_the_scope_from_its_headline(client):
    body = client.get("/").text
    assert '<a class="scope-card on-navy" href="/mirror">' in body
    assert "of your losses in five days" not in body
    assert re.search(r"Your report · Import \d+ · \d\d \w{3} \d{4}</span>", body)
    assert "Open your report" in body


def test_home_names_the_trader_and_offers_the_upload(client):
    body = client.get("/").text
    assert '<span class="num num--label">Fixture</span>' in body
    assert '<a class="btn btn--primary btn--block" href="/upload">Upload new trades</a>' in body
    assert "A new file replaces the days it covers." in body


def test_home_is_no_tab_of_the_three(client):
    body = client.get("/").text
    assert '<nav class="bottom-nav"' in body and 'aria-current="page"' not in body


def test_without_journals_there_is_no_empty_journal_list(client):
    body = client.get("/").text
    assert "Latest Journals" not in body and "Days worth a look" not in body


def test_the_days_say_their_day_their_trades_and_their_net(client, engine):
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader).where(m.Trader.login_id == "fx")).one()
        imp = sess.scalars(select(m.Import)).one()
        trips = [t for t in sess.scalars(select(m.Trip)) if t.trading_day == "2026-09-01"]
        sess.add(
            m.Journal(
                trader_id=trader.id,
                import_id=imp.id,
                unit=s.JournalUnit.DAY,
                period_start="2026-09-01",
                period_end="2026-09-01",
                version_no=1,
                generated_at=datetime.now(UTC),
                opened_at=None,
                trip_ids=json.dumps([t.trip_id for t in trips]),
                sections="{}",
            )
        )
        sess.commit()
        net = sum(t.net for t in trips)
        count = len(trips)
    body = client.get("/").text
    assert '<h2 class="card-title">Latest Journals</h2>' in body, "this one day isn't one the report named"
    row = re.search(r'<a class="latest__row" href="/journals/\d+">(.*?)</a>', body).group(1)
    assert '<span class="body">01 Sep 2026</span>' in row
    assert f">{count} trades</span>" in row
    from services.production.api.formatting import rupees, tone

    assert f'num--{tone(net)}">{rupees(net)}</span>' in row


def test_signed_in_without_a_record_goes_where_he_belongs(engine):
    with make_session(engine) as sess:
        sess.add(
            m.Trader(
                display_name="New",
                login_id="new",
                password_hash=auth.hash_password("a-long-enough-password"),
                created_at=datetime.now(UTC),
                development_data=True,
            )
        )
        sess.commit()
    c = TestClient(create_app())
    csrf = CSRF.search(c.get("/login").text).group(1)
    c.post(
        "/login",
        data={"login_id": "new", "password": "a-long-enough-password", "csrf_token": csrf},
        follow_redirects=False,
    )
    r = c.get("/", follow_redirects=False)
    assert (r.status_code, r.headers["location"]) == (303, "/upload")
