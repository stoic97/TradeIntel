"""Step B, cycle 7 — the conjugate core of M1, and the two samplers that may fit it.

ADR-006 chooses between NumPyro and PyMC+nutpie. A benchmark comparing two
implementations written by the same hand measures the hand as much as the library, so
neither implementation grades the other: both are checked against the **closed-form
posterior**, which exists because this model is conjugate when sigma is known
(Developer Manual 5.4 — expected values from the specification, never from output).

This is the *conjugate core* of M1, not M1. Partial pooling across traders and an
estimated sigma arrive in step C, validated by SBC. Calling it M1 here would overclaim.

The model, for one trader:

    y_i ~ Normal(mu + delta * x_i, sigma)      sigma known
    mu    ~ Normal(prior_mu_mean, prior_mu_sd)
    delta ~ Normal(prior_delta_mean, prior_delta_sd)

x_i marks the condition (post-loss, high-vol, whichever test asks). delta is the
effect the two-part promotion criterion reads.
"""
import numpy as np
import pytest

from services.research.models import benchmark as bm
from services.research.models import conditional_effect as ce

SIGMA = 0.9
SPEC = ce.ConditionalEffectSpec(sigma=SIGMA)
FIT = ce.FitConfig(draws=1000, warmup=1000, chains=4, seed=7)

# How many Monte Carlo standard errors a sampler may miss the exact answer by.
#
# Not a matter of taste. A posterior mean estimated from N effective draws has
# standard error sd/sqrt(N); a posterior standard deviation has sd/sqrt(2N). At five
# of those a single statistic fails about once in 1.7 million runs, and this file
# asserts eight, so the suite is not flaky by construction.
#
# The first version of this file used rel=0.05 — an undeclared 2.2-sigma bound that
# duly failed on the second backend it met. Calibrated 10 Oct 2026 with five sampler
# seeds per backend on fixed data: the signed error of every estimate scattered
# around zero (five-seed averages within 0.75 mcse for both backends, means and
# sds), so there is no bias for a wider bound to hide. Measured ESS/draws was near
# 0.5 for both, which is where MIN_ESS_FRACTION comes from.
TOLERANCE_SIGMAS = 5.0
MIN_ESS_FRACTION = 0.2


def _data(n=500, true_mu=-0.05, true_delta=-0.5, prevalence=0.25, seed=11):
    """A trader with a planted 0.5R post-loss leak. The data may be random; the
    posterior it implies is not — that comes from the algebra."""
    rng = np.random.default_rng(seed)
    x = (rng.random(n) < prevalence).astype(float)
    y = true_mu + true_delta * x + SIGMA * rng.standard_normal(n)
    return y, x


Y, X = _data()


@pytest.fixture(scope="module")
def fits():
    """One fit per backend, reused — sampling is the slow part."""
    return {name: fn(SPEC, Y, X, FIT) for name, fn in sorted(ce.BACKENDS.items())}


def _stub(**kw):
    base = {
        "backend": "stub",
        "spec_digest": "x",
        "posterior_mean": {"mu": 0.0, "delta": 0.0},
        "posterior_sd": {"mu": 1.0, "delta": 1.0},
        "r_hat": {"mu": 1.0, "delta": 1.0},
        "ess": {"mu": 2000.0, "delta": 2000.0},
        "divergences": 0,
        "draws": 2000,
        "seconds": 1.0,
    }
    return ce.FitResult(**{**base, **kw})


# --- the closed form, checked without any sampler ------------------------------

def test_with_no_data_the_analytic_posterior_is_the_prior():
    post = ce.analytic_posterior(SPEC, np.array([]), np.array([]))
    assert post.mean["mu"] == pytest.approx(SPEC.prior_mu_mean)
    assert post.mean["delta"] == pytest.approx(SPEC.prior_delta_mean)
    assert post.sd["mu"] == pytest.approx(SPEC.prior_mu_sd)
    assert post.sd["delta"] == pytest.approx(SPEC.prior_delta_sd)


