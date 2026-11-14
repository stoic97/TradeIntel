"""What one trade was charged, calculated, not read from his broker (TICKET-912).

RED stub: the signatures only. GREEN fills them in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from services.production.charges import rates as R

ZERO = Decimal(0)


def rate_segment(exchange: str, segment: str, *, same_day: bool) -> R.Segment | None:
    return None


@dataclass(frozen=True)
class TripCharges:
    """What one trade was charged, or why it can't be said."""

    covered: bool
    total: Decimal = ZERO
    by_component: dict[str, Decimal] = field(default_factory=dict)
    reason: str | None = None


def order_charges(seg: R.Segment, side: str, value: Decimal, on: date, *, broker: str,
                  own: Decimal | None = None, as_of: date | None = None,
                  table: tuple | None = None) -> dict[str, Decimal]:
    return {}


def trip_charges(*, broker: str, exchange: str, segment: str, direction: str,
                 entry_ts: datetime, exit_ts: datetime, quantity: int,
                 entry_price: Decimal, exit_price: Decimal, own: Decimal | None = None,
                 as_of: date | None = None, table: tuple | None = None) -> TripCharges:
    return TripCharges(covered=True)


def share_day(day_total: Decimal, ours: list[Decimal | None]) -> list[Decimal]:
    return []
