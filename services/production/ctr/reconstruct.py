"""Fills -> round trips, FIFO, per contract.

Brokers export fills; every research test needs round trips (ADR 001). This module
is the transformation between them, and it is a pure function of its input: the same
fills in the same order always produce the same trips, with the same ids
(Methodology s2 Rule 2).

**A round trip is a matched entry-exit parcel**, not a flat-to-flat cycle. A fill in
the same direction as the open position adds a lot; a fill in the opposite direction
closes lots oldest-first and emits one trip for the quantity it matched. A partial
close therefore produces a trip immediately and leaves the rest open. That is the
unit the research tests need -- one R per closed trade -- and it keeps the accounting
local, so matched units cannot go unrecorded. (The first draft of this module defined
a trip as flat-to-flat; the conservation assertion below caught it on the first run.)
When a closing fill is larger than the position, the position flips and the excess
opens a new one in the other direction.

**Gross is computed from the value sums, never from the average prices.** A weighted
average is a Decimal division and therefore truncates; ``(exit_price - entry_price) *
quantity`` would carry that truncation into a trader-facing number. So gross is
``sum(sell values) - sum(buy values)``, exact, and the average prices ride along for
display. Same principle as the adapter: the value is authoritative, the price derived.

**Nothing is forced.** A position still open when the history ends is reported as an
open position, not closed at an invented price (Research Spec s4.2). A trip the schema
refuses -- a short option, whose R convention is undecided -- is recorded with its
reason and its quantity, so the counts stay honest (s4.5).

The invariant, asserted by :class:`ReconstructionResult` itself:

    2*sum(trip.quantity) + sum(open.quantity) + 2*sum(skipped.quantity)
        == sum(fill.quantity)

Every unit that arrived is matched into a trip (consuming one unit on each side),
still open, or inside a refused trip. If that breaks, a unit was invented or lost.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from services.shared.schemas.ctr_v1 import (
    Direction,
    Fill,
    RiskUnitSource,
    RoundTrip,
    Segment,
    Side,
    UnsupportedInV1,
)

_ZERO = Decimal(0)


@dataclass(frozen=True)
class OpenPosition:
    """Quantity still open when the history ended. Never closed at a guessed price."""

    contract_key: str
    symbol: str
    direction: Direction
    quantity: int
    opened_at: datetime
    fill_ids: list[str]
    reason: str = "open at the end of the history"


@dataclass(frozen=True)
class SkippedTrip:
    """A matched trip the schema refused, with the reason and the quantity involved."""

    contract_key: str
    symbol: str
    direction: Direction
    quantity: int
    reason: str
    fill_ids: list[str]


@dataclass(frozen=True)
class ReconstructionResult:
    quantity_in: int
    round_trips: list[RoundTrip] = field(default_factory=list)
    open_positions: list[OpenPosition] = field(default_factory=list)
    skipped: list[SkippedTrip] = field(default_factory=list)
    fees_available: bool = False

    def __post_init__(self) -> None:
        matched = 2 * sum(t.quantity for t in self.round_trips)
        refused = 2 * sum(s.quantity for s in self.skipped)
        still_open = sum(o.quantity for o in self.open_positions)
        accounted = matched + refused + still_open
        if accounted != self.quantity_in:
            raise AssertionError(
                f"{self.quantity_in} units in but {accounted} accounted for "
                f"(matched {matched}, refused {refused}, open {still_open}) -- "
                "a unit was invented or lost"
            )


@dataclass
class _Lot:
    """One open parcel: quantity still live, at the price and time it was opened."""

    quantity: int
    price: Decimal
    ts: datetime
    fill_id: str


@dataclass
class _Leg:
    """One side of a trip being assembled: matched quantity and its exact value."""

    quantity: int = 0
    value: Decimal = _ZERO
    fill_ids: list[str] = field(default_factory=list)
    first_ts: datetime | None = None
    last_ts: datetime | None = None

    def add(self, quantity: int, price: Decimal, ts: datetime, fill_id: str) -> None:
        self.quantity += quantity
        self.value += price * quantity
        if fill_id not in self.fill_ids:
            self.fill_ids.append(fill_id)
        self.first_ts = ts if self.first_ts is None else min(self.first_ts, ts)
        self.last_ts = ts if self.last_ts is None else max(self.last_ts, ts)

    @property
    def average_price(self) -> Decimal:
        return self.value / self.quantity


def _build_trip(
    sample: Fill,
    direction: Direction,
    entry: _Leg,
    exit_: _Leg,
) -> RoundTrip:
    """Assemble one trip. ``sample`` supplies the contract fields; both legs are closed."""
    assert entry.quantity == exit_.quantity, "legs must match before a trip is built"
    assert entry.first_ts is not None and exit_.last_ts is not None

    # Exact: value in minus value out, by direction. Not derived from average prices.
    if direction is Direction.LONG:
        gross = exit_.value - entry.value
    else:
        gross = entry.value - exit_.value

    risk_unit: Decimal | None = None
    risk_unit_source = RiskUnitSource.UNKNOWN
    if sample.segment is Segment.OPT and direction is Direction.LONG:
        # The exact premium paid, not entry_price * quantity, which would carry the
        # truncation of the weighted average.
        risk_unit = entry.value
        risk_unit_source = RiskUnitSource.PREMIUM_PAID

    return RoundTrip(
        trader_id=sample.trader_id,
        broker=sample.broker,
        exchange=sample.exchange,
        segment=sample.segment,
        symbol=sample.symbol,
        expiry=sample.expiry,
        option_type=sample.option_type,
        strike=sample.strike,
        direction=direction,
        entry_ts=entry.first_ts,
        exit_ts=exit_.last_ts,
        quantity=entry.quantity,
        entry_price=entry.average_price,
        exit_price=exit_.average_price,
        gross_pnl=gross,
        fees=_ZERO,  # no charges column in any adapter yet; fees_available says so
        risk_unit=risk_unit,
        risk_unit_source=risk_unit_source,
        fill_ids=[*entry.fill_ids, *exit_.fill_ids],
    )


def _reconstruct_contract(
    fills: list[Fill],
    trips: list[RoundTrip],
    skipped: list[SkippedTrip],
    opens: list[OpenPosition],
) -> None:
    """Walk one contract's fills in time order, maintaining a FIFO lot queue."""
    sample = fills[0]
    lots: list[_Lot] = []
    position: Direction | None = None

    def emit(direction: Direction, entry: _Leg, exit_: _Leg) -> None:
        try:
            trips.append(_build_trip(sample, direction, entry, exit_))
        except UnsupportedInV1 as exc:
            skipped.append(
                SkippedTrip(
                    contract_key=sample.contract_key,
                    symbol=sample.symbol,
                    direction=direction,
                    quantity=entry.quantity,
                    reason=str(exc),
                    fill_ids=[*entry.fill_ids, *exit_.fill_ids],
                )
            )

    for f in fills:
        incoming = Direction.LONG if f.side is Side.BUY else Direction.SHORT
        remaining = f.quantity

        if not lots:
            position = incoming

        if incoming is position:
            lots.append(_Lot(remaining, f.price, f.ts, f.fill_id))
            continue

        # Opposite side: close lots oldest-first, then emit one trip for what matched.
        entry, exit_ = _Leg(), _Leg()
        while remaining and lots:
            lot = lots[0]
            take = min(remaining, lot.quantity)
            entry.add(take, lot.price, lot.ts, lot.fill_id)
            exit_.add(take, f.price, f.ts, f.fill_id)
            lot.quantity -= take
            remaining -= take
            if lot.quantity == 0:
                lots.pop(0)

        if entry.quantity:
            assert position is not None
            emit(position, entry, exit_)

        if remaining:
            # The closing fill was larger than the position: it flips.
            position = incoming
            lots.append(_Lot(remaining, f.price, f.ts, f.fill_id))

    if lots:
        assert position is not None
        opens.append(
            OpenPosition(
                contract_key=sample.contract_key,
                symbol=sample.symbol,
                direction=position,
                quantity=sum(lot.quantity for lot in lots),
                opened_at=min(lot.ts for lot in lots),
                fill_ids=[lot.fill_id for lot in lots],
            )
        )


def reconstruct(fills: Iterable[Fill], *, fees_available: bool = False) -> ReconstructionResult:
    """Turn fills into round trips, FIFO, per (trader, contract).

    Fills are sorted by timestamp before matching, so the caller need not rely on the
    export's own order -- Dhan's, for one, is newest-first.
    """
    ordered = sorted(fills, key=lambda f: (f.ts, f.contract_key, f.side.value, f.fill_id))

    by_contract: dict[tuple[str, str], list[Fill]] = defaultdict(list)
    for f in ordered:
        by_contract[(f.trader_id, f.contract_key)].append(f)

    trips: list[RoundTrip] = []
    skipped: list[SkippedTrip] = []
    opens: list[OpenPosition] = []
    for group in by_contract.values():
        _reconstruct_contract(group, trips, skipped, opens)

    trips.sort(key=lambda t: (t.exit_ts, t.contract_key))
    opens.sort(key=lambda o: (o.opened_at, o.contract_key))
    skipped.sort(key=lambda s: (s.contract_key, s.quantity))

    return ReconstructionResult(
        quantity_in=sum(f.quantity for f in ordered),
        round_trips=trips,
        open_positions=opens,
        skipped=skipped,
        fees_available=fees_available,
    )
