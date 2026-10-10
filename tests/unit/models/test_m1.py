"""Step C, cycle 8 — M1, conditional expectancy, exactly as the framework fixes it.

M1 is the model behind twelve of the eighteen core tests. The framework pre-commits
its shape and its priors, so the first duty of these tests is to pin the code to the
document that is about to be hashed:

    for trip i on day d(i):
        R_i  ~ StudentT(nu, eta_i, sigma)
        eta_i = alpha + a_{d(i)} + theta * condition_i + beta . controls_i
        a_d  ~ Normal(0, tau_day)

    alpha ~ Normal(0, 0.5)      theta ~ Normal(0, 0.25)     sigma ~ HalfNormal(2)
    nu    ~ Gamma(2, 0.1)       beta  ~ Normal(0, 0.3)      (section 6.3)

**Day-level random intercepts are not decoration.** Section 6.2 was added because
Draft 1 assumed serial dependence away and its intervals were therefore too narrow.
Trades within a day share a market state. Three tests below make that claim
falsifiable, including one that records where it stops working.

**tau_day's prior is not in the framework.** Section 6.2 mandates the random
intercepts; section 6.3 names alpha, theta, sigma, nu and beta and stops.
HalfNormal(0.5) is used, matching alpha's scale because a day's shared state shifts
the level, and it is labelled arbitrary: under section 0 an arbitrary value gets one
revision window, on synthetic corpora before any partner's data is read. That window
closes at the hash.

**No closed form.** Student-t with an estimated nu and a random intercept has no
conjugate answer, so step B's trick is gone. What replaces it here: the prior is
recovered where the data cannot speak, and the structure behaves as section 6.2
claims. Simulation-based calibration at 1,000 replications (cycle 9) does the
rigorous work.
"""
from dataclasses import replace

import numpy as np
import pytest

from services.research.models import m1
from services.research.models.base import BadDiagnostics, FitConfig, FitResult, check_diagnostics

FIT = FitConfig(draws=1000, warmup=1000, chains=4, seed=3)
PRIORS = m1.M1Priors()


def _data(
    n_days=40,
    per_day=6,
    theta=-0.5,
    prevalence=0.25,
    day_sd=0.0,
    sigma=0.9,
    nu=None,
    prevalence_tracks_day=False,
    confound=0.3,
    seed=5,
):
    """A trader's history with a known conditional effect and known day structure.

    ``prevalence_tracks_day`` makes the condition fire more often on days whose
    intercept is low, which is how a day effect masquerades as a conditional effect —
    the confound section 6.2 exists to stop. ``confound`` sets how strongly: at 0.3
    every day still holds both kinds of trip, at 1.5 the condition is nearly a
    function of the day.
    """
    rng = np.random.default_rng(seed)
    day_effect = day_sd * rng.standard_normal(n_days)
    day = np.repeat(np.arange(n_days), per_day)
    n = n_days * per_day
    if prevalence_tracks_day and day_sd > 0:
        p = np.clip(prevalence - confound * day_effect, 0.02, 0.95)
        x = (rng.random(n) < np.repeat(p, per_day)).astype(float)
    else:
        x = (rng.random(n) < prevalence).astype(float)
    noise = rng.standard_t(nu, size=n) if nu is not None else rng.standard_normal(n)
    r = -0.05 + np.repeat(day_effect, per_day) + theta * x + sigma * noise
    return m1.M1Data(r=r, condition=x, day=day)


def _stub(**kw):
    base = {
        "backend": "stub",
        "spec_digest": "x",
        "posterior_mean": {"theta": 0.0},
        "posterior_sd": {"theta": 1.0},
        "r_hat": {"theta": 1.0},
        "ess": {"theta": 2000.0},
        "divergences": 0,
        "draws": 4000,
        "seconds": 1.0,
    }
    return FitResult(**{**base, **kw})


# --- pinned to the framework that is about to be hashed ------------------------

def test_the_priors_are_the_frameworks_verbatim():
    """framework_v1.yaml section 6.3. If one of these moves here without moving
    there, the engine is not running the framework whose hash it carries."""
    p = m1.M1Priors()
    assert p.alpha_sd == 0.5
    assert p.theta_sd == 0.25
    assert p.sigma_scale == 2.0
    assert (p.nu_shape, p.nu_rate) == (2.0, 0.1)
    assert p.beta_sd == 0.3
    # nu's floor is the one proposed amendment to these; see the nu_ tests below.


def test_tau_day_is_declared_arbitrary_because_the_framework_omits_it():
    """Section 6.2 mandates day-level random intercepts; section 6.3 does not give
    their scale a prior. The value is a choice and the code must say so."""
    assert m1.M1Priors().tau_day_scale == 0.5
    assert "arbitrary" in m1.TAU_DAY_PROVENANCE.lower()


