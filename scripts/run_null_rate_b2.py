"""Step E: how often does B2 fire on a trader with nothing planted? (R-Spec §6.2)

Runs B2 end to end over corpus A's null histories and reports the false-positive
rate with the interval its clustering allows. The nulls are regenerated in
process from ``null_seed`` and the same crude market, which reproduces the
corpus's null histories exactly — the seeds fix them — without reading the
export back. That is a deliberate scope call: step E measures the statistics,
not the IO. Reading fills back through ``reconstruct`` waits for the real
importer and is covered separately by CTR v1.

Two classes, measured apart because they differ in kind:

* **adversarial_null** — all 600 index into the one crude series, so histories
  covering the same months saw the same noise. Clustered by 90-day calendar
  window. This is the Class B gate.
* **clean_null** — each has its own random walk, so they are independent by
  construction and each is its own cluster. This is the control: if the clean
  rate and the adversarial rate differ sharply, the adversarial noise is doing
  something and we should know what.

Usage:
    uv run python scripts/run_null_rate_b2.py                 # 600 + 400, ~30 min
    uv run python scripts/run_null_rate_b2.py --quick         # 40 + 20, a smoke run
    uv run python scripts/run_null_rate_b2.py --workers 6

Writes ``docs/phase0/null-rate-b2.json``. The manifest stamps the code commit,
so the script refuses a dirty tree: a rate stamped with a commit that did not
produce it would be a false record (Methodology §7).
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from services.research.evaluation import null_rate as nr
from services.research.evaluation.synthetic import corpus as cp
from services.research.evaluation.synthetic.crude import load_crude_1m
from services.research.library import b2
from services.research.models.base import BadDiagnostics, FitConfig

ROOT = Path(__file__).resolve().parents[1]
CRUDE = ROOT / "data" / "market" / "crude_1m.csv"
OUT = ROOT / "docs" / "phase0" / "null-rate-b2.json"

SEED = 20261010
WINDOW_DAYS = 90
CONFIG = FitConfig(1000, 1000, 4, SEED)

_MARKET: cp.Market | None = None


def _git(*args: str) -> str:
    out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True)
    return out.stdout.strip()


def _market() -> cp.Market:
    """Loaded once per worker process; the crude file is hash-verified on load."""
    global _MARKET
    if _MARKET is None:
        _MARKET = cp.Market.of(load_crude_1m(CRUDE))
    return _MARKET


@dataclass(frozen=True)
class Row:
    history_id: str
    kind: str
    n_trips: int
    median_day: int
    n_condition: int
    n_comparison: int
    n_condition_isolation: int
    evaluable: bool
    fired: bool
    reason: str
    tier: str
    failed_gate: str
    p_train: float
    m_train: float
    p_hold: float
    mde: float
    seconds: float


def one(task: tuple[str, int]) -> Row:
    kind, i = task
    t0 = time.time()
    h = cp.clean_null(i) if kind == "clean_null" else cp.adversarial_null(_market(), i)
    hid = f"{kind}-{h.seed}"
    median_day = int(np.median([t.day for t in h.trips])) if h.trips else 0
    blank = {
        "history_id": hid,
        "kind": kind,
        "n_trips": len(h.trips),
        "median_day": median_day,
        "n_condition": 0,
        "n_comparison": 0,
        "n_condition_isolation": 0,
        "tier": "",
        "failed_gate": "",
        "p_train": float("nan"),
        "m_train": float("nan"),
        "p_hold": float("nan"),
        "mde": float("nan"),
    }
    try:
        r = b2.run(b2.from_synthetic(h.trips), config=CONFIG)
    except (ValueError, BadDiagnostics) as e:
        # Too short to split, or too few days to fit. Anything else must crash the
        # sweep rather than be absorbed into the denominator as "not evaluable".
        return Row(**blank, evaluable=False, fired=False,
                   reason=f"{type(e).__name__}: {e}", seconds=time.time() - t0)

    n_min_c, n_min_comp = b2.N_MIN
    evaluable = r.n_condition >= n_min_c and r.n_comparison >= n_min_comp
    reason = ""
    if not evaluable:
        reason = (
            f"starved: {r.n_condition} condition trades (n_min {n_min_c}) and "
            f"{r.n_comparison} comparison (n_min {n_min_comp}) in the training zone"
        )
    fired = bool(r.core.real and r.core.big_enough and not r.core.killed)
    return Row(
        history_id=hid, kind=kind, n_trips=len(h.trips), median_day=median_day,
        n_condition=r.n_condition, n_comparison=r.n_comparison,
        n_condition_isolation=r.n_condition_isolation,
        evaluable=evaluable, fired=fired and evaluable, reason=reason,
        tier=r.finding.tier, failed_gate=r.finding.failed_gate,
        p_train=r.core.p_train, m_train=r.core.m_train, p_hold=r.core.p_hold,
        mde=r.finding.mde, seconds=time.time() - t0,
    )


def outcomes_for(rows: list[Row], kind: str) -> list[nr.NullOutcome]:
    mine = [r for r in rows if r.kind == kind]
    if kind == "adversarial_null":
        clusters = nr.cluster_by_window({r.history_id: r.median_day for r in mine}, WINDOW_DAYS)
    else:
        # Each clean null has its own price series: independent by construction.
        clusters = {r.history_id: i for i, r in enumerate(mine)}
    return [
        nr.NullOutcome(
            history_id=r.history_id, cluster=clusters[r.history_id],
            evaluable=r.evaluable, fired=r.fired, reason=r.reason,
        )
        for r in mine
    ]


UNIT = {
    "adversarial_null": f"{WINDOW_DAYS}-day calendar window on the shared crude series",
    "clean_null": "the history (each clean null has its own price series)",
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--quick", action="store_true", help="40 adversarial + 20 clean")
    ap.add_argument("--n-adversarial", type=int, default=None)
    ap.add_argument("--n-clean", type=int, default=None)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 4) // 2))
    ap.add_argument("--allow-dirty", action="store_true")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    dirty = bool(_git("status", "--porcelain", "--untracked-files=no"))
    if dirty and not args.allow_dirty:
        return print("refusing: tracked files have uncommitted changes (commit, or --allow-dirty)") or 1

    n_adv = args.n_adversarial if args.n_adversarial is not None else (40 if args.quick else cp.N_ADVERSARIAL)
    n_clean = args.n_clean if args.n_clean is not None else (20 if args.quick else cp.N_CLEAN)
    tasks = [("adversarial_null", i) for i in range(n_adv)] + [("clean_null", i) for i in range(n_clean)]

    # One BLAS thread per worker: nutpie already runs 4 chains, and oversubscribing
    # a laptop's cores makes every fit slower.
    for var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ.setdefault(var, "1")

    print(f"{len(tasks)} null histories on {args.workers} workers "
          f"({n_adv} adversarial, {n_clean} clean)", flush=True)
    rows: list[Row] = []
    start = time.time()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for row in pool.map(one, tasks, chunksize=1):
            rows.append(row)
            if len(rows) % 25 == 0 or len(rows) == len(tasks):
                done, el = len(rows), time.time() - start
                fired = sum(1 for r in rows if r.fired)
                ev = sum(1 for r in rows if r.evaluable)
                eta = el / done * (len(tasks) - done)
                print(f"  {done:5d}/{len(tasks)}  evaluable {ev:5d}  fired {fired:4d}  "
                      f"{el / 60:5.1f} min elapsed, ~{eta / 60:4.1f} min left", flush=True)

    report: dict[str, object] = {
        "test_id": b2.TEST_ID,
        "grid_version": cp.GRID_VERSION,
        "config": {"draws": CONFIG.draws, "warmup": CONFIG.warmup, "chains": CONFIG.chains,
                   "seed": SEED, "window_days": WINDOW_DAYS, "n_min": list(b2.N_MIN),
                   "theta_min": b2.THETA_MIN, "direction": b2.DIRECTION},
        "fired_definition": "core.real and core.big_enough and not core.killed",
        "scope": "nulls regenerated in process from null_seed; the export is not read back",
        "source": {"code_commit": _git("rev-parse", "HEAD"), "code_dirty": dirty,
                   "python": platform.python_version(), "numpy": np.__version__},
        "seconds": round(time.time() - start, 1),
    }
    for kind in ("adversarial_null", "clean_null"):
        o = outcomes_for(rows, kind)
        if not any(x.evaluable for x in o):
            report[kind] = {"error": "no evaluable histories", "n_histories": len(o)}
            print(f"\n{kind}: no evaluable histories", flush=True)
            continue
        rate = nr.assess(o, clustering_unit=UNIT[kind], seed=SEED)
        report[kind] = rate.record()
        print(f"\n{kind}")
        print(f"  {rate.n_fired} fired / {rate.n_evaluable} evaluable "
              f"({rate.n_starved} starved) = {rate.rate:.2%}")
        print(f"  interval [{rate.lo:.2%}, {rate.hi:.2%}] by {rate.interval_source}, "
              f"{rate.n_clusters} clusters")
        print(f"  point_inside={rate.point_inside}  interval_inside={rate.interval_inside}")
        print(f"  {rate.verdict}")

    trips = {}
    for r in rows:
        key = f"{r.kind}/{r.n_trips}"
        t = trips.setdefault(key, {"n": 0, "evaluable": 0, "fired": 0})
        t["n"] += 1
        t["evaluable"] += int(r.evaluable)
        t["fired"] += int(r.fired)
    report["by_trip_count"] = dict(sorted(trips.items()))
    print("\nevaluability by history length:")
    for key, t in sorted(trips.items()):
        print(f"  {key:28s} {t['evaluable']:4d}/{t['n']:4d} evaluable, {t['fired']} fired")

    report["histories"] = [vars(r) for r in rows]
    out = args.out or OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True, default=float) + "\n")
    print(f"\nwrote {out.relative_to(ROOT)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
