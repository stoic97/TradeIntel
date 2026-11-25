"""TICKET-1052 line 6: each label TICKET-1025 made one figure is read off the rendered pages that
print it, and every page prints the one function's figure, on records the pages have never seen.

A page that worked out its own figure would print a different number on one of these records:
  - "After two straight losses": the hub's answer and chapter 3's card table, against
    ``mx.two_straight_losses(same_day).condition``;
  - "Biggest drop": Home's card, against ``mx.running_result(record).drop``;
  - the usual size: both Journal sentences, "against your usual N" (prose) and "Your usual is about
    N lots" (``asking.size_line``), against ``formatting.lots(mx.average_lots(record).mean)``;
  - "N trading days": test_trading_days_one_count.py.

The records are made up and built from a seed: 15 weekdays, two books, sizes of 1 to 4 lots,
results drawn from a fixed set, and now and then a position held past the day.
"""
from __future__ import annotations

import random
import re
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from services.production.api import formatting
from services.production.api.app import create_app
from services.production.db import models as m
from services.production.db.session import make_session
from services.production.mirror import loader
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s
from tests.helpers.upload import CSRF, sign_up

IST = ZoneInfo("Asia/Kolkata")
D = Decimal


def record(seed: int) -> list[mx.Trip]:
    rnd = random.Random(seed)
    out, day = [], datetime(2026, 3, 2, 9, 20, tzinfo=IST)
    while len({t.trading_day for t in out}) < 15:
        if day.weekday() < 5:
            at = day
            for n in range(rnd.randint(2, 6)):
                book = rnd.choice(["NIFTY", "CRUDEOIL"])
                lots = rnd.randint(1, 4)
                net = D(rnd.choice([-700, -300, -80, 90, 250, 900])) * lots
                held = rnd.random() < 0.08
                leave = at + (timedelta(days=1, hours=1) if held else timedelta(minutes=9))
                line = mx.TradeLine(book, "OPT", "Buy", 75 * lots, None, None, net, entry_ts=at)
                out.append(mx.Trip(trip_id=f"s{seed}-{len(out)}", symbol=book, trading_day=at.date().isoformat(),
                                   entry_ts=at, exit_ts=leave, holding_seconds=int((leave - at).total_seconds()),
                                   net=net, lots=lots, risk_unit_source=s.RiskUnitSourceV1.PREMIUM_PAID,
                                   is_option=True, lines=(line,)))
                at += timedelta(minutes=rnd.randint(11, 40))
        day += timedelta(days=1)
    return out


SEEDS = [3, 11, 29]


@pytest.fixture()
def reader(engine, monkeypatch):
    def make(trips: list[mx.Trip]):
        client = sign_up(TestClient(create_app()), engine, "G-1", "labelreader")
        client.post("/upload/demo", data={"csrf_token": CSRF.search(client.get("/upload").text).group(1)})
        real = loader.load_for
        monkeypatch.setattr(loader, "load_for", lambda sess, trader: (trips, real(sess, trader)[1]))
        client.engine = engine
        return client
    return make


def plain(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


@pytest.mark.parametrize("seed", SEEDS)
def test_after_two_straight_losses_is_one_count_on_every_page(reader, seed):
    trips = record(seed)
    want = mx.two_straight_losses(mx.same_day_trips(trips)).condition
    client = reader(trips)
    hub = plain(client.get("/mirror").text)
    said = re.findall(r"After two straight losses you opened ([\d,]+) trades?", hub)
    card = client.get("/mirror/chapter/3").text
    row = re.search(r'<td class="table__text">After two straight losses</td><td class="table__num">(.*?)</td>', card)
    printed = {int(n.replace(",", "")) for n in said} | ({int(plain(row.group(1)).replace(",", ""))} if row else set())
    assert printed, "no page printed the count"
    assert printed == {want}, (seed, printed, want)


@pytest.mark.parametrize("seed", SEEDS)
def test_biggest_drop_on_home_is_the_running_results(reader, seed):
    trips = record(seed)
    drop = mx.running_result(trips).drop.value
    card = reader(trips).get("/?book=all&tf=d").text
    fig = re.search(r'<span class="hy-kpi__label">Biggest drop</span><span class="hy-kpi__fig[^"]*">(.*?)</span>', card)
    assert fig, "Home's card has no biggest drop"
    assert plain(fig.group(1)) == formatting.rupees(-drop), (seed, plain(fig.group(1)), drop)


@pytest.mark.parametrize("seed", SEEDS)
def test_the_usual_size_on_every_journal_page_is_one_figure(reader, seed):
    trips = record(seed)
    want = formatting.lots(mx.average_lots(trips).mean)
    client = reader(trips)
    with make_session(client.engine) as sess:
        ids = sess.scalars(select(m.Journal.id).where(m.Journal.period_start == m.Journal.period_end)).all()
    printed = set()
    for jid in ids:
        page = plain(client.get(f"/journals/{jid}").text)
        printed |= set(re.findall(r"against your usual (\d+(?:\.\d+)?)", page))
        printed |= set(re.findall(r"Your usual is about (\d+(?:\.\d+)?) lots", page))
    assert printed <= {want}, (seed, printed, want)
