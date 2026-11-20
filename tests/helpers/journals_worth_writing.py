"""Moved out of tests/unit/api/test_journals_worth_writing.py by TICKET-945, so that no test file imports another."""

from __future__ import annotations

import re

from sqlalchemy import select

from services.production.db import models as m
from services.production.db.session import make_session

HEADER = (
    "Date,Time,Name,Buy/Sell,Order,Exchange,Segment,Quantity/Lot,Trade Price,Trade Value,Status"
)


OPTION = "WIDGETOIL 28 FEB 5000 CALL"


LOT = 100


HISTORY = {
    "2025-02-03": [(1, 50), (1, 50)],
    "2025-02-04": [(1, -100), (1, 10)],
    "2025-02-05": [(1, -200), (1, 10)],
    "2025-02-06": [(1, -300), (1, 10)],
    "2025-02-07": [(1, -400), (1, 10)],
    "2025-02-10": [(1, -500), (1, 10)],
    "2025-02-11": [(1, -40), (1, -10), (1, -10), (3, -30), (1, 100)],
    "2025-02-12": [(1, 5), (1, -20), (1, 5), (1, 5), (1, 5), (1, 5)],
    "2025-02-13": [(1, 50), (1, 60)],
    "2025-02-14": [(1, 50), (1, 50)],
}


def _rows(day: str, trades: list[tuple[int, int]]) -> list[str]:
    rows = []
    for n, (lots, net) in enumerate(trades):
        quantity = lots * LOT
        paid = quantity * 50
        got = paid + net
        hour, opened, closed = 10 + n, f"{10 + n}:00:00", f"{10 + n}:05:00"
        assert hour < 23
        rows.append(
            f"{day},{opened},{OPTION},BUY,INTRADAY,MCX,Commodity,{quantity},50.00,{paid:.2f},Traded"
        )
        rows.append(
            f"{day},{closed},{OPTION},SELL,INTRADAY,MCX,Commodity,{quantity},"
            f"{got / quantity:.2f},{got:.2f},Traded"
        )
    return rows


FILE = (
    "\n".join([HEADER, *[row for day, trades in HISTORY.items() for row in _rows(day, trades)]])
    + "\n"
)


def _journal_ids(engine) -> dict[str, int]:
    with make_session(engine) as sess:
        rows = sess.scalars(select(m.Journal).order_by(m.Journal.version_no)).all()
        return {j.period_start: j.id for j in rows}


def _readable(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())
