"""M1 — conditional expectancy, the model behind twelve of the eighteen core tests.

Exactly as Research Specification v1.0 fixes it, per trader:

    for trip i on day d(i):
        R_i   ~ StudentT(nu, eta_i, sigma)
        eta_i = alpha + a_{d(i)} + theta * condition_i + beta . controls_i
        a_d   ~ Normal(0, tau_day)

Priors, section 6.3, PRE-COMMIT:

    alpha ~ Normal(0, 0.5)      theta ~ Normal(0, 0.25)
    sigma ~ HalfNormal(2)       nu    ~ Gamma(2, 0.1)       beta ~ Normal(0, 0.3)

**theta is the whole point.** It is what the two-part promotion criterion reads: is
the effect real (P(theta beyond 0) >= 0.95) and is it big enough (shrunk training
median beyond theta_min = 0.25R).

**The hierarchy is over days, not over traders.** Section 10 puts population priors
and fingerprint strata in Phase 2, because no population exists: pooling across
traders delivers nothing until there are 50 per stratum. What pools now is the
trading day — section 6.2, added because Draft 1 assumed serial dependence away and
its intervals were therefore too narrow. Trades within a day share a market state,
and the model says so.

**Two parameterisations of one model.** Non-centred, ``a_d = tau_day * z_d`` with
``z_d ~ Normal(0, 1)``, is right when per-day data is weak - the funnel that makes a
centred model diverge, and the framework permits zero divergences. Centred,
``a_d ~ Normal(0, tau_day)`` directly, is right when per-day data is strong: the SBC
log of 10 Oct 2026 showed alpha failing its diagnostics at low sigma under the
non-centred form, the known result of Papaspiliopoulos, Roberts and Skold (2007).
Both forms give the same posterior and carry the same spec digest; they differ only
in how well the sampler moves. ``fit(..., centred=True)`` selects the second.

**Measured, 10 Oct 2026: non-centred is the default for this prior.** Over 300 SBC
replications the centred form diverged on 23 per cent and completed tau_day on 30,
against 4-6 and 85-87 for non-centred, because under tau_day ~ HalfNormal(0.5) and
sigma ~ HalfNormal(2) most prior mass sits where day effects are drowned in noise.
Centred wins only where tau_day is large relative to sigma. theta calibrates under
the non-centred form on every run. The centred option stays for that corner, and a
per-day hybrid is parked as TD-022.

**Two numbers here are not the framework's as written.** ``TAU_DAY_PROVENANCE``
covers the one the framework omits; ``NU_FLOOR_PROVENANCE`` covers the one it got
wrong, found by the SBC run of 10 Oct 2026.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass

import numpy as np

from services.research.models.base import FitConfig, FitResult, summarise

SPEC_VERSION = "m1_conditional_expectancy_v1"

PARAMS = ("alpha", "theta", "sigma", "nu", "tau_day")

MIN_DAYS = 2
"""Derived, not arbitrary. With one day, ``alpha`` and that day's intercept are
additively unidentified, and the sampler says so loudly: a 240-trip single-day history
produced 236 divergent transitions. Two is the identification floor. Whether a
particular history needs more is answered per fit by the framework's diagnostics gate
- zero divergences, r_hat, bulk ess - so no further threshold is invented here."""

NU_FLOOR_PROVENANCE = (
    "a floor on nu, parked. Proposed 10 Oct 2026 after 59 of 1,000 SBC replications "
    "diverged, on the theory that Gamma(2, 0.1)'s mass below nu = 2 - where Student-t "
    "has no variance - was the cause. The prediction recorded before the re-run was "
    "divergences near zero and alpha and tau_day completion above 0.9. The re-run at "
    "floor = 2 gave 4.3 per cent diverged against 5.9, and 87 per cent completion "
    "against 84 and 85: the prediction failed, so the floor is withdrawn as a fix and "
    "the default is the framework's value. Cost per replication halved, so the tail "
    "made fits slow rather than failed. Whether nu should be floored on correctness "
    "grounds alone - real returns have finite variance - is a separate question for "
    "the kickoff (TD-021), and it must not ride in under a fix that fixed nothing."
)

TAU_DAY_PROVENANCE = (
    "arbitrary. Section 6.2 mandates day-level random intercepts; section 6.3 gives "
    "starting values for alpha, theta, sigma, nu and beta and stops, so the scale of "
    "the day effect has no pre-committed prior. HalfNormal(0.5) matches alpha's scale, "
    "because a day's shared state shifts the level. Under section 0 an arbitrary value "
    "gets exactly one revision window - on synthetic and fund corpora, before the first "
    "partner's data is read - and that window closes at the hash lock. Carried as TD-018."
)


@dataclass(frozen=True)
class M1Priors:
    """The framework's priors. Five are PRE-COMMIT; ``tau_day_scale`` is not."""

    alpha_sd: float = 0.5
    theta_sd: float = 0.25
    sigma_scale: float = 2.0
    nu_shape: float = 2.0
    nu_rate: float = 0.1
    nu_floor: float = 0.0  # framework as written; the floor is parked, see NU_FLOOR_PROVENANCE
    beta_sd: float = 0.3
    tau_day_scale: float = 0.5  # not in the framework: see TAU_DAY_PROVENANCE

    def __post_init__(self) -> None:
        values = (
            self.alpha_sd,
            self.theta_sd,
            self.sigma_scale,
            self.nu_shape,
            self.nu_rate,
            self.beta_sd,
            self.tau_day_scale,
        )
        if min(values) <= 0:
            raise ValueError("every prior scale must be positive")
        if self.nu_floor < 0:
            raise ValueError("nu_floor cannot be negative")

    def digest(self) -> str:
        payload = {"version": SPEC_VERSION, **asdict(self)}
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


