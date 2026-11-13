"""Which way the underlying had to move for a trip to make money [TICKET-890].

Bought call -> long. Bought put -> short. A sold option inverts the bought answer.
A future or share takes its own side. A multi-leg position is none: positions._links
joins only a bought leg to a sold one, so every position the product can build holds
both directions. The rule is written once in the research spec (TICKET-888) and once
in services/shared/option_direction.py; these tests pin what both say.

Direction is read from the legs, never from the result: a winner and a loser of the
same shape give the same answer, and the module never reads a money or price field.
"""

from __future__ import annotations

import ast
import inspect
from datetime import timedelta
from decimal import Decimal

import pytest

from services.shared import option_direction as od
from services.shared.schemas import ctr_v2
from services.shared.schemas.ctr_v1 import Direction, Segment
from tests.unit.test_positions import CE, LONG, PE, SHORT, T0, leg, one

U = od.Underlying


def own_side(direction, segment):
    """A future or share, bought or sold."""
    return ctr_v2.RoundTrip(
        trader_id="T01", broker="dhan", exchange="MCX" if segment is Segment.FUT else "NSE",
        segment=segment, symbol="CRUDEOIL" if segment is Segment.FUT else "RELIANCE",
        expiry=leg(LONG, 23000, 10).expiry if segment is Segment.FUT else None,
        direction=direction, entry_ts=T0, exit_ts=T0 + timedelta(hours=1), quantity=1,
        entry_price=Decimal(100), exit_price=Decimal(101),
        gross_pnl=Decimal(1) if direction is LONG else Decimal(-1), fees=Decimal(0),
        fill_ids=[f"{segment.value}{direction.value}"],
    )


# ------------------------------------------------------------ the table (gate 2)

SINGLE_LEG = [
    pytest.param(LONG, CE, U.LONG, id="bought call -> long"),
    pytest.param(LONG, PE, U.SHORT, id="bought put -> short"),
    pytest.param(SHORT, CE, U.SHORT, id="sold call -> short"),
    pytest.param(SHORT, PE, U.LONG, id="sold put -> long"),
]


@pytest.mark.parametrize(("side", "kind", "expected"), SINGLE_LEG)
def test_each_single_option_leg(side, kind, expected):
    assert od.underlying_direction(leg(side, 23000, 30, kind=kind)) is expected


@pytest.mark.parametrize(("side", "kind", "expected"), SINGLE_LEG)
def test_a_one_leg_position_answers_as_its_trip(side, kind, expected):
    assert od.underlying_direction(one([leg(side, 23000, 30, kind=kind)])) is expected


@pytest.mark.parametrize("segment", [Segment.FUT, Segment.EQ], ids=["future", "share"])
@pytest.mark.parametrize(("side", "expected"), [(LONG, U.LONG), (SHORT, U.SHORT)],
                         ids=["bought -> long", "sold -> short"])
def test_a_non_option_trip_takes_its_own_side(segment, side, expected):
    assert od.underlying_direction(own_side(side, segment)) is expected


# ------------------------------------------------------------ the inversion (gate 3)

@pytest.mark.parametrize("kind", [CE, PE], ids=["call", "put"])
def test_selling_inverts_buying_and_does_not_copy_it(kind):
    """Pins both the flip and the anchor, so neither "sold = bought" nor "always flip" passes."""
    bought = od.underlying_direction(leg(LONG, 23000, 30, kind=kind))
    sold = od.underlying_direction(leg(SHORT, 23000, 30, kind=kind))
    assert {bought, sold} == {U.LONG, U.SHORT}
    assert bought is (U.LONG if kind is CE else U.SHORT)


def test_a_bought_put_is_not_a_bought_call():
    """The bug the ticket exists for: the put case backwards flips every figure silently."""
    call = od.underlying_direction(leg(LONG, 23000, 30, kind=CE))
    put = od.underlying_direction(leg(LONG, 23000, 30, kind=PE))
    assert (call, put) == (U.LONG, U.SHORT)


def test_the_answer_is_not_the_contract_side():
    """Underlying.LONG is a different thing from Direction.LONG (= bought)."""
    assert all(u.value != d.value for u in U for d in Direction)
    assert {u.value for u in U} == {"long", "short", "none"}


# ------------------------------------------------------------ multi-leg (gate 2, ruling Q2 c)

def test_every_multi_leg_position_is_none_because_links_join_only_bought_to_sold():
    """The debit vertical of test_positions.py: bought 23000 CE at 30, sold 23100 CE at 10."""
    vertical = one([leg(LONG, 23000, 30), leg(SHORT, 23100, 10, seconds=2)])
    assert {t.direction for t in vertical.legs} == {LONG, SHORT}
    assert od.underlying_direction(vertical) is U.NONE


# ------------------------------------------------------------ never the result (gate 4)

@pytest.mark.parametrize(("side", "kind", "expected"), SINGLE_LEG)
def test_a_winner_and_a_loser_of_one_shape_agree(side, kind, expected):
    winner = leg(side, 23000, 30, 40 if side is LONG else 20, kind=kind)
    loser = leg(side, 23000, 30, 20 if side is LONG else 40, kind=kind)
    assert winner.gross_pnl > 0 > loser.gross_pnl
    assert od.underlying_direction(winner) is od.underlying_direction(loser) is expected


FORBIDDEN = {"gross_pnl", "net_pnl", "gross", "net", "fees", "r_multiple", "risk_unit",
             "entry_price", "exit_price", "is_win", "is_loss", "is_scratch"}


def test_the_module_never_reads_a_result_or_a_price():
    tree = ast.parse(inspect.getsource(od))
    read = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not read & FORBIDDEN, sorted(read & FORBIDDEN)


# ------------------------------------------------------------ beside uncapped (gate 5)

@pytest.mark.parametrize("kind", [CE, PE], ids=["sold call", "sold put"])
def test_uncapped_is_about_selling_and_direction_is_about_the_underlying(kind):
    """Both sold legs are uncapped; they bet opposite ways. One field, two questions."""
    sold = leg(SHORT, 23000, 30, kind=kind)
    assert sold.risk_unit_source is ctr_v2.RiskUnitSource.UNCAPPED
    assert od.underlying_direction(sold) is (U.SHORT if kind is CE else U.LONG)