# ruff: noqa: DTZ001 - the series are naive IST by convention (TICKET-893); so are these bars
"""TICKET-1000: your day on the market chart.

The day page draws the underlying's 5-minute candles for that day, folded from that one day's
file, with each trade's entry and exit marked at the underlying's close, and under each trade the
figures 999 stored: how far it went his way, against him, and what he took. Every bar and trade
here is made up, and every expected figure is worked by hand from them.
"""

from __future__ import annotations

import builtins
import re
from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services.production.accounts import auth
from services.production.accounts.consent import CURRENT as CONSENT_TEXT
from services.production.api import day_chart as DC
from services.production.api.app import create_app
from services.production.db import models as m
from services.production.db.session import make_engine, make_session, run_migrations
from services.production.market import bar_figures
from services.production.prices import layer as L
from services.shared.market import day_store as ds
from services.shared.market import series as ms
from services.shared.schemas import scope_v1 as s

IST = timezone(timedelta(hours=5, minutes=30))
HEADER = b"timestamp,open,high,low,close,volume\n"
CSRF = re.compile(r'name="csrf_token"\s+value="([^"]+)"')
MON, TUE = date(2026, 3, 2), date(2026, 3, 3)
P = 22000


def rows(day, start, end, price, overrides=None):
    overrides, out, t = overrides or {}, [], datetime.combine(day, start)
    while t < datetime.combine(day, end):
        o, h, low, c = overrides.get(t.time(), (price, price, price, price))
        out.append(f"{t:%Y-%m-%d %H:%M:%S},{o},{h},{low},{c},10\n".encode())
        t += timedelta(minutes=1)
    return out


def seed(root: Path, underlying: str, days: dict) -> None:
    store = ds.DayStore(root / underlying, underlying)
    for day, day_rows in days.items():
        store.put(day, HEADER, day_rows)
    store.save(serves=(underlying,), source="made up for a test", roll="", clock=ms.CLOCK,
               interval="1 minute", built=date(2026, 3, 20))


def at(day, hh, mm):
    return datetime(day.year, day.month, day.day, hh, mm, tzinfo=IST).astimezone(UTC)


TRADES = (  # trip id, symbol, exchange, option, opened, closed, net
    ("t1", "NIFTY", "NSE", "CE", at(MON, 9, 20), at(MON, 9, 40), 500),
    ("t2", "NIFTY", "NSE", "PE", at(MON, 10, 0), at(MON, 10, 10), -300),
    ("t3", "CRUDEOIL", "MCX", "CE", at(MON, 10, 0), at(MON, 10, 30), 200),
    ("t4", "NIFTY", "NSE", "CE", at(MON, 15, 0), at(TUE, 9, 30), 100),
    ("t0", "NIFTY", "NSE", "CE", at(date(2026, 2, 27), 15, 0), at(MON, 9, 30), -50),
    ("t5", "NIFTY", "NSE", "CE", at(date(2026, 3, 5), 9, 20), at(date(2026, 3, 5), 9, 30), 10),
)


@pytest.fixture()
def market(tmp_path, monkeypatch):
    root = tmp_path / "market"
    seed(root, "NIFTY", {
        MON: rows(MON, time(9, 15), time(15, 30), P, {
            time(9, 40): (P, P + 21, P, P + 21),
            time(9, 41): (P + 21, P + 30, P - 4, P + 3),
        }),
        TUE: rows(TUE, time(9, 15), time(15, 30), P),
    })
    seed(root, "CRUDEOIL", {MON: rows(MON, time(9, 0), time(23, 30), 5000)})
    monkeypatch.setenv("SCOPE_MARKET_DIR", str(root))
    return root


