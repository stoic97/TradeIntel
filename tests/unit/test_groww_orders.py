"""TICKET-895: Groww's order history, read the way an upload reads it.

Groww exports an Excel workbook with the account holder's name and client code above
its header, one row per exchange order, a total value and no price. Every figure here is
made up; the layout is the real one.
"""

from __future__ import annotations

import io
import zipfile
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path

import pytest

from services.production.ctr.adapters import filemap, groww_orders
from services.production.ctr.intake import outcomes as oc
from services.production.ctr.intake import pipeline as pl
from services.production.ctr.intake import workbook
from services.production.ctr.profiles import registry as profiles
from services.production.mirror import loader
from services.shared.schemas import scope_v1 as s
from services.shared.schemas.ctr_v1 import OptionType, Segment

FIXTURE = Path("data/fixtures/groww_orders_sample.xlsx")
HEADER = ",".join(groww_orders.HEADER)


def text() -> str:
    return pl.text_of(FIXTURE.read_bytes())


def parsed():
    return groww_orders.parse(text().splitlines(), trader_id="t", raw_hash="0" * 64)


def plan(body: str | None = None, *, production: bool = True) -> pl.ImportPlan:
    return pl.plan_import(body if body is not None else text(), production=production,
                          context=pl.ImportContext(trader_id="t", source_account="A",
                                                   code_version="test"))


def row(symbol: str, *, name: str = "X", isin: str = "", side: str = "BUY", qty: str = "65",
        value: str = "6500", exchange: str = "NSE", when: str = "12-11-2026 10:00 AM",
        status: str = "Executed") -> list[str]:
    line = f"{name},{symbol},{isin},{side},{qty},{value},{exchange},1000000000000001,{when},{status}"
    return [HEADER, line]


def one(symbol: str, **kw):
    got = groww_orders.parse(row(symbol, **kw), trader_id="t", raw_hash="0" * 64)
    assert got.rows_in == 1
    return got


# ---------- 1. Beside Dhan, selected by its header; an unknown file still has none ----------


def test_the_groww_header_selects_the_groww_adapter():
    adapter = oc.select_adapter(text())
    assert adapter is not None and adapter.adapter_id == groww_orders.FORMAT_ID
    assert adapter.parse is groww_orders.parse


def test_a_file_no_adapter_knows_is_still_rejected_not_guessed():
    p = plan("Symbol,Realised P&L\nWIDGETOIL,1500.00\n")
    assert p.outcome is s.ImportOutcome.REJECTED and p.adapter_id is None


def test_an_import_whose_adapter_is_gone_still_raises_unknown_adapter():
    assert oc.adapter_for("groww_orders_v0") is None
    assert hasattr(loader, "UnknownAdapter")


# ---------- the workbook: read from its header down, the preamble left behind ----------


def test_a_workbook_is_read_from_its_header_and_its_name_and_client_code_are_left_behind():
    body = text()
    assert body.splitlines()[0] == HEADER
    for preamble in ("Sample Trader", "Unique Client Code", "Order history for stocks"):
        assert preamble not in body


def test_no_stored_row_carries_the_preamble():
    for planned in plan().rows:
        assert "Sample Trader" not in planned.raw_text


def test_a_value_is_kept_as_the_workbook_wrote_it():
    assert ",4595.5,NSE," in text()


def test_a_comma_in_a_stock_name_stays_one_column():
    assert any(f.symbol == "BAJFINANCE" for f in parsed().fills)


def test_a_csv_that_already_starts_at_its_header_is_kept_byte_for_byte():
    raw = Path("data/fixtures/dhan_tradebook_sample.csv").read_bytes()
    assert pl.text_of(raw) == raw.decode("utf-8-sig")


def test_a_csv_with_a_preamble_above_its_header_is_read_from_the_header():
    body = "Name,Someone\nUnique Client Code,123\n\n" + "\n".join(row("NIFTY26N1724000CE")) + "\n"
    assert pl.text_of(body.encode()).splitlines()[0] == HEADER


def test_a_csv_with_a_line_too_big_to_parse_comes_back_whole_for_the_format_check():
    huge = b"x" * 300_000
    assert pl.text_of(huge) == huge.decode()
    assert plan(pl.text_of(huge)).outcome is s.ImportOutcome.REJECTED


def test_a_float_written_with_noise_reads_as_the_number_it_is():
    assert workbook._number("1234.4999999999998") == "1234.5"
    assert workbook._number("25210.5") == "25210.5"


