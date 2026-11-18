"""TICKET-911: the shipped rate table covers every segment from its first day, is pinned row by
row, and picks the right rate either side of each real change.

The change dates are the circulars': SEBI's true-to-label rates from 1 Oct 2024, NSE's
charge/IPFT re-split from 1 Mar 2026 (NSE/FA/73061) and Finance Act 2026's STT from 1 Apr 2026.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from services.production.charges import rates as R

S, C = R.Segment, R.Component
STARTS, ROWS, RAW = R.load()
TODAY = date(2026, 11, 13)


def at(seg, comp, side, on):
    return R.rate(seg, comp, side, on).rate


def test_the_table_starts_on_the_day_rates_became_the_same_for_every_trader():
    assert STARTS == date(2024, 10, 1)
    with pytest.raises(R.NotCovered, match="starts on 2024-10-01"):
        R.rate(S.NSE_OPT, C.STT, "sell", date(2024, 9, 30))


@pytest.mark.parametrize("segment", list(S))
def test_every_segment_has_every_rate_it_needs_on_every_day_from_the_start(segment):
    day = STARTS
    while day <= TODAY:
        for component, side in R.REQUIRED[segment]:
            R.rate(segment, component, side, day)
        day += timedelta(days=7)
    for component, side in R.REQUIRED[segment]:
        R.rate(segment, component, side, TODAY)


def test_every_row_is_pinned_and_no_pinned_row_has_changed():
    pinned = R.read_lock()
    assert list(pinned) == [row["id"] for row in RAW], "rates.lock pins every row, in order (run scripts/lock_charge_rates.py)"
    changed = [row["id"] for row in RAW if pinned[row["id"]] != R.digest(row)]
    assert not changed, f"rows {changed} were edited. A row is never edited: put it back and add a new one"


def test_every_row_names_its_source():
    documents = ("http", "Act", "Notification", "Regulations")
    assert all(any(d in r.source for d in documents) for r in ROWS), "each row names its circular, Act or notice"


@pytest.mark.parametrize(("seg", "before", "after"), [
    (S.NSE_FUT, "0.0002", "0.0005"), (S.NSE_OPT, "0.001", "0.0015"),
    (S.BSE_FUT, "0.0002", "0.0005"), (S.BSE_OPT, "0.001", "0.0015"),
])
def test_stt_on_derivatives_rises_on_1_april_2026(seg, before, after):
    assert at(seg, C.STT, "sell", date(2026, 3, 31)) == Decimal(before)
    assert at(seg, C.STT, "sell", date(2026, 4, 1)) == Decimal(after)


def test_cash_stt_and_ctt_do_not_move_in_2026():
    for d in (date(2026, 3, 31), date(2026, 4, 1)):
        assert at(S.NSE_EQ_DELIVERY, C.STT, "buy", d) == Decimal("0.001")
        assert at(S.NSE_EQ_INTRADAY, C.STT, "sell", d) == Decimal("0.00025")
        assert at(S.MCX_OPT, C.CTT, "sell", d) == Decimal("0.0005")


@pytest.mark.parametrize(("seg", "charge_before", "charge_after", "total"), [
    (S.NSE_EQ_DELIVERY, "0.0000297", "0.000030699", "0.0000307"),
    (S.NSE_FUT, "0.0000173", "0.000018299", "0.0000183"),
    (S.NSE_OPT, "0.0003503", "0.000355299", "0.0003553"),
])
def test_nse_resplits_its_charge_and_ipft_on_1_march_2026_and_the_total_holds(seg, charge_before, charge_after, total):
    before, after = date(2026, 2, 28), date(2026, 3, 1)
    assert at(seg, C.EXCHANGE, "buy", before) == Decimal(charge_before)
    assert at(seg, C.EXCHANGE, "buy", after) == Decimal(charge_after)
    for d in (before, after):
        assert at(seg, C.EXCHANGE, "sell", d) + at(seg, C.IPFT, "sell", d) == Decimal(total)


def test_a_made_up_option_sale_is_priced_component_by_component():
    got = R.statutory(S.NSE_OPT, "sell", Decimal(10_000), TODAY)
    assert got[C.STT] == Decimal("15.0000")
    assert got[C.EXCHANGE] == Decimal("3.552990000")
    assert got[C.SEBI] == Decimal("0.010000")
    assert got[C.GST] == Decimal("0.18") * (got[C.EXCHANGE] + got[C.SEBI] + got[C.IPFT])
    assert C.STAMP not in got, "stamp duty is the buyer's"


def test_stamp_duty_is_on_the_buy_side_only():
    assert R.statutory(S.NSE_OPT, "buy", Decimal(10_000), TODAY)[C.STAMP] == Decimal("0.30000")
    with pytest.raises(R.NotCovered):
        R.rate(S.NSE_OPT, C.STAMP, "sell", TODAY)
