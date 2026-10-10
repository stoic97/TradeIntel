"""The conjugate core of M1: one conditional effect, two samplers, one closed form.

For one trader, with sigma known:

    y_i   ~ Normal(mu + delta * x_i, sigma)
    mu    ~ Normal(prior_mu_mean, prior_mu_sd)
    delta ~ Normal(prior_delta_mean, prior_delta_sd)

``x_i`` marks the condition a test asks about (post-loss, high volatility, the
session, whichever); ``delta`` is the effect the two-part promotion criterion reads.

**Why this model and not M1.** M1 pools across traders and estimates sigma, and is
validated by simulation-based calibration in step C. This is M1's core with sigma
fixed, and it is here for one reason: with normal priors and known sigma the
posterior is a closed form, so a sampler can be checked against algebra instead of
against another sampler. ADR-006 chooses between NumPyro and PyMC+nutpie, and two
implementations written by the same hand would otherwise grade each other
(Developer Manual 5.4).

**Timing.** ``FitResult.seconds`` is the whole backend call, compilation included.
At the scale the corpus needs, compile-once-sample-many dominates, so excluding
compilation would answer a question nobody is asking. The benchmark script fits
twice; cold minus warm is the compile cost.

**Diagnostics are never swallowed.** A fit with a divergent transition or an r_hat
above the threshold raises. A fit that diverged is not a fit.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass

import numpy as np

from services.research.models.base import (
    MAX_DIVERGENCES,
    MAX_R_HAT,
    BadDiagnostics,
    FitConfig,
    FitResult,
    check_diagnostics,
    summarise,
)

__all__ = [
    "BACKENDS",
    "MAX_DIVERGENCES",
    "MAX_R_HAT",
    "PARAMS",
    "AnalyticPosterior",
    "BadDiagnostics",
    "ConditionalEffectSpec",
    "FitConfig",
    "FitResult",
    "analytic_posterior",
    "check_diagnostics",
    "fit_numpyro",
    "fit_pymc_nutpie",
]

SPEC_VERSION = "m1_conjugate_core_v1"
PARAMS = ("mu", "delta")

# NumPyro runs its chains vectorised on one device: the idiomatic fast path for a
# small model, and it needs no host-device configuration before jax initialises.
NUMPYRO_CHAIN_METHOD = "vectorized"


@dataclass(frozen=True)
class ConditionalEffectSpec:
    """The model, stated once. Both backends build from this and may not add to it."""

    prior_mu_mean: float = 0.0
    prior_mu_sd: float = 1.0
    prior_delta_mean: float = 0.0
    prior_delta_sd: float = 0.5
    sigma: float = 1.0

    def __post_init__(self) -> None:
        if min(self.sigma, self.prior_mu_sd, self.prior_delta_sd) <= 0:
            raise ValueError("sigma and both prior sds must be positive")

    def digest(self) -> str:
        """Fingerprint of the model. A backend's result carries it, so a backend
        that quietly fitted something else is detectable."""
        payload = {"version": SPEC_VERSION, **asdict(self)}
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


@dataclass(frozen=True)
class AnalyticPosterior:
    mean: dict[str, float]
    sd: dict[str, float]


def analytic_posterior(
    spec: ConditionalEffectSpec,
    y: np.ndarray,
    x: np.ndarray,
) -> AnalyticPosterior:
    """The exact posterior, by linear algebra. No sampling, no tolerance.

    With design matrix ``D = [1, x]``, prior ``N(m0, S0)`` and known sigma:

        precision = inv(S0) + D'D / sigma^2
        mean      = inv(precision) @ (inv(S0) @ m0 + D'y / sigma^2)

    With no data the precision is the prior's and the mean is the prior's, which is
    the first thing worth asserting about it.
    """
    y = np.asarray(y, dtype=float).ravel()
    x = np.asarray(x, dtype=float).ravel()
    if y.shape != x.shape:
        raise ValueError(f"y and x must have the same length, got {y.shape} and {x.shape}")

    design = np.column_stack([np.ones_like(x), x])
    prior_precision = np.diag([self_sd**-2 for self_sd in (spec.prior_mu_sd, spec.prior_delta_sd)])
    prior_mean = np.array([spec.prior_mu_mean, spec.prior_delta_mean])

    precision = prior_precision + design.T @ design / spec.sigma**2
    covariance = np.linalg.inv(precision)
    mean = covariance @ (prior_precision @ prior_mean + design.T @ y / spec.sigma**2)

    return AnalyticPosterior(
        mean=dict(zip(PARAMS, mean.tolist(), strict=True)),
        sd=dict(zip(PARAMS, np.sqrt(np.diag(covariance)).tolist(), strict=True)),
    )


def fit_numpyro(
    spec: ConditionalEffectSpec,
    y: np.ndarray,
    x: np.ndarray,
    config: FitConfig,
) -> FitResult:
    import jax
    import jax.numpy as jnp
    import numpyro
    import numpyro.distributions as dist
    from numpyro.infer import MCMC, NUTS

    def model(y_obs: jnp.ndarray, x_obs: jnp.ndarray) -> None:
        mu = numpyro.sample("mu", dist.Normal(spec.prior_mu_mean, spec.prior_mu_sd))
        delta = numpyro.sample("delta", dist.Normal(spec.prior_delta_mean, spec.prior_delta_sd))
        numpyro.sample("y", dist.Normal(mu + delta * x_obs, spec.sigma), obs=y_obs)

    started = time.perf_counter()
    mcmc = MCMC(
        NUTS(model),
        num_warmup=config.warmup,
        num_samples=config.draws,
        num_chains=config.chains,
        chain_method=NUMPYRO_CHAIN_METHOD,
        progress_bar=False,
    )
    mcmc.run(
        jax.random.PRNGKey(config.seed),
        y_obs=jnp.asarray(y),
        x_obs=jnp.asarray(x),
        extra_fields=("diverging",),
    )
    seconds = time.perf_counter() - started

    samples = {p: np.asarray(v) for p, v in mcmc.get_samples(group_by_chain=True).items()}
    diverging = int(np.asarray(mcmc.get_extra_fields()["diverging"]).sum())
    return summarise(
        backend="numpyro",
        spec_digest=spec.digest(),
        samples=samples,
        divergences=diverging,
        seconds=seconds,
        params=PARAMS,
    )


def fit_pymc_nutpie(
    spec: ConditionalEffectSpec,
    y: np.ndarray,
    x: np.ndarray,
    config: FitConfig,
) -> FitResult:
    import nutpie
    import pymc as pm

    started = time.perf_counter()
    with pm.Model() as model:
        mu = pm.Normal("mu", mu=spec.prior_mu_mean, sigma=spec.prior_mu_sd)
        delta = pm.Normal("delta", mu=spec.prior_delta_mean, sigma=spec.prior_delta_sd)
        pm.Normal("y", mu=mu + delta * np.asarray(x), sigma=spec.sigma, observed=np.asarray(y))

    trace = nutpie.sample(
        nutpie.compile_pymc_model(model),
        draws=config.draws,
        tune=config.warmup,
        chains=config.chains,
        seed=config.seed,
        progress_bar=False,
    )
    seconds = time.perf_counter() - started

    samples = {p: np.asarray(trace.posterior[p].values) for p in PARAMS}
    diverging = int(np.asarray(trace.sample_stats["diverging"].values).sum())
    return summarise(
        backend="pymc_nutpie",
        spec_digest=spec.digest(),
        samples=samples,
        divergences=diverging,
        seconds=seconds,
        params=PARAMS,
    )


Backend = Callable[[ConditionalEffectSpec, np.ndarray, np.ndarray, FitConfig], FitResult]

BACKENDS: dict[str, Backend] = {
    "numpyro": fit_numpyro,
    "pymc_nutpie": fit_pymc_nutpie,
}
