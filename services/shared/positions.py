"""Legs into positions, and a position's risk unit (Annex H draft 2, sections 3 to 5).

Shared because the unit of a research test is the position too, and one function decides
it, as with the B2 condition. A layer above trips: no trip's record changes.

**Linking.** Two legs link only as one LONG and one SHORT, on the same underlying and expiry,
different contract, entered within the window. A position is a connected component of those
links. Two bought legs never link, so a long straddle stays two trips, and that rule is what
keeps a wider window from gluing unrelated legs together. Calendars and diagonals are not
recognised, because a cross-expiry payoff has no single terminal date.

**P&L** is the sum of the legs and is never refused. Nothing here removes money.

**R** is the most the position can lose at expiry, ``-min(payoff)``, and the payoff's minimum
is at a strike when the position is covered (net long or flat in each option type). Net short
in a type is ``UNCAPPED``: the money counts, no number is made up. A figure of zero or less
describes a riskless position, which real fills do not produce, so it is flagged.

One unit of these options pays one rupee a point, so no multiplier appears here, for the
same reason ``reconstruct`` never applies one to money.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from services.shared.schemas.ctr_v1 import Direction, OptionType, Segment, _digest
from services.shared.schemas.ctr_v2 import RiskUnitSource, RoundTrip

LINK_WINDOW_SECONDS = 180
"""Set from the stability plateau on one trader's file. Revisit on the next export.

Short-containing positions on that file: 12 / 14 / 16 / 16 at 15 / 60 / 180 / 600 seconds.
180 is the floor, because two sold legs sit 61 and 74 seconds from their partners, and the
ceiling, because 600 glues on a bought leg from eight minutes earlier (Annex H section 3).
"""

_ZERO = Decimal(0)


@dataclass(frozen=True)
class Position:
    """One decision: one or more legs, one entry time, one outcome."""

    position_id: str
    legs: tuple[RoundTrip, ...]
    risk_unit: Decimal | None
    risk_unit_source: RiskUnitSource
    inconsistent: bool = False

    @property
    def gross(self) -> Decimal:
        return sum((t.gross_pnl for t in self.legs), _ZERO)

    @property
    def net(self) -> Decimal:
        return sum((t.net_pnl for t in self.legs), _ZERO)

    @property
    def entry_ts(self) -> datetime:
        return min(t.entry_ts for t in self.legs)

    @property
    def exit_ts(self) -> datetime:
        return max(t.exit_ts for t in self.legs)


def _links(a: RoundTrip, b: RoundTrip) -> bool:
    return a.direction is not b.direction and a.contract_key != b.contract_key


def _components(trips: list[RoundTrip], window_seconds: int) -> list[list[RoundTrip]]:
    parent = list(range(len(trips)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    markets: dict[tuple, list[int]] = defaultdict(list)
    for i, t in enumerate(trips):
        if t.segment is Segment.OPT:
            markets[(t.exchange, t.symbol, t.expiry)].append(i)

    for indices in markets.values():  # already in entry order, as trips is
        for at, i in enumerate(indices):
            for j in indices[at + 1:]:
                if (trips[j].entry_ts - trips[i].entry_ts).total_seconds() > window_seconds:
                    break
                if _links(trips[i], trips[j]):
                    parent[find(i)] = find(j)

    groups: dict[int, list[RoundTrip]] = defaultdict(list)
    for i, t in enumerate(trips):
        groups[find(i)].append(t)
    return list(groups.values())


def _covered(net_by_contract: dict) -> bool:
    for kind in OptionType:
        if sum(q for (k, _), (q, _) in net_by_contract.items() if k is kind) < 0:
            return False
    return True


def _worst_case_at_expiry(net_by_contract: dict) -> Decimal:
    """The lowest terminal profit, at a strike. Annex H section 5."""
    credit = _ZERO
    for quantity, value_in in net_by_contract.values():
        if quantity < 0:
            credit += value_in
        elif quantity > 0:
            credit -= value_in

    def profit_at(level: Decimal) -> Decimal:
        total = credit
        for (kind, strike), (quantity, _) in net_by_contract.items():
            intrinsic = level - strike if kind is OptionType.CE else strike - level
            total += quantity * max(intrinsic, _ZERO)
        return total

    return min(profit_at(strike) for _, strike in net_by_contract)


def _position(legs: list[RoundTrip]) -> Position:
    if len(legs) == 1:
        only = legs[0]
        return Position(only.trip_id, (only,), only.risk_unit, only.risk_unit_source)

    position_id = _digest("position", *sorted(t.trip_id for t in legs))
    net_by_contract: dict = defaultdict(lambda: (0, _ZERO))
    for t in legs:
        signed = t.quantity if t.direction is Direction.LONG else -t.quantity
        quantity, value_in = net_by_contract[(t.option_type, t.strike)]
        net_by_contract[(t.option_type, t.strike)] = (
            quantity + signed,
            value_in + t.entry_price * t.quantity,
        )

    if not _covered(net_by_contract):
        return Position(position_id, tuple(legs), None, RiskUnitSource.UNCAPPED)

    risk = -_worst_case_at_expiry(net_by_contract)
    if risk <= 0:
        return Position(position_id, tuple(legs), None, RiskUnitSource.UNKNOWN, inconsistent=True)
    return Position(position_id, tuple(legs), risk, RiskUnitSource.STRUCTURE_MAX_LOSS)


def group_positions(
    trips: Iterable[RoundTrip], *, window_seconds: int = LINK_WINDOW_SECONDS
) -> list[Position]:
    """Every leg into exactly one position, in entry order. Same input, same output."""
    ordered = sorted(trips, key=lambda t: (t.entry_ts, t.trip_id))
    positions = [_position(group) for group in _components(ordered, window_seconds)]
    return sorted(positions, key=lambda p: (p.entry_ts, p.position_id))
