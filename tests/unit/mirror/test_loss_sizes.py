"""The trader's own losses by size, and what an option cost [TICKET-824].

Worked by hand. Twenty losses of 100, 200 ... 2,000, ranked:
  half: the 10th is 1,000. Three in four: the 15th is 1,500. Nine in ten: the 18th is 1,800.
  One in twenty lost more than the 19th, 1,900: only the 2,000 did. Biggest: 2,000.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace

from services.production.mirror import loader
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


def _option(net, symbol="NIFTY", premium=1000):
    return replace(trips_from([net])[0], symbol=symbol, is_option=True, premium=Decimal(premium))


def _book(symbol, results, premium=1000):
    """Results of 30, 40 and 50 on a premium of 1,000: the median share is 4%."""
    return [_option(n, symbol, premium) for n in results * 4]


NIFTY = _book("NIFTY", [30, -40, 50, -30, 40, -50])


def test_a_typical_option_cost_and_its_share():
    read = mx.premium_by_book(NIFTY)
    assert [(r.book, r.paid, r.percent) for r in read] == [("NIFTY", 1000, 4)]


def test_each_book_is_read_on_its_own():
    """A blend of 1,000 and 3,000 would describe neither book."""
    crude = _book("CRUDEOIL", [60, -90, 120, -60, 90, -120], premium=3000)
    read = {r.book: (r.paid, r.percent) for r in mx.premium_by_book([*NIFTY, *crude])}
    assert read == {"NIFTY": (1000, 4), "crude": (3000, 3)}


def test_the_crude_contracts_are_one_book():
    trips = _book("CRUDEOIL", [30, -40]) + _book("CRUDEOILM", [50, -30]) + _book("CRUDEOIL", [40, -50])
    assert [(r.book, r.percent) for r in mx.premium_by_book(trips)] == [("crude", 4)]


def test_the_biggest_book_comes_first():
    small = _option(40, "BANKNIFTY")
    trips = [*[small] * 20, *NIFTY]
    assert [r.book for r in mx.premium_by_book(trips)] == ["NIFTY", "BANKNIFTY"]


def test_a_book_with_too_few_trades_is_left_out_and_not_pooled():
    trips = [*NIFTY, *[_option(40, "SENSEX")] * 19, *[_option(40, "GOLDM")] * 19]
    assert [r.book for r in mx.premium_by_book(trips)] == ["NIFTY"]


def test_only_bought_options_with_a_premium_are_read():
    shares = [replace(trips_from([500])[0], is_option=False, symbol="NIFTY")]
    no_premium = [replace(trips_from([500])[0], is_option=True, premium=None, symbol="NIFTY")]
    assert mx.premium_by_book([*NIFTY, *shares, *no_premium]) == mx.premium_by_book(NIFTY)


def test_a_level_trade_does_not_pull_the_share_down():
    assert mx.premium_by_book([*NIFTY, _option(0), _option(0)])[0].percent == 4


def test_no_book_has_enough():
    assert mx.premium_by_book([_option(40)] * 19) == []


def _leg(segment="OPT", direction="LONG", price=10, quantity=65):
    return SimpleNamespace(
        segment=segment, direction=direction, entry_price=Decimal(price), quantity=quantity
    )


def test_one_bought_option_has_a_premium():
    assert loader._premium([_leg()]) == Decimal(650)


def test_a_sold_option_has_none():
    assert loader._premium([_leg(direction="SHORT")]) is None


def test_shares_have_none():
    assert loader._premium([_leg(segment="EQ")]) is None


def test_a_spread_has_none():
    """Its cost is the two legs together, which isn't a premium paid."""
    assert loader._premium([_leg(), _leg(direction="SHORT")]) is None
