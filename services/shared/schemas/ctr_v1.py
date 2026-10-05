"""Canonical Trade Record (CTR), schema v1.

The one shape every broker export becomes (ADR 001). Two objects:

* ``Fill``      — one buy or sell, as the broker reported it.
* ``RoundTrip`` — one complete trade, entry to exit, with its risk unit and R.

Rules enforced here, each traceable to the frozen documents:

* Timestamps carry a timezone. A naive timestamp is ambiguous and is refused
  (Research Spec v1.0 §4.3 — point-in-time correctness needs an unambiguous instant).
* Contract identity: every futures or options record carries symbol **and** expiry;
  options also carry type and strike (§4.2, corrected at freeze). Crude rolls monthly,
  so a bare symbol cannot identify what was traded.
* Determinism: ``fill_id`` and ``trip_id`` are content hashes over a fixed field list
  in a fixed order. Same input, same id, on any machine (§4.2, Methodology §2 Rule 4).
  Adding a field to the model does not change existing ids; adding one to the hash
  tuple is a major version.
* Scope: a long option's risk unit is the premium paid; a **short** option raises
  ``UnsupportedInV1`` because the R convention for unlimited-risk positions is not
  decided (framework_v1.yaml ``scope``, Annex H — due week 3). A future with no
  recorded stop reports ``risk_unit=None`` and ``r_multiple=None`` rather than guess
  (§4.5 — typed missingness, never imputed).

All money is ``Decimal``; no float arithmetic decides a trader-facing number
(§6.5). An earlier version of this schema also forced money through integer paise
and refused sub-paise values. Real data showed that to be wrong on both counts:
Decimal addition and subtraction are already exact, so the conversion bought
nothing, and a fill apportioned across trips legitimately carries sub-paise
precision. Rounding belongs at the presentation boundary.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, computed_field, field_validator, model_validator

SCHEMA_VERSION = "ctr_v1"

_ID_LENGTH = 16


class Segment(str, Enum):
    """Instrument class. Contract identity is required for FUT and OPT."""

    EQ = "EQ"
    FUT = "FUT"
    OPT = "OPT"


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class Direction(str, Enum):
    """Which side opened the trip."""

    LONG = "LONG"
    SHORT = "SHORT"


class OptionType(str, Enum):
    CE = "CE"
    PE = "PE"


class RiskUnitSource(str, Enum):
    """Where the R denominator came from. ``UNKNOWN`` means no R is reported."""

    PREMIUM_PAID = "PREMIUM_PAID"
    RECORDED_STOP = "RECORDED_STOP"
    UNKNOWN = "UNKNOWN"


class UnsupportedInV1(Exception):
    """A record this schema version deliberately refuses.

    Raised so an adapter can catch it, count what it skipped and report the reason —
    never drop the row silently (Methodology §2 Rule 1).

    It deliberately does **not** subclass ``ValueError``: pydantic converts
    ``ValueError`` raised inside a validator into a ``ValidationError``, which would
    make "outside v1 scope" indistinguishable from "malformed record". Any other
    exception type propagates uncaught, so this one reaches the adapter as itself.
    """


def _digest(*parts: Any) -> str:
    """Stable short hash over an ordered tuple of fields."""
    payload = "\x1f".join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:_ID_LENGTH]


class _Contract(BaseModel):
    """Fields that identify what was traded. Shared by fills and round trips."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    trader_id: str
    broker: str
    exchange: str
    segment: Segment
    symbol: str
    expiry: date | None = None
    option_type: OptionType | None = None
    strike: Decimal | None = None

    @field_validator("trader_id", "broker", "exchange", "symbol")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be empty")
        return v

    @model_validator(mode="after")
    def _contract_identity(self) -> _Contract:
        """§4.2: derivatives need an expiry; options need type and strike."""
        if self.segment in (Segment.FUT, Segment.OPT) and self.expiry is None:
            raise ValueError(
                f"expiry is required for segment {self.segment.value} — "
                "a bare symbol cannot identify the contract traded"
            )
        if self.segment is Segment.OPT:
            if self.option_type is None:
                raise ValueError("option_type is required for segment OPT")
            if self.strike is None:
                raise ValueError("strike is required for segment OPT")
        if self.segment is Segment.EQ and self.expiry is not None:
            raise ValueError("expiry must be empty for segment EQ")
        return self

    @property
    def contract_key(self) -> str:
        """The fields that together name the contract. Part of every id."""
        return "|".join(
            str(p) if p is not None else ""
            for p in (
                self.exchange,
                self.segment.value,
                self.symbol,
                self.expiry,
                self.option_type.value if self.option_type else None,
                self.strike,
            )
        )


