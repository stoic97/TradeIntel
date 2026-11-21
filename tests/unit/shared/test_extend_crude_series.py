"""TICKET-893, TICKET-997: extending the crude series refuses a seam that disagrees and keeps only
finished sessions, and writes each new session as a day file through the one day writer.

A fake broker client stands in for the API, so nothing here needs the network or a token.
Every price is made up.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

import pytest

from scripts import extend_crude_series as ext
from services.shared.market import day_store as ds
from services.shared.market import series as ms

IST = timezone(timedelta(hours=5, minutes=30))
HEADER = b"timestamp,open,high,low,close,volume\n"
OPEN = time(9, 0)


def session(day: date, price: int) -> list[list]:
    """One made-up full session: 09:00 to 23:29, the close stepping by one point a minute."""
    out, t = [], datetime(day.year, day.month, day.day, 9, 0)  # noqa: DTZ001 - naive IST, as the series
    for i in range(14 * 60 + 30):
        p = price + i % 7
        out.append([t + timedelta(minutes=i), p, p + 2, p - 1, p + 1, 10])
    return out


def line(r, *, single_digit=False) -> bytes:
    stamp = f"{r[0]:%Y-%m-%d} {r[0].hour}:{r[0]:%M:%S}" if single_digit else f"{r[0]:%Y-%m-%d %H:%M:%S}"
    return (stamp + "," + ",".join(str(x) for x in r[1:]) + "\n").encode()


def held_store(folder, rows, *, single_digit=False) -> ds.DayManifest:
    """The day files a split would have made, written through the one writer."""
    store = ds.DayStore(folder, "CRUDEOIL")
    by_day: dict[date, list[bytes]] = {}
    for r in rows:
        by_day.setdefault(r[0].date(), []).append(line(r, single_digit=single_digit))
    for day, day_rows in by_day.items():
        store.put(day, HEADER, day_rows)
    return store.save(serves=ms.CRUDE_SERVES, source="made up for a test", roll=ms.ROLL_CONVENTION,
                      clock=ms.CLOCK, interval="1 minute", built=date(2026, 2, 28))


class FakeFyers:
    """Answers ``history`` like the broker: valid symbols only, candles as epoch seconds."""

    def __init__(self, rows, valid=("MCX:CRUDEOIL26MARFUT",)):
        self.rows, self.valid, self.asked = rows, set(valid), []

    def history(self, data):
        self.asked.append(data)
        if data["symbol"] not in self.valid:
            return {"s": "error", "message": "Invalid symbol provided"}
        assert data["cont_flag"] == "1" and data["resolution"] == "1"
        lo, hi = int(data["range_from"]), int(data["range_to"])
        c = [[int(r[0].replace(tzinfo=IST).timestamp()), *[float(x) for x in r[1:5]], r[5]] for r in self.rows]
        return {"s": "ok", "candles": [x for x in c if lo <= x[0] <= hi]}


DAYS = [date(2026, 2, 23) + timedelta(days=i) for i in range(12) if (date(2026, 2, 23) + timedelta(days=i)).weekday() < 5]
# Mon 23 Feb .. Fri 6 Mar 2026, ten weekdays. 3 Mar is closed in the test calendar below.
CAL = {date(2026, 3, 3): ms.SessionException(date(2026, 3, 3), "closed", "a made-up holiday")}


def market():
    return [r for i, d in enumerate(DAYS) if d != date(2026, 3, 3) for r in session(d, 5000 + 10 * i)]


def run(folder, rows, today, calendar=CAL):
    return ext.extend(folder, FakeFyers(rows), today=today, calendar=calendar, built=today, session_open=OPEN)


def test_the_near_month_symbol_is_the_first_contract_the_broker_still_knows():
    f = FakeFyers([], valid=("MCX:CRUDEOIL26APRFUT", "MCX:CRUDEOIL26MAYFUT"))
    assert ext.near_month_symbol(f, date(2026, 3, 20)) == "MCX:CRUDEOIL26APRFUT"
    assert [a["symbol"] for a in f.asked][:2] == ["MCX:CRUDEOIL26MARFUT", "MCX:CRUDEOIL26APRFUT"]


def test_extending_adds_only_finished_sessions_as_day_files_and_keeps_the_held_days(tmp_path):
    rows = market()
    folder = tmp_path / "CRUDEOIL"
    before = held_store(folder, [r for r in rows if r[0].date() <= date(2026, 2, 27)])
    held = {d: ds.day_path(folder, date.fromisoformat(d)).read_bytes() for d in before.days}
    today = date(2026, 3, 6)  # Friday's session is still open: it must not be kept
    m = run(folder, rows, today)
    assert {d: ds.day_path(folder, date.fromisoformat(d)).read_bytes() for d in before.days} == held
    assert max(m.days) == "2026-03-05" and "2026-03-06" not in m.days
    assert "2026-03-03" not in m.days
    assert sorted(set(m.days) - set(before.days)) == ["2026-03-02", "2026-03-04", "2026-03-05"]
    assert m.as_of == date(2026, 3, 5)
    assert all(m.days[d].rows == 14 * 60 + 30 for d in m.days)
    assert m.days["2026-03-04"].checked == ds.CALENDAR_CHECK
    assert m.serves == ("CRUDEOIL", "CRUDEOILM") and m.roll == ms.ROLL_CONVENTION
    assert any("2026-03-03" in s and "a made-up holiday" in s for s in m.sessions)
    assert "cont_flag=1" in m.source and m.source.startswith("made up for a test")
    assert ds.read_manifest(folder) == m


def test_a_seam_that_disagrees_with_the_held_bars_is_refused_and_nothing_is_written(tmp_path):
    rows = market()
    held = [list(r) for r in rows if r[0].date() <= date(2026, 2, 27)]
    held[-5][4] += 3  # the broker's construction changed: one held close no longer matches
    folder = tmp_path / "CRUDEOIL"
    before = held_store(folder, held)
    with pytest.raises(ext.Refused, match="seam"):
        run(folder, rows, date(2026, 3, 6))
    assert ds.read_manifest(folder) == before
    assert not ds.day_path(folder, date(2026, 3, 2)).exists()


def test_a_session_missing_without_a_reason_is_refused_and_nothing_is_written(tmp_path):
    rows = market()
    folder = tmp_path / "CRUDEOIL"
    before = held_store(folder, [r for r in rows if r[0].date() <= date(2026, 2, 27)])
    with pytest.raises(ext.Refused, match="2026-03-03"):
        run(folder, rows, date(2026, 3, 6), calendar={})
    assert ds.read_manifest(folder) == before
    assert not ds.day_path(folder, date(2026, 3, 2)).exists()


def test_a_second_run_extends_from_the_last_day_held(tmp_path):
    rows = market()
    folder = tmp_path / "CRUDEOIL"
    held_store(folder, [r for r in rows if r[0].date() <= date(2026, 2, 27)])
    run(folder, rows, date(2026, 3, 4))
    m = run(folder, rows, date(2026, 3, 7))
    assert m.as_of == date(2026, 3, 6) and "2026-03-02" in m.days and "2026-03-06" in m.days


def test_a_run_with_nothing_new_writes_nothing_and_says_so(tmp_path):
    rows = market()
    folder = tmp_path / "CRUDEOIL"
    held_store(folder, rows)
    with pytest.raises(ext.Refused, match="nothing new"):
        run(folder, rows, date(2026, 3, 7))


def test_a_folder_with_no_day_files_yet_is_refused_with_the_split_to_run(tmp_path):
    with pytest.raises(ext.Refused, match="split_series_by_day"):
        run(tmp_path / "CRUDEOIL", market(), date(2026, 3, 6))


def test_held_rows_with_single_digit_hours_are_read(tmp_path):
    rows = market()
    folder = tmp_path / "CRUDEOIL"
    held_store(folder, [r for r in rows if r[0].date() <= date(2026, 2, 27)], single_digit=True)
    m = run(folder, rows, date(2026, 3, 6))
    assert m.as_of == date(2026, 3, 5)
    first_row = ds.read_day(folder, date(2026, 2, 27), m.days["2026-02-27"]).splitlines()[1]
    assert first_row.startswith(b"2026-02-27 9:00")
