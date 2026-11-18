"""Moved out of tests/unit/api/test_trade_rows.py by TICKET-945, so that no test file imports another.

Fixtures are not kept here: each fixture that lived in that file is a plain function
below, and the fixture of the same name calls it.
"""

from __future__ import annotations

import re
from decimal import Decimal

from tests.helpers.upload import DUPES, upload

OPTION_ROWS = [
    ("2026-11-19", "09:30:00", 5000, "CALL", "BUY", "10.00"),
    ("2026-11-19", "09:40:00", 5000, "CALL", "SELL", "12.50"),
    ("2026-11-17", "14:00:00", 5000, "PUT", "BUY", "120.00"),
    ("2026-11-17", "14:20:00", 5000, "PUT", "SELL", "114.00"),
    ("2026-10-15", "10:00:00", 5200, "CALL", "SELL", "20.00"),
    ("2026-10-15", "11:00:00", 5200, "CALL", "BUY", "25.00"),
    ("2026-10-14", "09:30:00", 5100, "CALL", "BUY", "10.00"),
    ("2026-10-14", "09:30:05", 5000, "CALL", "SELL", "30.00"),
    ("2026-10-14", "15:00:00", 5100, "CALL", "SELL", "4.00"),
    ("2026-10-14", "15:00:05", 5000, "CALL", "BUY", "11.00"),
    ("2025-11-03", "11:00:00", 5400, "CALL", "BUY", "60.00"),
    ("2025-11-03", "11:30:00", 5400, "CALL", "SELL", "70.00"),
]


SHARE_ROWS = [
    ("2026-10-20", "10:00:00", "BUY", "100.00"),
    ("2026-10-28", "10:00:00", "SELL", "110.00"),
]


def tradebook(extra: tuple[str, ...] = ()) -> bytes:
    header = (DUPES / "clean.csv").read_text().splitlines()[0]
    options = [
        f"{day},{time},WIDGETOIL 19 NOV {strike} {kind},{side},INTRADAY,MCX,Commodity,100,"
        f"{price},{Decimal(price) * 100:.2f},Traded"
        for day, time, strike, kind, side, price in OPTION_ROWS
    ]
    shares = [
        f"{day},{time},Widget ETF,{side},DELIVERY,NSE,Equity,10,{price},"
        f"{Decimal(price) * 10:.2f},Traded"
        for day, time, side, price in SHARE_ROWS
    ]
    return ("\n".join([header, *options, *shares, *extra]) + "\n").encode()


def trade_rows_uploaded(client, engine):
    response = upload(client, content=tradebook())
    assert response.status_code == 303
    return client


def text(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).replace("&#39;", "'").split())


def articles(html: str) -> list[str]:
    """Each trade on a page, as a reader reads it."""
    return [text(a) for a in re.findall(r'<article class="trade">.*?</article>', html, re.DOTALL)]
