"""Uploads version trading days; they never append to them (PRD 5.4).

Per source account, a day present in an earlier upload is superseded by the later
upload's rows for that day. The earlier version is retained, the per-day diff is
shown in the import review, and a day that shrank is flagged.

Two things fall out of this one rule, which is why it is the rule:

**Cross-upload duplication becomes impossible.** A trader who exports an overlapping
range twice replaces the overlap rather than doubling it, so no hash comparison
across uploads is needed and no row has to be deleted to keep the arithmetic right.

**Late trades need no separate mechanism.** A day that grew is the same code path as
a day that was corrected: both produce a new version, and the Journal for that day is
regenerated as a new version too (PRD 7.2).

A day the new upload does not mention is left alone. Re-exporting one week must never
erase the weeks around it -- the upload says what those days contain, not what every
day contains.

Scoping to the source account is the caller's job: pass the ``existing`` map for one
account. Keeping that at the call site makes the per-account rule visible where the
account is known, rather than hidden behind a parameter here.
"""

from __future__ import annotations

from dataclasses import dataclass

from services.shared.schemas import scope_v1 as s


@dataclass(frozen=True)
class DayRows:
    """One trading day in the incoming upload, and how many rows it carries."""

    trading_day: str
    row_count: int


@dataclass(frozen=True)
class DayDiffResult:
    """What this upload does to one day."""

    trading_day: str
    rows_before: int
    rows_after: int
    diff: s.DayDiff
    day_shrank: bool


def diff_against_existing(
    *, incoming: list[DayRows], existing: dict[str, int]
) -> list[DayDiffResult]:
    """One result per day the upload contains, ordered by day.

    ``existing`` maps trading day to the row count of its current version, already
    scoped to one source account. A day absent from ``incoming`` produces no result
    and is therefore untouched.
    """
    results: list[DayDiffResult] = []
    for entry in sorted(incoming, key=lambda d: d.trading_day):
        before = existing.get(entry.trading_day, 0)
        after = entry.row_count
        if after == before:
            diff = s.DayDiff.IDENTICAL
        elif after > before:
            diff = s.DayDiff.GROWN
        else:
            diff = s.DayDiff.SHRUNK
        results.append(
            DayDiffResult(
                trading_day=entry.trading_day,
                rows_before=before,
                rows_after=after,
                diff=diff,
                day_shrank=diff is s.DayDiff.SHRUNK,
            )
        )
    return results


def apply(existing: dict[str, int], diffs: list[DayDiffResult]) -> dict[str, int]:
    """The day map after this upload. Days not in the upload are carried over."""
    updated = dict(existing)
    for d in diffs:
        updated[d.trading_day] = d.rows_after
    return updated


def shrunk_days(diffs: list[DayDiffResult]) -> list[DayDiffResult]:
    """The days to put in front of the trader. A day losing rows is never silent."""
    return [d for d in diffs if d.day_shrank]
