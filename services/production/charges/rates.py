"""Statutory charges, as a dated table somebody maintains (TICKET-911).

STT, CTT, exchange transaction charges, the SEBI turnover fee, stamp duty and GST are set by
Acts, circulars and notifications, and they are the same for every trader. So they are not
asked of a broker or an API. They are rows in ``rates.yaml``, each with the date it took
effect and the document that set it.

Four rules hold the table:

* **A date is covered or it refuses.** ``rate`` finds the row in force on the trade's date.
  Before ``TABLE_STARTS``, or where a segment has no row, it raises :class:`NotCovered`. It
  never falls back to today's rate.
* **Append-only.** Rows are never edited. ``rates.lock`` pins each row's content by digest,
  and a test fails if a pinned row changes. A correction is a new row. It either takes
  effect from a later date, or repeats an earlier ``effective_from`` with a later ``added``
  date. A read can pass ``as_of`` to see the table as it stood on a day, so a report made in
  March reproduces in September.
* **Every row names its source.**
* **Money is Decimal, read from strings.** A YAML float is refused at load.

Brokerage is not here: it varies by broker and plan (TICKET-912). Nothing here is applied
to a trader's figures yet.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from itertools import pairwise
from pathlib import Path

import yaml

HERE = Path(__file__).parent
TABLE = HERE / "rates.yaml"
LOCK = HERE / "rates.lock"


class Segment(StrEnum):
    NSE_EQ_DELIVERY = "NSE_EQ_DELIVERY"
    NSE_EQ_INTRADAY = "NSE_EQ_INTRADAY"
    NSE_FUT = "NSE_FUT"
    NSE_OPT = "NSE_OPT"
    BSE_FUT = "BSE_FUT"
    BSE_OPT = "BSE_OPT"
    MCX_FUT = "MCX_FUT"
    MCX_OPT = "MCX_OPT"


class Component(StrEnum):
    STT = "STT"            # securities transaction tax (NSE, BSE)
    CTT = "CTT"            # commodity transaction tax (MCX)
    EXCHANGE = "EXCHANGE"  # the exchange's transaction charge
    SEBI = "SEBI"          # SEBI turnover fee
    STAMP = "STAMP"        # stamp duty
    GST = "GST"            # on brokerage, exchange charges, the SEBI fee and IPFT
    IPFT = "IPFT"          # NSE's investor protection fund charge


SIDES = ("buy", "sell")
BASES = ("turnover", "premium", "charges")
"""What a rate is a fraction of: the order's turnover, its premium (options), or, for GST,
the charges it is levied on."""


class NotCovered(LookupError):
    """No row covers this segment, component, side and date, so the rupees can't be stated."""


class InvalidTable(ValueError):
    """The table breaks one of its own rules. Raised at load, where it is visible."""


@dataclass(frozen=True)
class Rate:
    id: int
    segment: Segment
    component: Component
    side: str
    base: str
    rate: Decimal
    effective_from: date
    added: date
    source: str
    note: str = ""


def digest(row: dict) -> str:
    """The pinned content of one row: canonical JSON of its fields, as written."""
    return hashlib.sha256(json.dumps(row, sort_keys=True, default=str).encode()).hexdigest()


