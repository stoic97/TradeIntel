
"""TICKET-999: bar figures worked out off the web app.

For each trade, in underlying points and in the trade's direction: how far the market went his
way while he held it, how far it went against him, and what he took; and the 30 minutes after he
clicked, beside the same from random moments. Measured from the close of the entry minute. A trade
that can't be measured is counted with its reason, never dropped. Every bar here is made up, and
every expected figure is worked by hand from the bars written below.
"""

from __future__ import annotations

import json
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

def test_a_bought_call_is_measured_from_the_entry_minutes_close_in_points(prices):
    got = BF.measure(position("t1", leg(entry=at(MON, 9, 20, 30), exit_=at(MON, 9, 40, 10))), prices)
    assert got.reason is None and got.underlying == "NIFTY" and got.direction == 1
    assert (got.way, got.against, got.took) == (Decimal(62), Decimal(18), Decimal(21))


def test_a_bought_put_is_measured_the_other_way(prices):
    got = BF.measure(position("t2", leg(option_type="PE", entry=at(MON, 10, 0), exit_=at(MON, 10, 10))), prices)
    assert got.direction == -1
    assert (got.way, got.against, got.took) == (Decimal(50), Decimal(10), Decimal(10))


def test_a_sold_call_needs_the_market_down(prices):
    got = BF.measure(position("t3", leg(direction="SHORT", entry=at(MON, 11, 0), exit_=at(MON, 11, 5))), prices)
    assert got.direction == -1
    assert (got.way, got.against, got.took) == (Decimal(0), Decimal(5), Decimal(-5))


def test_a_trade_held_overnight_reads_every_day_it_spans(prices):
    fut = leg(symbol="CRUDEOIL", exchange="MCX", segment="FUT", option_type=None, strike=None,
              quantity=1, expiry=date(2026, 3, 19), entry=at(date(2026, 3, 2), 22, 0),
              exit_=at(date(2026, 3, 3), 9, 30))
    got = BF.measure(position("t4", fut), prices)
    assert got.reason is None
    assert (got.way, got.against, got.took) == (Decimal(40), Decimal(30), Decimal(12))


def test_a_spread_with_no_single_direction_is_counted_with_its_reason(prices):
    straddle = position("t5", leg(entry=at(MON, 9, 20), exit_=at(MON, 9, 40)),
                        leg(option_type="PE", entry=at(MON, 9, 20), exit_=at(MON, 9, 40)))
    got = BF.measure(straddle, prices)
    assert got.reason == BF.NO_DIRECTION and got.way is None and got.path == ()


def test_a_bull_call_spread_takes_its_bought_legs_direction(prices):
    spread = position("t6", leg(entry=at(MON, 9, 20), exit_=at(MON, 9, 40)),
                      leg(direction="SHORT", strike=Decimal(22200), entry=at(MON, 9, 20), exit_=at(MON, 9, 40)))
    assert BF.measure(spread, prices).direction == 1


def test_a_crude_option_on_next_months_contract_is_left_out_with_its_reason(prices):
    april = leg(symbol="CRUDEOIL", exchange="MCX", option_type="CE", strike=Decimal(5000), quantity=100,
                expiry=date(2026, 4, 15), entry=at(date(2026, 3, 10), 10, 0), exit_=at(date(2026, 3, 10), 10, 20))
    got = BF.measure(position("t7", april), prices)
    assert got.reason == BF.MONTH and got.way is None


def test_a_crude_option_on_the_near_month_is_measured(prices):
    march = leg(symbol="CRUDEOIL", exchange="MCX", option_type="CE", strike=Decimal(5000), quantity=100,
                expiry=date(2026, 3, 16), entry=at(date(2026, 3, 10), 10, 0), exit_=at(date(2026, 3, 10), 10, 20))
    assert BF.measure(position("t8", march), prices).reason is None


def test_the_near_month_rolls_after_the_futures_expiry_on_the_19th():
    closed = frozenset({date(2026, 4, 3)})
    assert BF.crude_future_expiry(2026, 3, closed) == date(2026, 3, 19)       # a Thursday
    assert BF.crude_future_expiry(2026, 4, closed) == date(2026, 4, 17)       # the 19th is a Sunday
    assert BF.near_month(date(2026, 3, 19), closed) == (2026, 3)
    assert BF.near_month(date(2026, 3, 20), closed) == (2026, 4)
    assert BF.near_month(date(2026, 12, 21), closed) == (2027, 1)


def test_an_instrument_with_no_series_is_counted_with_its_reason(prices):
    got = BF.measure(position("t9", leg(symbol="BANKNIFTY", entry=at(MON, 9, 20), exit_=at(MON, 9, 40))), prices)
    assert got.reason == BF.NO_SERIES


# ---------- after you clicked ----------

def test_the_path_is_the_close_each_minute_after_the_entry_minute_in_his_direction(prices):
    got = BF.measure(position("t1", leg(entry=at(MON, 9, 20, 30), exit_=at(MON, 9, 40))), prices)
    assert len(got.path) == BF.HORIZON + 1 and got.path[0] == 0 and not got.short
    assert got.path[20] == Decimal(21)  # 09:40's close, 20 minutes after 09:20
    assert set(got.path) - {Decimal(0), Decimal(21)} == set()


def test_a_path_that_runs_past_the_session_end_stops_there_and_is_counted_short(prices):
    got = BF.measure(position("late", leg(entry=at(MON, 15, 15), exit_=at(MON, 15, 29))), prices)
    assert got.short and len(got.path) == 15  # 15:15 itself, then 15:16 to 15:29


