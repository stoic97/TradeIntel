"""Moved out of tests/unit/api/test_math_of_trading.py by TICKET-945, so that no test file imports another."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s


def make(
    nets,
    minutes=None,
    year=2025,
    symbol="WIDGET",
    lots=2,
    start_id=0,
    is_option=True,
    days_held=0,
    segment=None,
):
    """One trade a day, from 1 Jan of the year, closed the same day unless days_held says not."""
    minutes = minutes or [10] * len(nets)
    start = datetime.fromisoformat(f"{year}-01-01T09:15:00+05:30")
    trips = []
    for i, (net, held) in enumerate(zip(nets, minutes, strict=True)):
        entry = start + timedelta(days=i)
        exit_ts = entry + timedelta(days=days_held, minutes=held)
        lines = ()
        if segment:
            lines = (mx.TradeLine(symbol, segment, "Buy", 1, Decimal(1), Decimal(1), Decimal(net)),)
        trips.append(
            mx.Trip(
                f"{symbol}-{year}-{start_id + i}",
                symbol,
                entry.date().isoformat(),
                entry,
                exit_ts,
                int((exit_ts - entry).total_seconds()),
                Decimal(net),
                lots,
                s.RiskUnitSourceV1.DECLARED_BUDGET,
                is_option=is_option,
                lines=lines,
            )
        )
    return trips


def only_book(trips) -> mx.BookMath:
    books = mx.math_by_book(trips)
    assert len(books) == 1
    return books[0]
