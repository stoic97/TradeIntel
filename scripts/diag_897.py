"""TICKET-897 probe: for B2 planted histories that died on 'kill: failed_diagnostics',
which fit (training or isolation) failed, and on what (divergences / r_hat / ess)?
Usage: uv run python scripts/diag_897.py [--trips 1000] [--reps 3]
"""
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import run_null_rate_b2 as sweep
from services.research.evaluation.synthetic import corpus as cp
from services.research.library import b2
from services.research.models.base import failing_parameters

ap = argparse.ArgumentParser()
ap.add_argument("--trips", type=int, default=1000)
ap.add_argument("--reps", type=int, default=3)
a = ap.parse_args()

def show(tag, fit, n_obs, n_cond):
    fails = failing_parameters(fit)
    rh = {k: round(v, 3) for k, v in fit.r_hat.items()}
    es = {k: int(v) for k, v in fit.ess.items()}
    print(f"  {tag:5} n_obs={n_obs:4d} n_cond={n_cond:4d} div={fit.divergences:4d} "
          f"theta_failing={'theta' in fails}")
    print(f"        r_hat={rh}")
    print(f"        ess  ={es}")
    if fails: print(f"        failing={fails}")

for cell in sweep.b2_cells():
    for rep in range(a.reps):
        h = cp.planted_history(sweep._market(), cell, rep)
        if len(h.trips) != a.trips:
            break
        r = b2.run(b2.from_synthetic(h.trips), config=sweep.CONFIG)
        print(f"\n{h.kind}-{h.seed}  nominal={h.planting.nominal}  trips={len(h.trips)} "
              f"gate='{r.finding.failed_gate}'")
        show("train", r.train, r.n_condition + r.n_comparison, r.n_condition)
        show("hold", r.hold, len(r.zones.isolation), r.n_condition_isolation)
