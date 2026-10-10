"""The record ADR-006 is decided from.

A speed number without its environment is worthless six months later, so the record
names the interpreter, every library version, the platform and the core count beside
every rate. Doubt D8's compute budget currently rests on an assumed 2 s/fit; this is
what replaces that assumption with a measurement.
"""

from __future__ import annotations

import os
import platform
from collections.abc import Iterable
from importlib.metadata import version
from typing import Any

from services.research.models.conditional_effect import FitResult

LIBRARIES = ("numpy", "jax", "numpyro", "pymc", "nutpie", "arviz")


def environment() -> dict[str, Any]:
    env: dict[str, Any] = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count() or 1,
    }
    for name in LIBRARIES:
        env[name] = version(name)
    return env


def _row(result: FitResult) -> dict[str, Any]:
    return {
        "backend": result.backend,
        "spec_digest": result.spec_digest,
        "draws": result.draws,
        "seconds": round(result.seconds, 3),
        "draws_per_second": result.draws / result.seconds if result.seconds > 0 else float("inf"),
        "divergences": result.divergences,
        "r_hat": {k: round(v, 4) for k, v in sorted(result.r_hat.items())},
        "ess": {k: round(v, 1) for k, v in sorted(result.ess.items())},
        "posterior_mean": {k: round(v, 6) for k, v in sorted(result.posterior_mean.items())},
        "posterior_sd": {k: round(v, 6) for k, v in sorted(result.posterior_sd.items())},
        "summary_digest": result.summary_digest(),
    }


def benchmark_record(results: Iterable[FitResult]) -> dict[str, Any]:
    return {"environment": environment(), "rows": [_row(r) for r in results]}
