"""Cycle 2a — the Dhan tradebook adapter.

Rows below are the real shapes from a Dhan export (instrument data only; no
account details). The rules each test locks were established by inspecting
3,828 real rows, and the reasoning is in the commit message.

Header, verbatim:
    Date,Time,Name,Buy/Sell,Order,Exchange,Segment,Quantity/Lot,Trade Price,Trade Value,Status
"""
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from services.production.ctr.adapters.dhan_tradebook import HEADER, parse
from services.shared.schemas.ctr_v1 import OptionType, Segment, Side

IST = ZoneInfo("Asia/Kolkata")
RAW = "b" * 64

NIFTY_SELL = "2026-09-17,09:48:11,NIFTY 22 SEP 23300 PUT,SELL,INTRADAY,NSE,Derivative,65,140.45,9129.25,Traded"
NIFTY_BUY = "2026-09-17,09:39:08,NIFTY 22 SEP 23300 PUT,BUY,INTRADAY,NSE,Derivative,65,135.20,8788.00,Traded"
CRUDE_SELL = "2026-05-13,18:03:52,CRUDEOILM 14 MAY 9700 CALL,SELL,INTRADAY,MCX,Commodity,10,204.20,2042.00,Traded"
EQUITY = "2026-02-06,13:41:22,Jio Financial Services,SELL,DELIVERY,NSE,Equity,10,267.60,2676.00,Traded"
# Aggregated fills: 30 x 153.18 = 4595.40, but the broker's exact total is 4595.50.
AGGREGATED = "2026-11-10,14:02:00,CRUDEOILM 17 NOV 5300 PUT,BUY,INTRADAY,MCX,Commodity,30,153.18,4595.50,Traded"
# 16201.50 / 60 = 270.025 exactly -> rounds half-up to the quoted 270.03.
HALF_UP_TIE = "2026-10-01,11:00:00,CRUDEOILM 17 OCT 5900 PUT,BUY,INTRADAY,MCX,Commodity,60,270.03,16201.50,Traded"
# December trade, January expiry: the year must roll forward.
YEAR_ROLL = "2026-12-28,10:15:00,NIFTY 01 JAN 24000 CALL,BUY,INTRADAY,NSE,Derivative,75,88.40,6630.00,Traded"


def run(*lines):
    return parse([",".join(HEADER), *lines], trader_id="T01", raw_hash=RAW)


def only(*lines):
    r = run(*lines)
    assert not r.rejected, f"unexpectedly rejected: {r.rejected}"
    assert len(r.fills) == 1
    return r.fills[0]


# ---------------------------------------------------------------- the format

def test_header_must_match_exactly():
    with pytest.raises(ValueError, match="header"):
        parse(["Date,Time,Name,WRONG", NIFTY_BUY], trader_id="T01", raw_hash=RAW)


def test_every_row_is_accounted_for():
    """raw = mapped + rejected, always (Methodology s2 Rule 1)."""
    r = run(NIFTY_BUY, EQUITY, "2026-01-01,10:00:00,GARBAGE,BUY,INTRADAY,NSE,Derivative,1,1,1,Traded")
    assert len(r.fills) + len(r.rejected) == 3


def test_rejection_carries_row_number_and_reason():
    r = run("2026-01-01,10:00:00,GARBAGE,BUY,INTRADAY,NSE,Derivative,1,1,1,Traded")
    assert r.rejected[0].row == 2
    assert r.rejected[0].reason


# ---------------------------------------------------------------- parsing

def test_parses_a_nifty_option_row():
    f = only(NIFTY_BUY)
    assert f.exchange == "NSE"
    assert f.segment is Segment.OPT
    assert f.symbol == "NIFTY"
    assert f.expiry == date(2026, 9, 22)
    assert f.strike == Decimal(23300)
    assert f.option_type is OptionType.PE
    assert f.side is Side.BUY
    assert f.quantity == 65
    assert f.product == "INTRADAY"


def test_parses_a_crude_option_row_in_the_evening_session():
    f = only(CRUDE_SELL)
    assert f.exchange == "MCX"
    assert f.symbol == "CRUDEOILM"
    assert f.option_type is OptionType.CE
    assert f.ts.hour == 18
    assert f.side is Side.SELL


def test_parses_an_equity_row_with_no_contract_fields():
    f = only(EQUITY)
    assert f.segment is Segment.EQ
    assert f.symbol == "Jio Financial Services"
    assert f.expiry is None
    assert f.strike is None
    assert f.option_type is None


def test_timestamp_is_ist():
    f = only(NIFTY_BUY)
    assert f.ts == datetime(2026, 9, 17, 9, 39, 8, tzinfo=IST)


def test_raw_hash_is_attached():
    assert only(NIFTY_BUY).raw_hash == RAW


def test_rows_are_sorted_by_timestamp():
    """The export is newest-first; file order is not trusted."""
    r = run(NIFTY_SELL, NIFTY_BUY)
    assert [f.ts.strftime("%H:%M:%S") for f in r.fills] == ["09:39:08", "09:48:11"]


# ---------------------------------------------------------------- expiry year

def test_expiry_year_comes_from_the_trade_date():
    assert only(CRUDE_SELL).expiry == date(2026, 5, 14)


def test_expiry_year_rolls_into_the_next_year():
    """78 rows in the real file trade in December against a January expiry."""
    assert only(YEAR_ROLL).expiry == date(2027, 1, 1)


def test_expiry_more_than_120_days_out_is_rejected():
    """An expiry that far ahead means the inference misfired; refuse, never guess."""
    stale = "2026-05-20,10:00:00,CRUDEOILM 14 MAY 9700 CALL,BUY,INTRADAY,MCX,Commodity,10,195.05,1950.50,Traded"
    r = run(stale)
    assert not r.fills
    assert "expiry" in r.rejected[0].reason.lower()


# ---------------------------------------------------------------- price

def test_price_comes_from_trade_value_not_the_quoted_price():
    """Trade Value is exact; the quoted price is a rounded average of aggregated fills."""
    f = only(AGGREGATED)
    assert f.price == Decimal("4595.50") / Decimal(30)
    assert f.price != Decimal("153.18")


def test_quoted_price_is_preserved_for_display():
    assert only(AGGREGATED).quoted_price == Decimal("153.18")


def test_half_up_rounding_tie_is_accepted():
    """16201.50 / 60 = 270.025 -> 270.03 under ROUND_HALF_UP, which is what Dhan shows."""
    f = only(HALF_UP_TIE)
    assert f.quoted_price == Decimal("270.03")


def test_value_inconsistent_with_quoted_price_is_rejected():
    bad = "2026-05-13,18:03:52,CRUDEOILM 14 MAY 9700 CALL,BUY,INTRADAY,MCX,Commodity,10,204.20,9999.00,Traded"
    r = run(bad)
    assert not r.fills
    assert "value" in r.rejected[0].reason.lower()


def test_fees_are_not_invented():
    """The export carries no charges column, so every figure from it is gross."""
    r = run(NIFTY_BUY)
    assert r.fees_available is False


# ---------------------------------------------------------------- status

def test_non_traded_status_is_rejected():
    cancelled = NIFTY_BUY.replace(",Traded", ",Cancelled")
    r = run(cancelled)
    assert not r.fills
    assert "status" in r.rejected[0].reason.lower()