@pytest.fixture()
def client(market):
    import os
    engine = make_engine(os.environ["SCOPE_DB"])
    run_migrations(engine)
    with make_session(engine) as sess:
        trader = m.Trader(display_name="Fixture", login_id="day", created_at=datetime.now(UTC),
                          password_hash=auth.hash_password("a-long-enough-password"), development_data=True)
        sess.add(trader)
        sess.flush()
        raw = m.RawFile(trader_id=trader.id, sha256="d" * 64, original_name="f.csv", size=1,
                        stored_path="/tmp/f", uploaded_at=datetime.now(UTC))
        sess.add(raw)
        sess.flush()
        imp = m.Import(trader_id=trader.id, raw_file_id=raw.id, source_account="A", adapter_id="dhan_tradebook_v1",
                       adapter_version="1", filemap_version="1", code_version="fixturesha",
                       outcome=s.ImportOutcome.ACCEPTED_PARTIAL_FIELDS, rows_in=6, rows_parsed=6, rows_excluded=0,
                       fees_available=False, version_no=1, trips_reconstructed=6, density_default_unit="day",
                       created_at=datetime.now(UTC))
        sess.add(imp)
        sess.flush()
        for trip_id, symbol, exchange, kind, opened, closed, net in TRADES:
            sess.add(m.Trip(
                import_id=imp.id, trip_id=trip_id, trading_day=opened.astimezone(IST).date().isoformat(),
                exchange=exchange, symbol=symbol, segment="OPT", direction="LONG", option_type=kind,
                strike=Decimal(P), entry_ts=opened, exit_ts=closed, quantity=65 if exchange == "NSE" else 100,
                entry_price=Decimal(100), exit_price=Decimal(100), gross=Decimal(net), fees=Decimal(0),
                net=Decimal(net), fees_available=False, risk_unit_source=s.RiskUnitSourceV1.PREMIUM_PAID))
        stored = {"t1": ("62", "18", "21", None), "t2": (None, None, None, "waiting for this day's data"),
                  "t3": (None, None, None, DC.CRUDE_MONTH_REASON)}
        for trip_id, (way, against, took, reason) in stored.items():
            sess.add(m.BarTradeFigure(import_id=imp.id, trip_id=trip_id, underlying="CRUDEOIL" if trip_id == "t3"
                                      else "NIFTY", way=way, against=against, took=took, reason=reason, short=False))
        sess.add(m.ConsentEvent(trader_id=trader.id, purpose=s.ConsentPurpose.DIAGNOSIS, scope="v1",
                                terms_version=CONSENT_TEXT.version, granted=True, at=datetime.now(UTC),
                                method="web", wording_shown="x" * 100))
        sess.commit()
    c = TestClient(create_app())
    csrf = CSRF.search(c.get("/login").text).group(1)
    c.post("/login", data={"login_id": "day", "password": "a-long-enough-password", "csrf_token": csrf},
           follow_redirects=False)
    return c


def text(html: str) -> str:
    import html as h
    return h.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)))


def section(html: str) -> str:
    return html.split('<section class="dc" id="chart"')[1].split("</section>")[0]


# ---------- the fold ----------

def test_five_minute_candles_open_on_the_first_minute_close_on_the_last_and_leave_gaps(tmp_path):
    day = date(2026, 3, 3)  # a made-up evening-only session with a gap
    over = {time(17, 0): (100, 104, 99, 101), time(17, 4): (101, 102, 97, 98),
            time(17, 5): (98, 99, 96, 97), time(17, 9): (97, 110, 97, 108)}
    kept = [r for r in rows(day, time(17, 0), time(17, 20), 100, over)
            if not r.startswith(b"2026-03-03 17:1")]  # nothing from 17:10 to 17:19
    seed(tmp_path, "CRUDEOIL", {day: kept})
    candles = DC.fold(L.Prices(data_dir=tmp_path).series("CRUDEOIL"), day)
    assert [c.start.time() for c in candles] == [time(17, 0), time(17, 5)]
    first, second = candles
    assert (first.open, first.high, first.low, first.close) == (100, 104, 97, 98)
    assert (second.open, second.high, second.low, second.close) == (98, 110, 96, 108)


# ---------- the page ----------

def test_the_day_page_draws_the_chart_above_the_trades_with_no_script(client):
    page = client.get(f"/mirror/day/{MON}")
    assert page.status_code == 200
    html = page.text
    assert 'id="chart"' in html and "<svg" in section(html) and "<script" not in section(html).lower()
    assert html.index('id="chart"') < html.index('<article class="trade">')
    assert "One trading day" in html  # the page's own parts stay


