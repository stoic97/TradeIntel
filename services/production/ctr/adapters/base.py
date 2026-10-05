"""Shared types for broker adapters.

One adapter per broker, selected by matching the export's header exactly. Every
adapter returns a :class:`ParseResult`, never a bare list of fills, so that

    rows_in == len(fills) + len(rejected)

holds for every import. A row that cannot be parsed is recorded with its line
number and the reason; it is never dropped (Methodology §2 Rule 1 — "no silent
drops"; Research Spec §4.2).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from services.shared.schemas.ctr_v1 import Fill


@dataclass(frozen=True)
class Rejection:
    """A row the adapter refused, and why."""

    row: int
    reason: str
    raw: str


@dataclass(frozen=True)
class ParseResult:
    """What an adapter produced from one raw export.

    ``fees_available`` is False when the export carries no charges column. Every
    currency figure derived from such a file is **gross**, and the diagnosis must
    say so: fees are never estimated into a number presented as exact
    (Research Spec §4.5 — typed missingness, never imputed).
    """

    format_id: str
    rows_in: int
    fills: list[Fill] = field(default_factory=list)
    rejected: list[Rejection] = field(default_factory=list)
    fees_available: bool = False

    def __post_init__(self) -> None:
        accounted = len(self.fills) + len(self.rejected)
        if accounted != self.rows_in:
            raise AssertionError(
                f"{self.rows_in} rows in but {accounted} accounted for — "
                "every row must be mapped or rejected"
            )

    @property
    def rejection_summary(self) -> dict[str, int]:
        """Counts by reason, for the data-quality score (§4.5)."""
        out: dict[str, int] = {}
        for r in self.rejected:
            out[r.reason] = out.get(r.reason, 0) + 1
        return out
