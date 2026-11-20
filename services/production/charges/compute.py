"""What one trade was charged, calculated, not read from his broker (TICKET-912).

A trade is two executed orders: the one that opened it and the one that closed it. Each
order is charged on its own date, at that date's statutory rates from ``rates.yaml``
(TICKET-911), plus the broker's brokerage from ``brokerage.yaml`` and GST on that
brokerage. GST is on brokerage, exchange charges, IPFT and the SEBI fee, never on STT, CTT
or stamp duty (the table's GST rows).

**Each order's own date picks its rates** (gate 1). An order dated before the table starts
can't be priced, and the table never falls back to today's rate, so such a trade is
**not covered**: it keeps no calculated charge and says why. Ruled 14 Nov 2026 (founder,
Q1): price every trade from the day the table starts; earlier ones stay gross, counted and
named, and are never mixed into an after-charges total.

**Equity intraday or delivery** is read from the trade, not the broker's order type: a
trade closed the same day is intraday, one held past the day is delivery
(``definitions_v1.md``, same-day vs held).

**A day his own charges file covers** (gate 6) takes his total, shared across that day's
trades in proportion to ours, so the day sums to his figure; a day where we have no figure
shares it equally (``share_day``, ruled 14 Nov 2026, Q4).

Everything is Decimal and unrounded. Rounding is for display.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from services.production.charges import brokerage as B
from services.production.charges import rates as R

IST = ZoneInfo("Asia/Kolkata")
ZERO = Decimal(0)

_EXCHANGE_SEGMENT = {
    ("NSE", "OPT"): R.Segment.NSE_OPT,
    ("NSE", "FUT"): R.Segment.NSE_FUT,
    ("BSE", "OPT"): R.Segment.BSE_OPT,
    ("BSE", "FUT"): R.Segment.BSE_FUT,
    ("MCX", "OPT"): R.Segment.MCX_OPT,
    ("MCX", "FUT"): R.Segment.MCX_FUT,
}


def _day(ts: datetime) -> date:
    return ts.astimezone(IST).date()


def rate_segment(exchange: str, segment: str, *, same_day: bool) -> R.Segment | None:
    """The rate table's segment for a trade, or None where the table has no rows for it."""
    exchange, segment = (exchange or "").upper(), (segment or "").upper()
    if segment == "EQ":
        if exchange != "NSE":
            return None
        return R.Segment.NSE_EQ_INTRADAY if same_day else R.Segment.NSE_EQ_DELIVERY
    return _EXCHANGE_SEGMENT.get((exchange, segment))


def _plan_kind(seg: R.Segment) -> str:
    if seg is R.Segment.NSE_EQ_INTRADAY:
        return "EQ_INTRADAY"
    if seg is R.Segment.NSE_EQ_DELIVERY:
        return "EQ_DELIVERY"
    return "OPT" if seg.value.endswith("_OPT") else "FUT"


@dataclass(frozen=True)
class TripCharges:
    """What one trade was charged, or why it can't be said."""

    covered: bool
    total: Decimal = ZERO
    by_component: dict[str, Decimal] = field(default_factory=dict)
    reason: str | None = None


def _uncovered(reason: str) -> TripCharges:
    return TripCharges(covered=False, reason=reason)


Orders = Sequence[tuple[Decimal, Decimal]]
"""Executed orders behind one side of a trade, each as (share of the order, the order's value).

A share is below one when an order was split across trades: Groww's order closing two
trades is one order, billed once, so each trade carries its part of that order's brokerage.
"""


def order_charges(
    seg: R.Segment,
    side: str,
    value: Decimal,
    on: date,
    *,
    broker: str,
    own: Decimal | None = None,
    as_of: date | None = None,
    table: tuple | None = None,
    orders: Orders | None = None,
) -> dict[str, Decimal]:
    """Every charge on one side of a trade, by component, unrounded. Raises
    :class:`rates.NotCovered` or :class:`brokerage.UnknownBroker` when it can't be said.

    Statutory charges are on the side's own ``value``. Brokerage is per executed order:
    one order of ``value`` unless ``orders`` says which orders it was.
    """
    statutory = R.statutory(seg, side, value, on, as_of=as_of, table=table)
    out = {component.value: amount for component, amount in statutory.items()}
    kind = _plan_kind(seg)
    billed = orders if orders is not None else ((Decimal(1), value),)
    fee = sum(
        (share * B.per_order(broker, kind, order_value, own=own) for share, order_value in billed),
        ZERO,
    )
    gst = R.rate(seg, R.Component.GST, side, on, as_of=as_of, table=table).rate
    out["BROKERAGE"] = fee
    out[R.Component.GST.value] = out.get(R.Component.GST.value, ZERO) + gst * fee
    return out


def trip_charges(
    *,
    broker: str,
    exchange: str,
    segment: str,
    direction: str,
    entry_ts: datetime,
    exit_ts: datetime,
    quantity: int,
    entry_price: Decimal,
    exit_price: Decimal,
    own: Decimal | None = None,
    as_of: date | None = None,
    table: tuple | None = None,
    entry_orders: Orders | None = None,
    exit_orders: Orders | None = None,
) -> TripCharges:
    """The charges on one trade: its opening side and its closing side, each on its own date.

    Without ``entry_orders`` / ``exit_orders`` each side is one executed order (Dhan's
    export has no order id, so that is its approximation: ruled 14 Nov 2026, Q2).
    """
    opened, closed = _day(entry_ts), _day(exit_ts)
    seg = rate_segment(exchange, segment, same_day=opened == closed)
    if seg is None:
        return _uncovered(f"the rate table has no rows for {exchange} {segment}")
    long = str(getattr(direction, "value", direction)).upper() == "LONG"
    sides = (
        ("buy" if long else "sell", entry_price * quantity, opened, entry_orders),
        ("sell" if long else "buy", exit_price * quantity, closed, exit_orders),
    )
    total: dict[str, Decimal] = {}
    try:
        for side, value, on, orders in sides:
            for component, amount in order_charges(
                seg,
                side,
                value,
                on,
                broker=broker,
                own=own,
                as_of=as_of,
                table=table,
                orders=orders,
            ).items():
                total[component] = total.get(component, ZERO) + amount
    except R.NotCovered as exc:
        return _uncovered(str(exc))
    except B.UnknownBroker as exc:
        return _uncovered(str(exc))
    return TripCharges(covered=True, total=sum(total.values(), ZERO), by_component=total)


def share_day(day_total: Decimal, ours: list[Decimal | None]) -> list[Decimal]:
    """His charges for one day, shared across that day's trades (gate 6; ruled 14 Nov, Q4).

    In proportion to our own per-trade figures; equally where any trade that day has none
    (before the rate table starts) or ours sum to nothing. The shares always sum to his
    total exactly: the last trade takes what rounding left over.
    """
    n = len(ours)
    if n == 0:
        return []
    known = [x for x in ours if x is not None]
    weights: list[Decimal] = (
        list(known) if len(known) == n and sum(known, ZERO) > 0 else [Decimal(1)] * n
    )
    whole = sum(weights, ZERO)
    shares = [day_total * w / whole for w in weights[:-1]]
    shares.append(day_total - sum(shares, ZERO))
    return shares
