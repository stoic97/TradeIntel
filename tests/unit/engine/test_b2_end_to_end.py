"""Step D, cycle 11 — B2 end to end: the first real Finding.

Four pieces, each pinned to the spec rather than to a run:

* **Zones** (section 4.6, PRE-COMMIT, derived): the four-zone split as an algorithm —
  isolation = clamp(round(0.25 N), 30, 200), embargo = max(round(0.05 N), one full
  trading day), training = the rest, applied in trade order.
* **The condition** (Annex A.1): the two most recent resolved trips before entry, same
  day, were losses; population = trips with at least two same-day prior resolved trips.
  Checked on hand-built sequences for the edge cases and against the generator's own
  independent implementation of the same text.
* **Evidence arithmetic** (sections 4.6 and 5.4a): n_hold and MDE reproduce the spec's
  two tables **exactly**. Those tables are the expected values, in the document.
* **Promotion** (section 5.2): two-part - real (P_train) and big enough (m_train beyond
  theta_min); theta_hold = max(theta_min, the 20th percentile of the shrunk training
  posterior); P_hold from an isolation-only, prior-only fit; the overfit kill.

Robustness, BH, economic significance and sign agreement are later cycles. They are
carried as unevaluated gates, and no tier above Exploratory is awarded while any gate
is unevaluated - the alternative is to invent values, which is worse than waiting.
"""
import numpy as np
import pytest

from services.research.engine import evidence as ev
from services.research.engine import zones
from services.research.evaluation.synthetic import corpus as cp
from services.research.library import b2
from services.research.models.base import FitConfig

MARKET = cp.synthetic_market(seed=1, n_days=700)
FIT = FitConfig(draws=1000, warmup=1000, chains=4, seed=11)


def _cell(test_id, k, n):
    return next(c for c in cp.grid() if (c.test_id, c.multiple, c.n_trades) == (test_id, k, n))


# --- zones ---------------------------------------------------------------------

def test_isolation_is_a_quarter_clamped_to_30_and_200():
    """Section 4.6: isolation = clamp(round(0.25 N), 30, 200)."""
    assert zones.isolation_size(120) == 30  # 0.25 x 120 = 30
    assert zones.isolation_size(80) == 30  # 20 would be below the floor
    assert zones.isolation_size(400) == 100
    assert zones.isolation_size(1000) == 200  # 250 would be above the cap


def test_zones_are_in_trade_order_and_disjoint_and_cover_everything():
    days = np.repeat(np.arange(50), 4)  # 200 trips, 4 a day
    z = zones.split(days)
    assert len(z.isolation) == 50
    assert len(z.embargo) >= 10  # 0.05 x 200
    assert len(z.training) + len(z.embargo) + len(z.isolation) == 200
    assert set(z.training) | set(z.embargo) | set(z.isolation) == set(range(200))
    assert max(z.training) < min(z.embargo) < max(z.embargo) < min(z.isolation)
    assert z.isolation[-1] == 199  # isolation is the most recent trading


def test_the_embargo_spans_at_least_one_full_trading_day():
    """Trades within a day share a state (section 6.2). The embargo exists so that a
    state begun in training cannot leak into isolation, which it could if training
    and isolation shared a day across a too-thin embargo."""
    days = np.repeat(np.arange(40), 5)  # 200 trips, 5 a day; 0.05 N = 10 = exactly 2 days
    z = zones.split(days)
    embargo_days = set(days[z.embargo])
    training_days = set(days[z.training])
    assert embargo_days.isdisjoint(training_days)
    # At least one day lies wholly inside the embargo. Isolation's count is exact by
    # the section 4.6 formula and so may begin mid-day; the whole day inside the
    # embargo is what keeps training and isolation from ever sharing one.
    whole = [d for d in embargo_days if set(np.flatnonzero(days == d)) <= set(z.embargo)]
    assert whole
    assert set(days[z.isolation]).isdisjoint(training_days)


def test_a_history_too_short_to_leave_a_training_zone_is_refused():
    with pytest.raises(ValueError, match="training"):
        zones.split(np.repeat(np.arange(8), 4))  # 32 trips: isolation alone wants 30


# --- the condition -------------------------------------------------------------

