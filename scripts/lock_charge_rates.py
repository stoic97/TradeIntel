"""TICKET-911: pin new rows of the rate table in rates.lock. Never rewrites a pinned row.

    uv run python scripts/lock_charge_rates.py

Run it after appending rows to services/production/charges/rates.yaml. It adds a line for each
row not yet pinned, and refuses if a pinned row has changed: a row is never edited, so a
changed digest means a correction was typed over an old row instead of added as a new one.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.production.charges import rates as R


def main() -> int:
    _, _, raw = R.load()
    pinned = R.read_lock()
    for row in raw:
        if row["id"] in pinned and pinned[row["id"]] != R.digest(row):
            print(f"row {row['id']} has changed since it was pinned. Put it back and add a new row.")
            return 1
    new = [row for row in raw if row["id"] not in pinned]
    if new:
        with R.LOCK.open("a", encoding="utf-8", newline="\n") as f:
            for row in new:
                f.write(f"{row['id']} {R.digest(row)}\n")
    print(f"{len(new)} row(s) pinned; {len(pinned) + len(new)} in all.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
