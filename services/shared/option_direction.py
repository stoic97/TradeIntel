"""Which way the underlying had to move for a trip to profit [TICKET-890].

The executable form of the table in the research spec, docs/trade_dna_research_spec_v1_0.md
section 4.7.7 ("Direction, for one leg"), which names this module by path. One rule, two
pointers, neither one a copy. It sits in ``shared`` because production and research may both
read it and neither may read the other (methodology Rule 5).

A bought call is long the underlying, a bought put is short, and a sold option inverts the
bought answer. A future or a share takes its own side. ``Underlying`` is not
``ctr_v1.Direction``: that records whether the contract was bought or sold, this records
which way the underlying had to move.

Multi-leg direction follows the convention of section 4.7.8 (TICKET-902). ``positions._links``
joins only a bought leg to a sold one, so every multi-leg position holds both. After netting the
units at each strike, a position with two strikes and one option type takes the direction of its
larger-delta leg (the lower strike for calls, the higher for puts) when that leg carries at least
as many units as the other; otherwise, and for every other shape, the answer is ``NONE``. A count
reading this reports those trips with that reason; it never drops them silently.

Reads the legs only: segment, option type, bought or sold, and for a multi-leg position its
strikes, expiry and units. Nothing here looks at a price or at whether the trade made money.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum

from services.shared.positions import Position
from services.shared.schemas import ctr_v1
from services.shared.schemas.ctr_v1 import Direction, OptionType, Segment


class Underlying(str, Enum):
    """Which way the underlying had to move. ``NONE`` is "no single direction" (4.7.8)."""

    LONG = "long"
    SHORT = "short"
    NONE = "none"


BOUGHT, SOLD = Direction.LONG, Direction.SHORT
TABLE: dict[tuple[OptionType | None, Direction], Underlying] = {
    # section 4.7.7, row for row. ``None`` is a future or a share: it takes its own side.
    (OptionType.CE, BOUGHT): Underlying.LONG,
    (OptionType.PE, BOUGHT): Underlying.SHORT,
    (OptionType.CE, SOLD): Underlying.SHORT,
    (OptionType.PE, SOLD): Underlying.LONG,
    (None, BOUGHT): Underlying.LONG,
    (None, SOLD): Underlying.SHORT,
}

def _multi_leg(legs: tuple[ctr_v1.RoundTrip, ...]) -> Underlying:
    """Section 4.7.8, from the legs alone.

    Two strikes, one option type, one expiry, one side bought and one sold after netting the
    units at each strike. The larger-delta leg (lower strike for calls, higher for puts) decides
    when it carries at least as many units as the other: net delta then keeps its sign at every
    level, and the position takes that leg's 4.7.7 answer. Fewer units and the sign flips with
    the level, so the answer is none. Any other shape (a butterfly, a call against a put) is none.
    """
    if len({t.option_type for t in legs}) != 1 or len({t.expiry for t in legs}) != 1:
        return Underlying.NONE
    kind = legs[0].option_type
    if kind is None:
        return Underlying.NONE
    net: dict[Decimal, int] = {}
    for t in legs:
        if t.segment is not Segment.OPT or t.strike is None:
            return Underlying.NONE
        signed = t.quantity if t.direction is BOUGHT else -t.quantity
        net[t.strike] = net.get(t.strike, 0) + signed
    held = sorted((strike, units) for strike, units in net.items() if units)
    if len(held) != 2 or (held[0][1] > 0) == (held[1][1] > 0):
        return Underlying.NONE
    (_, low), (_, high) = held
    lead, other = (low, high) if kind is OptionType.CE else (high, low)
    if abs(lead) < abs(other):
        return Underlying.NONE
    return TABLE[(kind, BOUGHT if lead > 0 else SOLD)]


def underlying_direction(trip: ctr_v1.RoundTrip | Position) -> Underlying:
    """One trip or one position: long, short, or none (section 4.7.7, 4.7.8)."""
    legs: tuple[ctr_v1.RoundTrip, ...] = trip.legs if isinstance(trip, Position) else (trip,)
    if len(legs) != 1:
        return _multi_leg(legs)
    only = legs[0]
    if only.segment is not Segment.OPT:
        return TABLE[(None, only.direction)]
    if only.option_type is None:
        raise ValueError("an option leg without a call or put type has no direction")
    return TABLE[(only.option_type, only.direction)]