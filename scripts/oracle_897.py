"""TICKET-897, Stage A probe: does M1's theta track the quantity the product promises?

For each B2 planted history at 1,000 trips (first --reps seeds per k), on the training
zone's B2 population only (the same trades M1 fits):

  * oracle    - mean R, condition minus comparison, with a by-day bootstrap 80% interval
  * channels  - the exact decomposition of that contrast into: stop atom (-1R) share,
                target atom (+2R) share, other-mix, other-quality
  * M1        - theta's posterior median and 80% interval, nu floored at --floor

Writes nothing. Usage: uv run python scripts/oracle_897.py [--floor 2.0] [--reps 3]
"""
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import run_null_rate_b2 as sweep
from services.research.evaluation.synthetic import corpus as cp
from services.research.engine import zones as zn
from services.research.library import b2
from services.research.models import m1

ap = argparse.ArgumentParser()
ap.add_argument("--floor", type=float, default=2.0)
ap.add_argument("--reps", type=int, default=3)
ap.add_argument("--boot", type=int, default=400)
a = ap.parse_args()
rng = np.random.default_rng(897)


def contrast(r, c):
    return float(r[c == 1].mean() - r[c == 0].mean())


def channels(r, c):
    """theta = sum_K [ dpi_K * mbar_K + pibar_K * dm_K ], classes S (-1), T (+2), O (rest)."""
    S, T = np.isclose(r, -1.0), np.isclose(r, 2.0)
    O = ~(S | T)
    out, total = {}, 0.0
    for name, mask in (("stop", S), ("target", T), ("other", O)):
        pi1, pi0 = mask[c == 1].mean(), mask[c == 0].mean()
        m1_ = r[(c == 1) & mask].mean() if ((c == 1) & mask).any() else 0.0
        m0_ = r[(c == 0) & mask].mean() if ((c == 0) & mask).any() else 0.0
        mix = (pi1 - pi0) * 0.5 * (m1_ + m0_)
        qual = 0.5 * (pi1 + pi0) * (m1_ - m0_)
        out[name] = (pi1, pi0, mix, qual)
        total += mix + qual
    return out, total


print(f"nu floor = {a.floor}; oracle interval = by-day bootstrap, {a.boot} draws\n")
for cell in sweep.b2_cells():
    for rep in range(a.reps):
        h = cp.planted_history(sweep._market(), cell, rep)
        if len(h.trips) != 1000:
            break
        obs = b2.from_synthetic(h.trips)
        order = sorted(range(len(obs)), key=lambda i: (obs[i].day, obs[i].entry_at))
        obs = [obs[i] for i in order]
        days = np.array([o.day for o in obs])
        zones = zn.split(days)
        in_pop, cond = b2.population_and_condition(obs)
        sel = zones.training[in_pop[zones.training]]
        r = np.array([obs[i].r for i in sel]); c = cond[sel].astype(int); d = days[sel]
        theta_or = contrast(r, c)
        udays = np.unique(d); boots = []
        for _ in range(a.boot):
            pick = rng.choice(udays, size=len(udays), replace=True)
            idx = np.concatenate([np.flatnonzero(d == k) for k in pick])
            if (c[idx] == 1).sum() > 2 and (c[idx] == 0).sum() > 2:
                boots.append(contrast(r[idx], c[idx]))
        lo, hi = np.quantile(boots, [0.10, 0.90])
        ch, tot = channels(r, c)
        res = b2.run(obs, priors=m1.M1Priors(nu_floor=a.floor), config=sweep.CONFIG)
        th = res.train.samples["theta"]; nu = res.train.samples["nu"]
        print(f"{h.kind}-{h.seed} k={cell.multiple} nominal={h.planting.nominal} reached={h.planting.reached}"
              f"  n_cond={int(c.sum())} n_comp={int((1-c).sum())}")
        print(f"   oracle theta = {theta_or:+.3f}  80% [{lo:+.3f}, {hi:+.3f}]   (decomposition sums to {tot:+.3f})")
        for name, (pi1, pi0, mix, qual) in ch.items():
            print(f"      {name:6s} share cond {pi1:.2f} vs comp {pi0:.2f} -> mix {mix:+.3f} quality {qual:+.3f}")
        print(f"   M1 theta     = {np.median(th):+.3f}  80% [{np.quantile(th,0.10):+.3f}, {np.quantile(th,0.90):+.3f}]"
              f"   nu~{np.median(nu):.1f}  div train/hold {res.train.divergences}/{res.hold.divergences}"
              f"  gate='{res.finding.failed_gate}'")
        print(f"   twin truth: avoidable {h.truth['avoidable_cost_r']:.1f}R over {int(h.truth['n_flagged'])} flagged trades"
              f" = {h.truth['avoidable_cost_r']/max(h.truth['n_flagged'],1):+.3f}R per flagged trade (whole history)\n", flush=True)
