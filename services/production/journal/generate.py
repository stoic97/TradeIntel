"""Writing Journals, versioning them, and deciding which five he sees.

PRD 7.2. Three rules, and the third is the one broken by accident.

**One Journal per complete period**, written from the facts. Nothing is written for
a period still in progress: a trader who read it would have been told something the
next upload makes untrue.

**Immutable, versioned.** A later upload that changes a day writes a new version and
leaves the old one readable, because he may have read it. But an upload that changes
NOTHING writes nothing -- without that, every re-upload doubles his history and the
promise that old versions are kept becomes unusable noise. Sameness is decided by
comparing the facts, which is why the facts are stored rather than the prose.

**Latest five, with a catch-up list.** A backfill generates every Journal and
surfaces five. The PRD's own words: a developer who renders sixty entries has built
a defect.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from services.production.db import models as m
from services.production.journal import constants as k
from services.production.journal import periods as pd
from services.production.journal import sections as sec
from services.production.mirror.metrics import Trip
from services.shared.schemas import scope_v1 as s


@dataclass(frozen=True)
class Surface:
    """What the Journal list shows: five, and how many are behind them."""

    latest: list[m.Journal]
    catch_up_count: int
    total: int


def _current_versions(sess: Session, trader: m.Trader) -> list[m.Journal]:
    """One Journal per period: the newest version of each."""
    rows = sess.scalars(
        select(m.Journal)
        .where(m.Journal.trader_id == trader.id)
        .order_by(m.Journal.period_start, m.Journal.version_no)
    ).all()
    newest: dict[tuple[str, str], m.Journal] = {}
    for journal in rows:
        newest[(journal.unit.value, journal.period_start)] = journal
    return list(newest.values())


def _existing(sess: Session, trader: m.Trader, period: pd.Period) -> m.Journal | None:
    rows = sess.scalars(
        select(m.Journal)
        .where(m.Journal.trader_id == trader.id,
               m.Journal.period_start == period.period_start,
               m.Journal.period_end == period.period_end)
        .order_by(m.Journal.version_no.desc())
    ).all()
    return rows[0] if rows else None


def generate(
    sess: Session,
    *,
    trader: m.Trader,
    imp: m.Import,
    trips: list[Trip],
    preference: s.JournalUnit | None = None,
    preference_n: int | None = None,
) -> list[m.Journal]:
    """Write a Journal for every complete period this upload covers.

    Returns what it wrote, which is empty when the upload changed nothing.
    """
    choice = pd.resolve_unit(trips, preference=preference, preference_n=preference_n)
    periods = pd.periods_for(trips, unit=choice.unit, export_date=imp.export_date,
                             n=choice.n)

    written: list[m.Journal] = []
    now = datetime.now(UTC)
    for period in periods:
        if not period.complete:
            continue

        facts = sec.build(period, history=trips, fees_available=imp.fees_available)
        serialised = json.dumps(facts, sort_keys=True)

        previous = _existing(sess, trader, period)
        if previous is not None and previous.sections == serialised:
            # Nothing about this period changed. Writing a version anyway would
            # double his history on every re-upload and bury the versions that
            # genuinely differ.
            continue

        journal = m.Journal(
            trader_id=trader.id,
            import_id=imp.id,
            unit=choice.unit,
            period_start=period.period_start,
            period_end=period.period_end,
            version_no=(previous.version_no + 1) if previous else 1,
            supersedes=previous.id if previous else None,
            generated_at=now,
            trip_ids=json.dumps([t.trip_id for t in period.trips]),
            sections=serialised,
        )
        sess.add(journal)
        sess.flush()
        written.append(journal)
    return written


def surface(sess: Session, *, trader: m.Trader) -> Surface:
    """The latest five, newest first, and the count waiting in the catch-up list."""
    current = sorted(_current_versions(sess, trader),
                     key=lambda j: j.period_start, reverse=True)
    latest = current[:k.JOURNALS_ON_SURFACE]
    return Surface(latest=latest,
                   catch_up_count=max(0, len(current) - len(latest)),
                   total=len(current))


def catch_up(sess: Session, *, trader: m.Trader) -> list[m.Journal]:
    """Everything behind the surface, newest first."""
    current = sorted(_current_versions(sess, trader),
                     key=lambda j: j.period_start, reverse=True)
    return current[k.JOURNALS_ON_SURFACE:]


def mark_opened(sess: Session, journal: m.Journal) -> None:
    """Record the first time he opened it, and only the first.

    The willingness-to-pay trigger counts Journals OPENED, not generated (7.2), so
    this number decides when he is asked. Overwriting it on a second read would make
    a backfill look like engagement.
    """
    if journal.opened_at is not None:
        return
    opened = datetime.now(UTC)
    sess.connection().exec_driver_sql(
        "update journal set opened_at = ? where id = ?",
        (opened.isoformat(), journal.id),
    )
    # The raw statement bypasses the identity map, so the object the caller holds -
    # and anything that reads it in this session - would still say None. Expiring it
    # makes the next read go to the database. Without this, a route that marks a
    # Journal opened and then renders it shows it as never opened.
    sess.expire(journal, ["opened_at"])
