"""Direction of a multi-leg position: the convention of spec 4.7.8 [TICKET-902].

Ruled on TICKET-902, 12 and 13 Nov 2026. Two strikes, same expiry, same option type, one leg
bought and one sold. The larger-delta leg is the lower strike for calls and the higher strike
for puts. When it carries at least as many units as the other leg, net delta cannot change sign
at any level, so the position takes that leg's 4.7.7 direction; equal units (a vertical) counts
as fixed. Otherwise the sign flips with the underlying's level and the answer is none. A
butterfly, a call against a put, and any other shape are none, stated.

The shape is read after netting each (option type, strike), because a partial close splits one
leg into several trips. Nothing here reads a price, a level or a result.
"""

from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from services.shared import option_direction as od
from services.shared.schemas.ctr_v1 import Segment
from tests.unit.test_positions import LONG, PE, SHORT, leg, one

U = od.Underlying
IST = ZoneInfo("Asia/Kolkata")
DEMO = Path("data/fixtures/demo/scope_demo_tradebook.csv")


SHAPES = [
    # the four vertical rows of the 12 Nov ruling: equal units, so the sign is fixed
    pytest.param([leg(LONG, 23000, 30), leg(SHORT, 23100, 10, seconds=2)], U.LONG,
                 id="call vertical, lower bought (debit) -> long"),
    pytest.param([leg(LONG, 23100, 10), leg(SHORT, 23000, 30, seconds=2)], U.SHORT,
                 id="call vertical, lower sold (credit) -> short"),
    pytest.param([leg(LONG, 23100, 30, kind=PE), leg(SHORT, 23000, 10, kind=PE, seconds=2)],
                 U.SHORT, id="put vertical, higher bought (debit) -> short"),
    pytest.param([leg(LONG, 22900, 10, kind=PE), leg(SHORT, 23000, 30, kind=PE, seconds=2)],
                 U.LONG, id="put vertical, higher sold (credit) -> long"),
    # a leg split by a partial close nets before the shape is read
    pytest.param([leg(LONG, 23100, 10), leg(SHORT, 23000, 30, qty=30, seconds=1),
                  leg(SHORT, 23000, 30, qty=35, seconds=1, held=7200)], U.SHORT,
                 id="credit call vertical in two parcels -> short"),
    # ratios, 13 Nov ruling: fixed when the larger-delta leg has at least as many units
    pytest.param([leg(LONG, 23100, 10, qty=65), leg(SHORT, 23000, 30, 40, qty=130, seconds=1)],
                 U.SHORT, id="ratio of test_positions, 130 sold on the lower call -> short"),
    pytest.param([leg(LONG, 23000, 30, qty=130), leg(SHORT, 23100, 10, qty=65, seconds=1)],
                 U.LONG, id="call ratio, more bought on the lower strike -> long"),
    pytest.param([leg(LONG, 23000, 30, qty=65), leg(SHORT, 23100, 10, qty=130, seconds=1)],
                 U.NONE, id="call ratio, more sold on the higher strike -> none"),
    pytest.param([leg(LONG, 23100, 30, qty=130, kind=PE),
                  leg(SHORT, 23000, 10, qty=65, kind=PE, seconds=1)],
                 U.SHORT, id="put ratio, more bought on the higher strike -> short"),
    pytest.param([leg(LONG, 23100, 30, qty=65, kind=PE),
                  leg(SHORT, 23000, 10, qty=130, kind=PE, seconds=1)],
                 U.NONE, id="put ratio, more sold on the lower strike -> none"),
    # given no direction
    pytest.param([leg(LONG, 23000, 50, qty=1), leg(SHORT, 23100, 30, qty=2, seconds=1),
                  leg(LONG, 23200, 20, qty=1, seconds=2)], U.NONE, id="butterfly -> none"),
    pytest.param([leg(SHORT, 5800, 30, 40), leg(LONG, 5800, 20, 25, kind=PE, seconds=2)],
                 U.NONE, id="sold call and bought put, not one option type -> none"),
]


@pytest.mark.parametrize(("legs", "expected"), SHAPES)
def test_each_shape_gets_the_ruled_answer(legs, expected):
    position = one(legs)
    assert len(position.legs) == len(legs), "the legs did not link into one position"
    assert od.underlying_direction(position) is expected


def test_a_winner_and_a_loser_of_one_shape_agree():
    """Read from the legs, never from the result (gate 2)."""
    winner = one([leg(LONG, 23000, 30, 50), leg(SHORT, 23100, 10, 15, seconds=2)])
    loser = one([leg(LONG, 23000, 30, 20), leg(SHORT, 23100, 10, 5, seconds=2)])
    assert sum(t.gross_pnl for t in winner.legs) > 0 > sum(t.gross_pnl for t in loser.legs)
    assert od.underlying_direction(winner) is od.underlying_direction(loser) is U.LONG


@pytest.fixture(scope="module")
def demo():
    from services.production.ctr.intake import pipeline as pl

    plan = pl.plan_import(
        DEMO.read_text(encoding="utf-8"),
        context=pl.ImportContext(trader_id="demo", source_account="DEMO", code_version="test",
                                 export_date="2026-09-01", export_date_source="trader"),
        production=True)
    return plan.positions


def test_the_demo_file_counts_no_trip_out_for_want_of_a_direction(demo):
    """Gate 4 on synthetic data. The demo file's sample trader holds one two-leg position:
    CRUDEOILM, bought 10 CE 5750 and sold 10 CE 5850, a debit call vertical. Before the
    convention it was counted out as "no single direction"; now it is long, and no demo trip
    is counted out for want of a direction. If the demo's two-leg positions change, recount
    them by hand before changing this test."""
    from services.production.mirror import prior_minute as pm
    from tests.unit.mirror.test_prior_minute import walk

    multi = [p for p in demo if len(p.legs) > 1]
    assert len(multi) == 1
    (vertical,) = multi
    legs = sorted((t.option_type.value, int(t.strike), t.direction.value, t.quantity)
                  for t in vertical.legs)
    assert legs == [("CE", 5750, "LONG", 10), ("CE", 5850, "SHORT", 10)]
    answers = {p.position_id: od.underlying_direction(p) for p in demo}
    assert answers[vertical.position_id] is U.LONG

    sign = {U.LONG: 1, U.SHORT: -1, U.NONE: None}
    entries = [pm.Entry(p.position_id, p.legs[0].symbol, p.entry_ts, sign[answers[p.position_id]])
               for p in demo]
    days = sorted({p.entry_ts.astimezone(IST).date() for p in demo})
    result = pm.count(entries, {"NIFTY": walk(1, days), "CRUDEOIL": walk(2, days)})
    assert result.total == len(demo)
    assert result.unmeasured_by_reason().get(pm.Reason.NO_DIRECTION, 0) == 0


def test_every_demo_single_leg_answers_by_the_4_7_7_table(demo):
    """Gate 5: the single-leg rule is untouched."""
    singles = [p for p in demo if len(p.legs) == 1]
    assert singles, "the demo file has no single-leg position"
    for p in singles:
        t = p.legs[0]
        key = (t.option_type if t.segment is Segment.OPT else None, t.direction)
        assert od.underlying_direction(p) is od.TABLE[key], p.position_id