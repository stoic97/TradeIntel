# ruff: noqa: DTZ001 - the series are naive IST by convention (TICKET-893); so are these bars
"""TICKET-1009: after you closed.

The bar-figure job stores the 30 minutes after each exit, in points in the trade's direction, the
exit's close as zero. A losing trade *came back* when, within them, the underlying passed the
price he was measured from at entry. The page reads stored figures only. Every bar here is made
up, and every expected minute is worked by hand from the bars written below.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import inspect, select

from services.production.api import after_closed as ACL
from services.production.db import models as m
from services.production.market import bar_figures as BF
from services.production.prices import layer as L
from services.shared.market import day_store as ds
from services.shared.market import series as ms

IST = timezone(timedelta(hours=5, minutes=30))
HEADER = b"timestamp,open,high,low,close,volume\n"
MON = date(2026, 3, 2)
P = 22000


def day(day_: date, closes: dict[tuple[time, time], int]) -> list[bytes]:
    """A made-up NIFTY session, one bar a minute at P, with spans of minutes set to a close."""
    t, stop, out = datetime.combine(day_, time(9, 15)), datetime.combine(day_, time(15, 30)), []
    while t < stop:
        c = next((v for (a, b), v in closes.items() if a <= t.time() < b), P)
        out.append(f"{t:%Y-%m-%d %H:%M:%S},{c},{c},{c},{c},10\n".encode())
        t += timedelta(minutes=1)
    return out


SPANS = {
    (time(9, 30), time(9, 42)): P - 10,   # long 1 closes at 09:30, 10 down; flat until 09:42
    (time(9, 42), time(9, 45)): P + 1,    # 12 minutes after its exit: past the entry
    (time(11, 10), time(11, 45)): P - 20,  # long 2 closes at 11:10, 20 down, and stays there
    (time(13, 10), time(13, 15)): P + 10,  # the put closes at 13:10 with NIFTY 10 up
    (time(13, 15), time(13, 20)): P - 1,   # 5 minutes after its exit: past its entry, the other way
    (time(15, 20), time(15, 30)): P - 5,   # long 4 closes at 15:20; the session ends at 15:30
}


@pytest.fixture()
def prices(tmp_path):
    store = ds.DayStore(tmp_path / "NIFTY", "NIFTY")
    store.put(MON, HEADER, day(MON, SPANS))
    store.save(serves=("NIFTY",), source="made up for a test", roll="", clock=ms.CLOCK,
               interval="1 minute", built=date(2026, 3, 20))
    return L.Prices(data_dir=tmp_path)


def at(hh: int, mm: int) -> datetime:
    return datetime(MON.year, MON.month, MON.day, hh, mm, tzinfo=IST)


def trade(trip_id: str, entry: datetime, exit_: datetime, option_type="CE", direction="LONG"):
    return BF.Position(trip_id=trip_id, legs=(BF.Leg(
        exchange="NSE", symbol="NIFTY", segment="OPT", direction=direction, option_type=option_type,
        strike=Decimal(P), quantity=75, expiry=date(2026, 3, 26), entry_ts=entry, exit_ts=exit_),))


# ---------- the worker stores the 30 minutes after the exit ----------

def test_a_losing_long_comes_back_past_its_entry_12_minutes_after_it_closed(prices):
    got = BF.measure(trade("l1", at(9, 20), at(9, 30)), prices)
    assert got.took == Decimal(-10)
    assert got.after_exit[0] == 0 and len(got.after_exit) == ACL.HORIZON + 1
    assert got.after_exit[11] == 0 and got.after_exit[12] == Decimal(11)  # 22001 less 21990
    assert ACL.came_back_at(got.after_exit, got.took) == 12


def test_a_losing_long_that_stays_down_never_comes_back(prices):
    got = BF.measure(trade("l2", at(11, 0), at(11, 10)), prices)
    assert got.took == Decimal(-20)
    assert ACL.came_back_at(got.after_exit, got.took) is None


def test_a_bought_put_comes_back_when_the_market_falls_past_its_entry(prices):
    got = BF.measure(trade("p1", at(13, 0), at(13, 10), option_type="PE"), prices)
    assert got.direction == -1 and got.took == Decimal(-10)
    assert got.after_exit[5] == Decimal(11)  # (21999 less 22010), the other way
    assert ACL.came_back_at(got.after_exit, got.took) == 5


def test_a_path_that_reaches_the_session_end_stops_there(prices):
    got = BF.measure(trade("l4", at(15, 10), at(15, 20)), prices)
    assert len(got.after_exit) == 10  # 15:20 itself, then 15:21 to 15:29


def test_the_job_stores_the_path_after_the_exit(prices):
    got = BF.measure(trade("l1", at(9, 20), at(9, 30)), prices)
    assert json.loads(BF._series_json(got.after_exit))[12] == "11"


# ---------- the fact reads stored figures only ----------

def stored(path: list[int], took: int, underlying="NIFTY") -> dict:
    return {"underlying": underlying, "reason": None, "took": Decimal(took),
            "after_exit": tuple(Decimal(v) for v in path)}


def ctx_of(rows: list[tuple[str, int, dict]]) -> dict:
    return {"trips": [SimpleNamespace(trip_id=t, net=Decimal(n)) for t, n, _r in rows],
            "bars_after_close": {t: r for t, _n, r in rows}}


def test_a_winning_trade_is_never_counted_as_coming_back():
    rows = [("w", 500, stored([0, 30, 40], 25)), ("l", -500, stored([0, 3, 4], -10))]
    v = ACL.view(ctx_of(rows))
    assert v["losers"] == 1 and v["came_back"] == 0 and v["winners"] == 1


def test_thirty_losing_trades_draw_the_line_and_count_the_ones_that_came_back():
    rows = [(f"l{i}", -100, stored([0] + [i % 3 * 6] * 30, -10)) for i in range(30)]
    rows += [("w0", 100, stored([0, 1, 2], 5))]
    v = ACL.view(ctx_of(rows))
    assert v["enough"] and v["losers"] == 30
    assert v["came_back"] == 10  # every third trade reaches 12 points, 2 past its 10-point loss
    assert set(v["came_back_ids"]) == {f"l{i}" for i in range(30) if i % 3 == 2}
    g = ACL.geometry(v)
    assert g and {p["role"] for p in g["parts"]} >= {"acl-losers", "acl-winners", "acl-zero"}
    assert str(ACL.figure(v)) == "10 of 30 trades"


def test_under_thirty_losing_trades_is_not_enough_and_says_how_many_it_needs():
    v = ACL.view(ctx_of([(f"l{i}", -100, stored([0, 20], -10)) for i in range(29)]))
    assert not v["enough"] and ACL.geometry(v) is None and v["minimum"] == 30


def test_a_trade_with_no_stored_path_is_counted_not_dropped():
    v = ACL.view({"trips": [SimpleNamespace(trip_id="x", net=Decimal(-5))], "bars_after_close": {}})
    assert v["not_measured"] == 1 and v["reasons"] == [(ACL.NOT_WORKED_OUT, 1)]


def test_one_underlying_at_a_time_with_chips():
    rows = [(f"n{i}", -1, stored([0, 1], -5)) for i in range(3)]
    rows += [(f"c{i}", -1, stored([0, 1], -5, "CRUDEOIL")) for i in range(2)]
    v = ACL.view(ctx_of(rows))
    assert v["underlying"] == "NIFTY" and [c["underlying"] for c in v["chips"]] == ["NIFTY", "CRUDEOIL"]
    assert ACL.view(ctx_of(rows), "CRUDEOIL")["losers"] == 2


# ---------- the page ----------

def test_the_fact_page_renders_without_reading_a_bar(client, monkeypatch):
    def boom(*a, **kw):
        raise AssertionError("a page read bars")

    monkeypatch.setattr(L.Prices, "lookup", boom)
    monkeypatch.setattr(L.Prices, "series", boom)
    monkeypatch.setattr(BF, "measure", boom)
    r = client.get("/mirror/fact/after-close")
    assert r.status_code == 200
    section = r.text.split('id="after-close"', 1)[1].split("</section>", 1)[0]
    assert "<script" not in section  # the layout's own dwell script is not this fact's
    assert "this needs" in r.text


def test_the_page_never_says_what_he_would_have_made(client):
    text = client.get("/mirror/fact/after-close").text.lower()
    for word in ("could have", "would have", "should have", "left on the table", "missed", "too early"):
        assert word not in text, word


def test_the_migration_adds_the_column_on_a_fresh_database(tmp_path):
    from services.production.db.session import make_engine, run_migrations
    e = make_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
    run_migrations(e)
    assert "after_exit" in {c["name"] for c in inspect(e).get_columns("bar_trade_figure")}


def test_the_stored_row_keeps_the_path(engine):
    from services.production.db.session import make_session
    from services.shared.schemas import scope_v1 as s
    with make_session(engine) as sess:
        trader = m.Trader(display_name="t", login_id="t1009", password_hash="x", created_at=datetime.now(UTC))
        sess.add(trader)
        sess.flush()
        raw = m.RawFile(trader_id=trader.id, sha256="9" * 64, original_name="t.csv", size=1, stored_path="x",
                        uploaded_at=datetime.now(UTC))
        sess.add(raw)
        sess.flush()
        imp = m.Import(trader_id=trader.id, raw_file_id=raw.id, source_account="A", adapter_id="dhan_tradebook_v1",
                       adapter_version="1", filemap_version="1", code_version="t",
                       outcome=s.ImportOutcome.ACCEPTED_PARTIAL_FIELDS, rows_in=1, rows_parsed=1, rows_excluded=0,
                       fees_available=False, version_no=1, trips_reconstructed=1, density_default_unit="day",
                       created_at=datetime.now(UTC))
        sess.add(imp)
        sess.flush()
        sess.add(m.BarTradeFigure(import_id=imp.id, trip_id="a", underlying="NIFTY", reason=None, way="1",
                                  against="0", took="-10", path=None, short=False, after_exit='["0", "11"]'))
        sess.flush()
        got = ACL.load(sess, imp)
    assert got["a"]["after_exit"] == (Decimal(0), Decimal(11)) and got["a"]["took"] == Decimal(-10)


def test_nothing_under_api_but_the_cli_names_the_worker():
    for path in Path("services/production/api").rglob("*.py"):
        if path.name == "cli.py":
            continue
        assert "bar_figures" not in path.read_text(encoding="utf-8"), path
