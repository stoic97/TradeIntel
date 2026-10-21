"""The import pipeline, as a pure decision (PRD 5.2-5.4, 9).

``plan_import`` takes the file and what already exists, and returns everything that
should happen: the outcome, every row with its status and flag, the day diffs, the
reconstruction, and the versions that produced it. It touches no database and no
disk, so the pipeline's behaviour is testable without either -- and the
reproducibility test compares one digest instead of crawling nineteen tables.

Persistence is step two; this is the decision.
"""

from __future__ import annotations

from pathlib import Path

from services.production.ctr.intake import pipeline as pl
from services.shared.schemas import scope_v1 as s

DUPES = Path("data/fixtures/duplicates")
PNL_LIKE = "Symbol,Realised P&L,Unrealised P&L\nWIDGETOIL,1500.00,0.00\n"

CONTEXT = pl.ImportContext(
    trader_id="fixture",
    source_account="A",
    code_version="testsha",
    existing_days={},
    export_date="2026-10-17",
    export_date_source="trader",
)


def plan(name: str, **overrides: object) -> pl.ImportPlan:
    text = (DUPES / name).read_text()
    context = CONTEXT if not overrides else pl.ImportContext(**{**CONTEXT.__dict__, **overrides})
    return pl.plan_import(text, context=context)


def test_a_wrong_file_is_rejected_and_nothing_else_is_computed():
    result = pl.plan_import(PNL_LIKE, context=CONTEXT)
    assert result.outcome is s.ImportOutcome.REJECTED
    assert result.rejection_text
    assert result.rows == ()
    assert result.trips == ()
    assert result.day_diffs == ()


def test_a_clean_file_reconstructs_and_accounts_for_every_row():
    """A clean Dhan file is ACCEPTED_PARTIAL_FIELDS, not exclusions.

    The Dhan export has no charges column, so `fees` is a missing field on every
    Dhan import (TD-002). Nothing is excluded, so the precedence rule in
    definitions_v1.md section 4 gives partial fields. Until fees are resolved, no
    Dhan import can be anything else -- which is the honest state, not a defect.
    """
    result = plan("clean.csv")
    assert result.outcome is s.ImportOutcome.ACCEPTED_PARTIAL_FIELDS
    assert result.rows_excluded == 0
    assert result.rows_in == 4
    assert result.rows_parsed + result.rows_excluded == result.rows_in
    assert result.trips, "two buys and two sells make round trips"


def test_fees_absent_is_recorded_and_never_imputed():
    result = plan("clean.csv")
    assert result.fees_available is False
    assert "fees" in result.missing_fields
    assert all(t.fees == 0 for t in result.trips)


def test_identical_rows_are_flagged_not_dropped():
    result = plan("repeated_legitimate_fills.csv")
    flagged = [r for r in result.rows if r.flag is s.RowFlag.SUSPECTED_DUPLICATE]
    assert len(flagged) == 4
    assert result.rows_excluded == 0, "a flag is not an exclusion"


def test_the_plan_records_every_version_that_produced_it():
    result = plan("clean.csv")
    assert result.code_version == "testsha"
    assert result.adapter_id == "dhan_tradebook_v1"
    assert result.adapter_version
    assert result.filemap_version
    assert isinstance(result.profile_versions, dict)


def test_day_diffs_are_computed_against_what_exists():
    first = plan("clean.csv")
    days = {d.trading_day: d.rows_after for d in first.day_diffs}
    assert days, "the file covers at least one trading day"
    again = plan("clean.csv", existing_days=days)
    assert all(d.diff is s.DayDiff.IDENTICAL for d in again.day_diffs)


def test_the_same_file_plans_identically_twice():
    """Methodology Rule 4: same input, same code, same bytes out."""
    a = plan("duplicated_block.csv")
    b = plan("duplicated_block.csv")
    assert a.digest() == b.digest()


def test_a_different_file_plans_differently():
    assert plan("clean.csv").digest() != plan("duplicated_block.csv").digest()


def test_the_digest_ignores_wall_clock_time():
    """A digest that moved with the clock would make reproducibility untestable."""
    a = plan("clean.csv")
    b = plan("clean.csv", code_version="testsha")
    assert a.digest() == b.digest()


def test_a_checked_file_map_lets_a_real_file_be_planned_in_production():
    """TD-024 closed 21 Oct 2026: the Dhan map was checked against Dhan.

    This asserted the refusal until then, and the refusal was right while the map
    was a guess -- a rejection built from a guessed map sends a trader to the
    wrong export. The gate has not gone anywhere; it is tested on an unchecked
    map in tests/unit/shared/test_file_maps.py. What changed is that this
    broker's map is no longer one.
    """
    text = (DUPES / "clean.csv").read_text()
    result = pl.plan_import(text, context=CONTEXT, production=True)
    assert result.outcome is not s.ImportOutcome.REJECTED


def test_a_file_matching_no_adapter_is_rejected_even_in_production():
    result = pl.plan_import(PNL_LIKE, context=CONTEXT, production=True)
    assert result.outcome is s.ImportOutcome.REJECTED


def test_the_day_diff_counts_rows_not_trips():
    """A day's size is its rows, because that is what the trader sent.

    Found 17 Oct 2026 on the review page: the duplicated-block fixture has six rows
    on one day that reconstruct to two round trips, and the day table reported
    'after 2'. Two harms, the second worse than the first. He cannot reconcile the
    number against his own file. And the diff that detects a shrinking day is then
    computed on trips, so a day whose rows fell from six to four could reconstruct
    to two trips either way and be reported IDENTICAL -- a silent loss, which is the
    one thing day versioning exists to prevent.
    """
    result = plan("duplicated_block.csv")
    assert result.rows_in == 6
    assert len(result.trips) == 2, "the fixture must have more rows than trips"

    by_day = {d.trading_day: d for d in result.day_diffs}
    assert len(by_day) == 1
    only_day = next(iter(by_day.values()))
    assert only_day.rows_after == 6, "rows, not trips"


def test_a_day_that_loses_rows_shrinks_even_when_the_trips_match():
    """The case the trip count would hide."""
    six_rows = plan("duplicated_block.csv")
    day = six_rows.day_diffs[0].trading_day

    text = (DUPES / "duplicated_block.csv").read_text().splitlines()
    fewer = "\n".join([text[0], *text[1:5]]) + "\n"
    shrunk = pl.plan_import(
        fewer,
        context=pl.ImportContext(
            trader_id="fx", source_account="A", code_version="testsha",
            existing_days={day: 6},
        ),
    )
    assert shrunk.day_diffs[0].rows_after == 4
    assert shrunk.day_diffs[0].diff is s.DayDiff.SHRUNK
    assert shrunk.day_diffs[0].day_shrank is True
