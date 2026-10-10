"""The SBC run section 6.4 asks for: 1,000 replications of M1.

Draw from M1's prior, simulate from M1's own generative process, fit, rank the truth
among the posterior draws. Uniform ranks mean the machinery recovers what it was given.

**What a pass licenses, and what it does not.** Section 6.4: SBC licenses that the
inference machinery recovers parameters *under our own assumed model*. It does not
license that the model is right - a wrong model can pass SBC beautifully. M-SIM, where
data comes from processes M1 does not assume and 80% intervals must cover in
[72%, 88%], is the other gate. Both, or the model does not ship.

**The sampler budget is measured, not chosen.** 4 chains of 1,000 draws is the floor at
which tau_day cleared the framework's r_hat limit on a replication whose true day
effect was 0.055 (TD-020). At 1.8 s a fit, 1,000 replications is about half an hour.

**Gating is per parameter.** Each parameter contributes its rank when its own r_hat and
bulk ess pass; exclusions are counted against the parameter that caused them, and the
completion rate is reported beside the verdict. Excluding a whole replication because a
nuisance scale failed to mix conditions the surviving sample on an unrelated parameter.

Usage:
    uv run python scripts/run_sbc_m1.py --quick     # 50 replications, about 90 s
    uv run python scripts/run_sbc_m1.py             # the 1,000 section 6.4 asks for
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

from services.research.evaluation import sbc
from services.research.models import m1
from services.research.models.base import FitConfig

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "phase0" / "sbc-m1.json"

REPLICATIONS = 1000
QUICK_REPLICATIONS = 50
CHAINS, DRAWS = 4, 1000  # the floor TD-020 measured
SEED = 20261010


def _git(*args: str) -> str:
    out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True)
    return out.stdout.strip()


def _histogram(ranks: list[int], n_draws: int, bins: int = 10, width: int = 44) -> None:
    """The shape, not just the p-value: edge-piling means the posterior is too narrow,
    a skew means it is biased, and they have different causes."""
    counts, _ = np.histogram(np.asarray(ranks), bins=np.linspace(0, n_draws + 1, bins + 1))
    peak = max(int(counts.max()), 1)
    step = (n_draws + 1) / bins
    for i, count in enumerate(counts):
        lo, hi = int(i * step), int((i + 1) * step) - 1
        bar = "#" * int(width * count / peak)
        print(f"      {lo:3d}-{hi:3d} |{bar:<{width}}| {count}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--quick", action="store_true", help=f"{QUICK_REPLICATIONS} replications")
    ap.add_argument("--replications", type=int, default=None)
    ap.add_argument("--allow-dirty", action="store_true")
    args = ap.parse_args()

    dirty = bool(_git("status", "--porcelain", "--untracked-files=no"))
    if dirty and not args.allow_dirty:
        sys.exit("refusing: tracked files have uncommitted changes (commit, or --allow-dirty)")

    n = args.replications or (QUICK_REPLICATIONS if args.quick else REPLICATIONS)
    print(
        f"M1 SBC: {n} replications, {CHAINS} chains x {DRAWS} draws, "
        f"thinned to {sbc.N_THIN}, seed {SEED}"
    )

    result = sbc.run(
        n_replications=n,
        n_thin=sbc.N_THIN,
        fit=lambda data, seed: m1.fit(
            data, m1.M1Priors(), FitConfig(DRAWS, DRAWS, CHAINS, seed), keep_samples=True
        ),
        prior_draw=m1.prior_draw,
        simulate=m1.simulate,
        params=m1.PARAMS,
        seed=SEED,
        model="m1",
        progress_every=max(1, n // 20),
    )

    record = result.record()
    record["code_commit"] = _git("rev-parse", "HEAD")
    record["code_dirty"] = dirty
    record["sampler"] = {"chains": CHAINS, "draws": DRAWS, "warmup": DRAWS}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")

    print(f"\n{result.seconds:.0f} s   diverged {result.diverged_replications}"
          f"   refused {result.refused_replications}\n")
    print(f"{'parameter':<10} {'completed':>10} {'chi2':>9} {'p':>9}   verdict")
    verdicts = result.verdicts()
    completion = result.completion()
    for p in m1.PARAMS:
        if p not in verdicts:
            print(f"{p:<10} {0:>9.0%} {'-':>9} {'-':>9}   no ranks at all")
            continue
        v = verdicts[p]
        print(
            f"{p:<10} {completion[p]:>9.0%} {v.chi_square:>9.1f} {v.p_value:>9.4f}   "
            f"{'uniform' if v.uniform else 'NOT UNIFORM'}"
            f"{'' if completion[p] >= sbc.MIN_COMPLETION else '  (completion too low to read)'}"
        )
        _histogram(result.ranks[p], sbc.N_THIN)

    print(f"\npassed: {record['passed']}")
    print(f"written {OUT.relative_to(ROOT)}")
    print(f"\nbound: {record['bound']}")


if __name__ == "__main__":
    sys.exit(main())
