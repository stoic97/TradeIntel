"""Duplicate tiers: nothing is discarded on a hash alone (PRD 5.4).

Two legitimate fills can be byte-identical when a broker's timestamps are coarse --
one order filling twice inside the same second produces two true rows that look like
one row typed twice. From inside the file the two cases are indistinguishable, and
only the trader can tell them apart, so:

* **With a fill id** a repeat is provably the same fill. The extras are excluded with
  reason ``DUPLICATE_FILL_ID``, retained and inspectable.
* **Without one** identical rows are **kept** and flagged ``SUSPECTED_DUPLICATE``,
  grouped so the trader confirms a group in one tap rather than row by row. A
  confirmation excludes the extras as ``TRADER_CONFIRMED_DUPLICATE`` and the import
  is re-run as a new version.

The asymmetry is the decision in list item 24: keeping inflates a duplicated export,
dropping deletes a real fill, and deletion is the irreversible wrong. An adapter may
pin a stricter rule only with a fixture showing that broker never emits identical
legitimate rows.

Every row survives classification in one list; ``kept_count + len(excluded)`` always
equals the rows read.
"""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass, replace
from pathlib import Path

from services.shared.schemas import scope_v1 as s

FILL_ID_COLUMNS = ("Order ID", "Trade ID", "Fill ID")


@dataclass(frozen=True)
class ClassifiedRow:
    """One export row, with whatever the tiers concluded about it."""

    row_no: int
    raw_text: str
    flag: s.RowFlag | None = None
    dup_group: str | None = None
    fill_id: str | None = None

    @property
    def excluded(self) -> bool:
        return self.flag in (s.RowFlag.DUPLICATE_FILL_ID, s.RowFlag.TRADER_CONFIRMED_DUPLICATE)


@dataclass(frozen=True)
class Classification:
    rows: tuple[ClassifiedRow, ...]

    @property
    def excluded(self) -> list[ClassifiedRow]:
        return [r for r in self.rows if r.excluded]

    @property
    def kept_count(self) -> int:
        return sum(1 for r in self.rows if not r.excluded)

    @property
    def suspected_groups(self) -> dict[str, list[ClassifiedRow]]:
        groups: dict[str, list[ClassifiedRow]] = {}
        for r in self.rows:
            if r.flag is s.RowFlag.SUSPECTED_DUPLICATE and r.dup_group:
                groups.setdefault(r.dup_group, []).append(r)
        return groups


def _group_key(raw_text: str) -> str:
    """A short stable name for a set of identical rows. Not an identity claim."""
    return hashlib.sha256(raw_text.encode("utf-8")).hexdigest()[:12]


def _find_fill_id_column(fieldnames: list[str] | None) -> str | None:
    for candidate in FILL_ID_COLUMNS:
        if fieldnames and candidate in fieldnames:
            return candidate
    return None


def classify_rows(
    raw_rows: list[str], fill_ids: list[str | None] | None = None
) -> Classification:
    """Apply the tiers to rows already read, in the order given."""
    if fill_ids is not None and any(fid for fid in fill_ids):
        seen: dict[str, int] = {}
        out: list[ClassifiedRow] = []
        for i, (text, fid) in enumerate(zip(raw_rows, fill_ids, strict=True), start=1):
            if fid and fid in seen:
                out.append(
                    ClassifiedRow(i, text, s.RowFlag.DUPLICATE_FILL_ID, _group_key(fid), fid)
                )
            else:
                if fid:
                    seen[fid] = i
                out.append(ClassifiedRow(i, text, None, None, fid))
        return Classification(tuple(out))

    counts: dict[str, int] = {}
    for text in raw_rows:
        counts[text] = counts.get(text, 0) + 1
    return Classification(
        tuple(
            ClassifiedRow(
                i,
                text,
                s.RowFlag.SUSPECTED_DUPLICATE if counts[text] > 1 else None,
                _group_key(text) if counts[text] > 1 else None,
            )
            for i, text in enumerate(raw_rows, start=1)
        )
    )


def classify_file(path: Path, *, has_fill_id: bool) -> Classification:
    """Read an export and classify its rows. The header is not a row."""
    text = Path(path).read_text().splitlines()
    body = text[1:]
    if not has_fill_id:
        return classify_rows(body)

    reader = csv.DictReader(Path(path).read_text().splitlines())
    column = _find_fill_id_column(reader.fieldnames)
    ids: list[str | None] = [
        (record.get(column) if column else None) for record in reader
    ]
    return classify_rows(body, ids)


def confirm_group(classification: Classification, dup_group: str) -> Classification:
    """The trader says a flagged group is one trade typed twice.

    The first row of the group stays; the rest are excluded as
    ``TRADER_CONFIRMED_DUPLICATE``, retained and inspectable. Other groups are
    untouched -- a confirmation is about one group, never a file-wide policy.
    """
    first_seen = False
    out: list[ClassifiedRow] = []
    for row in classification.rows:
        if row.dup_group == dup_group and row.flag is s.RowFlag.SUSPECTED_DUPLICATE:
            if not first_seen:
                first_seen = True
                out.append(replace(row, flag=None))
            else:
                out.append(replace(row, flag=s.RowFlag.TRADER_CONFIRMED_DUPLICATE))
        else:
            out.append(row)
    return Classification(tuple(out))
