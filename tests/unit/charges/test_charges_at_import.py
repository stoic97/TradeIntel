"""TICKET-912: the import works out each trade's charges, once, and records where they came from.

``plan_import`` is pure, so every case runs on text: the demo tradebook (synthetic) and
made-up Dhan and Groww rows. No trader's file is read. Every expected total is worked by
hand from the rate rows it names (rates.yaml) and the broker's plan (brokerage.yaml).

Gate 1: each trade's own date picks its rates. Gate 2: brokerage is the broker's published
plan, which he can change. Gate 6: his own day totals outrank ours.
Rulings 14 Nov 2026 (founder): Q1 a trade the table doesn't reach is not priced, never at
today's rate, and counted; Q2 the plan applies only where the table does, Groww counts its
real orders and Dhan one per entry and one per exit, and the import records which plan and
read date it used; Q4 his day total is shared in proportion to ours, each such trade is
flagged, and the day's totals are kept where they can be seen.
"""

from __future__ import annotations

import json
from decimal import Decimal as D
from pathlib import Path

from services.production.ctr.intake import pipeline as pl

DEMO = Path("data/fixtures/demo/demo_tradebook.csv").read_text(encoding="utf-8")
DHAN = "Date,Time,Name,Buy/Sell,Order,Exchange,Segment,Quantity/Lot,Trade Price,Trade Value,Status"
GROWW = ("Stock name,Symbol,ISIN,Type,Quantity,Value,Exchange,Exchange Order Id,"
         "Execution date and time,Order status")


def plan(text: str, charges: pl.ChargesInput | None = None) -> pl.ImportPlan:
    return pl.plan_import(text, context=pl.ImportContext(
        trader_id="t", source_account="A", code_version="test", charges=charges))


def dhan(*rows: str) -> str:
    return "\n".join([DHAN, *rows]) + "\n"


def groww(*rows: str) -> str:
    return "\n".join([GROWW, *rows]) + "\n"


def nifty_order(side: str, qty: int, value: str, order_no: int, at: str) -> str:
    """One Groww order row for a made-up NIFTY 18 Nov 2025 26000 call, on 13 Nov 2025."""
    return (f"NIFTY 18 Nov 26000 Call,NIFTY25N1826000CE,,{side},{qty},{value},NSE,"
            f"110000000000000{order_no},13-11-2025 {at},Executed")


def widgetoil(day: str) -> tuple[str, str]:
    """100 WIDGETOIL options bought at 52.00, sold at 57.00: premium 5,200 in, 5,700 out."""
    contract = "WIDGETOIL 17 OCT 6950 CALL"
    return (f"{day},10:00:00,{contract},BUY,INTRADAY,MCX,Commodity,100,52.00,5200.00,Traded",
            f"{day},10:30:00,{contract},SELL,INTRADAY,MCX,Commodity,100,57.00,5700.00,Traded")


# MCX_OPT, any day from 1 Oct 2024 (rows 36/40 exchange 0.000418, 53 CTT sell 0.0005,
# 61 stamp buy 0.00003, 76/77 SEBI 0.000001, 92/93 GST 0.18), Dhan Rs 20 per order:
# buy 5,200: exchange 2.1736 + SEBI 0.0052 + stamp 0.156 + GST 0.18 x 2.1788 = 0.392184
# sell 5,700: CTT 2.85 + exchange 2.3826 + SEBI 0.0057 + GST 0.18 x 2.3883 = 0.429894
# brokerage 2 x 20 = 40, GST on it 7.2.  Total 55.595178.
WIDGETOIL_CHARGES = D("55.595178")


def test_without_charges_asked_for_the_trips_carry_only_what_the_file_says():
    got = plan(DEMO)
    assert got.fees_source == "none"
    assert all(t.fees == 0 for t in got.trips)
    assert set(got.trip_fees_source) == {"none"}


def test_each_trade_is_charged_at_its_own_dates_rates_and_net_is_gross_less_charges():
    got = plan(DEMO, pl.ChargesInput())
    first = got.trips[0]            # demo's first trade: 100 at 52.00 out at 57.00, 1 Sep 2026
    assert (first.entry_price, first.exit_price, first.quantity) == (D("52.00"), D("57.00"), 100)
    assert first.fees == WIDGETOIL_CHARGES
    assert first.net_pnl == D(500) - WIDGETOIL_CHARGES
    assert got.fees_source == "calculated"
    assert set(got.trip_fees_source) == {"calculated"}


