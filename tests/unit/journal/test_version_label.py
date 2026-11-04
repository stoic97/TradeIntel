"""A later upload changes a Journal only if it changes that day [TICKET-801].

One new trade moved the usual size and the count of trading days, both read against the whole
history. Those are stored in every Journal, so every day was written again, labelled "A later
upload changed this period", marked unread, and its note left behind on the old version.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta

from sqlalchemy import select

from services.production.db import models as m
from services.production.journal import fields as fl
from services.production.journal import generate as gen
from services.production.journal import sections as sec
from tests.unit.journal.test_generation import (  # noqa: F401
    an_import,
    load_trips,
    session,
    trader,
)


def one_more_trade(trips):
    """A new day, big enough to move the usual size and the count of trading days."""
    last = trips[-1]
    return [
        *trips,
        replace(
            last,
            trip_id="t99",
            trading_day="2026-09-11",
            entry_ts=last.entry_ts + timedelta(days=1),
            exit_ts=last.exit_ts + timedelta(days=1),
            lots=50,
        ),
    ]


def first_upload(session, trader):  # noqa: F811
    gen.generate(session, trader=trader, imp=an_import(session, trader), trips=load_trips())
    session.commit()


def second_upload(session, trader, trips=None):  # noqa: F811
    trips = one_more_trade(load_trips()) if trips is None else trips
    written = gen.generate(session, trader=trader, imp=an_import(session, trader), trips=trips)
    session.commit()
    return written


def day(session, start):  # noqa: F811
    return session.scalars(
        select(m.Journal).where(m.Journal.period_start == start).order_by(m.Journal.version_no)
    ).all()


def test_one_new_trade_writes_only_its_own_day(session, trader):  # noqa: F811
    first_upload(session, trader)
    assert [j.period_start for j in second_upload(session, trader)] == ["2026-09-11"]


def test_that_new_trade_does_move_the_history_wide_figures(session, trader):  # noqa: F811
    """Otherwise the test above proves nothing."""
    trips = load_trips()
    period = gen.pd.periods_for(trips, unit=gen.pd.resolve_unit(trips, preference=None, preference_n=None).unit,
                                export_date="2026-09-30", n=None)[0]
    before = sec.build(period, history=trips, fees_available=False)
    after = sec.build(period, history=one_more_trade(trips), fees_available=False)
    assert before != after
    assert sec.own_facts(before) == sec.own_facts(after)


def test_a_note_is_still_on_the_day_after_a_later_upload(session, trader):  # noqa: F811
    first_upload(session, trader)
    journal = day(session, "2026-09-01")[0]
    fl.record(session, journal=journal, field="note", value="my own words", trip_id=None)
    session.commit()
    second_upload(session, trader)
    assert [j.id for j in day(session, "2026-09-01")] == [journal.id]
    current = gen._current_versions(session, trader)
    shown = next(j for j in current if j.period_start == "2026-09-01")
    assert fl.current(session, journal=shown, field="note", trip_id=None).value == "my own words"


def test_a_journal_read_stays_read_after_a_later_upload(session, trader):  # noqa: F811
    first_upload(session, trader)
    gen.mark_opened(session, day(session, "2026-09-01")[0])
    session.commit()
    second_upload(session, trader)
    current = gen._current_versions(session, trader)
    assert next(j for j in current if j.period_start == "2026-09-01").opened_at is not None


def test_answering_a_stop_is_not_a_change_an_upload_made(session, trader):  # noqa: F811
    first_upload(session, trader)
    loser = next(t for t in load_trips() if t.is_loss)
    journal = day(session, loser.trading_day)[0]
    fl.record(session, journal=journal, field="planned_sl", value="100", trip_id=loser.trip_id)
    session.commit()
    second_upload(session, trader)
    assert [j.id for j in day(session, loser.trading_day)] == [journal.id]


def test_a_day_whose_trades_changed_still_gets_a_new_version(session, trader):  # noqa: F811
    first_upload(session, trader)
    second_upload(session, trader, [t for t in load_trips() if t.trip_id != "t03"])
    versions = day(session, "2026-09-01")
    assert [j.version_no for j in versions] == [1, 2]
    assert json.loads(versions[1].sections)["trades"]["count"] == 2


def test_only_that_day_is_marked_changed(session, trader):  # noqa: F811
    first_upload(session, trader)
    second_upload(session, trader, [t for t in load_trips() if t.trip_id != "t03"])
    assert gen.changed_by_upload(session, trader=trader) == {day(session, "2026-09-01")[1].id}


def _rewrite(session, trader, journal, trip_ids=None):  # noqa: F811
    """A version as the old rule stored it: already in his database, and it stays."""
    rewritten = m.Journal(
        trader_id=trader.id, import_id=journal.import_id, unit=journal.unit,
        period_start=journal.period_start, period_end=journal.period_end,
        version_no=journal.version_no + 1, supersedes=journal.id,
        generated_at=journal.generated_at, sections=journal.sections,
        trip_ids=journal.trip_ids if trip_ids is None else json.dumps(trip_ids),
    )
    session.add(rewritten)
    session.flush()
    return rewritten


def test_a_stored_rewrite_with_the_same_trades_is_not_marked(session, trader):  # noqa: F811
    first_upload(session, trader)
    _rewrite(session, trader, day(session, "2026-09-01")[0])
    assert gen.changed_by_upload(session, trader=trader) == set()


def test_a_real_change_stays_marked_through_a_later_rewrite(session, trader):  # noqa: F811
    first_upload(session, trader)
    changed = _rewrite(session, trader, day(session, "2026-09-01")[0], ["t01", "t02"])
    again = _rewrite(session, trader, changed)
    assert gen.changed_by_upload(session, trader=trader) == {changed.id, again.id}


def test_one_traders_changes_are_not_anothers(session, trader):  # noqa: F811
    first_upload(session, trader)
    second_upload(session, trader, [t for t in load_trips() if t.trip_id != "t03"])
    other = m.Trader(display_name="Other", login_id="other", password_hash="x",
                     created_at=trader.created_at)
    session.add(other)
    session.flush()
    assert gen.changed_by_upload(session, trader=other) == set()
