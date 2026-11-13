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
from collections.abc import Iterable
from dataclasses import dataclass, field

from services.production.ctr import reconstruct as rc
from services.production.ctr.adapters import filemap
from services.production.ctr.intake import day_versions as dv
from services.production.ctr.intake import duplicates as dup
from services.production.ctr.intake import outcomes as oc
from services.production.ctr.intake import workbook
from services.production.ctr.profiles import registry as profiles
from services.shared.positions import Position, group_positions
from services.shared.schemas import scope_v1 as s
from services.shared.schemas.ctr_v1 import Fill, RoundTrip, Segment

PROFILE_DIR = oc.ADAPTER_DIR.parent / "profiles"


def text_of(content: bytes) -> str:
    """An upload's bytes as the text ``plan_import`` reads (TICKET-895).

    A CSV is decoded as it always was. A workbook (Groww) becomes CSV from its header
    down, leaving its preamble's name and client code behind. A file that claims to be
    a workbook and is not one comes back decoded as it is, and the format check
    rejects it like any file we do not recognise.
    """
    try:
        return workbook.text_of(content, oc.headers())
    except workbook.UnreadableWorkbook:
        return content.decode("utf-8-sig", errors="replace")


SHARES, DERIVATIVES = "shares", "F&O"


def kinds_in(text: str) -> frozenset[str]:
    """What a file's readable rows hold: shares, F&O, or both. Empty for a file we can't read."""
    adapter = oc.select_adapter(text)
    if adapter is None:
        return frozenset()
    parsed = adapter.parse(text.splitlines(), trader_id="kinds", raw_hash="0" * 64)  # read, not kept
    return frozenset(SHARES if f.segment is Segment.EQ else DERIVATIVES for f in parsed.fills)


def files_kept(record: list[str], new: str) -> list[int]:
    """Which of the record's files a new upload is read together with (TICKET-926).

    Groww gives stocks and F&O as two downloads under one header, so a trader's record can
    need both. A file of the record stays when it is the same broker's format and holds
    nothing of the kinds the new file holds; anything it shares a kind with, the new file
    replaces, as a newer download of the same thing. A file of another format, or a new
    file with nothing readable, replaces the whole record, which is what happened before.
    """
    adapter = oc.select_adapter(new)
    new_kinds = kinds_in(new)
    if adapter is None or not new_kinds:
        return []
    kept: list[int] = []
    for at, text in enumerate(record):
        other = oc.select_adapter(text)
        if other is None or other.adapter_id != adapter.adapter_id:
            return []
        kinds = kinds_in(text)
        if kinds and not kinds & new_kinds:
            kept.append(at)
    return kept


def combine(texts: list[str]) -> str:
    """Files of one format read as one: the header once, then each file's rows in turn."""
    if len(texts) == 1:
        return texts[0]
    lines = [texts[0].splitlines()[0]]
    for text in texts:
        lines.extend(line for line in text.splitlines()[1:] if line.strip())
    return "\n".join(lines) + "\n"


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
    reconstruction_version: str | None = None
    rows: tuple[PlannedRow, ...] = ()
    rows_in: int = 0
    rows_parsed: int = 0
    """The rows the record is built from. Set-aside and unreadable rows aren't among them."""
    rows_excluded: int = 0
    fees_available: bool = False
    missing_fields: tuple[str, ...] = ()
    instruments_without_profile: tuple[str, ...] = ()
    trips: tuple[RoundTrip, ...] = ()
    positions: tuple[Position, ...] = ()
    open_positions: int = 0
    skipped: tuple[str, ...] = ()
    day_diffs: tuple[dv.DayDiffResult, ...] = ()
    density_default_unit: str | None = None
    export_date: str | None = None
    export_date_source: str | None = None

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


def out_of_date(imp) -> bool:
    """Whether this code would read this stored import's file differently.

    Asks what reconstruction and the broker's file map say, never ``code_version``, which
    moves on every deploy. An import from before the version was stored has none, so it
    reads as out of date. Profile versions stay out of it: nothing stored comes from a
    profile's lot sizes, the pages read those live, so a new one needs no re-read.
    """
    if imp.reconstruction_version != rc.RECONSTRUCTION_VERSION:
        return True
    adapter = oc.adapter_for(imp.adapter_id)
    return adapter is None or adapter.file_map().version != imp.adapter_version


def rebuilt_without_confirmed(imp) -> bool:
    """Whether this stored import's trips were built without the rows he confirmed."""
    return imp.reconstruction_version not in rc.BEFORE_CONFIRMED_ROWS_LEFT


def plan_import(
    text: str,
    *,
    context: ImportContext,
    production: bool = False,
    confirmed_groups: Iterable[str] = (),
) -> ImportPlan:
    """Decide what this upload does. Writes nothing.

    ``confirmed_groups`` are the duplicate groups the trader has confirmed. The file can't
    say which they are, so every read of a stored file passes them here (``dup.confirm_group``).
    Their extra rows leave before pairing, because a row gone can change how later fills pair,
    so every figure below comes from what remains. Rows and trips are decided here together
    and nothing changes one without the other.
    """
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
            reconstruction_version=rc.RECONSTRUCTION_VERSION,
            export_date=context.export_date,
            export_date_source=context.export_date_source,
        )

    file_map = adapter.file_map()
    raw_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    lines = text.splitlines()
    parsed = adapter.parse(lines, trader_id=context.trader_id, raw_hash=raw_hash)

    classification = dup.classify_rows([line for line in lines[1:] if line.strip()])
    for group in sorted(confirmed_groups):
        classification = dup.confirm_group(classification, group)

    rejected_by_row = {r.row: r.reason for r in parsed.rejected}
    rows: list[PlannedRow] = []
    for row in classification.rows:
        reason = rejected_by_row.get(row.row_no + 1)
        if row.excluded:
            status = "EXCLUDED"
        elif reason is not None:
            status = "REJECTED"
        else:
            status = "PARSED"
        rows.append(
            PlannedRow(row.row_no, row.raw_text, status, reason, row.flag, row.dup_group)
        )

    # The whole file above says what each row is; only what remains is read into fills.
    fills: list[Fill] = parsed.fills
    if classification.excluded:
        remaining = [r.raw_text for r in classification.rows if not r.excluded]
        fills = adapter.parse(
            [lines[0], *remaining], trader_id=context.trader_id, raw_hash=raw_hash
        ).fills
    result = rc.reconstruct(fills, fees_available=parsed.fees_available, short_options=True)

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
        reconstruction_version=rc.RECONSTRUCTION_VERSION,
        rows=tuple(rows),
        rows_in=parsed.rows_in,
        rows_parsed=len(fills),
        rows_excluded=excluded_count,
        fees_available=parsed.fees_available,
        missing_fields=tuple(missing_fields),
        instruments_without_profile=tuple(unprofiled),
        trips=tuple(result.round_trips),
        positions=tuple(group_positions(result.round_trips)),
        open_positions=len(result.open_positions),
        skipped=tuple(sk.reason for sk in result.skipped),
        day_diffs=tuple(day_diffs),
        density_default_unit=_density_default(result.round_trips, days),
        export_date=context.export_date,
        export_date_source=context.export_date_source,
    )
