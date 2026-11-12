"""TICKET-893: extending the crude series refuses a seam that disagrees and keeps only finished sessions.

A fake broker client stands in for the API, so nothing here needs the network or a token.
Every price is made up.
"""

from __future__ import annotations

import csv
import hashlib
from datetime import date, datetime, timedelta, timezone

import pytest

from scripts import extend_crude_series as ext
from services.shared.market import series as ms

IST = timezone(timedelta(hours=5, minutes=30))


def session(day: date, price: int) -> list[list]:
    """One made-up full session: 09:00 to 23:29, the close stepping by one point a minute."""
    out, t = [], datetime(day.year, day.month, day.day, 9, 0)
    for i in range(14 * 60 + 30):
        p = price + i % 7
        out.append([t + timedelta(minutes=i), p, p + 2, p - 1, p + 1, 10])
    return out


def write_series(path, rows):
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for r in rows:
            w.writerow([r[0].strftime("%Y-%m-%d %H:%M:%S"), *r[1:]])


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


def test_the_near_month_symbol_is_the_first_contract_the_broker_still_knows():
    f = FakeFyers([], valid=("MCX:CRUDEOIL26APRFUT", "MCX:CRUDEOIL26MAYFUT"))
    assert ext.near_month_symbol(f, date(2026, 3, 20)) == "MCX:CRUDEOIL26APRFUT"
    assert [a["symbol"] for a in f.asked][:2] == ["MCX:CRUDEOIL26MARFUT", "MCX:CRUDEOIL26APRFUT"]


def test_extending_appends_only_finished_sessions_and_keeps_the_old_bytes(tmp_path):
    rows = market()
    base = tmp_path / "base.csv"
    write_series(base, [r for r in rows if r[0].date() <= date(2026, 2, 27)])
    old_bytes = base.read_bytes()
    out = tmp_path / "crude_1m_current.csv"
    today = date(2026, 3, 6)  # Friday's session is still open: it must not be kept
    m = ext.extend(base, out, FakeFyers(rows), today=today, calendar=CAL, built=today)
    data = out.read_bytes()
    assert data.startswith(old_bytes), "the bars already held are kept byte for byte"
    kept = {datetime.strptime(r["timestamp"], "%Y-%m-%d %H:%M:%S").date() for r in csv.DictReader(out.open())}
    assert max(kept) == date(2026, 3, 5)
    assert date(2026, 3, 3) not in kept
    assert m.as_of == date(2026, 3, 5)
    assert m.extended_from == date(2026, 3, 2)
    assert m.sha256 == hashlib.sha256(data).hexdigest()
    assert m.rows == len(kept) * (14 * 60 + 30)
    assert m.serves == ("CRUDEOIL", "CRUDEOILM") and m.roll == ms.ROLL_CONVENTION
    assert any("2026-03-03" in s and "a made-up holiday" in s for s in m.sessions)
    assert ms.read_manifest(ext.manifest_path(out)) == m


def test_a_seam_that_disagrees_with_the_held_bars_is_refused_and_nothing_is_written(tmp_path):
    rows = market()
    held = [list(r) for r in rows if r[0].date() <= date(2026, 2, 27)]
    held[-5][4] += 3  # the broker's construction changed: one held close no longer matches
    base = tmp_path / "base.csv"
    write_series(base, held)
    out = tmp_path / "out.csv"
    with pytest.raises(ext.Refused, match="seam"):
        ext.extend(base, out, FakeFyers(rows), today=date(2026, 3, 6), calendar=CAL, built=date(2026, 3, 6))
    assert not out.exists()


def test_a_session_missing_without_a_reason_is_refused_and_nothing_is_written(tmp_path):
    rows = market()
    base = tmp_path / "base.csv"
    write_series(base, [r for r in rows if r[0].date() <= date(2026, 2, 27)])
    out = tmp_path / "out.csv"
    with pytest.raises(ext.Refused, match="2026-03-03"):
        ext.extend(base, out, FakeFyers(rows), today=date(2026, 3, 6), calendar={}, built=date(2026, 3, 6))
    assert not out.exists()


def test_a_second_run_extends_the_current_file_from_its_own_end(tmp_path):
    rows = market()
    base = tmp_path / "base.csv"
    write_series(base, [r for r in rows if r[0].date() <= date(2026, 2, 27)])
    out = tmp_path / "crude_1m_current.csv"
    ext.extend(base, out, FakeFyers(rows), today=date(2026, 3, 4), calendar=CAL, built=date(2026, 3, 4))
    first = out.read_bytes()
    m = ext.extend(out, out, FakeFyers(rows), today=date(2026, 3, 7), calendar=CAL, built=date(2026, 3, 7))
    assert out.read_bytes().startswith(first)
    assert m.as_of == date(2026, 3, 6) and m.extended_from == date(2026, 3, 4)


def test_a_run_with_nothing_new_writes_nothing_and_says_so(tmp_path):
    rows = market()
    base = tmp_path / "base.csv"
    write_series(base, rows)
    with pytest.raises(ext.Refused, match="nothing new"):
        ext.extend(base, tmp_path / "o.csv", FakeFyers(rows), today=date(2026, 3, 7), calendar=CAL,
                   built=date(2026, 3, 7))
