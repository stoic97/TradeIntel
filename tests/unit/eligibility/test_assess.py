"""Eligibility: what we tell a trader his history can and cannot support.

The page this feeds is the first thing a trader reads (PRD 5.6), and it is the
product's own account of its limits, so the states have to mean what section 8
says they mean. In particular `INSUFFICIENT_SAMPLE` and `NOT_YET_TESTED` must
never read as a clean bill of health, and neither may be reached by a guess.

Three answers, kept apart on purpose:

* a count of the thing the test needs -- B2's condition, or a plain total;
* a floor the test cannot run below whatever its condition is;
* no count at all, said plainly, for minimums written per bucket or per cell.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from services.production.eligibility import assess as el
from services.production.mirror.metrics import Trip
from services.shared.prereg import reader
from services.shared.prereg.reader import Unit
from services.shared.schemas import scope_v1 as s

FIXTURE = Path("tests/fixtures/mirror_contract/main.json")


def contract_trips() -> list[Trip]:
    """The 40-trip history every Mirror figure is checked against."""
    return [
        Trip(
            trip_id=row["trip_id"],
            trading_day=row["trading_day"],
            entry_ts=datetime.fromisoformat(row["entry_ts"]),
            exit_ts=datetime.fromisoformat(row["exit_ts"]),
            holding_seconds=int(row["holding_seconds"]),
            net=Decimal(str(row["net"])),
            lots=int(row["lots"]),
            risk_unit_source=s.RiskUnitSourceV1(row["risk_unit_source"]),
        )
        for row in json.loads(FIXTURE.read_text())
    ]


@pytest.fixture()
def eligibility():
    return el.assess(contract_trips())


def test_every_check_in_the_library_gets_an_answer(eligibility):
    """Silence about a check is the one thing section 5.6 cannot do."""
    framework = reader.load()
    assert eligibility.total == len(framework.tests)
    assert {v.test.id for v in eligibility.verdicts} == {
        t.id for t in framework.tests}


def test_every_state_is_one_v1_may_emit(eligibility):
    for verdict in eligibility.verdicts:
        assert verdict.state in s.V1_EMITTABLE_STATES, verdict.test.id
        assert verdict.state is not s.ResultState.COUNTED_FACT, (
            "eligibility is about what can be run, not about a counted figure"
        )


def test_b2_is_counted_exactly_and_falls_short_on_this_history(eligibility):
    """40 trades is a small history, and the honest answer is that it is small.

    B2 needs 30 trades meeting its condition and 60 that do not. This fixture has
    17 and 7 -- the same 17 the Mirror shows, because both ask the same function.
    """
    b2 = next(v for v in eligibility.verdicts if v.test.id == "B2")
    assert b2.basis is el.Basis.OWN_COUNT
    assert b2.have == 17
    assert b2.state is s.ResultState.INSUFFICIENT_SAMPLE
    assert "17" in b2.reason and "30" in b2.reason


def test_a_plain_total_is_counted_against_its_own_minimum(eligibility):
    """S11 wants 200 trips; this history has 40."""
    s11 = next(v for v in eligibility.verdicts if v.test.id == "S11")
    assert s11.basis is el.Basis.OWN_COUNT
    assert (s11.have, s11.need) == (40, 200)
    assert s11.state is s.ResultState.INSUFFICIENT_SAMPLE


def test_a_day_minimum_counts_days_not_trades(eligibility):
    """B5 wants 40 trading days. The fixture has eight, not forty."""
    b5 = next(v for v in eligibility.verdicts if v.test.id == "B5")
    assert b5.unit is Unit.DAYS
    assert (b5.have, b5.need) == (8, 40)
    assert b5.state is s.ResultState.INSUFFICIENT_SAMPLE


def test_a_test_needing_tick_data_says_so_rather_than_counting(eligibility):
    for test_id in ("E2", "E4p"):
        verdict = next(v for v in eligibility.verdicts if v.test.id == test_id)
        assert verdict.state is s.ResultState.REQUIRED_DATA_MISSING
        assert verdict.have is None, "nothing was counted, so nothing is shown"
        assert "tick" in verdict.reason and "TD-004" in verdict.reason


def test_a_test_needing_a_stop_order_says_which_field_is_absent(eligibility):
    r7 = next(v for v in eligibility.verdicts if v.test.id == "R7")
    assert r7.state is s.ResultState.REQUIRED_DATA_MISSING
    assert "stop" in r7.reason and "TD-003" in r7.reason


def test_a_test_needing_regime_labels_or_a_calendar_names_which(eligibility):
    s5 = next(v for v in eligibility.verdicts if v.test.id == "S5")
    assert s5.state is s.ResultState.REQUIRED_DATA_MISSING
    assert "regime" in s5.reason and "TD-011" in s5.reason

    s10 = next(v for v in eligibility.verdicts if v.test.id == "S10")
    assert s10.state is s.ResultState.REQUIRED_DATA_MISSING
    assert "calendar" in s10.reason and "TD-014" in s10.reason


def test_a_minimum_per_bucket_is_not_counted_and_does_not_pretend_to_be(eligibility):
    s1 = next(v for v in eligibility.verdicts if v.test.id == "S1")
    assert s1.basis is el.Basis.NOT_COUNTED
    assert s1.have is None
    assert "30/bucket" in s1.reason


def test_a_floor_is_reported_as_a_floor_not_as_the_tests_own_count():
    """The distinction that keeps the page honest.

    R2 needs 30 condition and 30 comparison trades. This product does not
    implement R2's condition, so it cannot say how many trades meet it. What it
    can say is that 60 trades is the least the test could possibly need, and 40
    is below that -- certain, without knowing the condition at all.
    """
    verdicts = el.assess(contract_trips()).verdicts
    r2 = next(v for v in verdicts if v.test.id == "R2")
    assert r2.basis is el.Basis.POPULATION_FLOOR
    assert (r2.have, r2.need) == (40, 60)
    assert r2.state is s.ResultState.INSUFFICIENT_SAMPLE


def test_above_the_floor_the_page_says_the_engine_decides():
    """A bigger history clears the floor, and the honest answer changes shape.

    It does not become "this check will run". It becomes "nothing here rules it
    out", because the condition is still the engine's to count.
    """
    one_day = contract_trips()[:1][0]
    many = [
        Trip(trip_id=f"t{n:04d}", trading_day=f"2026-09-{(n % 28) + 1:02d}",
             entry_ts=one_day.entry_ts, exit_ts=one_day.exit_ts,
             holding_seconds=one_day.holding_seconds,
             net=Decimal(100) if n % 2 else Decimal(-100),
             lots=1, risk_unit_source=one_day.risk_unit_source)
        for n in range(400)
    ]
    r2 = next(v for v in el.assess(many).verdicts if v.test.id == "R2")
    assert r2.state is s.ResultState.NOT_YET_TESTED
    assert r2.basis is el.Basis.POPULATION_FLOOR
    assert "engine" in r2.reason


def test_nothing_reads_as_a_clean_bill_of_health(eligibility):
    """Section 8: the absence of a finding is never evidence of good trading."""
    words = " ".join(v.reason for v in eligibility.verdicts).lower()
    for claim in ("no problem", "fine", "healthy", "good", "clean", "passed"):
        assert claim not in words, claim


def test_an_empty_history_runs_nothing_and_says_why():
    """No trades, no checks -- including the ones this page does not count.

    The first version let S1 and C1 through here. Their minimums are written per
    bucket and per cell, so the counting branch returned nothing and the verdict
    fell through to "nothing rules this out" on a history of zero trades. A
    minimum of 30 in each bucket still needs 30 trades in total, and that floor
    now applies to every test with a minimum at all.
    """
    nothing = el.assess([])
    assert nothing.runnable == (), [v.test.id for v in nothing.runnable]
    assert len(nothing.blocked) == nothing.total
    for verdict in nothing.blocked:
        assert verdict.reason, f"{verdict.test.id} is blocked without saying why"


def test_a_check_we_cannot_count_is_not_counted_as_enough(eligibility):
    """The distinction the page got wrong until someone read it.

    S1 and C1 have minimums written per bucket and per cell. This history clears
    the floor in trades, so nothing rules them out -- but nothing establishes them
    either, and grouping them with the checks that genuinely have enough produced
    a headline saying two checks were ready, naming the only two that cannot be
    judged here.
    """
    undetermined = {v.test.id for v in eligibility.undetermined}
    assert undetermined == {"S1", "C1"}
    assert all(v.basis is el.Basis.NOT_COUNTED for v in eligibility.undetermined)

    assert eligibility.enough == (), (
        "40 trades is not enough for any check whose quantity we can count"
    )
    assert set(eligibility.runnable) == set(eligibility.enough) | set(
        eligibility.undetermined)
