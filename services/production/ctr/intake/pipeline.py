"""The import pipeline, as a pure decision (PRD 5.2-5.4, 9).

``plan_import`` takes the file's text and what already exists, and returns everything
that should happen: the outcome, every row with its status and flag, the day diffs,
the reconstruction, and the versions that produced it. It touches no database and no
disk.

Why a plan rather than a procedure: methodology Rule 2 wants every transformation to
be a pure function of its versioned inputs. A function that reads a file, writes rows
and returns nothing cannot be compared with itself, so reproducibility becomes a
database crawl. ``ImportPlan.digest()`` is the comparison instead -- a content hash
over everything decision-relevant, and over nothing that moves with the clock.

Persistence writes the plan; it decides nothing.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace

from services.production.ctr import reconstruct as rc
from services.production.ctr.adapters import dhan_tradebook, filemap
from services.production.ctr.intake import day_versions as dv
from services.production.ctr.intake import duplicates as dup
from services.production.ctr.intake import outcomes as oc
from services.production.ctr.profiles import registry as profiles
from services.shared.schemas import scope_v1 as s
from services.shared.schemas.ctr_v1 import Fill, RoundTrip

PROFILE_DIR = oc.ADAPTER_DIR.parent / "profiles"


@dataclass(frozen=True)
class ImportContext:
    """What the pipeline needs to know that is not in the file."""

    trader_id: str
    source_account: str
    code_version: str
    existing_days: dict[str, int] = field(default_factory=dict)
    export_date: str | None = None
    export_date_source: str | None = None


@dataclass(frozen=True)
class PlannedRow:
    row_no: int
    raw_text: str
    status: str
    reason: str | None = None
    flag: s.RowFlag | None = None
    dup_group: str | None = None
    fill_id: str | None = None


@dataclass(frozen=True)
class ImportPlan:
    """Everything this upload should do. Nothing here has happened yet."""

    outcome: s.ImportOutcome
    rejection_text: str | None = None
    adapter_id: str | None = None
    adapter_version: str | None = None
    filemap_version: str | None = None
    profile_versions: dict[str, str] = field(default_factory=dict)
    code_version: str = ""
    rows: tuple[PlannedRow, ...] = ()
    rows_in: int = 0
    rows_parsed: int = 0
    rows_excluded: int = 0
    fees_available: bool = False
    missing_fields: tuple[str, ...] = ()
    instruments_without_profile: tuple[str, ...] = ()
    trips: tuple[RoundTrip, ...] = ()
    open_positions: int = 0
    skipped: tuple[str, ...] = ()
    day_diffs: tuple[dv.DayDiffResult, ...] = ()
    density_default_unit: str | None = None
    export_date: str | None = None
    export_date_source: str | None = None

    def with_rows(self, rows: tuple[PlannedRow, ...]) -> ImportPlan:
        """A copy carrying different row statuses, with the counts kept consistent.

        Used when a trader confirms a duplicate group: the file is re-read and the
        confirmed rows become exclusions. Rebuilding through dataclasses.replace
        rather than __dict__ means a field added later cannot be silently dropped.
        """
        return replace(
            self,
            rows=rows,
            rows_excluded=sum(1 for r in rows if r.status == "EXCLUDED"),
        )

    def digest(self) -> str:
        """A content hash over what this plan decided.

        Covers the outcome, every row's status and flag, every trip's identity and
        money, and the day diffs. Excludes anything that moves with the clock, so the
        same file planned a year apart hashes the same (methodology Rule 4).
        """
        parts: list[str] = [
            self.outcome.value,
            self.rejection_text or "",
            self.adapter_id or "",
            self.adapter_version or "",
            self.filemap_version or "",
            ",".join(f"{k}={v}" for k, v in sorted(self.profile_versions.items())),
            f"{self.rows_in}/{self.rows_parsed}/{self.rows_excluded}",
            str(self.fees_available),
            ",".join(sorted(self.missing_fields)),
            self.density_default_unit or "",
            ",".join(self.instruments_without_profile),
        ]
        parts.extend(
            f"{r.row_no}|{r.status}|{r.flag.value if r.flag else ''}|{r.dup_group or ''}"
            for r in self.rows
        )
        parts.extend(
            f"{t.trip_id}|{t.gross_pnl}|{t.fees}|{t.net_pnl}|{t.quantity}" for t in self.trips
        )
        parts.extend(
            f"{d.trading_day}|{d.rows_before}|{d.rows_after}|{d.diff.value}"
            for d in self.day_diffs
        )
        return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def _trading_day(
    trip: RoundTrip, profile_map: dict[tuple[str, str], profiles.InstrumentProfile]
) -> str:
    """The entry's calendar date in the instrument's own timezone.

    definitions_v1.md section 1. Indian exchanges share IST, so a trader on MCX and
    NSE gets one day; a US exchange's profile carries its own zone. With no profile
    the stored zone is used and the import records that no profile was found.
    """
    profile = profiles.lookup(profile_map, trip.exchange, trip.symbol, trip.segment)
    if profile is not None:
        return trip.entry_ts.astimezone(profile.timezone()).date().isoformat()
    return trip.entry_ts.date().isoformat()


def _fill_trading_day(
    fill: Fill, profile_map: dict[tuple[str, str], profiles.InstrumentProfile]
) -> str:
    """A fill's trading day, by the same rule as a trip's (definitions_v1.md s1)."""
    profile = profiles.lookup(profile_map, fill.exchange, fill.symbol, fill.segment)
    if profile is not None:
        return fill.ts.astimezone(profile.timezone()).date().isoformat()
    return fill.ts.date().isoformat()


def _density_default(trips: list[RoundTrip], days: list[str]) -> str:
    """PRD 2 and 7.2: the trading day unless the median eligible day is thin."""
    if not days:
        return s.JournalUnit.PER_N_TRIPS.value
    per_day: dict[str, int] = {}
    for day in days:
        per_day[day] = per_day.get(day, 0) + 1
    counts = sorted(per_day.values())
    median = counts[len(counts) // 2]
    return (
        s.JournalUnit.DAY.value if median >= 2 else s.JournalUnit.PER_N_TRIPS.value
    )


def plan_import(
    text: str, *, context: ImportContext, production: bool = False
) -> ImportPlan:
    """Decide what this upload does. Writes nothing."""
    decision = oc.check_format(text)
    adapter = oc.select_adapter(text)

    if production and adapter is not None:
        filemap.require_verified(adapter.file_map())

    if decision.outcome is s.ImportOutcome.REJECTED or adapter is None:
        if production and adapter is None:
            # Nothing to verify: the broker-neutral sentence names no export.
            pass
        return ImportPlan(
            outcome=s.ImportOutcome.REJECTED,
            rejection_text=oc.rejection_for(decision, adapter),
            code_version=context.code_version,
            export_date=context.export_date,
            export_date_source=context.export_date_source,
        )

    file_map = adapter.file_map()
    raw_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    parsed = dhan_tradebook.parse(
        text.splitlines(), trader_id=context.trader_id, raw_hash=raw_hash
    )

    body = text.splitlines()[1:]
    classification = dup.classify_rows([line for line in body if line.strip()])

    rejected_by_row = {r.row: r.reason for r in parsed.rejected}
    rows: list[PlannedRow] = []
    for row in classification.rows:
        reason = rejected_by_row.get(row.row_no + 1)
        if reason is not None:
            status = "REJECTED"
        elif row.excluded:
            status = "EXCLUDED"
        else:
            status = "PARSED"
        rows.append(
            PlannedRow(row.row_no, row.raw_text, status, reason, row.flag, row.dup_group)
        )

    fills: list[Fill] = parsed.fills
    result = rc.reconstruct(fills, fees_available=parsed.fees_available)

    profile_map = profiles.load_all(PROFILE_DIR)
    resolved = {
        (t.exchange, t.symbol): profiles.lookup(profile_map, t.exchange, t.symbol, t.segment)
        for t in result.round_trips
    }
    # Keyed by the profile actually used, so a segment profile is recorded once as
    # NSE:* rather than once per share, and its version is what the import cites.
    used = {p.key: p for p in resolved.values() if p is not None}
    # An instrument with no profile has no multiplier, tick size or timezone of its
    # own (PRD 9: never hard-coded, never defaulted). The trips are still read -- a
    # missing profile is our gap, not the trader's error -- but it is recorded and
    # shown, never silent, and no figure that needs a multiplier may be derived.
    unprofiled = sorted(
        f"{exchange}:{symbol}"
        for (exchange, symbol), profile in resolved.items()
        if profile is None
    )
    days = [_trading_day(t, profile_map) for t in result.round_trips]

    # A day's size is its ROWS, not its trips. The trader can reconcile a row count
    # against his own file, and -- the reason this matters more -- a day whose rows
    # fell can reconstruct to the same number of trips, so a trip-based diff would
    # report IDENTICAL and hide the loss that day versioning exists to catch.
    fill_days = [_fill_trading_day(f, profile_map) for f in fills]
    day_diffs = dv.diff_against_existing(
        incoming=[
            dv.DayRows(trading_day=day, row_count=fill_days.count(day))
            for day in sorted(set(fill_days))
        ],
        existing=context.existing_days,
    )

    missing_fields: list[str] = [] if parsed.fees_available else ["fees"]
    if unprofiled:
        missing_fields.append("instrument profile")
    excluded_count = sum(1 for r in rows if r.status == "EXCLUDED")
    outcome = oc.decide_outcome(
        excluded_count=excluded_count,
        missing_fields=missing_fields,
        parsed_count=len(fills),
    )

    return ImportPlan(
        outcome=outcome,
        adapter_id=adapter.adapter_id,
        adapter_version=file_map.version,
        filemap_version=file_map.version,
        profile_versions=profiles.versions_used(list(used.values())),
        code_version=context.code_version,
        rows=tuple(rows),
        rows_in=parsed.rows_in,
        rows_parsed=len(fills),
        rows_excluded=excluded_count,
        fees_available=parsed.fees_available,
        missing_fields=tuple(missing_fields),
        instruments_without_profile=tuple(unprofiled),
        trips=tuple(result.round_trips),
        open_positions=len(result.open_positions),
        skipped=tuple(sk.reason for sk in result.skipped),
        day_diffs=tuple(day_diffs),
        density_default_unit=_density_default(result.round_trips, days),
        export_date=context.export_date,
        export_date_source=context.export_date_source,
    )
