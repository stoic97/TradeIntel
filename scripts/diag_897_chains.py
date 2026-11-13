"""TICKET-897 probe 2: where does each chain sit? If chains split into
'theta ~ 0, nu small (planted trades read as outliers)' vs 'theta ~ -effect, nu large',
the posterior is bimodal under the Student-t likelihood.
Usage: uv run python scripts/diag_897_chains.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import run_null_rate_b2 as sweep
from services.research.evaluation.synthetic import corpus as cp
from services.research.library import b2

PICK = {"planted-1001101", "planted-1001400", "planted-1001401", "planted-1001700", "planted-1001102"}
for cell in sweep.b2_cells():
    for rep in range(3):
        h = cp.planted_history(sweep._market(), cell, rep)
        if f"{h.kind}-{h.seed}" not in PICK:
            continue
        r = b2.run(b2.from_synthetic(h.trips), config=sweep.CONFIG)
        print(f"\n{h.kind}-{h.seed} nominal={h.planting.nominal}")
        for tag, fit in (("train", r.train), ("hold", r.hold)):
            s = fit.samples
            print(f"  {tag}  div={fit.divergences}")
            for c in range(s["theta"].shape[0]):
                print("    chain %d  " % c + "  ".join(
                    f"{p}={np.mean(s[p][c]):7.3f}" for p in ("theta", "alpha", "sigma", "nu", "tau_day")))
