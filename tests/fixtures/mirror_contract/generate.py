"""The 40-trip Mirror contract fixture (PRD Appendix A).

Synthetic throughout, regenerated from code, never from a real export. Every figure
in ``expected.json`` is hand-calculated from Appendix A's formulas and checked
against this table by arithmetic, never copied from program output -- a fixture
whose expectations came from the code under test proves only that the code agrees
with itself.

Run: python tests/fixtures/mirror_contract/generate.py

What the 40 trips are built to contain, one case per Appendix A row:

* eight eligible days whose trip counts are 3,6,4,5,8,4,6,4 -- median 4.5, so the
  normal day is a fraction and day 5 at 8 trips is 1.78x it
* a share of total inside 0-100% (96%): every day is negative, which is the only
  way the five worst days can be less than the whole
* ties in both the best five (two trips at +1000, two at +500) and the worst five
  (five trips at -2000), resolved by earlier entry
* two scratch trades (net = 0), one of them between two losses, so the
  two-straight-losses run is broken and the strike rate excludes both
* two losses then a WIN, which is in the condition but is not itself a loss
* a losing run of ten that crosses a day boundary (two on day 4, eight on day 5)
* an hour with four trips and an hour with one, both flagged small sample
* all five risk-unit sources, so the showable/not-showable split is exercised
* winners held a median of 30 minutes against losers' 10 -- a 3x ratio
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
HERE = Path(__file__).parent

# (id, day, entry HH:MM, minutes held, net, lots, risk_unit_source)
TRIPS: list[tuple[str, str, str, int, int, int, str]] = [
    # Day 1 -- 3 trips, net -300. A win, then two losses.
    ("t01", "2026-09-01", "09:30", 30, 500, 1, "declared_budget"),
    ("t02", "2026-09-01", "10:00", 30, -400, 1, "declared_budget"),
    ("t03", "2026-09-01", "11:00", 20, -400, 1, "declared_budget"),
    # Day 2 -- 6 trips, net -8000. Two losses then a loss (in condition), then a win.
    ("t04", "2026-09-02", "09:20", 15, -1000, 2, "declared_budget"),
    ("t05", "2026-09-02", "09:40", 10, -1500, 2, "declared_budget"),
    ("t06", "2026-09-02", "10:00", 10, -2000, 2, "declared_budget"),
    ("t07", "2026-09-02", "10:30", 30, 500, 1, "declared_budget"),
    ("t08", "2026-09-02", "11:00", 10, -2000, 1, "declared_budget"),
    ("t09", "2026-09-02", "11:30", 60, -2000, 1, "declared_budget"),
    # Day 3 -- 4 trips, net -200. Two scratches; the second breaks a loss run.
    ("t10", "2026-09-03", "09:30", 10, -100, 1, "declared_budget"),
    ("t11", "2026-09-03", "09:45", 10, 0, 1, "declared_budget"),
    ("t12", "2026-09-03", "10:00", 10, -100, 1, "declared_budget"),
    ("t13", "2026-09-03", "10:20", 10, 0, 1, "declared_budget"),
    # Day 4 -- 5 trips, net -2000. Two losses then a WIN, then two losses.
    ("t14", "2026-09-04", "09:30", 10, -500, 1, "declared_budget"),
    ("t15", "2026-09-04", "09:45", 10, -500, 1, "declared_budget"),
    ("t16", "2026-09-04", "10:00", 30, 1000, 1, "declared_budget"),
    ("t17", "2026-09-04", "10:15", 10, -1000, 1, "declared_budget"),
    ("t18", "2026-09-04", "10:30", 10, -1000, 1, "declared_budget"),
    # Day 5 -- 8 trips, net -12000. All losses; the spike day and the long run.
    ("t19", "2026-09-07", "09:20", 5, -1000, 1, "defined_stop"),
    ("t20", "2026-09-07", "09:30", 5, -1000, 1, "defined_stop"),
    ("t21", "2026-09-07", "09:40", 5, -2000, 1, "defined_stop"),
    ("t22", "2026-09-07", "09:50", 5, -2000, 1, "defined_stop"),
    ("t23", "2026-09-07", "10:00", 5, -2000, 1, "defined_stop"),
    ("t24", "2026-09-07", "10:10", 5, -2000, 1, "defined_stop"),
    ("t25", "2026-09-07", "10:20", 5, -1000, 1, "defined_stop"),
    ("t26", "2026-09-07", "10:30", 5, -1000, 1, "defined_stop"),
    # Day 6 -- 4 trips, net -500. The win that ends the ten-trip losing run.
    ("t27", "2026-09-08", "09:30", 30, 1500, 1, "defined_stop"),
    ("t28", "2026-09-08", "10:05", 10, -1000, 1, "defined_stop"),
    ("t29", "2026-09-08", "10:20", 10, -500, 1, "premium_paid"),
    ("t30", "2026-09-08", "10:40", 10, -500, 1, "premium_paid"),
    # Day 7 -- 6 trips, net -1000.
    ("t31", "2026-09-09", "09:30", 20, 1000, 1, "premium_paid"),
    ("t32", "2026-09-09", "10:00", 10, -500, 1, "premium_paid"),
    ("t33", "2026-09-09", "10:20", 10, -500, 1, "premium_paid"),
    ("t34", "2026-09-09", "10:40", 10, -500, 1, "premium_paid"),
    ("t35", "2026-09-09", "11:00", 20, 500, 1, "premium_paid"),
    ("t36", "2026-09-09", "12:20", 10, -1000, 1, "premium_paid"),
    # Day 8 -- 4 trips, net -1000. Four equal losses.
    ("t37", "2026-09-10", "09:30", 10, -250, 1, "unavailable"),
    ("t38", "2026-09-10", "10:00", 10, -250, 1, "unavailable"),
    ("t39", "2026-09-10", "10:20", 10, -250, 1, "inferred_atr"),
    ("t40", "2026-09-10", "10:40", 10, -250, 1, "inferred_atr"),
]


LOT = 100
"""Units in one lot of the synthetic instrument, from MCX_WIDGETOIL.yaml."""


def build() -> list[dict]:
    out = []
    for trip_id, day, entry, minutes, net, lots, source in TRIPS:
        entry_ts = datetime.fromisoformat(f"{day}T{entry}:00").replace(tzinfo=IST)
        exit_ts = entry_ts + timedelta(minutes=minutes)
        out.append({
            "trip_id": trip_id,
            "trading_day": day,
            "entry_ts": entry_ts.isoformat(),
            "exit_ts": exit_ts.isoformat(),
            "holding_seconds": minutes * 60,
            "net": str(net),
            "gross": str(net),
            "fees": "0",
            "fees_available": False,
            "lots": lots,
            # What the broker's file would carry. Dhan reports units, not lots
            # (TD-029), so a one-lot trade in this instrument appears as 100.
            # `lots` above stays the derived answer the Mirror must reach.
            "quantity": lots * LOT,
            "risk_unit_source": source,
            "exchange": "MCX",
            "symbol": "WIDGETOIL",
        })
    return out


def main() -> None:
    trips = build()
    assert len(trips) == 40, f"the contract fixture is 40 trips, built {len(trips)}"
    total = sum(int(t["net"]) for t in trips)
    assert total == -25000, f"day totals must sum to -25000, got {total}"
    (HERE / "main.json").write_text(json.dumps(trips, indent=2) + "\n")
    print(f"wrote main.json: {len(trips)} trips, net {total}")


if __name__ == "__main__":
    main()
