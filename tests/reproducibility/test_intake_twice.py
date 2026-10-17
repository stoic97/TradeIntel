"""Same file, same code, same bytes out (methodology Rule 4, section 7).

Two levels, because one without the other is a half-proof:

The **plan digest** is a content hash over everything the pipeline decided and over
nothing that moves with the clock -- run the same file a year apart and it matches.

The **written rows** must agree too, since a deterministic decision written
non-deterministically is still a non-reproducible import. The database comparison
excludes only the identifiers and timestamps a second insert necessarily changes;
everything a trader could ever be shown is compared.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from services.production.ctr.intake import persist
from services.production.ctr.intake import pipeline as pl
from services.production.db import models as m
from services.production.db.session import make_engine, make_session, run_migrations

FIXTURES = sorted(Path("data/fixtures/duplicates").glob("*.csv"))


def context() -> pl.ImportContext:
    return pl.ImportContext(
        trader_id="fx", source_account="A", code_version="fixedsha",
        export_date="2026-10-18", export_date_source="trader",
    )


def test_every_fixture_plans_to_the_same_digest_twice():
    for path in FIXTURES:
        text = path.read_text()
        first = pl.plan_import(text, context=context())
        second = pl.plan_import(text, context=context())
        assert first.digest() == second.digest(), path.name


def test_each_fixture_has_its_own_digest():
    """A digest that collided would make the first test vacuous."""
    digests = {
        path.name: pl.plan_import(path.read_text(), context=context()).digest()
        for path in FIXTURES
    }
    assert len(set(digests.values())) == len(digests), digests


def _write_once(tmp_path, name: str, text: str) -> list[tuple]:
    engine = make_engine(f"sqlite:///{tmp_path / name}.db")
    run_migrations(engine)
    with make_session(engine) as sess:
        trader = m.Trader(display_name="Fixture", login_id="fx", password_hash="x",
                          created_at=datetime.now(UTC))
        sess.add(trader)
        sess.flush()
        persist.write_plan(
            sess, trader=trader, plan=pl.plan_import(text, context=context()),
            raw_sha256="a" * 64, original_name="f.csv", stored_path="/tmp/f.csv", size=1,
        )
        sess.commit()

        imp = sess.scalars(select(m.Import)).one()
        rows = [
            (r.row_no, r.status, r.flag, r.dup_group, r.raw_text)
            for r in sess.scalars(select(m.ImportRow).order_by(m.ImportRow.row_no))
        ]
        trips = [
            (t.trip_id, t.trading_day, t.gross, t.fees, t.net, t.quantity,
             t.risk_unit_source, t.risk_unit_value)
            for t in sess.scalars(select(m.Trip).order_by(m.Trip.trip_id))
        ]
        days = [
            (d.trading_day, d.rows_before, d.rows_after, d.diff, d.day_shrank)
            for d in sess.scalars(
                select(m.TradingDayVersion).order_by(m.TradingDayVersion.trading_day)
            )
        ]
        return [
            (imp.outcome, imp.rows_in, imp.rows_parsed, imp.rows_excluded,
             imp.fees_available, imp.snapshot_digest, imp.profile_versions,
             imp.density_default_unit, imp.rejection_text),
            rows, trips, days,
        ]


def test_the_written_rows_are_identical_across_two_fresh_databases(tmp_path):
    for path in FIXTURES:
        text = path.read_text()
        first = _write_once(tmp_path, f"{path.stem}_1", text)
        second = _write_once(tmp_path, f"{path.stem}_2", text)
        assert first == second, path.name


def test_the_stored_digest_matches_the_plan(tmp_path):
    """The import carries the digest of the decision that produced it."""
    text = (Path("data/fixtures/duplicates") / "clean.csv").read_text()
    plan = pl.plan_import(text, context=context())
    written = _write_once(tmp_path, "digest_check", text)
    assert written[0][5] == plan.digest()
