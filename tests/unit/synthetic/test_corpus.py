"""Step A, cycle 6a - corpus A: the planted grid, the twins and the two null classes.

Runs on a seeded synthetic market so it needs no data file. The real-series run is
the corpus build (cycle 6b); here the structure is pinned: 153 cells exactly as
§12.2 lists them, deterministic histories, twins without behaviour, honest
``reached`` marks, and nulls with no behaviour and no edge.
"""
import math
from collections import Counter

import numpy as np
import pytest

from services.research.evaluation.synthetic import corpus as cp
from services.research.evaluation.synthetic.market import Bars
from services.research.evaluation.synthetic.trader import TraderConfig, simulate_trader, trips_hash

MARKET = cp.synthetic_market(seed=1, n_days=700)
# Research Spec v1.0 §9 core library, less S12 (its truth is the noise class), typed
# out again here so the grid is checked against the spec, not against itself.
SPEC_TESTS = {
    *("B1", "B2", "B5", "B12"),
    *("R1", "R2", "R7", "R8", "R11"),
    *("E2", "E4'", "E5"),
    *("S1", "S5", "S6", "S10", "S11"),
}


def _cell(test_id, k, n):
    return next(c for c in cp.grid() if (c.test_id, c.multiple, c.n_trades) == (test_id, k, n))


def test_the_grid_is_17_tests_by_3_sizes_by_3_lengths():
    cells = cp.grid()
    assert len(cells) == 153
    assert {c.test_id for c in cells} == SPEC_TESTS
    combos = Counter((c.test_id, c.multiple, c.n_trades) for c in cells)
    assert set(combos.values()) == {1}
    assert {c.multiple for c in cells} == {1, 2, 4}
    assert {c.n_trades for c in cells} == {100, 300, 1000}
    assert [c.index for c in cells] == list(range(153))


def test_every_history_in_the_corpus_has_its_own_seed():
    planted = [cp.planted_seed(c, r) for c in cp.grid() for r in range(cp.SEEDS_PER_CELL)]
    clean = [cp.null_seed("clean_null", i) for i in range(cp.N_CLEAN)]
    adversarial = [cp.null_seed("adversarial_null", i) for i in range(cp.N_ADVERSARIAL)]
    seeds = planted + clean + adversarial
    assert len(seeds) == 153 * 8 + 400 + 600
    assert len(set(seeds)) == len(seeds)


def test_a_planted_history_is_reproducible_and_its_twin_carries_no_behaviour():
    cell = _cell("B2", 2, 300)
    a = cp.planted_history(MARKET, cell, 3)
    b = cp.planted_history(MARKET, cell, 3)
    assert trips_hash(list(a.trips)) == trips_hash(list(b.trips))
    assert trips_hash(list(a.twin)) == trips_hash(list(b.twin))
    assert len(a.trips) == len(a.twin) == 300
    assert any(t.applied for t in a.trips)
    assert not any(t.flags for t in a.twin)
    assert a.truth["n_applied"] == sum(bool(t.applied) for t in a.trips)


def test_every_short_cell_builds_and_plants_something():
    for cell in (c for c in cp.grid() if c.n_trades == 100 and c.multiple == 4):
        h = cp.planted_history(MARKET, cell, 0)
        assert len(h.trips) == 100
        if cell.test_id not in ("S10", "S11"):  # rare by construction: §12.5 measures it
            assert h.truth["n_flagged"] > 0, cell.test_id


def test_a_size_the_mechanism_cannot_reach_is_marked_not_reached():
    def reached(t, k):
        return cp.planted_history(MARKET, _cell(t, k, 100), 0).planting.reached

    assert reached("B2", 2) and not reached("B2", 4)  # 1.0R needs p > 1 at 0.78R per unit p
    assert reached("B12", 1) and not reached("B12", 2)
    assert reached("E5", 1) and not reached("E5", 2) and not reached("E5", 4)
    assert all(reached("R2", k) and reached("R7", k) and reached("R1", k) for k in (1, 2, 4))


@pytest.mark.parametrize("k", [1, 2, 4])
def test_exact_mappings_plant_exactly_the_nominal_size(k):
    def strength(t):
        return cp.planted_history(MARKET, _cell(t, k, 100), 0).planting.behaviours[0].strength

    assert strength("R2") == pytest.approx(1.25**k)
    assert strength("R7") == pytest.approx(0.25 * k)
    assert strength("E4'") == pytest.approx(0.25 * k)
    assert math.sqrt(math.exp(strength("R1") ** 2) - 1) == pytest.approx(0.6 * k)


def test_twin_measures_a_positive_avoidable_cost_for_a_strong_drift():
    h = cp.planted_history(MARKET, _cell("B5", 2, 1000), 0)
    assert h.truth["avoidable_cost_r"] > 50


def test_clean_nulls_have_no_behaviour_and_no_edge():
    nulls = [cp.clean_null(i) for i in range(30)]
    assert [h.n_trades for h in nulls[:3]] == [100, 300, 1000]
    r = np.array([t.r_multiple for h in nulls for t in h.trips])
    assert not any(t.flags or t.applied for h in nulls for t in h.trips)
    assert abs(r.mean()) < 4 * r.std() / np.sqrt(len(r))


def test_adversarial_nulls_differ_in_style_and_carry_no_behaviour():
    nulls = [cp.adversarial_null(MARKET, i) for i in range(12)]
    assert not any(t.flags or t.applied for h in nulls for t in h.trips)
    risks = {round(np.median([t.risk_per_unit for t in h.trips]), 3) for h in nulls}
    assert len(risks) > 6  # each trader has his own stop width
    assert len({h.truth["start_day"] for h in nulls}) > 6  # and his own stretch of the market


def test_a_zero_rate_wave_changes_nothing_and_a_wave_moves_the_daily_count():
    bars = MARKET.history.bars
    base = simulate_trader(bars, 9, 600)
    flat = simulate_trader(bars, 9, 600, config=TraderConfig(rate_wave=0.0))
    assert trips_hash(base) == trips_hash(flat)
    cfg = TraderConfig(trades_per_day=4.0, rate_wave=0.8, rate_period_days=60.0)
    wave = simulate_trader(bars, 9, 1500, config=cfg)
    days = np.arange(max(t.day for t in wave) + 1)
    counts = np.bincount([t.day for t in wave], minlength=len(days))
    schedule = np.sin(2 * np.pi * days / 60.0)
    assert np.corrcoef(counts, schedule)[0, 1] > 0.3


def test_standin_regime_for_a_day_uses_only_earlier_days():
    bars = MARKET.history.bars
    labels = cp.standin_regime(bars)
    cut = int(np.flatnonzero(bars.day == 400)[0])
    high = bars.high.copy()
    high[cut:] *= 3.0  # wreck day 400 onwards
    wrecked = cp.standin_regime(
        Bars(
            day=bars.day,
            minute=bars.minute,
            open=bars.open,
            high=high,
            low=bars.low,
            close=bars.close,
        )
    )
    assert (labels[: cut + 1] == wrecked[: cut + 1]).all()  # through day 400's first bar
    assert set(labels) == {"calm", "stress"}


def test_a_series_too_short_for_the_history_is_refused():
    tiny = cp.synthetic_market(seed=2, n_days=100)
    with pytest.raises(ValueError, match="too short"):
        cp.planted_history(tiny, _cell("B2", 1, 1000), 0)
