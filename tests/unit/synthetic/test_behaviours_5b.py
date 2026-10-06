"""Step A, cycle 5b - the seven behaviours that change the shape of a trade.

Each test states what the mechanism must do on a gapless synthetic path, where
every planted quantity has an exact value: a moved stop loses exactly 1 + extra R,
a giveback exit keeps exactly 1 - giveback of the best excursion, an add at 0.5R
against loses exactly 1.5R at the stop, and so on.
"""
from itertools import pairwise

import numpy as np
import pytest

from services.research.evaluation.synthetic import behaviours as bh
from services.research.evaluation.synthetic.market import generate_bars
from services.research.evaluation.synthetic.trader import LONG, simulate_trader

BARS = generate_bars(seed=1, n_days=1200)
N = 3000
BASE = simulate_trader(BARS, seed=5, n_trades=N)


def _run(behaviour, n=N, **kw):
    return simulate_trader(BARS, 5, n, behaviours=(behaviour,), **kw)


N_CARRY = 2000  # carried trips block next mornings, so 1,200 days hold fewer trades


def _trade(t):
    return (t.entry_idx, t.exit_idx, t.direction, t.r_multiple)


def _adverse(t, upto):
    w = slice(t.entry_idx, upto + 1)
    return BARS.low[w] if t.direction == LONG else BARS.high[w]


def _favour(t, upto):
    w = slice(t.entry_idx, upto + 1)
    return BARS.high[w] if t.direction == LONG else BARS.low[w]


def test_r1_varies_size_with_the_planted_dispersion_and_nothing_else():
    twin = _run(bh.r1_size_dispersion(0.55))
    sizes = np.array([t.size for t in twin])
    assert [_trade(t) for t in twin] == [_trade(t) for t in BASE]
    assert abs(sizes.mean() - 1.0) < 0.05
    assert abs(sizes.std() / sizes.mean() - np.sqrt(np.exp(0.55**2) - 1)) < 0.05


@pytest.mark.parametrize(
    "factory,test_id", [(bh.r7_stop_moved, "R7"), (bh.e4p_late_loss_accrual, "E4'")]
)
def test_a_stop_not_honoured_loses_exactly_one_plus_extra_r(factory, test_id):
    twin = _run(factory(1.0))
    stops = [t for t in twin if t.exit_reason == "STOP"]
    assert stops
    assert np.allclose([t.r_multiple for t in stops], -2.0)
    assert all(t.stop_moved for t in stops)
    for t in twin:  # stop_moved means the original stop was reached before the exit
        reached = (t.direction * (_adverse(t, t.exit_idx) - t.stop_price) <= 0).any()
        assert t.stop_moved == reached
        assert test_id in t.applied


def test_e2_keeps_one_minus_giveback_of_the_best_excursion():
    twin = _run(bh.e2_gives_back_winners(0.6))
    gb = [t for t in twin if t.exit_reason == "GIVEBACK"]
    assert len(gb) > 500
    assert not any(t.exit_reason == "TARGET" for t in twin)
    for t in gb:
        best = (t.direction * (_favour(t, t.exit_idx - 1) - t.entry_price)).max()
        kept = t.direction * (t.exit_price - t.entry_price)
        assert best >= 0.5 * t.risk_per_unit
        if kept != pytest.approx(0.4 * best):  # the bar opened through the level ...
            assert t.exit_price == BARS.open[t.exit_idx]  # ... so it filled at the open
            assert kept < 0.4 * best


def _latency_ratio(trips):
    after_loss, after_win = [], []
    for p, q in pairwise(trips):
        if q.day == p.day:
            (after_loss if p.r_multiple < 0 else after_win).append(q.entry_idx - p.exit_idx)
    return np.mean(after_loss) / np.mean(after_win)


def test_b1_re_enters_the_planted_minutes_after_a_loss():
    twin = _run(bh.b1_post_loss_latency(2))
    forced = [(p, q) for p, q in pairwise(twin) if "B1" in q.applied]
    assert len(forced) > 300
    for p, q in forced:
        assert p.r_multiple < 0
        assert q.entry_idx == p.exit_idx + 3  # the bar after the exit, plus 2 minutes
    assert _latency_ratio(twin) < 0.67 < _latency_ratio(BASE)  # Annex A: ratio <= 0.67


def test_b1_that_never_acts_leaves_every_trade_identical():
    twin = _run(bh.b1_post_loss_latency(2, prevalence=0.0))
    assert [_trade(t) for t in twin] == [_trade(t) for t in BASE]


def test_r11_adds_at_half_r_against_and_loses_one_and_a_half_r_at_the_stop():
    twin = _run(bh.r11_adds_to_losers(1.0))
    added = [t for t in twin if t.adds]
    assert len(added) > 500
    for t in added:
        ((bar, price, units),) = t.adds
        assert t.entry_idx <= bar <= t.exit_idx
        assert price == pytest.approx(t.entry_price - t.direction * 0.5 * t.risk_per_unit)
        assert units == 1.0
        if t.exit_reason == "STOP":
            assert t.r_multiple == pytest.approx(-1.5)
    for t in twin:
        if not t.adds:  # never reached 0.5R against before it closed
            level = t.entry_price - t.direction * 0.5 * t.risk_per_unit
            assert not (t.direction * (_adverse(t, t.exit_idx) - level) <= 0).any()


def test_s6_carries_late_entries_overnight_and_nowhere_else():
    twin = _run(bh.s6_overnight_carry(0.3), n=N_CARRY)
    for t in twin:
        late = BARS.minute[t.entry_idx] >= 17 * 60
        assert ("S6" in t.flags) == late
        assert t.carried == ("S6" in t.applied)
        if t.carried:
            assert BARS.day[t.exit_idx] == t.day + 1
    assert sum(t.carried for t in twin) > 200


def test_s6_respects_days_the_series_does_not_allow_carry():
    n_days = len(np.unique(BARS.day))
    blocked = np.zeros(n_days, dtype=bool)
    twin = _run(bh.s6_overnight_carry(0.3), n=N_CARRY, carry_allowed=blocked)
    assert not any(t.carried for t in twin)
    assert not any(t.flags for t in twin)


@pytest.mark.parametrize(
    "behaviour",
    [bh.r1_size_dispersion(0.55), bh.b1_post_loss_latency(2), bh.s6_overnight_carry(0.3)],
)
def test_one_position_at_a_time_survives_every_new_mechanism(behaviour):
    twin = _run(behaviour, n=N_CARRY)
    for p, q in pairwise(twin):
        assert q.entry_idx > p.exit_idx


@pytest.mark.parametrize(
    "behaviour",
    [
        bh.e2_gives_back_winners(1.0),
        bh.b1_post_loss_latency(-1),
        bh.s6_overnight_carry(1.5),
        bh.r7_stop_moved(0.0),
        bh.r11_adds_to_losers(-1.0),
    ],
)
def test_refuses_out_of_range_behaviours(behaviour):
    with pytest.raises(ValueError):
        simulate_trader(BARS, 5, 10, behaviours=(behaviour,))
