"""Moved out of tests/unit/api/test_add_charges.py by TICKET-945, so that no test file imports another."""

from __future__ import annotations

NAME = "WIDGETOIL 19 MAR 5000 CALL"


FILE = (
    "\n".join(
        [
            "Date,Time,Name,Buy/Sell,Order,Exchange,Segment,Quantity/Lot,Trade Price,Trade Value,Status",
            f"2020-03-02,09:30:00,{NAME},BUY,INTRADAY,MCX,Commodity,100,10.00,1000.00,Traded",
            f"2020-03-02,10:00:00,{NAME},SELL,INTRADAY,MCX,Commodity,100,12.00,1200.00,Traded",
            f"2020-03-03,09:30:00,{NAME},BUY,INTRADAY,MCX,Commodity,100,20.00,2000.00,Traded",
            f"2020-03-03,10:00:00,{NAME},SELL,INTRADAY,MCX,Commodity,100,15.00,1500.00,Traded",
        ]
    ).encode()
    + b"\n"
)


FULL = b"Date,Total Charges\n2020-03-02,50.50\n2020-03-03,60.25\n"
