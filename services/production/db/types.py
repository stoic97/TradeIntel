"""Column types that keep the guarantees ``ctr_v1`` makes.

SQLite has no decimal and no timezone-aware timestamp, so both are stored as text
and converted at the boundary. Postgres at Phase 1 maps ``DecimalText`` to NUMERIC
and ``AwareDateTime`` to TIMESTAMPTZ; the Python side does not change.

Why text and not integer paise: ``ctr_v1``'s own history. An earlier schema forced
money through integer paise and refused sub-paise values, and real data showed that
to be wrong -- a fill apportioned across trips legitimately carries sub-paise
precision, and rounding each trip would break ``sum(trip gross) == sum(fill values)``.
Text is exact at any precision.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import DateTime, Dialect, String, TypeDecorator


class DecimalText(TypeDecorator[Decimal]):
    """A ``Decimal`` stored as its exact string form.

    Sorting and SUM() in raw SQL are not numeric on this column, which is deliberate:
    every figure a trader sees is computed in Python from Decimals, never by the
    database (methodology Rule 2 -- transformations are pure functions of their inputs).
    """

    impl = String
    cache_ok = True

    def process_bind_param(self, value: Decimal | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        if not isinstance(value, Decimal):
            raise TypeError(
                f"money must be Decimal, got {type(value).__name__} -- a float here "
                "becomes a wrong rupee figure that looks right (ctr_v1)"
            )
        return str(value)

    def process_result_value(self, value: str | None, dialect: Dialect) -> Decimal | None:
        return None if value is None else Decimal(value)


class AwareDateTime(TypeDecorator[datetime]):
    """A timezone-aware ``datetime``. A naive one is refused, never assumed to be UTC.

    ``ctr_v1`` section 4.3: a naive timestamp is ambiguous, and point-in-time
    correctness needs an unambiguous instant. Values are normalised to UTC on the way
    in and returned aware; the trading day is computed from the instrument profile's
    timezone, never from the stored zone.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError("datetime must carry a timezone (ctr_v1 section 4.3)")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class EnumText(TypeDecorator[Any]):
    """A ``scope_v1`` enum stored as its string value and returned as the enum.

    Storing the value keeps a database row readable without a lookup. Returning the
    **enum** matters more: every rule in the product is written as an identity test --
    ``trip.risk_unit_source is RiskUnitSourceV1.DECLARED_BUDGET`` decides whether a
    figure may be shown as a denominator at all (PRD 5.5). A plain string would make
    every such test quietly false.
    """

    impl = String
    cache_ok = True

    def __init__(self, enum_cls: type[Enum], length: int = 64) -> None:
        self.enum_cls = enum_cls
        super().__init__(length=length)

    def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:
        if value is None:
            return None
        if not isinstance(value, self.enum_cls):
            raise TypeError(
                f"expected {self.enum_cls.__name__}, got {type(value).__name__}"
            )
        return str(value.value)

    def process_result_value(self, value: str | None, dialect: Dialect) -> Any:
        return None if value is None else self.enum_cls(value)
