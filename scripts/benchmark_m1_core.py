"""Measure what ADR-006 turns on: information per second from each sampler.

Fits the conjugate core of M1 at several problem sizes with every registered
backend and records the result. Replaces doubt D8's assumed 2 s/fit with a
measurement, and gives ADR-006 a number instead of a preference.

**Information per second, not fits per second.** A sampler twice as fast that
returns half the independent draws has bought nothing, so the headline rate is
effective sample size per second.

**A known flaw in the comparison, printed rather than hidden.** The nutpie backend
compiles the model on every call; NumPyro's JIT cache survives between calls of the
same shape. Repeat fits therefore favour NumPyro. Hoisting compilation out of the
fit loop is the production fix and is carried as a deferral, not done here.

Usage:
    uv run python scripts/benchmark_m1_core.py
    uv run python scripts/benchmark_m1_core.py --quick
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

from services.research.models import benchmark as bm
from services.research.models import conditional_effect as ce

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "phase0" / "adr-006-benchmark.json"

SIZES = (100, 300, 1000, 3000)
CORPUS_SIZES = (100, 300, 1000)  # corpus A is exactly one third each
REPEATS = 3
SIGMA = 0.9
PREVALENCE = 0.25
TRUE_DELTA = -0.5

CORPUS_HISTORIES = 2224
LIBRARY_TESTS = 18


def _git(*args: str) -> str:
    out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True)
    return out.stdout.strip()


def _data(n: int, seed: int = 11) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    x = (rng.random(n) < PREVALENCE).astype(float)
    y = -0.05 + TRUE_DELTA * x + SIGMA * rng.standard_normal(n)
    return y, x


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--quick", action="store_true", help="one size, one repeat")
    ap.add_argument("--allow-dirty", action="store_true")
    args = ap.parse_args()

    dirty = bool(_git("status", "--porcelain", "--untracked-files=no"))
    if dirty and not args.allow_dirty:
        sys.exit("refusing: tracked files have uncommitted changes (commit, or --allow-dirty)")

    sizes = (100,) if args.quick else SIZES
    repeats = 1 if args.quick else REPEATS
    spec = ce.ConditionalEffectSpec(sigma=SIGMA)
    config = ce.FitConfig(draws=1000, warmup=1000, chains=4, seed=7)

    runs: list[tuple[int, str, ce.FitResult]] = []
    for name in sorted(ce.BACKENDS):
        fit = ce.BACKENDS[name]
        for n in sizes:
            y, x = _data(n)
            print(f"  {name:12s} n={n:5d} ", end="", flush=True)
            for k in range(repeats + 1):
                result = fit(spec, y, x, config)
                ce.check_diagnostics(result)
                runs.append((n, "first" if k == 0 else "repeat", result))
                print(f"{result.seconds:6.2f}s", end="", flush=True)
            print()

    record = bm.benchmark_record([r for _, _, r in runs])
    for row, (n, call, _) in zip(record["rows"], runs, strict=True):
        row["n"] = n
        row["call"] = call
    record["code_commit"] = _git("rev-parse", "HEAD")
    record["code_dirty"] = dirty
    record["config"] = {
        "draws": config.draws,
        "warmup": config.warmup,
        "chains": config.chains,
        "sigma": SIGMA,
        "prevalence": PREVALENCE,
        "sizes": list(sizes),
        "repeats": repeats,
    }
    record["caveat"] = (
        "The nutpie backend compiles on every call; NumPyro's JIT cache survives "
        "calls of the same shape. Repeat fits favour NumPyro. Hoisting compilation "
        "out of the fit loop is the production fix and is not done here."
    )

    print("\nbackend        n    first    repeat avg   ess    ess/sec   max rhat")
    rate: dict[str, dict[int, float]] = {}
    for name in sorted(ce.BACKENDS):
        rate[name] = {}
        for n in sizes:
            mine = [r for (m, c, r) in runs if m == n and r.backend == name and c == "repeat"]
            first = next(r for (m, c, r) in runs if m == n and r.backend == name and c == "first")
            secs = float(np.mean([r.seconds for r in mine]))
            ess = float(np.mean([min(r.ess.values()) for r in mine]))
            rhat = max(max(r.r_hat.values()) for r in [first, *mine])
            rate[name][n] = secs
            print(
                f"{name:12s} {n:5d} {first.seconds:7.2f}s {secs:9.2f}s "
                f"{ess:7.0f} {ess / secs:9.0f} {rhat:10.4f}"
            )

    fits = CORPUS_HISTORIES * LIBRARY_TESTS
    print(f"\none full corpus pass = {CORPUS_HISTORIES} histories x {LIBRARY_TESTS} tests = {fits:,} fits")
    print("corpus A is one third each of 100 / 300 / 1000 trips, so the mean of those is used\n")
    projection: dict[str, dict[str, float]] = {}
    for name in sorted(ce.BACKENDS):
        if not all(n in rate[name] for n in CORPUS_SIZES):
            continue
        per_fit = float(np.mean([rate[name][n] for n in CORPUS_SIZES]))
        hours = fits * per_fit / 3600
        projection[name] = {"seconds_per_fit": per_fit, "hours_per_pass_1_core": hours}
        print(
            f"  {name:12s} {per_fit:5.2f} s/fit  ->  {hours:6.1f} h serial, "
            f"{hours / 8:5.1f} h on 8 cores"
        )
    record["projection"] = {
        "fits_per_pass": fits,
        "basis": "mean per-fit seconds over the corpus's 100/300/1000-trip mix",
        "backends": projection,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(f"\nwritten {OUT.relative_to(ROOT)}")
    print(f"caveat: {record['caveat']}")


if __name__ == "__main__":
    sys.exit(main())
