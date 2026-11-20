"""TICKET-897 probe 3: (a) how many trades sit at exactly -1R (the stop), and
(b) do the same 9 histories fit cleanly with a floor on nu?
Usage: uv run python scripts/diag_897_floor.py [--floor 2.0]

Run by: the research seat, by hand.
When: TICKET-897 diagnosis, 13 Nov 2026 - the probe the floor was adopted on.
Writes: nothing. Prints; capture with tee if the output is to be cited.
"""
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import run_null_rate_b2 as sweep
from services.research.evaluation.synthetic import corpus as cp
from services.research.library import b2
from services.research.models import m1
from services.research.models.base import failing_parameters

ap = argparse.ArgumentParser(); ap.add_argument("--floor", type=float, default=2.0)
a = ap.parse_args()
priors = m1.M1Priors(nu_floor=a.floor)
for cell in sweep.b2_cells():
    for rep in range(3):
        h = cp.planted_history(sweep._market(), cell, rep)
        if len(h.trips) != 1000:
            break
        obs = b2.from_synthetic(h.trips)
        r = np.array([o.r for o in obs])
        ties = int(np.sum(np.isclose(r, -1.0, atol=1e-9)))
        res = b2.run(obs, priors=priors, config=sweep.CONFIG)
        line = f"{h.kind}-{h.seed} nominal={h.planting.nominal:<4} at_exactly_-1R={ties:4d}/{len(r)}"
        for tag, f in (("train", res.train), ("hold", res.hold)):
            th = float(np.mean(f.samples["theta"]))
            line += (f" | {tag}: div={f.divergences:4d} maxRhat={max(f.r_hat.values()):.3f}"
                     f" theta={th:+.3f} ok={'theta' not in failing_parameters(f)}")
        print(line + f" | gate='{res.finding.failed_gate}' tier={res.finding.tier}", flush=True)
