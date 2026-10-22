"""Instrument profiles: everything instrument-specific, as versioned data.

PRD v1.2 section 9: contract multiplier, tick size, currency per point, expiry rule,
session boundaries and timezone are per instrument, versioned, and **never
hard-coded**. An import records the profile versions it used, so a reconstruction can
be reproduced years later even after a profile changes.

Nothing here is defaulted. A profile missing a field is an error, because a silently
defaulted multiplier is a wrong rupee figure that looks right.
"""

from __future__ import annotations

from datetime import time
from decimal import Decimal
from pathlib import Path

import pytest

from services.production.ctr.profiles import registry as reg

PROFILE_DIR = Path("services/production/ctr/profiles")


def test_every_shipped_profile_loads_and_declares_every_field():
    profiles = reg.load_all(PROFILE_DIR)
    assert profiles, "no profiles shipped"
    for key, p in profiles.items():
        assert p.exchange and p.symbol
        assert isinstance(p.version, str) and p.version
        assert isinstance(p.contract_multiplier, Decimal) and p.contract_multiplier > 0
        assert isinstance(p.tick_size, Decimal) and p.tick_size > 0
        assert isinstance(p.currency_per_point, Decimal) and p.currency_per_point > 0
        assert p.currency in {"INR", "USD"}
        assert isinstance(p.session_start, time) and isinstance(p.session_end, time)
        assert p.session_start < p.session_end
        assert p.expiry_rule in reg.KNOWN_EXPIRY_RULES
        assert key == (p.exchange, p.symbol)


def test_the_three_shipped_profiles_cover_mcx_nse_and_a_us_exchange():
    profiles = reg.load_all(PROFILE_DIR)
    exchanges = {ex for ex, _ in profiles}
    assert {"MCX", "NSE"} <= exchanges
    non_ist = [p for p in profiles.values() if p.timezone_name != "Asia/Kolkata"]
    assert non_ist, "a non-IST profile must exist: PRD section 2 names a US futures history"
    assert any(p.currency == "USD" for p in non_ist)


def test_timezone_resolves_and_ist_profiles_share_one_zone():
    profiles = reg.load_all(PROFILE_DIR)
    for p in profiles.values():
        assert p.timezone().utcoffset is not None
    ist = {p.timezone_name for p in profiles.values() if p.exchange in {"MCX", "NSE", "BSE"}}
    assert ist == {"Asia/Kolkata"}, "Indian exchanges share one IST day (PRD section 7.2)"


def test_lookup_by_exchange_and_symbol():
    profiles = reg.load_all(PROFILE_DIR)
    p = reg.get(profiles, "MCX", "CRUDEOIL")
    assert p.exchange == "MCX" and p.symbol == "CRUDEOIL"


def test_an_unknown_instrument_raises_rather_than_defaulting():
    profiles = reg.load_all(PROFILE_DIR)
    with pytest.raises(reg.UnknownInstrument):
        reg.get(profiles, "MCX", "NOTATHING")


def test_versions_used_is_reportable_for_the_import_record():
    profiles = reg.load_all(PROFILE_DIR)
    used = reg.versions_used([reg.get(profiles, "MCX", "CRUDEOIL")])
    assert used == {"MCX:CRUDEOIL": reg.get(profiles, "MCX", "CRUDEOIL").version}


def test_a_profile_missing_a_field_is_an_error(tmp_path):
    (tmp_path / "MCX_BROKEN.yaml").write_text(
        "exchange: MCX\nsymbol: BROKEN\nversion: '1'\ncontract_multiplier: '1'\n"
    )
    with pytest.raises(reg.InvalidProfile):
        reg.load_all(tmp_path)


def test_an_unknown_expiry_rule_is_an_error(tmp_path, ):
    good = (PROFILE_DIR / "MCX_CRUDEOIL.yaml").read_text()
    broken = good.replace("symbol: CRUDEOIL", "symbol: X").replace(
        "expiry_rule: from_instrument_name", "expiry_rule: whatever_i_feel_like"
    )
    assert "whatever_i_feel_like" in broken, "the corruption did not apply; this test would be vacuous"
    (tmp_path / "MCX_X.yaml").write_text(broken)
    with pytest.raises(reg.InvalidProfile):
        reg.load_all(tmp_path)


