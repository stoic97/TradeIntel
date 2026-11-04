"""Canonical Trade Record, schema v2: sold options are legs (Annex H draft 2).

Versioned by file (ADR 001), so ``ctr_v1`` is not edited and still refuses a sold option.
Everything v1 records means the same here. Two things are new: a SHORT option trip is built
rather than refused, and ``RiskUnitSource`` gains ``STRUCTURE_MAX_LOSS`` and ``UNCAPPED``.

**Ids stay v1 ids.** ``fill_id`` and ``trip_id`` hash ``ctr_v1.SCHEMA_VERSION``, and the
research seat's minute says every v1 trip id is unchanged. So those properties are inherited
and hash the v1 string, while :data:`SCHEMA_VERSION` here names the shape of the record.
Hashing the v2 string instead would silently change every id in every stored import.

P&L needs no convention and is never refused. R does, and a sold option has none of its own:
a leg records ``UNCAPPED``, and :mod:`services.shared.positions` decides the position's.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum

from pydantic import computed_field, model_validator

from services.shared.schemas import ctr_v1
from services.shared.schemas.ctr_v1 import Direction, Segment

SCHEMA_VERSION = "ctr_v2"


class RiskUnitSource(str, Enum):
    """Where the R denominator came from. ``UNKNOWN`` and ``UNCAPPED`` report no R."""

    PREMIUM_PAID = "PREMIUM_PAID"
    RECORDED_STOP = "RECORDED_STOP"
    UNKNOWN = "UNKNOWN"
    STRUCTURE_MAX_LOSS = "STRUCTURE_MAX_LOSS"
    UNCAPPED = "UNCAPPED"


class RoundTrip(ctr_v1.RoundTrip):
    """One leg: entry to exit, long or short. A position is one or more of these."""

    risk_unit_source: RiskUnitSource = RiskUnitSource.UNKNOWN  # type: ignore[assignment]

    @model_validator(mode="after")
    def _ordered_and_in_scope(self) -> RoundTrip:
        """Replaces v1's validator of this name: the same rules, less the refusal."""
        if self.exit_ts < self.entry_ts:
            raise ValueError("exit_ts must not precede entry_ts")

        if self.segment is Segment.OPT and self.direction is Direction.SHORT:
            if self.risk_unit is not None:
                raise ValueError("a sold option leg has no risk unit of its own")
            object.__setattr__(self, "risk_unit_source", RiskUnitSource.UNCAPPED)
            return self

        if (
            self.segment is Segment.OPT
            and self.direction is Direction.LONG
            and self.risk_unit_source is RiskUnitSource.UNKNOWN
        ):
            object.__setattr__(self, "risk_unit", self.entry_price * self.quantity)
            object.__setattr__(self, "risk_unit_source", RiskUnitSource.PREMIUM_PAID)

        if self.risk_unit_source is RiskUnitSource.UNKNOWN and self.risk_unit is not None:
            raise ValueError("risk_unit given without a risk_unit_source")
        if self.risk_unit is not None and self.risk_unit <= 0:
            raise ValueError("risk_unit must be positive")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def r_multiple(self) -> Decimal | None:
        """Net result in units of risk taken. ``None`` where there is no risk unit."""
        if self.risk_unit is None:
            return None
        return self.net_pnl / self.risk_unit
