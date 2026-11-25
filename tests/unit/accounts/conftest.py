"""Fixtures and the one trader builder every test in tests/unit/accounts shares (TICKET-896).

They lived in test_deletion.py, and test_broker_pull_consent.py imported them from there,
which TICKET-945's guard refuses. a_trader is a plain function, not a fixture: a test calls
it with a session, a login and a store. Imports from a conftest.py are not counted by the guard.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from services.production.accounts.file_store import FileStore
from services.production.db import models as m
from services.production.db.session import make_engine, run_migrations
from services.shared.schemas import scope_v1 as s


@pytest.fixture()
def engine():
    import os
    e = make_engine(os.environ["SCOPE_DB"])
    run_migrations(e)
    return e


@pytest.fixture()
def store(tmp_path):
    from services.production.accounts.file_store import generate_key
    return FileStore(tmp_path / "files", generate_key())


def a_trader(sess, login_id: str, store: FileStore, content: bytes) -> m.Trader:
    """A trader with one of everything his deletion has to reach."""
    trader = m.Trader(display_name=login_id, login_id=login_id,
                      password_hash="x", created_at=datetime.now(UTC))
    sess.add(trader)
    sess.flush()
    sess.add(m.ConsentEvent(trader_id=trader.id, purpose=s.ConsentPurpose.DIAGNOSIS,
                            scope="v1", terms_version="0-draft", granted=True,
                            at=datetime.now(UTC), method="web",
                            wording_shown="x" * 100))
    sess.add(m.RiskBudgetDeclaration(
        trader_id=trader.id, value=Decimal(3000), unit="INR",
        effective_from="2026-09-01", declared_at=datetime.now(UTC),
        retrospective=True))

    stored = store.put(content)
    raw = m.RawFile(trader_id=trader.id, sha256=stored.sha256,
                    original_name="t.csv", size=stored.size,
                    stored_path=str(stored.path), uploaded_at=datetime.now(UTC))
    sess.add(raw)
    sess.flush()
    imp = m.Import(trader_id=trader.id, raw_file_id=raw.id, source_account="A",
                   adapter_id="dhan_tradebook_v1", adapter_version="1",
                   filemap_version="1", code_version="t",
                   outcome=s.ImportOutcome.ACCEPTED_PARTIAL_FIELDS,
                   rows_in=1, rows_parsed=1, rows_excluded=0, fees_available=False,
                   version_no=1, trips_reconstructed=1, density_default_unit="day",
                   created_at=datetime.now(UTC))
    sess.add(imp)
    sess.flush()
    sess.add(m.Trip(
        import_id=imp.id, trip_id=f"{login_id}-trip", trading_day="2026-09-01",
        exchange="MCX", symbol="WIDGETOIL", segment="OPT", direction="LONG",
        entry_ts=datetime(2026, 9, 1, 9, 30, tzinfo=UTC),
        exit_ts=datetime(2026, 9, 1, 10, 0, tzinfo=UTC), quantity=1,
        entry_price=Decimal(100), exit_price=Decimal(105), gross=Decimal(5),
        fees=Decimal(0), net=Decimal(5), fees_available=False,
        risk_unit_source=s.RiskUnitSourceV1.PREMIUM_PAID))
    journal = m.Journal(trader_id=trader.id, import_id=imp.id,
                        unit=s.JournalUnit.DAY, period_start="2026-09-01",
                        period_end="2026-09-01", version_no=1,
                        generated_at=datetime.now(UTC), opened_at=None,
                        trip_ids=json.dumps([f"{login_id}-trip"]), sections="{}")
    sess.add(journal)
    sess.flush()
    sess.add(m.JournalFieldEntry(
        journal_id=journal.id, trip_id=f"{login_id}-trip", field="planned_sl",
        value="250", entered_at=datetime.now(UTC),
        capture_phase=s.CapturePhase.AFTER_CLOSE))
    feedback = m.ChapterFeedback(trader_id=trader.id, chapter=1, answer="wrong",
                                 import_id=imp.id, answered_at=datetime.now(UTC))
    sess.add(feedback)
    sess.flush()
    sess.add(m.ChapterFeedbackReason(feedback_id=feedback.id, reason="wrong_facts",
                                     given_at=datetime.now(UTC)))
    sess.add(m.ReportFeedback(trader_id=trader.id, import_id=imp.id, trading_day="",
                              answer="wrong", note="his own words",
                              answered_at=datetime.now(UTC)))
    sess.add(m.GuessAnswer(trader_id=trader.id, answer="unknown", labels_version="t",
                           import_id=imp.id, answered_at=datetime.now(UTC)))
    sess.add(m.WtpAsked(trader_id=trader.id, journal_id=journal.id, asked_at=datetime.now(UTC)))
    sess.add(m.JournalRememberAnswer(trader_id=trader.id, journal_id=journal.id,
                                     trading_day=journal.period_start, answer="no",
                                     day_age_days=30, answered_at=datetime.now(UTC)))
    sess.add(m.LeavingCardShown(trader_id=trader.id, copy_version="t",
                                shown_at=datetime.now(UTC)))
    sess.add(m.LeavingCardAnswer(trader_id=trader.id, outcome="answered",
                                 answer="his own words", copy_version="t",
                                 answered_at=datetime.now(UTC)))
    sess.add(m.ChargeStatement(trader_id=trader.id, raw_file_id=raw.id, reader="t", days="{}",
                               uploaded_at=datetime.now(UTC)))
    sess.add(m.DwellEvent(trader_id=trader.id, surface="mirror", key="worst-days",
                          event="drawer_opened", at=datetime.now(UTC),
                          duration_ms=1200))
    sess.commit()
    return trader
