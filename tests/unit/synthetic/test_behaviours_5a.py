"""Step A, cycle 5a - seven behaviours on the existing hooks (Research Spec v1.0 §9).

Each condition is recomputed here independently, from the trip list and the bars,
and must match the ``flags`` the generator wrote on every trip. Each DRIFT
behaviour must lower R where it acted and leave the rest a zero-edge trader.
"""
import numpy as np
import pytest

from services.research.evaluation.synthetic import behaviours as bh
from services.research.evaluation.synthetic.market import generate_bars
from services.research.evaluation.synthetic.trader import simulate_trader

BARS = generate_bars(seed=1, n_days=1200)
N = 3000
REGIME = np.where((np.arange(len(BARS.day)) // (870 * 20)) % 2 == 0, "calm", "stress")


def _run(behaviour, **kw):
    return simulate_trader(BARS, 5, N, behaviours=(behaviour,), regime=REGIME, **kw)


def _same_day_before(trips, k):
    return [p for p in trips[:k] if p.day == trips[k].day]


def _bar_atr(i, n=30):
    return (BARS.high[i - n : i] - BARS.low[i - n : i]).mean()


def _vol_tercile(i):
    d = BARS.day[i]
    if d == 0:
        return 1
    past = [
        _bar_atr(j)
        for j in np.flatnonzero((BARS.day >= max(0, d - 5)) & (BARS.day < d))
        if j >= 30
    ]
    lo, hi = np.percentile(past, [100 / 3, 200 / 3])
    return int(_bar_atr(i) > lo) + int(_bar_atr(i) > hi)


CASES = {
    "B5": (bh.b5_sequence_decay(1.0), lambda tr, k: len(_same_day_before(tr, k)) >= 2),
    "B12": (
        bh.b12_bad_start_day(1.0),
        lambda tr, k: len(s := _same_day_before(tr, k)) >= 2
        and s[0].r_multiple < 0
        and s[1].r_multiple < 0,
    ),
    "S1": (
        bh.s1_session_expectancy(1.0),
        lambda tr, k: BARS.minute[tr[k].entry_idx] >= 17 * 60,
    ),
    "S5": (
        bh.s5_regime_expectancy(1.0, "stress"),
        lambda tr, k: REGIME[tr[k].entry_idx] == "stress",
    ),
    "S10": (
        bh.s10_event_trading(1.0),
        lambda tr, k: tr[k].day % 5 == 2
        and 19 * 60 + 15 <= BARS.minute[tr[k].entry_idx] <= 20 * 60 + 30,
    ),
    "S11": (bh.s11_edge_decay(1.0), lambda tr, k: k >= N - 100),
    "R8": (bh.r8_high_vol_drift(1.0), lambda tr, k: _vol_tercile(tr[k].entry_idx) == 2),
}


@pytest.mark.parametrize("test_id", sorted(CASES))
def test_flags_match_an_independent_recomputation_of_the_condition(test_id):
    behaviour, expected = CASES[test_id]
    trips = _run(behaviour)
    k_range = range(0, N, 7) if test_id == "R8" else range(N)  # R8's check is slow
    for k in k_range:
        assert (test_id in trips[k].flags) == expected(trips, k), (test_id, k)


@pytest.mark.parametrize("test_id", sorted(CASES))
def test_drift_lowers_r_only_where_it_acts(test_id):
    trips = _run(CASES[test_id][0])
    acted = np.array([t.r_multiple for t in trips if t.applied])
    rest = np.array([t.r_multiple for t in trips if not t.flags])
    assert len(acted) >= 30
    assert acted.mean() < -0.5
    assert abs(rest.mean()) < 4 * rest.std() / np.sqrt(len(rest))


def test_r8_size_half_sizes_up_exactly_in_the_high_vol_tercile():
    trips = _run(bh.r8_high_vol_size(1.7))
    for t in trips[::7]:
        high = _vol_tercile(t.entry_idx) == 2
        assert t.size == (1.7 if high else 1.0)


def test_s10_follows_the_release_minute_it_is_given():
    winter = _run(bh.s10_event_trading(1.0, release_minute=21 * 60))
    for t in winter:
        m = BARS.minute[t.entry_idx]
        assert ("S10" in t.flags) == (t.day % 5 == 2 and 20 * 60 + 15 <= m <= 21 * 60 + 30)


def test_real_weekdays_replace_the_synthetic_default():
    n_days = len(np.unique(BARS.day))
    all_wed = np.full(n_days, 2)
    trips = _run(bh.s10_event_trading(1.0), weekdays=all_wed)
    flagged_days = {t.day % 5 for t in trips if t.flags}
    assert len(flagged_days) > 1  # every day is a Wednesday now, not one in five


def test_s5_without_regime_labels_is_refused():
    with pytest.raises(ValueError, match="regime"):
        simulate_trader(BARS, 5, 50, behaviours=(bh.s5_regime_expectancy(1.0, "stress"),))


@pytest.mark.parametrize("kw", [{"weekdays": np.zeros(3)}, {"regime": np.array(["a"])}])
def test_context_arrays_of_the_wrong_length_are_refused(kw):
    with pytest.raises(ValueError):
        simulate_trader(BARS, 5, 10, behaviours=(bh.b5_sequence_decay(0.5),), **kw)


def test_unknown_session_is_refused():
    with pytest.raises(ValueError, match="session"):
        bh.s1_session_expectancy(1.0, session="night")
