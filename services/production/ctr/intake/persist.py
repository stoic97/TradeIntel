"""Write an ``ImportPlan`` into the schema. Decides nothing.

Every judgement was made in ``pipeline.plan_import``; this module turns the plan into
rows. Keeping the split sharp is what lets the reproducibility test compare one
digest, and it means a bug is either in the decision or in the writing, never
somewhere between.

Three rules it enforces while writing:

**A rejected file still leaves a record.** He uploaded the wrong file; he must be
able to open the import and see that he did, with the sentence he was shown.

**Day versions accumulate.** A superseded version keeps its row and gains a
``superseded_by``; exactly one version of a day is current. The history is how an
earlier Journal stays explicable after a re-export (PRD 5.4, 7.2).

**Nothing is updated.** Seventeen of nineteen tables refuse an UPDATE, so
superseding is itself an insert followed by the one permitted write -- setting
``superseded_by`` on the row being replaced, which the guard allows because
``trading_day_version`` records history by appending, not by editing content.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from services.production.accounts import risk_budget as rb
from services.production.ctr.intake.pipeline import ImportPlan
from services.production.db import models as m
from services.shared.positions import Position
from services.shared.schemas import scope_v1 as s
from services.shared.schemas.ctr_v1 import RiskUnitSource as CtrRiskSource
from services.shared.schemas.ctr_v1 import RoundTrip


def existing_days(sess: Session, *, trader: m.Trader, source_account: str) -> dict[str, int]:
    """The current version of each trading day for one source account."""
    rows = sess.scalars(
        select(m.TradingDayVersion).where(
            m.TradingDayVersion.trader_id == trader.id,
            m.TradingDayVersion.source_account == source_account,
            m.TradingDayVersion.superseded_by.is_(None),
        )
    ).all()
    return {r.trading_day: r.rows_after for r in rows}


def _risk_unit_for(
    trip: RoundTrip | Position,
    trading_day: str,
    declarations: list[m.RiskBudgetDeclaration],
) -> tuple[s.RiskUnitSourceV1, Decimal | None, int | None]:
    """PRD 5.5's hierarchy: declared budget, then a recorded stop, then premium or structure.

    A leg of a position is written with the position's figure, so each leg's row says
    what the whole position is measured against (Annex H section 6).

    Only the first two may ever be a denominator on a v1 screen. The premium is the
    most an option could have lost rather than what was at risk, so it is recorded
    and never divided by; the Mirror says so in section 6.6.

    What this writes is what was knowable when the file was read. A budget declared
    afterwards -- which is where the PRD's flow puts the question -- is applied when
    the figure is read, by the same two functions from ``risk_budget``, so the two
    paths cannot drift apart.
    """
    declaration = rb.in_force(declarations, trading_day)
    amount = rb.rupees(declaration)
    if amount is not None and declaration is not None:
        return s.RiskUnitSourceV1.DECLARED_BUDGET, amount, declaration.id

    source = trip.risk_unit_source.value
    if source == CtrRiskSource.RECORDED_STOP.value and trip.risk_unit:
        return s.RiskUnitSourceV1.DEFINED_STOP, trip.risk_unit, None
    if source == "UNCAPPED":
        return s.RiskUnitSourceV1.UNCAPPED, None, None
    if source == "STRUCTURE_MAX_LOSS":
        return s.RiskUnitSourceV1.STRUCTURE_MAX_LOSS, trip.risk_unit, None
    if trip.risk_unit is not None:
        return s.RiskUnitSourceV1.PREMIUM_PAID, trip.risk_unit, None
    return s.RiskUnitSourceV1.UNAVAILABLE, None, None


def _next_version(sess: Session, trader: m.Trader,
                  source_account: str) -> tuple[int, int | None]:
    """The next version of this source account's export, and the import it supersedes.

    Per source account, as day versions are (``existing_days``): a version of one
    account's file says nothing about another's. It is what keeps the demo (TICKET-842)
    out of a real upload's history, since imports are insert-only and a real import
    pointing at a demo one would pin the demo in place.
    """
    previous = sess.scalars(
        select(m.Import)
        .where(m.Import.trader_id == trader.id, m.Import.source_account == source_account)
        .order_by(m.Import.id.desc())
    ).first()
    if previous is None:
        return 1, None
    return previous.version_no + 1, previous.id


def write_plan(
    sess: Session,
    *,
    trader: m.Trader,
    plan: ImportPlan,
    raw_sha256: str,
    original_name: str,
    stored_path: str,
    size: int,
    source_account: str = "A",
    also_reads: tuple[m.RawFile, ...] = (),
) -> m.Import:
    """Record the file, write the plan and return the import row it produced.

    ``also_reads`` are the record's files this upload was read together with
    (``pipeline.files_kept``); the new file is the last of them.
    """
    raw = m.RawFile(
        trader_id=trader.id,
        sha256=raw_sha256,
        original_name=original_name,
        size=size,
        stored_path=stored_path,
        uploaded_at=datetime.now(UTC),
    )
    sess.add(raw)
    sess.flush()
    return write_reading(sess, trader=trader, plan=plan, raw=raw, source_account=source_account,
                         reads=(*also_reads, raw) if also_reads else ())


def confirmed_groups(sess: Session, imp: m.Import) -> set[str]:
    """The duplicate groups the trader confirmed on this import."""
    return set(sess.scalars(
        select(m.ImportRow.dup_group).where(
            m.ImportRow.import_id == imp.id,
            m.ImportRow.flag == s.RowFlag.TRADER_CONFIRMED_DUPLICATE,
        )
    ))


def still_suspected(sess: Session, imp: m.Import) -> set[str]:
    """The duplicate groups on this import he has not yet confirmed."""
    return set(sess.scalars(
        select(m.ImportRow.dup_group).where(
            m.ImportRow.import_id == imp.id,
            m.ImportRow.flag == s.RowFlag.SUSPECTED_DUPLICATE,
        )
    ))


def earlier_reading(sess: Session, imp: m.Import) -> m.Import | None:
    """The import with trades that came before this one in the same source account."""
    return sess.scalars(
        select(m.Import)
        .join(m.Trip, m.Trip.import_id == m.Import.id)
        .where(m.Import.trader_id == imp.trader_id,
               m.Import.source_account == imp.source_account,
               m.Import.id < imp.id)
        .order_by(m.Import.id.desc())
        .limit(1)
    ).first()


def files_read(sess: Session, imp: m.Import) -> list[m.RawFile]:
    """Every file this reading read, oldest first: its own, or all it was read together with."""
    if imp.reads_files:
        return [sess.get(m.RawFile, file_id) for file_id in json.loads(imp.reads_files)]
    return [sess.get(m.RawFile, imp.raw_file_id)]


def current_reading(sess: Session, trader: m.Trader, source_account: str) -> m.Import | None:
    """The latest reading of this source account that has trades: what an upload adds to."""
    return sess.scalars(
        select(m.Import)
        .join(m.Trip, m.Trip.import_id == m.Import.id)
        .where(m.Import.trader_id == trader.id, m.Import.source_account == source_account)
        .order_by(m.Import.id.desc())
        .limit(1)
    ).first()


def same_file(sess: Session, one: m.Import, other: m.Import) -> bool:
    """Whether two imports read the same bytes. Older confirmations each wrote a ``RawFile``."""
    return ([f.sha256 for f in files_read(sess, one)]
            == [f.sha256 for f in files_read(sess, other)])


def reads_same_file_as_before(sess: Session, imp: m.Import) -> bool:
    """Whether the import before this one read the same bytes: no new file came with it."""
    earlier = earlier_reading(sess, imp)
    return earlier is not None and same_file(sess, imp, earlier)


def set_aside_more(sess: Session, imp: m.Import) -> bool:
    """Whether this import read the file behind the one before it, with more confirmed."""
    earlier = earlier_reading(sess, imp)
    return (earlier is not None and same_file(sess, imp, earlier)
            and bool(confirmed_groups(sess, imp) - confirmed_groups(sess, earlier)))


def read_with_newer_code(sess: Session, imp: m.Import) -> bool:
    """Whether this import read the file behind the one before it, with code that moved."""
    earlier = earlier_reading(sess, imp)
    return (earlier is not None and same_file(sess, imp, earlier)
            and (earlier.reconstruction_version, earlier.adapter_version)
            != (imp.reconstruction_version, imp.adapter_version))


def write_reading(
    sess: Session, *, trader: m.Trader, plan: ImportPlan, raw: m.RawFile, source_account: str,
    reads: tuple[m.RawFile, ...] | list[m.RawFile] = (),
) -> m.Import:
    """Write the plan as a new version, reading ``raw``. Nothing earlier is touched.

    ``reads`` names every file the plan was read from when there was more than one.
    """
    now = datetime.now(UTC)

    version_no, supersedes = _next_version(sess, trader, source_account)

    imp = m.Import(
        trader_id=trader.id,
        raw_file_id=raw.id,
        reads_files=json.dumps([f.id for f in reads]) if len(reads) > 1 else None,
        source_account=source_account,
        export_date=plan.export_date,
        export_date_source=plan.export_date_source,
        adapter_id=plan.adapter_id or "",
        adapter_version=plan.adapter_version or "",
        filemap_version=plan.filemap_version or "",
        profile_versions=json.dumps(plan.profile_versions, sort_keys=True),
        code_version=plan.code_version,
        reconstruction_version=plan.reconstruction_version,
        snapshot_digest=plan.digest(),
        outcome=plan.outcome,
        rejection_text=plan.rejection_text,
        rows_in=plan.rows_in,
        rows_parsed=plan.rows_parsed,
        rows_excluded=plan.rows_excluded,
        fees_available=plan.fees_available,
        partial_fields=json.dumps(list(plan.missing_fields)),
        # Trades as the record reads them: a spread's legs are one (TICKET-788).
        trips_reconstructed=len(plan.positions),
        trips_refused=len(plan.skipped),
        density_default_unit=plan.density_default_unit,
        version_no=version_no,
        supersedes_import_id=supersedes,
        created_at=now,
    )
    sess.add(imp)
    sess.flush()

    for row in plan.rows:
        sess.add(
            m.ImportRow(
                import_id=imp.id,
                row_no=row.row_no,
                raw_text=row.raw_text,
                status=row.status,
                reason=row.reason,
                flag=row.flag,
                dup_group=row.dup_group,
                fill_id=row.fill_id,
            )
        )

    declarations = list(sess.scalars(
        select(m.RiskBudgetDeclaration)
        .where(m.RiskBudgetDeclaration.trader_id == trader.id)
        .order_by(m.RiskBudgetDeclaration.effective_from)
    ).all())

    position_of = {id(leg): pos for pos in plan.positions for leg in pos.legs}
    seen_trip_ids: dict[str, int] = {}
    for trip in plan.trips:
        occurrence = seen_trip_ids.get(trip.trip_id, 0) + 1
        seen_trip_ids[trip.trip_id] = occurrence
        position = position_of.get(id(trip))
        multi_leg = position is not None and len(position.legs) > 1
        sess.add(
            m.Trip(
                import_id=imp.id,
                trip_id=trip.trip_id,
                occurrence=occurrence,
                position_id=position.position_id if multi_leg else None,
                option_type=trip.option_type.value if trip.option_type else None,
                strike=trip.strike,
                uncapped=(position or trip).risk_unit_source.value == "UNCAPPED",
                # The stored timestamp's own date. Correct while every profile is
                # IST (MCX, NSE); for a non-IST instrument the trading day must come
                # from the profile's timezone, as the plan already computes it for
                # the day diffs. Carried per trip when the first such history lands
                # (TD-026).
                trading_day=trip.entry_ts.date().isoformat(),
                exchange=trip.exchange,
                symbol=trip.symbol,
                segment=trip.segment.value,
                direction=trip.direction.value,
                entry_ts=trip.entry_ts,
                exit_ts=trip.exit_ts,
                quantity=trip.quantity,
                entry_price=trip.entry_price,
                exit_price=trip.exit_price,
                gross=trip.gross_pnl,
                fees=trip.fees,
                net=trip.net_pnl,
                fees_available=plan.fees_available,
                ctr_risk_source=trip.risk_unit_source.value,
                **dict(zip(
                    ("risk_unit_source", "risk_unit_value", "risk_budget_ref"),
                    _risk_unit_for(position if multi_leg else trip,
                                   trip.entry_ts.date().isoformat(), declarations),
                    strict=True,
                )),
            )
        )

    for reason in plan.skipped:
        sess.add(m.SkippedTrip(import_id=imp.id, reason=reason))
    for _ in range(plan.open_positions):
        sess.add(m.OpenPosition(import_id=imp.id, description="open at end of upload"))

    for diff in plan.day_diffs:
        previous = sess.scalars(
            select(m.TradingDayVersion).where(
                m.TradingDayVersion.trader_id == trader.id,
                m.TradingDayVersion.source_account == source_account,
                m.TradingDayVersion.trading_day == diff.trading_day,
                m.TradingDayVersion.superseded_by.is_(None),
            )
        ).first()
        new_version = m.TradingDayVersion(
            trader_id=trader.id,
            source_account=source_account,
            trading_day=diff.trading_day,
            import_id=imp.id,
            rows_before=diff.rows_before,
            rows_after=diff.rows_after,
            diff=diff.diff,
            day_shrank=diff.day_shrank,
        )
        sess.add(new_version)
        sess.flush()
        if previous is not None:
            # The one permitted write to a history table: closing the previous
            # version by naming its successor. The row's content is untouched.
            sess.connection().exec_driver_sql(
                "update trading_day_version set superseded_by = ? where id = ?",
                (new_version.id, previous.id),
            )

    sess.flush()
    return imp