def _obs(rows):
    """rows: (day, entry_at, exit_at, r)."""
    return [b2.Obs(day=d, entry_at=e, exit_at=x, r=r) for d, e, x, r in rows]


def test_the_condition_is_two_prior_same_day_losses_and_population_needs_two_priors():
    obs = _obs([
        (0, 1, 2, -1.0),  # first of the day: no priors -> outside the population
        (0, 3, 4, -1.0),  # one prior -> outside the population
        (0, 5, 6, +0.5),  # priors (-1, -1) -> condition
        (0, 7, 8, -0.5),  # priors (-1, +0.5) -> in population, not condition
        (0, 9, 10, +1.0),  # priors (+0.5, -0.5) -> in population, not condition
    ])
    in_pop, cond = b2.population_and_condition(obs)
    assert in_pop.tolist() == [False, False, True, True, True]
    assert cond.tolist() == [False, False, True, False, False]


def test_a_trip_still_open_at_entry_is_not_a_resolved_prior():
    """Resolved means exited before this entry. An overlapping trip does not count,
    however it later ends."""
    obs = _obs([
        (0, 1, 20, -1.0),  # exits after the third trip enters
        (0, 2, 3, -1.0),
        (0, 4, 5, -1.0),
        (0, 6, 7, +0.5),  # resolved priors by now: trips 2 and 3 -> condition
    ])
    in_pop, cond = b2.population_and_condition(obs)
    assert in_pop.tolist() == [False, False, False, True]
    assert cond.tolist() == [False, False, False, True]


def test_losses_do_not_carry_across_the_day_boundary():
    obs = _obs([
        (0, 1, 2, -1.0),
        (0, 3, 4, -1.0),
        (1, 1, 2, +0.5),  # new day: no same-day priors
    ])
    in_pop, cond = b2.population_and_condition(obs)
    assert in_pop.tolist() == [False, False, False]
    assert not cond.any()


def test_the_engines_condition_agrees_with_the_generators_independent_one():
    """Two implementations of Annex A.1's text, written separately: the generator
    stamps the condition into each trip's flags at entry; the engine reconstructs it
    from the resolved history. They must mark the same trips."""
    h = cp.planted_history(MARKET, _cell("B2", 2, 300), 0)
    obs = b2.from_synthetic(h.trips)
    _, cond = b2.population_and_condition(obs)
    flagged = np.array(["B2" in t.flags for t in h.trips])
    assert cond.tolist() == flagged.tolist()
    assert cond.sum() > 0


# --- evidence arithmetic, pinned to the spec's own tables -----------------------

@pytest.mark.parametrize(
    "theta_hold,expected",
    [(1.0, 2), (0.8, 3), (0.5, 7), (0.4, 11), (0.3, 20), (0.25, 28)],
)
def test_n_hold_reproduces_the_section_4_6_table(theta_hold, expected):
    """At sigma_R = 1.4 with a comparison group four times the condition group."""
    assert ev.n_hold(theta_hold, sigma_r=1.4, comparison_ratio=4.0) == expected


@pytest.mark.parametrize(
    "effect,expected",
    [(1.0, 25), (0.8, 40), (0.5, 100), (0.4, 157), (0.3, 278), (0.25, 400)],
)
def test_condition_trades_for_a_confident_null_reproduce_the_section_5_4a_table(effect, expected):
    """80% power, one-sided, with the 1.65x shuffle inflation. The table is reproduced
    exactly only when the inflation multiplies the variance; on the standard error it
    would give 165 rather than 100 for 0.5R."""
    assert ev.n_for_confident_null(effect, sigma_r=1.4, comparison_ratio=4.0) == expected


def test_mde_at_a_sample_inverts_the_table():
    assert ev.mde(n_condition=100, n_comparison=400, sigma_r=1.4) == pytest.approx(0.5, abs=0.002)
    assert ev.mde(n_condition=400, n_comparison=1600, sigma_r=1.4) == pytest.approx(0.25, abs=0.001)


# --- promotion -----------------------------------------------------------------

def _samples(mean, sd, n=4000, seed=0):
    return np.random.default_rng(seed).normal(mean, sd, n)


