"""The five worst days against all losing days, never against the net result [TICKET-812].

A net result has no floor or ceiling: gains and losses cancel, so the same five days
could read 80%, 930% or a negative number. Against losing days the figure is bounded
and means what it says. Expected values are worked by hand in each test.
"""

from __future__ import annotations

import inspect
from decimal import Decimal

from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s
from tests.unit.api.test_scope_chapters import trips_from

# Worst five -1000, -500, -500, -400, -300 = -2700. All losing days = -3000, so 90%.
# Five of ten days is 50%. Net is -3000 + 2100 = -900, which would have read 300%.
NETS = [-1000, -500, -400, -300, -200, -100, -500, 600, 700, 800]


def test_the_five_worst_days_are_measured_against_all_losing_days():
    result = mx.share_of_losses(trips_from(NETS))
    assert result.shown_as_percentage is True
    assert result.share_percent == 90


def test_a_big_winning_day_does_not_move_the_figure():
    """The ticket's test: the old figure moves with a +50,000 day, this one must not."""
    assert mx.share_of_losses(trips_from([*NETS, 50000])).share_percent == 90


def test_a_net_of_exactly_zero_still_has_a_figure():
    assert mx.share_of_losses(trips_from([-100, 100])).share_percent == 100


def test_the_rupees_are_still_the_net_ones():
    result = mx.share_of_losses(trips_from(NETS))
    assert result.five_day_sum == Decimal(-2700)
    assert result.total == Decimal(-900)


def test_the_base_rate_is_the_five_days_among_all_days():
    result = mx.share_of_losses(trips_from(NETS))
    assert (result.worst_day_count, result.trading_day_count) == (5, 10)
    assert result.days_percent == 50


def test_percentages_are_whole_numbers():
    """Worst five 50 of 75 is 66.67%, five of thirty days is 16.67%."""
    result = mx.share_of_losses(trips_from([-10] * 5 + [-1] * 25))
    assert (str(result.share_percent), str(result.days_percent)) == ("67", "17")


def test_a_real_share_never_reads_as_zero():
    """50 of 10,850 is 0.46%, which would round to a claim that the days carried nothing."""
    result = mx.share_of_losses(trips_from([-10] * 5 + [-9] * 1200))
    assert result.share_percent == 1


def test_a_winning_day_among_the_five_is_not_counted_as_a_loss():
    """Worst five -100, -50, +20, +30, +40. Losing part -150 of -150 losing days: 100%."""
    result = mx.share_of_losses(trips_from([-100, -50, 20, 30, 40, 60]))
    assert result.share_percent == 100
    assert result.five_day_sum == Decimal(-60)


def test_a_history_with_no_losing_day_has_no_percentage():
    result = mx.share_of_losses(trips_from([10, 20, 30, 40, 50, 60]))
    assert result.shown_as_percentage is False
    assert result.share_percent is None
    assert result.state is s.ResultState.COUNTED_FACT


def test_fewer_than_five_days_says_how_many():
    assert mx.share_of_losses(trips_from([-100, 50])).worst_day_count == 2


def test_nothing_in_the_metrics_divides_by_the_net_result():
    source = inspect.getsource(mx)
    assert "/ total" not in source
    assert "share_of_total" not in source
