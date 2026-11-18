"""The finding bar, measured (TICKET-909, spec section 5.5a).

Run: python -m services.research.evaluation.finding_bar   (from the repository root)

Two measurements, written to ``docs/phase0/finding-bar-b2.json``:

* **Null books.** Synthetic books with nothing planted: trades one after another each day,
  outcomes independent of what came before. Each goes through the live gate as production
  runs it (``b2_shuffle.shuffle_test``, 10,000 draws, the family of 18). The share that gets
  a finding should sit in [3.5%, 6.5%] (section 5.5a.8). The same books are read under the
  old bar (p <= 0.05, no correction), Bonferroni (p x 18 <= 0.05) and the corrected bar
  without the two-halves condition, so each part's effect is visible.
* **The demo file,** under the old bar, Bonferroni and the new one, as the ruling's gate 5
  asks. A real trader's book is measured the same way locally and reported outside the repo.

Every book here is generated from a seed; no one's trades.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np

from services.shared.conditions import b2_shuffle as T
from services.shared.conditions import multiplicity as M
from services.shared.conditions.b2_condition import Obs

SEED = 909
BOOKS = 1000
DAYS, PER_DAY = 100, 5
OUT = Path("docs/phase0/finding-bar-b2.json")


def null_book(rng: np.random.Generator) -> list[Obs]:
    out = []
    for day in range(DAYS):
        for k in range(PER_DAY):
            out.append(Obs(day=day, entry_at=float(day * 1000 + k * 10),
                           exit_at=float(day * 1000 + k * 10 + 5), r=float(rng.normal() * 1000)))
    return out


def rules(result: T.ShuffleResult) -> dict[str, bool]:
    """Would this file have a finding under each rule? All in B2's direction."""
    if result.p is None:
        return {"old": False, "bonferroni": False, "corrected": False, "corrected_and_halves": False}
    below = result.difference is not None and result.difference < 0
    family = M.family()
    return {
        "old": below and result.p <= T.ALPHA,
        "bonferroni": below and M.bonferroni(result.p, family) <= T.ALPHA,
        "corrected": below and result.p_adjusted <= T.ALPHA,
        "corrected_and_halves": result.passes,
    }


def null_run(books: int = BOOKS) -> dict:
    rng = np.random.default_rng(SEED)
    counts = {"old": 0, "bonferroni": 0, "corrected": 0, "corrected_and_halves": 0}
    evaluable = 0
    for i in range(books):
        result = T.shuffle_test(null_book(rng))
        evaluable += result.p is not None
        for rule, hit in rules(result).items():
            counts[rule] += hit
        if (i + 1) % 100 == 0:
            print(f"{i + 1} books", file=sys.stderr, flush=True)
    return {"books": books, "evaluable": evaluable, "days": DAYS, "per_day": PER_DAY,
            "seed": SEED, "draws": T.DRAWS, "family": len(M.family()),
            "with_a_finding": counts,
            "share": {k: round(v / books, 4) for k, v in counts.items()},
            "band": [0.035, 0.065]}


def demo_run() -> dict:
    from services.production.ctr.intake import pipeline as pl
    from services.production.mirror import metrics as mx

    plan = pl.plan_import(Path("data/fixtures/demo/scope_demo_tradebook.csv").read_text(encoding="utf-8"),
                          context=pl.ImportContext(trader_id="demo", source_account="DEMO",
                                                   code_version="finding-bar", export_date="2026-09-01",
                                                   export_date_source="trader"), production=True)
    trips = mx.load_trips([
        {"trip_id": p.position_id, "symbol": p.legs[0].symbol, "trading_day": p.entry_ts.date().isoformat(),
         "entry_ts": p.entry_ts.isoformat(), "exit_ts": p.exit_ts.isoformat(),
         "holding_seconds": int((p.exit_ts - p.entry_ts).total_seconds()), "net": str(p.net), "lots": 1,
         "risk_unit_source": "premium_paid", "segment": "OPT"} for p in plan.positions])
    result = T.shuffle_test(mx.b2_observations(mx.same_day_trips(trips)))
    return {"result": {k: v for k, v in asdict(result).items()}, "finding_under": rules(result)}


if __name__ == "__main__":
    report = {"null_books": null_run(), "demo_file": demo_run()}
    OUT.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
