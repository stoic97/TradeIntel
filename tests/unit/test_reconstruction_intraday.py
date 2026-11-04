"""An intraday close takes that day's lots first [TICKET-789].

FIFO alone lets one share held from an earlier day take the first intraday sell, and every
later pairing shifts by a unit, so a day's loss lands on an earlier day. Synthetic rows of
the same shape as the case reported; gross worked by hand in each test.
"""

from __future__ import annotations

from decimal import Decimal

from services.production.ctr.reconstruct import reconstruct
from services.shared.schemas.ctr_v1 import Direction, Side
from tests.unit.test_reconstruction import EQ, T0, fill

DAY = 24 * 60
I, D, M = "INTRADAY", "DELIVERY", "MARGIN"


def eq(side, qty, price, minutes, product):
    return fill(side, qty, price, minutes, **EQ, product=product)


def shape(result) -> list[tuple[int, int, int, Decimal]]:
    """Entry day, exit day, quantity and gross of each trip, as day offsets from T0."""
    first = T0.date()
    return sorted(
        ((t.entry_ts.date() - first).days, (t.exit_ts.date() - first).days, t.quantity, t.gross_pnl)
        for t in result.round_trips
    )


def held_share_history():
    """One share held from day 0, then a day of 6 in and out, then a day of 12."""
    return [
        eq(Side.BUY, 1, 100, 0, D),
        eq(Side.BUY, 6, 110, 2 * DAY, I),
        eq(Side.SELL, 6, 111, 2 * DAY + 90, I),
        eq(Side.BUY, 12, 120, 4 * DAY, I),
        eq(Side.SELL, 12, 115, 4 * DAY + 20, I),
        eq(Side.SELL, 1, 130, 4 * DAY + 60, D),
    ]


def test_a_day_in_and_out_stays_on_that_day():
    trips = shape(reconstruct(held_share_history()))
    assert (2, 2, 6, Decimal(6)) in trips


def test_the_loss_lands_on_the_day_it_was_made():
    """12 at 120 sold at 115 is -60, all of it on day 4, none on day 2."""
    trips = shape(reconstruct(held_share_history()))
    assert (4, 4, 12, Decimal(-60)) in trips


def test_the_held_share_waits_for_its_own_sale():
    """Bought at 100 on day 0, sold at 130 on day 4: +30."""
    trips = shape(reconstruct(held_share_history()))
    assert (0, 4, 1, Decimal(30)) in trips


def test_the_total_does_not_move():
    """Buys 100 + 660 + 1440, sells 666 + 1380 + 130: -24, however the units pair."""
    result = reconstruct(held_share_history())
    assert sum(t.gross_pnl for t in result.round_trips) == Decimal(-24)
    assert len(result.round_trips) == 3


def test_with_no_lot_from_that_day_it_closes_the_older_one():
    """A genuine carry: nothing bought today, so the intraday sell has to reach back."""
    result = reconstruct([eq(Side.BUY, 5, 100, 0, M), eq(Side.SELL, 5, 110, DAY, I)])
    assert shape(result) == [(0, 1, 5, Decimal(50))]


def test_a_close_larger_than_the_day_takes_that_day_then_the_older_lot():
    """Sell 8: 6 from today at 110 (+60 at 120), then 2 from day 0 at 100 (+40). One trip."""
    result = reconstruct([
        eq(Side.BUY, 5, 100, 0, D),
        eq(Side.BUY, 6, 110, DAY, I),
        eq(Side.SELL, 8, 120, DAY + 30, I),
    ])
    assert shape(result) == [(0, 1, 8, Decimal(100))]
    assert [o.quantity for o in result.open_positions] == [3]


def test_a_short_day_works_the_same_way():
    """A short from day 0, then a short and cover on day 1 at +5 a unit."""
    result = reconstruct([
        eq(Side.SELL, 1, 100, 0, M),
        eq(Side.SELL, 4, 105, DAY, I),
        eq(Side.BUY, 4, 100, DAY + 30, I),
        eq(Side.BUY, 1, 90, DAY + 60, M),
    ])
    assert shape(result) == [(0, 1, 1, Decimal(10)), (1, 1, 4, Decimal(20))]
    assert all(t.direction is Direction.SHORT for t in result.round_trips)


def test_a_non_intraday_close_is_still_fifo():
    result = reconstruct([
        eq(Side.BUY, 1, 100, 0, D),
        eq(Side.BUY, 1, 110, DAY, I),
        eq(Side.SELL, 1, 120, DAY + 30, D),
    ])
    assert shape(result) == [(0, 1, 1, Decimal(20))]


def test_a_file_with_no_product_column_is_still_fifo():
    result = reconstruct([
        fill(Side.BUY, 1, 100, 0, **EQ),
        fill(Side.BUY, 1, 110, DAY, **EQ),
        fill(Side.SELL, 1, 120, DAY + 30, **EQ),
    ])
    assert shape(result) == [(0, 1, 1, Decimal(20))]


def test_the_same_fills_give_the_same_trips_in_any_order():
    fills = held_share_history()
    ids = [t.trip_id for t in reconstruct(fills).round_trips]
    assert ids == [t.trip_id for t in reconstruct(list(reversed(fills))).round_trips]