def test_a_trade_before_the_table_starts_is_not_priced_and_is_counted():
    got = plan(dhan(*widgetoil("2024-09-30"), *widgetoil("2024-10-01")), pl.ChargesInput())
    before, after = got.trips
    assert before.fees == 0                       # never at today's rate, and no brokerage
    assert after.fees == WIDGETOIL_CHARGES
    assert got.trip_fees_source == ("not_priced", "calculated")
    assert got.trips_not_priced == 1


def test_his_own_brokerage_replaces_the_published_plan():
    got = plan(DEMO, pl.ChargesInput(own_per_order=D(10)))
    # 55.595178 - brokerage 20 - GST on it 3.6
    assert got.trips[0].fees == D("31.995178")


def test_groww_counts_its_real_orders_and_an_order_split_across_trades_is_billed_once():
    # One buy order of 130 closed by two sell orders of 65: two trades sharing the buy order.
    text = groww(nifty_order("BUY", 130, "13000.00", 1, "10:00 AM"),
                 nifty_order("SELL", 65, "7150.00", 2, "10:30 AM"),
                 nifty_order("SELL", 65, "7280.00", 3, "11:00 AM"))
    got = plan(text, pl.ChargesInput())
    # NSE_OPT 13 Nov 2025 (rows 13-16, 45, 57, 68/69, 84/85). Brokerage per trade: half the
    # shared buy order (10) + its own sell order (20) = 30, GST on it 5.4 (Dhan's rule would be 40).
    # Buy 6,500: exchange 2.27695 + IPFT 0.0325 + SEBI 0.0065 + stamp 0.195
    #            + GST 0.416871 = 2.927821
    # Sell 7,150: STT 7.15 + exchange 2.504645 + IPFT 0.03575 + SEBI 0.00715
    #            + GST 0.4585581 = 10.1561031
    # Sell 7,280: STT 7.28 + exchange 2.550184 + IPFT 0.0364 + SEBI 0.00728
    #            + GST 0.46689552 = 10.34075952
    assert [t.fees for t in got.trips] == [D("48.4839241"), D("48.66858052")]


def test_the_import_records_the_table_day_the_plan_its_read_date_and_how_orders_were_counted():
    got = json.loads(plan(DEMO, pl.ChargesInput()).charges_provenance)
    assert got["rate_table_as_of"] and got["rate_table_starts"]
    assert got["brokerage"]["dhan"]["read_on"]
    assert got["orders_counted"]["dhan"] == "one per entry and one per exit"
    assert got["own_per_order"] is None


def test_his_day_total_replaces_ours_shared_by_our_figures_flagged_and_the_day_kept():
    ours = plan(DEMO, pl.ChargesInput())
    got = plan(DEMO, pl.ChargesInput(statement_days={"2026-09-01": D(100)}))
    on_day = [i for i, s in enumerate(got.trip_fees_source) if s == "statement"]
    assert on_day                                          # every trade that day is flagged
    assert sum(got.trips[i].fees for i in on_day) == D(100)
    ours_that_day = sum(ours.trips[i].fees for i in on_day)
    assert got.day_scales == (("2026-09-01", str(ours_that_day), "100"),)
    assert all(s == "calculated" for i, s in enumerate(got.trip_fees_source) if i not in on_day)


def test_a_day_before_the_table_his_own_file_covers_is_priced_from_his_file():
    got = plan(dhan(*widgetoil("2024-09-30")),
               pl.ChargesInput(statement_days={"2024-09-30": D(50)}))
    assert got.trips[0].fees == D(50)
    assert got.trip_fees_source == ("statement",)
    assert got.day_scales == (("2024-09-30", None, "50"),)


def test_the_same_file_and_inputs_give_the_same_digest_and_different_inputs_a_different_one():
    a = plan(DEMO, pl.ChargesInput())
    assert a.digest() == plan(DEMO, pl.ChargesInput()).digest()
    assert a.digest() != plan(DEMO).digest()
    assert a.digest() != plan(DEMO, pl.ChargesInput(own_per_order=D(10))).digest()
