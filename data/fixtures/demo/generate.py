"""Generate a Dhan-format tradebook carrying the Mirror contract history.

Run: python data/fixtures/demo/generate.py

Why it exists: the 40-trip contract history lives as JSON that tests insert straight
into the database, so it has never been through the adapter. That left two things
untested together -- parsing-and-reconstruction, and the metric contract -- and left
no file to walk the product with. Uploading this one should make the Mirror show the
hand-calculated answers in expected.json; if it does not, the two halves disagree
and that is worth knowing.

Two decisions the file reflects:

**Each trip gets its own strike.** The history contains trips that overlap on the
same day. Fills are matched FIFO within a contract, so emitting overlapping trips on
one strike would pair the first buy with the first sell and reconstruct different
trips than the history intends. A separate strike per trip removes the ambiguity, and
a trader working several strikes in a session is ordinary.

**Trade Value is derived from the history's gross, and price from the value.** That
is the direction the adapter reads them: Trade Value is authoritative and price is
value over quantity. Setting the value to produce the intended gross is therefore
setting the thing the product actually uses, rather than setting a price and hoping.

Everything here is synthetic -- it comes from the generated contract fixture, not
from any trader's export (PRD section 10, section 14).
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
HISTORY = HERE.parents[2] / "tests/fixtures/mirror_contract/main.json"
OUT = HERE / "demo_tradebook.csv"

HEADER = ("Date,Time,Name,Buy/Sell,Order,Exchange,Segment,Quantity/Lot,"
          "Trade Price,Trade Value,Status")
BASE_PRICE = Decimal(5200)
EXPIRY = "19 SEP"


def rows() -> list[tuple[datetime, str]]:
    history = json.loads(HISTORY.read_text())
    out: list[tuple[datetime, str]] = []
    for n, trip in enumerate(history):
        strike = 5000 + n * 50
        name = f"WIDGETOIL {EXPIRY} {strike} CALL"
        lots = int(trip["lots"])
        entry_value = BASE_PRICE * lots
        exit_value = entry_value + Decimal(trip["gross"])
        for ts_key, side, value in (
            ("entry_ts", "BUY", entry_value),
            ("exit_ts", "SELL", exit_value),
        ):
            ts = datetime.fromisoformat(trip[ts_key])
            price = (value / lots).quantize(Decimal("0.01"))
            out.append((ts, ",".join([
                ts.date().isoformat(), ts.strftime("%H:%M:%S"), name, side,
                "INTRADAY", trip["exchange"], "Commodity", str(lots),
                f"{price:.2f}", f"{value:.2f}", "Traded",
            ])))
    return out


def main() -> None:
    body = sorted(rows(), key=lambda r: r[0], reverse=True)  # newest first, as Dhan
    OUT.write_text("\n".join([HEADER, *(line for _, line in body)]) + "\n")

    # The file is only useful if it reproduces the history it was built from.
    from services.production.ctr.intake import pipeline as pl
    plan = pl.plan_import(
        OUT.read_text(),
        context=pl.ImportContext(trader_id="1", source_account="A",
                                 code_version="demo-generate", existing_days={}),
    )
    history = json.loads(HISTORY.read_text())
    expected = sorted(Decimal(t["gross"]) for t in history)
    got = sorted(t.gross_pnl for t in plan.trips)
    assert len(plan.trips) == len(history), (
        f"reconstructed {len(plan.trips)} trips from {len(history)}: "
        f"{plan.rows_excluded} rows excluded, outcome {plan.outcome}"
    )
    assert got == expected, "reconstructed results differ from the history"
    print(f"wrote {OUT.relative_to(HERE.parents[2])}: "
          f"{len(body)} rows, {len(plan.trips)} trips, outcome {plan.outcome.value}")


if __name__ == "__main__":
    main()