def test_a_real_and_large_effect_passes_both_parts():
    core = ev.statistical_core(
        train=_samples(-0.5, 0.1), hold=_samples(-0.4, 0.2), direction="<", theta_min=0.25
    )
    assert core.p_train > 0.95
    assert core.m_train < -0.25
    assert core.real and core.big_enough
    assert core.p_hold > 0.80


def test_a_real_but_small_effect_fails_the_second_part():
    core = ev.statistical_core(
        train=_samples(-0.10, 0.03), hold=_samples(-0.1, 0.05), direction="<", theta_min=0.25
    )
    assert core.real and not core.big_enough


def test_an_uncertain_effect_fails_the_first_part():
    core = ev.statistical_core(
        train=_samples(-0.5, 0.6), hold=_samples(-0.5, 0.6), direction="<", theta_min=0.25
    )
    assert not core.real and core.big_enough


def test_theta_hold_is_the_conservative_quantile_floored_at_theta_min():
    """Section 4.6: theta_hold = max(theta_min, 20th percentile of the shrunk training
    posterior) - the quantile nearest zero, because a candidate that reached the
    hold-out is the one most likely to have been flattered by selection."""
    strong = ev.statistical_core(_samples(-0.6, 0.1), _samples(-0.6, 0.1), "<", 0.25)
    assert strong.theta_hold == pytest.approx(0.6 - 0.8416 * 0.1, abs=0.01)
    weak = ev.statistical_core(_samples(-0.2, 0.1), _samples(-0.2, 0.1), "<", 0.25)
    assert weak.theta_hold == 0.25


def test_a_confident_training_fit_that_the_hold_out_contradicts_is_killed():
    """Section 5.2: P_hold < 0.50 after P_train >= 0.95 is the classic overfit
    signature, and it overrides every tier."""
    core = ev.statistical_core(_samples(-0.5, 0.1), _samples(+0.2, 0.3), "<", 0.25)
    assert core.p_train >= 0.95 and core.p_hold < 0.50
    assert core.killed


def test_no_tier_above_exploratory_while_a_gate_is_unevaluated():
    core = ev.statistical_core(_samples(-0.5, 0.1), _samples(-0.4, 0.2), "<", 0.25)
    finding = ev.assess(
        core, n_condition=80, n_comparison=320, n_condition_isolation=30, sigma_r=1.4,
        n_min=(30, 60),
    )
    assert finding.tier == "Exploratory"
    assert "robustness" in finding.pending_gates
    assert finding.n_hold == ev.n_hold(core.theta_hold, 1.4, 4.0)
    assert finding.mde > 0


def test_below_the_minimum_sample_is_not_enough_evidence_with_the_reason_stored():
    core = ev.statistical_core(_samples(-0.5, 0.1), _samples(-0.4, 0.2), "<", 0.25)
    finding = ev.assess(
        core, n_condition=12, n_comparison=320, n_condition_isolation=4, sigma_r=1.4,
        n_min=(30, 60),
    )
    assert finding.tier == "Not enough evidence yet"
    assert "n_condition" in finding.failed_gate


# --- end to end ----------------------------------------------------------------

def test_b2_fires_on_a_planted_trader_and_is_silent_on_a_clean_one():
    """The point of step D. A trader with a planted 0.5R post-loss leak: the
    statistical core fires - real, big enough, and the hold-out agrees. A clean trader:
    it does not, and the null carries its MDE rather than a clean bill."""
    planted = cp.planted_history(MARKET, _cell("B2", 2, 1000), 0)
    clean = cp.adversarial_null(MARKET, 3)

    fired = b2.run(b2.from_synthetic(planted.trips), config=FIT)
    assert fired.n_condition >= 30 and fired.n_comparison >= 60
    assert fired.core.real, fired.core.p_train
    assert fired.core.big_enough, fired.core.m_train
    assert fired.core.p_hold >= 0.65, fired.core.p_hold
    assert not fired.core.killed
    assert fired.core.theta_hold >= 0.25
    assert fired.finding.n_hold >= 1

    quiet = b2.run(b2.from_synthetic(clean.trips), config=FIT)
    assert not (quiet.core.real and quiet.core.big_enough), (quiet.core.p_train, quiet.core.m_train)
    assert quiet.finding.mde > 0
    assert "no leak larger than" in quiet.finding.null_statement
