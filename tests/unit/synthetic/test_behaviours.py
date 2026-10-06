"""Step A, cycle 4 - the three hooks and their first three behaviours.

What must hold, from the spec rather than from a run:

* Twin pairing (§12.2). A behaviour that never acts leaves every trade identical,
  and before a behaviour first acts the two twins are the same trader.
* Labels are ground truth. ``flags`` is exactly where the condition held at entry,
  recomputed here from resolved trips only; ``applied`` is a subset of ``flags``.
* Each mechanism does what it says, and only on the trips it applied to.
"""
import numpy as np
import pytest

from services.research.evaluation.synthetic.behaviours import (
    b2_post_loss_expectancy,
    e5_holding_asymmetry,
    r2_post_loss_size_up,
)
from services.research.evaluation.synthetic.market import generate_bars
from services.research.evaluation.synthetic.trader import simulate_trader

BARS = generate_bars(seed=1, n_days=1200)
N = 3000
BASE = simulate_trader(BARS, seed=5, n_trades=N)


def _path(trips):
    """A trip's trade, without its labels."""
    return [(t.entry_idx, t.exit_idx, t.direction, t.r_multiple, t.size) for t in trips]


def _r(trips):
    return np.array([t.r_multiple for t in trips])


def test_a_behaviour_that_never_acts_leaves_every_trade_identical():
    twin = simulate_trader(BARS, 5, N, behaviours=(b2_post_loss_expectancy(1.0, prevalence=0.0),))
    assert _path(twin) == _path(BASE)
    assert any(t.flags for t in twin) and not any(t.applied for t in twin)


def test_twins_are_the_same_trader_until_the_behaviour_first_acts():
    twin = simulate_trader(BARS, 5, N, behaviours=(b2_post_loss_expectancy(1.0),))
    first = next(k for k, t in enumerate(twin) if t.applied)
    assert first > 0
    assert _path(twin[:first]) == _path(BASE[:first])
    assert twin[first].entry_idx == BASE[first].entry_idx


def test_b2_flags_exactly_the_trips_after_two_same_day_losses():
    twin = simulate_trader(BARS, 5, N, behaviours=(b2_post_loss_expectancy(0.5),))
    for k, t in enumerate(twin):
        today = [p for p in twin[:k] if p.day == t.day]
        expected = len(today) >= 2 and today[-1].r_multiple < 0 and today[-2].r_multiple < 0
        assert ("B2" in t.flags) == expected
        assert set(t.applied) <= set(t.flags)


def test_b2_drift_lowers_r_only_where_it_acts():
    twin = simulate_trader(BARS, 5, N, behaviours=(b2_post_loss_expectancy(1.0),))
    acted = _r([t for t in twin if t.applied])
    rest = _r([t for t in twin if not t.flags])
    assert len(acted) >= 200
    assert acted.mean() < -0.5  # always against the move: a large, real shortfall
    assert abs(rest.mean()) < 4 * rest.std() / np.sqrt(len(rest))  # still a zero-edge trader


def test_prevalence_acts_on_about_that_share_of_flagged_trips():
    twin = simulate_trader(BARS, 5, N, behaviours=(b2_post_loss_expectancy(1.0, prevalence=0.5),))
    flagged = [t for t in twin if t.flags]
    share = sum(bool(t.applied) for t in flagged) / len(flagged)
    assert 0.4 < share < 0.6


def test_r2_multiplies_size_exactly_on_the_trips_after_a_loss():
    twin = simulate_trader(BARS, 5, N, behaviours=(r2_post_loss_size_up(1.7),))
    assert _path(twin) != _path(BASE)  # sizes differ ...
    assert [p[:4] for p in _path(twin)] == [p[:4] for p in _path(BASE)]  # ... the trades do not
    for k, t in enumerate(twin):
        after_loss = k > 0 and twin[k - 1].r_multiple < 0
        assert ("R2" in t.applied) == after_loss
        assert t.size == (1.7 if after_loss else 1.0)


def _duration_ratio(trips):
    win = [t.exit_idx - t.entry_idx for t in trips if t.r_multiple > 0]
    loss = [t.exit_idx - t.entry_idx for t in trips if t.r_multiple < 0]
    return np.mean(win) / np.mean(loss)


def test_e5_closes_winners_early_and_never_touches_a_losing_exit():
    twin = simulate_trader(BARS, 5, N, behaviours=(e5_holding_asymmetry(0.05),))
    assert _duration_ratio(twin) < 0.67 < _duration_ratio(BASE)  # Annex A: theta_min 0.67
    for t in twin:
        if t.exit_reason in ("STOP", "TARGET"):
            continue
        held = t.exit_idx - t.entry_idx
        base_same = next((b for b in BASE if b.entry_idx == t.entry_idx), None)
        if base_same is not None and held < base_same.exit_idx - base_same.entry_idx:
            assert t.r_multiple > 0  # only a winner is ever closed early


@pytest.mark.parametrize(
    "behaviour",
    [
        b2_post_loss_expectancy(1.5),
        b2_post_loss_expectancy(0.5, prevalence=-0.1),
        r2_post_loss_size_up(0.0),
        e5_holding_asymmetry(-1.0),
    ],
)
def test_refuses_out_of_range_behaviours(behaviour):
    with pytest.raises(ValueError):
        simulate_trader(BARS, 5, 10, behaviours=(behaviour,))
