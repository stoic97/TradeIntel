"""TICKET-907 (FB-0168; C2 ruled 17 Nov): the number in points per lot, one line per book.

A point on one lot is worth the instrument profile's currency_per_point at today's lot
(MCX_CRUDEOIL 100, MCX_CRUDEOILM 10, NSE_NIFTY 65); the loader puts it on each trip as
point_value. CRUDEOIL and CRUDEOILM are one book (book_of) but ten times apart a point, so
the crude line names both.

Hand-worked, against 2000:
  crude: CRUDEOIL 2000/100 = 20 points (3 trades), CRUDEOILM 2000/10 = 200 points (1 trade)
  NIFTY: 2000/65 = 30.769... -> 30.77 points (1 trade)
  RELIANCE shares (EQ) -> no line: a share has no lot
  a trip with no point value -> no line: nothing to divide by
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s


def trip(tid: str, symbol: str, value: str | None, segment: str = "FUT") -> mx.Trip:
    entry = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)
    line = mx.TradeLine(
        symbol=symbol,
        segment=segment,
        side="Buy",
        quantity=1,
        entry_price=None,
        exit_price=None,
        net=Decimal(-100),
    )
    return mx.Trip(
        trip_id=tid,
        symbol=symbol,
        trading_day="2026-09-01",
        entry_ts=entry,
        exit_ts=entry + timedelta(minutes=30),
        holding_seconds=1800,
        net=Decimal(-100),
        lots=1,
        risk_unit_source=s.RiskUnitSourceV1.PREMIUM_PAID,
        is_option=segment == "OPT",
        lines=(line,),
        point_value=Decimal(value) if value else None,
    )


def history() -> list[mx.Trip]:
    return [
        trip("a", "CRUDEOIL", "100"),
        trip("b", "CRUDEOIL", "100", "OPT"),
        trip("c", "CRUDEOIL", "100"),
        trip("m", "CRUDEOILM", "10"),
        trip("d", "NIFTY", "65", "OPT"),
        trip("e", "RELIANCE", "1", "EQ"),
        trip("f", "MYSTERY", None),
    ]


def test_a_trip_carries_no_point_value_unless_the_loader_gives_it_one():
    assert trip("x", "CRUDEOIL", None).point_value is None


def test_one_line_per_book_each_contract_with_its_own_points():
    rows = mx.points_per_lot(history(), Decimal(2000))
    assert [(r.book, r.parts) for r in rows] == [
        ("crude", (("CRUDEOIL", Decimal(20)), ("CRUDEOILM", Decimal(200)))),
        ("NIFTY", (("NIFTY", Decimal("30.77")),)),
    ]


def test_the_book_he_trades_most_comes_first():
    rows = mx.points_per_lot(history(), Decimal(2000))
    assert [(r.book, r.trades) for r in rows] == [("crude", 4), ("NIFTY", 1)]


def test_shares_and_instruments_with_no_point_value_have_no_line():
    books = {r.book for r in mx.points_per_lot(history(), Decimal(2000))}
    assert "RELIANCE" not in books and "MYSTERY" not in books


def test_no_trades_no_lines():
    assert mx.points_per_lot([], Decimal(2000)) == []


@pytest.mark.parametrize("bad", ["0", "-5"])
def test_a_number_of_zero_or_less_is_refused(bad):
    with pytest.raises(ValueError):
        mx.points_per_lot(history(), Decimal(bad))
