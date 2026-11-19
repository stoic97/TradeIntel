"""Option legs and one-position builders, shared by the position tests.

Moved unchanged from tests/unit/test_positions.py so that a test file takes them from here
rather than from another test file (the cross-test import guard,
tests/unit/repo/test_no_cross_test_imports.py). Synthetic throughout.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from services.shared import positions as pos
from services.shared.schemas import ctr_v2
from services.shared.schemas.ctr_v1 import Direction, OptionType, Segment

T0 = datetime.fromisoformat("2026-03-27T10:00:00+05:30")
EXPIRY = date(2026, 3, 30)
LONG, SHORT = Direction.LONG, Direction.SHORT
CE, PE = OptionType.CE, OptionType.PE


def leg(direction, strike, entry, exit_=None, qty=65, kind=CE, seconds=0, held=3600,
        symbol="NIFTY", expiry=EXPIRY, cls=ctr_v2.RoundTrip):
    """One leg, entered at ``entry`` a unit and closed at ``exit_`` (the entry if not given)."""
    exit_ = entry if exit_ is None else exit_
    gross = (exit_ - entry) * qty if direction is LONG else (entry - exit_) * qty
    return cls(
        trader_id="T01", broker="dhan", exchange="NSE", segment=Segment.OPT, symbol=symbol,
        expiry=expiry, option_type=kind, strike=Decimal(strike), direction=direction,
        entry_ts=T0 + timedelta(seconds=seconds), exit_ts=T0 + timedelta(seconds=seconds + held),
        quantity=qty, entry_price=Decimal(entry), exit_price=Decimal(exit_),
        gross_pnl=Decimal(gross), fees=Decimal(0), fill_ids=[f"{direction.value}{strike}{seconds}"],
    )


def one(legs, **kw):
    positions = pos.group_positions(legs, **kw)
    assert len(positions) == 1
    return positions[0]