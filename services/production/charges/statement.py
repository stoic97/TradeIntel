"""A second file from the broker: what he was charged, day by day (TICKET-828).

A record, not a calculation: amounts are taken as the file states them.

**This shape is a placeholder.** Nobody working on this has a real contract note or
charges ledger to read it against, so ``Date,Total Charges`` is the smallest shape the
path can be built and tested on, and it names no real export. ``VERIFIED`` keeps it out
of production by the same rule as a broker's file map (ctr/adapters/filemap.py): what a
real trader reads is not built on a guessed file. With a real sample, change ``parse``,
set ``VERIFIED``, and the rest of the path stands.
"""

from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal, InvalidOperation

READER_ID = "charges_statement_draft_v0"
VERIFIED = False
HEADER = ("Date", "Total Charges")


class Unreadable(Exception):
    """A file this reader refuses, with the sentence to show."""


def parse(content: bytes) -> dict[str, Decimal]:
    """Each trading day's charges, as the file states them. Anything else is refused."""
    try:
        lines = content.decode("utf-8-sig").splitlines()
    except UnicodeDecodeError as exc:
        raise Unreadable("That is not a text file we can read.") from exc
    rows = [row for row in csv.reader(lines) if any(cell.strip() for cell in row)]
    if not rows or tuple(cell.strip() for cell in rows[0]) != HEADER:
        raise Unreadable(f"We read files with the columns {', '.join(HEADER)}. This one has others.")
    days: dict[str, Decimal] = {}
    for row in rows[1:]:
        if len(row) != len(HEADER):
            raise Unreadable(f"A row has {len(row)} columns: {','.join(row)}")
        day, amount = (cell.strip() for cell in row)
        try:
            date.fromisoformat(day)
            value = Decimal(amount)
        except (ValueError, InvalidOperation) as exc:
            raise Unreadable(f"We could not read this row: {day}, {amount}") from exc
        if not value.is_finite() or value < 0:
            raise Unreadable(f"Charges cannot be {amount}, on {day}.")
        if day in days:
            raise Unreadable(f"{day} appears twice.")
        days[day] = value
    if not days:
        raise Unreadable("That file has no days in it.")
    return days
