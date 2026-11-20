"""Moved out of tests/unit/api/test_spread_upload.py by TICKET-945, so that no test file imports another."""

from __future__ import annotations

import re
from decimal import Decimal

from sqlalchemy import select

from services.production.db import models as m
from services.production.db.session import make_session
from services.production.mirror import loader
from tests.helpers.upload import DUPES

ROWS = [
    ("2026-10-14", "09:30:00", 5100, "BUY", "10.00"),
    ("2026-10-14", "09:30:05", 5000, "SELL", "30.00"),
    ("2026-10-14", "12:00:00", 5300, "BUY", "5.00"),
    ("2026-10-14", "12:30:00", 5300, "SELL", "7.00"),
    ("2026-10-14", "15:00:00", 5100, "SELL", "4.00"),
    ("2026-10-14", "15:00:05", 5000, "BUY", "11.00"),
    ("2026-10-15", "10:00:00", 5200, "SELL", "20.00"),
    ("2026-10-15", "11:00:00", 5200, "BUY", "25.00"),
    ("2026-10-15", "12:00:00", 5400, "BUY", "3.00"),
    ("2026-10-15", "12:30:00", 5400, "SELL", "4.00"),
    ("2026-10-16", "09:30:00", 5500, "BUY", "2.00"),
    ("2026-10-16", "10:00:00", 5500, "SELL", "2.50"),
    ("2026-10-16", "11:00:00", 5600, "BUY", "2.00"),
    ("2026-10-16", "11:30:00", 5600, "SELL", "2.50"),
]


def tradebook() -> bytes:
    header = (DUPES / "clean.csv").read_text().splitlines()[0]
    lines = [
        f"{day},{time},WIDGETOIL 19 NOV {strike} CALL,{side},INTRADAY,MCX,Commodity,100,"
        f"{price},{Decimal(price) * 100:.2f},Traded"
        for day, time, strike, side, price in ROWS
    ]
    return ("\n".join([header, *lines]) + "\n").encode()


def text(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).replace("&#39;", "'").split())


def loaded(engine):
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader)).one()
        return loader.load_for(sess, trader)[0]
