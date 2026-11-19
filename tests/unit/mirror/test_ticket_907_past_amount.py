"""TICKET-907 (FB-0168, T-001's R34): a number he is considering, against his own losses.

As he moves the number, /budget says how many of his same-day trades lost more than it and
what the part past it came to, in rupees. The count trades_past_number makes for the number
he recorded, made for a number he has not. A count of what happened: it suggests no number.

Hand-worked, against 2000:
  c lost 3000.00 -> past, 1000.00 beyond
  d lost 2500.50 -> past,  500.50 beyond
  e lost 2000.00 -> not past ("more than" is strict, as in trades_past_number)
  a, b smaller losses, f a win -> not past
  h held past the day -> left out, as every same-day figure leaves it out
  count 2, beyond 1500.50, same-day trades 6, held 1
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s


def trip(tid: str, net: str, held: bool = False, number: str | None = None) -> mx.Trip:
    entry = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)
    exit_ = entry + (timedelta(days=1) if held else timedelta(minutes=30))
    return mx.Trip(
        trip_id=tid,
        symbol="WIDGETOIL",
        trading_day="2026-09-01",
        entry_ts=entry,
        exit_ts=exit_,
        holding_seconds=int((exit_ - entry).total_seconds()),
        net=Decimal(net),
        lots=1,
        risk_unit_source=s.RiskUnitSourceV1.PREMIUM_PAID,
        number_in_force=Decimal(number) if number else None,
    )


def trips() -> list[mx.Trip]:
    return [
        trip("a", "-500"),
        trip("b", "-1200"),
        trip("c", "-3000"),
        trip("d", "-2500.50"),
        trip("e", "-2000"),
        trip("f", "800"),
        trip("h", "-9000", held=True),
    ]


def test_counts_the_trades_that_lost_more_than_the_number():
    past = mx.past_amount(trips(), Decimal(2000))
    assert past.count == 2
    assert sorted(past.trip_ids) == ["c", "d"]


def test_the_part_past_the_number_in_rupees():
    assert mx.past_amount(trips(), Decimal(2000)).beyond == Decimal("1500.50")


def test_a_loss_equal_to_the_number_is_not_past_it():
    assert "e" not in mx.past_amount(trips(), Decimal(2000)).trip_ids


def test_positions_held_past_the_day_are_left_out_and_said():
    past = mx.past_amount(trips(), Decimal(2000))
    assert "h" not in past.trip_ids
    assert past.same_day == 6
    assert past.held_past_day == 1


def test_it_reads_the_number_typed_not_the_number_recorded():
    recorded = [trip("x", "-3000", number="5000")]
    assert mx.past_amount(recorded, Decimal(2000)).count == 1


def test_above_his_biggest_loss_nothing_is_past_and_that_is_a_fact():
    past = mx.past_amount(trips(), Decimal(100000))
    assert (past.count, past.beyond) == (0, Decimal(0))
    assert past.state is s.ResultState.COUNTED_FACT


def test_no_trades_is_not_a_zero():
    assert mx.past_amount([], Decimal(2000)).state is s.ResultState.INSUFFICIENT_SAMPLE


@pytest.mark.parametrize("bad", ["0", "-1"])
def test_a_number_of_zero_or_less_is_not_a_number_to_count_against(bad):
    with pytest.raises(ValueError):
        mx.past_amount(trips(), Decimal(bad))


def test_a_trade_inside_the_number_adds_nothing_not_a_negative():
    """Pawan, 17 Nov (C1): each trade adds max(0, |loss| - number) to the part past it."""
    assert mx.past_amount([trip("u", "-1500")], Decimal(2000)).beyond == Decimal(0)
    both = mx.past_amount([trip("u", "-1500"), trip("o", "-2600")], Decimal(2000))
    assert (both.count, both.beyond) == (1, Decimal(600))
