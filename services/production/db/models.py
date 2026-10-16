"""The Scope v1 product tables (design section 3).

Two guarantees are enforced here rather than left to discipline:

**Insert-only.** Every table the PRD or the thesis calls versioned, append-only or a
ledger refuses an UPDATE at the session level. A correction is a new row that points
at what it supersedes. The guard is a mapper event, so it fires whether the update
comes from the ORM or from a Core statement.

**No archetype.** PRD section 3 puts archetypes -- as a field, an inference or a
label -- outside v1. A test walks the metadata and asserts no column is named one.

Money is ``DecimalText`` and timestamps are ``AwareDateTime``; both refuse the wrong
type rather than coercing it. ``trading_day`` is an ISO date string in the instrument
profile's timezone, computed once at import and never recomputed from a timestamp
(definitions_v1.md section 1).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from services.production.db.types import AwareDateTime, DecimalText, EnumText
from services.shared.schemas import scope_v1 as s


class InsertOnlyViolation(Exception):
    """An UPDATE against a table whose rows are history. Write a new row instead."""


class Base(DeclarativeBase):
    pass


class _InsertOnly:
    """Marker: rows of this table are never updated (design section 3)."""


class InviteCode(Base):
    __tablename__ = "invite_code"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime)
    redeemed_by: Mapped[int | None] = mapped_column(ForeignKey("trader.id"))
    redeemed_at: Mapped[datetime | None] = mapped_column(AwareDateTime)


class Trader(Base):
    __tablename__ = "trader"
    id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200))
    login_id: Mapped[str] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime | None] = mapped_column(AwareDateTime)
    journal_unit_pref: Mapped[str | None] = mapped_column(String(32))
    journal_unit_n: Mapped[int | None] = mapped_column(Integer)
    deletion_state: Mapped[str | None] = mapped_column(String(32))
    development_data: Mapped[bool] = mapped_column(Boolean, default=False)


class ConsentEvent(Base, _InsertOnly):
    """Thesis 19.3: one row per consent event, with the exact wording shown.

    A withdrawal is a new row with ``granted`` false, never an edit. These rows and
    ``deletion_record`` survive a deletion as legal proof (thesis 19.4).
    """

    __tablename__ = "consent_event"
    id: Mapped[int] = mapped_column(primary_key=True)
    trader_id: Mapped[int] = mapped_column(ForeignKey("trader.id"))
    purpose: Mapped[s.ConsentPurpose] = mapped_column(EnumText(s.ConsentPurpose, 64))
    scope: Mapped[str] = mapped_column(String(64))
    terms_version: Mapped[str] = mapped_column(String(32))
    granted: Mapped[bool] = mapped_column(Boolean)
    at: Mapped[datetime] = mapped_column(AwareDateTime)
    method: Mapped[str] = mapped_column(String(32))
    wording_shown: Mapped[str] = mapped_column(Text)


class RiskBudgetDeclaration(Base, _InsertOnly):
    """PRD 5.5. A percentage requires the capital, or no trip has a denominator."""

    __tablename__ = "risk_budget_declaration"
    id: Mapped[int] = mapped_column(primary_key=True)
    trader_id: Mapped[int] = mapped_column(ForeignKey("trader.id"))
    value: Mapped[Decimal] = mapped_column(DecimalText)
    unit: Mapped[str] = mapped_column(String(8))
    capital_amount: Mapped[Decimal | None] = mapped_column(DecimalText)
    effective_from: Mapped[str] = mapped_column(String(10))
    declared_at: Mapped[datetime] = mapped_column(AwareDateTime)
    retrospective: Mapped[bool] = mapped_column(Boolean, default=False)


class RawFile(Base, _InsertOnly):
    __tablename__ = "raw_file"
    id: Mapped[int] = mapped_column(primary_key=True)
    trader_id: Mapped[int] = mapped_column(ForeignKey("trader.id"))
    sha256: Mapped[str] = mapped_column(String(64))
    original_name: Mapped[str] = mapped_column(Text)
    size: Mapped[int] = mapped_column(Integer)
    stored_path: Mapped[str] = mapped_column(Text)
    uploaded_at: Mapped[datetime] = mapped_column(AwareDateTime)


class Import(Base, _InsertOnly):
    """One upload's outcome and every version that produced it (PRD 5.3, 9)."""

    __tablename__ = "import"
    id: Mapped[int] = mapped_column(primary_key=True)
    trader_id: Mapped[int] = mapped_column(ForeignKey("trader.id"))
    raw_file_id: Mapped[int] = mapped_column(ForeignKey("raw_file.id"))
    source_account: Mapped[str] = mapped_column(String(100))
    export_date: Mapped[str | None] = mapped_column(String(10))
    export_date_source: Mapped[str | None] = mapped_column(String(16))
    adapter_id: Mapped[str] = mapped_column(String(64))
    adapter_version: Mapped[str] = mapped_column(String(32))
    filemap_version: Mapped[str] = mapped_column(String(32))
    profile_versions: Mapped[str | None] = mapped_column(Text)
    code_version: Mapped[str] = mapped_column(String(40))
    snapshot_digest: Mapped[str | None] = mapped_column(String(64))
    outcome: Mapped[s.ImportOutcome] = mapped_column(EnumText(s.ImportOutcome, 32))
    rejection_text: Mapped[str | None] = mapped_column(Text)
    rows_in: Mapped[int] = mapped_column(Integer)
    rows_parsed: Mapped[int] = mapped_column(Integer)
    rows_excluded: Mapped[int] = mapped_column(Integer)
    fees_available: Mapped[bool] = mapped_column(Boolean)
    partial_fields: Mapped[str | None] = mapped_column(Text)
    trips_reconstructed: Mapped[int] = mapped_column(Integer, default=0)
    trips_refused: Mapped[int] = mapped_column(Integer, default=0)
    density_default_unit: Mapped[str | None] = mapped_column(String(32))
    version_no: Mapped[int] = mapped_column(Integer)
    supersedes_import_id: Mapped[int | None] = mapped_column(ForeignKey("import.id"))
    created_at: Mapped[datetime] = mapped_column(AwareDateTime)


