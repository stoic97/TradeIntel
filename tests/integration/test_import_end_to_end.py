"""Upload to stored trips, through every layer (Manual Appendix A; closes TD-006).

TD-006 deferred tests/integration until there was a pipeline to integrate. There is
one now: format check, adapter, duplicate tiers, reconstruction, day versioning,
persistence. This walks it on a real fixture file and checks what a trader would be
able to see afterwards.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from services.production.ctr.intake import persist
from services.production.ctr.intake import pipeline as pl
from services.production.db import models as m
from services.production.db.session import make_engine, make_session, run_migrations
from services.shared.schemas import scope_v1 as s

CLEAN = Path("data/fixtures/duplicates/clean.csv")
DUPLICATED = Path("data/fixtures/duplicates/duplicated_block.csv")


def session(tmp_path, name="e2e"):
    engine = make_engine(f"sqlite:///{tmp_path / name}.db")
    run_migrations(engine)
    return make_session(engine)


def trader(sess) -> m.Trader:
    t = m.Trader(display_name="Design partner", login_id="dp", password_hash="x",
                 created_at=datetime.now(UTC))
    sess.add(t)
    sess.flush()
    return t


def upload(sess, who: m.Trader, path: Path, existing: dict[str, int] | None = None):
    plan = pl.plan_import(
        path.read_text(),
        context=pl.ImportContext(
            trader_id=str(who.id), source_account="A", code_version="e2e",
            existing_days=existing or {}, export_date="2026-10-18",
            export_date_source="trader",
        ),
    )
    return persist.write_plan(
        sess, trader=who, plan=plan, raw_sha256="a" * 64,
        original_name=path.name, stored_path=f"/tmp/{path.name}", size=path.stat().st_size,
    )


def test_a_first_upload_produces_everything_the_review_page_needs(tmp_path):
    with session(tmp_path) as sess:
        who = trader(sess)
        imp = upload(sess, who, CLEAN)
        sess.commit()

        assert imp.outcome is s.ImportOutcome.ACCEPTED_PARTIAL_FIELDS
        assert imp.rows_in == 4 and imp.rows_parsed == 4 and imp.rows_excluded == 0
        assert imp.fees_available is False
        assert imp.trips_reconstructed == 2
        assert imp.density_default_unit
        assert sess.scalars(select(m.ImportRow)).all()
        assert sess.scalars(select(m.TradingDayVersion)).all()


def test_a_second_upload_of_the_same_file_changes_no_day(tmp_path):
    with session(tmp_path) as sess:
        who = trader(sess)
        upload(sess, who, CLEAN)
        sess.commit()
        existing = persist.existing_days(sess, trader=who, source_account="A")
        upload(sess, who, CLEAN, existing)
        sess.commit()

        current = sess.scalars(
            select(m.TradingDayVersion).where(m.TradingDayVersion.superseded_by.is_(None))
        ).all()
        assert all(v.diff is s.DayDiff.IDENTICAL for v in current)
        assert not any(v.day_shrank for v in current)


def test_a_file_with_repeats_surfaces_them_without_losing_a_row(tmp_path):
    with session(tmp_path) as sess:
        who = trader(sess)
        imp = upload(sess, who, DUPLICATED)
        sess.commit()
        rows = sess.scalars(select(m.ImportRow)).all()
        assert len(rows) == imp.rows_in
        flagged = [r for r in rows if r.flag is s.RowFlag.SUSPECTED_DUPLICATE]
        assert len(flagged) == 6
        assert imp.rows_excluded == 0, "flagged, never dropped"


def test_nothing_in_the_database_mentions_a_real_trader(tmp_path):
    """The repo holds no trader-derived figure; the fixtures are synthetic."""
    with session(tmp_path) as sess:
        who = trader(sess)
        upload(sess, who, CLEAN)
        sess.commit()
        for row in sess.scalars(select(m.ImportRow)):
            assert "WIDGETOIL" in row.raw_text
