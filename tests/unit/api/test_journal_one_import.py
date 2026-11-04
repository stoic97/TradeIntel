"""A Journal shows the trades of the upload it was written from, once each (TICKET-796).

trip_id is a content hash, so the same trade in a later upload carries the same id. The
lookup behind the Journal page and home searched every upload, so a second upload showed
every trade twice and a third three times, and home added the money up that many times.

The file below is synthetic. Its figures are worked by hand:

    Day 1, same option, 50 units a time:
      trade 1: bought for 5000, sold for 4500  ->  -500
      trade 2: bought for 5000, sold for 4700  ->  -300
      the day: 2 trades, -800
    Day 2 is the file's last day, so it gets no Journal (it may not be complete). It has
    two trades as well, because a median under two a day writes per-10-trade Journals.
"""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from services.production.api.app import create_app
from services.production.db import models as m
from services.production.db.session import make_engine, make_session, run_migrations
from tests.unit.api.test_upload import CSRF, sign_up

HEADER = "Date,Time,Name,Buy/Sell,Order,Exchange,Segment,Quantity/Lot,Trade Price,Trade Value,Status"
OPTION = "NIFTY 25 JAN 20000 CALL"


def _row(day: str, time: str, side: str, value: int) -> str:
    return f"{day},{time},{OPTION},{side},INTRADAY,NSE,Derivative,50,{value / 50:.2f},{value:.2f},Traded"


DAY_ONE = [
    _row("2024-01-02", "09:30:00", "BUY", 5000),
    _row("2024-01-02", "09:40:00", "SELL", 4500),
    _row("2024-01-02", "10:00:00", "BUY", 5000),
    _row("2024-01-02", "10:10:00", "SELL", 4700),
]
LAST_DAY = [
    _row("2024-01-03", "09:30:00", "BUY", 5000),
    _row("2024-01-03", "09:40:00", "SELL", 5100),
    _row("2024-01-03", "10:00:00", "BUY", 5000),
    _row("2024-01-03", "10:10:00", "SELL", 5200),
]
FILE = "\n".join([HEADER, *DAY_ONE, *LAST_DAY]) + "\n"


@pytest.fixture()
def engine():
    e = make_engine(os.environ["SCOPE_DB"])
    run_migrations(e)
    return e


@pytest.fixture()
def client(engine):
    return sign_up(TestClient(create_app()), engine, "ONE-IMPORT", "one-import")


def _upload(client, body: str) -> None:
    token = CSRF.search(client.get("/upload").text).group(1)
    sent = client.post(
        "/upload",
        files={"file": ("t.csv", body.encode(), "text/csv")},
        data={"csrf_token": token},
        follow_redirects=False,
    )
    assert sent.status_code == 303, sent.text


def _first_day_journal(engine) -> m.Journal:
    with make_session(engine) as sess:
        journal = sess.scalars(
            select(m.Journal).where(m.Journal.period_start == "2024-01-02")
            .order_by(m.Journal.version_no.desc())
        ).first()
        sess.expunge(journal)
    return journal


def _trade_blocks(page: str) -> list[str]:
    return re.findall(r'<p class="journal-trade__head"><span>(Trade \d+)</span>', page)


