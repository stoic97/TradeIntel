"""TICKET-995 review (24 Nov): the jolt line's two figures count the same trades.

"Your average winner is ₹A. Each trade pays ₹C in charges." compares A with C, so both are over
the trades in the waterfall: the trades whose charges are known. A trade left out of the
waterfall (no charge for it) is in neither.

Every trade here is made up. Worked by hand, from the rate rows as in test_charges_waterfall.py:

One WIDGETOIL option trade, 100 bought at 52.00, from 1 Oct 2024 (MCX_OPT rows as in
test_charges_waterfall.py: exchange 0.000418, CTT sell 0.0005, stamp buy 0.00003, SEBI 0.000001,
GST 0.18; Dhan Rs 20 an order):
    sold at 57.00 (912's figure)                 sold at 47.00
    Brokerage 2 x 20               40            40
    CTT       0.0005 x 5,700        2.85         0.0005 x 4,700       2.35
    Exchange  0.000418 x 10,900     4.5562       0.000418 x 9,900     4.1382
    SEBI fee  0.000001 x 10,900     0.0109       0.000001 x 9,900     0.0099
    Stamp     0.00003 x 5,200       0.156        0.156
    GST       0.18 x 44.5671        8.022078     0.18 x 44.1481       7.946658
    Total                          55.595178                         54.600758
A priced trade's result is after its charges (gross less the total above).

The record, 32 trades, every one closed the day it opened:
    30 trades, two a day, 1 to 15 Oct 2025. Trade i (0 to 29) sold at 47.00 when i is a
    multiple of 3, else at 57.00:
        losers  i = 0, 3, ..., 27     10 trades, gross 100 x (47 - 52) = -500 each
        winners the other 20          20 trades, gross 100 x (57 - 52) = +500 each,
                                      after charges 500 - 55.595178 = 444.404822 each
    2 trades on 30 Sep 2024, sold at 80.00: gross 100 x (80 - 52) = +2,800 each. Before the
    rate table, so not priced: left out of the waterfall, their result before charges.

In the waterfall: the 30 Oct 2025 trades.
    Charges          20 x 55.595178 + 10 x 54.600758 = 1,111.90356 + 546.00758 = 1,657.91114
    Each trade pays  1,657.91114 / 30 = 55.2637..., cut to whole rupees: ₹55
    Average winner   20 x 444.404822 / 20 = 444.404822: ₹444

Over every same-day trade instead (the left-out two included), the average winner would be
(20 x 444.404822 + 2 x 2,800) / 22 = 14,488.09644 / 22 = 658.549...: ₹658. That is the
mismatch the review found; the page must not show it.
"""
from __future__ import annotations

import re
from decimal import Decimal as D

import pytest
from sqlalchemy import select

from services.production.ctr.intake import persist
from services.production.ctr.intake import pipeline as pl
from services.production.db import models as m
from services.production.db.session import make_session
from tests.helpers.upload import upload_client, upload_engine

DHAN = "Date,Time,Name,Buy/Sell,Order,Exchange,Segment,Quantity/Lot,Trade Price,Trade Value,Status"
CONTRACT = "WIDGETOIL 17 OCT 6950 CALL"


def _trade(day: str, sold: str, at: str) -> list[str]:
    value = D(sold) * 100
    return [f"{day},{at}:00:00,{CONTRACT},BUY,INTRADAY,MCX,Commodity,100,52.00,5200.00,Traded",
            f"{day},{at}:30:00,{CONTRACT},SELL,INTRADAY,MCX,Commodity,100,{sold},{value:.2f},Traded"]


def _record() -> str:
    rows = []
    for i in range(30):
        rows += _trade(f"2025-10-{1 + i // 2:02d}", "47.00" if i % 3 == 0 else "57.00",
                       ("10", "12")[i % 2])
    rows += _trade("2024-09-30", "80.00", "10") + _trade("2024-09-30", "80.00", "12")
    return "\n".join([DHAN, *rows]) + "\n"


@pytest.fixture()
def engine():
    return upload_engine()


@pytest.fixture()
def client(engine):
    return upload_client(engine)


def _store(engine, text: str) -> None:
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader)).first()
        plan = pl.plan_import(text, context=pl.ImportContext(
            trader_id="t", source_account="A", code_version="test", charges=pl.ChargesInput()))
        persist.write_plan(sess, trader=trader, plan=plan, raw_sha256="a" * 64,
                           original_name="made-up.csv", stored_path="x", size=len(text))
        sess.commit()


def _text(client) -> str:
    html = client.get("/mirror/fact/charges").text
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html))


def test_the_average_winner_and_each_trade_s_charges_are_over_the_same_trades(client, engine):
    _store(engine, _record())
    text = _text(client)
    assert "Your average winner is ₹444. Each trade pays ₹55 in charges." in text


def test_a_trade_left_out_of_the_waterfall_is_not_in_the_average_winner(client, engine):
    _store(engine, _record())
    text = _text(client)
    assert "Your average winner is ₹658" not in text
    assert "2 trades are not in this: their result is before charges." in text
