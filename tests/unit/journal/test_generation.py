"""Generating, versioning and surfacing Journals (PRD 7.2).

Three rules, and the third is the one a developer breaks by accident:

A Journal is written once per complete period, from the facts, and is IMMUTABLE. A
later upload that changes a day writes a NEW VERSION; the old one stays readable,
because a trader may have read it.

A backfill generates every Journal and surfaces the latest five, with a catch-up
list for the rest. "A developer who renders sixty entries has built a defect" is the
PRD's own wording, and this is the test of it.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from services.production.db import models as m
from services.production.db.session import make_engine, make_session, run_migrations
from services.production.journal import constants as k
from services.production.journal import generate as gen
from services.production.mirror.metrics import Trip
from services.shared.schemas import scope_v1 as s


def load_trips() -> list[Trip]:
    return [
        Trip(trip_id=r["trip_id"], trading_day=r["trading_day"],
             entry_ts=datetime.fromisoformat(r["entry_ts"]),
             exit_ts=datetime.fromisoformat(r["exit_ts"]),
             holding_seconds=r["holding_seconds"], net=Decimal(r["net"]),
             lots=r["lots"],
             risk_unit_source=s.RiskUnitSourceV1(r["risk_unit_source"]),
             symbol=r["symbol"])
        for r in json.loads(
            Path("tests/fixtures/mirror_contract/main.json").read_text())
    ]


@pytest.fixture()
def session():
    import os
    engine = make_engine(os.environ["SCOPE_DB"])
    run_migrations(engine)
    with make_session(engine) as sess:
        yield sess


@pytest.fixture()
def trader(session):
    t = m.Trader(display_name="Fixture", login_id="fx", password_hash="x",
                 created_at=datetime.now(UTC))
    session.add(t)
    session.flush()
    return t


def an_import(session, trader, export_date="2026-09-30") -> m.Import:
    raw = m.RawFile(trader_id=trader.id, sha256="a" * 64, original_name="f.csv",
                    size=1, stored_path="/tmp/f", uploaded_at=datetime.now(UTC))
    session.add(raw)
    session.flush()
    imp = m.Import(trader_id=trader.id, raw_file_id=raw.id, source_account="A",
                   adapter_id="dhan", adapter_version="1", filemap_version="1",
                   code_version="gen", outcome=s.ImportOutcome.ACCEPTED_PARTIAL_FIELDS,
                   rows_in=40, rows_parsed=40, rows_excluded=0, fees_available=False,
                   trips_reconstructed=40, version_no=1, export_date=export_date,
                   density_default_unit="day", created_at=datetime.now(UTC))
    session.add(imp)
    session.flush()
    return imp


def test_one_journal_per_complete_period(session, trader):
    imp = an_import(session, trader)
    written = gen.generate(session, trader=trader, imp=imp, trips=load_trips())
    session.commit()
    assert len(written) == 8
    assert {j.period_start for j in written} == {
        "2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04",
        "2026-09-07", "2026-09-08", "2026-09-09", "2026-09-10"}


def test_an_incomplete_period_is_not_written(session, trader):
    imp = an_import(session, trader, export_date=None)
    written = gen.generate(session, trader=trader, imp=imp, trips=load_trips())
    session.commit()
    assert len(written) == 7, "the last day has no later day and no export date"


def test_the_stored_journal_holds_facts_and_its_trips(session, trader):
    imp = an_import(session, trader)
    gen.generate(session, trader=trader, imp=imp, trips=load_trips())
    session.commit()
    first = session.scalars(
        select(m.Journal).order_by(m.Journal.period_start)).first()
    facts = json.loads(first.sections)
    assert facts["trades"]["count"] == 3
    assert json.loads(first.trip_ids) == ["t01", "t02", "t03"]
    assert first.version_no == 1


def test_regenerating_a_changed_day_writes_a_new_version(session, trader):
    imp = an_import(session, trader)
    gen.generate(session, trader=trader, imp=imp, trips=load_trips())
    session.commit()

    second = an_import(session, trader)
    fewer = [t for t in load_trips() if t.trip_id != "t03"]
    gen.generate(session, trader=trader, imp=second, trips=fewer)
    session.commit()

    versions = session.scalars(
        select(m.Journal).where(m.Journal.period_start == "2026-09-01")
        .order_by(m.Journal.version_no)).all()
    assert len(versions) == 2, "the first version stays; a trader may have read it"
    assert versions[1].version_no == 2
    assert versions[1].supersedes == versions[0].id
    assert json.loads(versions[1].sections)["trades"]["count"] == 2


def test_an_unchanged_day_is_not_rewritten(session, trader):
    imp = an_import(session, trader)
    gen.generate(session, trader=trader, imp=imp, trips=load_trips())
    session.commit()
    second = an_import(session, trader)
    gen.generate(session, trader=trader, imp=second, trips=load_trips())
    session.commit()
    assert len(session.scalars(select(m.Journal)).all()) == 8, "no version churn"


def test_the_surface_shows_the_latest_five(session, trader):
    imp = an_import(session, trader)
    gen.generate(session, trader=trader, imp=imp, trips=load_trips())
    session.commit()
    surface = gen.surface(session, trader=trader)
    assert len(surface.latest) == k.JOURNALS_ON_SURFACE
    assert surface.latest[0].period_start == "2026-09-10", "newest first"
    assert surface.catch_up_count == 3
    assert surface.total == 8


def test_a_short_history_has_no_catch_up_list(session, trader):
    imp = an_import(session, trader)
    gen.generate(session, trader=trader, imp=imp,
                 trips=[t for t in load_trips() if t.trading_day <= "2026-09-03"])
    session.commit()
    surface = gen.surface(session, trader=trader)
    assert surface.catch_up_count == 0


def test_only_the_current_version_is_surfaced(session, trader):
    imp = an_import(session, trader)
    gen.generate(session, trader=trader, imp=imp, trips=load_trips())
    session.commit()
    second = an_import(session, trader)
    gen.generate(session, trader=trader, imp=second,
                 trips=[t for t in load_trips() if t.trip_id != "t40"])
    session.commit()
    surface = gen.surface(session, trader=trader)
    assert len({j.period_start for j in surface.latest}) == len(surface.latest)
    assert surface.total == 8, "versions are not extra Journals"


def test_opening_a_journal_records_when(session, trader):
    imp = an_import(session, trader)
    written = gen.generate(session, trader=trader, imp=imp, trips=load_trips())
    session.commit()
    assert written[0].opened_at is None
    gen.mark_opened(session, written[0])
    session.commit()
    assert session.get(m.Journal, written[0].id).opened_at is not None


def test_opening_twice_keeps_the_first_time(session, trader):
    imp = an_import(session, trader)
    written = gen.generate(session, trader=trader, imp=imp, trips=load_trips())
    session.commit()
    gen.mark_opened(session, written[0])
    session.commit()
    first = session.get(m.Journal, written[0].id).opened_at
    gen.mark_opened(session, written[0])
    session.commit()
    assert session.get(m.Journal, written[0].id).opened_at == first
