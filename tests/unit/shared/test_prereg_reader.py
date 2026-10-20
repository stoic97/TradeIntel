"""Reading the pre-registered framework, and saying how much to trust it.

The eligibility statement is the product telling a trader which checks his history
can support. Every number in it comes from this file, so two things have to be
true: the numbers must be the ones in the framework, and the page must know whether
the framework it read is the locked one.

That last part is not pedantry. An eligibility figure computed from a draft is a
different claim from the same figure computed from a locked pre-registration --
the whole point of the lock is that the thresholds were fixed before anyone looked
at a trader's data. The reader reports which it read; it never decides that for
itself.
"""

from __future__ import annotations

import hashlib
import shutil

import pytest

from services.shared.prereg import reader


def test_the_real_framework_reads():
    framework = reader.load()
    assert framework.version == "1.0.0"
    ids = [t.id for t in framework.tests]
    assert "B2" in ids and "S12" in ids
    assert len(ids) == len(set(ids)), "an id appears twice"
    assert len(ids) >= 15, ids


def test_today_the_framework_is_a_draft():
    """It is locked at the kickoff, and that is a decision, not an oversight.

    When the lock happens this test fails, and the person locking it changes it
    deliberately -- which is the point. Until then the eligibility page has to say
    the thresholds are not yet fixed.
    """
    framework = reader.load()
    assert framework.lock is reader.LockState.DRAFT
    assert framework.trustworthy is False
    assert framework.status == "draft"


def test_a_matching_hash_file_reads_as_locked(tmp_path):
    source = reader.FRAMEWORK
    copy = tmp_path / source.name
    shutil.copy(source, copy)
    digest = hashlib.sha256(copy.read_bytes()).hexdigest()
    copy.with_name(copy.name + ".sha256").write_text(f"{digest}  {copy.name}\n")

    framework = reader.load(copy)
    assert framework.lock is reader.LockState.LOCKED
    assert framework.trustworthy is True


def test_a_hash_that_does_not_match_is_refused(tmp_path):
    """The case the lock exists for: the file changed after it was pre-registered.

    Reading it anyway and carrying on would make every threshold on the page a
    number nobody agreed to, presented as one everybody did.
    """
    source = reader.FRAMEWORK
    copy = tmp_path / source.name
    shutil.copy(source, copy)
    copy.with_name(copy.name + ".sha256").write_text(f"{'0' * 64}  {copy.name}\n")

    framework = reader.load(copy)
    assert framework.lock is reader.LockState.TAMPERED
    assert framework.trustworthy is False
    with pytest.raises(reader.TamperedFramework):
        reader.require_trustworthy(framework)


@pytest.mark.parametrize(
    ("raw", "condition", "comparison", "unit", "inferred"),
    [
        ("30/60", 30, 60, reader.Unit.TRIPS, False),
        (30, 30, None, reader.Unit.TRIPS, False),
        (200, 200, None, reader.Unit.TRIPS, False),
        ("40_days", 40, None, reader.Unit.DAYS, False),
        ("40_winners", 40, None, reader.Unit.WINNERS, False),
        ("30_losers", 30, None, reader.Unit.LOSERS, False),
        ("30/bucket", 30, None, reader.Unit.PER_BUCKET, False),
        ("30/regime", 30, None, reader.Unit.PER_REGIME, False),
        ("20/cell", 20, None, reader.Unit.PER_CELL, False),
        # Read by analogy with 30/60, not stated anywhere. TD-030.
        ("20/40_days", 20, 40, reader.Unit.DAYS, True),
    ],
)
def test_each_minimum_shape_parses(raw, condition, comparison, unit, inferred):
    n_min = reader.parse_n_min(raw)
    assert n_min.condition == condition
    assert n_min.comparison == comparison
    assert n_min.unit is unit
    assert n_min.inferred is inferred
    assert n_min.understood is True


def test_a_shape_nobody_has_taught_it_is_not_guessed():
    """A new test with a new shape must read as unknown, not as a number.

    Falling back to "the first integer in the string" would turn an unfamiliar
    rule into a confident threshold, which is how a trader gets told a check can
    run when nobody has decided what running it would mean.
    """
    n_min = reader.parse_n_min("30_per_fortnight_of_tuesdays")
    assert n_min.understood is False
    assert n_min.condition is None


def test_every_test_in_the_real_library_has_a_minimum_we_understand():
    """The guard that makes the one above matter.

    If someone adds a test with a shape the reader cannot read, this fails here
    rather than quietly showing a trader one fewer check than he has.
    """
    unreadable = [
        (t.id, t.n_min.raw) for t in reader.load().tests if not t.n_min.understood
    ]
    assert unreadable == []


def test_the_readings_taken_by_analogy_are_listed():
    """Whatever rests on an inference should be countable, not buried."""
    inferred = sorted(t.id for t in reader.load().tests if t.n_min.inferred)
    assert inferred == ["B12"], (
        "if this list grew, TD-030 needs the new entries before the page uses them"
    )


def test_a_test_carries_the_names_of_what_else_it_depends_on():
    """S10 needs a release calendar; S5 needs regime labels; S1 needs buckets.

    Each of those is a key on the library entry. Reading them by name means a
    dependency added to the framework reaches the product without anyone
    remembering a list -- and the eligibility page can say *which* thing is
    missing rather than "something".
    """
    framework = reader.load()
    assert "events" in framework.test("S10").extras
    assert "regime" in framework.test("S5").extras
    assert "buckets" in framework.test("S1").extras
    assert framework.test("B2").extras == ()
