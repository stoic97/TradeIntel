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

SPEC_VERSION = "m1_conjugate_core_v1"
PARAMS = ("mu", "delta")

MAX_R_HAT = 1.01
MAX_DIVERGENCES = 0

# NumPyro runs its chains vectorised on one device: the idiomatic fast path for a
# small model, and it needs no host-device configuration before jax initialises.
NUMPYRO_CHAIN_METHOD = "vectorized"


class BadDiagnostics(Exception):
    """The sampler did not produce a usable posterior."""


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
class FitConfig:
    draws: int = 1000
    warmup: int = 1000
    chains: int = 4
    seed: int = 0


@dataclass(frozen=True)
class AnalyticPosterior:
    mean: dict[str, float]
    sd: dict[str, float]


@dataclass(frozen=True)
class FitResult:
    backend: str
    spec_digest: str
    posterior_mean: dict[str, float]
    posterior_sd: dict[str, float]
    r_hat: dict[str, float]
    ess: dict[str, float]
    divergences: int
    draws: int
    seconds: float

    def summary_digest(self) -> str:
        """Identity of what the fit *concluded*, to six decimals. Timing is excluded
        on purpose: a slow run and a fast run of the same fit are the same fit."""
        payload = {
            "backend": self.backend,
            "spec_digest": self.spec_digest,
            "draws": self.draws,
            "mean": {k: round(v, 6) for k, v in sorted(self.posterior_mean.items())},
            "sd": {k: round(v, 6) for k, v in sorted(self.posterior_sd.items())},
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


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


def check_diagnostics(result: FitResult) -> None:
    """Refuse a fit the sampler itself says is unsound."""
    if result.divergences > MAX_DIVERGENCES:
        raise BadDiagnostics(
            f"{result.backend}: {result.divergences} divergent transitions, limit "
            f"{MAX_DIVERGENCES} — a fit that diverged is not a fit"
        )
    unconverged = {p: round(r, 4) for p, r in result.r_hat.items() if r > MAX_R_HAT}
    if unconverged:
        raise BadDiagnostics(f"{result.backend}: r_hat above {MAX_R_HAT}: {unconverged}")


def _summarise(
    backend: str,
    spec: ConditionalEffectSpec,
    samples: dict[str, np.ndarray],
    divergences: int,
    seconds: float,
) -> FitResult:
    """``samples``: parameter -> array shaped (chains, draws).

    Means and standard deviations are computed with numpy, so they are unambiguous.
    ArviZ is used only for r_hat and effective sample size — the one place a
    hand-rolled statistic would itself need validating. That keeps the surface for
    ArviZ's announced refactor to this function alone.
    """
    import arviz as az

    posterior = {p: np.asarray(samples[p], dtype=float) for p in PARAMS}
    idata = az.from_dict(posterior=posterior)
    rhat, ess = az.rhat(idata), az.ess(idata)
    total = int(sum(v.size for v in posterior.values()) / len(PARAMS))

    return FitResult(
        backend=backend,
        spec_digest=spec.digest(),
        posterior_mean={p: float(posterior[p].mean()) for p in PARAMS},
        posterior_sd={p: float(posterior[p].std(ddof=1)) for p in PARAMS},
        r_hat={p: float(rhat[p]) for p in PARAMS},
        ess={p: float(ess[p]) for p in PARAMS},
        divergences=int(divergences),
        draws=total,
        seconds=seconds,
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
    return _summarise("numpyro", spec, samples, diverging, seconds)


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
    return _summarise("pymc_nutpie", spec, samples, diverging, seconds)


Backend = Callable[[ConditionalEffectSpec, np.ndarray, np.ndarray, FitConfig], FitResult]

BACKENDS: dict[str, Backend] = {
    "numpyro": fit_numpyro,
    "pymc_nutpie": fit_pymc_nutpie,
}
