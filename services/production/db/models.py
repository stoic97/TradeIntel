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
    # Every raw file this reading read, oldest first, as a JSON list of ids, when it read
    # more than one (a Groww trader's stocks and F&O files). Empty: ``raw_file_id`` alone.
    reads_files: Mapped[str | None] = mapped_column(Text)
    source_account: Mapped[str] = mapped_column(String(100))
    export_date: Mapped[str | None] = mapped_column(String(10))
    export_date_source: Mapped[str | None] = mapped_column(String(16))
    adapter_id: Mapped[str] = mapped_column(String(64))
    adapter_version: Mapped[str] = mapped_column(String(32))
    filemap_version: Mapped[str] = mapped_column(String(32))
    profile_versions: Mapped[str | None] = mapped_column(Text)
    code_version: Mapped[str] = mapped_column(String(40))
    # Empty means read before this was recorded, so older than any current reading.
    reconstruction_version: Mapped[str | None] = mapped_column(String(32))
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
    position_id: Mapped[str | None] = mapped_column(String(64))
    """The position this leg is part of, when it has more than one leg (Annex H). Null
    is a position of its own, which is every trip of an import made before Annex H."""
    option_type: Mapped[str | None] = mapped_column(String(2))
    strike: Mapped[Decimal | None] = mapped_column(DecimalText)
    uncapped: Mapped[bool | None] = mapped_column(Boolean)
    """Whether its position can lose without limit. Kept apart from risk_unit_source, which
    says what it is measured against: a budget changes that, and does not cap the loss."""
    occurrence: Mapped[int] = mapped_column(Integer, default=1)
    """Which occurrence of an identical trip this is, within one import.

    trip_id is a content hash (ctr_v1), so two genuinely identical trades -- the same
    contract, direction, times, quantity and prices -- share one. That happens when a
    trader repeats a trade and when a file repeats a block, and PRD 5.4 forbids
    dropping either. The constraint stays, widened by this column: identical trips
    are distinguishable rows, while writing the same occurrence twice still collides.
    """

    __table_args__ = (UniqueConstraint("import_id", "trip_id", "occurrence"),)


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


class WtpAsked(Base, _InsertOnly):
    """Which Journal the willingness-to-pay question was put on. It is asked there and nowhere
    else: this row is the "asked once" flag, written when the question is first drawn."""

    __tablename__ = "wtp_asked"
    id: Mapped[int] = mapped_column(primary_key=True)
    trader_id: Mapped[int] = mapped_column(ForeignKey("trader.id"), unique=True)
    journal_id: Mapped[int] = mapped_column(ForeignKey("journal.id"))
    asked_at: Mapped[datetime] = mapped_column(AwareDateTime)


