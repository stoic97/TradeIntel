"""
Cycle 1 — the Canonical Trade Record (CTR), schema v1.

These tests state what a trade record must be before any broker adapter exists.
Each rule traces to Research Spec v1.0 §4.2 (contract identity, determinism),
§4.5 (typed missingness) and framework_v1.yaml `scope` (long options in, short out).

Money and prices are ``Decimal``, never float: the schema is strict (ADR 004) because
float arithmetic must not decide a trader-facing number (§6.5). A float price is
refused, and `test_float_price_is_refused` locks that. Sub-paise precision is
allowed, because an apportioned fill produces it — see
`test_sub_paise_net_pnl_is_allowed`.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from services.shared.schemas.ctr_v1 import (
    SCHEMA_VERSION,
    Direction,
    Fill,
    OptionType,
    RiskUnitSource,
    RoundTrip,
    Segment,
    Side,
    UnsupportedInV1,
)

IST = ZoneInfo("Asia/Kolkata")
T0 = datetime(2026, 9, 1, 10, 5, 0, tzinfo=IST)


def make_fill(**overrides):
    base = {
        "trader_id": "T01",
        "broker": "zerodha",
        "ts": T0,
        "exchange": "MCX",
        "segment": Segment.OPT,
        "symbol": "CRUDEOILM",
        "expiry": date(2026, 9, 17),
        "option_type": OptionType.CE,
        "strike": Decimal(5500),
        "side": Side.BUY,
        "quantity": 100,
        "price": Decimal("42.5"),
        "product": "INTRADAY",
        "raw_hash": "a" * 64,
    }
    base.update(overrides)
    return Fill(**base)


def make_trip(**overrides):
    base = {
        "trader_id": "T01",
        "broker": "zerodha",
        "exchange": "MCX",
        "segment": Segment.OPT,
        "symbol": "CRUDEOILM",
        "expiry": date(2026, 9, 17),
        "option_type": OptionType.CE,
        "strike": Decimal(5500),
        "direction": Direction.LONG,
        "entry_ts": T0,
        "exit_ts": T0 + timedelta(minutes=40),
        "quantity": 100,
        "entry_price": Decimal("42.5"),
        "exit_price": Decimal(38),
        "gross_pnl": Decimal(-450),
        "fees": Decimal(35),
        "fill_ids": ["f1", "f2"],
    }
    base.update(overrides)
    return RoundTrip(**base)


# ---------------------------------------------------------------- identity

def test_schema_version_is_v1():
    assert SCHEMA_VERSION == "ctr_v1"


def test_fill_id_is_deterministic_and_sensitive_to_content():
    a, b = make_fill(), make_fill()
    assert a.fill_id == b.fill_id
    assert len(a.fill_id) == 16
    assert make_fill(price=Decimal("42.6")).fill_id != a.fill_id


def test_trip_id_is_deterministic():
    assert make_trip().trip_id == make_trip().trip_id


# ---------------------------------------------------------------- fills: what is refused

def test_fill_rejects_naive_timestamp():
    with pytest.raises(ValidationError, match="timezone"):
        make_fill(ts=datetime(2026, 9, 1, 10, 5, 0))  # noqa: DTZ001 - naive on purpose


def test_derivative_fill_requires_expiry():
    with pytest.raises(ValidationError, match="expiry"):
        make_fill(expiry=None)


def test_option_fill_requires_type_and_strike():
    with pytest.raises(ValidationError, match="option_type"):
        make_fill(option_type=None)
    with pytest.raises(ValidationError, match="strike"):
        make_fill(strike=None)


def test_equity_fill_needs_no_contract_fields():
    f = make_fill(segment=Segment.EQ, exchange="NSE", symbol="RELIANCE",
                  expiry=None, option_type=None, strike=None)
    assert f.expiry is None


def test_fill_rejects_non_positive_quantity_and_price():
    with pytest.raises(ValidationError):
        make_fill(quantity=0)
    with pytest.raises(ValidationError):
        make_fill(price=Decimal(0))


# ---------------------------------------------------------------- round trips: R and scope

def test_net_pnl_is_gross_minus_fees():
    assert make_trip().net_pnl == Decimal(-485)


def test_long_option_risk_unit_is_premium_paid():
    t = make_trip()
    assert t.risk_unit == Decimal(4250)
    assert t.risk_unit_source == RiskUnitSource.PREMIUM_PAID
    assert t.r_multiple == Decimal(-485) / Decimal(4250)


def test_short_option_is_unsupported_in_v1():
    with pytest.raises(UnsupportedInV1, match="short option"):
        make_trip(direction=Direction.SHORT)


def test_futures_without_risk_unit_has_no_r_and_says_so():
    t = make_trip(segment=Segment.FUT, option_type=None, strike=None,
                  entry_price=Decimal(5500), exit_price=Decimal(5480),
                 gross_pnl=Decimal(-2000))
    assert t.risk_unit is None
    assert t.risk_unit_source == RiskUnitSource.UNKNOWN
    assert t.r_multiple is None


def test_futures_with_recorded_stop_risk_unit():
    t = make_trip(segment=Segment.FUT, option_type=None, strike=None,
                  entry_price=Decimal(5500), exit_price=Decimal(5480),
                 gross_pnl=Decimal(-2000), risk_unit=Decimal(3000),
                 risk_unit_source=RiskUnitSource.RECORDED_STOP)
    assert t.r_multiple == Decimal(-2035) / Decimal(3000)


def test_exit_before_entry_is_rejected():
    with pytest.raises(ValidationError, match="exit_ts"):
        make_trip(exit_ts=T0 - timedelta(minutes=1))


# ---------------------------------------------------------------- strictness

def test_float_price_is_refused():
    """Strict mode (ADR 004): no float may become a price. §6.5."""
    with pytest.raises(ValidationError, match="Decimal"):
        make_fill(price=42.5)


def test_extra_field_is_refused():
    """extra='forbid': a schema that silently accepts an unknown field accepts a bug."""
    with pytest.raises(ValidationError):
        make_fill(unexpected_column="x")


def test_sub_paise_net_pnl_is_allowed():
    """A fill apportioned across trips carries sub-paise precision, legitimately.

    An earlier version refused it. Rikk's real history broke that rule within
    minutes: an aggregated fill of 30 units totalling 4595.50 has a per-unit price
    of 153.18333..., so a trip matching part of it owns a fraction of a paisa.
    Decimal arithmetic is exact; rounding happens at the presentation boundary.
    """
    t = make_trip(gross_pnl=Decimal("-450.001"))
    assert t.net_pnl == Decimal("-485.001")