class Fill(_Contract):
    """One buy or sell as the broker reported it.

    ``price`` is the exact price the arithmetic uses. ``quoted_price`` is what the
    broker displayed — often a rounded average of aggregated fills — kept so the
    trader sees the number he saw, and never used in a computation. It is outside
    the hash tuple, so adding it did not change any existing ``fill_id``.

    ``raw_hash`` ties the fill to the immutable raw export it came from
    (Methodology §2 Rule 1); ``fill_id`` is its content hash.
    """

    ts: datetime
    side: Side
    quantity: int
    price: Decimal
    quoted_price: Decimal | None = None
    product: str | None = None
    raw_hash: str

    @field_validator("ts")
    @classmethod
    def _aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.tzinfo.utcoffset(v) is None:
            raise ValueError(
                "ts must carry a timezone — a naive timestamp is ambiguous (§4.3)"
            )
        return v

    @field_validator("quantity")
    @classmethod
    def _positive_qty(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("quantity must be positive; direction is carried by side")
        return v

    @field_validator("price")
    @classmethod
    def _positive_price(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("price must be positive")
        return v

    @field_validator("raw_hash")
    @classmethod
    def _sha256_hex(cls, v: str) -> str:
        if len(v) != 64 or any(c not in "0123456789abcdef" for c in v.lower()):
            raise ValueError("raw_hash must be a 64-character sha256 hex digest")
        return v.lower()

    @computed_field  # type: ignore[prop-decorator]
    @property
    def fill_id(self) -> str:
        """Deterministic id. The hash tuple is fixed; changing it is a major version."""
        return _digest(
            SCHEMA_VERSION,
            self.trader_id,
            self.broker,
            self.contract_key,
            self.ts.isoformat(),
            self.side.value,
            self.quantity,
            self.price,
        )


class RoundTrip(_Contract):
    """One complete trade: entry to exit, with the risk unit that gives it an R."""

    direction: Direction
    entry_ts: datetime
    exit_ts: datetime
    quantity: int
    entry_price: Decimal
    exit_price: Decimal
    gross_pnl: Decimal
    fees: Decimal
    risk_unit: Decimal | None = None
    risk_unit_source: RiskUnitSource = RiskUnitSource.UNKNOWN
    fill_ids: list[str]

    @field_validator("entry_ts", "exit_ts")
    @classmethod
    def _aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.tzinfo.utcoffset(v) is None:
            raise ValueError("timestamps must carry a timezone (§4.3)")
        return v

    @field_validator("quantity")
    @classmethod
    def _positive_qty(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("quantity must be positive")
        return v

    @field_validator("entry_price", "exit_price")
    @classmethod
    def _positive_price(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("price must be positive")
        return v

    @field_validator("fees")
    @classmethod
    def _fees_not_negative(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("fees must not be negative")
        return v

    @field_validator("fill_ids")
    @classmethod
    def _has_fills(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("a round trip must cite the fills it was built from")
        return v

    @model_validator(mode="after")
    def _ordered_and_in_scope(self) -> RoundTrip:
        if self.exit_ts < self.entry_ts:
            raise ValueError("exit_ts must not precede entry_ts")

        if self.segment is Segment.OPT and self.direction is Direction.SHORT:
            raise UnsupportedInV1(
                "a short option position is outside ctr_v1: the R convention for "
                "unlimited-risk positions is not decided (framework scope; Annex H)"
            )

        # A long option's risk is bounded by the premium it paid, so R is derivable
        # without a stop. Set it here unless the adapter supplied one explicitly.
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
    def trip_id(self) -> str:
        return _digest(
            SCHEMA_VERSION,
            self.trader_id,
            self.broker,
            self.contract_key,
            self.direction.value,
            self.entry_ts.isoformat(),
            self.exit_ts.isoformat(),
            self.quantity,
            self.entry_price,
            self.exit_price,
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def net_pnl(self) -> Decimal:
        """Gross minus fees, exact.

        Decimal subtraction is exact, so no rounding happens here. The value may
        carry sub-paise precision when a fill was apportioned across trips -- an
        aggregated fill of 30 units at a total of 4595.50 has a per-unit price of
        153.18333..., and a trip matching 10 of those units legitimately owns
        1531.8333... of it. Rounding each trip to the paise would break
        sum(trip gross) == sum(fill values) by up to half a paisa per trip.
        Trader-facing figures are rounded at the presentation boundary, never in
        the record (s6.5: the conservative 5th percentile, shown as "at least").
        """
        return self.gross_pnl - self.fees

    @computed_field  # type: ignore[prop-decorator]
    @property
    def r_multiple(self) -> Decimal | None:
        """Net result in units of risk taken. ``None`` when the risk unit is unknown."""
        if self.risk_unit is None or self.risk_unit_source is RiskUnitSource.UNKNOWN:
            return None
        return self.net_pnl / self.risk_unit

    @computed_field  # type: ignore[prop-decorator]
    @property
    def holding_seconds(self) -> int:
        return int((self.exit_ts - self.entry_ts).total_seconds())
