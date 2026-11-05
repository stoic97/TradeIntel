"""A lot size belongs to the contract's expiry, not to the day it traded [TICKET-835].

At a changeover two sizes are live at once: expiries already listed keep the old one, new
ones get the new. A quantity both divide could be either, and the trade date cannot say
which. The expiry can, wherever the profile states which expiries a size covers.

Synthetic, worked by hand. All traded 15 Oct 2026, when SENSEX has 20 and 25 live and
HDFCBANK has 650 and 750:

  SENSEX    100 units. 100 / 20 = 5 lots, 100 / 25 = 4 lots.
  HDFCBANK  9,750 units. 9,750 / 650 = 15 lots, 9,750 / 750 = 13 lots.
  SENSEX    40 units fits 20 only, 50 units fits 25 only.

NIFTY on 10 Jan 2026 has 75 and 65 live and 975 units fits both (13 or 15 lots). Its profile
does not say which expiries take which, so it stays at the largest that divides.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select

from services.production.ctr.adapters import dhan_tradebook
from services.production.ctr.profiles import registry as profiles
from services.production.db import models as m
from services.production.db.session import make_session
from services.production.mirror import loader
from tests.unit.api.test_upload import (  # noqa: F401 - fixtures used by name
    client,
    engine,
    upload,
)

TRADED = date(2026, 10, 15)
NOV_2026 = date(2026, 11, 19)
DEC_2026 = date(2026, 12, 17)
JAN_2027 = date(2027, 1, 21)

ALL = profiles.load_all(loader.PROFILE_DIR)
SENSEX = ALL[("BSE", "SENSEX")]
HDFCBANK = ALL[("NSE", "HDFCBANK")]
NIFTY = ALL[("NSE", "NIFTY")]
CRUDEOIL = ALL[("MCX", "CRUDEOIL")]


def lots(profile, quantity: int, expiry: date | None, on: date = TRADED) -> int:
    return loader.lots_for(quantity, profile, "units", on=on, expiry=expiry)


# ---------- The gate ----------


def test_a_near_expiry_reads_the_size_it_was_listed_with():
    assert lots(SENSEX, 100, NOV_2026) == 5


def test_a_far_expiry_reads_the_new_size():
    assert lots(SENSEX, 100, JAN_2027) == 4


def test_the_last_expiry_of_the_old_size_still_reads_it():
    """The profile's Fyers line has 20 on every expiry through December 2026."""
    assert lots(SENSEX, 100, DEC_2026) == 5


def test_the_other_stated_changeover_reads_by_expiry_too():
    assert lots(HDFCBANK, 9750, DEC_2026) == 15
    assert lots(HDFCBANK, 9750, JAN_2027) == 13


# ---------- What no one can read keeps today's answer ----------


def test_a_trade_with_no_readable_expiry_keeps_the_largest_that_divides():
    assert lots(SENSEX, 100, None) == 4
    assert loader.lots_for(100, SENSEX, "units", on=TRADED) == 4


def test_a_changeover_with_no_stated_boundary_keeps_the_largest_that_divides():
    day = date(2026, 1, 10)
    assert lots(NIFTY, 975, date(2026, 1, 27), on=day) == 13
    assert lots(NIFTY, 975, date(2026, 3, 30), on=day) == 13


def test_a_profile_with_one_size_ignores_the_expiry():
    assert lots(CRUDEOIL, 700, NOV_2026) == 7


def test_with_no_date_the_current_size_is_still_the_only_one():
    assert loader.lots_for(100, SENSEX, "units", expiry=NOV_2026) == 4


def test_a_gap_between_stated_boundaries_keeps_the_largest_that_divides(tmp_path):
    """Nothing says which size December takes here, so it reads as it did without them."""
    gapped = profiles.load_one(_profile(tmp_path, (
        '  - {units: "20", from: "2024-11-20", until: "2026-12-31", expiries_until: "2026-11-30"}',
        '  - {units: "25", from: "2026-10-01", expiries_from: "2027-01-01"}',
    )))
    assert lots(gapped, 100, NOV_2026) == 5
    assert lots(gapped, 100, DEC_2026) == 4
    assert lots(gapped, 100, JAN_2027) == 4


# ---------- The expiry settles a tie, it does not start a refusal ----------


def test_a_quantity_only_the_other_size_divides_is_not_a_new_refusal():
    """50 on a November expiry fits 25, not 20. Today that reads 2 lots and shows the
    record; a stated boundary is no reason to take the whole Mirror away over one trade."""
    assert lots(SENSEX, 50, NOV_2026) == 2
    assert lots(SENSEX, 40, JAN_2027) == 2


def test_a_quantity_no_live_size_divides_is_still_refused():
    with pytest.raises(loader.MisdeclaredQuantityUnit):
        lots(SENSEX, 7, NOV_2026)


def test_lots_counted_by_the_broker_are_still_the_quantity():
    assert loader.lots_for(3, SENSEX, "lots", on=TRADED, expiry=NOV_2026) == 3


