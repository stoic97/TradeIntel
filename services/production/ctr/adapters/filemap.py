"""Broker file maps: which export we need, in the broker's own words.

PRD v1.2 section 5.2. Most brokers offer four or more exports and a trader cannot
tell from a rejection which one we mean, so each adapter ships a map naming every
export the broker offers, where it lives in their interface, and which is ours. Of
the first five histories collected, three were unusable -- two P&L statements, one
with dates but no times -- which makes this the highest-yield validation we have.

**An unverified map cannot reach a partner.** The PRD requires the wording to be
checked against the broker's interface rather than guessed, so a map carries
``verified`` and ``verified_on``, and :func:`require_verified` refuses an unverified
one. A draft is usable in development and in tests; it is not usable on a rejection
screen a real trader will read.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

QUANTITY_UNITS = frozenset({"lots", "units"})


class InvalidFileMap(Exception):
    """A map file the loader refuses."""


class UnverifiedFileMap(Exception):
    """A map that has not been checked against the broker's interface."""


@dataclass(frozen=True)
class Export:
    """One export the broker offers, named as the broker names it."""

    broker_name: str
    where_it_lives: str
    is_the_one_we_need: bool
    note: str | None = None


@dataclass(frozen=True)
class FileMap:
    broker: str
    adapter_id: str
    version: str
    verified: bool
    verified_on: str | None
    quantity_unit: str
    """Whether the export's quantity column counts lots or single units.

    A fact about the broker's file, so it belongs here and is gated by the same
    verification. It decides the size figure the Mirror prints: with "units" the
    count is divided by the instrument's contract multiplier to reach lots.
    Money never consults it -- gross comes from the broker's own rupee totals.
    """

    exports: tuple[Export, ...]

    @property
    def wanted(self) -> Export:
        return next(e for e in self.exports if e.is_the_one_we_need)


def load(path: Path) -> FileMap:
    raw: Any = yaml.safe_load(Path(path).read_text())
    if not isinstance(raw, dict):
        raise InvalidFileMap(f"{path.name}: expected a mapping")
    for field in ("broker", "adapter_id", "version", "verified",
                  "quantity_unit", "exports"):
        if field not in raw:
            raise InvalidFileMap(f"{path.name}: missing {field}")

    exports = tuple(
        Export(
            broker_name=str(e["broker_name"]),
            where_it_lives=str(e["where_it_lives"]),
            is_the_one_we_need=bool(e["is_the_one_we_need"]),
            note=e.get("note"),
        )
        for e in raw["exports"]
    )
    wanted = [e for e in exports if e.is_the_one_we_need]
    if len(wanted) != 1:
        raise InvalidFileMap(
            f"{path.name}: exactly one export must be the trade-level one, found {len(wanted)}"
        )
    quantity_unit = str(raw["quantity_unit"])
    if quantity_unit not in QUANTITY_UNITS:
        raise InvalidFileMap(
            f"{path.name}: quantity_unit must be one of {sorted(QUANTITY_UNITS)}, "
            f"not {quantity_unit!r} -- it decides whether a trader's size reads "
            "as lots or as hundreds of them"
        )
    return FileMap(
        broker=str(raw["broker"]),
        adapter_id=str(raw["adapter_id"]),
        version=str(raw["version"]),
        verified=bool(raw["verified"]),
        verified_on=raw.get("verified_on"),
        quantity_unit=quantity_unit,
        exports=exports,
    )


def require_verified(file_map: FileMap) -> FileMap:
    """Gate for anything a partner will see. Raises unless the map was checked."""
    if not file_map.verified:
        raise UnverifiedFileMap(
            f"the {file_map.broker} file map has not been verified against the "
            "broker's interface (PRD 5.2); verify it and set verified_on before a "
            "partner can be shown a rejection built from it"
        )
    return file_map


def rejection_text(file_map: FileMap, *, looks_like: str, missing: str) -> str:
    """PRD 5.3's rejection: what the file is, what is missing, what to send instead.

    Nothing else is shown -- no next step, no other screen, no encouragement.
    """
    wanted = file_map.wanted
    return (
        f"This looks like {looks_like}, and it has no {missing}. "
        f"We need the trade-level export: on {file_map.broker} it is called "
        f"'{wanted.broker_name}' and is under {wanted.where_it_lives}."
    )
