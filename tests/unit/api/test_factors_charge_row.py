"""TICKET-995 review (24 Nov): /factors says whether his own file let Scope look at each factor.

The "What charges took, charge by charge" row read "in your file" for every trader with a trade,
because the trade list's charge filter answers with a list and an empty list was counted as
seen. A file whose trades carry no charge must read "Not in your file"; one whose trades carry
charges must read "Yes". Made-up trades only.
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

ROW = "What charges took, charge by charge"
DHAN = "Date,Time,Name,Buy/Sell,Order,Exchange,Segment,Quantity/Lot,Trade Price,Trade Value,Status"
CONTRACT = "WIDGETOIL 17 OCT 6950 CALL"


def _dhan(*days: str) -> str:
    rows = []
    for day in days:
        rows.append(f"{day},10:00:00,{CONTRACT},BUY,INTRADAY,MCX,Commodity,100,52.00,5200.00,Traded")
        rows.append(f"{day},10:30:00,{CONTRACT},SELL,INTRADAY,MCX,Commodity,100,57.00,"
                    f"{D('57.00') * 100:.2f},Traded")
    return "\n".join([DHAN, *rows]) + "\n"


def _store(engine, charges: pl.ChargesInput | None) -> None:
    text = _dhan("2024-09-30", "2024-10-01", "2024-10-02")
    plan = pl.plan_import(text, context=pl.ImportContext(
        trader_id="t", source_account="A", code_version="test", charges=charges))
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader)).first()
        persist.write_plan(sess, trader=trader, plan=plan, raw_sha256="a" * 64,
                           original_name="made-up.csv", stored_path="x", size=len(text))
        sess.commit()


def _row(client) -> str:
    page = client.get("/factors").text
    rows = dict(re.findall(r'<tr data-factor="([^"]+)">.*?<td class="factor-map__file">([^<]+)</td>',
                           page, re.DOTALL))
    return rows[ROW]


@pytest.fixture()
def engine():
    return upload_engine()


@pytest.fixture()
def client(engine):
    return upload_client(engine)


def test_a_file_whose_trades_carry_no_charge_reads_not_in_your_file(client, engine):
    _store(engine, None)
    assert _row(client) == "Not in your file"


def test_a_file_whose_trades_carry_charges_reads_yes(client, engine):
    _store(engine, pl.ChargesInput())
    assert _row(client) == "Yes"
