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

from sqlalchemy import select
from sqlalchemy.orm import Session

from services.production.ctr.intake.pipeline import ImportPlan
from services.production.db import models as m
from services.shared.schemas import scope_v1 as s


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


def _next_version(sess: Session, trader: m.Trader) -> tuple[int, int | None]:
    previous = sess.scalars(
        select(m.Import)
        .where(m.Import.trader_id == trader.id)
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
) -> m.Import:
    """Write the plan and return the import row it produced."""
    now = datetime.now(UTC)

    raw = m.RawFile(
        trader_id=trader.id,
        sha256=raw_sha256,
        original_name=original_name,
        size=size,
        stored_path=stored_path,
        uploaded_at=now,
    )
    sess.add(raw)
    sess.flush()

    version_no, supersedes = _next_version(sess, trader)

    imp = m.Import(
        trader_id=trader.id,
        raw_file_id=raw.id,
        source_account=source_account,
        export_date=plan.export_date,
        export_date_source=plan.export_date_source,
        adapter_id=plan.adapter_id or "",
        adapter_version=plan.adapter_version or "",
        filemap_version=plan.filemap_version or "",
        profile_versions=json.dumps(plan.profile_versions, sort_keys=True),
        code_version=plan.code_version,
        snapshot_digest=plan.digest(),
        outcome=plan.outcome,
        rejection_text=plan.rejection_text,
        rows_in=plan.rows_in,
        rows_parsed=plan.rows_parsed,
        rows_excluded=plan.rows_excluded,
        fees_available=plan.fees_available,
        partial_fields=json.dumps(list(plan.missing_fields)),
        trips_reconstructed=len(plan.trips),
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

    for trip in plan.trips:
        sess.add(
            m.Trip(
                import_id=imp.id,
                trip_id=trip.trip_id,
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
                risk_unit_value=trip.risk_unit,
                risk_unit_source=(
                    s.RiskUnitSourceV1.PREMIUM_PAID
                    if trip.risk_unit is not None
                    else s.RiskUnitSourceV1.UNAVAILABLE
                ),
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
