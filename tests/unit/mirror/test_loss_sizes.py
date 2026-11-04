"""The trader's own losses by size, and what an option cost [TICKET-824].

Worked by hand. Twenty losses of 100, 200 ... 2,000, ranked:
  half: the 10th is 1,000. Three in four: the 15th is 1,500. Nine in ten: the 18th is 1,800.
  One in twenty lost more than the 19th, 1,900: only the 2,000 did. Biggest: 2,000.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from services.production.mirror import metrics as mx
from tests.unit.api.test_scope_chapters import trips_from

TWENTY = trips_from([-100 * i for i in range(1, 21)])


def test_the_sizes_are_read_off_the_ranked_losses():
    sizes = mx.loss_sizes(TWENTY)
    assert (sizes.half, sizes.three_quarters, sizes.nine_tenths) == (1000, 1500, 1800)
    assert (sizes.one_in_twenty, sizes.biggest) == (1900, 2000)


def test_winners_and_level_trades_are_not_losses():
    assert mx.loss_sizes([*TWENTY, *trips_from([5000, 0])]) == mx.loss_sizes(TWENTY)


def test_too_few_losses_say_nothing():
    assert mx.loss_sizes(TWENTY[:19]) is None


def test_or_less_rounds_up_so_it_stays_true():
    """10 of these 20 lost 100.50 or less. "100 or less" would not be true of them."""
    trips = [
        replace(t, net=Decimal("-100.50") if i < 10 else t.net) for i, t in enumerate(TWENTY)
    ]
    assert mx.loss_sizes(trips).half == 101


def _option(net, premium=1000):
    return replace(trips_from([net])[0], is_option=True, premium=Decimal(premium))


def test_a_typical_option_cost_and_its_share():
    """Premium 1,000 each. Results of 30, 40 and 50 either way: the median share is 4%."""
    trips = [_option(n) for n in [30, -40, 50, -30, 40, -50] * 4]
    read = mx.premium_paid(trips)
    assert (read.paid, read.percent) == (1000, 4)


def test_only_bought_options_with_a_premium_are_read():
    options = [_option(n) for n in [30, -40, 50, -30, 40, -50] * 4]
    shares = [replace(trips_from([500])[0], is_option=False)]
    no_premium = [replace(trips_from([500])[0], is_option=True, premium=None)]
    assert mx.premium_paid([*options, *shares, *no_premium]) == mx.premium_paid(options)


def test_a_level_trade_does_not_pull_the_share_down():
    options = [_option(n) for n in [30, -40, 50, -30, 40, -50] * 4]
    assert mx.premium_paid([*options, _option(0), _option(0)]).percent == 4


def test_too_few_options_say_nothing():
    assert mx.premium_paid([_option(40)] * 19) is None