def read_lock(path: Path | None = None) -> dict[int, str]:
    """Each pinned row's id and digest, in the order they were pinned."""
    path = path or LOCK
    if not path.exists():
        return {}
    out: dict[int, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            id_, digest_ = line.split()
            out[int(id_)] = digest_
    return out


def _date(value: object, where: str) -> date:
    if not isinstance(value, str):
        raise InvalidTable(f"{where}: dates are written as quoted strings, got {value!r}")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise InvalidTable(f"{where}: {value!r} is not a date") from exc


def _row(raw: dict) -> Rate:
    where = f"row {raw.get('id')!r}"
    if not isinstance(raw.get("id"), int):
        raise InvalidTable(f"{where}: every row needs a whole-number id")
    if not isinstance(raw.get("rate"), str):
        raise InvalidTable(f"{where}: a rate is written as a string, never a YAML number")
    try:
        value = Decimal(raw["rate"])
    except InvalidOperation as exc:
        raise InvalidTable(f"{where}: {raw['rate']!r} is not a number") from exc
    if not value.is_finite() or value < 0:
        raise InvalidTable(f"{where}: a rate can't be {raw['rate']}")
    try:
        segment, component = Segment(raw.get("segment")), Component(raw.get("component"))
    except ValueError as exc:
        raise InvalidTable(f"{where}: {exc}") from exc
    if raw.get("side") not in SIDES or raw.get("base") not in BASES:
        raise InvalidTable(f"{where}: side must be one of {SIDES} and base one of {BASES}")
    source = raw.get("source")
    if not isinstance(source, str) or not source.strip():
        raise InvalidTable(f"{where}: every row names the document that set it")
    return Rate(id=raw["id"], segment=segment, component=component, side=raw["side"],
                base=raw["base"], rate=value, effective_from=_date(raw.get("effective_from"), where),
                added=_date(raw.get("added"), where), source=source.strip(),
                note=str(raw.get("note") or "").strip())


def load(path: Path = TABLE) -> tuple[date, list[Rate], list[dict]]:
    """The table's start date, its rows, and the raw rows as written (for the lock)."""
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    starts = _date(doc.get("starts"), "starts")
    raw = doc.get("rows") or []
    rows = [_row(r) for r in raw]
    ids = [r.id for r in rows]
    if any(b <= a for a, b in pairwise(ids)):
        raise InvalidTable("ids must only grow down the file: a new row is added at the end")
    return starts, rows, raw


_LOADED: tuple[date, list[Rate], list[dict]] | None = None


def _shipped() -> tuple[date, list[Rate], list[dict]]:
    global _LOADED
    if _LOADED is None:
        _LOADED = load()
    return _LOADED


def rate(segment: Segment, component: Component, side: str, on: date, *,
         as_of: date | None = None, table: tuple[date, list[Rate], list[dict]] | None = None) -> Rate:
    """The row in force on ``on`` (as the table stood on ``as_of``), or :class:`NotCovered`.

    Of the rows for this segment, component and side that had been added by ``as_of``, the
    one with the latest ``effective_from`` on or before ``on`` wins; between rows with the
    same ``effective_from``, the one added later (a correction) wins.
    """
    starts, rows, _ = table if table is not None else _shipped()
    if on < starts:
        raise NotCovered(f"the rate table starts on {starts.isoformat()}; {on.isoformat()} is before it")
    found = [r for r in rows
             if r.segment == segment and r.component == component and r.side == side
             and r.effective_from <= on and (as_of is None or r.added <= as_of)]
    if not found:
        raise NotCovered(f"no {component} rate for {segment}, {side} side, on {on.isoformat()}")
    return max(found, key=lambda r: (r.effective_from, r.added, r.id))


_BOTH = (("buy",), ("sell",))
_EVERY_ORDER = tuple((c, s) for c in (Component.EXCHANGE, Component.SEBI, Component.GST) for (s,) in _BOTH)


def _required(tax: Component, tax_sides: tuple[str, ...], *, ipft: bool) -> tuple[tuple[Component, str], ...]:
    extra = tuple((Component.IPFT, s) for (s,) in _BOTH) if ipft else ()
    return tuple((tax, s) for s in tax_sides) + _EVERY_ORDER + ((Component.STAMP, "buy"),) + extra


REQUIRED: dict[Segment, tuple[tuple[Component, str], ...]] = {
    Segment.NSE_EQ_DELIVERY: _required(Component.STT, ("buy", "sell"), ipft=True),
    Segment.NSE_EQ_INTRADAY: _required(Component.STT, ("sell",), ipft=True),
    Segment.NSE_FUT: _required(Component.STT, ("sell",), ipft=True),
    Segment.NSE_OPT: _required(Component.STT, ("sell",), ipft=True),
    Segment.BSE_FUT: _required(Component.STT, ("sell",), ipft=False),
    Segment.BSE_OPT: _required(Component.STT, ("sell",), ipft=False),
    Segment.MCX_FUT: _required(Component.CTT, ("sell",), ipft=False),
    Segment.MCX_OPT: _required(Component.CTT, ("sell",), ipft=False),
}
"""What each segment must have a row for, from the table's first day to today. Option
exercise (STT/CTT on settlement value) is not here: a trip the product reads is closed by a
trade, and exercise is its own row when a history needs it."""

GST_ON = (Component.EXCHANGE, Component.SEBI, Component.IPFT)
"""What GST is levied on, of what this table holds. Brokerage is the broker's (TICKET-912)."""


def statutory(segment: Segment, side: str, value: Decimal, on: date, *,
              as_of: date | None = None, table: tuple[date, list[Rate], list[dict]] | None = None,
              ) -> dict[Component, Decimal]:
    """The statutory charges on one made-up order of ``value`` (turnover, or premium for
    options), unrounded, by component. GST is on the exchange charge, the SEBI fee and IPFT;
    GST on brokerage comes with brokerage (TICKET-912)."""
    out: dict[Component, Decimal] = {}
    for component, need_side in REQUIRED[segment]:
        if need_side != side or component is Component.GST:
            continue
        out[component] = value * rate(segment, component, side, on, as_of=as_of, table=table).rate
    gst = rate(segment, Component.GST, side, on, as_of=as_of, table=table).rate
    out[Component.GST] = gst * sum((out.get(c, Decimal(0)) for c in GST_ON), Decimal(0))
    return out
