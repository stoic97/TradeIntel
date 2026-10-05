"""Step A, cycle 2 - loading the real MCX crude series into ``Bars``.

The real file is gitignored (data/market/, logged in CROSSINGS.md), so the unit
tests run on small CSVs written to a temp folder in the file's exact format. One
integration test reads the real file and is skipped where it is absent.
"""
from datetime import date
from pathlib import Path

import numpy as np
import pytest

from services.research.evaluation.synthetic.crude import (
    CRUDE_1M_SHA256,
    MAX_CARRY_GAP,
    load_crude_1m,
)

HEADER = "timestamp,open,high,low,close,volume\n"


def _write(tmp_path: Path, rows: list[str]) -> Path:
    p = tmp_path / "crude.csv"
    p.write_text(HEADER + "".join(r + "\n" for r in rows))
    return p


TWO_DAYS = [
    "2024-01-01 9:00:00,6000,6005,5998,6004,10",  # unpadded hour, as in the real file
    "2024-01-01 9:01:00,6004,6006,6001,6002,5",
    "2024-01-01 23:29:00,6010,6012,6009,6011,7",
    "2024-01-02 09:00:00,6020,6021,6015,6016,3",
    "2024-01-02 09:01:00,6016,6018,6014,6017,4",
]


def test_rows_become_bars_with_day_index_and_ist_minutes(tmp_path):
    h = load_crude_1m(_write(tmp_path, TWO_DAYS), verify_hash=False)
    assert list(h.bars.day) == [0, 0, 0, 1, 1]
    assert list(h.bars.minute) == [540, 541, 1409, 540, 541]
    assert h.dates == (date(2024, 1, 1), date(2024, 1, 2))
    assert h.bars.close[2] == 6011.0


def test_loading_twice_gives_identical_bytes(tmp_path):
    p = _write(tmp_path, TWO_DAYS)
    a = load_crude_1m(p, verify_hash=False)
    b = load_crude_1m(p, verify_hash=False)
    assert a.bars.content_hash() == b.bars.content_hash()


def test_inconsistent_bars_are_repaired_and_counted_never_dropped(tmp_path):
    rows = [
        "2024-01-01 9:00:00,5085,5084,5085,5084,16",  # high and low swapped
        "2024-01-01 9:01:00,7282,7296,7279,7300,40",  # close above the reported high
        "2024-01-01 9:02:00,6000,6001,5999,6000,1",  # clean
    ]
    h = load_crude_1m(_write(tmp_path, rows), verify_hash=False)
    b = h.bars
    assert len(b.close) == 3
    assert h.report.repaired_bars == 2
    assert (b.low <= np.minimum(b.open, b.close)).all()
    assert (b.high >= np.maximum(b.open, b.close)).all()
    assert (b.high[1], b.low[1]) == (7300.0, 7279.0)


def test_carry_is_blocked_across_an_abnormal_overnight_gap(tmp_path):
    rows = [
        "2020-04-20 16:59:00,963,965,963,965,446",
        "2020-04-21 9:00:00,1727,1727,1702,1702,43",  # +79%: stitched roll, not a market move
        "2020-04-21 23:29:00,1325,1326,1324,1325,5",
        "2020-04-22 9:00:00,1272,1272,1245,1245,13",  # -4%: real
    ]
    h = load_crude_1m(_write(tmp_path, rows), verify_hash=False)
    assert MAX_CARRY_GAP == 0.10
    assert list(h.carry_allowed) == [False, True, False]  # last day has no next day
    assert h.report.carry_blocked_days == (date(2020, 4, 20),)


def test_refuses_a_file_whose_hash_does_not_match(tmp_path):
    with pytest.raises(ValueError, match="sha256"):
        load_crude_1m(_write(tmp_path, TWO_DAYS))


@pytest.mark.parametrize(
    "rows",
    [
        ["2024-01-01 9:01:00,1,1,1,1,1", "2024-01-01 9:00:00,1,1,1,1,1"],  # out of order
        ["2024-01-01 9:00:00,1,1,1,1,1", "2024-01-01 9:00:00,1,1,1,1,1"],  # duplicate
        ["2024-01-01 9:00:00,0,1,0,1,1"],  # non-positive price
    ],
)
def test_refuses_malformed_series(tmp_path, rows):
    with pytest.raises(ValueError):
        load_crude_1m(_write(tmp_path, rows), verify_hash=False)


REAL = Path(__file__).resolve().parents[3] / "data" / "market" / "crude_1m.csv"


@pytest.mark.skipif(not REAL.exists(), reason="real crude file not present on this machine")
def test_real_file_matches_its_crossing_record():
    h = load_crude_1m(REAL)
    assert h.report.source_sha256 == CRUDE_1M_SHA256
    assert len(h.dates) == 1861  # CROSSINGS.md
    assert h.dates[0] == date(2018, 10, 1)
    assert h.dates[-1] == date(2025, 12, 24)
    assert date(2020, 4, 20) in h.report.carry_blocked_days
