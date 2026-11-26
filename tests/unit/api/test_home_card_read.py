"""TICKET-1080: Home's card read as a person reads it, the period it lands on proven on the page,
and the held-past-the-day figure kept whole with its sign.

Line 3: on two made-up records the rendered card lands where the rule says. A latest month under
a quarter of his median month's trades is passed over for the latest month with at least his
median, and the card says so; a latest month a little under his usual stays.
Line 5: "Held past the day: N positions, net <signed rupees>" keeps its sign with its figure on
the money card and the money fact page.
Line 6: the card's words are read: the month names on the month view, the trade-count label and
the last-value tag. Home's ten digests in test_charts_toolkit.py pin bytes; this pins what they
say, so a digest re-taken after a change still has to say the same things.

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


# ---------- 3. the period the card lands on, on the rendered card ----------
# Months Jan-Apr with 6, 6, 6, 1 trades: his median month (the lower middle of 1 6 6 6) is 6.
# April's 1 is under a quarter of 6 (1 x 4 = 4 < 6), so the card lands on March and says why.

@pytest.mark.skip(reason="Superseded by the 24 Nov 22:23 ruling on TICKET-1080: the card names the period it passes over and no longer calls the one it describes his usual; test_landing_period.py holds the rule")
def test_a_latest_month_of_almost_nothing_is_passed_over_and_the_card_says_so(home):
    card = home(months([6, 6, 6, 1]))
    assert readout_when(card) == "Mar 2026 · the latest month with your usual number of trades"


# Months Jan-Apr with 6, 6, 6, 5: April's 5 is a little under his usual 6 (5 x 4 = 20 >= 6), so
# the card stays on April, his latest month.

def test_a_latest_month_a_little_under_his_usual_stays(home):
    card = home(months([6, 6, 6, 5]))
    assert readout_when(card) == "Apr 2026 · the last month"


# ---------- 6. what the card says on the month view ----------
# Jan 2, Feb 4, Mar 3 trades of +100: closes 200, 600, 900. The busiest month holds 4 trades;
# the last close is ₹900, the chart's tag; the month labels are January's year, then Feb, Mar.

def test_the_month_view_names_its_months_its_count_and_its_last_value(home):
    card = home(months([2, 4, 3]))
    svg = re.search(r"<svg.*?</svg>", card, re.DOTALL).group(0)
    labels = [plain(t) for t in re.findall(r'<text[^>]*class="hy-axis hy-axis--x"[^>]*>(.*?)</text>', svg)]
    assert labels == ["2026", "Feb", "Mar"]
    assert re.search(r'class="hy-axis"[^>]*>4 trades</text>', svg)
    assert re.search(r'class="hy-last-text"[^>]*>₹900</text>', svg)
    assert readout_when(card) == "Mar 2026 · the last month"


# ---------- 5. held past the day keeps its sign with its figure ----------
# Twelve same-day trades and one position held for three days that lost 1,250.

HELD = months([6, 6]) + [trip("h1", datetime(2026, 2, 20, 14, 0, tzinfo=IST), -1250,
                              closed=datetime(2026, 2, 23, 10, 0, tzinfo=IST))]


@pytest.mark.parametrize("path", ["/mirror/chapter/1", "/mirror/fact/money"])
def test_held_past_the_day_keeps_its_sign_with_its_figure(engine, monkeypatch, path):
    client = sign_up(TestClient(create_app()), engine, "H-9", "heldreader")
    client.post("/upload/demo", data={"csrf_token": CSRF.search(client.get("/upload").text).group(1)})
    real = loader.load_for
    monkeypatch.setattr(loader, "load_for", lambda sess, trader: (HELD, real(sess, trader)[1]))
    html = client.get(path).text
    found = re.search(r"Held past the day: .*?, net (.*?)\.", html, re.DOTALL)
    assert found, f"no held-past-the-day line on {path}"
    assert re.fullmatch(r'<span class="nowrap">−₹1,250</span>', found.group(1).strip()), found.group(1)
