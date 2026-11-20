"""TICKET-998: the market sync adds each finished session, through the one day writer.

A fake broker stands in for Fyers and a fake clock for time, so nothing here touches the network,
sleeps, or needs a token. Every price is made up.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, time, timedelta, timezone

from sqlalchemy import create_engine, select

from services.production.db import models as m
from services.production.db.session import make_session, run_migrations
from services.production.market import fyers, sync
from services.production.prices import layer as L
from services.shared.market import closures as C
from services.shared.market import day_store as ds
from services.shared.market import series as ms

IST = timezone(timedelta(hours=5, minutes=30))
HEADER = b"timestamp,open,high,low,close,volume\n"
NOW = datetime(2026, 3, 7, 4, 0, tzinfo=UTC)  # Saturday 09:30 IST
TODAY = date(2026, 3, 7)
CAL = {date(2026, 1, 26): ms.SessionException(date(2026, 1, 26), "closed", "a made-up closure")}
CLOSED = {"NSE": C.Closures(frozenset({date(2026, 3, 4)}), date(2026, 11, 12)),
          "BSE": C.Closures(frozenset(), date(2026, 11, 12))}


def crude_session(day: date, price: int = 5000, start=(9, 0), end=(23, 30)) -> list[tuple]:
    """A made-up MCX session, one bar every ten minutes."""
    t = datetime(day.year, day.month, day.day, *start)
    stop = datetime(day.year, day.month, day.day, *end)
    out = []
    while t < stop:
        out.append((t, price, price + 3, price - 2, price + 1, 10))
        t += timedelta(minutes=10)
    return out


def nse_session(day: date, price: int = 22000) -> list[tuple]:
    return crude_session(day, price, start=(9, 15), end=(15, 30))


def line(r) -> bytes:
    return (f"{r[0]:%Y-%m-%d %H:%M:%S}," + ",".join(str(x) for x in r[1:]) + "\n").encode()


def seed(root, underlying, rows, check=None):
    store = ds.DayStore(root / underlying, underlying)
    by_day: dict[date, list[bytes]] = {}
    for r in rows:
        by_day.setdefault(r[0].date(), []).append(line(r))
    for day, day_rows in by_day.items():
        store.put(day, HEADER, day_rows, check=check)
    return store.save(serves=(underlying,), source="made up for a test", roll="", clock=ms.CLOCK,
                      interval="1 minute", built=date(2026, 3, 1))


class FakeFyers:
    """Answers ``history`` like the broker: known symbols only, candles as epoch seconds."""

    def __init__(self, bars: dict[str, list[tuple]], busy: int = 0):
        self.bars, self.asked, self.busy = bars, [], busy

    def history(self, data):
        self.asked.append(data)
        if self.busy:
            self.busy -= 1
            return {"s": "error", "code": 429, "message": "request limit reached"}
        rows = self.bars.get(data["symbol"])
        if rows is None:
            return {"s": "error", "code": -300, "message": "Invalid symbol provided"}
        lo, hi = int(data["range_from"]), int(data["range_to"])
        c = [[int(r[0].replace(tzinfo=IST).timestamp()), *[float(x) for x in r[1:5]], r[5]] for r in rows]
        return {"s": "ok", "candles": [x for x in c if lo <= x[0] <= hi]}


class Clock:
    def __init__(self):
        self.t, self.slept = 0.0, []

    def now(self):
        return self.t

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.t += seconds


def db():
    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)
    return make_session(engine)


def run(sess, root, broker, **kw):
    clock = Clock()
    paced = fyers.Paced(broker, clock=clock.now, sleep=clock.sleep)
    report = sync.run(sess, paced, root=root, today=kw.pop("today", TODAY), prices=L.Prices(data_dir=root),
                      calendar=CAL, closures=CLOSED, now=NOW, **kw)
    return report, clock


CRUDE = "MCX:CRUDEOIL26MARFUT"


def market():
    return {CRUDE: [r for d in (date(2026, 3, 2), date(2026, 3, 3), date(2026, 3, 5), date(2026, 3, 6),
                                date(2026, 3, 7)) for r in crude_session(d)]}


# ---------- finished sessions only, through the day writer ----------

def test_only_finished_sessions_after_the_last_day_held_are_added_never_today(tmp_path):
    seed(tmp_path, "CRUDEOIL", [r for d in (date(2026, 3, 2), date(2026, 3, 3)) for r in crude_session(d)])
    broker = FakeFyers(market())
    with db() as sess:
        report, _ = run(sess, tmp_path, broker)
    m_ = ds.read_manifest(tmp_path / "CRUDEOIL")
    assert sorted(m_.days) == ["2026-03-02", "2026-03-03", "2026-03-05", "2026-03-06"]
    assert m_.as_of == date(2026, 3, 6) and "2026-03-07" not in m_.days
    assert all(m_.days[d].checked == ds.CALENDAR_CHECK for d in ("2026-03-05", "2026-03-06"))
    probe, *fetches = [a for a in broker.asked if a["symbol"] == CRUDE]  # the first finds the near month
    assert fetches
    assert datetime.fromtimestamp(int(fetches[0]["range_from"]), IST).date() == date(2026, 3, 4)
    assert all(datetime.fromtimestamp(int(a["range_to"]), IST).date() < TODAY for a in fetches), \
        "today's session is never asked for"
    assert report["CRUDEOIL"]["added"] == 2 and report["CRUDEOIL"]["last"] == "2026-03-06"


def test_a_refused_day_is_recorded_and_the_next_day_is_still_written(tmp_path):
    seed(tmp_path, "CRUDEOIL", crude_session(date(2026, 3, 2)))
    bars = {CRUDE: crude_session(date(2026, 3, 3), start=(17, 0))  # evening only, and no reason for it
            + crude_session(date(2026, 3, 4)) + crude_session(date(2026, 3, 5))}
    with db() as sess:
        report, _ = run(sess, tmp_path, FakeFyers(bars))
        sess.commit()
        last = sess.scalars(select(m.MarketSyncRun).order_by(m.MarketSyncRun.id.desc())).first()
    days = ds.read_manifest(tmp_path / "CRUDEOIL").days
    assert "2026-03-03" not in days and "2026-03-04" in days and "2026-03-05" in days
    refused = report["CRUDEOIL"]["refused"]
    assert refused and refused[0][0] == "2026-03-03" and "evening only" in refused[0][1]
    assert last.result == "some days refused"
    assert "2026-03-03" in last.summary and "5000" not in last.summary, "counts and dates, never a price"


def test_an_index_is_checked_against_its_open_and_its_closures(tmp_path):
    seed(tmp_path, "NIFTY", nse_session(date(2026, 3, 2)))
    bars = {"NSE:NIFTY50-INDEX": nse_session(date(2026, 3, 3)) + nse_session(date(2026, 3, 4))
            + nse_session(date(2026, 3, 5))}
    with db() as sess:
        report, _ = run(sess, tmp_path, FakeFyers(bars))
    days = ds.read_manifest(tmp_path / "NIFTY").days
    assert days["2026-03-03"].checked == ds.OPEN_CHECK
    assert "2026-03-04" not in days, "the closures say NSE was shut on 4 Mar"
    assert report["NIFTY"]["refused"][0][0] == "2026-03-04"


def test_an_underlying_with_no_day_files_yet_is_named_and_never_asked_for(tmp_path):
    broker = FakeFyers(market())
    with db() as sess:
        report, _ = run(sess, tmp_path, broker)
    assert report["NIFTY"]["note"].startswith("no day files yet")
    assert not any(a["symbol"].startswith("NSE:NIFTY") for a in broker.asked)


def test_a_series_already_current_asks_for_nothing(tmp_path):
    seed(tmp_path, "CRUDEOIL", crude_session(date(2026, 3, 6)))
    broker = FakeFyers(market())
    with db() as sess:
        report, _ = run(sess, tmp_path, broker)
    assert report["CRUDEOIL"]["added"] == 0 and broker.asked == []


# ---------- the broker's limits ----------

def test_a_long_gap_is_asked_for_at_most_a_hundred_days_at_a_time_one_request_a_second(tmp_path):
    seed(tmp_path, "CRUDEOIL", crude_session(date(2025, 10, 1)))
    broker = FakeFyers(market())
    with db() as sess:
        _, clock = run(sess, tmp_path, broker)
    spans = [(int(a["range_to"]) - int(a["range_from"])) / 86400 for a in broker.asked]
    assert len(broker.asked) >= 3 and max(spans) <= 100
    assert len(clock.slept) == len(broker.asked) - 1 and all(s >= 1 for s in clock.slept)


def test_a_busy_broker_is_backed_off_and_asked_again():
    clock = Clock()
    broker = FakeFyers(market(), busy=2)
    paced = fyers.Paced(broker, clock=clock.now, sleep=clock.sleep)
    got = paced.history({"symbol": CRUDE, "range_from": "0", "range_to": "1", "cont_flag": "1", "resolution": "1"})
    assert got["s"] == "ok" and len(broker.asked) == 3
    assert clock.slept[:2] == [2, 4]


def test_a_broker_busy_past_its_retries_is_left_to_the_next_run():
    clock = Clock()
    paced = fyers.Paced(FakeFyers({}, busy=99), clock=clock.now, sleep=clock.sleep)
    assert paced.history({"symbol": CRUDE})["code"] == 429
    assert sum(clock.slept) < 120


# ---------- stock days on request ----------

def ask(sess, symbol, day):
    sess.add(m.MarketDayRequest(underlying=symbol, trading_day=day, requested_at=NOW, status="waiting", tries=0))
    sess.commit()


def test_a_stock_day_asked_for_is_fetched_into_its_own_folder(tmp_path):
    with db() as sess:
        ask(sess, "INFY", "2026-03-05")
        run(sess, tmp_path, FakeFyers({"NSE:INFY-EQ": nse_session(date(2026, 3, 5), price=1500)}))
        sess.commit()
        req = sess.scalars(select(m.MarketDayRequest)).one()
    assert req.status == "fetched" and req.tries == 1
    m_ = ds.read_manifest(tmp_path / "INFY")
    assert list(m_.days) == ["2026-03-05"] and m_.days["2026-03-05"].checked == ds.OPEN_CHECK
    assert L.Prices(data_dir=tmp_path).lookup("INFY", datetime(2026, 3, 5, 9, 15)).kind is L.Kind.BAR


def test_a_stock_the_broker_does_not_serve_stops_after_three_tries(tmp_path):
    with db() as sess:
        ask(sess, "NOSUCH", "2026-03-05")
        broker = FakeFyers({})
        for _ in range(4):
            run(sess, tmp_path, broker)
            sess.commit()
        req = sess.scalars(select(m.MarketDayRequest)).one()
    assert req.status == "gave up" and req.tries == 3 and "Invalid symbol" in req.reason
    assert len([a for a in broker.asked if a["symbol"] == "NSE:NOSUCH-EQ"]) == 3


def test_an_index_or_commodity_is_never_fetched_on_request(tmp_path):
    with db() as sess:
        ask(sess, "NIFTY", "2026-03-05")
        broker = FakeFyers({})
        run(sess, tmp_path, broker)
        sess.commit()
        req = sess.scalars(select(m.MarketDayRequest)).one()
    assert req.status == "gave up" and "kept whole" in req.reason
    assert broker.asked == []


def test_every_run_is_recorded_with_counts_and_dates(tmp_path):
    seed(tmp_path, "CRUDEOIL", crude_session(date(2026, 3, 3)))
    with db() as sess:
        run(sess, tmp_path, FakeFyers(market()))
        sess.commit()
        last = sess.scalars(select(m.MarketSyncRun)).one()
    assert last.result == "ok" and last.finished_at is not None
    summary = json.loads(last.summary)
    assert summary["CRUDEOIL"]["added"] == 2


def test_a_needs_login_run_touches_nothing_and_is_recorded(tmp_path):
    with db() as sess:
        sync.needs_login(sess, now=NOW)
        sess.commit()
        last = sess.scalars(select(m.MarketSyncRun)).one()
    assert last.result == "needs login" and list(tmp_path.iterdir()) == []


def test_prices_are_kept_to_the_brokers_precision_not_six_digits(tmp_path):
    seed(tmp_path, "SENSEX", crude_session(date(2026, 3, 2), 81234, start=(9, 15), end=(15, 30)))
    rows = [(r[0], 81234.55, 81240.15, 81230.05, 81236.85, 10) for r in nse_session(date(2026, 3, 3))]
    with db() as sess:
        run(sess, tmp_path, FakeFyers({"BSE:SENSEX-INDEX": rows}))
    got = L.Prices(data_dir=tmp_path).lookup("SENSEX", datetime(2026, 3, 3, 9, 15))
    assert str(got.bar.close) == "81236.85"


def test_the_crude_symbol_is_the_near_month_the_extend_script_chooses():
    from scripts import extend_crude_series as ext
    assert sync.near_month_symbol is ext.near_month_symbol
    assert sync.fetch is ext.fetch


def test_the_sync_decrypts_no_token_and_imports_nothing_from_research():
    import ast
    from pathlib import Path
    for path in Path("services/production/market").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module]
        assert not [n for n in names if n.startswith("services.research")], path
    assert "token" not in Path("services/production/market/sync.py").read_text(encoding="utf-8").lower()


def test_the_command_with_no_token_says_needs_login_exits_cleanly_and_touches_no_market_file(
        tmp_path, monkeypatch, capsys):
    from cryptography.fernet import Fernet

    from services.production.api import cli
    url = f"sqlite:///{(tmp_path / 'scope.db').as_posix()}"
    monkeypatch.setenv("SCOPE_FILE_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("SCOPE_MARKET_DIR", str(tmp_path / "market"))
    monkeypatch.setenv("FYERS_APP_ID", "MADEUP-100")
    monkeypatch.setenv("FYERS_SECRET_KEY", "made-up")
    monkeypatch.setenv("FYERS_REDIRECT_URI", "https://www.google.com")
    called = []
    monkeypatch.setattr(fyers, "history_client", lambda *a: called.append(a))
    cli.main(["--db", url, "init-db"])
    cli.main(["--db", url, "market-sync"])
    assert "needs login" in capsys.readouterr().out
    assert called == [] and not (tmp_path / "market").exists()
    with make_session(create_engine(url)) as sess:
        assert sess.scalars(select(m.MarketSyncRun)).one().result == "needs login"


_ = time  # the session times above are built from datetimes
