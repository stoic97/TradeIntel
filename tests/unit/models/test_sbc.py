"""Step C, cycle 9 — simulation-based calibration, and a detector that can fail.

Section 6.4, quoting Talts et al. 2018: draw from the prior, simulate, fit, check the
true parameter's rank among the posterior draws is uniform across 1,000 replications.

**What SBC licenses**, in the spec's own words: that the inference machinery recovers
parameters *under our own assumed model*. **What it does not license:** that the model
is right. A wrong model can pass SBC beautifully. That is why M-SIM (cycle 10) exists
and why both are gates.

**The detector must be falsifiable.** An implementation that always reports uniformity
passes every run and catches nothing, which is worse than having none because it
carries authority. So the uniformity test is aimed at two posteriors that are known to
be wrong - one too narrow, one biased - and it must reject both. Those are the
positive controls, in the same spirit as section 4.4's positive control on the leakage
detector.

**Ranks are taken from thinned draws.** Posterior draws are autocorrelated; a rank
computed over 4,000 correlated draws is not a rank over 4,000 independent ones, and
the uniformity test would be reading noise it does not model. Thinning to a fixed,
smaller count is the standard remedy and it is pre-registered here rather than tuned.
"""
import numpy as np
import pytest

from services.research.evaluation import sbc
from services.research.models import m1
from services.research.models.base import FitConfig

FIT = FitConfig(draws=500, warmup=500, chains=4, seed=2)


# --- draws have to reach the caller at all ------------------------------------

def test_a_fit_can_return_its_draws_and_the_digest_ignores_them():
    """A rank, an 80% interval and P(theta < 0) all need the sample, not the summary.
    But two fits of the same data are the same fit whether or not the draws were
    kept, so the digest must not move."""
    data = m1.M1Data(
        r=np.array([0.1, -0.2, 0.3, -0.4, 0.5, -0.6]),
        condition=np.array([0.0, 1.0, 0.0, 1.0, 0.0, 1.0]),
        day=np.array([0, 0, 1, 1, 2, 2]),
    )
    plain = m1.fit(data, m1.M1Priors(), FIT)
    kept = m1.fit(data, m1.M1Priors(), FIT, keep_samples=True)
    assert plain.samples is None
    assert kept.samples is not None
    assert set(kept.samples) == set(m1.PARAMS)
    assert kept.samples["theta"].size == FIT.draws * FIT.chains
    assert plain.summary_digest() == kept.summary_digest()


# --- the rank, which is the whole measurement ---------------------------------

def test_the_rank_is_zero_below_every_draw_and_the_count_above_every_draw():
    draws = np.array([0.0, 1.0, 2.0, 3.0])
    assert sbc.rank_of(draws, truth=-1.0) == 0
    assert sbc.rank_of(draws, truth=4.0) == 4
    assert sbc.rank_of(draws, truth=1.5) == 2


def test_thinning_takes_a_fixed_count_spread_across_the_chain():
    draws = np.arange(100.0)
    thinned = sbc.thin(draws, 10)
    assert thinned.size == 10
    assert thinned[0] == 0.0
    assert len(set(thinned.tolist())) == 10


# --- the detector, and the controls that prove it can fail --------------------

def test_uniform_ranks_pass_the_uniformity_test():
    rng = np.random.default_rng(1)
    ranks = rng.integers(0, 100, size=1000)
    verdict = sbc.uniformity(ranks, n_draws=sbc.N_THIN)
    assert verdict.uniform, verdict.detail


def test_a_posterior_that_is_too_narrow_is_rejected():
    """An overconfident posterior puts the truth outside its bulk, so ranks pile at
    both ends. This is the failure that matters most: it is the shape of a model whose
    intervals lie."""
    rng = np.random.default_rng(2)
    middle = rng.integers(40, 61, size=200)
    edges = rng.choice([0, 1, 98, 99], size=800)
    verdict = sbc.uniformity(np.concatenate([middle, edges]), n_draws=sbc.N_THIN)
    assert not verdict.uniform


