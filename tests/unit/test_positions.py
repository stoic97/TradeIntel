"""ctr_v2 and positions, Annex H draft 2 [TICKET-810].

A sold option is a leg, not a refusal. Legs link into a position only as one LONG and one
SHORT on the same underlying and expiry, different contract, entered within the window.
P&L is the sum of legs; R is the most the position can lose at expiry, or UNCAPPED.
Synthetic throughout, every expected value worked by hand from Annex H section 5.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from services.production.ctr.reconstruct import reconstruct
from services.shared import positions as pos
from services.shared.schemas import ctr_v1, ctr_v2
from services.shared.schemas.ctr_v1 import Direction, Fill, OptionType, Segment, Side

T0 = datetime.fromisoformat("2026-03-27T10:00:00+05:30")
EXPIRY = date(2026, 3, 30)
LONG, SHORT = Direction.LONG, Direction.SHORT
CE, PE = OptionType.CE, OptionType.PE


def leg(direction, strike, entry, exit_=None, qty=65, kind=CE, seconds=0, held=3600,
        symbol="NIFTY", expiry=EXPIRY, cls=ctr_v2.RoundTrip):
    """One leg, entered at ``entry`` a unit and closed at ``exit_`` (the entry if not given)."""
    exit_ = entry if exit_ is None else exit_
    gross = (exit_ - entry) * qty if direction is LONG else (entry - exit_) * qty
    return cls(
        trader_id="T01", broker="dhan", exchange="NSE", segment=Segment.OPT, symbol=symbol,
        expiry=expiry, option_type=kind, strike=Decimal(strike), direction=direction,
        entry_ts=T0 + timedelta(seconds=seconds), exit_ts=T0 + timedelta(seconds=seconds + held),
        quantity=qty, entry_price=Decimal(entry), exit_price=Decimal(exit_),
        gross_pnl=Decimal(gross), fees=Decimal(0), fill_ids=[f"{direction.value}{strike}{seconds}"],
    )


def one(legs, **kw):
    positions = pos.group_positions(legs, **kw)
    assert len(positions) == 1
    return positions[0]


# ---------------------------------------------------------------- ctr_v2


def test_a_sold_option_is_a_leg_in_ctr_v2():
    t = leg(SHORT, 23000, 30, 10)
    assert t.gross_pnl == Decimal(1300)
    assert t.risk_unit is None
    assert t.risk_unit_source is ctr_v2.RiskUnitSource.UNCAPPED
    assert t.r_multiple is None


def test_ctr_v1_still_refuses_a_sold_option():
    with pytest.raises(ctr_v1.UnsupportedInV1):
        leg(SHORT, 23000, 30, 10, cls=ctr_v1.RoundTrip)


def test_a_bought_option_keeps_its_premium_as_the_risk_unit():
    t = leg(LONG, 23000, 30, 40)
    assert t.risk_unit == Decimal(1950)
    assert t.risk_unit_source is ctr_v2.RiskUnitSource.PREMIUM_PAID


def test_the_schema_is_v2_and_the_ids_are_still_v1():
    """The minute: every ctr_v1 trip id is unchanged. The hash includes the version string."""
    assert ctr_v2.SCHEMA_VERSION == "ctr_v2"
    v1 = leg(LONG, 23000, 30, 40, cls=ctr_v1.RoundTrip)
    v2 = leg(LONG, 23000, 30, 40)
    assert v2.trip_id == v1.trip_id


def test_an_exit_before_the_entry_is_still_refused():
    with pytest.raises(ValueError):
        leg(LONG, 23000, 30, 40, held=-5)


# ---------------------------------------------------------------- reconstruction


def fill(side, qty, price, seconds=0, strike=23000, kind=CE):
    return Fill(trader_id="T01", broker="dhan", ts=T0 + timedelta(seconds=seconds), side=side,
                quantity=qty, price=Decimal(price), raw_hash="c" * 64, exchange="NSE",
                segment=Segment.OPT, symbol="NIFTY", expiry=EXPIRY, option_type=kind,
                strike=Decimal(strike))


SOLD = [fill(Side.SELL, 65, 30, 0), fill(Side.BUY, 65, 10, 3600)]


def test_reconstruction_refuses_sold_options_by_default():
    r = reconstruct(SOLD)
    assert r.round_trips == [] and len(r.skipped) == 1


def test_reconstruction_builds_the_leg_when_asked():
    r = reconstruct(SOLD, short_options=True)
    assert r.skipped == []
    assert [(t.direction, t.gross_pnl) for t in r.round_trips] == [(SHORT, Decimal(1300))]


def test_asking_for_sold_options_leaves_other_trips_identical():
    bought = [fill(Side.BUY, 65, 30, 0, strike=23100), fill(Side.SELL, 65, 40, 60, strike=23100)]
    assert [t.trip_id for t in reconstruct(bought, short_options=True).round_trips] == [
        t.trip_id for t in reconstruct(bought).round_trips
    ]


# ---------------------------------------------------------------- linking


def test_one_bought_and_one_sold_leg_link():
    assert len(one([leg(LONG, 23100, 10), leg(SHORT, 23000, 30, seconds=2)]).legs) == 2


@pytest.mark.parametrize("window", [60, 180, 600])
def test_two_bought_legs_never_link(window):
    legs = [leg(LONG, 6300, 10), leg(LONG, 6300, 12, kind=PE, seconds=5)]
    assert len(pos.group_positions(legs, window_seconds=window)) == 2


def test_two_sold_legs_never_link():
    legs = [leg(SHORT, 6300, 10), leg(SHORT, 6300, 12, kind=PE, seconds=5)]
    assert len(pos.group_positions(legs)) == 2


def test_the_window_is_180_seconds_and_says_so():
    assert pos.LINK_WINDOW_SECONDS == 180


def test_exactly_on_the_window_links():
    assert len(one([leg(LONG, 23100, 10), leg(SHORT, 23000, 30, seconds=180)]).legs) == 2


def test_a_second_past_the_window_does_not():
    legs = [leg(LONG, 23100, 10), leg(SHORT, 23000, 30, seconds=181)]
    assert len(pos.group_positions(legs)) == 2


def test_a_leg_in_of_74_seconds_is_one_position_at_180_and_two_at_60():
    legs = [leg(LONG, 23100, 10), leg(SHORT, 23000, 30, seconds=74)]
    assert len(pos.group_positions(legs)) == 1
    assert len(pos.group_positions(legs, window_seconds=60)) == 2


def test_different_expiries_never_link():
    legs = [leg(LONG, 23100, 10), leg(SHORT, 23000, 30, expiry=date(2026, 4, 28))]
    assert len(pos.group_positions(legs)) == 2


def test_different_underlyings_never_link():
    legs = [leg(LONG, 23100, 10), leg(SHORT, 23000, 30, symbol="BANKNIFTY")]
    assert len(pos.group_positions(legs)) == 2


def test_the_same_contract_never_links_to_itself():
    legs = [leg(LONG, 23000, 10), leg(SHORT, 23000, 30, seconds=5)]
    assert len(pos.group_positions(legs)) == 2


def test_a_share_or_future_is_a_position_of_its_own():
    share = ctr_v2.RoundTrip(
        trader_id="T01", broker="dhan", exchange="NSE", segment=Segment.EQ, symbol="NIFTY",
        direction=LONG, entry_ts=T0, exit_ts=T0 + timedelta(hours=1), quantity=1,
        entry_price=Decimal(10), exit_price=Decimal(11), gross_pnl=Decimal(1), fees=Decimal(0),
        fill_ids=["x"],
    )
    positions = pos.group_positions([share, leg(SHORT, 23000, 30)])
    assert len(positions) == 2


# ---------------------------------------------------------------- what a position is


def test_gross_is_the_sum_of_the_legs():
    """Long loses 20 x 65, short makes 25 x 65: -1300 + 1625."""
    p = one([leg(LONG, 23100, 30, 10), leg(SHORT, 23000, 50, 25, seconds=2)])
    assert p.gross == Decimal(325) and p.net == Decimal(325)


def test_entry_is_the_first_leg_in_and_exit_the_last_out():
    legs = [leg(LONG, 23100, 10, held=600), leg(SHORT, 23000, 30, seconds=2, held=60)]
    p = one(legs)
    assert p.entry_ts == T0
    assert p.exit_ts == T0 + timedelta(seconds=600)


def test_legs_closing_at_different_times_are_still_one_position():
    legs = [leg(LONG, 23100, 10, held=60), leg(SHORT, 23000, 30, seconds=1, held=600)]
    assert len(one(legs).legs) == 2


def test_the_position_id_ignores_input_order():
    a, b = leg(LONG, 23100, 10), leg(SHORT, 23000, 30, seconds=2)
    assert one([a, b]).position_id == one([b, a]).position_id


def test_a_single_leg_position_has_the_trips_id():
    t = leg(LONG, 23100, 10)
    assert one([t]).position_id == t.trip_id


# ---------------------------------------------------------------- the risk unit


def test_a_single_bought_option_is_its_premium():
    p = one([leg(LONG, 23000, 30, 40)])
    assert p.risk_unit == Decimal(1950)
    assert p.risk_unit_source is ctr_v2.RiskUnitSource.PREMIUM_PAID


def test_a_credit_vertical_is_width_times_units_less_the_credit():
    """Sold 23000 at 30, bought 23100 at 10. Credit 20 x 65 = 1300. 100 x 65 - 1300 = 5200."""
    p = one([leg(LONG, 23100, 10), leg(SHORT, 23000, 30, seconds=2)])
    assert p.risk_unit == Decimal(5200)
    assert p.risk_unit_source is ctr_v2.RiskUnitSource.STRUCTURE_MAX_LOSS


def test_a_debit_vertical_is_the_net_debit():
    """Bought 23000 at 30, sold 23100 at 10. Debit 20 x 65 = 1300."""
    p = one([leg(LONG, 23000, 30), leg(SHORT, 23100, 10, seconds=2)])
    assert p.risk_unit == Decimal(1300)


def test_a_put_credit_vertical_works_the_same():
    """Sold 23000 PE at 30, bought 22900 PE at 10. 100 x 65 - 1300 = 5200."""
    p = one([leg(LONG, 22900, 10, kind=PE), leg(SHORT, 23000, 30, kind=PE, seconds=2)])
    assert p.risk_unit == Decimal(5200)


def test_a_butterfly_is_the_lowest_point_at_a_strike():
    """Bought 23000 at 50 and 23200 at 20, sold two 23100 at 30. Debit 10 a unit."""
    p = one([
        leg(LONG, 23000, 50, qty=1),
        leg(SHORT, 23100, 30, qty=2, seconds=1),
        leg(LONG, 23200, 20, qty=1, seconds=2),
    ])
    assert p.risk_unit == Decimal(10)


def test_a_leg_split_by_a_partial_close_classifies_the_same():
    """The 65 sold is two parcels. Same contract, so they add before the covered test."""
    p = one([
        leg(LONG, 23100, 10),
        leg(SHORT, 23000, 30, qty=30, seconds=1),
        leg(SHORT, 23000, 30, qty=35, seconds=1, held=7200),
    ])
    assert p.risk_unit == Decimal(5200)


@pytest.mark.parametrize(
    "legs",
    [
        pytest.param([leg(SHORT, 23000, 30, 40)], id="naked short"),
        pytest.param(
            [leg(SHORT, 5800, 30, 40), leg(LONG, 5800, 20, 25, kind=PE, seconds=2)],
            id="sold call and bought put",
        ),
        pytest.param(
            [leg(LONG, 23100, 10, qty=65), leg(SHORT, 23000, 30, 40, qty=130, seconds=1)],
            id="ratio spread",
        ),
    ],
)
def test_net_short_in_a_type_is_uncapped_and_its_money_still_counts(legs):
    p = one(legs)
    assert p.risk_unit is None
    assert p.risk_unit_source is ctr_v2.RiskUnitSource.UNCAPPED
    assert p.gross == sum(t.gross_pnl for t in legs)
    assert p.gross != 0


def test_a_position_that_could_not_lose_is_flagged_and_keeps_its_money():
    """Credit 490 on a width of 100 is riskless, which real fills do not produce."""
    p = one([leg(LONG, 23100, 10, 20, qty=1), leg(SHORT, 23000, 500, 490, qty=1, seconds=1)])
    assert p.inconsistent is True
    assert p.risk_unit is None
    assert p.gross == Decimal(20)


def test_an_ordinary_position_is_not_flagged():
    assert one([leg(LONG, 23100, 10), leg(SHORT, 23000, 30, seconds=2)]).inconsistent is False


# ---------------------------------------------------------------- the framework


def test_the_framework_accepts_what_the_minute_accepted():
    path = Path("services/research/prereg/framework_v1.yaml")
    scope = yaml.safe_load(path.read_text(encoding="utf-8"))["scope"]
    assert {"short_options", "multi_leg_spreads"} <= set(scope["accepted_trade_types"])
    assert not {"short_options", "multi_leg_spreads"} & set(scope.get("not_yet_accepted") or [])
