"""Groww order history -> :class:`Fill` objects (TICKET-895).

Groww's "Order history" download is an Excel workbook: the account holder's name, his
client code and a line naming the date range, then this header on row 6, verbatim::

    Stock name,Symbol,ISIN,Type,Quantity,Value,Exchange,Exchange Order Id,Execution date and time,Order status

``intake.workbook`` turns the sheet into CSV text from the header down, so the name and
client code never reach a row. What follows was established from one real export
(204 executed share orders, NSE and BSE) rather than assumed:

**One row is one exchange order, and Value is its exact total.** There is no price
column. ``Value / Quantity`` lands on a whole paisa in every row and off the 0.05 tick in
22 of 204, which is an order filled at more than one price with the fills added up. The
price is derived from the value at full precision; nothing is multiplied back.

**Quantity counts units.** Shares are whole numbers of shares. The F&O download carries
the same header (founder, 13 Nov 2026); its quantity is declared as units in the file map,
and a quantity that is not a whole number of lots raises ``MisdeclaredQuantityUnit``
downstream rather than being read as lots.

**Times are to the minute, 12-hour, IST** (``13-11-2026 02:31 PM``). An after-market
order is stamped 09:00, before the 09:15 open: that is when it was sent, not when it
filled, and it is kept as stamped. No bar exists at 08:59, so a minute-bar fact finds no
bar for it and counts it unmeasured rather than measuring it against the wrong minute.

**There are no charges, no product type and no trade id.** ``fees_available`` is False,
so every figure from this file is gross (s4.5), as with Dhan's. The Exchange Order Id
and ISIN are read to check the row, and not kept: a Fill has no field for them.

**A contract is read from Symbol** in the exchange's own trading-symbol forms, which the
Groww API also uses: ``NIFTY25N1826000CE`` (weekly: year, month code, day), and
``BANKNIFTY25DEC27000PE`` / ``NIFTY25DECFUT`` (monthly), or Groww's own
``NSE-NIFTY-18Nov25-26000-CE``. A monthly symbol has no day; it is taken from a date in
Stock name when there is one, else the month's last expiry weekday for that exchange
(:data:`MONTHLY_EXPIRY_WEEKDAY`). A row that is neither a contract nor a share with an
ISIN is rejected with its reason, never guessed.
"""

from __future__ import annotations

import calendar
import csv
import re
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

from services.production.ctr.adapters.base import ParseResult, Rejection
from services.shared.schemas.ctr_v1 import Fill, OptionType, Segment, Side

FORMAT_ID = "groww_orders_v1"

HEADER: tuple[str, ...] = (
    "Stock name",
    "Symbol",
    "ISIN",
    "Type",
    "Quantity",
    "Value",
    "Exchange",
    "Exchange Order Id",
    "Execution date and time",
    "Order status",
)

IST = ZoneInfo("Asia/Kolkata")
ACCEPTED_STATUS = "Executed"
TIME_FORMAT = "%d-%m-%Y %I:%M %p"

