"""TICKET-997: market data stored by day, checked when written.

One gzip file per underlying per trading day, and a manifest that lists every day with its row
count and the sha256 of its uncompressed text. ``DayStore.put`` is the one way a day is written,
and it refuses, naming why, before anything reaches disk. Every bar here is made up.
"""

from __future__ import annotations

import gzip
import hashlib
from datetime import date, datetime, time, timedelta

import pytest

from services.shared.market import day_store as ds
from services.shared.market import series as ms

HEADER = b"timestamp,open,high,low,close,volume\n"
MON = date(2026, 3, 2)


def rows(day: date, start=(9, 15), minutes=5, price=22000, step=1) -> list[bytes]:
    t0 = datetime.combine(day, time(*start))
    return [f"{t0 + timedelta(minutes=i * step):%Y-%m-%d %H:%M:%S},{price + i},{price + i + 2},"
            f"{price + i - 1},{price + i + 1},10\n".encode() for i in range(minutes)]


def store(tmp_path, underlying="NIFTY") -> ds.DayStore:
    return ds.DayStore(tmp_path / underlying, underlying)


def save(s: ds.DayStore, **kw) -> ds.DayManifest:
    return s.save(serves=(s.underlying,), source="made up for a test", roll="", clock=ms.CLOCK,
                  interval="1 minute", built=date(2026, 11, 20), **kw)


# ---------- the layout ----------

def test_a_day_is_one_gzip_file_under_its_year_holding_the_header_and_that_days_rows(tmp_path):
    s = store(tmp_path)
    s.put(MON, HEADER, rows(MON))
    path = tmp_path / "NIFTY" / "2026" / "2026-03-02.csv.gz"
    assert path.exists()
    assert gzip.decompress(path.read_bytes()) == HEADER + b"".join(rows(MON))


def test_the_manifest_lists_each_day_with_rows_and_the_hash_of_its_uncompressed_text(tmp_path):
    s = store(tmp_path)
    s.put(MON, HEADER, rows(MON))
    s.put(MON + timedelta(days=1), HEADER, rows(MON + timedelta(days=1), minutes=3))
    m = save(s)
    text = HEADER + b"".join(rows(MON))
    assert m.days["2026-03-02"].rows == 5
    assert m.days["2026-03-02"].sha256 == hashlib.sha256(text).hexdigest()
    assert m.days["2026-03-03"].rows == 3
    assert m.as_of == date(2026, 3, 3)
    assert (tmp_path / "NIFTY" / "manifest.json").exists()
    assert ds.read_manifest(tmp_path / "NIFTY") == m


def test_the_manifest_keeps_what_the_single_file_manifest_kept(tmp_path):
    s = store(tmp_path)
    s.put(MON, HEADER, rows(MON))
    m = save(s, sessions=("2026-03-02 evening only: a made-up reason",))
    for name in ("underlying", "serves", "source", "roll", "clock", "interval", "built", "as_of", "sessions"):
        assert hasattr(m, name), name
    assert m.covers(MON) and not m.covers(MON - timedelta(days=1)) and not m.covers(MON + timedelta(days=1))


def test_the_same_day_always_makes_the_same_bytes(tmp_path):
    a, b = store(tmp_path / "a"), store(tmp_path / "b")
    a.put(MON, HEADER, rows(MON))
    b.put(MON, HEADER, rows(MON))
    assert ds.day_path(a.folder, MON).read_bytes() == ds.day_path(b.folder, MON).read_bytes()


def test_rows_with_single_digit_hours_are_kept_byte_for_byte(tmp_path):
    old = [r.replace(b" 09:", b" 9:") for r in rows(MON, start=(9, 0))]
    s = store(tmp_path, "CRUDEOIL")
    s.put(MON, HEADER, old)
    assert ds.read_day(s.folder, MON, s.days["2026-03-02"]) == HEADER + b"".join(old)


# ---------- checked when written ----------

@pytest.mark.parametrize(("why", "bad"), [
    ("whole minute", [r.replace(b":00,", b":30,", 1) for r in rows(MON)]),
    ("come after", list(reversed(rows(MON)))),
    ("not on 2026-03-02", rows(MON) + rows(MON + timedelta(days=1), minutes=1)),
    ("not a timestamp", [b"yesterday,1,2,3,4,5\n"]),
    ("no bars", []),
])
def test_a_day_that_breaks_a_stamp_rule_is_refused_and_nothing_is_written(tmp_path, why, bad):
    s = store(tmp_path)
    with pytest.raises(ds.Refused, match=why):
        s.put(MON, HEADER, bad)
    assert not ds.day_path(s.folder, MON).exists()
    assert "2026-03-02" not in s.days


def test_a_refusal_names_the_stamp_and_never_a_price(tmp_path):
    bad = [b"2026-03-02 09:15:30,22123.5,22125,22122,22124,10\n"]
    with pytest.raises(ds.Refused) as got:
        store(tmp_path).put(MON, HEADER, bad)
    assert "09:15:30" in str(got.value) and "22123" not in str(got.value)


