"""TICKET-1080 lines 1-3, as ruled 24 Nov 22:23: the card lands on the latest period that is not
itself almost nothing (at least a quarter of his median period's trades), and says which period
it describes without calling it his usual.


Every trade here is made up; each month's trades and results are worked by hand below.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
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


def trip(tid: str, opened: datetime, net: int, closed: datetime | None = None) -> mx.Trip:
    leave = closed or opened + timedelta(minutes=10)
    line = mx.TradeLine("NIFTY", "OPT", "Buy", 75, None, None, Decimal(net), entry_ts=opened)
    return mx.Trip(trip_id=tid, symbol="NIFTY", trading_day=opened.date().isoformat(), entry_ts=opened,
                   exit_ts=leave, holding_seconds=int((leave - opened).total_seconds()), net=Decimal(net),
                   lots=1, risk_unit_source=s.RiskUnitSourceV1.PREMIUM_PAID, is_option=True, lines=(line,))


def months(counts: list[int], net: int = 100) -> list[mx.Trip]:
    """counts[i] same-day trades of +net in the i-th month from January 2026, one a weekday."""
    out = []
    for m, n in enumerate(counts, start=1):
        day = datetime(2026, m, 2, 10, 0, tzinfo=IST)
        while len([t for t in out if t.entry_ts.month == m]) < n:
            if day.weekday() < 5:
                out.append(trip(f"m{m}-{day.day}", day, net))
            day += timedelta(days=1)
    return out


@pytest.fixture()
def home(engine, monkeypatch):
    def make(trips: list[mx.Trip], query: str = "?book=all&tf=m") -> str:
        client = sign_up(TestClient(create_app()), engine, "H-8", "homereader")
        client.post("/upload/demo", data={"csrf_token": CSRF.search(client.get("/upload").text).group(1)})
        real = loader.load_for
        monkeypatch.setattr(loader, "load_for", lambda sess, trader: (trips, real(sess, trader)[1]))
        page = client.get("/" + query).text
        return re.search(r'<section[^>]*id="how".*?</section>', page, re.DOTALL).group(0)
    return make


def plain(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def readout_when(card: str) -> str:
    return plain(re.search(r'<span class="hy-readout__when">(.*?)</span>', card, re.DOTALL).group(1))


# Months Jan-May with 10, 10, 10, 9, 1 trades. His median month is the lower middle of
# 1 9 10 10 10, which is 10. May's 1 is almost nothing (1 x 4 = 4 < 10). April's 9 is not
# (9 x 4 = 36 >= 10), so the card describes April, not March, and names May as the month passed.

def test_the_card_lands_on_the_latest_month_that_is_not_almost_nothing(home):
    card = home(months([10, 10, 10, 9, 1]))
    assert readout_when(card) == "Apr 2026 · May 2026 had only 1 trade"


# Months Jan-Apr with 6, 6, 6, 1: median 6; April's 1 is almost nothing (4 < 6); March's 6 is
# not, so the card describes March and names April.

def test_a_thin_latest_month_is_named_when_the_card_passes_it(home):
    card = home(months([6, 6, 6, 1]))
    assert readout_when(card) == "Mar 2026 · Apr 2026 had only 1 trade"
    assert "usual" not in readout_when(card)


# Months Jan-Apr with 6, 6, 6, 5: April's 5 is not almost nothing (20 >= 6), so the card stays.

def test_a_latest_month_a_little_under_his_usual_stays(home):
    card = home(months([6, 6, 6, 5]))
    assert readout_when(card) == "Apr 2026 · the last month"


# One month only, Jan with 3 trades: it is its own median, never almost nothing, so it is described.

def test_a_record_of_one_month_lands_on_it(home):
    card = home(months([3]))
    assert readout_when(card) == "Jan 2026 · the last month"