@dataclass(frozen=True, eq=False)
class M1Data:
    """One trader's history, as M1 reads it.

    ``day`` holds a day label per trip; labels need not be contiguous or sorted, and
    are remapped internally. ``condition`` is the 0/1 indicator the test defines;
    ``controls`` are the pre-registered controls and never include the condition.
    """

    r: np.ndarray
    condition: np.ndarray
    day: np.ndarray
    controls: np.ndarray | None = None

    def __post_init__(self) -> None:
        r = np.asarray(self.r, dtype=float).ravel()
        condition = np.asarray(self.condition, dtype=float).ravel()
        day = np.asarray(self.day).ravel()
        if not (r.shape == condition.shape == day.shape):
            raise ValueError(
                f"r, condition and day must align: {r.shape}, {condition.shape}, {day.shape}"
            )
        if r.size and not np.isfinite(r).all():
            raise ValueError("r contains a non-finite value")
        if not np.isin(condition, (0.0, 1.0)).all():
            raise ValueError("condition must be 0 or 1 — M1 takes an indicator, not a level")
        if self.controls is not None:
            controls = np.asarray(self.controls, dtype=float)
            if controls.ndim != 2 or controls.shape[0] != r.size:
                raise ValueError(f"controls must be (n_obs, k), got {controls.shape}")

    @property
    def n_obs(self) -> int:
        return int(np.asarray(self.r).size)

    @property
    def n_controls(self) -> int:
        return 0 if self.controls is None else int(np.asarray(self.controls).shape[1])

    def day_index(self) -> tuple[np.ndarray, int]:
        """Day labels remapped to a contiguous 0..n_days-1, and the day count."""
        day = np.asarray(self.day).ravel()
        if day.size == 0:
            return np.empty(0, dtype=int), 0
        _, index = np.unique(day, return_inverse=True)
        return index.astype(int), int(index.max()) + 1