def test_a_biased_posterior_is_rejected():
    """A posterior centred off the truth skews the ranks one way."""
    rng = np.random.default_rng(3)
    ranks = np.clip(rng.binomial(100, 0.75, size=1000), 0, 99)
    verdict = sbc.uniformity(ranks, n_draws=sbc.N_THIN)
    assert not verdict.uniform


def test_the_uniformity_test_refuses_a_rank_outside_its_range():
    with pytest.raises(ValueError, match="rank"):
        sbc.uniformity(np.array([0, 50, 100]), n_draws=sbc.N_THIN)


# --- SBC on M1, end to end at a small replication count ----------------------

def test_sbc_accounts_for_every_replication_per_parameter():
    """The harness must lose nothing, and must not let one parameter's failure
    disqualify another's rank.

    For each parameter: ranks contributed plus times excluded equals the replication
    count — the same accounting discipline the CTR reconstruction uses, because a
    silently dropped replication biases the uniformity test it was meant to feed.

    The sampler budget is set by measurement. On a replication whose true day effect
    was 0.055, tau_day's r_hat was 1.017 at 2,000 draws and 1.003 at 4,000, so 4
    chains of 1,000 is the floor that clears the framework's gate. theta mixed well at
    every budget, which is why it must now complete nearly every replication even
    though tau_day will not (TD-020).
    """
    result = sbc.run(
        n_replications=12,
        n_thin=sbc.N_THIN,
        fit=lambda data, seed: m1.fit(
            data, m1.M1Priors(), FitConfig(1000, 1000, 4, seed), keep_samples=True
        ),
        prior_draw=m1.prior_draw,
        simulate=m1.simulate,
        params=m1.PARAMS,
        seed=5,
    )
    assert result.n_replications == 12
    assert set(result.ranks) == set(m1.PARAMS)
    for name, ranks in result.ranks.items():
        accounted = len(ranks) + result.excluded[name]
        assert accounted == 12, f"{name}: {accounted} of 12 accounted for"
        assert all(0 <= r <= sbc.N_THIN for r in ranks), name
    assert len(result.ranks["theta"]) >= 11, (
        f"theta completed only {len(result.ranks['theta'])} of 12; it mixed cleanly at "
        "every budget measured, so a shortfall here is the gating logic, not the sampler"
    )


def test_the_sbc_record_names_what_it_measured_and_what_it_lost():
    """A record that reports uniformity without reporting completion invites the exact
    mistake per-parameter gating was introduced to avoid: a clean rank histogram over a
    biased subset. So the record carries both, and ``passed`` requires both."""
    result = sbc.SBCResult(
        model="m1",
        spec_digest="abc123",
        n_replications=12,
        n_thin=sbc.N_THIN,
        ranks={"theta": [1, 2, 3]},
        excluded={"theta": 9},
        diverged_replications=0,
        refused_replications=0,
        seconds=1.0,
    )
    record = result.record()
    assert record["model"] == "m1"
    assert record["spec_digest"] == "abc123"
    assert record["n_replications"] == 12
    assert record["n_thin"] == sbc.N_THIN
    assert "theta" in record["uniformity"]
    assert record["completion"]["theta"] == 0.25
    assert record["excluded_by_parameter"]["theta"] == 9
    assert record["min_completion"] == sbc.MIN_COMPLETION
    # Three of twelve is far below the completion floor, so no verdict may be claimed
    # however the three ranks happen to fall.
    assert record["passed"] is False
    for key in ("python", "numpy", "pymc", "nutpie", "platform"):
        assert record["environment"][key], key


def test_a_bin_count_that_does_not_divide_the_ranks_is_refused():
    """The binning bug this constant exists to prevent: 51 rank values over 20 bins
    cover alternately two or three integers, so the chi-square reads its own binning
    as non-uniformity. Harmless at a dozen replications, capable of rejecting a
    calibrated model at a thousand."""
    with pytest.raises(ValueError, match="do not divide"):
        sbc.uniformity(np.array([0, 25, 50]), n_draws=50, n_bins=20)
