"""The vocabulary every Scope v1 module keys off.

Each test fixes a count as well as the members, because the PRD's rules are about
exhaustiveness: "three import outcomes, never a fourth" (section 5.3), "all seven
result states exist from day one, v1 emits four" (section 8). A test that only
checked membership would pass while a fourth state was quietly added.
"""

from __future__ import annotations

from enum import Enum

import pytest

from services.shared.schemas import scope_v1 as s

ALL_ENUMS = [
    s.ResultState,
    s.ImportOutcome,
    s.RowFlag,
    s.DayDiff,
    s.CapturePhase,
    s.RiskUnitSourceV1,
    s.JournalUnit,
    s.ConsentPurpose,
]


def names(enum_cls: type[Enum]) -> set[str]:
    return {m.name for m in enum_cls}


def test_result_state_has_all_seven_and_names_the_four_v1_emits():
    assert names(s.ResultState) == {
        "COUNTED_FACT",
        "INSUFFICIENT_SAMPLE",
        "REQUIRED_DATA_MISSING",
        "NOT_YET_TESTED",
        "VALIDATED_FINDING",
        "NO_EFFECT_ABOVE_THRESHOLD",
        "COULD_NOT_COMPUTE",
    }
    assert s.V1_EMITTABLE_STATES == {
        s.ResultState.COUNTED_FACT,
        s.ResultState.INSUFFICIENT_SAMPLE,
        s.ResultState.REQUIRED_DATA_MISSING,
        s.ResultState.NOT_YET_TESTED,
    }


def test_import_outcome_has_exactly_three():
    assert names(s.ImportOutcome) == {
        "REJECTED",
        "ACCEPTED_WITH_EXCLUSIONS",
        "ACCEPTED_PARTIAL_FIELDS",
    }


def test_row_flag_has_exactly_the_three_duplicate_tiers():
    assert names(s.RowFlag) == {
        "DUPLICATE_FILL_ID",
        "SUSPECTED_DUPLICATE",
        "TRADER_CONFIRMED_DUPLICATE",
    }


def test_day_diff_has_three():
    assert names(s.DayDiff) == {"IDENTICAL", "GROWN", "SHRUNK"}


def test_capture_phase_has_three():
    assert names(s.CapturePhase) == {"BEFORE_ENTRY", "DURING_TRADE", "AFTER_CLOSE"}


def test_risk_unit_source_has_five_and_only_two_may_be_denominators_on_screen():
    assert names(s.RiskUnitSourceV1) == {
        "DECLARED_BUDGET",
        "DEFINED_STOP",
        "PREMIUM_PAID",
        "INFERRED_ATR",
        "UNAVAILABLE",
    }
    assert s.SHOWABLE_DENOMINATORS == {
        s.RiskUnitSourceV1.DECLARED_BUDGET,
        s.RiskUnitSourceV1.DEFINED_STOP,
    }


def test_journal_unit_has_day_week_and_per_n_trips():
    assert names(s.JournalUnit) == {"DAY", "WEEK", "PER_N_TRIPS"}


def test_consent_purpose_has_the_thesis_six_plus_engine_testing():
    assert names(s.ConsentPurpose) == {
        "DIAGNOSIS",
        "RETAIN_MODEL",
        "POPULATION_PRIORS",
        "PUBLISHED_RESEARCH",
        "THIRD_PARTY_SUMMARY",
        "MARKETING",
        "ENGINE_TESTING",
    }


@pytest.mark.parametrize("enum_cls", ALL_ENUMS)
def test_every_enum_is_a_str_enum_whose_value_is_its_lowercase_name(enum_cls):
    assert issubclass(enum_cls, str)
    for member in enum_cls:
        assert member.value == member.name.lower()


@pytest.mark.parametrize("enum_cls", ALL_ENUMS)
def test_no_enum_mentions_archetype(enum_cls):
    for member in enum_cls:
        assert "archetype" not in member.name.lower()
        assert "archetype" not in member.value.lower()