def fit(
    data: M1Data,
    priors: M1Priors | None = None,
    config: FitConfig | None = None,
    keep_samples: bool = False,
    centred: bool = False,
) -> FitResult:
    """Fit M1 with the sampler ADR-006 chose. Timing includes compilation (ADR-006)."""
    import nutpie
    import pymc as pm

    priors = priors or M1Priors()
    config = config or FitConfig()
    day_idx, n_days = data.day_index()
    if n_days < MIN_DAYS:
        raise ValueError(
            f"M1 needs at least {MIN_DAYS} distinct days to identify the day-level "
            f"intercepts against alpha; this history has {n_days}. A diagnosis cannot "
            "be drawn from a single day's trading."
        )

    started = time.perf_counter()
    with pm.Model(coords={"day": np.arange(n_days)}) as model:
        alpha = pm.Normal("alpha", 0.0, priors.alpha_sd)
        theta = pm.Normal("theta", 0.0, priors.theta_sd)
        sigma = pm.HalfNormal("sigma", priors.sigma_scale)
        nu_excess = pm.Gamma("nu_excess", alpha=priors.nu_shape, beta=priors.nu_rate)
        nu = pm.Deterministic("nu", priors.nu_floor + nu_excess)
        tau_day = pm.HalfNormal("tau_day", priors.tau_day_scale)

        if centred:
            # Right when per-day data is strong (low sigma): the non-centred form
            # mixes poorly in alpha and tau_day there (SBC log, 10 Oct 2026).
            a_day = pm.Normal("a_day", 0.0, tau_day, dims="day")
        else:
            # Right when per-day data is weak - the funnel - and zero divergences is a
            # pre-committed threshold, not an aspiration.
            z_day = pm.Normal("z_day", 0.0, 1.0, dims="day")
            a_day = pm.Deterministic("a_day", tau_day * z_day, dims="day")

        eta = alpha + a_day[day_idx] + theta * np.asarray(data.condition, dtype=float)
        if data.n_controls:
            beta = pm.Normal("beta", 0.0, priors.beta_sd, shape=data.n_controls)
            eta = eta + pm.math.dot(np.asarray(data.controls, dtype=float), beta)

        pm.StudentT("R", nu=nu, mu=eta, sigma=sigma, observed=np.asarray(data.r, dtype=float))

    trace = nutpie.sample(
        nutpie.compile_pymc_model(model),
        draws=config.draws,
        tune=config.warmup,
        chains=config.chains,
        seed=config.seed,
        progress_bar=False,
    )
    seconds = time.perf_counter() - started

    return summarise(
        backend="pymc_nutpie",
        spec_digest=priors.digest(),
        samples={p: np.asarray(trace.posterior[p].values) for p in PARAMS},
        divergences=int(np.asarray(trace.sample_stats["diverging"].values).sum()),
        seconds=seconds,
        params=PARAMS,
        keep_samples=keep_samples,
    )


# ---------------------------------------------------------------- SBC support

SIM_N_DAYS = 40
SIM_PER_DAY = 6
SIM_PREVALENCE = 0.25


def prior_draw(rng: np.random.Generator, priors: M1Priors | None = None) -> dict[str, float]:
    """One draw from M1's prior, which is where SBC gets its truth.

    This must be the same prior the model declares. If the two drift apart, SBC
    validates nothing — it would be checking the machinery against a prior the
    machinery does not use, and it would still produce a clean rank histogram.
    """
    p = priors or M1Priors()
    return {
        "alpha": float(rng.normal(0.0, p.alpha_sd)),
        "theta": float(rng.normal(0.0, p.theta_sd)),
        "sigma": float(abs(rng.normal(0.0, p.sigma_scale))),  # HalfNormal
        "nu": float(p.nu_floor + rng.gamma(p.nu_shape, 1.0 / p.nu_rate)),  # numpy: scale
        "tau_day": float(abs(rng.normal(0.0, p.tau_day_scale))),
    }


def simulate(
    params: dict[str, float],
    rng: np.random.Generator,
    n_days: int = SIM_N_DAYS,
    per_day: int = SIM_PER_DAY,
    prevalence: float = SIM_PREVALENCE,
) -> M1Data:
    """Data from M1's own generative process, for the parameters given.

    The shape — 40 days of 6 trips at 25% prevalence, so 240 trips with about 60 in
    the condition — is fixed here rather than chosen per run, so SBC measures the
    machinery and not a shape picked to flatter it. It sits just inside the framework's
    minimums of 30 condition and 60 comparison.

    No clamping. ``nu ~ Gamma(2, 0.1)`` puts roughly half a per cent of draws below 1,
    where Student-t has no mean and this returns enormous values. That is what the
    pre-committed prior says, so SBC runs on it; the runner counts the replications it
    costs instead of hiding them.
    """
    n = n_days * per_day
    day = np.repeat(np.arange(n_days), per_day)
    a_day = rng.normal(0.0, params["tau_day"], size=n_days)
    x = (rng.random(n) < prevalence).astype(float)
    mu = params["alpha"] + np.repeat(a_day, per_day) + params["theta"] * x
    r = mu + params["sigma"] * rng.standard_t(params["nu"], size=n)
    return M1Data(r=r, condition=x, day=day)
