"""Brokerage: each broker's published plan, as a preset the trader can change (TICKET-912).

RED stub: the signatures only. GREEN fills them in.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

TABLE = Path(__file__).parent / "brokerage.yaml"
KINDS = ("OPT", "FUT", "EQ_INTRADAY", "EQ_DELIVERY")


class UnknownBroker(LookupError):
    """No preset for this broker, so its brokerage can't be stated."""


class InvalidPresets(ValueError):
    """``brokerage.yaml`` breaks one of its own rules. Raised at load."""


@dataclass(frozen=True)
class Plan:
    flat: Decimal
    pct: Decimal | None = None
    min: Decimal | None = None
    min_pct: Decimal | None = None


@dataclass(frozen=True)
class Preset:
    broker: str
    name: str
    read_on: str
    source: str
    plans: dict[str, Plan]


def load(path: Path = TABLE) -> dict[str, Preset]:
    return {}


def presets() -> dict[str, Preset]:
    return {}


def preset(broker: str) -> Preset:
    raise UnknownBroker(broker)


def per_order(broker: str, kind: str, value: Decimal, *, own: Decimal | None = None) -> Decimal:
    return Decimal(0)