class ImportRow(Base, _InsertOnly):
    """Every row of the export, retained. Nothing is dropped silently (PRD 5.4)."""

    __tablename__ = "import_row"
    id: Mapped[int] = mapped_column(primary_key=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("import.id"))
    row_no: Mapped[int] = mapped_column(Integer)
    raw_text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str | None] = mapped_column(Text)
    flag: Mapped[s.RowFlag | None] = mapped_column(EnumText(s.RowFlag, 32))
    dup_group: Mapped[str | None] = mapped_column(String(64))
    fill_id: Mapped[str | None] = mapped_column(String(64))


class TradingDayVersion(Base, _InsertOnly):
    """Uploads version days; they never append to them (PRD 5.4)."""

    __tablename__ = "trading_day_version"
    id: Mapped[int] = mapped_column(primary_key=True)
    trader_id: Mapped[int] = mapped_column(ForeignKey("trader.id"))
    source_account: Mapped[str] = mapped_column(String(100))
    trading_day: Mapped[str] = mapped_column(String(10))
    import_id: Mapped[int] = mapped_column(Integer)
    rows_before: Mapped[int] = mapped_column(Integer)
    rows_after: Mapped[int] = mapped_column(Integer)
    diff: Mapped[s.DayDiff] = mapped_column(EnumText(s.DayDiff, 16))
    day_shrank: Mapped[bool] = mapped_column(Boolean, default=False)
    superseded_by: Mapped[int | None] = mapped_column(Integer)


