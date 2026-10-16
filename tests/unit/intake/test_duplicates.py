"""Duplicate tiers. A row is never discarded on a hash alone (PRD 5.4).

Three tiers, three fixtures, named by the PRD:

* **repeated legitimate fills** -- two real fills can be byte-identical when a
  broker's timestamps are coarse. Deleting one would break the product's central
  promise that nothing disappears silently, so both are kept and flagged.
* **a duplicated block** -- the same rows pasted twice in one file. Also kept and
  flagged, because from inside the file it is indistinguishable from the case above;
  the trader is the one who can tell, and he can confirm it in one tap.
* **an overlapping re-export** -- handled across uploads by day versioning (1.7),
  not here. This file's job is to show that within one file it changes nothing.

The asymmetry is deliberate (decision list item 24): keeping inflates a duplicated
export, dropping deletes a real fill, and deletion is the irreversible wrong.
"""

from __future__ import annotations

from pathlib import Path

from services.production.ctr.intake import duplicates as dup
from services.shared.schemas import scope_v1 as s

FIXTURES = Path("data/fixtures/duplicates")


def rows(path: Path) -> list[str]:
    return path.read_text().splitlines()


def test_repeated_legitimate_fills_are_kept_and_flagged():
    result = dup.classify_file(FIXTURES / "repeated_legitimate_fills.csv", has_fill_id=False)
    assert result.excluded == [], "nothing is excluded without a fill id"
    flagged = [r for r in result.rows if r.flag is s.RowFlag.SUSPECTED_DUPLICATE]
    assert len(flagged) == 4, "two pairs of identical rows, all four kept and flagged"
    assert len({r.dup_group for r in flagged}) == 2, "one group per set of identical rows"
    assert result.kept_count == len(rows(FIXTURES / "repeated_legitimate_fills.csv")) - 1


def test_a_duplicated_block_is_kept_and_flagged_not_dropped():
    result = dup.classify_file(FIXTURES / "duplicated_block.csv", has_fill_id=False)
    assert result.excluded == []
    flagged = [r for r in result.rows if r.flag is s.RowFlag.SUSPECTED_DUPLICATE]
    assert len(flagged) == 6, "a three-row block appearing twice flags all six"
    assert len({r.dup_group for r in flagged}) == 3


def test_a_file_with_no_repeats_flags_nothing():
    result = dup.classify_file(FIXTURES / "clean.csv", has_fill_id=False)
    assert all(r.flag is None for r in result.rows)
    assert result.excluded == []


def test_with_a_fill_id_the_extras_are_excluded_and_retained():
    result = dup.classify_file(FIXTURES / "with_fill_ids.csv", has_fill_id=True)
    excluded = result.excluded
    assert excluded, "a repeated fill id is a true duplicate"
    assert all(r.flag is s.RowFlag.DUPLICATE_FILL_ID for r in excluded)
    assert all(r.raw_text for r in excluded), "an excluded row is retained, not dropped"
    first_of_each = [r for r in result.rows if r.flag is None]
    assert len(first_of_each) + len(excluded) == len(result.rows)


def test_confirming_a_group_excludes_it_and_leaves_the_rest_alone():
    result = dup.classify_file(FIXTURES / "duplicated_block.csv", has_fill_id=False)
    group = next(r.dup_group for r in result.rows if r.dup_group)
    confirmed = dup.confirm_group(result, group)
    excluded = [r for r in confirmed.rows if r.flag is s.RowFlag.TRADER_CONFIRMED_DUPLICATE]
    assert len(excluded) == 1, "one of the pair is excluded; the first is kept"
    still_flagged = [r for r in confirmed.rows if r.flag is s.RowFlag.SUSPECTED_DUPLICATE]
    assert len(still_flagged) == 4, "the other two groups are untouched"


def test_classification_is_deterministic():
    a = dup.classify_file(FIXTURES / "duplicated_block.csv", has_fill_id=False)
    b = dup.classify_file(FIXTURES / "duplicated_block.csv", has_fill_id=False)
    assert [(r.row_no, r.flag, r.dup_group) for r in a.rows] == [
        (r.row_no, r.flag, r.dup_group) for r in b.rows
    ]


def test_every_row_is_accounted_for():
    """rows_in == kept + excluded, on every fixture. Nothing vanishes."""
    for name in ("repeated_legitimate_fills.csv", "duplicated_block.csv", "clean.csv"):
        result = dup.classify_file(FIXTURES / name, has_fill_id=False)
        assert result.kept_count + len(result.excluded) == len(rows(FIXTURES / name)) - 1
