"""Brokerage: each broker's published plan, as a preset the trader can change (TICKET-912).

Brokerage is the one part of a contract note that is not statutory, so it is not in
``rates.yaml``. It is the broker's price for an executed order. ``brokerage.yaml`` holds
each broker's published plan with the page it was read from and the day it was read.

**Ruled 14 Nov 2026 (founder, TICKET-912 Q2).** The published plan is the preset from
the day the rate table starts: neither broker publishes a dated history of
its plans, and the trader can change the figure. Before that date nothing is applied, so a
trade is either fully priced or not priced. Brokerage is per executed order, never per row:
Groww's export carries the order id; Dhan's doesn't, so a Dhan trade counts one order per
entry and one per exit of each leg (a part-filled order is billed once).

A trader's own figure (``per_order``) replaces the plan's flat rupees per order wherever
the plan charges one. A percentage cap and a minimum stay as the plan sets them: they are
the broker's rules, not the price.

Money is Decimal, read from strings. A YAML float is refused at load.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

import yaml

TABLE = Path(__file__).parent / "brokerage.yaml"
KINDS = ("OPT", "FUT", "EQ_INTRADAY", "EQ_DELIVERY")
_FIELDS = ("flat", "pct", "min", "min_pct")


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


def _money(value: object, where: str) -> Decimal:
    if not isinstance(value, str):
        raise InvalidPresets(f"{where}: written as a quoted string, never a YAML number")
    try:
        out = Decimal(value)
    except InvalidOperation as exc:
        raise InvalidPresets(f"{where}: {value!r} is not a number") from exc
    if not out.is_finite() or out < 0:
        raise InvalidPresets(f"{where}: can't be {value}")
    return out


def load(path: Path = TABLE) -> dict[str, Preset]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    out: dict[str, Preset] = {}
    for broker, raw in (doc.get("brokers") or {}).items():
        where = f"broker {broker!r}"
        for key in ("name", "read_on", "source"):
            if not isinstance(raw.get(key), str) or not raw[key].strip():
                raise InvalidPresets(f"{where}: needs a {key}")
        plans: dict[str, Plan] = {}
        for kind, plan in (raw.get("plans") or {}).items():
            if kind not in KINDS:
                raise InvalidPresets(f"{where}: {kind!r} is not one of {KINDS}")
            unknown = set(plan) - set(_FIELDS)
            if unknown or "flat" not in plan:
                raise InvalidPresets(f"{where} {kind}: fields are {_FIELDS}, flat required")
            plans[kind] = Plan(**{k: _money(v, f"{where} {kind} {k}") for k, v in plan.items()})
        out[broker] = Preset(broker, raw["name"].strip(), raw["read_on"].strip(),
                             raw["source"].strip(), plans)
    return out


_LOADED: dict[str, Preset] | None = None


def presets() -> dict[str, Preset]:
    global _LOADED
    if _LOADED is None:
        _LOADED = load()
    return _LOADED


def preset(broker: str) -> Preset:
    try:
        return presets()[broker]
    except KeyError:
        raise UnknownBroker(f"no brokerage preset for {broker!r}") from None


def per_order(broker: str, kind: str, value: Decimal, *, own: Decimal | None = None) -> Decimal:
    """Brokerage on one executed order of ``value``, unrounded.

    ``own`` is the trader's own rupees per order, which replaces the plan's flat figure
    wherever the plan charges one.
    """
    try:
        plan = preset(broker).plans[kind]
    except KeyError:
        if broker in presets():
            raise UnknownBroker(f"{broker!r} has no {kind} plan") from None
        raise
    flat = own if (own is not None and plan.flat > 0) else plan.flat
    fee = min(flat, plan.pct * value) if plan.pct is not None else flat
    if plan.min is not None and fee < plan.min:
        floor = plan.min if plan.min_pct is None else min(plan.min, plan.min_pct * value)
        fee = max(fee, floor)
    return fee