_MONTHS = {m: i + 1 for i, m in enumerate(
    ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"))}
_MON = "|".join(_MONTHS)
# The exchanges' weekly month code: 1-9 for January to September, then O, N, D.
_WEEKLY_MONTH = {**{str(i): i for i in range(1, 10)}, "O": 10, "N": 11, "D": 12}

_STRIKE = r"(?P<strike>\d+(?:\.\d+)?)"
_FORMS = (
    re.compile(rf"^(?P<u>[A-Z][A-Z0-9&-]*?)(?P<yy>\d{{2}})(?P<m>[1-9OND])(?P<dd>\d{{2}}){_STRIKE}(?P<kind>CE|PE)$"),
    re.compile(rf"^(?P<u>[A-Z][A-Z0-9&-]*?)(?P<yy>\d{{2}})(?P<mon>{_MON}){_STRIKE}(?P<kind>CE|PE)$"),
    re.compile(rf"^(?P<u>[A-Z][A-Z0-9&-]*?)(?P<yy>\d{{2}})(?P<mon>{_MON})(?P<kind>FUT)$"),
    re.compile(rf"^(?P<ex>[A-Z]+)-(?P<u>[A-Z0-9&-]+?)-(?P<dd>\d{{1,2}})(?P<mon>[A-Za-z]{{3}})(?P<yy>\d{{2}})"
               rf"-(?:{_STRIKE}-(?P<kind>CE|PE)|(?P<fut>FUT))$"),
)
_NAME_DATE = re.compile(rf"\b(?P<dd>\d{{1,2}})\s*(?P<mon>{_MON})[A-Z]*\b", re.IGNORECASE)

MONTHLY_EXPIRY_WEEKDAY: dict[str, tuple[tuple[date, int], ...]] = {
    # (first expiry month it applies to, weekday: Monday=0). NSE moved every F&O expiry
    # from Thursday to Tuesday from September 2025; BSE's SENSEX went Friday (relaunch,
    # May 2023) -> Tuesday (January 2025) -> Thursday (September 2025).
    "NSE": ((date(2000, 1, 1), 3), (date(2025, 9, 1), 1)),
    "BSE": ((date(2000, 1, 1), 3), (date(2023, 5, 1), 4), (date(2025, 1, 1), 1),
            (date(2025, 9, 1), 3)),
}
"""Used only when a monthly symbol leaves the day out and Stock name doesn't give it. A
holiday that moves an expiry a day earlier is not modelled, so such a contract's date
can read a day late; it is still one contract, so pairing is unaffected."""

_SIDES = {"BUY": Side.BUY, "SELL": Side.SELL}
_OPTION_TYPES = {"CE": OptionType.CE, "PE": OptionType.PE}


class RowRejected(Exception):
    """Internal: this row cannot be parsed, for the reason given."""


def _decimal(raw: str, field_name: str) -> Decimal:
    try:
        return Decimal(raw.strip().replace(",", ""))
    except (InvalidOperation, ValueError) as exc:
        raise RowRejected(f"{field_name} is not a number: {raw!r}") from exc


def _last_weekday(year: int, month: int, weekday: int) -> date:
    last = date(year, month, calendar.monthrange(year, month)[1])
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _monthly_expiry(exchange: str, year: int, month: int, stock_name: str) -> date:
    named = _NAME_DATE.search(stock_name)
    if named and _MONTHS[named["mon"].upper()] == month:
        try:
            return date(year, month, int(named["dd"]))
        except ValueError:
            pass
    rules = MONTHLY_EXPIRY_WEEKDAY.get(exchange)
    if rules is None:
        raise RowRejected(
            f"a monthly contract on {exchange} names no expiry day, and there is no rule "
            "for that exchange's expiry day -- the contract cannot be identified")
    month_start = date(year, month, 1)
    weekday = [w for since, w in rules if since <= month_start][-1]
    return _last_weekday(year, month, weekday)


def _contract(symbol: str, stock_name: str, exchange: str
              ) -> tuple[Segment, str, date, Decimal | None, OptionType | None] | None:
    """A derivative's identity from its symbol, or None when the symbol is not one."""
    for form in _FORMS:
        match = form.match(symbol.upper())
        if match is None:
            continue
        parts = match.groupdict()
        year = 2000 + int(parts["yy"])
        if parts.get("m"):
            expiry = date(year, _WEEKLY_MONTH[parts["m"]], int(parts["dd"]))
        else:
            month = _MONTHS.get(parts["mon"].upper())
            if month is None:
                raise RowRejected(f"unknown month in {symbol!r}")
            expiry = (date(year, month, int(parts["dd"])) if parts.get("dd")
                      else _monthly_expiry(exchange, year, month, stock_name))
        if parts.get("kind") in _OPTION_TYPES:
            return (Segment.OPT, parts["u"], expiry, Decimal(parts["strike"]),
                    _OPTION_TYPES[parts["kind"]])
        return Segment.FUT, parts["u"], expiry, None, None
    return None


def _parse_row(row: dict[str, str], trader_id: str, raw_hash: str) -> Fill:
    status = row["Order status"].strip()
    if status != ACCEPTED_STATUS:
        raise RowRejected(f"status is {status!r}, not {ACCEPTED_STATUS!r}")

    side_label = row["Type"].strip().upper()
    if side_label not in _SIDES:
        raise RowRejected(f"unknown side {side_label!r}")

    exchange = row["Exchange"].strip().upper()
    if not exchange:
        raise RowRejected("exchange is empty")

    try:
        # The export carries no offset; IST is attached here, deliberately and once.
        stamped = datetime.strptime(row["Execution date and time"].strip(), TIME_FORMAT)  # noqa: DTZ007
    except ValueError as exc:
        raise RowRejected(f"unparseable date/time: {exc}") from exc
    ts = stamped.replace(tzinfo=IST)

    symbol_text = row["Symbol"].strip()
    if not symbol_text:
        raise RowRejected("symbol is empty")
    try:
        contract = _contract(symbol_text, row["Stock name"], exchange)
    except ValueError as exc:  # a day that does not exist in its month
        raise RowRejected(f"symbol {symbol_text!r} names no real expiry: {exc}") from exc
    if contract is not None:
        segment, symbol, expiry, strike, option_type = contract
        if expiry < ts.date():
            raise RowRejected(f"contract {symbol_text!r} expired {expiry}, before the trade")
    elif row["ISIN"].strip():
        segment, symbol, expiry, strike, option_type = Segment.EQ, symbol_text, None, None, None
    else:
        raise RowRejected(
            f"symbol {symbol_text!r} is not a contract name and the row has no ISIN -- "
            "the instrument cannot be identified")

    quantity_raw = _decimal(row["Quantity"], "Quantity")
    if quantity_raw != quantity_raw.to_integral_value():
        raise RowRejected(f"quantity is not whole: {quantity_raw}")
    quantity = int(quantity_raw)
    if quantity <= 0:
        raise RowRejected(f"quantity must be positive, got {quantity}")

    value = _decimal(row["Value"], "Value")
    if value <= 0:
        raise RowRejected(f"value must be positive, got {value}")

    return Fill(
        trader_id=trader_id,
        broker="groww",
        ts=ts,
        exchange=exchange,
        segment=segment,
        symbol=symbol,
        expiry=expiry,
        option_type=option_type,
        strike=strike,
        side=_SIDES[side_label],
        quantity=quantity,
        price=value / quantity,
        quoted_price=None,  # Groww shows no price, only the order's total
        trade_value=value,
        product=None,  # the order history does not say delivery or intraday
        raw_hash=raw_hash,
    )


def parse(source: Iterable[str] | str | Path, *, trader_id: str, raw_hash: str) -> ParseResult:
    """Read Groww order history, as CSV lines from its header down, into fills.

    ``source`` is a path to such text, or any iterable of its lines. Raises ``ValueError``
    if the header is not this format's: adapter selection is by exact header match.
    """
    if isinstance(source, (str, Path)) and Path(source).exists():
        with Path(source).open(newline="", encoding="utf-8-sig") as handle:
            lines = handle.read().splitlines()
    else:
        lines = list(source)  # type: ignore[arg-type]
    if not lines:
        raise ValueError("empty file: no header row")

    reader = csv.reader(lines)
    header = tuple(h.strip().lstrip("﻿") for h in next(reader))
    if header != HEADER:
        raise ValueError(
            f"header does not match {FORMAT_ID}\n  expected: {HEADER}\n  found:    {header}")

    fills: list[Fill] = []
    rejected: list[Rejection] = []
    rows_in = 0
    for offset, values in enumerate(reader, start=2):
        if not any(v.strip() for v in values):
            continue
        rows_in += 1
        raw = ",".join(values)
        if len(values) != len(HEADER):
            rejected.append(
                Rejection(offset, f"expected {len(HEADER)} columns, found {len(values)}", raw))
            continue
        try:
            fills.append(_parse_row(dict(zip(HEADER, values)), trader_id, raw_hash))
        except RowRejected as exc:
            rejected.append(Rejection(offset, str(exc), raw))
        # As Dhan's: an unforeseen failure becomes a recorded rejection, never a lost row.
        except Exception as exc:  # noqa: BLE001
            rejected.append(Rejection(offset, f"{type(exc).__name__}: {exc}", raw))

    fills.sort(key=lambda f: (f.ts, f.contract_key, f.side.value))
    return ParseResult(format_id=FORMAT_ID, rows_in=rows_in, fills=fills, rejected=rejected,
                       fees_available=False)  # the order history carries no charges
