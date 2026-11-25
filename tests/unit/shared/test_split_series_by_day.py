# ruff: noqa: DTZ001 - the series are naive IST by convention (TICKET-893); so are these bars
"""TICKET-997: splitting a single-file series into day files.

The split refuses unless every row lands in exactly one day file, the rows add up to the
series' own count, and the day files' text joined in order is the series' rows byte for byte.
It prints counts and dates, never a price. Every bar here is made up.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta

import pytest

from scripts import split_series_by_day as split
from services.production.prices import layer as L
from services.shared.market import day_store as DS
from services.shared.market import series as SS

HEADER = "timestamp,open,high,low,close,volume\n"


def crude_day(day: date, price: int, *, single_digit=False) -> list[str]:
    """A made-up full MCX session, 09:00 to 23:29, one bar every ten minutes."""
    t0 = datetime(day.year, day.month, day.day, 9, 0)
    out = []
    for i in range(0, 14 * 60 + 30, 10):
        t = t0 + timedelta(minutes=i)
        stamp = f"{t:%Y-%m-%d} {t.hour}:{t:%M:%S}" if single_digit else f"{t:%Y-%m-%d %H:%M:%S}"
        out.append(f"{stamp},{price + i % 7},{price + 9},{price - 3},{price + i % 5},10")
    return out


def write_series(path, rows, *, rows_in_manifest=None, as_of=None):
    body = (HEADER + "".join(r + "\n" for r in rows)).encode()
    path.write_bytes(body)
    stamps = [datetime.fromisoformat(r.split(",")[0].replace(" 9:", " 09:")) for r in rows]
    SS.write_manifest(SS.SeriesManifest(
        underlying="CRUDEOIL", serves=SS.CRUDE_SERVES, file=path.name, sha256=hashlib.sha256(body).hexdigest(),
        rows=rows_in_manifest if rows_in_manifest is not None else len(rows), first_bar=stamps[0],
        last_bar=stamps[-1], as_of=as_of or stamps[-1].date(), source="made up for a test",
        roll=SS.ROLL_CONVENTION, clock=SS.CLOCK, interval="1 minute", built=date(2026, 11, 13),
        extended_from=stamps[0].date(), sessions=("2026-03-03 evening only: a made-up holiday",)),
        path.with_suffix(".json"))
    return path


DAYS = [date(2019, 10, 1), date(2019, 10, 3), date(2026, 3, 2), date(2026, 3, 4)]
CAL = {date(2026, 1, 26): SS.SessionException(date(2026, 1, 26), "closed", "a made-up closure")}


def market():
    return [r for i, d in enumerate(DAYS) for r in crude_day(d, 5000 + 10 * i, single_digit=d.year < 2020)]


def test_a_series_splits_into_one_file_a_day_that_joins_back_byte_for_byte(tmp_path):
    src = write_series(tmp_path / "crude_1m_current.csv", market())
    m = split.split(src, "CRUDEOIL", tmp_path / "out", built=date(2026, 11, 20), calendar=CAL)
    folder = tmp_path / "out" / "CRUDEOIL"
    assert sorted(m.days) == [d.isoformat() for d in DAYS]
    joined = HEADER.encode() + b"".join(
        DS.read_day(folder, d, m.days[d.isoformat()]).split(b"\n", 1)[1] for d in DAYS)
    assert joined == src.read_bytes()
    assert sum(e.rows for e in m.days.values()) == len(market())


def test_the_split_keeps_the_series_manifest_and_says_how_each_day_was_checked(tmp_path):
    src = write_series(tmp_path / "crude.csv", market(), as_of=date(2026, 3, 4))
    m = split.split(src, "CRUDEOIL", tmp_path / "out", built=date(2026, 11, 20), calendar=CAL)
    old = SS.read_manifest(src.with_suffix(".json"))
    assert (m.serves, m.roll, m.clock, m.interval, m.as_of, m.sessions) == (
        old.serves, old.roll, old.clock, old.interval, old.as_of, old.sessions)
    assert m.source.startswith(old.source) and "split" in m.source
    assert m.days["2019-10-01"].checked == DS.STAMPS_ONLY  # before the calendar starts
    assert m.days["2026-03-02"].checked == DS.CALENDAR_CHECK
    assert DS.read_manifest(tmp_path / "out" / "CRUDEOIL") == m


def test_the_layer_answers_the_split_series_as_it_answered_the_file(tmp_path):
    src = write_series(tmp_path / "crude.csv", market())
    split.split(src, "CRUDEOIL", tmp_path / "out", built=date(2026, 11, 20), calendar=CAL)
    old = L.Series.open("CRUDEOIL", src, session_open=datetime(2026, 1, 1, 9, 0).time())
    new = L.Prices(data_dir=tmp_path / "out").series("CRUDEOIL")
    for d in DAYS:
        for minute in range(9 * 60, 24 * 60, 5):
            t = datetime(d.year, d.month, d.day) + timedelta(minutes=minute)
            assert old.bar(t) == new.bar(t), t


def test_rows_that_do_not_add_up_to_the_manifests_count_are_refused_and_no_manifest_is_written(tmp_path):
    src = write_series(tmp_path / "crude.csv", market(), rows_in_manifest=len(market()) + 1)
    with pytest.raises(split.Refused, match="rows"):
        split.split(src, "CRUDEOIL", tmp_path / "out", built=date(2026, 11, 20), calendar=CAL)
    assert not (tmp_path / "out" / "CRUDEOIL" / "manifest.json").exists()


def test_a_series_that_fails_its_own_checks_is_refused_before_anything_is_written(tmp_path):
    src = write_series(tmp_path / "crude.csv", market())
    src.write_bytes(src.read_bytes() + b"2026-03-04 23:40:00,1,2,0,1,10\n")  # the digest no longer matches
    with pytest.raises(split.Refused, match="digest"):
        split.split(src, "CRUDEOIL", tmp_path / "out", built=date(2026, 11, 20), calendar=CAL)
    assert not (tmp_path / "out").exists()


def test_a_folder_split_already_is_never_overwritten(tmp_path):
    src = write_series(tmp_path / "crude.csv", market())
    split.split(src, "CRUDEOIL", tmp_path / "out", built=date(2026, 11, 20), calendar=CAL)
    with pytest.raises(split.Refused, match="already"):
        split.split(src, "CRUDEOIL", tmp_path / "out", built=date(2026, 11, 21), calendar=CAL)


def test_the_script_prints_counts_and_dates_never_a_price(tmp_path, capsys, monkeypatch):
    src = write_series(tmp_path / "crude.csv", market())
    monkeypatch.setattr(split.ms, "load_calendar", lambda: CAL)
    assert split.main([str(src), "CRUDEOIL", "--out", str(tmp_path / "out")]) == 0
    out = capsys.readouterr().out
    assert "4 day files" in out and "2019-10-01" in out and "2026-03-04" in out
    for r in market():
        for price in r.split(",")[1:5]:
            assert f",{price}" not in out and f" {price} " not in out
