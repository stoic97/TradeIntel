"""Moved out of tests/unit/mirror/test_run_story.py by TICKET-945, so that no test file imports another."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s


def trip(
    trip_id,
    day,
    opened,
    closed,
    net,
    *,
    symbol="WIDGETOIL",
    kind="CE",
    strike=5000,
    qty=50,
    closed_day=None,
    segment="OPT",
):
    entry = datetime.fromisoformat(f"{day}T{opened}+05:30")
    exit_ = datetime.fromisoformat(f"{closed_day or day}T{closed}+05:30")
    is_option = segment == "OPT"
    line = mx.TradeLine(
        symbol=symbol,
        segment=segment,
        side="Buy",
        quantity=qty,
        entry_price=Decimal(10),
        exit_price=Decimal(9),
        net=Decimal(net),
        strike=Decimal(strike) if is_option else None,
        option_type=kind if is_option else None,
        entry_ts=entry,
    )
    return mx.Trip(
        trip_id,
        symbol,
        day,
        entry,
        exit_,
        int((exit_ - entry).total_seconds()),
        Decimal(net),
        1,
        s.RiskUnitSourceV1.PREMIUM_PAID,
        is_option=is_option,
        lines=(line,),
    )


def spread(trip_id, day, opened, closed, net):
    """A position of two legs: one Trip with one result."""
    first = trip("x", day, opened, closed, net)
    second = trip("y", day, opened, closed, 0, kind="PE", strike=4900)
    legs = (mx.Leg("Bought 5000 CE", Decimal(net)), mx.Leg("Bought 4900 PE", Decimal(0)))
    return mx.Trip(
        trip_id,
        "WIDGETOIL",
        day,
        first.entry_ts,
        first.exit_ts,
        first.holding_seconds,
        Decimal(net),
        1,
        s.RiskUnitSourceV1.STRUCTURE_MAX_LOSS,
        legs=legs,
        lines=(first.lines[0], second.lines[0]),
    )


DAY = "2026-03-03"


RUN = [
    trip("r1", DAY, "18:00:00", "18:10:00", -100),
    trip("r2", DAY, "18:10:12", "18:20:00", -200),
    trip("r3", DAY, "18:21:30", "18:30:00", -300, kind="PE", strike=4900, qty=100),
    trip("r4", DAY, "18:32:00", "18:40:00", -50, kind="PE", strike=4900, qty=150),
    trip("r5", DAY, "18:42:01", "18:50:00", -150, qty=150),
    trip("r6", DAY, "18:50:30", "19:00:00", -200, kind="PE", strike=4900, qty=100),
]


EVENING = [
    trip("m", DAY, "09:00:00", "09:05:00", 200),
    *RUN,
    trip("a", DAY, "19:01:00", "19:30:00", 400, qty=100),
    trip("c1", "2026-03-04", "15:00:00", "15:10:00", -800, symbol="WIDGETIDX", strike=100, qty=75),
    trip("c2", "2026-03-05", "09:20:00", "09:30:00", -900, symbol="WIDGETIDX", strike=100, qty=75),
    trip("e", "2026-03-05", "10:00:00", "10:05:00", 50, symbol="WIDGETIDX", strike=100, qty=75),
]
