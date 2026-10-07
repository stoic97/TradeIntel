"""Build corpus A from the real crude series: 1,224 planted histories and 1,000 nulls.

Writes three gzip'd JSON Lines tables and a manifest to ``data/corpus/`` (gitignored:
the corpus regenerates from code + seed + the logged price file, so only its
manifest digest needs to be recorded). Every history's fills are checked to
reconstruct into exactly its trips before anything is written.

Usage:
    uv run python scripts/build_corpus_a.py            # the full corpus, ~3-6 min
    uv run python scripts/build_corpus_a.py --quick    # 2 cells + 4 nulls, a smoke run

The manifest stamps the code commit, so the script refuses to run on a tree with
uncommitted changes to tracked files: a digest stamped with a commit that did not
produce it would be a false record (Methodology §7). ``--allow-dirty`` overrides
for experiments and marks the manifest ``code_dirty: true``.
"""
from __future__ import annotations

import argparse
import platform
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import numpy as np

from services.research.evaluation.synthetic import corpus as cp
from services.research.evaluation.synthetic.crude import load_crude_1m
from services.research.evaluation.synthetic.export import write_corpus

ROOT = Path(__file__).resolve().parents[1]
CRUDE = ROOT / "data" / "market" / "crude_1m.csv"


def _git(*args: str) -> str:
    out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True)
    return out.stdout.strip()


def _dirty() -> bool:
    return bool(_git("status", "--porcelain", "--untracked-files=no"))


def histories(market: cp.Market, quick: bool) -> Iterator[cp.SyntheticHistory]:
    cells = cp.grid()[:2] if quick else cp.grid()
    seeds = 1 if quick else cp.SEEDS_PER_CELL
    n_clean, n_adv = (2, 2) if quick else (cp.N_CLEAN, cp.N_ADVERSARIAL)
    total = len(cells) * seeds + n_clean + n_adv
    done, start = 0, time.time()

    def tick() -> None:
        nonlocal done
        done += 1
        if done % 100 == 0 or done == total:
            print(f"  {done:5d} / {total}  ({time.time() - start:5.0f} s)", flush=True)

    for cell in cells:
        for r in range(seeds):
            yield cp.planted_history(market, cell, r)
            tick()
    for i in range(n_clean):
        yield cp.clean_null(i)
        tick()
    for i in range(n_adv):
        yield cp.adversarial_null(market, i)
        tick()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--quick", action="store_true", help="2 cells + 4 nulls, for a smoke run")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--allow-dirty", action="store_true", help="run with uncommitted changes")
    args = ap.parse_args()
    dirty = _dirty()
    if dirty and not args.allow_dirty:
        sys.exit("refusing: tracked files have uncommitted changes (commit, or --allow-dirty)")
    name = f"{cp.GRID_VERSION}_quick" if args.quick else cp.GRID_VERSION
    out = args.out or ROOT / "data" / "corpus" / name

    print(f"loading {CRUDE.relative_to(ROOT)} (hash-verified against CROSSINGS.md)")
    history = load_crude_1m(CRUDE)
    market = cp.Market.of(history)
    source = {
        "crude_sha256": history.report.source_sha256,
        "code_commit": _git("rev-parse", "HEAD"),
        "code_dirty": dirty,
        "python": platform.python_version(),
        "numpy": np.__version__,
    }
    print(f"writing {out.relative_to(ROOT)}")
    manifest = write_corpus(histories(market, args.quick), market, out, source)
    print("\nhistories :", manifest["histories"])
    for t in manifest["tables"].values():
        print(f"{t['file']:20s} {t['rows']:>9,d} rows  sha256 {t['sha256'][:16]}...")
    print(f"\ndecision_sha256  {manifest['decision_sha256']}  (must match on every machine)")
    print(f"corpus_sha256    {manifest['corpus_sha256']}  (exact for this environment)")


if __name__ == "__main__":
    sys.exit(main())
