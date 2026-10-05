"""Step A, cycle 3 - the base trader (Research Spec v1.0 §12.2).

Expected values come from the policy's definition, not from a run: a stop exit
on a gapless path loses exactly 1R, a target exit makes exactly target_r, a
zero-skill trader has zero expectancy, and the stop distance may not depend on
any bar at or after entry.
"""
from dataclasses import replace
from itertools import pairwise

import numpy as np
import pytest

from services.research.evaluation.synthetic.market import Bars, generate_bars
from services.research.evaluation.synthetic.trader import (
    LONG,
    SHORT,
    TraderConfig,
    simulate_trader,
    trips_hash,
)

BARS = generate_bars(seed=1, n_days=1200)  # gapless within a day: open[i] == close[i-1]


def _r(trips):
    return np.array([t.r_multiple for t in trips])


def test_same_seed_gives_identical_trips():
    a = simulate_trader(BARS, seed=5, n_trades=300)
    b = simulate_trader(BARS, seed=5, n_trades=300)
    assert trips_hash(a) == trips_hash(b)
    assert trips_hash(a) != trips_hash(simulate_trader(BARS, seed=6, n_trades=300))


def test_exactly_n_trades_one_at_a_time_and_intraday():
    trips = simulate_trader(BARS, seed=5, n_trades=300)
    assert len(trips) == 300
    for t in trips:
        assert t.entry_idx <= t.exit_idx
        assert BARS.day[t.entry_idx] == BARS.day[t.exit_idx] == t.day
        assert t.direction in (LONG, SHORT)
    for prev, nxt in pairwise(trips):
        assert nxt.entry_idx > prev.exit_idx


def test_stop_and_target_exits_are_exactly_minus_one_and_target_r():
    cfg = TraderConfig(target_r=2.0)
    trips = simulate_trader(BARS, seed=5, n_trades=1000, config=cfg)
    stops = [t for t in trips if t.exit_reason == "STOP"]
    targets = [t for t in trips if t.exit_reason == "TARGET"]
    times = [t for t in trips if t.exit_reason == "TIME"]
    assert stops and targets and times
    assert np.allclose(_r(stops), -1.0)
    assert np.allclose(_r(targets), 2.0)
    assert ((_r(times) > -1.0) & (_r(times) < 2.0)).all()


def test_stop_gapped_through_fills_at_the_open_and_loses_more_than_1r():
    n = 60
    close = np.full(n, 100.0)
    close[35:] = 50.0
    open_ = np.concatenate([[100.0], close[:-1]])
    open_[35] = 50.0  # bar 35 opens 50% below bar 34's close: a gap between bars
    bars = Bars(
        day=np.zeros(n, dtype=np.int64),
        minute=np.arange(540, 540 + n, dtype=np.int64),
        open=open_,
        high=np.maximum(open_, close) + 0.5,
        low=np.minimum(open_, close) - 0.5,
        close=close,
    )
    # skill 1 with horizon 0 on a flat path always goes long; a long hold reaches the gap
    cfg = TraderConfig(
        trades_per_day=200, skill=1.0, skill_horizon=0, no_entry_last_min=1,
        hold_median_min=1000, hold_sigma=0.0,
    )
    (t,) = simulate_trader(bars, seed=3, n_trades=1, config=cfg)
    assert t.direction == LONG and t.entry_idx < 35
    assert t.risk_per_unit == 3.0  # 3 x ATR, ATR = the 1.0 range of every earlier bar
    assert t.exit_reason == "STOP"
    assert t.exit_price == 50.0
    assert t.r_multiple < -1.0


def test_stop_distance_uses_only_bars_before_entry():
    trips = simulate_trader(BARS, seed=5, n_trades=50)
    t = trips[10]
    high = BARS.high.copy()
    high[t.entry_idx :] *= 1.5  # wreck every bar from the entry bar onwards
    future_changed = replace(BARS, high=high)
    again = simulate_trader(future_changed, seed=5, n_trades=11)
    assert again[10].entry_idx == t.entry_idx
    assert again[10].risk_per_unit == t.risk_per_unit


def test_zero_skill_trader_has_no_edge():
    r = _r(simulate_trader(BARS, seed=5, n_trades=3000))
    se = r.std() / np.sqrt(len(r))
    assert abs(r.mean()) < 4 * se


def test_skill_creates_edge_from_the_price_path():
    zero = _r(simulate_trader(BARS, seed=5, n_trades=3000))
    skilled = _r(simulate_trader(BARS, seed=5, n_trades=3000, config=TraderConfig(skill=0.3)))
    assert skilled.mean() - zero.mean() > 0.15


def test_runs_out_of_history_loudly():
    with pytest.raises(ValueError, match="ran out"):
        simulate_trader(generate_bars(seed=1, n_days=2), seed=5, n_trades=1000)


@pytest.mark.parametrize(
    "kwargs",
    [{"seed": -1}, {"n_trades": 0}, {"config": TraderConfig(skill=1.5)}],
)
def test_refuses_bad_arguments(kwargs):
    args = {"seed": 5, "n_trades": 10, **kwargs}
    with pytest.raises(ValueError):
        simulate_trader(BARS, **args)
