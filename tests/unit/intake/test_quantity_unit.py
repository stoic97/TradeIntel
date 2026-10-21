"""What the broker's Quantity column counts, and what the multiplier may touch.

Two figures a trader reads come out of these two columns, and they take opposite
treatments. Getting them the same way round is a 100x error in either direction.

**Money is the broker's own total.** Trade Value is authoritative -- the adapter
established that against 3,828 real rows, where 217 of them had
``price x quantity != value`` and the value was right every time. So gross is a
difference of rupee figures, and the instrument's contract multiplier must never be
applied to it. This file pins that, because a multiplier sitting unused in the
profile looks exactly like an oversight, and the obvious "fix" multiplies every
rupee a trader sees by the lot size.

**Size is a count whose unit was never established.** The column is named
"Quantity/Lot", and the four facts the adapter verified against real rows do not
include which of the two it is. Both conventions satisfy ``value / quantity =
price``, so no file in this repository can settle it -- it takes one look at a real
Dhan export. The unit is therefore declared in the file map, which already refuses
to reach a partner until it is verified, and both paths are built here. When
someone checks the export, one word changes and these tests say whether it worked.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from services.production.ctr.adapters import dhan_tradebook, filemap
from services.production.ctr.intake import outcomes as oc
from services.production.ctr.intake import pipeline as pl
from services.production.ctr.profiles import registry as profiles
from services.production.mirror import loader

CLEAN = Path("data/fixtures/duplicates/clean.csv")


def _profile(multiplier: str) -> profiles.InstrumentProfile:
    """The fixture instrument, at a chosen lot size."""
    profile = profiles.load_one(
        Path("services/production/ctr/profiles/MCX_WIDGETOIL.yaml"))
    assert profile.contract_multiplier == Decimal(multiplier), (
        "this test reads the real profile so a change to it is visible here"
    )
    return profile


def test_gross_is_the_brokers_value_and_carries_no_multiplier():
    """5200 -> 5215 on one lot is Rs 15, because Rs 15 is what the broker's own
    totals differ by. The profile's multiplier of 100 is not a licence to make it
    1,500: the broker already reported rupees.
    """
    plan = pl.plan_import(
        CLEAN.read_text(),
        context=pl.ImportContext(trader_id="1", source_account="A",
                                 code_version="test", existing_days={}),
    )
    gross = [t.gross_pnl for t in plan.trips]
    assert gross == [Decimal("15.00"), Decimal("30.00")], (
        "gross must be the difference of the broker's authoritative Trade Values"
    )
    assert _profile("100").contract_multiplier == Decimal(100), (
        "and the profile's multiplier is 100 while that holds -- the two are "
        "unrelated, which is the whole point of this test"
    )


def test_lots_are_the_quantity_itself_when_the_map_says_lots():
    assert loader.lots_for(3, _profile("100"), "lots") == 3


def test_lots_divide_by_the_lot_size_when_the_map_says_units():
    """300 barrels of a 100-barrel contract is three lots, not three hundred."""
    assert loader.lots_for(300, _profile("100"), "units") == 3


def test_a_quantity_that_is_not_whole_lots_refuses_rather_than_rounds():
    """150 units of a 100-unit contract cannot be a real position.

    It means the declared unit is wrong, and a silent 1.5 would be printed to a
    trader as his average size.
    """
    with pytest.raises(loader.MisdeclaredQuantityUnit):
        loader.lots_for(150, _profile("100"), "units")


def test_the_file_map_must_declare_a_unit_it_recognises(tmp_path):
    bad = tmp_path / "bad_filemap.yaml"
    bad.write_text(
        'broker: X\nadapter_id: x_v1\nversion: "0"\nverified: false\n'
        'quantity_unit: whatever\nexports:\n'
        '  - broker_name: Tradebook\n    where_it_lives: Reports\n'
        '    is_the_one_we_need: true\n'
    )
    with pytest.raises(filemap.InvalidFileMap):
        filemap.load(bad)


def test_the_dhan_map_declares_units_and_has_been_checked():
    """Checked 21 October 2026. It said "lots", and lots was wrong.

    Dhan reports quantity in units: one NIFTY lot appears as its contract size.
    The decisive evidence was already in the adapter -- `Trade Value / Quantity`
    equals the quoted premium on all but 217 of 3,828 real rows, and that only
    holds if the quantity is units. Read as lots, the Mirror would have told a
    trader he traded sixty-five times the size he did.
    """
    adapter = oc.adapter_for(dhan_tradebook.FORMAT_ID)
    assert adapter is not None
    file_map = adapter.file_map()
    assert file_map.quantity_unit == "units"
    assert file_map.verified is True
