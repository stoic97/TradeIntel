"""TICKET-912: what one trade was charged, calculated from the dated rate table and the
broker's published plan, never read from his broker.

Every expected figure below is worked by hand from the rate rows it names
(services/production/charges/rates.yaml) and the brokerage page (brokerage.yaml), never
copied from the program. Made-up orders only: no trader's trade is read here.

Gate 1: each order's own date picks its rates, never today's.
Gate 2: brokerage is the broker's published plan, which the trader can change.
Rulings 14 Nov 2026 (founder): Q1 a trade before 1 Oct 2024 is not covered and says why;
Q2 one order per entry and one per exit; Q4 his day total is shared in proportion to ours,
equally where we have none. GST is on brokerage, exchange, IPFT and SEBI, never on STT,
CTT or stamp duty.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal as D
from zoneinfo import ZoneInfo

import pytest

from services.production.charges import brokerage as B
from services.production.charges import compute as C
from services.production.charges import rates as R

IST = ZoneInfo("Asia/Kolkata")


def at(day: str, hhmm: str) -> datetime:
    return datetime.fromisoformat(f"{day}T{hhmm}:00").replace(tzinfo=IST)


def nifty_long(day: str, *, exit_day: str | None = None, broker: str = "dhan", own=None):
    """75 NIFTY options bought at 100.00 and sold at 110.00: premium 7,500 in, 8,250 out."""
    return C.trip_charges(
        broker=broker,
        exchange="NSE",
        segment="OPT",
        direction="LONG",
        entry_ts=at(day, "10:00"),
        exit_ts=at(exit_day or day, "10:30"),
        quantity=75,
        entry_price=D("100.00"),
        exit_price=D("110.00"),
        own=own,
    )


# --- gate 1: the order's own date picks the row ------------------------------------------


def test_a_nifty_option_round_trip_is_charged_at_its_own_dates_rates():
    # 10 Jun 2025, rows 13/14/15/16 (exchange 0.0003503, IPFT 0.000005), 45 (STT sell 0.001),
    # 57 (stamp buy 0.00003), 68/69 (SEBI 0.000001), 84/85 (GST 0.18), Dhan Rs 20 per order.
    # Buy 7,500: exchange 2.62725 + IPFT 0.0375 + SEBI 0.0075 + stamp 0.225
    #            + GST 0.18 x 2.67225 = 0.481005 + brokerage 20 + GST on it 3.6 = 26.978255
    # Sell 8,250: STT 8.25 + exchange 2.889975 + IPFT 0.04125 + SEBI 0.00825
    #            + GST 0.18 x 2.939475 = 0.5291055 + 20 + 3.6 = 35.3185805
    got = nifty_long("2025-06-10")
    assert got.covered
    assert got.total == D("62.2968355")


def test_either_side_of_the_1_april_2026_stt_change_the_trade_gets_its_own_days_rate():
    # 31 Mar 2026: STT row 45 (0.001); exchange/IPFT re-split on 1 Mar 2026 (rows 29-32,
    # 0.000355299 + 0.000000001 = the same 0.0003553 as before), so the total is unchanged.
    assert nifty_long("2026-03-31").total == D("62.2968355")
    # 1 Apr 2026: STT row 49 (0.0015) on the 8,250 sell = 12.375, up 4.125 from 8.25.
    assert nifty_long("2026-04-01").total == D("66.4218355")


def test_a_short_crude_option_is_charged_on_the_sell_that_opened_it():
    # 1 Sep 2026, MCX_OPT: exchange 0.000418 (36/40), CTT sell 0.0005 (53), stamp buy 0.00003
    # (61), SEBI 0.000001 (76/77), no IPFT. 100 sold at 50.00, bought back at 40.00.
    # Sell 5,000: CTT 2.5 + exchange 2.09 + SEBI 0.005 + GST 0.18 x 2.095 = 0.3771 + 23.6
    # Buy 4,000: exchange 1.672 + SEBI 0.004 + stamp 0.12 + GST 0.18 x 1.676 = 0.30168 + 23.6
    got = C.trip_charges(
        broker="dhan",
        exchange="MCX",
        segment="OPT",
        direction="SHORT",
        entry_ts=at("2026-09-01", "10:00"),
        exit_ts=at("2026-09-01", "11:00"),
        quantity=100,
        entry_price=D("50.00"),
        exit_price=D("40.00"),
    )
    assert got.total == D("54.26978")
    assert got.by_component["CTT"] == D("2.5")  # on the sell that opened it
    assert got.by_component["STAMP"] == D("0.12")  # on the buy that closed it


def test_gst_is_on_brokerage_exchange_ipft_and_sebi_never_on_stt_or_stamp():
    got = nifty_long("2025-06-10").by_component
    base = got["EXCHANGE"] + got["IPFT"] + got["SEBI"] + got["BROKERAGE"]
    assert got["GST"] == D("0.18") * base
    assert got["BROKERAGE"] == D(40)  # one order in, one order out


# --- Q1: before the table starts, the trade is not covered and says why ------------------


def test_a_trade_before_1_october_2024_is_not_covered_and_never_priced_at_todays_rate():
    got = nifty_long("2024-09-30")
    assert not got.covered
    assert got.total == 0
    assert "2024-10-01" in got.reason


def test_a_trade_opened_before_the_table_and_closed_after_it_is_not_covered():
    got = nifty_long("2024-09-30", exit_day="2024-10-01")
    assert not got.covered


def test_a_segment_the_table_has_no_rows_for_is_not_covered():
    got = C.trip_charges(
        broker="dhan",
        exchange="BSE",
        segment="EQ",
        direction="LONG",
        entry_ts=at("2025-06-10", "10:00"),
        exit_ts=at("2025-06-10", "11:00"),
        quantity=10,
        entry_price=D(100),
        exit_price=D(101),
    )
    assert not got.covered


def test_a_broker_with_no_preset_is_not_covered():
    assert not nifty_long("2025-06-10", broker="someone-else").covered


# --- equity: intraday or delivery from the trade, not the order type -------------------


@pytest.mark.parametrize(
    ("exchange", "segment", "same_day", "want"),
    [
        ("NSE", "EQ", True, R.Segment.NSE_EQ_INTRADAY),
        ("NSE", "EQ", False, R.Segment.NSE_EQ_DELIVERY),
        ("NSE", "OPT", True, R.Segment.NSE_OPT),
        ("MCX", "FUT", False, R.Segment.MCX_FUT),
        ("BSE", "OPT", True, R.Segment.BSE_OPT),
        ("BSE", "EQ", True, None),
    ],
)
def test_the_rate_segment_comes_from_exchange_segment_and_whether_it_closed_that_day(
    exchange, segment, same_day, want
):
    assert C.rate_segment(exchange, segment, same_day=same_day) == want


# --- gate 2: brokerage is the broker's published plan, which he can change --------------


@pytest.mark.parametrize(
    ("broker", "kind", "value", "want"),
    [
        ("dhan", "OPT", D(7500), D(20)),  # flat Rs 20 per executed order
        ("dhan", "FUT", D(50000), D(15)),  # Rs 20 or 0.03%, whichever lower: 15
        ("dhan", "FUT", D(1000000), D(20)),  # 0.03% is 300, so Rs 20
        ("dhan", "EQ_DELIVERY", D(100000), D(0)),  # zero brokerage on delivery
        ("groww", "OPT", D(7500), D(20)),
        ("groww", "EQ_INTRADAY", D(1000), D(5)),  # 0.1% is 1, under Rs 5: the lower of 5 or 25
        ("groww", "EQ_INTRADAY", D(100), D("2.5")),  # 0.1% is 0.1: the lower of 5 or 2.5
    ],
)
def test_brokerage_per_order_is_the_brokers_published_plan(broker, kind, value, want):
    assert B.per_order(broker, kind, value) == want


def test_every_preset_names_its_page_and_the_day_it_was_read():
    assert set(B.presets()) >= {"dhan", "groww"}  # both adapters' brokers (Fill.broker)
    for p in B.presets().values():
        assert p.source and p.read_on
        assert all(isinstance(plan.flat, D) for plan in p.plans.values())


def test_a_yaml_number_in_a_preset_is_refused(tmp_path):
    bad = tmp_path / "b.yaml"
    bad.write_text(
        'brokers:\n  x:\n    name: X\n    read_on: "2026-11-14"\n    source: "p"\n'
        "    plans:\n      OPT: {flat: 20}\n",
        encoding="utf-8",
    )
    with pytest.raises(B.InvalidPresets):
        B.load(bad)


def test_his_own_figure_replaces_the_flat_rupees_per_order():
    # Case of the first test with Rs 10 per order: brokerage 20 instead of 40, GST on it 3.6
    # instead of 7.2, so 62.2968355 - 20 - 3.6 = 38.6968355.
    assert nifty_long("2025-06-10", own=D(10)).total == D("38.6968355")
    assert B.per_order("dhan", "FUT", D(50000), own=D(10)) == D(10)
    assert B.per_order("dhan", "EQ_DELIVERY", D(100000), own=D(10)) == D(0)


# --- Q4: his day total, shared across the day's trades -----------------------------------


def test_his_day_total_is_shared_in_proportion_to_ours_and_sums_to_his_figure():
    shares = C.share_day(D(100), [D(30), D(10)])
    assert shares == [D(75), D(25)]
    assert sum(shares) == D(100)


def test_a_day_we_have_no_figure_for_is_shared_equally_and_still_sums_exactly():
    shares = C.share_day(D(100), [None, None, None])
    assert sum(shares) == D(100)
    assert shares[0] == shares[1]


def test_no_float_decides_a_figure():
    got = nifty_long("2025-06-10")
    assert isinstance(got.total, D)
    assert all(isinstance(v, D) for v in got.by_component.values())
