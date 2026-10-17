"""Writing an ImportPlan into the schema (design section 3).

The plan decided everything; this layer only writes it. So these tests check the
writing, not the decisions: that every row of the file survives as a row in the
database, that the import records the versions that produced it, that day versions
supersede rather than accumulate, and that a rejected file still leaves a record --
a trader who uploaded the wrong thing must be able to see that he did.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select

from services.production.ctr.intake import persist
from services.production.ctr.intake import pipeline as pl
from services.production.db import models as m
from services.production.db.session import make_engine, make_session, run_migrations
from services.shared.schemas import scope_v1 as s

DUPES = Path("data/fixtures/duplicates")


def fresh_session(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'scope.db'}")
    run_migrations(engine)
    return make_session(engine)


def seed_trader(sess) -> m.Trader:
    trader = m.Trader(display_name="Fixture", login_id="fx", password_hash="x",
                      created_at=datetime.now(UTC))
    sess.add(trader)
    sess.flush()
    return trader


def plan_for(name: str, existing: dict[str, int] | None = None) -> pl.ImportPlan:
    return pl.plan_import(
        (DUPES / name).read_text(),
        context=pl.ImportContext(
            trader_id="fx", source_account="A", code_version="testsha",
            existing_days=existing or {}, export_date="2026-10-18",
            export_date_source="trader",
        ),
    )


def test_a_plan_becomes_an_import_with_its_versions(tmp_path):
    with fresh_session(tmp_path) as sess:
        trader = seed_trader(sess)
        imp = persist.write_plan(sess, trader=trader, plan=plan_for("clean.csv"),
                                 raw_sha256="a" * 64, original_name="clean.csv",
                                 stored_path="/tmp/clean.csv", size=100)
        sess.commit()
        loaded = sess.scalars(select(m.Import)).one()
        assert loaded.id == imp.id
        assert loaded.code_version == "testsha"
        assert loaded.adapter_id == "dhan_tradebook_v1"
        assert loaded.outcome is s.ImportOutcome.ACCEPTED_PARTIAL_FIELDS
        assert loaded.version_no == 1
        assert loaded.export_date == "2026-10-18"


def test_every_row_of_the_file_is_written(tmp_path):
    with fresh_session(tmp_path) as sess:
        trader = seed_trader(sess)
        plan = plan_for("repeated_legitimate_fills.csv")
        persist.write_plan(sess, trader=trader, plan=plan, raw_sha256="b" * 64,
                           original_name="r.csv", stored_path="/tmp/r.csv", size=1)
        sess.commit()
        rows = sess.scalars(select(m.ImportRow)).all()
        assert len(rows) == plan.rows_in == 6
        flagged = [r for r in rows if r.flag is s.RowFlag.SUSPECTED_DUPLICATE]
        assert len(flagged) == 4
        assert all(r.raw_text for r in rows), "raw text is retained on every row"


def test_trips_are_written_with_their_money_intact(tmp_path):
    with fresh_session(tmp_path) as sess:
        trader = seed_trader(sess)
        plan = plan_for("clean.csv")
        persist.write_plan(sess, trader=trader, plan=plan, raw_sha256="c" * 64,
                           original_name="c.csv", stored_path="/tmp/c.csv", size=1)
        sess.commit()
        trips = sess.scalars(select(m.Trip)).all()
        assert len(trips) == len(plan.trips)
        for written, planned in zip(trips, plan.trips, strict=True):
            assert written.gross == planned.gross_pnl
            assert written.net == planned.net_pnl
            assert written.trading_day


def test_a_second_upload_supersedes_the_day_it_covers(tmp_path):
    with fresh_session(tmp_path) as sess:
        trader = seed_trader(sess)
        first = plan_for("clean.csv")
        persist.write_plan(sess, trader=trader, plan=first, raw_sha256="d" * 64,
                           original_name="1.csv", stored_path="/tmp/1.csv", size=1)
        sess.commit()
        existing = persist.existing_days(sess, trader=trader, source_account="A")
        second = plan_for("clean.csv", existing=existing)
        persist.write_plan(sess, trader=trader, plan=second, raw_sha256="e" * 64,
                           original_name="2.csv", stored_path="/tmp/2.csv", size=1)
        sess.commit()

        versions = sess.scalars(select(m.TradingDayVersion)).all()
        assert len(versions) == 2, "two versions of the one day, both retained"
        latest = [v for v in versions if v.superseded_by is None]
        assert len(latest) == 1
        assert latest[0].diff is s.DayDiff.IDENTICAL
        assert sess.scalar(select(func.count()).select_from(m.Import)) == 2


def test_the_second_import_records_what_it_supersedes(tmp_path):
    with fresh_session(tmp_path) as sess:
        trader = seed_trader(sess)
        persist.write_plan(sess, trader=trader, plan=plan_for("clean.csv"),
                           raw_sha256="f" * 64, original_name="1.csv",
                           stored_path="/tmp/1.csv", size=1)
        sess.commit()
        persist.write_plan(sess, trader=trader, plan=plan_for("clean.csv"),
                           raw_sha256="0" * 64, original_name="2.csv",
                           stored_path="/tmp/2.csv", size=1)
        sess.commit()
        imports = sess.scalars(select(m.Import).order_by(m.Import.id)).all()
        assert imports[1].version_no == 2
        assert imports[1].supersedes_import_id == imports[0].id


def test_a_rejected_file_still_leaves_a_record(tmp_path):
    """He uploaded the wrong file; he must be able to see that he did."""
    with fresh_session(tmp_path) as sess:
        trader = seed_trader(sess)
        plan = pl.plan_import(
            "Symbol,Realised P&L\nWIDGETOIL,1500.00\n",
            context=pl.ImportContext(trader_id="fx", source_account="A",
                                     code_version="testsha"),
        )
        persist.write_plan(sess, trader=trader, plan=plan, raw_sha256="1" * 64,
                           original_name="pnl.csv", stored_path="/tmp/pnl.csv", size=1)
        sess.commit()
        imp = sess.scalars(select(m.Import)).one()
        assert imp.outcome is s.ImportOutcome.REJECTED
        assert imp.rejection_text
        assert sess.scalar(select(func.count()).select_from(m.Trip)) == 0


def test_the_raw_file_row_is_written_once_per_upload(tmp_path):
    with fresh_session(tmp_path) as sess:
        trader = seed_trader(sess)
        persist.write_plan(sess, trader=trader, plan=plan_for("clean.csv"),
                           raw_sha256="2" * 64, original_name="c.csv",
                           stored_path="/tmp/c.csv", size=42)
        sess.commit()
        raw = sess.scalars(select(m.RawFile)).one()
        assert raw.sha256 == "2" * 64
        assert raw.size == 42
