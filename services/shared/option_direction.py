"""Which way the underlying had to move for a trip to profit [TICKET-890].

The executable form of the table in the research spec, docs/trade_dna_research_spec_v1_0.md
section 4.7.7 ("Direction, for one leg"), which names this module by path. One rule, two
pointers, neither one a copy. It sits in ``shared`` because production and research may both
read it and neither may read the other (methodology Rule 5).

A bought call is long the underlying, a bought put is short, and a sold option inverts the
bought answer. A future or a share takes its own side. ``Underlying`` is not
``ctr_v1.Direction``: that records whether the contract was bought or sold, this records
which way the underlying had to move.

Multi-leg direction is open (section 4.7.8). ``positions._links`` joins only a bought leg to a
sold one, so every multi-leg position the product can build holds both, and the answer is
``NONE`` -- as the rule, not an edge case. A count reading this reports those trips with that
reason; it never drops them silently.

Reads the legs only: segment, option type, bought or sold. Nothing here looks at a price or
at whether the trade made money.
"""

from __future__ import annotations

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

def underlying_direction(trip: ctr_v1.RoundTrip | Position) -> Underlying:
    """One trip or one position: long, short, or none (section 4.7.7, 4.7.8)."""
    legs: tuple[ctr_v1.RoundTrip, ...] = trip.legs if isinstance(trip, Position) else (trip,)
    if len(legs) != 1:
        return Underlying.NONE
    only = legs[0]
    if only.segment is not Segment.OPT:
        return TABLE[(None, only.direction)]
    if only.option_type is None:
        raise ValueError("an option leg without a call or put type has no direction")
    return TABLE[(only.option_type, only.direction)]