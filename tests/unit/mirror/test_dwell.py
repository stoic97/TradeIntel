"""Dwell events: what the trader read, so v2 can reorder the Mirror for him.

PRD decision 12: the Mirror's order is fixed in v1 and every line emits a dwell
event, so v2 can reorder per trader. Nothing in v1 reads this data. It is collected
now because retrofitting it would mean asking the first partners to use a product
that learns nothing from them.

This is the first thing the product records about what the trader DOES rather than
what his file says, so the consent text names it.
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

CSRF = re.compile(r'name="csrf_token"\s+value="([^"]+)"')


@pytest.fixture()
def engine():
    import os
    e = make_engine(os.environ["SCOPE_DB"])
    run_migrations(e)
    return e


@pytest.fixture()
def client(engine):
    from datetime import UTC, datetime

    from services.production.accounts import auth
    from services.shared.schemas import scope_v1 as s
    with make_session(engine) as sess:
        trader = m.Trader(display_name="Fixture", login_id="fx",
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


def test_an_event_is_stored(client, engine):
    response = client.post("/events", json={"events": [
        {"surface": "mirror_line", "key": "worst-days", "event": "view",
         "duration_ms": 4200},
    ]})
    assert response.status_code == 204
    with make_session(engine) as sess:
        stored = sess.scalars(select(m.DwellEvent)).one()
    assert stored.surface == "mirror_line"
    assert stored.key == "worst-days"
    assert stored.duration_ms == 4200


def test_several_events_post_in_one_batch(client, engine):
    client.post("/events", json={"events": [
        {"surface": "mirror_line", "key": "worst-days", "event": "view", "duration_ms": 100},
        {"surface": "mirror_line", "key": "by-hour", "event": "drawer_open"},
        {"surface": "mirror_line", "key": "by-hour", "event": "leave", "duration_ms": 900},
    ]})
    with make_session(engine) as sess:
        assert len(sess.scalars(select(m.DwellEvent)).all()) == 3


def test_events_are_attributed_to_the_signed_in_trader(client, engine):
    client.post("/events", json={"events": [
        {"surface": "mirror_line", "key": "worst-days", "event": "view"}]})
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader)).one()
        stored = sess.scalars(select(m.DwellEvent)).one()
    assert stored.trader_id == trader.id


def test_a_signed_out_post_stores_nothing(engine):
    anonymous = TestClient(create_app())
    response = anonymous.post("/events", json={"events": [
        {"surface": "mirror_line", "key": "worst-days", "event": "view"}]})
    assert response.status_code in (204, 401, 403)
    with make_session(engine) as sess:
        assert sess.scalars(select(m.DwellEvent)).all() == []


def test_an_unknown_surface_or_event_is_refused(client, engine):
    """The vocabulary is fixed: this collects reading behaviour, not anything else."""
    client.post("/events", json={"events": [
        {"surface": "something_else", "key": "x", "event": "view"},
        {"surface": "mirror_line", "key": "x", "event": "keystroke"},
    ]})
    with make_session(engine) as sess:
        assert sess.scalars(select(m.DwellEvent)).all() == []


def test_a_malformed_body_does_not_error(client):
    """Telemetry must never break the page it is measuring."""
    assert client.post("/events", json={"nope": 1}).status_code == 204
    assert client.post("/events", content=b"not json").status_code in (204, 400, 422)


def test_no_trade_data_is_ever_in_an_event(client, engine):
    """A dwell event names a line, never a figure or a trade."""
    client.post("/events", json={"events": [
        {"surface": "mirror_line", "key": "worst-days", "event": "view",
         "duration_ms": 100}]})
    with make_session(engine) as sess:
        stored = sess.scalars(select(m.DwellEvent)).one()
    for field in (stored.surface, stored.key, stored.event):
        assert "₹" not in field
        assert not any(ch.isdigit() for ch in field), f"{field!r} carries a number"


def test_the_mirror_page_carries_the_dwell_script(engine):
    """A Mirror with lines on it loads the script; an empty one has nothing to
    measure and does not."""
    import json
    from datetime import UTC, datetime
    from decimal import Decimal
    from pathlib import Path as P

    from services.production.accounts import auth
    from services.shared.schemas import scope_v1 as s

    with make_session(engine) as sess:
        trader = m.Trader(display_name="WithTrips", login_id="wt",
                          password_hash=auth.hash_password("a-long-enough-password"),
                          created_at=datetime.now(UTC), development_data=True)
        sess.add(trader)
        sess.flush()
        sess.add(m.ConsentEvent(trader_id=trader.id, purpose=s.ConsentPurpose.DIAGNOSIS,
                                scope="v1", terms_version="0-draft", granted=True,
                                at=datetime.now(UTC), method="web",
                                wording_shown="x" * 100))
        raw = m.RawFile(trader_id=trader.id, sha256="a" * 64, original_name="f.csv",
                        size=1, stored_path="/tmp/f", uploaded_at=datetime.now(UTC))
        sess.add(raw)
        sess.flush()
        imp = m.Import(trader_id=trader.id, raw_file_id=raw.id, source_account="A",
                       adapter_id="dhan_tradebook_v1", adapter_version="1",
                       filemap_version="1", code_version="dwellsha",
                       outcome=s.ImportOutcome.ACCEPTED_PARTIAL_FIELDS, rows_in=40,
                       rows_parsed=40, rows_excluded=0, fees_available=False,
                       trips_reconstructed=40, version_no=1,
                       density_default_unit="day", created_at=datetime.now(UTC))
        sess.add(imp)
        sess.flush()
        for t in json.loads(P("tests/fixtures/mirror_contract/main.json").read_text()):
            sess.add(m.Trip(
                import_id=imp.id, trip_id=t["trip_id"], trading_day=t["trading_day"],
                exchange="MCX", symbol="WIDGETOIL", segment="OPT", direction="LONG",
                entry_ts=datetime.fromisoformat(t["entry_ts"]),
                exit_ts=datetime.fromisoformat(t["exit_ts"]),
                quantity=t["quantity"], entry_price=Decimal(100), exit_price=Decimal(100),
                gross=Decimal(t["gross"]), fees=Decimal(t["fees"]),
                net=Decimal(t["net"]), fees_available=False,
                risk_unit_source=s.RiskUnitSourceV1(t["risk_unit_source"])))
        sess.commit()

    c = TestClient(create_app())
    csrf = CSRF.search(c.get("/login").text).group(1)
    c.post("/login", data={"login_id": "wt", "password": "a-long-enough-password",
                           "csrf_token": csrf}, follow_redirects=False)
    body = c.get("/mirror").text
    assert "/static/dwell.js" in body
    assert 'data-dwell-line="worst-days"' in body


def test_the_consent_text_names_what_we_record_about_reading(client):
    """Decision: dwell is not a separable purpose, so the text says it plainly."""
    assert "read" in cs.CURRENT.what_we_store.lower()
    body = client.get("/consent").text.lower()
    assert "which lines you open" in body or "what you read" in body