def test_money_fields_are_never_floats(tmp_path):
    """ctr_v1 keeps all money in Decimal; a float here would leak into a rupee figure."""
    good = (PROFILE_DIR / "MCX_CRUDEOIL.yaml").read_text()
    broken = good.replace('symbol: CRUDEOIL', 'symbol: Y').replace(
        'tick_size: "1"', "tick_size: 1.1"
    )
    assert "tick_size: 1.1" in broken, "the corruption did not apply; this test would be vacuous"
    (tmp_path / "MCX_Y.yaml").write_text(broken)
    with pytest.raises(reg.InvalidProfile):
        reg.load_all(tmp_path)


def test_nse_cash_equity_is_covered_as_a_segment_not_a_default():
    """Every NSE share is one unit, one rupee a point, no expiry, one IST session."""
    profiles = reg.load_all(PROFILE_DIR)
    p = reg.lookup(profiles, "NSE", "Jio Financial Services", "EQ")
    assert p is not None and p.covers_segment and p.segment == "EQ"
    assert p.contract_multiplier == Decimal("1") and p.currency_per_point == Decimal("1")
    assert p.expiry_rule == "none" and p.timezone_name == "Asia/Kolkata"
    assert reg.versions_used([p]) == {"NSE:*": p.version}


def test_a_segment_profile_never_resolves_a_derivative():
    """An NSE option with no file of its own stays unknown: its lot size is its own."""
    profiles = reg.load_all(PROFILE_DIR)
    assert reg.lookup(profiles, "NSE", "BANKNIFTY", "OPT") is None
    assert reg.lookup(profiles, "NSE", "BANKNIFTY", "FUT") is None
    assert reg.lookup(profiles, "MCX", "NOTATHING", "EQ") is None


def test_a_named_profile_wins_over_the_segment_profile():
    profiles = reg.load_all(PROFILE_DIR)
    p = reg.lookup(profiles, "NSE", "NIFTY", "OPT")
    assert p is not None and p.symbol == "NIFTY"


def test_lookup_accepts_the_segment_enum_as_well_as_its_value():
    from services.shared.schemas.ctr_v1 import Segment

    profiles = reg.load_all(PROFILE_DIR)
    assert reg.lookup(profiles, "NSE", "ANYSHARE", Segment.EQ) is not None
    assert reg.lookup(profiles, "NSE", "ANYSHARE", Segment.OPT) is None


def test_a_segment_profile_must_name_its_segment(tmp_path):
    good = (PROFILE_DIR / "NSE_EQUITY.yaml").read_text()
    broken = "\n".join(line for line in good.splitlines() if not line.startswith("segment:"))
    assert "segment:" not in broken
    (tmp_path / "NSE_EQUITY.yaml").write_text(broken)
    with pytest.raises(reg.InvalidProfile):
        reg.load_all(tmp_path)


def test_a_named_instrument_may_not_carry_a_segment(tmp_path):
    good = (PROFILE_DIR / "MCX_CRUDEOIL.yaml").read_text()
    (tmp_path / "MCX_CRUDEOIL.yaml").write_text(good + "segment: FUT\n")
    with pytest.raises(reg.InvalidProfile):
        reg.load_all(tmp_path)


def test_a_cash_equity_segment_profile_cannot_declare_an_expiry(tmp_path):
    good = (PROFILE_DIR / "NSE_EQUITY.yaml").read_text()
    broken = good.replace("expiry_rule: none", "expiry_rule: monthly_day_19")
    assert "monthly_day_19" in broken
    (tmp_path / "NSE_EQUITY.yaml").write_text(broken)
    with pytest.raises(reg.InvalidProfile):
        reg.load_all(tmp_path)
