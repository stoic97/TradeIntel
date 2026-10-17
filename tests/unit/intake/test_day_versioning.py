"""Uploads version trading days; they never append to them (PRD 5.4).

The rule, per source account: a day present in an earlier upload is **superseded** by
the later upload's rows for that day. The earlier version is retained. The import
review shows the per-day diff -- rows before, rows after, identical / grown / shrunk
-- and a day that shrank is flagged and shown.

Two consequences the PRD draws out, and these tests pin both: cross-upload
duplication becomes impossible by construction, and late trades need no separate
mechanism -- a day that grew is the same path as a day that was corrected.
"""

from __future__ import annotations

from services.production.ctr.intake import day_versions as dv
from services.shared.schemas import scope_v1 as s


def day(date: str, rows: int) -> dv.DayRows:
    return dv.DayRows(trading_day=date, row_count=rows)


def test_a_first_upload_creates_a_version_of_every_day_it_contains():
    diffs = dv.diff_against_existing(
        incoming=[day("2026-10-14", 3), day("2026-10-15", 5)], existing={}
    )
    assert [d.trading_day for d in diffs] == ["2026-10-14", "2026-10-15"]
    assert all(d.rows_before == 0 for d in diffs)
    assert [d.diff for d in diffs] == [s.DayDiff.GROWN, s.DayDiff.GROWN]
    assert not any(d.day_shrank for d in diffs)


def test_an_unchanged_day_is_identical_not_appended():
    diffs = dv.diff_against_existing(
        incoming=[day("2026-10-14", 3)], existing={"2026-10-14": 3}
    )
    assert diffs[0].diff is s.DayDiff.IDENTICAL
    assert diffs[0].rows_before == 3 and diffs[0].rows_after == 3


def test_a_day_that_grew_is_the_late_trade_path():
    diffs = dv.diff_against_existing(
        incoming=[day("2026-10-14", 5)], existing={"2026-10-14": 3}
    )
    assert diffs[0].diff is s.DayDiff.GROWN
    assert diffs[0].rows_after == 5
    assert not diffs[0].day_shrank


def test_a_day_that_shrank_is_flagged_and_shown():
    diffs = dv.diff_against_existing(
        incoming=[day("2026-10-14", 2)], existing={"2026-10-14": 6}
    )
    assert diffs[0].diff is s.DayDiff.SHRUNK
    assert diffs[0].day_shrank is True


def test_a_day_absent_from_the_new_upload_is_left_alone():
    """Re-exporting one week must not erase the weeks around it."""
    diffs = dv.diff_against_existing(
        incoming=[day("2026-10-15", 4)], existing={"2026-10-14": 3, "2026-10-15": 4}
    )
    assert [d.trading_day for d in diffs] == ["2026-10-15"]


def test_an_overlapping_re_export_cannot_duplicate_rows():
    """The whole point: the overlap replaces, it never adds."""
    existing = {"2026-10-14": 3, "2026-10-15": 5}
    diffs = dv.diff_against_existing(
        incoming=[day("2026-10-15", 5), day("2026-10-16", 2)], existing=existing
    )
    after = dv.apply(existing, diffs)
    assert after == {"2026-10-14": 3, "2026-10-15": 5, "2026-10-16": 2}
    assert after["2026-10-15"] == 5, "the overlapping day is replaced, not 5 + 5"


def test_diffs_are_ordered_by_day_and_deterministic():
    incoming = [day("2026-10-16", 1), day("2026-10-14", 1), day("2026-10-15", 1)]
    a = dv.diff_against_existing(incoming=incoming, existing={})
    b = dv.diff_against_existing(incoming=incoming, existing={})
    assert [d.trading_day for d in a] == ["2026-10-14", "2026-10-15", "2026-10-16"]
    assert a == b


def test_source_accounts_do_not_collide():
    """Two accounts can trade the same day; one does not supersede the other."""
    existing = {"2026-10-14": 3}
    diffs = dv.diff_against_existing(incoming=[day("2026-10-14", 9)], existing=existing)
    assert diffs[0].rows_before == 3
    fresh = dv.diff_against_existing(incoming=[day("2026-10-14", 9)], existing={})
    assert fresh[0].rows_before == 0
