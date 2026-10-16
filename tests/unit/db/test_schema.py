"""The Scope v1 product schema.

Design section 3 fixes the tables; this file fixes what the database must guarantee
about them, not merely what columns exist:

* money survives the round trip exactly, including sub-paise (``ctr_v1``: an
  apportioned fill legitimately carries it, and rounding belongs at the presentation
  boundary),
* timestamps keep their timezone (``ctr_v1`` section 4.3: a naive instant is ambiguous),
* the versioned tables are insert-only in code, so a correction is a new row,
* no column is named archetype (PRD anti-scope).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import inspect, select, update
from sqlalchemy.exc import IntegrityError, StatementError

from services.production.db import models as m
from services.production.db.session import make_engine, make_session, run_migrations
from services.shared.schemas import scope_v1 as s

IST = UTC  # any aware zone serves; the point is that tzinfo survives


@pytest.fixture()
def session(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'scope.db'}")
    run_migrations(engine)
    with make_session(engine) as sess:
        yield sess


def _trader(sess) -> m.Trader:
    trader = m.Trader(display_name="Fixture", login_id="fixture", password_hash="x")
    sess.add(trader)
    sess.flush()
    return trader


def test_every_design_table_exists():
    engine = make_engine("sqlite:///:memory:")
    run_migrations(engine)
    tables = set(inspect(engine).get_table_names())
    expected = {
        "invite_code", "trader", "consent_event", "risk_budget_declaration",
        "raw_file", "import", "import_row", "trading_day_version", "trip",
        "open_position", "skipped_trip", "journal", "journal_field_entry",
        "wtp_answer", "dwell_event", "rule_declaration", "adherence_event",
        "deletion_record", "admin_action",
    }
    assert expected <= tables, f"missing: {sorted(expected - tables)}"


def test_no_column_anywhere_is_named_archetype():
    engine = make_engine("sqlite:///:memory:")
    run_migrations(engine)
    insp = inspect(engine)
    for table in insp.get_table_names():
        for col in insp.get_columns(table):
            assert "archetype" not in col["name"].lower(), f"{table}.{col['name']}"


def test_money_round_trips_exactly_including_sub_paise(session):
    trader = _trader(session)
    raw = m.RawFile(trader_id=trader.id, sha256="a" * 64, original_name="x.csv",
                    size=1, stored_path="/tmp/x", uploaded_at=datetime.now(UTC))
    session.add(raw)
    session.flush()
    imp = m.Import(trader_id=trader.id, raw_file_id=raw.id, source_account="A",
                   adapter_id="dhan_tradebook_v1", adapter_version="1",
                   filemap_version="1", code_version="deadbeef",
                   outcome=s.ImportOutcome.ACCEPTED_WITH_EXCLUSIONS,
                   rows_in=1, rows_parsed=1, rows_excluded=0, fees_available=False,
                   version_no=1, created_at=datetime.now(UTC))
    session.add(imp)
    session.flush()

    awkward = Decimal("1531.8333333333333333")
    trip = m.Trip(import_id=imp.id, trip_id="t1", trading_day="2026-10-16",
                  gross=awkward, fees=Decimal(0), net=awkward,
                  fees_available=False, risk_unit_source=s.RiskUnitSourceV1.UNAVAILABLE)
    session.add(trip)
    session.commit()

    loaded = session.scalars(select(m.Trip)).one()
    assert loaded.gross == awkward
    assert str(loaded.gross) == str(awkward)
    assert isinstance(loaded.gross, Decimal)


def test_timestamps_keep_their_timezone(session):
    trader = _trader(session)
    when = datetime.now(UTC) - timedelta(days=3)
    session.add(m.AdminAction(actor="cli", action="create_trader",
                              target=str(trader.id), at=when))
    session.commit()
    loaded = session.scalars(select(m.AdminAction)).one()
    assert loaded.at.tzinfo is not None
    assert loaded.at == when


def test_a_naive_timestamp_is_refused(session):
    """SQLAlchemy wraps the type's ValueError; the refusal is what matters."""
    trader = _trader(session)
    with pytest.raises((ValueError, StatementError)):
        # A naive datetime on purpose: this test exists to prove it is refused.
        session.add(m.AdminAction(actor="cli", action="x", target=str(trader.id),
                                  at=datetime.now()))  # noqa: DTZ005
        session.flush()


def test_enum_columns_store_their_string_value(session):
    trader = _trader(session)
    session.add(m.ConsentEvent(trader_id=trader.id, purpose=s.ConsentPurpose.DIAGNOSIS,
                               scope="v1", terms_version="1", granted=True,
                               at=datetime.now(UTC), method="web",
                               wording_shown="..."))
    session.commit()
    raw_value = session.connection().exec_driver_sql(
        "select purpose from consent_event"
    ).scalar_one()
    assert raw_value == "diagnosis"
    assert session.scalars(select(m.ConsentEvent)).one().purpose is s.ConsentPurpose.DIAGNOSIS


def test_insert_only_tables_reject_an_update(session):
    trader = _trader(session)
    session.add(m.ConsentEvent(trader_id=trader.id, purpose=s.ConsentPurpose.DIAGNOSIS,
                               scope="v1", terms_version="1", granted=True,
                               at=datetime.now(UTC), method="web", wording_shown="..."))
    session.commit()
    with pytest.raises(m.InsertOnlyViolation):
        session.execute(update(m.ConsentEvent).values(granted=False))
        session.flush()


def test_two_versions_of_one_trading_day_coexist(session):
    trader = _trader(session)
    for version, rows in ((1, 10), (2, 7)):
        session.add(m.TradingDayVersion(
            trader_id=trader.id, source_account="A", trading_day="2026-10-15",
            import_id=version, rows_before=10, rows_after=rows,
            diff=s.DayDiff.SHRUNK if rows < 10 else s.DayDiff.IDENTICAL,
            day_shrank=rows < 10))
    session.commit()
    both = session.scalars(select(m.TradingDayVersion)).all()
    assert len(both) == 2


def test_a_trip_without_an_import_is_refused(session):
    session.add(m.Trip(import_id=999999, trip_id="orphan", trading_day="2026-10-16",
                       gross=Decimal(1), fees=Decimal(0), net=Decimal(1),
                       fees_available=False,
                       risk_unit_source=s.RiskUnitSourceV1.UNAVAILABLE))
    with pytest.raises(IntegrityError):
        session.commit()


def test_the_migration_is_reversible(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'rev.db'}")
    run_migrations(engine)
    before = sorted(inspect(engine).get_table_names())
    run_migrations(engine, target="base")
    assert [t for t in inspect(engine).get_table_names() if t != "alembic_version"] == []
    run_migrations(engine)
    assert sorted(inspect(engine).get_table_names()) == before
