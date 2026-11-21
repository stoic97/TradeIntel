"""Moved out of tests/unit/api/test_admin_page.py by TICKET-945, so that no test file imports another.

Fixtures are not kept here: each fixture that lived in that file is a plain function
below, and the fixture of the same name calls it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from services.production.accounts import auth
from services.production.api.app import create_app
from services.production.db import models as m
from services.production.db.session import make_session
from services.shared.schemas import scope_v1 as s
from tests.conftest import TEST_SECRET_KEY

ADMIN = "boss"


TEMPLATES = Path("services/production/api/templates")


THEN = datetime(2026, 3, 2, 4, 30, tzinfo=UTC)


RUNNING = "aaa1111"


PLANTED_RUPEES = "₹98,765"


def admin_page_app(monkeypatch):
    monkeypatch.setenv("ADMIN_LOGIN_IDS", ADMIN)
    application = create_app()
    application.state.code_version = RUNNING
    return application


def admin_page_engine(app):
    return app.state.engine


def add_trader(engine, login_id, *, dev=False, name=None, joined=THEN) -> int:
    with make_session(engine) as sess:
        trader = m.Trader(display_name=name or login_id.title(), login_id=login_id,
                          password_hash="not-a-real-hash", created_at=joined,
                          development_data=dev)
        sess.add(trader)
        sess.commit()
        return trader.id


def signed_in(app, trader_id: int | None = None) -> TestClient:
    client = TestClient(app, follow_redirects=False)
    if trader_id is not None:
        with make_session(app.state.engine) as sess:
            trader = sess.get(m.Trader, trader_id)
            password_hash = trader.password_hash if trader else "an account that has gone"
        session = auth.new_session(trader_id, password_hash, TEST_SECRET_KEY)
        client.cookies.set(auth.SESSION_COOKIE, auth.seal_session(session, TEST_SECRET_KEY))
    return client


def admin_client(app, engine) -> TestClient:
    return signed_in(app, add_trader(engine, ADMIN))


def add_import(sess, trader_id, *, version=RUNNING, outcome=s.ImportOutcome.ACCEPTED_WITH_EXCLUSIONS,
               rejection=None, rows=(10, 8, 2), at=THEN, source="A", trips=0,
               raw_file_id=None, adapter=("made-up", "1"), reconstruction=None) -> m.Import:
    if raw_file_id is None:
        raw = m.RawFile(trader_id=trader_id, sha256=f"{trader_id}-{at.isoformat()}-{version}",
                        original_name="tradebook.csv", size=1, stored_path="nowhere", uploaded_at=at)
        sess.add(raw)
        sess.flush()
        raw_file_id = raw.id
    imp = m.Import(trader_id=trader_id, raw_file_id=raw_file_id, source_account=source,
                   trips_reconstructed=trips,
                   adapter_id=adapter[0], adapter_version=adapter[1], filemap_version="1",
                   reconstruction_version=reconstruction,
                   code_version=version, outcome=outcome, rejection_text=rejection,
                   rows_in=rows[0], rows_parsed=rows[1], rows_excluded=rows[2],
                   fees_available=False, version_no=1, created_at=at)
    sess.add(imp)
    sess.flush()
    return imp


def add_dwell(sess, trader_id, key, event_name="view", *, ms=60_000, surface="mirror_line", at=THEN):
    sess.add(m.DwellEvent(trader_id=trader_id, surface=surface, key=key, event=event_name,
                          at=at, duration_ms=ms))


def add_journal(sess, trader_id, import_id, *, opened=None) -> m.Journal:
    journal = m.Journal(trader_id=trader_id, import_id=import_id, unit=s.JournalUnit.DAY,
                        period_start="2026-03-02", period_end="2026-03-02", version_no=1,
                        generated_at=THEN, opened_at=opened, trip_ids="[]", sections="{}")
    sess.add(journal)
    sess.flush()
    return journal


def add_field_entry(sess, journal_id, value=f"felt fine at {PLANTED_RUPEES}", at=THEN):
    sess.add(m.JournalFieldEntry(journal_id=journal_id, field="note", value=value, entered_at=at,
                                 capture_phase=s.CapturePhase.AFTER_CLOSE))


def add_budget(sess, trader_id, at=THEN):
    sess.add(m.RiskBudgetDeclaration(trader_id=trader_id, value=Decimal(4321), unit="PCT",
                                     capital_amount=Decimal(876543), effective_from="2026-03-02",
                                     declared_at=at))


def add_consent(sess, trader_id, *, granted=True, purpose=s.ConsentPurpose.DIAGNOSIS, at=THEN):
    sess.add(m.ConsentEvent(trader_id=trader_id, purpose=purpose, scope="v1", terms_version="1",
                            granted=granted, at=at, method="web", wording_shown="the words"))


def view(app, engine) -> dict:
    from services.production.api import admin_view

    with make_session(engine) as sess:
        return admin_view.build(sess, running_version=app.state.code_version,
                                production=app.state.settings.production)


def row_of(the_view: dict, login_id: str) -> dict:
    return next(r for r in the_view["rows"] if r["login_id"] == login_id)


def row_counts(engine) -> dict[str, int]:
    with make_session(engine) as sess:
        return {t.name: sess.scalar(select(func.count()).select_from(t))
                for t in m.Base.metadata.sorted_tables}


def every_route(routes):
    """app.routes holds each include_router as a wrapper, so a flat walk finds no route at all."""
    for route in routes:
        included = getattr(route, "original_router", None)
        if included is not None:
            yield from every_route(included.routes)
        else:
            yield route
