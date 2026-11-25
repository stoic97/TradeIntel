"""TICKET-1011 gate 1: the worker stores each traded day's range, high minus low in points.

For every (underlying, trading day) a trader traded, read from that one day file: the session's
highest high less its lowest low, with the day file's sha256. Stored on ``bar_day_range``, deleted
with the trader. A crude trade the worker leaves out for "contract month differs" still gives its
day a range, because the range is the series' day, not the trade's. Every bar is made up; the
expected ranges are worked by hand from the bars written below:

* NIFTY, 2 Mar: the flat session is 22000; the highest high is 22062 (09:25), the lowest low is
  21950 (10:05). Range 22062 - 21950 = 112.
* CRUDEOIL, 2 Mar: flat at 5000 with one high of 5040 (22:30). Range 5040 - 5000 = 40.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from services.production.db import models as m
from services.production.market import bar_figures as BF
from services.production.prices import layer as L
from services.shared.market import day_store as ds
from services.shared.market import series as ms

IST = timezone(timedelta(hours=5, minutes=30))
HEADER = b"timestamp,open,high,low,close,volume\n"
MON = date(2026, 3, 2)
P = 22000


def day_rows(day: date, start: time, end: time, price: int, overrides=None) -> list[bytes]:
    """A flat made-up session at ``price``, one bar a minute, with some bars set by hand."""
    overrides = overrides or {}
    t, stop, out = datetime.combine(day, start), datetime.combine(day, end), []
    while t < stop:
        o, h, low, c = overrides.get(t.time(), (price, price, price, price))
        out.append(f"{t:%Y-%m-%d %H:%M:%S},{o},{h},{low},{c},10\n".encode())
        t += timedelta(minutes=1)
    return out


def seed(root: Path, underlying: str, days: dict[date, list[bytes]], as_of: date | None = None) -> None:
    store = ds.DayStore(root / underlying, underlying)
    for day, rows in days.items():
        store.put(day, HEADER, rows)
    store.save(serves=(underlying,), source="made up for a test", roll="", clock=ms.CLOCK,
               interval="1 minute", built=date(2026, 3, 20), as_of=as_of)


NIFTY_MON = {
    time(9, 25): (P, P + 62, P, P),        # trade 1's best
    time(9, 30): (P, P, P - 18, P),        # trade 1's worst
    time(9, 40): (P, P + 21, P, P + 21),   # trade 1's exit close
    time(10, 5): (P, P, P - 50, P),        # trade 2 (a bought put): its best
    time(10, 7): (P, P + 10, P, P),        # and its worst
    time(10, 10): (P, P, P - 10, P - 10),  # its exit close
    time(11, 5): (P, P + 5, P, P + 5),     # trade 3 (a sold call): against him at the exit
}


@pytest.fixture()
def prices(tmp_path):
    seed(tmp_path, "NIFTY", {MON: day_rows(MON, time(9, 15), time(15, 30), P, NIFTY_MON),
                             MON + timedelta(days=1): day_rows(MON + timedelta(days=1), time(9, 15),
                                                               time(15, 30), P)})
    crude = {}
    for d in (date(2026, 3, 2), date(2026, 3, 3), date(2026, 3, 10)):
        over = {}
        if d == date(2026, 3, 2):
            over = {time(22, 30): (5000, 5040, 5000, 5000)}   # the overnight trade's best, day one
        if d == date(2026, 3, 3):
            over = {time(9, 10): (5000, 5000, 4970, 5000),    # its worst, day two
                    time(9, 30): (5000, 5012, 5000, 5012)}    # its exit close
        crude[d] = day_rows(d, time(9, 0), time(23, 30), 5000, over)
    seed(tmp_path, "CRUDEOIL", crude)
    return L.Prices(data_dir=tmp_path)


def at(day: date, hh: int, mm: int, ss: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hh, mm, ss, tzinfo=IST)


def leg(symbol="NIFTY", exchange="NSE", segment="OPT", direction="LONG", option_type="CE",
        strike=Decimal(22000), quantity=75, expiry=date(2026, 3, 26), entry=None, exit_=None):
    return BF.Leg(exchange=exchange, symbol=symbol, segment=segment, direction=direction,
                  option_type=option_type, strike=strike, quantity=quantity, expiry=expiry,
                  entry_ts=entry, exit_ts=exit_)


def position(trip_id, *legs):
    return BF.Position(trip_id=trip_id, legs=tuple(legs))


# ---------- went your way, against you, you took ----------


def a_trader_with_trips(sess, store_key="t"):
    from services.shared.schemas import scope_v1 as s
    trader = m.Trader(display_name="t", login_id=f"t-{store_key}", password_hash="x", created_at=datetime.now(UTC))
    sess.add(trader)
    sess.flush()
    raw = m.RawFile(trader_id=trader.id, sha256=store_key.ljust(64, "0"), original_name="t.csv", size=1,
                    stored_path="x", uploaded_at=datetime.now(UTC))
    sess.add(raw)
    sess.flush()
    imp = m.Import(trader_id=trader.id, raw_file_id=raw.id, source_account="A", adapter_id="dhan_tradebook_v1",
                   adapter_version="1", filemap_version="1", code_version="t",
                   outcome=s.ImportOutcome.ACCEPTED_PARTIAL_FIELDS, rows_in=1, rows_parsed=1, rows_excluded=0,
                   fees_available=False, version_no=1, trips_reconstructed=2, density_default_unit="day",
                   created_at=datetime.now(UTC))
    sess.add(imp)
    sess.flush()
    for trip_id, symbol, day in (("a", "NIFTY", MON), ("b", "INFY", MON)):
        sess.add(m.Trip(
            import_id=imp.id, trip_id=trip_id, trading_day=day.isoformat(), exchange="NSE", symbol=symbol,
            segment="OPT" if symbol == "NIFTY" else "EQ", direction="LONG",
            option_type="CE" if symbol == "NIFTY" else None, strike=Decimal(22000) if symbol == "NIFTY" else None,
            entry_ts=at(day, 9, 20, 30).astimezone(UTC), exit_ts=at(day, 9, 40).astimezone(UTC), quantity=1,
            entry_price=Decimal(100), exit_price=Decimal(105), gross=Decimal(5), fees=Decimal(0), net=Decimal(5),
            fees_available=False, risk_unit_source=s.RiskUnitSourceV1.PREMIUM_PAID))
    sess.add(m.BarFigureJob(import_id=imp.id, trader_id=trader.id, state=BF.PENDING, requested_at=datetime.now(UTC)))
    sess.flush()
    return trader, imp


@pytest.fixture()
def sess():
    import os

    from services.production.db.session import make_engine, make_session, run_migrations
    e = make_engine(os.environ["SCOPE_DB"])
    run_migrations(e)
    with make_session(e) as s:
        yield s



# ---------- the range of a day, worked out by hand ----------

def test_a_days_range_is_its_highest_high_less_its_lowest_low(prices):
    got = BF.day_range(prices, "NIFTY", MON)
    assert got is not None and got[0] == Decimal(112)


def test_a_crude_trade_left_out_for_its_month_still_gives_its_day_a_range(prices):
    april = leg(symbol="CRUDEOIL", exchange="MCX", option_type="CE", strike=Decimal(5000), quantity=100,
                expiry=date(2026, 4, 15), entry=at(date(2026, 3, 2), 10, 0), exit_=at(date(2026, 3, 2), 10, 20))
    p = position("c1", april)
    assert BF.measure(p, prices).reason == BF.MONTH
    ranges = BF.day_ranges([p], prices)
    assert ranges[("CRUDEOIL", "2026-03-02")][0] == Decimal(40)


def test_a_day_with_no_series_has_no_range(prices):
    stock = leg(symbol="INFY", segment="EQ", option_type=None, strike=None, quantity=1, expiry=None,
                entry=at(MON, 9, 20), exit_=at(MON, 9, 40))
    assert BF.day_ranges([position("s1", stock)], prices) == {}


# ---------- stored by the worker, read by the page, deleted with him ----------

def test_the_job_stores_each_traded_days_range_with_its_day_files_sha(sess, prices):
    _trader, imp = a_trader_with_trips(sess, "range1")
    BF.run(sess, prices, now=datetime(2026, 3, 20, 5, 0, tzinfo=UTC))
    rows = sess.scalars(select(m.BarDayRange).where(m.BarDayRange.import_id == imp.id)).all()
    assert [(r.underlying, r.day, Decimal(r.range_points)) for r in rows] == [("NIFTY", "2026-03-02", Decimal(112))]
    sha = prices.series("NIFTY").manifest.days["2026-03-02"].sha256
    assert rows[0].sha256 == sha


def test_the_market_row_reads_the_stored_ranges(sess, prices):
    from services.production.api import process_bars
    _trader, imp = a_trader_with_trips(sess, "range2")
    BF.run(sess, prices, now=datetime(2026, 3, 20, 5, 0, tzinfo=UTC))
    assert process_bars.ranges(sess, imp.id) == {("NIFTY", "2026-03-02"): Decimal(112)}


def test_deleting_the_trader_removes_his_day_ranges(sess, prices):
    from services.production.accounts import deletion
    from services.production.accounts.file_store import FileStore, generate_key
    trader, imp = a_trader_with_trips(sess, "range3")
    BF.run(sess, prices, now=datetime(2026, 3, 20, 5, 0, tzinfo=UTC))
    deletion.delete_trader(sess, FileStore(Path(prices.data_dir) / "files", generate_key()), trader=trader)
    assert sess.scalars(select(m.BarDayRange).where(m.BarDayRange.import_id == imp.id)).all() == []
