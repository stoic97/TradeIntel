"""Shared fitting machinery for the research models.

The thresholds here are the framework's, not ours. ``framework_v1.yaml``:

    diagnostics: {rhat_max: 1.01, bulk_ess_min: 400, divergences: 0, ...}

``check_diagnostics`` raises rather than returning a flag, because a flag can be
ignored and a fit that misses a pre-committed threshold is not a fit.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

MAX_R_HAT = 1.01
MIN_BULK_ESS = 400.0
MAX_DIVERGENCES = 0


class BadDiagnostics(Exception):
    """The sampler did not produce a posterior the framework will accept."""


@dataclass(frozen=True)
class FitConfig:
    draws: int = 1000
    warmup: int = 1000
    chains: int = 4
    seed: int = 0


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
    # Kept only when asked for. A rank, an 80% interval and P(theta < 0) all need the
    # sample rather than the summary, and carrying 4,000 floats per parameter through
    # every fit is waste. Excluded from summary_digest: the same fit is the same fit
    # whether or not its draws were retained.
    samples: dict[str, np.ndarray] | None = None

    def summary_digest(self) -> str:
        """Identity of what the fit concluded, to six decimals. Timing is excluded on
        purpose: a slow run and a fast run of the same fit are the same fit."""
        payload = {
            "backend": self.backend,
            "spec_digest": self.spec_digest,
            "draws": self.draws,
            "mean": {k: round(v, 6) for k, v in sorted(self.posterior_mean.items())},
            "sd": {k: round(v, 6) for k, v in sorted(self.posterior_sd.items())},
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def check_diagnostics(result: FitResult) -> None:
    """Refuse a fit the framework's own thresholds refuse."""
    if result.divergences > MAX_DIVERGENCES:
        raise BadDiagnostics(
            f"{result.backend}: {result.divergences} divergent transitions, limit "
            f"{MAX_DIVERGENCES} — a fit that diverged is not a fit"
        )
    unconverged = {p: round(r, 4) for p, r in result.r_hat.items() if r > MAX_R_HAT}
    if unconverged:
        raise BadDiagnostics(f"{result.backend}: r_hat above {MAX_R_HAT}: {unconverged}")
    starved = {p: round(e, 1) for p, e in result.ess.items() if e < MIN_BULK_ESS}
    if starved:
        raise BadDiagnostics(
            f"{result.backend}: bulk ess below the framework minimum "
            f"{MIN_BULK_ESS:.0f}: {starved}"
        )


def summarise(
    *,
    backend: str,
    spec_digest: str,
    samples: dict[str, np.ndarray],
    divergences: int,
    seconds: float,
    params: Sequence[str],
    keep_samples: bool = False,
) -> FitResult:
    """``samples``: parameter -> array shaped (chains, draws).

    Means and standard deviations are computed with numpy, so they are unambiguous.
    ArviZ is used only for r_hat and effective sample size — the one place a
    hand-rolled statistic would itself need validating. That keeps the surface for
    ArviZ's announced refactor to this function alone.
    """
    import arviz as az

    posterior = {p: np.asarray(samples[p], dtype=float) for p in params}
    idata = az.from_dict(posterior=posterior)
    rhat, ess = az.rhat(idata), az.ess(idata)
    total = int(next(iter(posterior.values())).size)

    return FitResult(
        backend=backend,
        spec_digest=spec_digest,
        posterior_mean={p: float(posterior[p].mean()) for p in params},
        posterior_sd={p: float(posterior[p].std(ddof=1)) for p in params},
        r_hat={p: float(rhat[p]) for p in params},
        ess={p: float(ess[p]) for p in params},
        divergences=int(divergences),
        draws=total,
        seconds=seconds,
        samples={p: posterior[p].ravel() for p in params} if keep_samples else None,
    )


def failing_parameters(result: FitResult) -> dict[str, str]:
    """Which parameters miss the framework's thresholds, and why. Empty means all pass.

    ``check_diagnostics`` asks whether a *fit* is usable, which is the right question
    before a fit is reported to anyone. This asks the per-parameter question, which is
    the right one during validation: excluding a whole replication because a nuisance
    scale failed to mix conditions the surviving sample on an unrelated parameter and
    biases it (measured 10 Oct 2026: a third of SBC replications refused on tau_day
    while theta mixed cleanly in all of them).

    **Divergences are a property of the fit, not of a parameter.** When a fit diverged
    the sampler did not explore the posterior at all, so every parameter fails.
    """
    if result.divergences > MAX_DIVERGENCES:
        reason = f"{result.divergences} divergent transitions in the fit"
        return dict.fromkeys(result.r_hat, reason)
    failing: dict[str, str] = {}
    for name, value in result.r_hat.items():
        if value > MAX_R_HAT:
            failing[name] = f"r_hat {value:.4f} above {MAX_R_HAT}"
        elif result.ess.get(name, 0.0) < MIN_BULK_ESS:
            failing[name] = f"bulk ess {result.ess[name]:.0f} below {MIN_BULK_ESS:.0f}"
    return failing
