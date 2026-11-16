"""TICKET-907 (FB-0168): the number he is considering, in points per lot, per instrument he trades.

A point on one lot is worth the instrument profile's currency_per_point (MCX_CRUDEOIL: 100,
NSE_NIFTY: 65), at today's lot. The loader puts it on each trip as point_value.

Hand-worked, against 2000:
  CRUDEOIL 100/point -> 20 points      three trades, listed first
  NIFTY     65/point -> 30.77 points   2000 / 65 = 30.769..., to two places
  RELIANCE shares (EQ) -> no row: a share has no lot to count points on
  a trip with no point value -> no row: nothing to divide by
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s


def trip(tid: str, symbol: str, value: str | None, segment: str = "FUT") -> mx.Trip:
    entry = datetime(2026, 9, 1, 10, 0)
    line = mx.TradeLine(symbol=symbol, segment=segment, side="Buy", quantity=1,
                        entry_price=None, exit_price=None, net=Decimal("-100"))
    return mx.Trip(
        trip_id=tid, symbol=symbol, trading_day="2026-09-01", entry_ts=entry,
        exit_ts=entry + timedelta(minutes=30), holding_seconds=1800, net=Decimal("-100"),
        lots=1, risk_unit_source=s.RiskUnitSourceV1.PREMIUM_PAID,
        is_option=segment == "OPT", lines=(line,),
        point_value=Decimal(value) if value else None,
    )


def history() -> list[mx.Trip]:
    return [trip("a", "CRUDEOIL", "100"), trip("b", "CRUDEOIL", "100", "OPT"),
            trip("c", "CRUDEOIL", "100"), trip("d", "NIFTY", "65", "OPT"),
            trip("e", "RELIANCE", "1", "EQ"), trip("f", "MYSTERY", None)]


def test_a_trip_carries_no_point_value_unless_the_loader_gives_it_one():
    assert trip("x", "CRUDEOIL", None).point_value is None


def test_the_number_in_points_per_lot_for_each_instrument():
    rows = {r.symbol: r.points for r in mx.points_per_lot(history(), Decimal("2000"))}
    assert rows == {"CRUDEOIL": Decimal("20"), "NIFTY": Decimal("30.77")}


def test_the_instrument_he_trades_most_comes_first():
    rows = mx.points_per_lot(history(), Decimal("2000"))
    assert [(r.symbol, r.trades) for r in rows] == [("CRUDEOIL", 3), ("NIFTY", 1)]


def test_shares_and_instruments_with_no_point_value_have_no_row():
    symbols = {r.symbol for r in mx.points_per_lot(history(), Decimal("2000"))}
    assert "RELIANCE" not in symbols and "MYSTERY" not in symbols


def test_no_trades_no_rows():
    assert mx.points_per_lot([], Decimal("2000")) == []


@pytest.mark.parametrize("bad", ["0", "-5"])
def test_a_number_of_zero_or_less_is_refused(bad):
    with pytest.raises(ValueError):
        mx.points_per_lot(history(), Decimal(bad))