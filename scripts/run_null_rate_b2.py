"""Step E: how often does B2 fire on a trader with nothing planted? (R-Spec §6.2)

Runs B2 end to end over corpus A's null histories and reports the false-positive
rate with every interval its clustering allows. The nulls are regenerated in
process from ``null_seed`` and the same crude market, which reproduces the
corpus's null histories exactly — the seeds fix them — without reading the
export back. That is a deliberate scope call: step E measures the statistics,
not the IO. Reading fills back through ``reconstruct`` waits for the real
importer and is covered separately by CTR v1.

Two classes, measured apart because they differ in kind:

* **adversarial_null** — all 600 index into the one crude series, so histories
  covering the same months saw the same noise. Clustered by 90-day calendar
  window. This is the Class B gate, and it runs first so the gate can be read
  before the control finishes.
* **clean_null** — each has its own random walk, so they are independent by
  construction and each is its own cluster. The control, with a caveat: its
  trips-per-day density differs from the real series, and B2's population
  depends on that density, so the two classes are not yet like for like.

**Survivability.** A 90-minute sweep on a laptop will be interrupted, and the
first full run proved it: all 1,000 fits finished, the pool then took so long
shutting down that the run looked dead, and every result sat in process memory
with nothing on disk. So:

* Every row appends to ``data/null_rate/<name>.rows.jsonl`` as it completes.
* ``--report-only`` assembles the report from that file without running a fit.
* ``--rebuild-from <report.json>`` recomputes a finished report's intervals
  from its own saved rows, for when the statistics improve but the fits have
  not changed. It keeps the original ``code_commit`` and adds ``recomputed_by``,
  so the record never claims the new code produced the old numbers.
* The stamp comes from metadata written at run start, not from HEAD at report
  time, so a commit made mid-run cannot mislabel the result (Methodology §7).
* Resume refuses when the commit or configuration has changed since those rows
  were written. ``--restart`` discards the checkpoint deliberately.

Usage:
    uv run python scripts/run_null_rate_b2.py                 # 600 + 400
    uv run python scripts/run_null_rate_b2.py --quick         # 40 + 20
    uv run python scripts/run_null_rate_b2.py --report-only
    uv run python scripts/run_null_rate_b2.py --rebuild-from docs/phase0/null-rate-b2.json

``--quick`` writes to its own path. A smoke result must never sit where the
gate result belongs.
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
QUICK_OUT = ROOT / "docs" / "phase0" / "null-rate-b2-quick.json"
PLANTED_OUT = ROOT / "docs" / "phase0" / "recall-b2.json"
CHECKPOINTS = ROOT / "data" / "null_rate"

SEED = 20261010
WINDOW_DAYS = 90
CONFIG = FitConfig(1000, 1000, 4, SEED)
CHECKPOINT_VERSION = 2

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


def planted_tasks() -> list[tuple[str, int, int]]:
    """Every B2 cell x every seed: the recall sweep."""
    return [("planted", c.index, r) for c in b2_cells() for r in range(cp.SEEDS_PER_CELL)]


def b2_cells() -> list[cp.Cell]:
    return [c for c in cp.grid() if c.test_id == b2.TEST_ID]


def history_id(kind: str, i: int, rep: int = 0) -> str:
    """Known without generating the history, so a resume can skip it cheaply."""
    if kind == "planted":
        return f"planted-{cp.planted_seed(cp.grid()[i], rep)}"
    return f"{kind}-{cp.null_seed(kind, i)}"


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
    # Planted sweeps only; defaulted so null rows written earlier still load.
    cell_index: int = -1
    multiple: int = 0
    nominal: float = float("nan")
    reached: bool = True


def one(task: tuple[str, int, int]) -> Row:
    kind, i, rep = task
    t0 = time.time()
    extra: dict[str, object] = {}
    if kind == "planted":
        cell = cp.grid()[i]
        h = cp.planted_history(_market(), cell, rep)
        extra = {
            "cell_index": cell.index,
            "multiple": cell.multiple,
            "nominal": float(h.planting.nominal) if h.planting else float("nan"),
            "reached": bool(h.planting.reached) if h.planting else True,
        }
    elif kind == "clean_null":
        h = cp.clean_null(i)
    else:
        h = cp.adversarial_null(_market(), i)
    hid = f"{h.kind}-{h.seed}"
    median_day = int(np.median([t.day for t in h.trips])) if h.trips else 0
    blank = {
        "history_id": hid,
        "kind": h.kind,
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
        return Row(**blank, **extra, evaluable=False, fired=False,
                   reason=f"{type(e).__name__}: {e}", seconds=time.time() - t0)

    n_min_c, n_min_comp = b2.N_MIN
    evaluable = r.n_condition >= n_min_c and r.n_comparison >= n_min_comp
    reason = ""
    if not evaluable:
        reason = (
            f"starved: {r.n_condition} condition trades (n_min {n_min_c}) and "
            f"{r.n_comparison} comparison (n_min {n_min_comp}) in the training zone"
        )
    # "Fired" must mean the product would SHOW this, not that the statistics
    # merely looked significant. A Finding killed on diagnostics is never shown,
    # so counting it as recall flatters the engine -- which is precisely what
    # happened on 12 Oct: 5 of 8 counted at k=2 where the truth was zero.
    fired = bool(
        not r.finding.failed_gate
        and r.core.real
        and r.core.big_enough
        and not r.core.killed
    )
    return Row(
        history_id=hid, kind=h.kind, n_trips=len(h.trips), median_day=median_day,
        n_condition=r.n_condition, n_comparison=r.n_comparison,
        n_condition_isolation=r.n_condition_isolation,
        evaluable=evaluable, fired=fired and evaluable, reason=reason,
        tier=r.finding.tier, failed_gate=r.finding.failed_gate,
        p_train=r.core.p_train, m_train=r.core.m_train, p_hold=r.core.p_hold,
        mde=r.finding.mde, seconds=time.time() - t0, **extra,
    )


def run_meta(commit: str, dirty: bool, n_adv: int, n_clean: int) -> dict[str, object]:
    """What must match for a resume to be legitimate, and what stamps the report."""
    return {
        "version": CHECKPOINT_VERSION,
        "code_commit": commit,
        "code_dirty": dirty,
        "n_adversarial": n_adv,
        "n_clean": n_clean,
        "seed": SEED,
        "window_days": WINDOW_DAYS,
        "draws": CONFIG.draws,
        "warmup": CONFIG.warmup,
        "chains": CONFIG.chains,
        "python": platform.python_version(),
        "numpy": np.__version__,
    }


def checkpoint_paths(out: Path) -> tuple[Path, Path]:
    CHECKPOINTS.mkdir(parents=True, exist_ok=True)
    return CHECKPOINTS / f"{out.stem}.rows.jsonl", CHECKPOINTS / f"{out.stem}.meta.json"


def load_rows(rows_path: Path) -> list[Row]:
    text = rows_path.read_text() if rows_path.exists() else ""
    return [Row(**json.loads(ln)) for ln in text.splitlines() if ln.strip()]


def open_checkpoint(out: Path, meta: dict[str, object], restart: bool) -> tuple[Path, list[Row]]:
    rows_path, meta_path = checkpoint_paths(out)
    if restart:
        rows_path.unlink(missing_ok=True)
        meta_path.unlink(missing_ok=True)
    if not (rows_path.exists() and meta_path.exists()):
        meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")
        rows_path.write_text("")
        return rows_path, []
    if json.loads(meta_path.read_text()) != meta:
        raise SystemExit(
            f"refusing to resume: {rows_path.relative_to(ROOT)} was written by a different "
            "code commit or configuration, and a rate assembled from two versions would be "
            "a false record. Re-run with --restart to discard it."
        )
    return rows_path, load_rows(rows_path)


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


def write_report(rows: list[Row], meta: dict[str, object], out: Path, total: int,
                 seconds: float, recomputed_by: str | None = None) -> None:
    source: dict[str, object] = {
        "code_commit": meta["code_commit"],
        "code_dirty": meta["code_dirty"],
        "python": meta.get("python"),
        "numpy": meta.get("numpy"),
    }
    if recomputed_by:
        source["recomputed_by"] = recomputed_by
        source["note"] = (
            "rows were produced by code_commit; intervals recomputed by recomputed_by "
            "without re-running a single fit"
        )
    report: dict[str, object] = {
        "test_id": b2.TEST_ID,
        "grid_version": cp.GRID_VERSION,
        "config": {"draws": CONFIG.draws, "warmup": CONFIG.warmup, "chains": CONFIG.chains,
                   "seed": SEED, "window_days": WINDOW_DAYS, "n_min": list(b2.N_MIN),
                   "theta_min": b2.THETA_MIN, "direction": b2.DIRECTION},
        "fired_definition": "evaluable, no failed gate, and core.real and "
                            "core.big_enough and not core.killed",
        "scope": "nulls regenerated in process from null_seed; the export is not read back",
        "source": source,
        "n_rows": len(rows),
        "n_expected": total,
        "complete": len(rows) == total,
        "seconds": round(seconds, 1),
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
        print(f"  authority [{rate.lo:.2%}, {rate.hi:.2%}] by {rate.interval_source}"
              f"{'  (bootstrap degenerate)' if rate.bootstrap_degenerate else ''}")
        print(f"  envelope  [{rate.envelope_lo:.2%}, {rate.envelope_hi:.2%}]  over "
              f"{rate.n_clusters} windows, {rate.n_clusters_fired} with a fire")
        print(f"  point_inside={rate.point_inside}  interval_inside={rate.interval_inside}  "
              f"envelope_inside={rate.envelope_inside}")
        print(f"  {rate.verdict}")

    trips: dict[str, dict[str, int]] = {}
    for r in rows:
        t = trips.setdefault(f"{r.kind}/{r.n_trips}", {"n": 0, "evaluable": 0, "fired": 0})
        t["n"] += 1
        t["evaluable"] += int(r.evaluable)
        t["fired"] += int(r.fired)
    report["by_trip_count"] = dict(sorted(trips.items()))
    print("\nevaluability by history length:")
    for key, t in sorted(trips.items()):
        print(f"  {key:28s} {t['evaluable']:4d}/{t['n']:4d} evaluable, {t['fired']} fired")

    report["histories"] = [vars(r) for r in rows]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True, default=float) + "\n")
    print(f"\nwrote {out.relative_to(ROOT)}  ({len(rows)}/{total} histories, "
          f"complete={len(rows) == total})", flush=True)


def write_recall_report(rows: list[Row], meta: dict[str, object], out: Path, total: int,
                        seconds: float, recomputed_by: str | None = None) -> None:
    """Recall: of the histories where B2 was planted and could be tested, how many fired?

    Reported per effect size and history length, never pooled across effect
    sizes — pooling would let a strong cell carry a weak one and hide the shape,
    and the shape across k is the evidence. Intervals are Wilson over 8 seeds
    per cell, which is few; they are wide on purpose. These histories also share
    the one crude series, so the seeds within a cell are not fully independent
    and the true intervals are wider still.
    """
    source: dict[str, object] = {
        "code_commit": meta["code_commit"], "code_dirty": meta["code_dirty"],
        "python": meta.get("python"), "numpy": meta.get("numpy"),
    }
    if recomputed_by:
        source["recomputed_by"] = recomputed_by
    planted = [r for r in rows if r.kind == "planted"]
    wrong_direction = [r.history_id for r in planted if r.fired and r.m_train > 0]

    cells: dict[tuple[int, int], dict[str, object]] = {}
    for r in planted:
        c = cells.setdefault((r.multiple, r.n_trips), {
            "multiple": r.multiple, "n_trades": r.n_trips, "nominal": r.nominal,
            "reached": r.reached, "n": 0, "evaluable": 0, "fired": 0,
        })
        c["n"] = int(c["n"]) + 1
        c["evaluable"] = int(c["evaluable"]) + int(r.evaluable)
        c["fired"] = int(c["fired"]) + int(r.fired)
    for c in cells.values():
        ev, fired = int(c["evaluable"]), int(c["fired"])
        c["recall"] = fired / ev if ev else None
        c["interval"] = list(nr.wilson_interval(fired, ev)) if ev else None

    by_k: dict[int, dict[str, object]] = {}
    for (k, _), c in cells.items():
        a = by_k.setdefault(k, {"nominal": c["nominal"], "reached": c["reached"],
                                "n": 0, "evaluable": 0, "fired": 0})
        for key in ("n", "evaluable", "fired"):
            a[key] = int(a[key]) + int(c[key])
    for a in by_k.values():
        ev, fired = int(a["evaluable"]), int(a["fired"])
        a["recall"] = fired / ev if ev else None
        a["interval"] = list(nr.wilson_interval(fired, ev)) if ev else None

    report: dict[str, object] = {
        "test_id": b2.TEST_ID,
        "grid_version": cp.GRID_VERSION,
        "measure": "recall on planted histories",
        "fired_definition": "core.real and core.big_enough and not core.killed",
        "clustering": "8 seeds per cell share the one crude series; intervals are "
                      "Wilson over seeds and so are narrower than the truth",
        "config": {"draws": CONFIG.draws, "warmup": CONFIG.warmup, "chains": CONFIG.chains,
                   "seed": SEED, "n_min": list(b2.N_MIN), "theta_min": b2.THETA_MIN,
                   "direction": b2.DIRECTION},
        "source": source,
        "n_rows": len(rows), "n_expected": total, "complete": len(rows) == total,
        "seconds": round(seconds, 1),
        "wrong_direction_fires": wrong_direction,
        "by_effect_size": {str(k): by_k[k] for k in sorted(by_k)},
        "by_cell": [cells[key] for key in sorted(cells)],
        "histories": [vars(r) for r in rows],
    }

    print(f"\n{'k':>2} {'planted':>9} {'trades':>7} {'evaluable':>10} {'fired':>6} "
          f"{'recall':>8}  95% interval")
    for key in sorted(cells):
        c = cells[key]
        ev = int(c["evaluable"])
        rec = f"{c['recall']:.0%}" if c["recall"] is not None else "   -"
        iv = (f"[{c['interval'][0]:.0%}, {c['interval'][1]:.0%}]"
              if c["interval"] else "not testable")
        star = "" if c["reached"] else "  (saturated)"
        print(f"{c['multiple']:>2} {float(c['nominal']):>8.2f}R {c['n_trades']:>7} "
              f"{ev:>7}/{c['n']:<2} {int(c['fired']):>6} {rec:>8}  {iv}{star}")
    print("\nby effect size, lengths pooled:")
    for k in sorted(by_k):
        a = by_k[k]
        rec = f"{a['recall']:.0%}" if a["recall"] is not None else "-"
        iv = f"[{a['interval'][0]:.0%}, {a['interval'][1]:.0%}]" if a["interval"] else ""
        print(f"  k={k}  {float(a['nominal']):.2f}R  {int(a['fired'])}/{int(a['evaluable'])} "
              f"= {rec}  {iv}{'' if a['reached'] else '  (saturated)'}")
    print(f"\nfires in the wrong direction: {len(wrong_direction)}")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True, default=float) + "\n")
    print(f"wrote {out.relative_to(ROOT)}  ({len(rows)}/{total}, "
          f"complete={len(rows) == total})", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--planted", action="store_true",
                    help="sweep B2's planted cells and report recall instead of the null rate")
    ap.add_argument("--quick", action="store_true", help="40 adversarial + 20 clean")
    ap.add_argument("--n-adversarial", type=int, default=None)
    ap.add_argument("--n-clean", type=int, default=None)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 4) // 2))
    ap.add_argument("--report-only", action="store_true",
                    help="assemble the report from the checkpoint without running fits")
    ap.add_argument("--rebuild-from", type=Path, default=None,
                    help="recompute a finished report's intervals from its own saved rows")
    ap.add_argument("--restart", action="store_true", help="discard any checkpoint")
    ap.add_argument("--allow-dirty", action="store_true")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    n_adv = args.n_adversarial if args.n_adversarial is not None else (
        40 if args.quick else cp.N_ADVERSARIAL)
    n_clean = args.n_clean if args.n_clean is not None else (20 if args.quick else cp.N_CLEAN)
    planted = planted_tasks() if args.planted else []
    if args.planted:
        out = args.out or PLANTED_OUT
        total = len(planted)
    else:
        out = args.out or (QUICK_OUT if args.quick else OUT)
        total = n_adv + n_clean
    writer = write_recall_report if args.planted else write_report

    if args.rebuild_from:
        previous = json.loads(args.rebuild_from.read_text())
        rows = [Row(**h) for h in previous["histories"]]
        print(f"rebuilding from {len(rows)} saved rows, no fits run", flush=True)
        writer(rows, previous["source"], out, len(rows), 0.0,
               recomputed_by=_git("rev-parse", "HEAD"))
        return 0

    if args.report_only:
        rows_path, meta_path = checkpoint_paths(out)
        if not (rows_path.exists() and meta_path.exists()):
            print(f"no checkpoint at {rows_path.relative_to(ROOT)}")
            return 1
        rows = load_rows(rows_path)
        print(f"assembling from {len(rows)} checkpointed rows, no fits run", flush=True)
        writer(rows, json.loads(meta_path.read_text()), out, total, 0.0)
        return 0

    dirty = bool(_git("status", "--porcelain", "--untracked-files=no"))
    if dirty and not args.allow_dirty:
        print("refusing: tracked files have uncommitted changes (commit, or --allow-dirty)")
        return 1
    meta = run_meta(_git("rev-parse", "HEAD"), dirty,
                    0 if args.planted else n_adv, 0 if args.planted else n_clean)
    meta["planted"] = bool(args.planted)
    rows_path, rows = open_checkpoint(out, meta, args.restart)
    done_ids = {r.history_id for r in rows}

    if args.planted:
        tasks = list(planted)
    else:
        tasks = [("adversarial_null", i, 0) for i in range(n_adv)]
        tasks += [("clean_null", i, 0) for i in range(n_clean)]
    tasks = [t for t in tasks if history_id(*t) not in done_ids]

    # One BLAS thread per worker: nutpie already runs 4 chains, and oversubscribing
    # a laptop's cores makes every fit slower.
    for var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ.setdefault(var, "1")

    if rows:
        print(f"resuming: {len(rows)} of {total} already done", flush=True)
    what = (f"{len(b2_cells())} planted cells x {cp.SEEDS_PER_CELL} seeds" if args.planted
            else f"{n_adv} adversarial first, then {n_clean} clean")
    print(f"{len(tasks)} to run on {args.workers} workers ({what}); checkpoint "
          f"{rows_path.relative_to(ROOT)}", flush=True)

    start = time.time()
    if tasks:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            for row in pool.map(one, tasks, chunksize=1):
                rows.append(row)
                with rows_path.open("a") as fh:
                    fh.write(json.dumps(vars(row), sort_keys=True) + "\n")
                n_new = len(rows) - len(done_ids)
                if n_new % 25 == 0 or len(rows) == total:
                    el = time.time() - start
                    fired = sum(1 for r in rows if r.fired)
                    ev = sum(1 for r in rows if r.evaluable)
                    eta = el / max(n_new, 1) * (len(tasks) - n_new)
                    print(f"  {len(rows):5d}/{total}  evaluable {ev:5d}  fired {fired:4d}  "
                          f"{el / 60:5.1f} min elapsed, ~{eta / 60:4.1f} min left", flush=True)
            print("  all fits done; shutting the pool down (this can take minutes)", flush=True)

    writer(rows, meta, out, total, time.time() - start)
    return 0


if __name__ == "__main__":
    sys.exit(main())
