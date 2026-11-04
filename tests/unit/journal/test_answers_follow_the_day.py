"""What a trader wrote stays with the day when a later upload changes it [TICKET-814].

Answers are insert-only and carry when they were written, so nothing is copied onto a new
version: a version reads its own answers and those of the versions before it. A trade's id is
a hash of the trade, so an answer follows a trade only while the trade is the same.

Day 2026-09-01 holds t01, t02 and t03 in the synthetic contract fixture.
"""

from __future__ import annotations

import json

from sqlalchemy import func, select

from services.production.db import models as m
from services.production.journal import fields as fl
from services.production.journal import generate as gen
from tests.unit.journal.test_generation import (  # noqa: F401
    load_trips,
    session,
    trader,
)
from tests.unit.journal.test_version_label import (
    _rewrite,
    day,
    first_upload,
    second_upload,
)

WITHOUT_T03 = [t for t in load_trips() if t.trip_id != "t03"]


def changed_day(session, trader):  # noqa: F811
    """A version 1 and a version 2 of 2026-09-01, the second without t03."""
    first_upload(session, trader)
    v1 = day(session, "2026-09-01")[0]
    return v1


def test_the_note_shows_on_the_new_version(session, trader):  # noqa: F811
    v1 = changed_day(session, trader)
    fl.record(session, journal=v1, field="note", value="my own words", trip_id=None)
    second_upload(session, trader, WITHOUT_T03)
    v2 = day(session, "2026-09-01")[1]
    assert fl.current(session, journal=v2, field="note", trip_id=None).value == "my own words"


def test_an_answer_shows_for_a_trade_still_in_the_day(session, trader):  # noqa: F811
    v1 = changed_day(session, trader)
    fl.record(session, journal=v1, field="rationale", value="the reason", trip_id="t01")
    second_upload(session, trader, WITHOUT_T03)
    v2 = day(session, "2026-09-01")[1]
    assert fl.current(session, journal=v2, field="rationale", trip_id="t01").value == "the reason"


def test_nothing_is_copied_and_the_original_is_untouched(session, trader):  # noqa: F811
    v1 = changed_day(session, trader)
    entry = fl.record(session, journal=v1, field="note", value="my own words", trip_id=None)
    phase, written = entry.capture_phase, entry.entered_at
    second_upload(session, trader, WITHOUT_T03)
    v2 = day(session, "2026-09-01")[1]
    shown = fl.current(session, journal=v2, field="note", trip_id=None)
    assert (shown.id, shown.journal_id) == (entry.id, v1.id)
    assert (shown.capture_phase, shown.entered_at) == (phase, written)
    assert session.scalar(select(func.count()).select_from(m.JournalFieldEntry)) == 1


def test_an_edit_on_the_new_version_points_at_the_old_answer(session, trader):  # noqa: F811
    v1 = changed_day(session, trader)
    old = fl.record(session, journal=v1, field="note", value="first", trip_id=None)
    second_upload(session, trader, WITHOUT_T03)
    v2 = day(session, "2026-09-01")[1]
    new = fl.record(session, journal=v2, field="note", value="second", trip_id=None)
    assert (new.journal_id, new.previous_entry_id) == (v2.id, old.id)
    assert fl.current(session, journal=v2, field="note", trip_id=None).value == "second"
    assert [e.value for e in fl.history(session, journal=v2, field="note", trip_id=None)] == [
        "first", "second",
    ]


def test_an_earlier_version_does_not_read_a_later_answer(session, trader):  # noqa: F811
    v1 = changed_day(session, trader)
    second_upload(session, trader, WITHOUT_T03)
    v2 = day(session, "2026-09-01")[1]
    fl.record(session, journal=v2, field="note", value="written later", trip_id=None)
    assert fl.current(session, journal=v1, field="note", trip_id=None) is None


def test_another_days_answers_stay_there(session, trader):  # noqa: F811
    v1 = changed_day(session, trader)
    fl.record(session, journal=v1, field="note", value="about the first", trip_id=None)
    other = day(session, "2026-09-02")[0]
    assert fl.current(session, journal=other, field="note", trip_id=None) is None


def test_a_recorded_stop_is_still_counted_two_versions_later(session, trader):  # noqa: F811
    """It carried one version and was lost on the next, so the line told him he recorded none."""
    trips = load_trips()
    target = next(
        d for d in sorted({t.trading_day for t in trips})
        if sum(t.trading_day == d for t in trips) >= 3
        and any(t.is_loss for t in trips if t.trading_day == d)
    )
    in_day = [t for t in trips if t.trading_day == target]
    loser = next(t for t in in_day if t.is_loss)
    others = [t for t in in_day if t.trip_id != loser.trip_id]
    first_upload(session, trader)
    v1 = day(session, target)[0]
    fl.record(session, journal=v1, field="planned_sl", value="100", trip_id=loser.trip_id)
    session.commit()
    second_upload(session, trader, [t for t in trips if t.trip_id != others[0].trip_id])
    gone = {others[0].trip_id, others[1].trip_id}
    second_upload(session, trader, [t for t in trips if t.trip_id not in gone])
    v3 = day(session, target)[2]
    assert v3.version_no == 3
    left = [t for t in in_day if t.trip_id not in gone]
    facts = json.loads(v3.sections)
    assert facts["planned_sl"]["losing_trades_without_one"] == sum(t.is_loss for t in left) - 1


def test_the_way_back_is_the_version_with_the_other_trades(session, trader):  # noqa: F811
    v1 = changed_day(session, trader)
    second_upload(session, trader, WITHOUT_T03)
    v2 = day(session, "2026-09-01")[1]
    assert gen.earlier_with_other_trades(session, v2) == v1.id


def test_the_way_back_skips_a_version_with_the_same_trades(session, trader):  # noqa: F811
    v1 = changed_day(session, trader)
    second_upload(session, trader, WITHOUT_T03)
    v2 = day(session, "2026-09-01")[1]
    v3 = _rewrite(session, trader, v2)
    assert gen.earlier_with_other_trades(session, v3) == v1.id


def test_a_first_version_has_no_way_back(session, trader):  # noqa: F811
    assert gen.earlier_with_other_trades(session, changed_day(session, trader)) is None


def test_a_rewrite_with_the_same_trades_has_no_way_back(session, trader):  # noqa: F811
    v2 = _rewrite(session, trader, changed_day(session, trader))
    assert gen.earlier_with_other_trades(session, v2) is None
