"""Moved out of tests/unit/api/test_dates_with_year.py by TICKET-945, so that no test file imports another."""

from __future__ import annotations

MONTHS = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"


HEADER = (
    "Date,Time,Name,Buy/Sell,Order,Exchange,Segment,Quantity/Lot,Trade Price,Trade Value,Status"
)


DAYS = ["2024-06-14", "2024-11-05", "2025-01-07", "2025-08-14", "2026-03-27", "2026-07-13"]


def _day_rows(day: str, loss: int) -> list[str]:
    # An expiry in the same month: the adapter rejects one too far from the trade.
    option = f"WIDGETOIL 28 {MONTHS.split('|')[int(day[5:7]) - 1].upper()} 5000 CALL"
    rows = []
    for time_in, time_out, sold in (
        ("09:30:00", "09:40:00", 5000 - loss),
        ("10:00:00", "10:10:00", 5100),
    ):
        rows.append(f"{day},{time_in},{option},BUY,INTRADAY,MCX,Commodity,100,50.00,5000.00,Traded")
        rows.append(
            f"{day},{time_out},{option},SELL,INTRADAY,MCX,Commodity,100,{sold / 100:.2f},{sold:.2f},Traded"
        )
    return rows


FILE = (
    "\n".join(
        [HEADER, *[row for i, day in enumerate(DAYS) for row in _day_rows(day, 100 * (i + 1))]]
    )
    + "\n"
)
