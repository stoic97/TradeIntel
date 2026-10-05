"""Dhan tradebook export -> :class:`Fill` objects.

The export's header, verbatim::

    Date,Time,Name,Buy/Sell,Order,Exchange,Segment,Quantity/Lot,Trade Price,Trade Value,Status

Four facts about this format, each established by inspecting 3,828 real rows
rather than assumed:

**Trade Value is authoritative; Trade Price is a rounded average.** 217 rows had
``price x quantity != value``. In every one, ``round_half_up(value / quantity, 2)``
equalled the quoted price -- these are several fills aggregated onto one line, with
the average price rounded to two decimals for display while the total stayed exact.
Multiplying the quoted price would inject up to Rs 8 of error per row, so ``price``
is derived as ``value / quantity`` at full precision and the quoted figure is kept
as ``quoted_price`` for display only.

**The expiry has no year.** ``NIFTY 22 SEP 23300 PUT`` -- the year is inferred as the
first ``DD MON`` on or after the trade date. 78 real rows trade in December against a
January expiry, so this is not an edge case. An inferred expiry more than
``MAX_EXPIRY_HORIZON_DAYS`` ahead means the inference misfired, and the row is
rejected rather than guessed (Research Spec s4.2 -- contract identity).

**The file is newest-first.** Rows are sorted by timestamp; file order is not trusted.

**There is no charges column.** ``fees_available`` is False, so every currency figure
from this file is gross until a charges statement arrives (s4.5).

Times are IST. ``Order`` is the product type (INTRADAY / MARGIN / DELIVERY), not an
order id -- this export carries no id, so fills are identified by their content hash.
"""

from __future__ import annotations

import csv
import re
from collections.abc import Iterable
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

from services.production.ctr.adapters.base import ParseResult, Rejection
from services.shared.schemas.ctr_v1 import Fill, OptionType, Segment, Side

FORMAT_ID = "dhan_tradebook_v1"

HEADER: tuple[str, ...] = (
    "Date",
    "Time",
    "Name",
    "Buy/Sell",
    "Order",
    "Exchange",
    "Segment",
    "Quantity/Lot",
    "Trade Price",
    "Trade Value",
    "Status",
)

IST = ZoneInfo("Asia/Kolkata")
ACCEPTED_STATUS = "Traded"
MAX_EXPIRY_HORIZON_DAYS = 120
_CENT = Decimal("0.01")

_MONTHS = {
    m: i + 1
    for i, m in enumerate(
        ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
    )
}

# "CRUDEOILM 14 MAY 9700 CALL" -> symbol, day, month, strike, CALL|PUT
_CONTRACT = re.compile(
    r"^(?P<symbol>\S+)\s+(?P<day>\d{1,2})\s+(?P<mon>[A-Za-z]{3})\s+"
    r"(?P<strike>\d+(?:\.\d+)?)\s+(?P<kind>CALL|PUT)$"
)

_SEGMENTS = {
    "Commodity": Segment.OPT,
    "Derivative": Segment.OPT,
    "Equity": Segment.EQ,
}

_SIDES = {"BUY": Side.BUY, "SELL": Side.SELL}

_OPTION_TYPES = {"CALL": OptionType.CE, "PUT": OptionType.PE}


class RowRejected(Exception):
    """Internal: this row cannot be parsed, for the reason given."""


def _infer_expiry(day: int, month: int, traded_on: date) -> date:
    """The first ``day/month`` falling on or after the trade date.

    Tries the trade year, then the next, so a December trade against a January
    expiry resolves forward. A 29 February that does not exist in a candidate year
    is skipped by the ``ValueError``.
    """
    for year in (traded_on.year, traded_on.year + 1):
        try:
            candidate = date(year, month, day)
        except ValueError:
            continue
        if candidate >= traded_on:
            horizon = (candidate - traded_on).days
            if horizon > MAX_EXPIRY_HORIZON_DAYS:
                raise RowRejected(
                    f"inferred expiry {candidate} is {horizon} days after the trade -- "
                    "the year inference misfired, so the contract cannot be identified"
                )
            return candidate
    raise RowRejected("no expiry date on or after the trade date could be formed")


def _decimal(raw: str, field_name: str) -> Decimal:
    try:
        return Decimal(raw.strip())
    except (InvalidOperation, ValueError) as exc:
        raise RowRejected(f"{field_name} is not a number: {raw!r}") from exc


