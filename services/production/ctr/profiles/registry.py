"""Instrument profiles: the instrument-specific facts, as versioned data.

PRD v1.2 section 9 requires contract multiplier, tick size, currency per point,
expiry rule, session boundaries and timezone to be per instrument, versioned, and
never hard-coded, and requires every import to record the profile versions it used.

Nothing is defaulted. A profile missing a field, carrying a float where money
belongs, or naming an expiry rule the code does not implement raises
:class:`InvalidProfile` at load time -- at startup, where it is visible, rather than
inside a reconstruction where it would become a wrong rupee figure that looks right.

Money is ``Decimal`` and is read from YAML **strings**, because a YAML float has
already lost precision by the time this module sees it (``ctr_v1``: no float
arithmetic decides a trader-facing number).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

KNOWN_EXPIRY_RULES: frozenset[str] = frozenset(
    {
        # The contract's expiry is written in the instrument name in the export and is
        # parsed by the adapter; the profile records that this is how it arrives.
        "from_instrument_name",
        # MCX crude futures expire on the 19th of the contract month, or the previous
        # working day when the 19th is a holiday. Declared here, implemented when a
        # futures history needs it; no caller may assume it before then.
        "monthly_day_19",
        # Cash equity and anything else with no expiry.
        "none",
    }
)

_REQUIRED = (
    "exchange",
    "symbol",
    "version",
    "contract_multiplier",
    "tick_size",
    "currency_per_point",
    "currency",
    "timezone",
    "session_start",
    "session_end",
    "expiry_rule",
)


class InvalidProfile(Exception):
    """A profile file the loader refuses. Raised at load time, never at use time."""


class UnknownInstrument(Exception):
    """No profile for this exchange and symbol. Never defaulted (PRD section 9)."""


# A profile whose symbol is this covers every instrument on its exchange in the
# segment it names. It is not a default: it is used only where the facts really are
# the segment's and not any one symbol's -- NSE cash equity, where every share is one
# unit, one rupee per point, no expiry, one IST session. A derivative never resolves
# to it, because its lot size and expiry are the contract's own.
SEGMENT_WILDCARD = "*"
KNOWN_SEGMENTS: frozenset[str] = frozenset({"EQ", "FUT", "OPT"})


@dataclass(frozen=True)
class InstrumentProfile:
    """One instrument's facts, at one version."""

    exchange: str
    symbol: str
    version: str
    contract_multiplier: Decimal
    tick_size: Decimal
    currency_per_point: Decimal
    currency: str
    timezone_name: str
    session_start: time
    session_end: time
    expiry_rule: str
    # Set only on a segment profile (symbol == SEGMENT_WILDCARD): which segment's
    # instruments it covers. None on an ordinary, single-instrument profile.
    segment: str | None = None

    @property
    def key(self) -> tuple[str, str]:
        return (self.exchange, self.symbol)

    @property
    def covers_segment(self) -> bool:
        return self.symbol == SEGMENT_WILDCARD

    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_name)


def _decimal_from_string(raw: Any, field: str, where: str) -> Decimal:
    if not isinstance(raw, str):
        raise InvalidProfile(
            f"{where}: {field} must be a quoted string, not {type(raw).__name__} -- "
            "a YAML float has already lost precision (ctr_v1: money is Decimal)"
        )
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise InvalidProfile(f"{where}: {field} is not a number: {raw!r}") from exc
    if value <= 0:
        raise InvalidProfile(f"{where}: {field} must be positive, got {value}")
    return value


def _time_from_string(raw: Any, field: str, where: str) -> time:
    if not isinstance(raw, str):
        raise InvalidProfile(f"{where}: {field} must be a quoted HH:MM string")
    try:
        hour, minute = (int(part) for part in raw.split(":"))
        return time(hour, minute)
    except ValueError as exc:
        raise InvalidProfile(f"{where}: {field} is not HH:MM: {raw!r}") from exc


