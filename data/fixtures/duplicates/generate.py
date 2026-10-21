"""Generate the duplicate fixtures (PRD 5.4) in Dhan's export format.

Synthetic throughout: invented symbols, round numbers, no trader's history anywhere
near it (methodology 7.6 -- no trader-derived content enters the repository, and a
fixture is regenerated from code, never hand-edited).

Run: python data/fixtures/duplicates/generate.py

The three fixtures the PRD names, plus a clean control:

The instrument is a long call: the Dhan adapter currently maps every commodity row to
an option (see TD-025), so a futures fixture could not get through it today.

``repeated_legitimate_fills`` two pairs of byte-identical rows -- what a coarse
timestamp produces when one order fills twice in the same second. Both are real.

``duplicated_block``          a three-row block appearing twice, as a trader pasting
                              an overlapping range into one file would produce.

``with_fill_ids``             the same shape, but the broker supplies an order id, so
                              a repeat is provably the same fill.

``clean``                     no repeats at all; the control that proves the detector
                              does not invent groups.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

HEADER = (
    "Date,Time,Name,Buy/Sell,Order,Exchange,Segment,"
    "Quantity/Lot,Trade Price,Trade Value,Status"
)
HEADER_WITH_ID = HEADER + ",Order ID"
HERE = Path(__file__).parent


LOT = Decimal(100)
"""Units in one lot of the synthetic instrument, from MCX_WIDGETOIL.yaml.

Dhan reports quantity in units, not lots: one NIFTY lot appears as its contract
size, and `Trade Value / Quantity` equals the quoted premium, which only holds
if the quantity is units (TD-029, confirmed 21 Oct 2026). These fixtures said 1
where a real export says 100.
"""


def row(date: str, time: str, name: str, side: str, lots: int, lot_price: str,
        value: str) -> str:
    """One row, written the way the broker writes it.

    Call sites give lots and the value of one lot, because that is how a person
    thinks about the trade. The file carries units and the price of one unit,
    because that is what Dhan writes.
    """
    assert Decimal(value) == lots * Decimal(lot_price), (
        f"{lots} x {lot_price} is not {value}"
    )
    units = lots * LOT
    unit_price = (Decimal(value) / units).quantize(Decimal("0.01"))
    assert unit_price * units == Decimal(value), (
        f"{value} over {units} units is not a clean price"
    )
    return (
        f"{date},{time},{name},{side},INTRADAY,MCX,Commodity,{units},"
        f"{unit_price},{value},Traded"
    )


def write(name: str, header: str, lines: list[str]) -> None:
    (HERE / name).write_text("\n".join([header, *lines]) + "\n")
    print(f"wrote {name}: {len(lines)} rows")


def main() -> None:
    # Two pairs of identical rows, each pair a single order filling twice in one second.
    write(
        "repeated_legitimate_fills.csv",
        HEADER,
        [
            row("2026-10-16", "10:15:03", "WIDGETOIL 19 NOV 5000 CALL", "BUY", 1, "5000.00", "5000.00"),
            row("2026-10-16", "10:15:03", "WIDGETOIL 19 NOV 5000 CALL", "BUY", 1, "5000.00", "5000.00"),
            row("2026-10-16", "11:02:40", "WIDGETOIL 19 NOV 5000 CALL", "SELL", 2, "5010.00", "10020.00"),
            row("2026-10-16", "14:31:19", "WIDGETOIL 19 NOV 5000 CALL", "SELL", 1, "4990.00", "4990.00"),
            row("2026-10-16", "14:31:19", "WIDGETOIL 19 NOV 5000 CALL", "SELL", 1, "4990.00", "4990.00"),
            row("2026-10-16", "15:00:00", "WIDGETOIL 19 NOV 5000 CALL", "BUY", 2, "4985.00", "9970.00"),
        ],
    )

    block = [
        row("2026-10-15", "09:30:00", "WIDGETOIL 19 NOV 5000 CALL", "BUY", 1, "5100.00", "5100.00"),
        row("2026-10-15", "09:45:12", "WIDGETOIL 19 NOV 5000 CALL", "SELL", 1, "5120.00", "5120.00"),
        row("2026-10-15", "10:05:55", "WIDGETOIL 19 NOV 5000 CALL", "BUY", 3, "5115.00", "15345.00"),
    ]
    write("duplicated_block.csv", HEADER, [*block, *block])

    write(
        "clean.csv",
        HEADER,
        [
            row("2026-10-14", "09:20:01", "WIDGETOIL 19 NOV 5000 CALL", "BUY", 1, "5200.00", "5200.00"),
            row("2026-10-14", "10:11:30", "WIDGETOIL 19 NOV 5000 CALL", "SELL", 1, "5215.00", "5215.00"),
            row("2026-10-14", "13:40:07", "WIDGETOIL 19 NOV 5000 CALL", "BUY", 2, "5190.00", "10380.00"),
            row("2026-10-14", "14:55:44", "WIDGETOIL 19 NOV 5000 CALL", "SELL", 2, "5205.00", "10410.00"),
        ],
    )

    with_ids = [
        row("2026-10-13", "09:30:00", "WIDGETOIL 19 NOV 5000 CALL", "BUY", 1, "5300.00", "5300.00") + ",ORD-1",
        row("2026-10-13", "09:30:00", "WIDGETOIL 19 NOV 5000 CALL", "BUY", 1, "5300.00", "5300.00") + ",ORD-1",
        row("2026-10-13", "10:00:00", "WIDGETOIL 19 NOV 5000 CALL", "SELL", 1, "5310.00", "5310.00") + ",ORD-2",
        row("2026-10-13", "11:00:00", "WIDGETOIL 19 NOV 5000 CALL", "BUY", 1, "5295.00", "5295.00") + ",ORD-3",
        row("2026-10-13", "11:00:00", "WIDGETOIL 19 NOV 5000 CALL", "BUY", 1, "5295.00", "5295.00") + ",ORD-3",
        row("2026-10-13", "11:00:00", "WIDGETOIL 19 NOV 5000 CALL", "BUY", 1, "5295.00", "5295.00") + ",ORD-3",
    ]
    write("with_fill_ids.csv", HEADER_WITH_ID, with_ids)


if __name__ == "__main__":
    main()
