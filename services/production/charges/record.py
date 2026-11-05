"""The broker's charges beside the record: net = gross - what his file states.

Kept in its own rows. ``trip.fees``, ``trip.net`` and ``import.fees_available`` go on
saying what the tradebook said, so every metric reads what it read before; this is one
line on home, worked out when read.

**Rounding.** None. Amounts stay exact Decimals through the sum; the page's ``rupees``
filter cuts them to whole rupees when shown, so shown gross less shown charges can
differ from shown net by a rupee.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from services.production.db import models as m


@dataclass(frozen=True)
class ChargesView:
    gross: Decimal
    charges: Decimal
    net: Decimal
    covered_days: int
    trading_days: int
    unmatched_days: int

    @property
    def covers_every_day(self) -> bool:
        return self.covered_days == self.trading_days


def record_statement(
    sess: Session, trader: m.Trader, raw: m.RawFile, reader: str, days: dict[str, Decimal]
) -> None:
    sess.add(m.ChargeStatement(
        trader_id=trader.id, raw_file_id=raw.id, reader=reader,
        days=json.dumps({day: str(amount) for day, amount in days.items()}, sort_keys=True),
        uploaded_at=datetime.now(UTC),
    ))


def statement_days(sess: Session, trader: m.Trader) -> dict[str, Decimal]:
    """Every day any of his files covers; for a day in two, the later file."""
    out: dict[str, Decimal] = {}
    for stored in sess.scalars(
        select(m.ChargeStatement).where(m.ChargeStatement.trader_id == trader.id)
        .order_by(m.ChargeStatement.id)
    ):
        out.update({day: Decimal(amount) for day, amount in json.loads(stored.days).items()})
    return out


def trading_days(sess: Session, imp: m.Import) -> set[str]:
    """Every day this upload has a row on, a position's closing day included."""
    return set(sess.scalars(
        select(m.TradingDayVersion.trading_day).where(m.TradingDayVersion.import_id == imp.id)
    ))


def gross_of(sess: Session, imp: m.Import) -> Decimal:
    """The whole result as the tradebook gives it, before any charge."""
    return sum(sess.scalars(select(m.Trip.gross).where(m.Trip.import_id == imp.id)), Decimal(0))


def build(sess: Session, trader: m.Trader, imp: m.Import) -> ChargesView | None:
    """The line's figures. None when nothing applies, and then no page changes."""
    if imp.fees_available:
        return None  # the tradebook carries its own charges
    stated = statement_days(sess, trader)
    days = trading_days(sess, imp)
    covered = days & stated.keys()
    if not covered:
        return None
    gross = gross_of(sess, imp)
    charges = sum((stated[day] for day in covered), Decimal(0))
    return ChargesView(gross=gross, charges=charges, net=gross - charges,
                       covered_days=len(covered), trading_days=len(days),
                       unmatched_days=len(stated.keys() - days))
