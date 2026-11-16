"""TICKET-907 (FB-0170, T-001's R36): his capital as a share, not a figure in isolation.

His worst day, his deepest fall and his biggest premium, each as a share of the capital he
entered. Every figure is his own, from the trades already loaded; nothing is estimated.

Hand-worked, capital 1,00,000:
  day  result  running
  D1   +1000    1000   high point
  D2   -3000   -2000   worst day: 3000 -> 3%
  D3    +500   -1500
  D4   -2500   -4000   deepest fall: 1000 down to -4000 = 5000, D1 to D4 -> 5%
  D5   +4000       0
  D6   -1000   -1000   a fall of 2000 from D1: smaller, not the deepest
  biggest premium paid 4000 (D5's option) -> 4%
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s


def trip(tid: str, day: int, net: str, premium: str | None = None) -> mx.Trip:
    entry = datetime(2026, 9, day, 10, 0)
    exit_ = entry + timedelta(minutes=30)
    return mx.Trip(
        trip_id=tid, symbol="WIDGETOIL", trading_day=entry.date().isoformat(),
        entry_ts=entry, exit_ts=exit_, holding_seconds=1800, net=Decimal(net), lots=1,
        risk_unit_source=s.RiskUnitSourceV1.PREMIUM_PAID,
        is_option=premium is not None, premium=Decimal(premium) if premium else None,
    )


def history() -> list[mx.Trip]:
    return [trip("a", 1, "1000", premium="1200"), trip("b", 2, "-3000"),
            trip("c", 3, "500"), trip("d", 4, "-2500"),
            trip("e", 5, "4000", premium="4000"), trip("f", 6, "-1000")]


CAPITAL = Decimal("100000")


def test_the_deepest_fall_is_from_a_high_point_to_the_lowest_after_it():
    fall = mx.deepest_fall(history())
    assert fall.amount == Decimal("5000")
    assert (fall.from_day, fall.to_day) == ("2026-09-01", "2026-09-04")


def test_a_fall_from_the_first_day_starts_at_the_start_of_the_file():
    fall = mx.deepest_fall([trip("x", 1, "-700"), trip("y", 2, "200")])
    assert fall.amount == Decimal("700")
    assert fall.from_day is None and fall.to_day == "2026-09-01"


def test_a_history_that_never_fell_has_no_fall():
    assert mx.deepest_fall([trip("x", 1, "100"), trip("y", 2, "50")]) is None


def test_each_figure_as_a_share_of_his_capital():
    shares = mx.capital_shares(history(), CAPITAL)
    assert shares.worst_day.trading_day == "2026-09-02"
    assert (-shares.worst_day.net, shares.worst_day_percent) == (Decimal("3000"), Decimal(3))
    assert (shares.fall.amount, shares.fall_percent) == (Decimal("5000"), Decimal(5))
    assert (shares.premium, shares.premium_percent) == (Decimal("4000"), Decimal(4))
    assert shares.state is s.ResultState.COUNTED_FACT


def test_the_worst_day_is_the_scopes_own_worst_day():
    shares = mx.capital_shares(history(), CAPITAL)
    assert shares.worst_day == mx.five_worst_days(history()).days[0]


def test_a_part_that_is_really_there_is_never_shown_as_none_percent():
    shares = mx.capital_shares(history(), Decimal("10000000"))
    assert shares.premium_percent == Decimal(1)


def test_no_capital_shows_the_figures_and_no_share():
    shares = mx.capital_shares(history(), None)
    assert shares.fall.amount == Decimal("5000")
    assert shares.worst_day_percent is None
    assert shares.fall_percent is None
    assert shares.premium_percent is None


def test_no_losing_day_and_no_option_leave_those_figures_out():
    shares = mx.capital_shares([trip("x", 1, "100"), trip("y", 2, "50")], CAPITAL)
    assert shares.worst_day is None and shares.fall is None and shares.premium is None


def test_no_trades_is_not_a_zero():
    assert mx.capital_shares([], CAPITAL).state is s.ResultState.INSUFFICIENT_SAMPLE