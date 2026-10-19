"""Journal fields, and the provenance that keeps them honest (PRD 7.4).

Four fields: planned_sl, rationale, note, stop_existed_at_entry. Prompted, never
required.

Every entry carries entered_at and a capture_phase DERIVED BY THE SYSTEM from that
timestamp against the trip's own entry and exit -- never chosen by the trader. In v1
every entry is after_close by construction, because the Journal exists only after an
upload. The machinery exists now so that when v3 captures a stop before the trade,
hindsight and commitment cannot be confused.

That is the whole point of this step. A stop typed in on Sunday about Tuesday's
trade is a recollection; the same field filled before the trade is a commitment, and
the Experiment loop is worthless if it cannot tell them apart. Edits are append-only
for the same reason: a changed answer must not erase the first one.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from services.production.db import models as m
from services.production.db.session import make_engine, make_session, run_migrations
from services.production.journal import fields as fl
from services.shared.schemas import scope_v1 as s


@pytest.fixture()
def session():
    import os
    engine = make_engine(os.environ["SCOPE_DB"])
    run_migrations(engine)
    with make_session(engine) as sess:
        yield sess


ENTRY = datetime(2026, 9, 2, 9, 20, tzinfo=UTC)
EXIT = datetime(2026, 9, 2, 9, 35, tzinfo=UTC)


def test_a_phase_before_the_entry_is_a_commitment():
    assert fl.capture_phase(ENTRY - timedelta(minutes=5), ENTRY, EXIT) \
        is s.CapturePhase.BEFORE_ENTRY


def test_a_phase_between_entry_and_exit_is_during_the_trade():
    assert fl.capture_phase(ENTRY + timedelta(minutes=5), ENTRY, EXIT) \
        is s.CapturePhase.DURING_TRADE


def test_a_phase_after_the_exit_is_hindsight():
    assert fl.capture_phase(EXIT + timedelta(days=3), ENTRY, EXIT) \
        is s.CapturePhase.AFTER_CLOSE


def test_the_boundaries_belong_to_the_trade():
    """Exactly at entry is during; exactly at exit is during. A field filled at the
    instant of entry was not filled before it."""
    assert fl.capture_phase(ENTRY, ENTRY, EXIT) is s.CapturePhase.DURING_TRADE
    assert fl.capture_phase(EXIT, ENTRY, EXIT) is s.CapturePhase.DURING_TRADE


def test_in_v1_every_entry_is_after_close(session):
    """The Journal exists only after an upload, so there is no other possibility."""
    journal = _a_journal(session)
    entry = fl.record(session, journal=journal, field="planned_sl", value="4800",
                      trip_id="t04", trip_entry=ENTRY, trip_exit=EXIT)
    session.commit()
    assert entry.capture_phase is s.CapturePhase.AFTER_CLOSE


def test_the_phase_is_never_taken_from_the_caller(session):
    """A caller that could pass a phase could pass a false one."""
    import inspect
    assert "capture_phase" not in inspect.signature(fl.record).parameters


def test_an_edit_is_a_new_row_pointing_at_the_old(session):
    journal = _a_journal(session)
    first = fl.record(session, journal=journal, field="planned_sl", value="4800",
                      trip_id="t04", trip_entry=ENTRY, trip_exit=EXIT)
    session.commit()
    second = fl.record(session, journal=journal, field="planned_sl", value="4750",
                       trip_id="t04", trip_entry=ENTRY, trip_exit=EXIT)
    session.commit()

    rows = session.scalars(select(m.JournalFieldEntry)
                           .order_by(m.JournalFieldEntry.id)).all()
    assert len(rows) == 2, "the first answer is not erased"
    assert rows[0].value == "4800"
    assert rows[1].value == "4750"
    assert rows[1].previous_entry_id == first.id
    assert second.previous_entry_id == first.id


def test_the_current_value_is_the_latest_entry(session):
    journal = _a_journal(session)
    for value in ("4800", "4750", "4700"):
        fl.record(session, journal=journal, field="planned_sl", value=value,
                  trip_id="t04", trip_entry=ENTRY, trip_exit=EXIT)
    session.commit()
    assert fl.current(session, journal=journal, field="planned_sl",
                      trip_id="t04").value == "4700"


def test_fields_are_per_trip_where_they_belong_to_a_trip(session):
    journal = _a_journal(session)
    fl.record(session, journal=journal, field="planned_sl", value="4800",
              trip_id="t04", trip_entry=ENTRY, trip_exit=EXIT)
    fl.record(session, journal=journal, field="planned_sl", value="5100",
              trip_id="t05", trip_entry=ENTRY, trip_exit=EXIT)
    session.commit()
    assert fl.current(session, journal=journal, field="planned_sl",
                      trip_id="t04").value == "4800"
    assert fl.current(session, journal=journal, field="planned_sl",
                      trip_id="t05").value == "5100"


def test_a_note_belongs_to_the_day_not_a_trip(session):
    journal = _a_journal(session)
    entry = fl.record(session, journal=journal, field="note",
                      value="Slept badly.", trip_id=None)
    session.commit()
    assert entry.trip_id is None
    assert entry.capture_phase is s.CapturePhase.AFTER_CLOSE


def test_stop_existed_is_recorded_as_his_assertion(session):
    """PRD 7.4: his assertion, recorded as such -- not as a fact about the file."""
    journal = _a_journal(session)
    entry = fl.record(session, journal=journal, field="stop_existed_at_entry",
                      value="yes", trip_id="t04", trip_entry=ENTRY, trip_exit=EXIT)
    session.commit()
    assert entry.field == "stop_existed_at_entry"
    assert entry.value == "yes"


def test_an_unknown_field_is_refused(session):
    journal = _a_journal(session)
    with pytest.raises(fl.UnknownField):
        fl.record(session, journal=journal, field="mood", value="fine", trip_id=None)


def test_losing_trades_without_a_stop_counts_only_those_without_one(session):
    """The gap flagged when sections was written: the count must not be the loss
    count once the field exists, or a trader who recorded every stop is told he
    recorded none."""
    journal = _a_journal(session)
    fl.record(session, journal=journal, field="planned_sl", value="4800",
              trip_id="t04", trip_entry=ENTRY, trip_exit=EXIT)
    session.commit()
    recorded = fl.trips_with_a_planned_stop(session, journal=journal)
    assert recorded == {"t04"}


def _a_journal(session) -> m.Journal:
    import json
    trader = m.Trader(display_name="F", login_id="f", password_hash="x",
                      created_at=datetime.now(UTC))
    session.add(trader)
    session.flush()
    raw = m.RawFile(trader_id=trader.id, sha256="a" * 64, original_name="f",
                    size=1, stored_path="/tmp/f", uploaded_at=datetime.now(UTC))
    session.add(raw)
    session.flush()
    imp = m.Import(trader_id=trader.id, raw_file_id=raw.id, source_account="A",
                   adapter_id="d", adapter_version="1", filemap_version="1",
                   code_version="c", outcome=s.ImportOutcome.ACCEPTED_PARTIAL_FIELDS,
                   rows_in=1, rows_parsed=1, rows_excluded=0, fees_available=False,
                   version_no=1, created_at=datetime.now(UTC))
    session.add(imp)
    session.flush()
    journal = m.Journal(trader_id=trader.id, import_id=imp.id,
                        unit=s.JournalUnit.DAY, period_start="2026-09-02",
                        period_end="2026-09-02", version_no=1,
                        generated_at=datetime.now(UTC), trip_ids=json.dumps(["t04"]),
                        sections="{}")
    session.add(journal)
    session.flush()
    return journal