def test_a_file_that_claims_to_be_a_workbook_and_is_not_is_rejected_not_raised():
    p = plan(pl.text_of(b"PK\x03\x04 not really a zip"))
    assert p.outcome is s.ImportOutcome.REJECTED


def test_a_workbook_with_no_known_header_is_rejected():
    buffer = io.BytesIO()
    with zipfile.ZipFile(FIXTURE) as src, zipfile.ZipFile(buffer, "w") as out:
        for name in src.namelist():
            body = src.read(name)
            if name == "xl/sharedStrings.xml":
                body = body.replace(b"Execution date and time", b"Trade time")
            out.writestr(name, body)
    assert plan(pl.text_of(buffer.getvalue())).outcome is s.ImportOutcome.REJECTED


# ---------- 2. Its own golden: see tests/reproducibility/test_golden_groww.py ----------
# ---------- 3. Quantity units, stated and enforced ----------


def test_the_map_declares_units_and_is_verified():
    m = filemap.require_verified(filemap.load(oc.adapter_for(groww_orders.FORMAT_ID).filemap_path))
    assert m.broker == "Groww" and m.quantity_unit == "units"
    assert m.wanted.broker_name == "Order history"


def test_one_nifty_lot_in_units_is_one_lot_and_a_size_no_lot_divides_raises():
    nifty = profiles.load_all(pl.PROFILE_DIR)[("NSE", "NIFTY")]
    assert loader.lots_for(65, nifty, "units", on=date(2026, 11, 12)) == 1
    with pytest.raises(loader.MisdeclaredQuantityUnit):
        loader.lots_for(1, nifty, "units", on=date(2026, 11, 12))


def test_a_share_quantity_that_is_not_whole_is_rejected():
    got = one("INFY", isin="INE009A01021", qty="2.5", value="4000")
    assert "not whole" in got.rejected[0].reason


# ---------- 4. Value is the total; the price is derived from it ----------


def test_the_value_is_the_orders_total_and_the_price_comes_from_it():
    infy = next(f for f in parsed().fills if f.symbol == "INFY" and f.side.value == "BUY")
    assert infy.trade_value == Decimal("4595.5")
    assert infy.price == Decimal("4595.5") / 3
    assert infy.quoted_price is None


def test_an_order_filled_at_several_prices_keeps_its_exact_total_through_a_trip():
    (infy,) = [t for t in plan().trips if t.symbol == "INFY"]
    assert infy.gross_pnl == Decimal("204.50")


# ---------- 5. Charges: the file has none, and says so ----------


def test_the_order_history_has_no_charges_so_every_figure_is_gross():
    p = plan()
    assert p.fees_available is False and "fees" in p.missing_fields
    assert p.outcome is s.ImportOutcome.ACCEPTED_PARTIAL_FIELDS


# ---------- 6. The import records which adapter and which profiles ----------


def test_the_import_records_the_adapter_and_the_profile_versions():
    p = plan()
    assert (p.adapter_id, p.adapter_version) == (groww_orders.FORMAT_ID, "1")
    assert {"NSE:*", "BSE:*", "NSE:NIFTY", "NSE:BANKNIFTY"} <= set(p.profile_versions)
    assert p.instruments_without_profile == ()


# ---------- 7. Profiles reused: contracts named the exchanges' way ----------


@pytest.mark.parametrize(("symbol", "name", "exchange", "when", "want"), [
    ("NIFTY26N1724000CE", "", "NSE", "12-11-2026 10:00 AM",
     (Segment.OPT, "NIFTY", date(2026, 11, 17), Decimal(24000), OptionType.CE)),
    ("NIFTY26D0124000PE", "", "NSE", "12-11-2026 10:00 AM",
     (Segment.OPT, "NIFTY", date(2026, 12, 1), Decimal(24000), OptionType.PE)),
    ("BANKNIFTY26NOV52000PE", "", "NSE", "10-11-2026 11:00 AM",
     (Segment.OPT, "BANKNIFTY", date(2026, 11, 24), Decimal(52000), OptionType.PE)),
    ("NIFTY26NOVFUT", "", "NSE", "10-11-2026 11:00 AM",
     (Segment.FUT, "NIFTY", date(2026, 11, 24), None, None)),
    ("NIFTY24DEC24000CE", "", "NSE", "02-12-2024 10:00 AM",
     (Segment.OPT, "NIFTY", date(2024, 12, 26), Decimal(24000), OptionType.CE)),
    ("SENSEX25JAN80000CE", "", "BSE", "02-01-2025 10:00 AM",
     (Segment.OPT, "SENSEX", date(2025, 1, 28), Decimal(80000), OptionType.CE)),
    # Thursday 30 Mar 2023 was a holiday (Ram Navami): the monthly expired on the Wednesday
    ("NIFTY23MAR17000CE", "", "NSE", "01-03-2023 10:00 AM",
     (Segment.OPT, "NIFTY", date(2023, 3, 29), Decimal(17000), OptionType.CE)),
    ("NIFTY26NOV24000CE", "NIFTY 23 Nov 24000 Call", "NSE", "10-11-2026 11:00 AM",
     (Segment.OPT, "NIFTY", date(2026, 11, 23), Decimal(24000), OptionType.CE)),
    ("NSE-NIFTY-17Nov26-24000-CE", "", "NSE", "12-11-2026 10:00 AM",
     (Segment.OPT, "NIFTY", date(2026, 11, 17), Decimal(24000), OptionType.CE)),
])
def test_a_contract_is_read_from_its_symbol(symbol, name, exchange, when, want):
    (fill,) = one(symbol, name=name or "X", exchange=exchange, when=when).fills
    assert (fill.segment, fill.symbol, fill.expiry, fill.strike, fill.option_type) == want