def test_the_analytic_posterior_matches_a_hand_computed_case():
    # One observation, y=2, at x=0, with sigma=1, prior sds 1 and 0.5.
    # precision = diag(1, 4) + [[1, 0], [0, 0]] = diag(2, 4)
    # mean      = diag(0.5, 0.25) @ (2, 0) = (1.0, 0.0)
    spec = ce.ConditionalEffectSpec(prior_mu_sd=1.0, prior_delta_sd=0.5, sigma=1.0)
    post = ce.analytic_posterior(spec, np.array([2.0]), np.array([0.0]))
    assert post.mean["mu"] == pytest.approx(1.0)
    assert post.sd["mu"] == pytest.approx(np.sqrt(0.5))
    assert post.mean["delta"] == pytest.approx(0.0)
    assert post.sd["delta"] == pytest.approx(0.5)  # no data at x=1 touches delta


# --- one spec, two backends ----------------------------------------------------

@pytest.mark.parametrize("backend", sorted(ce.BACKENDS))
def test_every_backend_fits_the_spec_it_was_given_and_nothing_else(backend, fits):
    got = fits[backend]
    assert got.backend == backend
    assert got.spec_digest == SPEC.digest()
    assert set(got.posterior_mean) == {"mu", "delta"}
    assert got.draws == FIT.draws * FIT.chains


@pytest.mark.parametrize("backend", sorted(ce.BACKENDS))
def test_every_backend_matches_the_closed_form_posterior(backend, fits):
    want = ce.analytic_posterior(SPEC, Y, X)
    got = fits[backend]
    ce.check_diagnostics(got)
    for p in ce.PARAMS:
        mcse_mean = want.sd[p] / np.sqrt(got.ess[p])
        mcse_sd = want.sd[p] / np.sqrt(2 * got.ess[p])
        assert got.posterior_mean[p] == pytest.approx(
            want.mean[p], abs=TOLERANCE_SIGMAS * mcse_mean
        )
        assert got.posterior_sd[p] == pytest.approx(
            want.sd[p], abs=TOLERANCE_SIGMAS * mcse_sd
        )


@pytest.mark.parametrize("backend", sorted(ce.BACKENDS))
def test_every_backend_turns_its_draws_into_information(backend, fits):
    """A degrading sampler still returns draws — it returns fewer independent ones,
    which widens every interval the promotion criterion reads. Both backends measured
    near half on 10 Oct 2026, so a fifth is a floor, not a target."""
    got = fits[backend]
    for p in ce.PARAMS:
        assert got.ess[p] > MIN_ESS_FRACTION * got.draws, f"{p}: {got.ess[p]} of {got.draws}"


@pytest.mark.parametrize("backend", sorted(ce.BACKENDS))
def test_the_same_seed_gives_the_same_posterior_summary(backend):
    a = ce.BACKENDS[backend](SPEC, Y, X, FIT)
    b = ce.BACKENDS[backend](SPEC, Y, X, FIT)
    assert a.summary_digest() == b.summary_digest()


def test_the_two_backends_agree_with_each_other(fits):
    assert len(fits) >= 2, "a one-backend benchmark cannot decide ADR-006"
    a, b = (fits[n] for n in sorted(fits))
    for p in ce.PARAMS:
        # Two independent estimates of the same quantity differ with sqrt(2) times
        # the standard error of either one.
        mcse = max(a.posterior_sd[p], b.posterior_sd[p]) / np.sqrt(min(a.ess[p], b.ess[p]))
        assert a.posterior_mean[p] == pytest.approx(
            b.posterior_mean[p], abs=TOLERANCE_SIGMAS * np.sqrt(2) * mcse
        )


# --- diagnostics are checked, never swallowed ----------------------------------

def test_a_fit_that_diverged_is_refused():
    with pytest.raises(ce.BadDiagnostics, match="diverg"):
        ce.check_diagnostics(_stub(divergences=1))


def test_a_fit_that_did_not_converge_is_refused():
    with pytest.raises(ce.BadDiagnostics, match="r_hat"):
        ce.check_diagnostics(_stub(r_hat={"mu": 1.0, "delta": 1.05}))


def test_a_clean_fit_passes_the_diagnostics_check():
    ce.check_diagnostics(_stub())


# --- the measurement the ADR is decided on -------------------------------------

def test_the_benchmark_record_names_its_environment_and_its_rate():
    record = bm.benchmark_record([_stub(backend="a", seconds=2.0, draws=4000)])
    assert record["rows"][0]["draws_per_second"] == pytest.approx(2000.0)
    for key in ("python", "numpy", "jax", "numpyro", "pymc", "nutpie", "arviz", "platform", "cpu_count"):
        assert record["environment"][key], key
