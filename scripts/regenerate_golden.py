"""Regenerate the committed golden snapshot. A deliberate act, never automatic.

The golden is a photograph of correct output. Regenerating it is how an intended
behaviour change is recorded -- and the only way to be sure the change was intended
is to read the diff. So this script prints the diff and refuses to write unless
--yes is passed.

    uv run python scripts/regenerate_golden.py          # show the diff
    uv run python scripts/regenerate_golden.py --yes    # write it
"""
from __future__ import annotations

import difflib
import hashlib
import sys
from pathlib import Path

from services.production.ctr.adapters.dhan_tradebook import parse
from services.production.ctr.reconstruct import reconstruct
from services.production.ctr.snapshot import canonical_json, snapshot

FIXTURE = Path("data/fixtures/dhan_tradebook_sample.csv")
GOLDEN = Path("data/golden/dhan_tradebook_sample.ctr.json")
TRADER_ID = "FIXTURE"


def build() -> str:
    raw_hash = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    parsed = parse(FIXTURE, trader_id=TRADER_ID, raw_hash=raw_hash)
    recon = reconstruct(parsed.fills, fees_available=parsed.fees_available)
    return canonical_json(snapshot(parsed, recon))


def main() -> int:
    fresh = build()
    old = GOLDEN.read_text(encoding="utf-8") if GOLDEN.exists() else ""

    if fresh == old:
        print("golden is up to date; nothing to do")
        return 0

    diff = list(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            fresh.splitlines(keepends=True),
            fromfile=f"{GOLDEN} (committed)",
            tofile=f"{GOLDEN} (fresh)",
        )
    )
    print("".join(diff) if old else "(no committed golden yet)")
    added = len([d for d in diff if d.startswith("+") and not d.startswith("+++")])
    removed = len([d for d in diff if d.startswith("-") and not d.startswith("---")])
    print(f"\n{added} lines added, {removed} removed")

    if "--yes" not in sys.argv:
        print("\nRead the diff above. Every changed number must be one you meant to change.")
        print("Then re-run with --yes to write it.")
        return 1

    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN.write_text(fresh, encoding="utf-8")
    print(f"\nwritten: {GOLDEN}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
