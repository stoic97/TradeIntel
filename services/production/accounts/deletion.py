"""Deletion that executes (PRD 3, PRD 10).

The consent screen says: *"The file, every artefact derived from it, and every
Journal. Backups roll off within 30 days, so your data is gone from those too.
What we keep is the record that you consented and the record that you deleted."*
This is the code that has to be worth that sentence.

Three things it is careful about.

**It deletes from a list, and the list is the data-flow map.** Anything holding a
trader's data that is not in ``LOCATIONS`` is a location nobody checks. The map is
in ``docs/runbooks/data-deletion.md`` and the two are meant to be read together.

**A shared file is not deleted twice.** The store is content-addressed by the hash
of the plaintext, so two traders who upload byte-identical exports share one
encrypted blob. Deleting it because one of them asked would delete the other's
file -- silently, since nothing would error until he next opened his record. The
blob goes only when no other trader's row still points at it.

**Insert-only does not mean undeletable.** Those tables refuse UPDATE, so a
correction is a new row; a deletion is not a correction. The guard permits DELETE
deliberately, and a test pins that, because tightening it later would turn this
promise into a silent failure.

What survives, and the consent text says so: the record that he consented, and the
record that he deleted. No name, no trades, no derived figure.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from services.production.accounts.file_store import FileStore
from services.production.db import models as m

LOCATIONS = (
    "the application database",
    "the encrypted file store on the server disk",
)
"""Everywhere this code can reach. Backups are the runbook's, not the code's.

A daily droplet backup holds yesterday's copy of both, and no code of ours can
reach into it. The consent text promises 30 days because that is the retention,
and the runbook is what checks it. Saying so here keeps the gap visible rather
than letting this list imply a completeness it does not have.
"""

RETAINED = (
    "the record that this account consented, and the record that it was deleted. "
    "No name, no trades, no figure derived from them."
)


@dataclass
class Removed:
    """What came out, by table, plus the files that went with it."""

    rows: dict[str, int] = field(default_factory=dict)
    files_deleted: list[str] = field(default_factory=list)
    files_kept_shared: list[str] = field(default_factory=list)

    def record(self, table: str, count: int) -> None:
        if count:
            self.rows[table] = self.rows.get(table, 0) + count

    @property
    def total_rows(self) -> int:
        return sum(self.rows.values())


def _ids(sess: Session, column, where) -> list[int]:
    return list(sess.scalars(select(column).where(where)).all())


def _delete_where(sess: Session, model, where, removed: Removed) -> None:
    result = sess.execute(delete(model).where(where))
    removed.record(model.__tablename__, result.rowcount or 0)


def delete_trader(
    sess: Session,
    store: FileStore,
    *,
    trader: m.Trader,
    requested_at: datetime | None = None,
) -> m.DeletionRecord:
    """Remove this trader and everything derived from him. Returns the record.

    Children before parents, so nothing is left pointing at something gone. The
    caller commits.
    """
    trader_id = trader.id
    requested_at = requested_at or datetime.now(UTC)
    removed = Removed()

    import_ids = _ids(sess, m.Import.id, m.Import.trader_id == trader_id)
    journal_ids = _ids(sess, m.Journal.id, m.Journal.trader_id == trader_id)
    digests = list(sess.scalars(
        select(m.RawFile.sha256).where(m.RawFile.trader_id == trader_id)).all())

    if journal_ids:
        _delete_where(sess, m.JournalFieldEntry,
                      m.JournalFieldEntry.journal_id.in_(journal_ids), removed)
    _delete_where(sess, m.WtpAnswer, m.WtpAnswer.trader_id == trader_id, removed)
    _delete_where(sess, m.Journal, m.Journal.trader_id == trader_id, removed)

    if import_ids:
        for model in (m.Trip, m.OpenPosition, m.SkippedTrip, m.ImportRow):
            _delete_where(sess, model, model.import_id.in_(import_ids), removed)
    _delete_where(sess, m.Import, m.Import.trader_id == trader_id, removed)

    for model in (m.TradingDayVersion, m.RiskBudgetDeclaration, m.DwellEvent,
                  m.RuleDeclaration, m.AdherenceEvent, m.ConsentEvent, m.RawFile):
        _delete_where(sess, model, model.trader_id == trader_id, removed)

    # His invite is his: leaving the row would point at an account that is gone,
    # and clearing the trader from it would hand the code back out as unused.
    _delete_where(sess, m.InviteCode, m.InviteCode.redeemed_by == trader_id, removed)
    _delete_where(sess, m.Trader, m.Trader.id == trader_id, removed)

    sess.flush()
    _remove_files(sess, store, digests, removed)

    record = m.DeletionRecord(
        trader_id=trader_id,
        requested_at=requested_at,
        completed_at=datetime.now(UTC),
        what_removed=json.dumps({
            "rows": removed.rows,
            "files_deleted": len(removed.files_deleted),
            "files_kept_because_another_account_has_the_same_bytes":
                len(removed.files_kept_shared),
        }, sort_keys=True),
        what_retained=RETAINED,
        locations_checked=json.dumps(list(LOCATIONS)),
    )
    sess.add(record)
    sess.flush()
    return record


def _remove_files(
    sess: Session, store: FileStore, digests: list[str], removed: Removed
) -> None:
    """Delete each stored file no other account still points at.

    The store is keyed by the hash of the plaintext, so identical exports from two
    traders are one blob on disk. Deleting it for one of them would take the
    other's file with it, and nothing would say so until he opened his record.
    """
    for digest in dict.fromkeys(digests):
        still_referenced = sess.scalars(
            select(m.RawFile.id).where(m.RawFile.sha256 == digest).limit(1)
        ).first()
        if still_referenced is not None:
            removed.files_kept_shared.append(digest)
            continue
        if store.delete(digest) is not None:
            removed.files_deleted.append(digest)


def nothing_remains(sess: Session, store: FileStore, trader_id: int) -> list[str]:
    """Every place this trader's data is still found. Empty is the point.

    Used by the test suite and by the deletion drill the release gate requires
    (PRD 10, step 3). It asks the database the question the runbook asks a human,
    so the drill checks the same list twice rather than two different ones.
    """
    found: list[str] = []
    for model in (m.ConsentEvent, m.RiskBudgetDeclaration, m.RawFile, m.Import,
                  m.TradingDayVersion, m.Journal, m.WtpAnswer, m.DwellEvent,
                  m.RuleDeclaration, m.AdherenceEvent):
        if sess.scalars(select(model.id)
                        .where(model.trader_id == trader_id).limit(1)).first():
            found.append(model.__tablename__)

    if sess.get(m.Trader, trader_id) is not None:
        found.append("trader")

    journal_ids = _ids(sess, m.Journal.id, m.Journal.trader_id == trader_id)
    if journal_ids and sess.scalars(
        select(m.JournalFieldEntry.id)
        .where(m.JournalFieldEntry.journal_id.in_(journal_ids)).limit(1)
    ).first():
        found.append("journal_field_entry")

    import_ids = _ids(sess, m.Import.id, m.Import.trader_id == trader_id)
    if import_ids:
        for model in (m.Trip, m.OpenPosition, m.SkippedTrip, m.ImportRow):
            if sess.scalars(select(model.id)
                            .where(model.import_id.in_(import_ids))
                            .limit(1)).first():
                found.append(model.__tablename__)
    return found
