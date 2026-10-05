"""Run the import pipeline on one real tradebook and report counts only.

Not a test: a one-off diagnostic. It prints aggregates -- how many rows parsed,
how many trips reconstructed, what was refused and why -- and never a trade, a
price or a P&L figure. Reads the file read-only and writes nothing.

Usage:  uv run python scripts/first_real_run.py <path-to-dhan-export.csv>
"""
from __future__ import annotations

import hashlib
import sys
from collections import Counter
from pathlib import Path

from services.production.ctr.adapters.dhan_tradebook import parse
from services.production.ctr.reconstruct import reconstruct
from services.shared.schemas.ctr_v1 import RiskUnitSource, Segment


def main(path: Path) -> None:
    raw = path.read_bytes()
    raw_hash = hashlib.sha256(raw).hexdigest()
    print(f"file      {path.name}  ({len(raw) // 1024} KB)")
    print(f"sha256    {raw_hash}")

    result = parse(path, trader_id="T01", raw_hash=raw_hash)

    print("\n=== PARSE ===")
    print(f"rows in            {result.rows_in}")
    print(f"fills parsed       {len(result.fills)}")
    print(f"rows rejected      {len(result.rejected)}")
    print(f"fees available     {result.fees_available}")
    if result.rejected:
        print("\nrejections by reason:")
        # Reasons carry row values, so group by the leading phrase only.
        for reason, n in Counter(
            r.reason.split(":")[0].split(" -- ")[0] for r in result.rejected
        ).most_common():
            print(f"  {n:5d}  {reason}")

    by_segment = Counter(f.segment.value for f in result.fills)
    by_exchange = Counter(f.exchange for f in result.fills)
    print(f"\nfills by segment   {dict(by_segment)}")
    print(f"fills by exchange  {dict(by_exchange)}")
    print(f"distinct contracts {len({f.contract_key for f in result.fills})}")
    if result.fills:
        print(f"date range         {min(f.ts for f in result.fills).date()}"
              f" .. {max(f.ts for f in result.fills).date()}")

    recon = reconstruct(result.fills, fees_available=result.fees_available)

    print("\n=== RECONSTRUCT ===")
    print(f"units in           {recon.quantity_in}")
    print(f"round trips        {len(recon.round_trips)}")
    print(f"open at end        {len(recon.open_positions)} positions,"
          f" {sum(o.quantity for o in recon.open_positions)} units")
    print(f"trips refused      {len(recon.skipped)},"
          f" {sum(s.quantity for s in recon.skipped)} units")
    print("conservation       HOLDS (asserted by ReconstructionResult)")

    if recon.skipped:
        print("\nrefusals by reason:")
        for reason, n in Counter(
            s.reason.split(":")[0] for s in recon.skipped
        ).most_common():
            print(f"  {n:5d}  {reason}")

    trips = recon.round_trips
    if not trips:
        return

    print("\n=== WHAT THE RESEARCH LAYER CAN USE ===")
    with_r = [t for t in trips if t.r_multiple is not None]
    print(f"trips with an R      {len(with_r)} of {len(trips)}")
    print(f"  risk unit source   {dict(Counter(t.risk_unit_source.value for t in trips))}")
    print(f"trips by segment     {dict(Counter(t.segment.value for t in trips))}")
    print(f"trips by symbol      {dict(Counter(t.symbol for t in trips).most_common(6))}")

    crude = [t for t in trips if t.symbol.startswith("CRUDEOIL")]
    print(f"\ncrude trips          {len(crude)}  ({len(with_r)} usable R across all symbols)")
    print(f"crude with an R      {len([t for t in crude if t.r_multiple is not None])}")

    # Holding time, which decides whether the tick-resolution tests can run at all.
    holds = sorted(t.holding_seconds for t in trips)
    def pct(p: float) -> str:
        v = holds[min(int(len(holds) * p), len(holds) - 1)]
        return f"{v // 60}m" if v < 3600 else f"{v / 3600:.1f}h"
    print(f"\nholding time         p10 {pct(0.10)}  median {pct(0.50)}"
          f"  p90 {pct(0.90)}  max {pct(0.999)}")
    print("  (E2 and E4' need tick data when holds are under ~45 min -- ADR 005)")

    # Trading frequency: s12.5 asks whether the improvement loop can serve this trader.
    days = {t.exit_ts.date() for t in trips}
    weeks = max(1, (max(days) - min(days)).days / 7)
    print(f"\ntrading days         {len(days)}")
    print(f"trips per week       {len(trips) / weeks:.1f}"
          f"   (s12.5 wants >= 5 for a readable adherence count)")

    # Zone split (s4.6): what the hold-out would look like for this history.
    n = len(trips)
    isolation = max(30, min(200, round(0.25 * n)))
    embargo = max(1, round(0.05 * n))
    print(f"\nzones at N={n}        training {n - isolation - embargo}"
          f" / embargo {embargo} / isolation {isolation}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: uv run python scripts/first_real_run.py <export.csv>")
    main(Path(sys.argv[1]))