def test_a_day_held_already_is_replaced_only_with_a_reason_and_the_reason_is_kept(tmp_path):
    s = store(tmp_path)
    s.put(MON, HEADER, rows(MON))
    save(s)
    again = store(tmp_path)
    with pytest.raises(ds.Refused, match="reason"):
        again.put(MON, HEADER, rows(MON, price=22100))
    again.put(MON, HEADER, rows(MON, price=22100), reason="the broker corrected the day")
    m = save(again)
    assert any("2026-03-02" in r and "the broker corrected the day" in r for r in m.replaced)


def test_a_day_goes_through_a_temporary_name_and_os_replace(tmp_path, monkeypatch):
    moves = []
    real = ds.os.replace
    monkeypatch.setattr(ds.os, "replace", lambda a, b: (moves.append((str(a), str(b))), real(a, b)))
    s = store(tmp_path)
    s.put(MON, HEADER, rows(MON))
    save(s)
    assert [b.endswith(".csv.gz") and a.endswith(".part") for a, b in moves[:1]] == [True]
    assert moves[-1][1].endswith("manifest.json") and moves[-1][0].endswith(".part")


# ---------- the session checks ----------

CAL = {  # the calendar starts on its first entry, 26 Jan, so 2 Mar is inside it
    date(2026, 1, 26): ms.SessionException(date(2026, 1, 26), "closed", "a made-up closure"),
    date(2026, 3, 3): ms.SessionException(date(2026, 3, 3), "evening_only", "a made-up holiday"),
    date(2026, 3, 4): ms.SessionException(date(2026, 3, 4), "closed", "a made-up closure"),
}
MCX = ds.mcx_check(CAL, time(9, 0))


def full(day: date) -> list[bytes]:
    return rows(day, start=(9, 0), minutes=30, step=30)  # 09:00 to 23:30, every half hour


def test_mcx_a_full_session_inside_the_calendar_is_checked_against_it(tmp_path):
    assert store(tmp_path, "CRUDEOIL").put(MON, HEADER, full(MON), check=MCX).checked == ds.CALENDAR_CHECK


def test_mcx_a_part_session_needs_its_reason_in_the_calendar(tmp_path):
    s = store(tmp_path, "CRUDEOIL")
    assert s.put(date(2026, 3, 3), HEADER, rows(date(2026, 3, 3), start=(17, 0)), check=MCX).checked == ds.CALENDAR_CHECK
    with pytest.raises(ds.Refused, match="2026-03-05.*evening only"):
        s.put(date(2026, 3, 5), HEADER, rows(date(2026, 3, 5), start=(17, 0)), check=MCX)


def test_mcx_a_day_the_calendar_calls_closed_has_no_bars(tmp_path):
    with pytest.raises(ds.Refused, match="2026-03-04"):
        store(tmp_path, "CRUDEOIL").put(date(2026, 3, 4), HEADER, full(date(2026, 3, 4)), check=MCX)


def test_mcx_a_full_session_must_open_at_the_open(tmp_path):
    late = rows(MON, start=(9, 1), minutes=30, step=30)  # stamped at the end of each minute
    with pytest.raises(ds.Refused, match="09:01"):
        store(tmp_path, "CRUDEOIL").put(MON, HEADER, late, check=MCX)


def test_mcx_a_day_before_the_calendar_starts_is_written_with_its_stamps_checked_only(tmp_path):
    old = date(2019, 10, 27)  # a Sunday muhurat session, years before mcx_sessions.yaml begins
    got = store(tmp_path, "CRUDEOIL").put(old, HEADER, rows(old, start=(18, 15)), check=MCX)
    assert got.checked == ds.STAMPS_ONLY


NSE = ds.open_check(time(9, 15), frozenset({date(2026, 3, 4)}), date(2026, 11, 12))


def test_nse_the_first_bar_is_at_the_open(tmp_path):
    s = store(tmp_path)
    assert s.put(MON, HEADER, rows(MON), check=NSE).checked == ds.OPEN_CHECK
    with pytest.raises(ds.Refused, match="09:16"):
        s.put(MON + timedelta(days=1), HEADER, rows(MON + timedelta(days=1), start=(9, 16)), check=NSE)


def test_nse_a_closed_day_has_no_bars(tmp_path):
    with pytest.raises(ds.Refused, match="closed"):
        store(tmp_path).put(date(2026, 3, 4), HEADER, rows(date(2026, 3, 4)), check=NSE)


# ---------- read back ----------

def test_a_day_whose_text_no_longer_matches_its_hash_is_refused_when_read(tmp_path):
    s = store(tmp_path)
    entry = s.put(MON, HEADER, rows(MON))
    ds.day_path(s.folder, MON).write_bytes(gzip.compress(HEADER + b"".join(rows(MON, price=1))))
    with pytest.raises(ds.Refused, match="hash"):
        ds.read_day(s.folder, MON, entry)