@pytest.mark.parametrize(
    "field,value",
    [
        ("alpha_sd", 0.6),
        ("theta_sd", 0.2),
        ("sigma_scale", 1.0),
        ("nu_shape", 3.0),
        ("nu_rate", 0.2),
        ("beta_sd", 0.4),
        ("tau_day_scale", 1.0),
    ],
)
def test_changing_any_prior_changes_the_spec_digest(field, value):
    assert replace(PRIORS, **{field: value}).digest() != PRIORS.digest()


def test_a_condition_no_trade_ever_met_leaves_theta_at_its_prior():
    """If no trip meets the condition the data cannot speak about theta, so the
    posterior must be the prior. Catches a model that has wired theta to every trip."""
    got = m1.fit(_data(theta=0.0, prevalence=0.0, seed=4), PRIORS, FIT)
    check_diagnostics(got)
    assert got.posterior_sd["theta"] == pytest.approx(PRIORS.theta_sd, rel=0.15)
    assert abs(got.posterior_mean["theta"]) < 0.1


# --- the structure section 6.2 exists for, and where it stops working ----------

def test_tau_day_is_larger_when_days_really_differ():
    flat = m1.fit(_data(day_sd=0.0, seed=7), PRIORS, FIT)
    lumpy = m1.fit(_data(day_sd=0.6, seed=7), PRIORS, FIT)
    check_diagnostics(flat)
    check_diagnostics(lumpy)
    assert lumpy.posterior_mean["tau_day"] > 2 * flat.posterior_mean["tau_day"]


def test_day_structure_protects_theta_from_a_day_level_confound():
    """Section 6.2's justification, as a test.

    True theta is zero, days really differ, and the condition fires more often on the
    bad days. A model that cannot see the day structure credits the day effect to
    theta and reports an effect that is not there — which is how Draft 1's intervals
    came to be too confident.

    The control is *shuffled* day labels, not one day: alpha and a single day's
    intercept are additively unidentified, and relabelling every trip to one day
    produced 236 divergent transitions. A degenerate fit is not a fair comparison.
    Shuffling keeps the day count and the identification, and destroys only the
    alignment between the day effect and the condition.

    Twelve trips a day and a confound of 0.3 are chosen by reasoning, not by trying
    values: the day intercept must be well enough estimated that shrinkage leaks
    little of the day effect into the residual (at twelve trips and sigma 0.9, about a
    fifth leaks), and every day must still hold both kinds of trip so theta is
    identified from within-day contrast. Where those conditions fail, M1 cannot
    protect theta at all — the next test.
    """
    data = _data(
        n_days=50,
        per_day=12,
        theta=0.0,
        day_sd=0.5,
        prevalence_tracks_day=True,
        confound=0.3,
        seed=11,
    )
    scrambled = np.random.default_rng(29).permutation(np.asarray(data.day))
    honest = m1.fit(data, PRIORS, FIT)
    blinded = m1.fit(replace(data, day=scrambled), PRIORS, FIT)
    check_diagnostics(honest)
    check_diagnostics(blinded)
    assert abs(honest.posterior_mean["theta"]) < 3 * honest.posterior_sd["theta"]
    assert abs(blinded.posterior_mean["theta"]) > abs(honest.posterior_mean["theta"])


def test_a_condition_almost_determined_by_the_day_defeats_m1():
    """A limitation worth knowing before the library is built, not after.

    When the condition's prevalence swings from 2 to 95 per cent across days there is
    almost no within-day contrast left: theta can only be estimated from between-day
    differences, which is precisely what the day intercepts are there to block.
    Partial pooling leaves part of the day effect in the residual, theta absorbs it,
    and the model reports a large effect with a tight interval when the truth is zero
    — measured at -0.45 against a posterior sd of 0.14.

    **None of the framework's diagnostics catch it.** Zero divergences, r_hat inside
    1.01, bulk ess far above 400. It is not a sampling failure but
    non-identifiability, and the clean diagnostic report is what makes it dangerous.

    Not hypothetical for the library: several core tests have conditions that are
    day-linked by construction. S10 fires on the Wednesday EIA release, B12's outcome
    is the day itself, S1 is the session, S6 is overnight carry. For those, theta and
    the day effect are confounded by design. Carried as TD-019, and it needs a ruling
    before the hash — the remedy is either a pre-registered identifiability check per
    test or a different model for day-linked conditions.
    """
    data = _data(theta=0.0, day_sd=0.6, prevalence_tracks_day=True, confound=1.5, seed=11)
    got = m1.fit(data, PRIORS, FIT)
    check_diagnostics(got)  # clean, which is the whole point
    assert abs(got.posterior_mean["theta"]) > 3 * got.posterior_sd["theta"]


def test_nu_falls_when_the_tails_are_heavy():
    """Student-t is in the model for fat tails. If nu does not respond to them, the
    robustness is nominal."""
    gaussian = m1.fit(_data(seed=13), PRIORS, FIT)
    heavy = m1.fit(_data(nu=3.0, seed=13), PRIORS, FIT)
    check_diagnostics(gaussian)
    check_diagnostics(heavy)
    assert heavy.posterior_mean["nu"] < gaussian.posterior_mean["nu"]


