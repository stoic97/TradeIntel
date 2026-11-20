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

A later upload that changes a day writes a new version of its Journal. Nothing is copied
onto it, because a copy would claim to have been written then. A version reads its own
answers and those of the versions before it. A trade's id is a hash of the trade, so an
answer follows a trade only while the trade is the same; one about a trade that changed
stays on the version that listed it.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from services.production.db import models as m
from services.shared.schemas import scope_v1 as s

CHOICES: dict[str, tuple[tuple[str, str], ...]] = {
    "exit_how": (("stop", "At my stop"), ("target", "At my target"), ("closed", "I closed it"),
                 ("expiry", "Held to expiry"), ("dont_remember", "Don't remember")),
    "target": (("price", "A price I set"), ("none", "No target"), ("dont_remember", "Don't remember")),
    "planned": (("yes", "Yes"), ("no", "No"), ("dont_remember", "Don't remember")),
}
"""TICKET-1008: three per-trade questions with fixed answers, one tap each, and no free text.
They are Journal answers like the stop question, under consent v1's "the Journals written from
those trades", and go with "every Journal" when he deletes."""

QUESTIONS = {"exit_how": "How did it end?", "target": "Did it have a target?",
             "planned": "Planned before the session?"}
DONT_REMEMBER = "dont_remember"
"""An answer, counted as one, and left out of every rate."""

PER_TRIP_FIELDS = frozenset({"planned_sl", "rationale", "stop_existed_at_entry", *CHOICES})
PER_PERIOD_FIELDS = frozenset({"note"})
KNOWN_FIELDS = PER_TRIP_FIELDS | PER_PERIOD_FIELDS


class UnknownField(Exception):
    """A field name the Journal does not have, or an answer one of its fixed questions doesn't
    offer. Both sets are closed on purpose."""


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


def _lineage(sess: Session, journal: m.Journal) -> list[int]:
    """This version and the versions before it. Never the ones after."""
    ids = [journal.id]
    earlier = journal.supersedes
    while earlier is not None:
        ids.append(earlier)
        earlier = sess.scalar(select(m.Journal.supersedes).where(m.Journal.id == earlier))
    return ids


def _latest(
    sess: Session, journal: m.Journal, field: str, trip_id: str | None
) -> m.JournalFieldEntry | None:
    return sess.scalars(
        select(m.JournalFieldEntry)
        .where(m.JournalFieldEntry.journal_id.in_(_lineage(sess, journal)),
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

    if field in CHOICES and value not in {v for v, _ in CHOICES[field]}:
        raise UnknownField(f"{value!r} is not an answer to {field!r}: {[v for v, _ in CHOICES[field]]}")

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
        .where(m.JournalFieldEntry.journal_id.in_(_lineage(sess, journal)),
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
        .where(m.JournalFieldEntry.journal_id.in_(_lineage(sess, journal)),
               m.JournalFieldEntry.field == "planned_sl",
               m.JournalFieldEntry.trip_id.is_not(None))
    ).all()
    return {row.trip_id for row in rows if row.value}


def answers_by_trip(sess: Session, trader: m.Trader) -> dict[str, dict[str, str]]:
    """His answer as it stands to each fixed question, for every trade he has answered, across
    all his Journals (TICKET-1008). A trade's id is a hash of the trade, so an answer follows it
    from one version of a Journal to the next; the latest answer stands."""
    rows = sess.scalars(
        select(m.JournalFieldEntry)
        .join(m.Journal, m.JournalFieldEntry.journal_id == m.Journal.id)
        .where(m.Journal.trader_id == trader.id,
               m.JournalFieldEntry.field.in_(tuple(CHOICES)),
               m.JournalFieldEntry.trip_id.is_not(None))
        .order_by(m.JournalFieldEntry.id)
    ).all()
    out: dict[str, dict[str, str]] = {}
    for row in rows:
        out.setdefault(row.trip_id, {})[row.field] = row.value
    return out
