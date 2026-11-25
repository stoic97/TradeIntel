"""TICKET-1052 line 3: every "N trading days" on Scope's pages is one count, read off the page.

The count is the days he opened a trade on, every trade, a position held past the day included
(``{t.trading_day for t in trips}``; ``metrics.daily_series`` counts the same days). It is printed
on the hub's answer, the hub's foot, the share line on chapter 1's card, and Eligibility. Chapter 3
counts a different set, the days with a same-day trade (TICKET-855), and names it. The import
page's count sits under "Days in this upload" and counts that upload's days, a population of its
own, named by its heading.

A made-up record where the two sets differ, worked by hand: 60 same-day trades, four a day on
15 weekdays from Mon 2 Mar (each day two lost 300 and two made 100), and one position opened on
Mon 23 Mar at 14:00 and closed Wed 25 Mar, -400, with nothing else opened that day.
Days he opened a trade on: 15 + 1 = 16. Days with a same-day trade: 15.
"""
from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from services.production.api.app import create_app
from services.production.mirror import loader
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s
from tests.helpers.upload import CSRF, sign_up

IST = ZoneInfo("Asia/Kolkata")


def trip(tid: str, opened: str, closed: str, net: int) -> mx.Trip:
    entry = datetime.fromisoformat(opened).replace(tzinfo=IST)
    leave = datetime.fromisoformat(closed).replace(tzinfo=IST)
    line = mx.TradeLine("NIFTY", "OPT", "Buy", 75, None, None, Decimal(net), entry_ts=entry)
    return mx.Trip(trip_id=tid, symbol="NIFTY", trading_day=entry.date().isoformat(), entry_ts=entry,
                   exit_ts=leave, holding_seconds=int((leave - entry).total_seconds()), net=Decimal(net),
                   lots=1, risk_unit_source=s.RiskUnitSourceV1.PREMIUM_PAID, is_option=True, lines=(line,))


def weekdays(n: int) -> list[str]:
    out, day = [], datetime(2026, 3, 2, tzinfo=IST)
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day.date().isoformat())
        day = day.replace(day=day.day + 1) if day.day < 28 else day.replace(month=day.month + 1, day=1)
    return out


RECORD = [trip(f"d{i}{k}", f"{d}T{9 + k:02d}:30", f"{d}T{9 + k:02d}:40", -300 if k < 2 else 100)
          for i, d in enumerate(weekdays(15)) for k in range(4)]
RECORD.append(trip("h1", "2026-03-23T14:00", "2026-03-25T10:00", -400))
OPENED_ON, SAME_DAY = 16, 15


@pytest.fixture()
def reader(engine, monkeypatch):
    client = sign_up(TestClient(create_app()), engine, "T-9", "daysreader")
    client.post("/upload/demo", data={"csrf_token": CSRF.search(client.get("/upload").text).group(1)})
    real = loader.load_for
    monkeypatch.setattr(loader, "load_for", lambda sess, trader: (RECORD, real(sess, trader)[1]))
    return client


def plain(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def counts(text: str) -> set[int]:
    """Every N in "N trading days" on a page."""
    return {int(n.replace(",", "")) for n in re.findall(r"([\d,]+)\s+trading days", text)}


def test_the_record_has_two_sets_of_days():
    assert len({t.trading_day for t in RECORD}) == OPENED_ON
    assert len({t.trading_day for t in mx.same_day_trips(RECORD)}) == SAME_DAY


@pytest.mark.parametrize("path", ["/mirror", "/mirror/chapter/1", "/eligibility"])
def test_every_trading_days_count_on_the_page_is_the_days_he_opened_a_trade_on(reader, path):
    found = counts(plain(reader.get(path).text))
    assert found == {OPENED_ON}, (path, found)


def test_the_hub_prints_it_twice_as_one_figure(reader):
    text = plain(reader.get("/mirror").text)
    assert f"of your {OPENED_ON} trading days" in text  # the hub's answer
    assert f"{OPENED_ON} trading days" in text.split("No buy or sell calls")[0][-200:]  # the foot