def _readable(page: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", page).split())


def _home_row(client) -> str:
    text = _readable(client.get("/").text)
    return text[text.index("Latest Journals"):text.index("Upload new trades")]


def test_one_upload_shows_each_trade_once(engine, client):
    _upload(client, FILE)
    page = client.get(f"/journals/{_first_day_journal(engine).id}").text
    assert _trade_blocks(page) == ["Trade 1", "Trade 2"]


def test_a_second_upload_does_not_list_the_trades_again(engine, client):
    _upload(client, FILE)
    _upload(client, FILE + "\n")
    page = client.get(f"/journals/{_first_day_journal(engine).id}").text
    assert _trade_blocks(page) == ["Trade 1", "Trade 2"]


def test_a_third_upload_does_not_list_them_a_third_time(engine, client):
    _upload(client, FILE)
    _upload(client, FILE + "\n")
    _upload(client, FILE + "\n\n")
    page = client.get(f"/journals/{_first_day_journal(engine).id}").text
    assert _trade_blocks(page) == ["Trade 1", "Trade 2"]


def test_home_counts_a_days_trades_once_after_a_second_upload(engine, client):
    _upload(client, FILE)
    _upload(client, FILE + "\n")
    assert "2 trades" in _home_row(client)


def test_home_adds_a_days_money_once_after_a_second_upload(engine, client):
    _upload(client, FILE)
    _upload(client, FILE + "\n")
    assert "−₹800" in _home_row(client)


def test_a_trade_keeps_one_answer_after_a_second_upload(engine, client):
    """Each block is a form for one trip id, so two blocks meant two forms for one trade."""
    _upload(client, FILE)
    _upload(client, FILE + "\n")
    page = client.get(f"/journals/{_first_day_journal(engine).id}").text
    ids = re.findall(r'name="trip_id" value="([^"]+)"', page)
    assert len(ids) == 2 and len(set(ids)) == 2


def test_two_identical_trades_in_one_upload_both_stay(engine, client):
    """Guard. PRD 5.4: identical trades share an id and neither may be dropped.

    So the fix cannot be "keep one row per id". It has to be "this upload's rows".
    """
    _upload(client, FILE)
    written = _first_day_journal(engine)
    with make_session(engine) as sess:
        first = sess.scalars(select(m.Trip).where(m.Trip.import_id == written.import_id)
                             .order_by(m.Trip.entry_ts)).first()
        ids = json.loads(written.trip_ids)
        sess.add(m.Trip(
            import_id=first.import_id, trip_id=first.trip_id, occurrence=2,
            trading_day=first.trading_day, exchange=first.exchange, symbol=first.symbol,
            segment=first.segment, direction=first.direction, entry_ts=first.entry_ts,
            exit_ts=first.exit_ts, quantity=first.quantity, entry_price=first.entry_price,
            exit_price=first.exit_price, gross=first.gross, fees=first.fees, net=first.net,
            fees_available=first.fees_available, risk_unit_source=first.risk_unit_source,
        ))
        journal = m.Journal(
            trader_id=written.trader_id, import_id=written.import_id, unit=written.unit,
            period_start=written.period_start, period_end=written.period_end,
            version_no=written.version_no + 1, supersedes=written.id,
            generated_at=datetime.now(UTC), trip_ids=json.dumps([*ids, first.trip_id]),
            sections=written.sections,
        )
        sess.add(journal)
        sess.commit()
        journal_id = journal.id
    page = client.get(f"/journals/{journal_id}").text
    assert _trade_blocks(page) == ["Trade 1", "Trade 2", "Trade 3"]


def test_a_journal_keeps_its_trades_when_a_later_upload_changes_the_day(engine, client):
    """Guard. The old version of a day still reads from the upload that wrote it."""
    _upload(client, FILE)
    written = _first_day_journal(engine)
    changed = [
        _row("2024-01-02", "09:30:00", "BUY", 5000),
        _row("2024-01-02", "09:40:00", "SELL", 4000),
        _row("2024-01-02", "10:00:00", "BUY", 5000),
        _row("2024-01-02", "10:10:00", "SELL", 4100),
    ]
    _upload(client, "\n".join([HEADER, *changed, *LAST_DAY]) + "\n")
    newest = _first_day_journal(engine)
    assert newest.id != written.id, "the changed day should have a new version"

    assert _trade_blocks(client.get(f"/journals/{written.id}").text) == ["Trade 1", "Trade 2"]
    assert "−₹1,900" in _readable(client.get(f"/journals/{newest.id}").text)
    assert _trade_blocks(client.get(f"/journals/{newest.id}").text) == ["Trade 1", "Trade 2"]


def test_fixture_figures_are_the_hand_worked_ones(engine, client):
    _upload(client, FILE)
    written = _first_day_journal(engine)
    with make_session(engine) as sess:
        nets = [t.net for t in sess.scalars(
            select(m.Trip).where(m.Trip.import_id == written.import_id,
                                 m.Trip.trading_day == "2024-01-02")
            .order_by(m.Trip.entry_ts))]
    assert nets == [Decimal(-500), Decimal(-300)]
