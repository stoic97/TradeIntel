"""Journal fields, and the provenance that keeps them honest (PRD 7.4).

Four fields -- ``planned_sl``, ``rationale``, ``note``, ``stop_existed_at_entry`` --
prompted and never required.

Every entry carries ``entered_at`` and a ``capture_phase`` **derived here** from that
timestamp against the trip's own entry and exit. ``record()`` deliberately takes no
phase argument: a caller that could pass one could pass a false one, and the whole
value of the field is that it cannot be claimed.

Why this matters more than it looks. A stop typed on Sunday about Tuesday's trade is
a recollection. The same number entered before the trade is a commitment. The
Experiment loop in v3 asks whether a trader did what he said he would, and that
question is unanswerable if the two are stored identically. In v1 every entry is
``after_close`` by construction -- the Journal exists only after an upload -- so none
of this machinery changes a single v1 figure. It exists so the data collected now is
still usable when it does.

Edits are append-only for the same reason: the first answer is evidence too, and a
changed stop tells you something a single current value cannot.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from services.production.db import models as m
from services.shared.schemas import scope_v1 as s

PER_TRIP_FIELDS = frozenset({"planned_sl", "rationale", "stop_existed_at_entry"})
PER_PERIOD_FIELDS = frozenset({"note"})
KNOWN_FIELDS = PER_TRIP_FIELDS | PER_PERIOD_FIELDS


class UnknownField(Exception):
    """A field name the Journal does not have. The set is closed on purpose."""


def capture_phase(
    entered_at: datetime, trip_entry: datetime | None, trip_exit: datetime | None
) -> s.CapturePhase:
    """When this was written, relative to the trade it is about.

    The boundaries belong to the trade: a field filled at the instant of entry was
    not filled *before* it, and one filled at the exit was written while the
    position still existed. Both are DURING_TRADE. Treating either as a commitment
    would be the generous reading, and this field exists to refuse generous
    readings.
    """
    if trip_entry is None or trip_exit is None:
        return s.CapturePhase.AFTER_CLOSE
    if entered_at < trip_entry:
        return s.CapturePhase.BEFORE_ENTRY
    if entered_at <= trip_exit:
        return s.CapturePhase.DURING_TRADE
    return s.CapturePhase.AFTER_CLOSE


def _latest(
    sess: Session, journal: m.Journal, field: str, trip_id: str | None
) -> m.JournalFieldEntry | None:
    return sess.scalars(
        select(m.JournalFieldEntry)
        .where(m.JournalFieldEntry.journal_id == journal.id,
               m.JournalFieldEntry.field == field,
               m.JournalFieldEntry.trip_id.is_(trip_id) if trip_id is None
               else m.JournalFieldEntry.trip_id == trip_id)
        .order_by(m.JournalFieldEntry.id.desc())
    ).first()


def record(
    sess: Session,
    *,
    journal: m.Journal,
    field: str,
    value: str,
    trip_id: str | None,
    trip_entry: datetime | None = None,
    trip_exit: datetime | None = None,
) -> m.JournalFieldEntry:
    """Record an answer. Never an update: a changed answer is a new row.

    There is no ``capture_phase`` parameter, and there must never be one.
    """
    if field not in KNOWN_FIELDS:
        raise UnknownField(
            f"{field!r} is not a Journal field. The set is closed: {sorted(KNOWN_FIELDS)}"
        )

    entered_at = datetime.now(UTC)
    previous = _latest(sess, journal, field, trip_id)
    entry = m.JournalFieldEntry(
        journal_id=journal.id,
        trip_id=trip_id,
        field=field,
        value=value,
        entered_at=entered_at,
        capture_phase=capture_phase(entered_at, trip_entry, trip_exit),
        previous_entry_id=previous.id if previous else None,
    )
    sess.add(entry)
    sess.flush()
    return entry


def current(
    sess: Session, *, journal: m.Journal, field: str, trip_id: str | None
) -> m.JournalFieldEntry | None:
    """His answer as it stands. The earlier ones are still there."""
    return _latest(sess, journal, field, trip_id)


def history(
    sess: Session, *, journal: m.Journal, field: str, trip_id: str | None
) -> list[m.JournalFieldEntry]:
    """Every answer he has given to this field, oldest first."""
    return list(sess.scalars(
        select(m.JournalFieldEntry)
        .where(m.JournalFieldEntry.journal_id == journal.id,
               m.JournalFieldEntry.field == field,
               m.JournalFieldEntry.trip_id.is_(trip_id) if trip_id is None
               else m.JournalFieldEntry.trip_id == trip_id)
        .order_by(m.JournalFieldEntry.id)
    ).all())


def trips_with_a_planned_stop(sess: Session, *, journal: m.Journal) -> set[str]:
    """Which trips in this Journal have a planned stop recorded.

    The Journal's 'no planned stop recorded on N trades that lost' line counts the
    losses NOT in this set. Counting all losses would tell a trader who recorded
    every stop that he recorded none.
    """
    rows = sess.scalars(
        select(m.JournalFieldEntry)
        .where(m.JournalFieldEntry.journal_id == journal.id,
               m.JournalFieldEntry.field == "planned_sl",
               m.JournalFieldEntry.trip_id.is_not(None))
    ).all()
    return {row.trip_id for row in rows if row.value}