# ---------- The profile states it, and a mistake there is refused ----------


def _profile(tmp_path: Path, rows: tuple[str, ...]) -> Path:
    head = (loader.PROFILE_DIR / "BSE_SENSEX.yaml").read_text().split("lot_sizes:")[0]
    path = tmp_path / "BSE_SENSEX.yaml"
    path.write_text(head + "lot_sizes:\n" + "\n".join(rows) + "\n")
    return path


def test_a_stated_boundary_must_be_a_date(tmp_path):
    path = _profile(tmp_path, (
        '  - {units: "20", from: "2024-11-20", until: "2026-12-31", expiries_until: "soon"}',
        '  - {units: "25", from: "2026-10-01"}',
    ))
    with pytest.raises(profiles.InvalidProfile):
        profiles.load_one(path)


def test_a_stated_range_cannot_end_before_it_starts(tmp_path):
    path = _profile(tmp_path, (
        '  - {units: "20", from: "2024-11-20", until: "2026-12-31"}',
        '  - {units: "25", from: "2026-10-01", expiries_from: "2027-01-01", '
        'expiries_until: "2026-01-01"}',
    ))
    with pytest.raises(profiles.InvalidProfile):
        profiles.load_one(path)


def test_a_misspelt_boundary_is_refused_rather_than_ignored(tmp_path):
    """Ignored, it would read as no boundary, and every figure would still look right."""
    path = _profile(tmp_path, (
        '  - {units: "20", from: "2024-11-20", until: "2026-12-31", expiry_until: "2026-12-31"}',
        '  - {units: "25", from: "2026-10-01"}',
    ))
    with pytest.raises(profiles.InvalidProfile):
        profiles.load_one(path)


# ---------- Through a real upload, as every page reads it ----------


def _tradebook(rows: list[tuple[str, str, str, str, str]]) -> bytes:
    """(time, name, side, exchange and segment, quantity), all on the trade date, at 10."""
    lines = [
        f"2026-10-15,{time},{name},{side},INTRADAY,{where},{quantity},10.00,"
        f"{10 * int(quantity)}.00,Traded"
        for time, name, side, where, quantity in rows
    ]
    return ("\n".join([",".join(dhan_tradebook.HEADER), *lines]) + "\n").encode()


def _round_trip(opened: str, closed: str, name: str, quantity: str = "100") -> list[tuple]:
    return [
        (opened, f"SENSEX {name} 5000 CALL", "BUY", "BSE,Derivative", quantity),
        (closed, f"SENSEX {name} 5000 CALL", "SELL", "BSE,Derivative", quantity),
    ]


def _lots_by_hour(client, engine, content: bytes) -> dict[int, int]:  # noqa: F811
    assert upload(client, content=content).status_code == 303
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader)).one()
        trips, _ = loader.load_for(sess, trader)
    return {t.entry_ts.hour: t.lots for t in trips}


def test_the_record_reads_each_contract_at_its_own_expirys_size(client, engine):  # noqa: F811
    content = _tradebook([
        *_round_trip("10:00:00", "10:30:00", "19 NOV"),
        *_round_trip("11:00:00", "11:30:00", "21 JAN"),
    ])
    assert _lots_by_hour(client, engine, content) == {10: 5, 11: 4}


def test_a_share_on_the_same_day_keeps_its_answer(client, engine):  # noqa: F811
    content = _tradebook([
        *_round_trip("10:00:00", "10:30:00", "19 NOV"),
        ("11:00:00", "Widget ETF", "BUY", "NSE,Equity", "100"),
        ("11:30:00", "Widget ETF", "SELL", "NSE,Equity", "100"),
    ])
    assert _lots_by_hour(client, engine, content) == {10: 5, 11: 100}


def test_one_contract_at_one_instant_under_two_expiries_keeps_todays_answer(client, engine):  # noqa: F811
    """The stored row cannot be told apart from its twin, so its expiry is not read."""
    content = _tradebook([
        *_round_trip("10:00:00", "10:30:00", "19 NOV"),
        *_round_trip("10:00:00", "10:45:00", "21 JAN"),
    ])
    assert set(_lots_by_hour(client, engine, content).values()) == {4}


def test_a_quantity_only_one_size_divides_does_not_read_the_raw_file(  # noqa: F811
    client, engine, monkeypatch  # noqa: F811
):
    """Every page loads the record, and parsing the whole file each time would be waste."""
    content = _tradebook(_round_trip("10:00:00", "10:30:00", "19 NOV", quantity="40"))
    assert upload(client, content=content).status_code == 303

    def refuse(*_args):
        raise AssertionError("the expiry cannot change this trade's lots")

    monkeypatch.setattr(loader, "expiries_for", refuse)
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader)).one()
        trips, _ = loader.load_for(sess, trader)
    assert [t.lots for t in trips] == [2]
