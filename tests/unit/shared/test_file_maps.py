"""Broker file maps, and the rule that an unverified one cannot reach a partner.

PRD v1.2 section 5.2: each adapter ships a map of every export the broker offers, by
the broker's own name for it, where it lives, and whether it is the one we need --
"verified against the broker's interface when the adapter is built, not guessed, and
versioned with the adapter."

Dhan's map is drafted from the one export we hold and is **not** verified. Rather
than leave that as a comment, the loader refuses an unverified map in production, so
the first partner upload cannot quietly reject someone with wording nobody checked.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from services.production.ctr.adapters import filemap as fm

MAP_DIR = Path("services/production/ctr/adapters")


def test_the_dhan_map_loads_and_names_the_export_we_need():
    m = fm.load(MAP_DIR / "dhan_filemap.yaml")
    assert m.broker == "Dhan"
    assert m.version
    wanted = [e for e in m.exports if e.is_the_one_we_need]
    assert len(wanted) == 1, "exactly one export is the trade-level one"
    assert wanted[0].broker_name and wanted[0].where_it_lives


def test_every_export_entry_states_a_name_and_a_location():
    m = fm.load(MAP_DIR / "dhan_filemap.yaml")
    assert len(m.exports) >= 2, "a map with one entry does not help a trader choose"
    for e in m.exports:
        assert e.broker_name.strip()
        assert e.where_it_lives.strip()
        assert isinstance(e.is_the_one_we_need, bool)


def test_the_dhan_map_was_checked_against_dhan():
    """Verified 21 October 2026, and this test is how that is recorded.

    It asserted the opposite until then, so flipping the flag had to be done on
    purpose rather than by someone editing a yaml file in passing. What was
    checked: the trade-level export's name and where it sits, the header row,
    and that quantity is reported in units.
    """
    m = fm.load(MAP_DIR / "dhan_filemap.yaml")
    assert m.verified is True
    assert m.verified_on == "2026-10-21"
    assert m.quantity_unit == "units"
    assert m.wanted.broker_name == "All Exchange Transactions"
    assert m.wanted.where_it_lives == "Profile"


def test_an_unverified_map_is_still_refused_in_production(tmp_path):
    """The gate itself, on a map that has not been checked."""
    draft = (MAP_DIR / "dhan_filemap.yaml").read_text().replace(
        "verified: true", "verified: false"
    ).replace("verified_on: '2026-10-21'", "verified_on: null")
    assert "verified: false" in draft, "the edit did not apply"
    path = tmp_path / "x_filemap.yaml"
    path.write_text(draft)
    with pytest.raises(fm.UnverifiedFileMap):
        fm.require_verified(fm.load(path))


def test_a_verified_map_passes_the_production_check():
    fm.require_verified(fm.load(MAP_DIR / "dhan_filemap.yaml"))


def test_the_rejection_message_names_the_export_and_where_it_lives():
    m = fm.load(MAP_DIR / "dhan_filemap.yaml")
    text = fm.rejection_text(m, looks_like="a profit-and-loss statement", missing="time of day")
    wanted = next(e for e in m.exports if e.is_the_one_we_need)
    assert "profit-and-loss statement" in text
    assert "time of day" in text
    assert wanted.broker_name in text
    assert wanted.where_it_lives in text
    assert "Dhan" in text


def test_the_rejection_message_says_nothing_else():
    """PRD 5.3: on a rejection, nothing else is shown."""
    m = fm.load(MAP_DIR / "dhan_filemap.yaml")
    text = fm.rejection_text(m, looks_like="a tax report", missing="prices")
    for banned in ("Mirror", "Journal", "upload another", "score", "finding"):
        assert banned.lower() not in text.lower()
