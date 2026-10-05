"""Cycle 2b - fills to round trips, FIFO.

The invariant that matters is quantity conservation, not row counting, because a
single fill can be split across several trips:

    2*sum(trip.quantity) + sum(open.quantity) + 2*sum(skipped.quantity)
        == sum(fill.quantity)

Every unit that arrived is matched into a trip (consuming one unit on each side),
still open, or inside a trip we refused. Research Spec s4.2: unresolved positions
are flagged, never forced.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from services.production.ctr.reconstruct import reconstruct
from services.shared.schemas.ctr_v1 import (
    Direction,
    Fill,
    OptionType,
    RiskUnitSource,
    Segment,
    Side,
)

IST = datetime(2026, 9, 1, 9, 15, 0).astimezone().tzinfo
T0 = datetime(2026, 9, 1, 9, 15, 0, tzinfo=IST)
RAW = "c" * 64

CRUDE = {
    "exchange": "MCX",
    "segment": Segment.OPT,
    "symbol": "CRUDEOILM",
    "expiry": date(2026, 9, 17),
    "option_type": OptionType.CE,
    "strike": Decimal(5500),
}
NIFTY = {**CRUDE, "exchange": "NSE", "symbol": "NIFTY", "expiry": date(2026, 9, 22)}
EQ = {"exchange": "NSE", "segment": Segment.EQ, "symbol": "RELIANCE"}


def fill(side, qty, price, minutes=0, **contract):
    return Fill(
        trader_id="T01",
        broker="dhan",
        ts=T0 + timedelta(minutes=minutes),
        side=side,
        quantity=qty,
        price=Decimal(str(price)),
        raw_hash=RAW,
        **(contract or CRUDE),
    )


def signed_value(f):
    v = f.price * f.quantity
    return v if f.side is Side.SELL else -v


# ---------------------------------------------------------------- the basics

def test_empty_input_gives_an_empty_result():
    r = reconstruct([])
    assert r.round_trips == []
    assert r.open_positions == []
    assert r.skipped == []


def test_a_buy_then_a_sell_is_one_long_round_trip():
    r = reconstruct([fill(Side.BUY, 10, 100, 0), fill(Side.SELL, 10, 110, 5)])
    assert len(r.round_trips) == 1
    t = r.round_trips[0]
    assert t.direction is Direction.LONG
    assert t.quantity == 10
    assert t.entry_ts == T0
    assert t.exit_ts == T0 + timedelta(minutes=5)
    assert not r.open_positions


def test_gross_pnl_is_exact():
    r = reconstruct([fill(Side.BUY, 10, 100, 0), fill(Side.SELL, 10, 110, 5)])
    assert r.round_trips[0].gross_pnl == Decimal(100)


def test_fees_are_zero_and_the_result_says_they_are_unavailable():
    """The adapter reported no charges column; the trip must not invent fees."""
    r = reconstruct([fill(Side.BUY, 10, 100, 0), fill(Side.SELL, 10, 110, 5)])
    assert r.round_trips[0].fees == Decimal(0)
    assert r.fees_available is False


def test_the_trip_cites_every_fill_that_built_it():
    fills = [fill(Side.BUY, 10, 100, 0), fill(Side.SELL, 10, 110, 5)]
    r = reconstruct(fills)
    assert set(r.round_trips[0].fill_ids) == {f.fill_id for f in fills}


# ---------------------------------------------------------------- FIFO

def test_several_buys_then_one_sell_uses_a_weighted_average_entry():
    r = reconstruct(
        [
            fill(Side.BUY, 10, 100, 0),
            fill(Side.BUY, 30, 120, 1),
            fill(Side.SELL, 40, 130, 5),
        ]
    )
    t = r.round_trips[0]
    assert t.quantity == 40
    assert t.entry_price == Decimal(4600) / Decimal(40)  # (10*100 + 30*120) / 40
    assert t.gross_pnl == Decimal(5200) - Decimal(4600)


def test_the_first_lot_is_closed_first():
    """FIFO: selling 10 against buys of 10@100 then 10@200 closes the 100 lot."""
    r = reconstruct(
        [
            fill(Side.BUY, 10, 100, 0),
            fill(Side.BUY, 10, 200, 1),
            fill(Side.SELL, 10, 150, 5),
        ]
    )
    assert len(r.round_trips) == 1
    assert r.round_trips[0].entry_price == Decimal(100)
    assert r.round_trips[0].gross_pnl == Decimal(500)
    assert r.open_positions[0].quantity == 10


def test_a_partial_close_leaves_the_rest_open():
    r = reconstruct([fill(Side.BUY, 10, 100, 0), fill(Side.SELL, 4, 110, 5)])
    assert r.round_trips[0].quantity == 4
    assert r.open_positions[0].quantity == 6
    assert r.open_positions[0].direction is Direction.LONG


def test_a_flip_closes_the_long_and_opens_a_short():
    r = reconstruct([fill(Side.BUY, 10, 100, 0), fill(Side.SELL, 15, 110, 5)])
    assert r.round_trips[0].quantity == 10
    assert r.round_trips[0].direction is Direction.LONG
    assert r.open_positions[0].direction is Direction.SHORT
    assert r.open_positions[0].quantity == 5


# ---------------------------------------------------------------- scope and R

def test_a_long_option_trip_carries_the_exact_premium_as_its_risk_unit():
    r = reconstruct([fill(Side.BUY, 30, "153.18", 0), fill(Side.SELL, 30, 160, 5)])
    t = r.round_trips[0]
    assert t.risk_unit_source is RiskUnitSource.PREMIUM_PAID
    assert t.risk_unit == Decimal("153.18") * 30
    assert t.r_multiple == t.net_pnl / t.risk_unit


def test_a_short_option_trip_is_skipped_with_its_reason():
    """15 of 494 real contracts open with a SELL. Refused, counted, never guessed."""
    r = reconstruct([fill(Side.SELL, 10, 110, 0), fill(Side.BUY, 10, 100, 5)])
    assert not r.round_trips
    assert len(r.skipped) == 1
    assert r.skipped[0].quantity == 10
    assert "short option" in r.skipped[0].reason


def test_an_equity_trip_has_no_r():
    r = reconstruct(
        [fill(Side.BUY, 10, 100, 0, **EQ), fill(Side.SELL, 10, 110, 5, **EQ)]
    )
    t = r.round_trips[0]
    assert t.risk_unit is None
    assert t.r_multiple is None


# ---------------------------------------------------------------- separation

def test_different_contracts_do_not_interact():
    r = reconstruct(
        [
            fill(Side.BUY, 10, 100, 0),
            fill(Side.BUY, 10, 200, 1, **NIFTY),
            fill(Side.SELL, 10, 110, 5),
            fill(Side.SELL, 10, 210, 6, **NIFTY),
        ]
    )
    assert len(r.round_trips) == 2
    assert {t.symbol for t in r.round_trips} == {"CRUDEOILM", "NIFTY"}


def test_the_same_symbol_with_a_different_expiry_is_a_different_contract():
    other = {**CRUDE, "expiry": date(2026, 10, 17)}
    r = reconstruct(
        [
            fill(Side.BUY, 10, 100, 0),
            fill(Side.SELL, 10, 110, 5, **other),
        ]
    )
    assert not r.round_trips
    assert len(r.open_positions) == 2


def test_round_trips_are_sorted_by_exit_time():
    r = reconstruct(
        [
            fill(Side.BUY, 10, 200, 0, **NIFTY),
            fill(Side.SELL, 10, 210, 20, **NIFTY),
            fill(Side.BUY, 10, 100, 1),
            fill(Side.SELL, 10, 110, 5),
        ]
    )
    assert [t.symbol for t in r.round_trips] == ["CRUDEOILM", "NIFTY"]


# ---------------------------------------------------------------- properties

sides = st.sampled_from([Side.BUY, Side.SELL])
qtys = st.integers(min_value=1, max_value=50)
prices = st.decimals(min_value=Decimal("0.05"), max_value=Decimal(500), places=2)
sequences = st.lists(st.tuples(sides, qtys, prices), min_size=0, max_size=14)


def build(seq):
    return [fill(s, q, p, i) for i, (s, q, p) in enumerate(seq)]


@given(sequences)
@settings(max_examples=400, deadline=None)
def test_quantity_is_conserved(seq):
    """Nothing is invented and nothing is lost."""
    fills = build(seq)
    r = reconstruct(fills)
    matched = 2 * sum(t.quantity for t in r.round_trips)
    refused = 2 * sum(s.quantity for s in r.skipped)
    still_open = sum(o.quantity for o in r.open_positions)
    assert matched + refused + still_open == sum(f.quantity for f in fills)


@given(sequences)
@settings(max_examples=400, deadline=None)
def test_gross_equals_the_matched_fill_values(seq):
    """The headline property: a reconstruction bug would break this silently."""
    fills = build(seq)
    r = reconstruct(fills)
    if r.skipped or r.open_positions:
        return  # only fully-closed histories have a clean total
    total_gross = sum((t.gross_pnl for t in r.round_trips), Decimal(0))
    total_value = sum((signed_value(f) for f in fills), Decimal(0))
    assert abs(total_gross - total_value) <= Decimal("0.01")


@given(sequences)
@settings(max_examples=200, deadline=None)
def test_no_trip_exits_before_it_enters(seq):
    for t in reconstruct(build(seq)).round_trips:
        assert t.exit_ts >= t.entry_ts


@given(sequences)
@settings(max_examples=200, deadline=None)
def test_reconstruction_is_deterministic(seq):
    fills = build(seq)
    a = [t.trip_id for t in reconstruct(fills).round_trips]
    b = [t.trip_id for t in reconstruct(fills).round_trips]
    assert a == b
