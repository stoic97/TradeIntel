"""Moved out of tests/unit/api/test_scope_home_verdict.py by TICKET-945, so that no test file imports another."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as sc


def t(day, net, symbol="CRUDEOIL", is_option=True, held_days=0, at="10:00"):
    entry = datetime.fromisoformat(f"{day}T{at}:00+05:30")
    exit_ts = entry + timedelta(days=held_days, minutes=10)
    lines = () if is_option else (mx.TradeLine(symbol, "EQ", "Buy", 1, None, None, Decimal(net)),)
    return mx.Trip(
        f"{symbol}-{day}-{at}",
        symbol,
        day,
        entry,
        exit_ts,
        int((exit_ts - entry).total_seconds()),
        Decimal(net),
        1,
        sc.RiskUnitSourceV1.PREMIUM_PAID,
        is_option=is_option,
        lines=lines,
    )