def _parse_row(row: dict[str, str], trader_id: str, raw_hash: str) -> Fill:
    if row["Status"].strip() != ACCEPTED_STATUS:
        raise RowRejected(f"status is {row['Status'].strip()!r}, not {ACCEPTED_STATUS!r}")

    segment_label = row["Segment"].strip()
    if segment_label not in _SEGMENTS:
        raise RowRejected(f"unknown segment {segment_label!r}")
    segment = _SEGMENTS[segment_label]

    side_label = row["Buy/Sell"].strip().upper()
    if side_label not in _SIDES:
        raise RowRejected(f"unknown side {side_label!r}")

    try:
        # The export carries no offset; IST is attached below, deliberately and once.
        traded_on = datetime.strptime(row["Date"].strip(), "%Y-%m-%d").date()  # noqa: DTZ007
        clock = datetime.strptime(row["Time"].strip(), "%H:%M:%S").time()  # noqa: DTZ007
    except ValueError as exc:
        raise RowRejected(f"unparseable date/time: {exc}") from exc
    ts = datetime.combine(traded_on, clock, tzinfo=IST)

    name = row["Name"].strip()
    symbol: str
    expiry: date | None = None
    strike: Decimal | None = None
    option_type: OptionType | None = None

    if segment is Segment.OPT:
        match = _CONTRACT.match(name)
        if match is None:
            raise RowRejected(
                f"name {name!r} is not 'SYMBOL DD MON STRIKE CALL|PUT' -- "
                "the contract cannot be identified"
            )
        mon = match["mon"].upper()
        if mon not in _MONTHS:
            raise RowRejected(f"unknown month {mon!r} in name {name!r}")
        symbol = match["symbol"]
        expiry = _infer_expiry(int(match["day"]), _MONTHS[mon], traded_on)
        strike = _decimal(match["strike"], "strike")
        option_type = _OPTION_TYPES[match["kind"]]
    else:
        symbol = name
        if not symbol:
            raise RowRejected("name is empty")

    quantity_raw = _decimal(row["Quantity/Lot"], "Quantity/Lot")
    if quantity_raw != quantity_raw.to_integral_value():
        raise RowRejected(f"quantity is not whole: {quantity_raw}")
    quantity = int(quantity_raw)
    if quantity <= 0:
        raise RowRejected(f"quantity must be positive, got {quantity}")

    quoted_price = _decimal(row["Trade Price"], "Trade Price")
    trade_value = _decimal(row["Trade Value"], "Trade Value")

    # Trade Value is authoritative. The quoted price must be that value per unit,
    # rounded half-up to two decimals -- anything else means the row is inconsistent.
    price = trade_value / quantity
    if price.quantize(_CENT, rounding=ROUND_HALF_UP) != quoted_price.quantize(_CENT):
        raise RowRejected(
            f"trade value {trade_value} over quantity {quantity} is {price:.6f}, "
            f"which does not round to the quoted price {quoted_price}"
        )

    return Fill(
        trader_id=trader_id,
        broker="dhan",
        ts=ts,
        exchange=row["Exchange"].strip(),
        segment=segment,
        symbol=symbol,
        expiry=expiry,
        option_type=option_type,
        strike=strike,
        side=_SIDES[side_label],
        quantity=quantity,
        price=price,
        quoted_price=quoted_price,
        product=row["Order"].strip() or None,
        raw_hash=raw_hash,
    )


def parse(source: Iterable[str] | str | Path, *, trader_id: str, raw_hash: str) -> ParseResult:
    """Read a Dhan tradebook export into fills.

    ``source`` is a path, or any iterable of CSV lines (the first being the header).
    Raises ``ValueError`` if the header is not this format's -- adapter selection is
    by exact header match, so a near-miss is a different export, not a bad row.
    """
    if isinstance(source, (str, Path)) and Path(source).exists():
        with Path(source).open(newline="", encoding="utf-8-sig") as handle:
            lines = handle.read().splitlines()
    else:
        lines = list(source)  # type: ignore[arg-type]

    if not lines:
        raise ValueError("empty file: no header row")

    reader = csv.reader(lines)
    header = tuple(h.strip() for h in next(reader))
    if header != HEADER:
        raise ValueError(
            f"header does not match {FORMAT_ID}\n  expected: {HEADER}\n  found:    {header}"
        )

    fills: list[Fill] = []
    rejected: list[Rejection] = []
    rows_in = 0

    for offset, values in enumerate(reader, start=2):
        if not any(v.strip() for v in values):
            continue  # a blank trailing line is not a row
        rows_in += 1
        raw = ",".join(values)
        if len(values) != len(HEADER):
            rejected.append(
                Rejection(offset, f"expected {len(HEADER)} columns, found {len(values)}", raw)
            )
            continue
        row = dict(zip(HEADER, values))
        try:
            fills.append(_parse_row(row, trader_id=trader_id, raw_hash=raw_hash))
        except RowRejected as exc:
            rejected.append(Rejection(offset, str(exc), raw))
        # A broad catch on purpose: an unforeseen failure must become a recorded
        # Rejection, never a lost row or an aborted import (s4.2, no silent drops).
        except Exception as exc:  # noqa: BLE001
            rejected.append(Rejection(offset, f"{type(exc).__name__}: {exc}", raw))

    fills.sort(key=lambda f: (f.ts, f.contract_key, f.side.value))

    return ParseResult(
        format_id=FORMAT_ID,
        rows_in=rows_in,
        fills=fills,
        rejected=rejected,
        fees_available=False,  # this export carries no charges column
    )