class ChapterFeedback(Base, _InsertOnly):
    """B4: "Does this match your trading?" under chapters 1-3 (handoff 9).

    One answer per chapter per trader: the unique constraint holds it, so a second
    tap cannot quietly become a second vote. The import is the record he was
    looking at when he answered, so an answer can be read against the figures it
    was about.
    """

    __tablename__ = "chapter_feedback"
    __table_args__ = (UniqueConstraint("trader_id", "chapter"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    trader_id: Mapped[int] = mapped_column(ForeignKey("trader.id"))
    chapter: Mapped[int] = mapped_column(Integer)
    answer: Mapped[str] = mapped_column(String(16))
    import_id: Mapped[int] = mapped_column(ForeignKey("import.id"))
    answered_at: Mapped[datetime] = mapped_column(AwareDateTime)


class ChapterFeedbackReason(Base, _InsertOnly):
    """The optional reason after "Wrong" - its own row, because it comes later and
    an answer is never edited. At most one per answer."""

    __tablename__ = "chapter_feedback_reason"
    id: Mapped[int] = mapped_column(primary_key=True)
    feedback_id: Mapped[int] = mapped_column(ForeignKey("chapter_feedback.id"), unique=True)
    reason: Mapped[str] = mapped_column(String(32))
    given_at: Mapped[datetime] = mapped_column(AwareDateTime)


class ReportFeedback(Base, _InsertOnly):
    """TICKET-825: "Does this match your trading?" about a whole report, with a note.

    One route for what a trader says is wrong: trading_day is empty for the whole
    report and is there for TICKET-817's "Is this day wrong?". One answer per report,
    so a new upload, being a new report, asks again.
    """

    __tablename__ = "report_feedback"
    __table_args__ = (UniqueConstraint("trader_id", "import_id", "trading_day"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    trader_id: Mapped[int] = mapped_column(ForeignKey("trader.id"))
    import_id: Mapped[int] = mapped_column(ForeignKey("import.id"))
    trading_day: Mapped[str] = mapped_column(String(10), default="")
    answer: Mapped[str] = mapped_column(String(16))
    note: Mapped[str | None] = mapped_column(Text)
    answered_at: Mapped[datetime] = mapped_column(AwareDateTime)


class GuessAnswer(Base, _InsertOnly):
    """B6: the trader's guess, before the reveal shows him his five worst days.

    One per trader, ever: a guess made after seeing the answer is not a guess. The
    label is one of the frozen set (TR-009) or "unknown" for "I don't know". The
    import is the record the reveal then showed him.
    """

    __tablename__ = "guess_answer"
    id: Mapped[int] = mapped_column(primary_key=True)
    trader_id: Mapped[int] = mapped_column(ForeignKey("trader.id"), unique=True)
    answer: Mapped[str] = mapped_column(String(32))
    labels_version: Mapped[str] = mapped_column(String(32))
    import_id: Mapped[int] = mapped_column(ForeignKey("import.id"))
    answered_at: Mapped[datetime] = mapped_column(AwareDateTime)


class LeavingCardShown(Base, _InsertOnly):
    """B7: that the leaving card was shown to this trader. It is shown once, ever:
    this row is the "shown once" flag, written when the card is drawn, so a card he
    scrolls past is not shown again."""

    __tablename__ = "leaving_card_shown"
    id: Mapped[int] = mapped_column(primary_key=True)
    trader_id: Mapped[int] = mapped_column(ForeignKey("trader.id"), unique=True)
    copy_version: Mapped[str] = mapped_column(String(32))
    shown_at: Mapped[datetime] = mapped_column(AwareDateTime)


class LeavingCardAnswer(Base, _InsertOnly):
    """B7: what he did with the leaving card - his answer in his own words, or
    "Not now". One per trader, never edited. The words are his, so deletion takes
    them with everything else."""

    __tablename__ = "leaving_card_answer"
    id: Mapped[int] = mapped_column(primary_key=True)
    trader_id: Mapped[int] = mapped_column(ForeignKey("trader.id"), unique=True)
    outcome: Mapped[str] = mapped_column(String(16))  # answered | dismissed
    answer: Mapped[str | None] = mapped_column(Text)
    copy_version: Mapped[str] = mapped_column(String(32))
    answered_at: Mapped[datetime] = mapped_column(AwareDateTime)


class JournalRememberAnswer(Base, _InsertOnly):
    """TICKET-906: his answer to "Do you remember this day?", with the day's age.

    One per trader per trading day, never edited: the first stands, so a later version of
    that day's Journal does not ask again. A fixed answer, yes or no, counted - never a
    typed word, so consent v1 is untouched. The day's age (calendar days from the trading
    day to the answer, in IST) is what lets NEW_DAY_WITHIN_DAYS be checked against what
    traders say. Deletion takes it with everything else of his.
    """

    __tablename__ = "journal_remember_answer"
    __table_args__ = (UniqueConstraint("trader_id", "trading_day"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    trader_id: Mapped[int] = mapped_column(ForeignKey("trader.id"))
    journal_id: Mapped[int] = mapped_column(ForeignKey("journal.id"))
    trading_day: Mapped[str] = mapped_column(String(10))
    answer: Mapped[str] = mapped_column(String(3))
    day_age_days: Mapped[int] = mapped_column(Integer)
    answered_at: Mapped[datetime] = mapped_column(AwareDateTime)


class DwellEvent(Base, _InsertOnly):
    __tablename__ = "dwell_event"
    id: Mapped[int] = mapped_column(primary_key=True)
    trader_id: Mapped[int] = mapped_column(ForeignKey("trader.id"))
    surface: Mapped[str] = mapped_column(String(32))
    key: Mapped[str] = mapped_column(String(64))
    event: Mapped[str] = mapped_column(String(32))
    at: Mapped[datetime] = mapped_column(AwareDateTime)
    duration_ms: Mapped[int | None] = mapped_column(Integer)


class ChargeStatement(Base, _InsertOnly):
    """A second file, the broker's own charges by day (TICKET-828). Kept apart from the
    trips: ``trip.fees`` and ``fees_available`` go on saying what the tradebook said."""

    __tablename__ = "charge_statement"
    id: Mapped[int] = mapped_column(primary_key=True)
    trader_id: Mapped[int] = mapped_column(ForeignKey("trader.id"))
    raw_file_id: Mapped[int] = mapped_column(ForeignKey("raw_file.id"))
    reader: Mapped[str] = mapped_column(String(64))
    days: Mapped[str] = mapped_column(Text)  # JSON: trading day -> amount, as a string
    uploaded_at: Mapped[datetime] = mapped_column(AwareDateTime)


class RuleDeclaration(Base, _InsertOnly):
    """A rule the trader set, by tapping, dated before it is tested (TICKET-922).

    ``factor`` and ``value`` are chips from ``rules.chips``; ``text`` keeps the rule's
    words as they read when he set it. Never updated: a newer one governs only the
    trades after it. ``applies_from``/``applies_to`` are India dates; one day for a
    before-the-session commitment, open-ended for a standing rule.
    """

    __tablename__ = "rule_declaration"
    id: Mapped[int] = mapped_column(primary_key=True)
    trader_id: Mapped[int] = mapped_column(ForeignKey("trader.id"))
    text: Mapped[str] = mapped_column(Text)
    declared_at: Mapped[datetime] = mapped_column(AwareDateTime)
    factor: Mapped[str | None] = mapped_column(String(32))
    value: Mapped[int | None] = mapped_column(Integer)
    applies_from: Mapped[str | None] = mapped_column(String(10))
    applies_to: Mapped[str | None] = mapped_column(String(10))
    screen: Mapped[str | None] = mapped_column(String(32))


class Challenge(Base):
    """A challenge he set himself: 10 or 20 exchange trading days and one to three
    of the rules he set. Written once when he starts it; only how it ended and his share link
    change after that, so it is not insert-only. ``rule_ids`` is a JSON list of
    ``rule_declaration`` ids; ``start_day`` an India date."""

    __tablename__ = "challenge"
    id: Mapped[int] = mapped_column(primary_key=True)
    trader_id: Mapped[int] = mapped_column(ForeignKey("trader.id"))
    rule_ids: Mapped[str] = mapped_column(Text)
    length: Mapped[int] = mapped_column(Integer)
    start_day: Mapped[str] = mapped_column(String(10))
    started_at: Mapped[datetime] = mapped_column(AwareDateTime)
    ended_at: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)
    ended_how: Mapped[str | None] = mapped_column(String(16), nullable=True)
    share_token: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)


class PreTradeNote(Base, _InsertOnly):
    """Two taps before a click: the book and the reason, matched to a fill on upload."""

    __tablename__ = "pre_trade_note"
    id: Mapped[int] = mapped_column(primary_key=True)
    trader_id: Mapped[int] = mapped_column(ForeignKey("trader.id"))
    book: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(String(32))
    entered_at: Mapped[datetime] = mapped_column(AwareDateTime)


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


class MarketToken(Base):
    """The day's Fyers token, one row (TICKET-998). It can place orders, so only its Fernet
    ciphertext is kept, under the file key; the sync is the one reader that decrypts it. A new
    login replaces the row. No trader's data: the admin who connected is ``trader:<id>``, as the
    admin trail writes it."""

    __tablename__ = "market_token"
    id: Mapped[int] = mapped_column(primary_key=True)
    ciphertext: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(AwareDateTime)
    connected_at: Mapped[datetime] = mapped_column(AwareDateTime)
    connected_by: Mapped[str] = mapped_column(String(100))


class MarketSyncRun(Base, _InsertOnly):
    """One run of ``cli market-sync`` (TICKET-998): its result, and per underlying the days it
    added and refused, as counts, dates and reasons. Never a price."""

    __tablename__ = "market_sync_run"
    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(AwareDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(AwareDateTime)
    result: Mapped[str] = mapped_column(String(32))
    summary: Mapped[str] = mapped_column(Text)


class MarketDayRequest(Base):
    """A stock's trading day that a trader's trades need and the store lacks (TICKET-998). The
    sync fetches it; one Fyers won't serve is given up after three tries, with the reason. It names
    a stock and a day, never a trader, so a deletion leaves it: it holds nothing of his."""

    __tablename__ = "market_day_request"
    __table_args__ = (UniqueConstraint("underlying", "trading_day"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    underlying: Mapped[str] = mapped_column(String(40))
    trading_day: Mapped[str] = mapped_column(String(10))
    requested_at: Mapped[datetime] = mapped_column(AwareDateTime)
    status: Mapped[str] = mapped_column(String(16))
    tries: Mapped[int] = mapped_column(Integer, default=0)
    reason: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime | None] = mapped_column(AwareDateTime)


class BarFigureJob(Base):
    """One import's bar figures, to be worked out off the web app (TICKET-999). The upload adds it
    as pending, a cheap insert; ``cli bar-figures`` works it out, leaves it waiting while a day it
    needs isn't in, and marks it done. ``provenance`` names the code and every day file read."""

    __tablename__ = "bar_figure_job"
    id: Mapped[int] = mapped_column(primary_key=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("import.id"), unique=True)
    trader_id: Mapped[int] = mapped_column(ForeignKey("trader.id"))
    state: Mapped[str] = mapped_column(String(16))
    waiting_days: Mapped[int] = mapped_column(Integer, default=0)
    requested_at: Mapped[datetime] = mapped_column(AwareDateTime)
    updated_at: Mapped[datetime | None] = mapped_column(AwareDateTime)
    provenance: Mapped[str | None] = mapped_column(Text)


class BarTradeFigure(Base):
    """One trade's bar figures (TICKET-999), in underlying points in its direction, or the reason
    it has none. Points are Decimal text; ``path`` is the 30 minutes after he clicked, as JSON."""

    __tablename__ = "bar_trade_figure"
    id: Mapped[int] = mapped_column(primary_key=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("import.id"))
    trip_id: Mapped[str] = mapped_column(String(64))
    underlying: Mapped[str | None] = mapped_column(String(40))
    reason: Mapped[str | None] = mapped_column(Text)
    way: Mapped[str | None] = mapped_column(String(32))
    against: Mapped[str | None] = mapped_column(String(32))
    took: Mapped[str | None] = mapped_column(String(32))
    path: Mapped[str | None] = mapped_column(Text)
    short: Mapped[bool] = mapped_column(Boolean, default=False)


class BarPathSummary(Base):
    """An import's after-you-clicked paths for one underlying, beside random moments (TICKET-999):
    medians, his middle half, the random middle 95%, and up to 200 of his paths, as JSON."""

    __tablename__ = "bar_path_summary"
    id: Mapped[int] = mapped_column(primary_key=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("import.id"))
    underlying: Mapped[str] = mapped_column(String(40))
    measured: Mapped[int] = mapped_column(Integer)
    randoms: Mapped[int] = mapped_column(Integer)
    his_median: Mapped[str] = mapped_column(Text)
    his_q25: Mapped[str] = mapped_column(Text)
    his_q75: Mapped[str] = mapped_column(Text)
    random_median: Mapped[str] = mapped_column(Text)
    random_lo: Mapped[str] = mapped_column(Text)
    random_hi: Mapped[str] = mapped_column(Text)
    faint: Mapped[str] = mapped_column(Text)


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
