"""TICKET-898 RED: an independent count of the prior-minute figure, from spec s4.7 only.

Every expected number below was worked out by hand from s4.7 on BARS, never copied from
program output. Bars are stamped at the START of their minute (s4.7.2), so the price at a
minute edge E is the close of the bar stamped E - 1 minute; a move is the close at one edge
against the close at another (s4.7.5). Entry t lies in minute m0; the minute before entry is
edge m0 against edge m0 - 1; "+N after entry" is edge m0 + N against edge m0.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from scripts.independent_count_898 import (
    LONG,
    NONE,
    SHORT,
    Series,
    Trip,
    count,
    direction,
    load_series,
)

D = "2026-01-05"


def _t(hms: str, day: str = D) -> datetime:
    return datetime.fromisoformat(f"{day} {hms}")


# stamp (start of minute): (open, close). No bar at 08:59 (before the open) or 09:07 (a gap).
BARS = {
    "09:00": (100.0, 100.0),
    "09:01": (100.5, 101.0),
    "09:02": (104.0, 103.0),
    "09:03": (103.0, 103.0),
    "09:04": (103.0, 102.0),
    "09:05": (102.0, 104.0),
    "09:06": (104.0, 105.0),
    "09:08": (105.5, 106.0),
}


def _series() -> Series:
    return Series({_t(k + ":00"): v for k, v in BARS.items()})


TRIPS = [
    Trip("A", "MCX_CRUDEOIL", "FUT", "BUY", _t("09:03:20")),   # 103-101=+2 long  -> with
    Trip("B", "MCX_CRUDEOIL", "FUT", "SELL", _t("09:03:00")),  # same move, short -> against
    Trip("C", "MCX_CRUDEOILM", "PUT", "BUY", _t("09:05:10")),  # 102-103=-1 short -> with
    Trip("D", "MCX_CRUDEOIL", "PUT", "SELL", _t("09:04:59")),  # 103-103=0        -> flat
    Trip("E", "MCX_CRUDEOIL", "MULTI", "BUY", _t("09:03:20")),  # no single direction
    Trip("F", "MCX_NATURALGAS", "FUT", "BUY", _t("09:03:20")),  # no series
    Trip("G", "MCX_CRUDEOIL", "FUT", "BUY", _t("09:03:20", "2026-02-10")),  # not covered
    Trip("H", "MCX_CRUDEOIL", "CALL", "BUY", _t("09:00:30")),  # bar 08:59 missing
    Trip("I", "MCX_CRUDEOIL", "CALL", "BUY", _t("09:07:30")),  # 105-104=+1 long  -> with
    Trip("J", "MCX_CRUDEOIL", "FUT", "BUY", _t("09:08:10")),   # bar 09:07 missing (gap)
    Trip("K", "MCX_CRUDEOIL", "FUT", "BUY", _t("09:06:30")),   # 104-102=+2 long  -> with
]


@pytest.fixture
def result():
    return count(TRIPS, {"CRUDE": _series()}, horizons=(2,))


def test_direction_table_s4_7_7():
    assert direction("CALL", "BUY") == LONG
    assert direction("PUT", "BUY") == SHORT
    assert direction("CALL", "SELL") == SHORT
    assert direction("PUT", "SELL") == LONG
    assert direction("FUT", "BUY") == LONG
    assert direction("FUT", "SELL") == SHORT
    assert direction("STOCK", "BUY") == LONG
    assert direction("MULTI", "BUY") == NONE


def test_prior_minute_headline(result):
    p = result.prior
    assert (p.with_, p.against, p.flat, p.measured) == (4, 1, 1, 6)


def test_prior_minute_unmeasured_each_with_its_reason(result):
    assert dict(result.prior.unmeasured) == {
        "no_single_direction": 1,
        "no_series_for_underlying": 1,
        "series_does_not_cover": 1,
        "missing_bar": 2,
    }
    assert result.prior.measured + sum(result.prior.unmeasured.values()) == result.total == 11


def test_entry_on_the_minute_reads_the_bar_before_not_the_entry_bar(result):
    # B enters at 09:03:00 exactly. Reading the entry bar instead (one-minute shift)
    # would give close 09:03 vs close 09:02 = 103-103 = flat, not "against".
    assert result.prior.per_trip["B"] == "against"


def test_bought_put_is_short_the_underlying(result):
    assert result.prior.per_trip["C"] == "with"


def test_a_gap_is_never_filled_with_the_nearest_bar(result):
    assert result.prior.per_trip["J"] == "missing_bar"
    assert result.after[2].per_trip["K"] == "missing_bar"


def test_plus_two_after_entry(result):
    # A 102-103=-1 against, B with, C 105-102=+3 short against, D 104-103=+1 sold put with,
    # I 106-105=+1 with; H, J no reference bar; K no bar at the horizon.
    a = result.after[2]
    assert (a.with_, a.against, a.flat, a.measured) == (3, 2, 0, 5)
    assert dict(a.unmeasured) == {
        "no_single_direction": 1,
        "no_series_for_underlying": 1,
        "series_does_not_cover": 1,
        "missing_bar": 3,
    }


def test_open_to_close_sensitivity_is_reported_separately(result):
    # Bar 09:02 opens 104 and closes 103: open->close reads A as -1 (against),
    # while the s4.7.5 close->close reading is +2 (with).
    assert result.prior.per_trip["A"] == "with"
    assert result.prior_open_close.per_trip["A"] == "against"
    alt = result.prior_open_close
    assert (alt.with_, alt.against, alt.flat) == (4, 1, 1)


def test_default_horizons_are_the_tickets():
    assert sorted(count([], {"CRUDE": _series()}).after) == [5, 15, 30, 60]


def test_loader_refuses_a_stamp_off_the_minute(tmp_path):
    p = tmp_path / "bars.csv"
    p.write_text(
        "datetime,open,high,low,close,volume\n2026-01-05 09:00:30,1,1,1,1,0\n", encoding="utf-8"
    )
    with pytest.raises(ValueError):
        load_series(p)


def test_loader_reads_start_stamped_closes(tmp_path):
    p = tmp_path / "bars.csv"
    p.write_text(
        "datetime,open,high,low,close,volume\n"
        "2026-01-05 09:00:00,100,101,99,100.5,10\n"
        "2026-01-05 09:01:00,100.5,102,100,101.5,10\n",
        encoding="utf-8",
    )
    assert load_series(p).price_at_edge(_t("09:02:00")) == 101.5