def load_one(path: Path) -> InstrumentProfile:
    """Parse one profile file, refusing anything incomplete or imprecise."""
    where = path.name
    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise InvalidProfile(f"{where}: not valid YAML") from exc
    if not isinstance(raw, dict):
        raise InvalidProfile(f"{where}: expected a mapping")

    missing = [field for field in _REQUIRED if field not in raw]
    if missing:
        raise InvalidProfile(f"{where}: missing {', '.join(missing)}")

    expiry_rule = raw["expiry_rule"]
    if expiry_rule not in KNOWN_EXPIRY_RULES:
        raise InvalidProfile(
            f"{where}: expiry_rule {expiry_rule!r} is not implemented; "
            f"known rules are {sorted(KNOWN_EXPIRY_RULES)}"
        )

    timezone_name = raw["timezone"]
    try:
        ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise InvalidProfile(f"{where}: timezone {timezone_name!r} is not an IANA zone") from exc

    session_start = _time_from_string(raw["session_start"], "session_start", where)
    session_end = _time_from_string(raw["session_end"], "session_end", where)
    if session_start >= session_end:
        raise InvalidProfile(f"{where}: session_start must precede session_end")

    version = raw["version"]
    if not isinstance(version, str) or not version:
        raise InvalidProfile(f"{where}: version must be a non-empty quoted string")

    symbol = str(raw["symbol"])
    segment = raw.get("segment")
    if symbol == SEGMENT_WILDCARD:
        if segment not in KNOWN_SEGMENTS:
            raise InvalidProfile(
                f"{where}: a profile for every symbol on an exchange must name the "
                f"segment it covers, one of {sorted(KNOWN_SEGMENTS)}"
            )
        if segment == "EQ" and expiry_rule != "none":
            raise InvalidProfile(f"{where}: cash equity has no expiry; expiry_rule must be none")
    elif segment is not None:
        raise InvalidProfile(
            f"{where}: segment is only for a profile whose symbol is {SEGMENT_WILDCARD!r}; "
            "a named instrument's segment comes from the trade, not the profile"
        )

    return InstrumentProfile(
        exchange=str(raw["exchange"]),
        symbol=symbol,
        version=version,
        contract_multiplier=_decimal_from_string(
            raw["contract_multiplier"], "contract_multiplier", where
        ),
        tick_size=_decimal_from_string(raw["tick_size"], "tick_size", where),
        currency_per_point=_decimal_from_string(
            raw["currency_per_point"], "currency_per_point", where
        ),
        currency=str(raw["currency"]),
        timezone_name=str(timezone_name),
        session_start=session_start,
        session_end=session_end,
        expiry_rule=str(expiry_rule),
        segment=None if segment is None else str(segment),
    )


def load_all(directory: Path) -> dict[tuple[str, str], InstrumentProfile]:
    """Every profile in a directory, keyed by (exchange, symbol)."""
    profiles: dict[tuple[str, str], InstrumentProfile] = {}
    for path in sorted(Path(directory).glob("*.yaml")):
        profile = load_one(path)
        if profile.key in profiles:
            raise InvalidProfile(f"{path.name}: duplicate profile for {profile.key}")
        profiles[profile.key] = profile
    return profiles


def get(
    profiles: dict[tuple[str, str], InstrumentProfile], exchange: str, symbol: str
) -> InstrumentProfile:
    try:
        return profiles[(exchange, symbol)]
    except KeyError:
        raise UnknownInstrument(
            f"no instrument profile for {exchange}:{symbol} -- add one rather than "
            "defaulting a multiplier (PRD section 9)"
        ) from None


def lookup(
    profiles: dict[tuple[str, str], InstrumentProfile],
    exchange: str,
    symbol: str,
    segment: object,
) -> InstrumentProfile | None:
    """The profile for a trade, or None when there is none to be had.

    The instrument's own profile first. Failing that, the exchange's segment
    profile, and only when the trade's segment is the one it covers: an NSE share
    resolves to NSE cash equity, an NSE option with no file of its own does not.
    ``segment`` may be the enum or its value; the stored row carries the value.
    """
    exact = profiles.get((exchange, symbol))
    if exact is not None:
        return exact
    wildcard = profiles.get((exchange, SEGMENT_WILDCARD))
    if wildcard is None:
        return None
    segment_value = getattr(segment, "value", segment)
    if wildcard.segment == segment_value:
        return wildcard
    return None


def versions_used(used: list[InstrumentProfile]) -> dict[str, str]:
    """What an import records, so its reconstruction can be reproduced later."""
    return {f"{p.exchange}:{p.symbol}": p.version for p in used}
