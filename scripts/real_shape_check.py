"""Does this trader's data have the shape M1 assumes? Aggregates only.

Written 12 Oct 2026 after the B2 recall sweep found M1 failing on the planted
corpus. The cause was not what we first thought. On the k=4 cell the condition
group had a quarter the variance of the comparison group (sd 0.56 against 1.25)
and the opposite tail shape — excess kurtosis +11 against -1.3. M1 carries one
``sigma`` and one ``nu`` for both groups, so no setting satisfies both and the
sampler tears itself apart. Capping ``nu`` only masked it.

That raises a question only real data answers: **is heteroscedasticity between
condition and comparison a property of trading, or an artifact of planting the
behaviour at prevalence 1.0?** If real post-two-loss trades genuinely have a
different spread, M1 needs a group-specific sigma and that is a framework
change. If they do not, the corpus's saturated cell is the thing to fix.

Needs no risk unit. Everything here is computed on price movement per lot and
on realised P&L per unit, so it runs before TD-013 lands. R is reported too,
wherever the import could supply one.

Prints counts, moments and ratios. Never a trade, a price, a date or a total.
Reads read-only and writes nothing, so no trader-derived figure reaches the
repo (SR-006).

Usage:  uv run python scripts/real_shape_check.py <path-to-export.csv>
"""
from __future__ import annotations

import hashlib
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from scipy import stats

from services.production.ctr.adapters.dhan_tradebook import parse
from services.production.ctr.reconstruct import reconstruct
from services.research.library import b2


def moments(name: str, v: np.ndarray) -> None:
    if v.size < 3:
        print(f"  {name:12s} n={v.size:4d}  too few to describe")
        return
    print(f"  {name:12s} n={v.size:4d}  mean {v.mean():+8.3f}  sd {v.std(ddof=1):7.3f}  "
          f"exkurt {stats.kurtosis(v):+7.2f}  skew {stats.skew(v):+6.2f}  "
          f"distinct {np.unique(np.round(v, 6)).size}")


def split_report(label: str, values: np.ndarray, cond: np.ndarray) -> None:
    c, nc = values[cond], values[~cond]
    print(f"\n{label}")
    moments("condition", c)
    moments("comparison", nc)
    if c.size > 2 and nc.size > 2:
        ratio = nc.var(ddof=1) / c.var(ddof=1)
        print(f"  variance ratio comparison/condition = {ratio:.2f}")
        # Levene is robust to non-normality, which this data is not short of.
        stat, p = stats.levene(c, nc, center="median")
        print(f"  Levene equal-variance test: W={stat:.2f}, p={p:.4f}"
              f"   -> {'DIFFERENT spread' if p < 0.05 else 'no evidence of different spread'}")
        print(f"  mean difference (condition - comparison) = {c.mean() - nc.mean():+.3f}")


def main(path: Path) -> None:
    raw = path.read_bytes()
    print(f"file   {path.name}   sha256 {hashlib.sha256(raw).hexdigest()[:16]}")
    result = parse(path, trader_id="T01", raw_hash=hashlib.sha256(raw).hexdigest())
    recon = reconstruct(result.fills, fees_available=result.fees_available)
    trips = recon.round_trips
    print(f"rows {result.rows_in} -> fills {len(result.fills)} -> trips {len(trips)}")

    print("\n=== WHAT IS ACTUALLY HERE ===")
    print(f"  segment  {dict(Counter(t.segment.value for t in trips))}")
    print(f"  exchange {dict(Counter(t.exchange for t in trips))}")
    opts = [t for t in trips if t.segment.value == "OPT"]
    print(f"  option direction {dict(Counter(t.direction.value for t in opts))}"
          "   <- SHORT means premium received, which is NOT the risk (TD-001)")
    print(f"  risk source by direction: "
          f"{dict(Counter((t.direction.value, t.risk_unit_source.value) for t in opts))}")

    fut = [t for t in trips if t.r_multiple is not None]
    print(f"\ntrips with an R      {len(fut)}")
    print(f"by symbol            {dict(Counter(t.symbol.rstrip('0123456789') for t in fut).most_common(6))}")
    print(f"risk unit source     {dict(Counter(t.risk_unit_source.value for t in fut))}")
    if not fut:
        return

    # Points per lot: price movement in the trade's own direction, size removed.
    sign = np.array([1.0 if t.direction.value == "LONG" else -1.0 for t in fut])
    points = sign * np.array([float(t.exit_price - t.entry_price) for t in fut])
    net_per_unit = np.array([float(t.gross_pnl - t.fees) / t.quantity for t in fut])
    has_r = np.array([t.r_multiple is not None for t in fut])

    print("\n=== OVERALL SHAPE (is R light- or heavy-tailed in reality?) ===")
    moments("points/lot", points)
    moments("net/unit", net_per_unit)
    if has_r.any():
        moments("R", np.array([float(t.r_multiple) for t, ok in zip(fut, has_r) if ok]))
    else:
        print("  R            none available — risk unit not yet implemented (TD-013)")

    # B2's population, computed on realised money so "loss" means what he felt.
    obs = [
        b2.Obs(day=int(t.entry_ts.date().toordinal()),
               entry_at=t.entry_ts.timestamp(),
               exit_at=t.exit_ts.timestamp(),
               r=float(t.gross_pnl - t.fees) / t.quantity)
        for t in fut
    ]
    order = sorted(range(len(obs)), key=lambda i: (obs[i].day, obs[i].entry_at))
    obs_s = [obs[i] for i in order]
    in_pop, cond = b2.population_and_condition(obs_s)

    days = np.array([o.day for o in obs_s])
    per_day = np.bincount(np.unique(days, return_inverse=True)[1])
    print("\n=== DENSITY (does he clear the intake bar?) ===")
    print(f"  trading days {per_day.size}, trips/day min {per_day.min()} "
          f"median {int(np.median(per_day))} mean {per_day.mean():.2f} max {per_day.max()}")
    print(f"  B2 population {int(in_pop.sum())} of {len(obs_s)}; "
          f"condition {int(cond.sum())}, comparison {int(in_pop.sum() - cond.sum())}")
    n_min_c, n_min_comp = b2.N_MIN
    ok = cond.sum() >= n_min_c and (in_pop.sum() - cond.sum()) >= n_min_comp
    print(f"  n_min {n_min_c}/{n_min_comp} on the WHOLE history: "
          f"{'clears' if ok else 'STARVED'}  (training zone is ~70% of this)")

    # The question this script exists for.
    pts_s = np.array([points[i] for i in order])
    net_s = np.array([net_per_unit[i] for i in order])
    pop = in_pop
    print("\n=== THE QUESTION: same spread after two losses? ===")
    split_report("points per lot, population only", pts_s[pop], cond[pop].astype(bool))
    split_report("net P&L per unit, population only", net_s[pop], cond[pop].astype(bool))
    print("\nFor reference, corpus A's planted k=4 cell: variance ratio 4.98, "
          "condition exkurt +11.1 against comparison -1.3.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: uv run python scripts/real_shape_check.py <export.csv>")
    main(Path(sys.argv[1]))