class Trip(Base, _InsertOnly):
    __tablename__ = "trip"
    id: Mapped[int] = mapped_column(primary_key=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("import.id"))
    trip_id: Mapped[str] = mapped_column(String(64))
    trading_day: Mapped[str] = mapped_column(String(10))
    exchange: Mapped[str | None] = mapped_column(String(16))
    symbol: Mapped[str | None] = mapped_column(String(64))
    segment: Mapped[str | None] = mapped_column(String(8))
    direction: Mapped[str | None] = mapped_column(String(8))
    entry_ts: Mapped[datetime | None] = mapped_column(AwareDateTime)
    exit_ts: Mapped[datetime | None] = mapped_column(AwareDateTime)
    quantity: Mapped[int | None] = mapped_column(Integer)
    entry_price: Mapped[Decimal | None] = mapped_column(DecimalText)
    exit_price: Mapped[Decimal | None] = mapped_column(DecimalText)
    gross: Mapped[Decimal] = mapped_column(DecimalText)
    fees: Mapped[Decimal] = mapped_column(DecimalText)
    net: Mapped[Decimal] = mapped_column(DecimalText)
    fees_available: Mapped[bool] = mapped_column(Boolean)
    ctr_risk_source: Mapped[str | None] = mapped_column(String(32))
    risk_unit_value: Mapped[Decimal | None] = mapped_column(DecimalText)
    risk_unit_source: Mapped[s.RiskUnitSourceV1] = mapped_column(EnumText(s.RiskUnitSourceV1, 32))
    risk_budget_ref: Mapped[int | None] = mapped_column(
        ForeignKey("risk_budget_declaration.id")
    )
    __table_args__ = (UniqueConstraint("import_id", "trip_id"),)


class OpenPosition(Base, _InsertOnly):
    __tablename__ = "open_position"
    id: Mapped[int] = mapped_column(primary_key=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("import.id"))
    description: Mapped[str] = mapped_column(Text)


class SkippedTrip(Base, _InsertOnly):
    __tablename__ = "skipped_trip"
    id: Mapped[int] = mapped_column(primary_key=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("import.id"))
    reason: Mapped[str] = mapped_column(Text)
    detail: Mapped[str | None] = mapped_column(Text)


class Journal(Base, _InsertOnly):
    """Immutable once written; a correction is a new version (PRD 7.2)."""

    __tablename__ = "journal"
    id: Mapped[int] = mapped_column(primary_key=True)
    trader_id: Mapped[int] = mapped_column(ForeignKey("trader.id"))
    import_id: Mapped[int] = mapped_column(ForeignKey("import.id"))
    unit: Mapped[s.JournalUnit] = mapped_column(EnumText(s.JournalUnit, 32))
    period_start: Mapped[str] = mapped_column(String(10))
    period_end: Mapped[str] = mapped_column(String(10))
    version_no: Mapped[int] = mapped_column(Integer)
    supersedes: Mapped[int | None] = mapped_column(Integer)
    generated_at: Mapped[datetime] = mapped_column(AwareDateTime)
    opened_at: Mapped[datetime | None] = mapped_column(AwareDateTime)
    trip_ids: Mapped[str] = mapped_column(Text)
    sections: Mapped[str] = mapped_column(Text)


class JournalFieldEntry(Base, _InsertOnly):
    """PRD 7.4: capture_phase is derived from entered_at, never chosen."""

    __tablename__ = "journal_field_entry"
    id: Mapped[int] = mapped_column(primary_key=True)
    journal_id: Mapped[int] = mapped_column(ForeignKey("journal.id"))
    trip_id: Mapped[str | None] = mapped_column(String(64))
    field: Mapped[str] = mapped_column(String(32))
    value: Mapped[str | None] = mapped_column(Text)
    entered_at: Mapped[datetime] = mapped_column(AwareDateTime)
    capture_phase: Mapped[s.CapturePhase] = mapped_column(EnumText(s.CapturePhase, 32))
    previous_entry_id: Mapped[int | None] = mapped_column(Integer)


class WtpAnswer(Base, _InsertOnly):
    __tablename__ = "wtp_answer"
    id: Mapped[int] = mapped_column(primary_key=True)
    trader_id: Mapped[int] = mapped_column(ForeignKey("trader.id"))
    journal_id: Mapped[int] = mapped_column(ForeignKey("journal.id"))
    answer: Mapped[str] = mapped_column(String(16))
    free_text: Mapped[str | None] = mapped_column(Text)
    uploads_so_far: Mapped[int] = mapped_column(Integer)
    days_since_first_upload: Mapped[int] = mapped_column(Integer)
    asked_at: Mapped[datetime] = mapped_column(AwareDateTime)


