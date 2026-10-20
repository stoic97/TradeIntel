"""Adapter selection, the format check, and the three outcomes (PRD 5.3).

**Selection is by exact header match.** A near-miss is a different export, not a bad
row. Treating it as a bad file produces a rejection naming the export we need;
treating it as rows would produce a screen full of parse errors that tells the trader
nothing he can act on.

**The format check runs before parsing**, because the highest-yield validation in the
product is telling someone his file is the wrong one. Of the first five histories
collected, three were unusable: two P&L statements with no prices or quantities, one
with dates but no times. Without an adapter there is nothing to parse with, so the
check reads the header for the three concepts a trade-level export must carry. It is
deliberately crude: it can only ever produce a rejection, never an acceptance.

**Three outcomes, never a fourth** (PRD 5.3), with the precedence from
definitions_v1.md section 4: exclusions beat partial fields, a clean file is
ACCEPTED_WITH_EXCLUSIONS with a count of zero, and rows with zero parsable fills
cannot proceed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from services.production.ctr.adapters import dhan_tradebook, filemap
from services.shared.schemas import scope_v1 as s

ADAPTER_DIR = Path(__file__).resolve().parents[1] / "adapters"

_TIME_HINTS = ("time", "timestamp", "trade time", "order time")
_PRICE_HINTS = ("price", "rate", "trade price")
_QUANTITY_HINTS = ("quantity", "qty", "lot", "quantity/lot")


@dataclass(frozen=True)
class Adapter:
    """One broker format: how to recognise it, how to parse it, what to say."""

    adapter_id: str
    header: tuple[str, ...]
    filemap_path: Path

    def file_map(self) -> filemap.FileMap:
        return filemap.load(self.filemap_path)


ADAPTERS: tuple[Adapter, ...] = (
    Adapter(
        adapter_id=dhan_tradebook.FORMAT_ID,
        header=dhan_tradebook.HEADER,
        filemap_path=ADAPTER_DIR / "dhan_filemap.yaml",
    ),
)


@dataclass(frozen=True)
class FormatDecision:
    """What the format check concluded, before a single row is parsed."""

    outcome: s.ImportOutcome | None
    adapter_id: str | None = None
    looks_like: str = "a file we do not recognise"
    missing: str = ""


def _header_of(text: str) -> tuple[str, ...]:
    first = text.splitlines()[0] if text.splitlines() else ""
    return tuple(h.strip().lstrip("\ufeff") for h in first.split(","))


def adapter_for(adapter_id: str) -> Adapter | None:
    """The adapter an import recorded, by id.

    ``select_adapter`` matches a file being read; this answers for a file already
    read, which is what anything downstream of an import needs.
    """
    for adapter in ADAPTERS:
        if adapter.adapter_id == adapter_id:
            return adapter
    return None


def select_adapter(text: str) -> Adapter | None:
    """The adapter whose header matches exactly, or none."""
    header = _header_of(text)
    for adapter in ADAPTERS:
        if header == adapter.header:
            return adapter
    return None


def _describe(header: tuple[str, ...]) -> str:
    joined = " ".join(h.lower() for h in header)
    if "p&l" in joined or "profit" in joined:
        return "a profit-and-loss statement"
    if "capital gain" in joined or "tax" in joined:
        return "a tax statement"
    if "ledger" in joined or "narration" in joined:
        return "a funds ledger"
    return "a file we do not recognise"


def _first_missing(header: tuple[str, ...]) -> str:
    """Which required concept the header lacks. Prices first: it is the clearest."""
    lowered = [h.lower() for h in header]

    def has(hints: tuple[str, ...]) -> bool:
        return any(any(hint in column for hint in hints) for column in lowered)

    if not has(_PRICE_HINTS):
        return "prices"
    if not has(_QUANTITY_HINTS):
        return "quantities"
    if not has(_TIME_HINTS):
        return "time of day"
    return ""


def check_format(text: str) -> FormatDecision:
    """Decide before parsing whether this file can proceed at all."""
    adapter = select_adapter(text)
    if adapter is not None:
        return FormatDecision(outcome=None, adapter_id=adapter.adapter_id)

    header = _header_of(text)
    return FormatDecision(
        outcome=s.ImportOutcome.REJECTED,
        adapter_id=None,
        looks_like=_describe(header),
        missing=_first_missing(header) or "the trade-level detail we need",
    )


def decide_outcome(
    *, excluded_count: int, missing_fields: list[str], parsed_count: int | None = None
) -> s.ImportOutcome:
    """The outcome of an import that got past the format check.

    ``parsed_count`` of zero means the file had rows but none became a fill, which
    cannot proceed however the rows failed (definitions_v1.md section 4).
    """
    if parsed_count == 0:
        return s.ImportOutcome.REJECTED
    if excluded_count > 0:
        return s.ImportOutcome.ACCEPTED_WITH_EXCLUSIONS
    if missing_fields:
        return s.ImportOutcome.ACCEPTED_PARTIAL_FIELDS
    return s.ImportOutcome.ACCEPTED_WITH_EXCLUSIONS


def rejection_for(decision: FormatDecision, adapter: Adapter | None = None) -> str:
    """The sentence the trader reads, built from the broker's own file map.

    Falls back to a broker-neutral sentence when no adapter matched, because naming
    one broker's export to a trader who uses another is worse than naming none.
    """
    if adapter is None:
        return (
            f"This looks like {decision.looks_like}, and it has no {decision.missing}. "
            "We need the trade-level export: every executed trade, with the time of "
            "day, the price and the quantity."
        )
    return filemap.rejection_text(
        adapter.file_map(), looks_like=decision.looks_like, missing=decision.missing
    )
