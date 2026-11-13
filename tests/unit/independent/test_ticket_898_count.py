"""TICKET-898: an independent count of the prior-minute figure, from spec s4.7 and the rulings.

Every expected number below was worked out by hand on BARS, never copied from program output.
Bars are stamped at the START of their minute (s4.7.2). Entry t lies in minute m0.

Rulings on TICKET-898 (13 Nov 2026) that this file pins:
  D1  "+N after entry" runs from the close of the entry-minute bar (bar m0) to the close of
      bar m0 + N. Anything earlier counts seconds that came before the entry.
  D2  the minute before entry is bar m0 - 1, read as its own open to its own close. The
      close(m0 - 2) to close(m0 - 1) reading stays only as a sensitivity row.
  D3  a count drops a trip only when a bar that count needs is missing, and the reason names
      the bar: the prior count needs bar m0 - 1; a +N count needs bar m0 and bar m0 + N.
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


# Prior = bar m0 - 1, open to close. The comment on each trip is its prior reading.
TRIPS = [
    Trip("A", "MCX_CRUDEOIL", "FUT", "BUY", _t("09:03:20")),    # 09:02 is -1, long: against
    Trip("B", "MCX_CRUDEOIL", "FUT", "SELL", _t("09:03:00")),   # 09:02 is -1, short: with
    Trip("C", "MCX_CRUDEOILM", "PUT", "BUY", _t("09:05:10")),   # 09:04 is -1, put=short: with
    Trip("D", "MCX_CRUDEOIL", "PUT", "SELL", _t("09:04:59")),   # 09:03 is 0: flat
    Trip("E", "MCX_CRUDEOIL", "MULTI", "BUY", _t("09:03:20")),  # no single direction
    Trip("F", "MCX_NATURALGAS", "FUT", "BUY", _t("09:03:20")),  # no series
    Trip("G", "MCX_CRUDEOIL", "FUT", "BUY", _t("09:03:20", "2026-02-10")),  # not covered
    Trip("H", "MCX_CRUDEOIL", "CALL", "BUY", _t("09:00:30")),   # prior bar 08:59 missing
    Trip("I", "MCX_CRUDEOIL", "CALL", "BUY", _t("09:07:30")),   # 09:06 is +1, long: with
    Trip("J", "MCX_CRUDEOIL", "FUT", "BUY", _t("09:08:10")),    # prior bar 09:07 missing
    Trip("K", "MCX_CRUDEOIL", "FUT", "BUY", _t("09:06:30")),    # 09:05 is +2, long: with
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
    # with: B, C, I, K. against: A. flat: D.
    p = result.prior
    assert (p.with_, p.against, p.flat, p.measured) == (4, 1, 1, 6)


def test_prior_minute_unmeasured_each_with_its_reason(result):
    assert dict(result.prior.unmeasured) == {
        "no_single_direction": 1,
        "no_series_for_underlying": 1,
        "series_does_not_cover": 1,
        "missing_prior_bar": 2,
    }
    assert result.prior.measured + sum(result.prior.unmeasured.values()) == result.total == 11


def test_prior_minute_is_the_prior_bars_own_open_to_close(result):
    # A enters 09:03:20, so its prior bar is 09:02: open 104, close 103 = -1. A is long, so
    # against. Close to close (103 - 101 = +2) would read it as with.
    assert result.prior.per_trip["A"] == "against"


def test_entry_on_the_minute_reads_the_bar_before_not_the_entry_bar(result):
    # B enters at 09:03:00 exactly. Reading the entry bar instead (a one-minute shift) would
    # give open 103, close 103 = flat, not "with".
    assert result.prior.per_trip["B"] == "with"


def test_bought_put_is_short_the_underlying(result):
    assert result.prior.per_trip["C"] == "with"


def test_a_gap_is_never_filled_with_the_nearest_bar(result):
    # J's prior bar 09:07 is missing. C's +2 bar is 09:07, also missing.
    assert result.prior.per_trip["J"] == "missing_prior_bar"
    assert result.after[2].per_trip["C"] == "missing_horizon_bar"


def test_plus_two_runs_from_the_close_of_the_entry_minute(result):
    # close of bar m0 + 2 less close of bar m0:
    # A 09:05 104 - 09:03 103 = +1 long: with. B same move, short: against.
    # D 09:06 105 - 09:04 102 = +3 sold put (long): with. H 09:02 103 - 09:00 100 = +3: with.
    # K 09:08 106 - 09:06 105 = +1 long: with.
    # C no bar 09:07. I no entry bar 09:07. J no bar 09:10.
    a = result.after[2]
    assert (a.with_, a.against, a.flat, a.measured) == (4, 1, 0, 5)
    assert dict(a.unmeasured) == {
        "no_single_direction": 1,
        "no_series_for_underlying": 1,
        "series_does_not_cover": 1,
        "missing_entry_minute_bar": 1,
        "missing_horizon_bar": 2,
    }
    # A tells the bases apart: from the start of the entry minute it would read
    # close(09:04) 102 - close(09:02) 103 = -1, against.
    assert a.per_trip["A"] == "with"


def test_each_count_needs_only_the_bars_it_uses(result):
    # H: prior bar 08:59 missing, yet +2 needs only bars 09:00 and 09:02, so it is measured.
    assert result.prior.per_trip["H"] == "missing_prior_bar"
    assert result.after[2].per_trip["H"] == "with"
    # I: entry bar 09:07 missing (the entry-minute bar is reported first), yet its prior bar
    # 09:06 is there, so the prior count still measures it.
    assert result.prior.per_trip["I"] == "with"
    assert result.after[2].per_trip["I"] == "missing_entry_minute_bar"


def test_close_to_close_is_reported_separately_as_a_sensitivity(result):
    # close(m0 - 2) to close(m0 - 1): A 103 - 101 = +2, long: with, where the ruled
    # reading says against.
    alt = result.prior_close_close
    assert alt.per_trip["A"] == "with"
    assert result.prior.per_trip["A"] == "against"
    assert (alt.with_, alt.against, alt.flat, alt.measured) == (4, 1, 1, 6)
    assert dict(alt.unmeasured)["missing_prior_bar"] == 2


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