class DwellEvent(Base, _InsertOnly):
    __tablename__ = "dwell_event"
    id: Mapped[int] = mapped_column(primary_key=True)
    trader_id: Mapped[int] = mapped_column(ForeignKey("trader.id"))
    surface: Mapped[str] = mapped_column(String(32))
    key: Mapped[str] = mapped_column(String(64))
    event: Mapped[str] = mapped_column(String(32))
    at: Mapped[datetime] = mapped_column(AwareDateTime)
    duration_ms: Mapped[int | None] = mapped_column(Integer)


class RuleDeclaration(Base, _InsertOnly):
    """Captured, unused in v1. Collecting from day one is free (PRD 9)."""

    __tablename__ = "rule_declaration"
    id: Mapped[int] = mapped_column(primary_key=True)
    trader_id: Mapped[int] = mapped_column(ForeignKey("trader.id"))
    text: Mapped[str] = mapped_column(Text)
    declared_at: Mapped[datetime] = mapped_column(AwareDateTime)


class AdherenceEvent(Base, _InsertOnly):
    __tablename__ = "adherence_event"
    id: Mapped[int] = mapped_column(primary_key=True)
    trader_id: Mapped[int] = mapped_column(ForeignKey("trader.id"))
    rule_declaration_id: Mapped[int | None] = mapped_column(Integer)
    observed_at: Mapped[datetime] = mapped_column(AwareDateTime)
    detail: Mapped[str | None] = mapped_column(Text)


class DeletionRecord(Base, _InsertOnly):
    """Survives the deletion it records (thesis 19.4)."""

    __tablename__ = "deletion_record"
    id: Mapped[int] = mapped_column(primary_key=True)
    trader_id: Mapped[int] = mapped_column(Integer)
    requested_at: Mapped[datetime] = mapped_column(AwareDateTime)
    completed_at: Mapped[datetime | None] = mapped_column(AwareDateTime)
    what_removed: Mapped[str | None] = mapped_column(Text)
    what_retained: Mapped[str | None] = mapped_column(Text)
    locations_checked: Mapped[str | None] = mapped_column(Text)


class AdminAction(Base, _InsertOnly):
    """Thesis 19.1: least-privilege access with an audit log."""

    __tablename__ = "admin_action"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(64))
    target: Mapped[str | None] = mapped_column(String(200))
    at: Mapped[datetime] = mapped_column(AwareDateTime)


INSERT_ONLY_TABLES = frozenset(
    mapper.class_.__tablename__
    for mapper in Base.registry.mappers
    if issubclass(mapper.class_, _InsertOnly)
)


def install_insert_only_guard(session_class: type) -> None:
    """Refuse any UPDATE against an insert-only table, ORM or Core.

    A ``before_update`` mapper hook would miss ``session.execute(update(...))``, which
    is how a bulk correction would most likely be written, so the guard sits on the
    session's execute path where every statement passes.
    """

    @event.listens_for(session_class, "do_orm_execute")
    def _refuse_update(state: Any) -> None:
        if not state.is_update:
            return
        name = getattr(getattr(state.statement, "table", None), "name", None)
        if name in INSERT_ONLY_TABLES:
            raise InsertOnlyViolation(
                f"{name} is insert-only: write a new row that supersedes this "
                "one (design section 3)"
            )

    @event.listens_for(session_class, "before_flush")
    def _refuse_dirty(session: Any, _ctx: Any, _instances: Any) -> None:
        for obj in session.dirty:
            if isinstance(obj, _InsertOnly) and session.is_modified(obj):
                raise InsertOnlyViolation(
                    f"{type(obj).__tablename__} is insert-only: write a new row that "
                    "supersedes this one (design section 3)"
                )