def test_a_share_is_its_symbol_with_its_isin_and_a_bse_share_finds_the_bse_profile():
    (fill,) = one("TATASTEEL", isin="INE081A01020", exchange="BSE", qty="20", value="3100").fills
    assert (fill.segment, fill.symbol, fill.exchange) == (Segment.EQ, "TATASTEEL", "BSE")
    found = profiles.lookup(profiles.load_all(pl.PROFILE_DIR), "BSE", "TATASTEEL", Segment.EQ)
    assert found is not None and found.key == ("BSE", "*")


@pytest.mark.parametrize(("symbol", "kw", "why"), [
    ("NOT A CONTRACT", {}, "cannot be identified"),
    ("CRUDEOIL26NOV5000CE", {"exchange": "MCX"}, "no rule for that exchange"),
    ("NIFTY26N3124000CE", {}, "no real expiry"),
    ("NIFTY26N1024000CE", {}, "before the trade"),
    ("INFY", {"isin": "INE009A01021", "status": "Cancelled"}, "Cancelled"),
    ("INFY", {"isin": "INE009A01021", "side": "HOLD"}, "unknown side"),
    ("INFY", {"isin": "INE009A01021", "when": "2026-11-12 10:00"}, "unparseable"),
    ("INFY", {"isin": "INE009A01021", "value": "0"}, "must be positive"),
])
def test_a_row_that_cannot_be_read_is_rejected_with_its_reason(symbol, kw, why):
    got = one(symbol, **kw)
    assert not got.fills and why in got.rejected[0].reason


# ---------- the clock ----------


def test_times_are_ist_to_the_minute_from_a_12_hour_clock():
    fill = next(f for f in parsed().fills if f.symbol == "RELIANCE" and f.side.value == "SELL")
    assert fill.ts.tzinfo is not None and fill.ts.utcoffset().total_seconds() == 19800
    assert fill.ts == datetime(2026, 11, 2, 14, 45, tzinfo=groww_orders.IST)


def test_an_after_market_order_keeps_the_0900_it_was_stamped_with():
    sbin = next(f for f in parsed().fills if f.symbol == "SBIN" and f.side.value == "BUY")
    assert sbin.ts.time() == time(9, 0)


def test_every_row_is_a_fill_or_a_rejection():
    got = parsed()
    assert got.rows_in == 20 and len(got.fills) == 17 and len(got.rejected) == 3


def test_a_share_with_its_own_options_profile_is_still_read_as_cash_equity():
    """RELIANCE's profile is its options' (lot 500): ten shares are not a fiftieth of a lot."""
    found = profiles.load_all(pl.PROFILE_DIR)
    assert profiles.lookup(found, "NSE", "RELIANCE", Segment.EQ).key == ("NSE", "*")
    assert profiles.lookup(found, "NSE", "RELIANCE", Segment.OPT).key == ("NSE", "RELIANCE")
    assert "NSE:RELIANCE" not in plan().profile_versions


def test_the_closure_calendar_was_read_from_the_exchanges_and_holds_dates_only():
    from services.shared.market import closures

    shut = closures.load()
    assert set(shut) == {"NSE", "BSE"}
    assert date(2023, 3, 30) in shut["NSE"].closed and date(2026, 1, 26) in shut["BSE"].closed
    assert shut["NSE"].trading_day_on_or_before(date(2023, 3, 30)) == date(2023, 3, 29)
    assert shut["NSE"].trading_day_on_or_before(date(2030, 1, 3)) == date(2030, 1, 3)