def test_random_moments_are_drawn_the_same_way_every_time(prices):
    trades = [BF.measure(position(f"t{i}", leg(entry=at(MON, 9, 20 + 7 * i), exit_=at(MON, 10, 7 * i))), prices)
              for i in range(4)]
    one = BF.random_paths(trades, prices, key="trader:1:import:9")
    two = BF.random_paths(trades, prices, key="trader:1:import:9")
    assert one == two and len(one) == len(trades)
    other = BF.random_paths(trades, prices, key="trader:1:import:10")
    assert [r.moment for r in one] != [r.moment for r in other]
    for r, t in zip(one, trades, strict=True):
        assert (r.moment.year, r.moment.month, r.moment.hour) == (t.entry_minute.year, t.entry_minute.month,
                                                                   t.entry_minute.hour)
        assert all(abs((r.moment - x.entry_minute).total_seconds()) >= 30 * 60 for x in trades)


def test_the_summary_holds_medians_his_middle_half_and_the_random_middle_95(prices):
    trades = [BF.measure(position(f"t{i}", leg(entry=at(MON, 9, 20), exit_=at(MON, 9, 40))), prices)
              for i in range(3)]
    s = BF.summarise("NIFTY", trades, BF.random_paths(trades, prices, key="k"))
    assert s.measured == 3
    assert len(s.his_median) == BF.HORIZON + 1 and s.his_median[20] == Decimal(21)
    assert s.his_q25[20] == s.his_q75[20] == Decimal(21)
    assert len(s.random_lo) == len(s.random_hi) == BF.HORIZON + 1
    assert len(s.faint) == 3


def test_at_most_200_faint_paths_chosen_evenly_through_the_record():
    picked = BF.evenly(list(range(1000)), BF.FAINT)
    assert len(picked) == 200 and picked[0] == 0 and picked[-1] == 999
    assert BF.evenly([1, 2, 3], BF.FAINT) == [1, 2, 3]


# ---------- the job, off the web app ----------

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


def test_the_job_stores_each_trade_asks_for_the_stock_days_it_lacks_and_waits(sess, prices):
    _trader, imp = a_trader_with_trips(sess, "job1")
    BF.run(sess, prices, now=datetime(2026, 3, 20, 5, 0, tzinfo=UTC))
    rows = {r.trip_id: r for r in sess.scalars(select(m.BarTradeFigure).where(m.BarTradeFigure.import_id == imp.id))}
    assert rows["a"].reason is None and Decimal(rows["a"].took) == Decimal(21)
    assert rows["b"].reason == BF.WAITING_FOR_DAY and rows["b"].underlying == "INFY"
    asked = sess.scalars(select(m.MarketDayRequest).where(m.MarketDayRequest.underlying == "INFY")).all()
    assert [(r.trading_day, r.status) for r in asked] == [("2026-03-02", "waiting")]
    job = sess.scalars(select(m.BarFigureJob).where(m.BarFigureJob.import_id == imp.id)).one()
    assert job.state == BF.WAITING and job.waiting_days == 1
    prov = json.loads(job.provenance)
    assert prov["code_version"] and prov["days"]["NIFTY"]["2026-03-02"]


def test_a_waiting_job_is_filled_when_its_day_arrives(sess, prices, tmp_path):
    _trader, imp = a_trader_with_trips(sess, "job2")
    BF.run(sess, prices, now=datetime(2026, 3, 20, 5, 0, tzinfo=UTC))
    seed(tmp_path, "INFY", {MON: day_rows(MON, time(9, 15), time(15, 30), 1500)})
    BF.run(sess, L.Prices(data_dir=tmp_path), now=datetime(2026, 3, 20, 5, 10, tzinfo=UTC))
    rows = {r.trip_id: r for r in sess.scalars(select(m.BarTradeFigure).where(m.BarTradeFigure.import_id == imp.id))}
    assert rows["b"].reason is None and Decimal(rows["b"].took) == 0
    assert sess.scalars(select(m.BarFigureJob).where(m.BarFigureJob.import_id == imp.id)).one().state == BF.DONE
    summary = sess.scalars(select(m.BarPathSummary).where(m.BarPathSummary.import_id == imp.id)).all()
    assert sorted(s.underlying for s in summary) == ["INFY", "NIFTY"]


def test_deleting_the_trader_removes_his_job_and_figures(sess, prices):
    from services.production.accounts import deletion
    from services.production.accounts.file_store import FileStore, generate_key
    trader, imp = a_trader_with_trips(sess, "job3")
    BF.run(sess, prices, now=datetime(2026, 3, 20, 5, 0, tzinfo=UTC))
    deletion.delete_trader(sess, FileStore(Path(prices.data_dir) / "files", generate_key()), trader=trader)
    for model in (m.BarFigureJob, m.BarTradeFigure, m.BarPathSummary):
        assert sess.scalars(select(model).where(model.import_id == imp.id)).all() == [], model.__name__


def test_an_upload_records_its_job_and_nothing_more(sess):
    source = Path("services/production/ctr/intake/persist.py").read_text(encoding="utf-8")
    assert "m.BarFigureJob(" in source
    assert "bar_figures" not in source and "Prices(" not in source and "day_store" not in source


def test_no_page_works_out_a_bar_figure():
    for path in Path("services/production/api").rglob("*.py"):
        if path.name == "cli.py":
            continue
        text = path.read_text(encoding="utf-8")
        assert "bar_figures" not in text, f"{path} imports the bar-figure worker; pages read stored figures"