def test_two_underlyings_get_chips_the_busier_one_first(client):
    html = client.get(f"/mirror/day/{MON}").text
    chips = re.findall(r'href="\?u=([A-Z]+)#chart"', html)
    assert chips == ["NIFTY", "CRUDEOIL"]
    assert re.search(r'href="\?u=NIFTY#chart"[^>]*aria-current="true"', html)  # shown when none is asked for


def test_marks_sit_at_the_underlyings_close_numbered_in_entry_order(client):
    html = client.get(f"/mirror/day/{MON}").text
    marks = dict(re.findall(r'data-mark="([0-9]+-(?:in|out))" data-close="([0-9.]+)"', html))
    # Numbered across the day's trades in entry order: 1 (09:20), 2 (10:00), 3 the crude trade at
    # 10:00 (on its own chart), 4 (15:00), then 5, the trade opened on an earlier day.
    assert marks["1-in"] == str(P) and marks["1-out"] == str(P + 21)  # 09:20's close, 09:40's close
    assert marks["2-in"] == str(P) and marks["2-out"] == str(P)
    assert "3-in" not in marks  # crude, on the other chart
    assert "4-in" in marks and "4-out" not in marks  # held overnight
    assert "5-out" in marks and "5-in" not in marks  # opened on an earlier day
    said = text(html)
    assert "closed on 03 Mar 2026" in said and "opened 27 Feb 2026" in said


def test_under_each_trade_the_stored_figures_or_the_stored_reason(client, monkeypatch):
    def never(*a, **kw):
        raise AssertionError("a page never works a bar figure out")

    monkeypatch.setattr(bar_figures, "measure", never)
    monkeypatch.setattr(bar_figures, "run", never)
    said = text(client.get(f"/mirror/day/{MON}").text)
    assert re.search(r"Went your way 62 pts · Against you 18 pts · You took 21 pts", said)
    assert "waiting for this day's data" in said


def test_crude_on_another_months_contract_is_shown_unmarked_and_counted(client):
    html = client.get(f"/mirror/day/{MON}?u=CRUDEOIL").text
    said = text(html)
    assert "<svg" in html
    assert not re.findall(r'data-mark="[0-9]+-in"', html)
    assert "Trades on the next month's contract are not marked: the chart is this month's future." in said
    assert re.search(r"1 trade on the next month's contract", said)


def test_a_day_after_the_series_says_it_isnt_in_yet_and_the_trades_still_show(client):
    page = client.get("/mirror/day/2026-03-05")
    assert page.status_code == 200
    assert "The market for this day isn't in yet" in text(page.text) and '<article class="trade">' in page.text


def test_a_day_before_the_series_says_we_dont_hold_it(client):
    page = client.get("/mirror/day/2026-02-27")
    assert "We don't hold the market for this day" in text(page.text)


def test_the_page_reads_one_day_file_and_the_manifest(client, market, monkeypatch):
    opened: list[str] = []
    real = builtins.open

    def spy(file, *a, **kw):
        opened.append(Path(file).as_posix())
        return real(file, *a, **kw)

    monkeypatch.setattr(builtins, "open", spy)
    client.get(f"/mirror/day/{MON}")
    root = market.as_posix() + "/"
    assert sorted(o.removeprefix(root) for o in opened if o.startswith(root)) == [
        "NIFTY/2026/2026-03-02.csv.gz", "NIFTY/manifest.json"]


def test_the_chart_as_text_lists_each_trade_and_the_day_in_one_line(client):
    html = client.get(f"/mirror/day/{MON}").text
    table = html.split('class="table ch-table"')[1].split("</table>")[0]
    assert text(table).count("09:20") == 1 and "09:40" in text(table)
    assert "Open" in text(html) and "High" in text(html) and "Low" in text(html) and "Close" in text(html)


def test_the_crude_month_reason_is_the_workers_own():
    assert DC.CRUDE_MONTH_REASON == bar_figures.MONTH


def test_it_fits_a_phone_drawn_to_the_kit_width():
    assert DC.WIDTH <= 358
    assert DC.MARK_TAP >= 16