def test_the_funnel_case_samples_without_divergences():
    """Many days with few trips each is the geometry that makes hierarchical models
    diverge, and the framework permits zero. A centred parameterisation fails here; a
    non-centred one does not. This is also where ADR-006 is most likely to reverse."""
    got = m1.fit(_data(n_days=120, per_day=2, day_sd=0.5, seed=17), PRIORS, FIT)
    check_diagnostics(got)
    assert got.divergences == 0


def test_a_history_on_one_day_is_refused_rather_than_fitted():
    """Found by the confound test: one day leaves alpha and that day's intercept
    additively unidentified, and the sampler returns a posterior full of divergences
    rather than an error. A trader whose qualifying trips all fall on one day cannot
    be diagnosed by M1, and saying so is the honest answer."""
    with pytest.raises(ValueError, match="day"):
        m1.fit(_data(n_days=1, per_day=60, seed=23), PRIORS, FIT)


# --- determinism and the framework's diagnostic thresholds --------------------

def test_the_same_seed_gives_the_same_posterior_summary():
    data = _data(seed=19)
    assert m1.fit(data, PRIORS, FIT).summary_digest() == m1.fit(data, PRIORS, FIT).summary_digest()


def test_the_diagnostics_gate_is_the_frameworks_three_thresholds():
    """framework_v1.yaml: rhat_max 1.01, bulk_ess_min 400, divergences 0."""
    with pytest.raises(BadDiagnostics, match="diverg"):
        check_diagnostics(_stub(divergences=1))
    with pytest.raises(BadDiagnostics, match="r_hat"):
        check_diagnostics(_stub(r_hat={"theta": 1.02}))
    with pytest.raises(BadDiagnostics, match="ess"):
        check_diagnostics(_stub(ess={"theta": 399.0}))
    check_diagnostics(_stub())


# --- nu's prior, corrected after the SBC run of 10 Oct 2026 --------------------

def test_a_nu_floor_holds_at_both_ends_when_set():
    """The floor mechanism is kept, defaulted off. It was proposed as the fix for 59
    diverged SBC replications and its pre-registered prediction failed - 4.3 per cent
    diverged against 5.9 - so it is withdrawn as a fix. Whether to floor nu on
    correctness grounds is a separate kickoff question (TD-021). Here: when a floor is
    set, neither the prior nor the posterior can fall below it; by default, the prior
    is the framework's and can."""
    floored = replace(PRIORS, nu_floor=2.0)
    rng = np.random.default_rng(31)
    assert min(m1.prior_draw(rng, floored)["nu"] for _ in range(5000)) >= 2.0
    got = m1.fit(_data(nu=3.0, seed=37), floored, FIT, keep_samples=True)
    check_diagnostics(got)
    assert got.samples is not None
    assert float(got.samples["nu"].min()) >= 2.0

    assert PRIORS.nu_floor == 0.0
    rng = np.random.default_rng(31)
    assert min(m1.prior_draw(rng)["nu"] for _ in range(5000)) < 2.0


def test_the_nu_floor_is_part_of_the_spec_digest():
    """Moving the floor must move the digest, or a fit could carry a hash for a
    prior it did not use."""
    assert replace(PRIORS, nu_floor=2.0).digest() != PRIORS.digest()


# --- parameterisation: the same model, two geometries --------------------------

def test_centred_and_non_centred_are_the_same_model():
    """The non-centred form was chosen for the funnel - weak per-day data. The SBC
    log of 10 Oct 2026 showed alpha failing at low sigma, where per-day data is
    strong and the centred form is the right one (Papaspiliopoulos, Roberts and
    Skold 2007). Before either is preferred, they must be shown to be the same model:
    identical posteriors for the reported parameter and the intercept, within five
    standard errors. They may differ only in how well the sampler moves."""
    data = _data(n_days=40, per_day=8, day_sd=0.4, sigma=1.0, seed=41)
    # Twice the usual budget on purpose: this dataset sits near the regime boundary
    # where per-day standard error is about tau_day, and the centred form failed
    # tau_day's r_hat there at 4,000 draws (1.0155). The claim under test is a shared
    # posterior target, which is what more draws let a poorer geometry reach.
    long = FitConfig(draws=2000, warmup=2000, chains=4, seed=3)
    a = m1.fit(data, PRIORS, long)
    b = m1.fit(data, PRIORS, long, centred=True)
    check_diagnostics(a)
    check_diagnostics(b)
    assert a.spec_digest == b.spec_digest  # same model, same hash
    for p in ("theta", "alpha"):
        mcse = max(a.posterior_sd[p], b.posterior_sd[p]) / np.sqrt(min(a.ess[p], b.ess[p]))
        assert a.posterior_mean[p] == pytest.approx(
            b.posterior_mean[p], abs=5 * np.sqrt(2) * mcse
        ), p
