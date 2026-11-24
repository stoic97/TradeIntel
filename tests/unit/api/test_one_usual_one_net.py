"""TICKET-1052: one usual size, rounded one way in both sentences that say it, and one net figure
on Home's card for the last period.

Gate 2: ``journal/prose.py`` ("against your usual N") and ``api/asking.py`` ("Your usual is about
N lots") rounded a usual size two ways: 1.25 was "1.2" in one (half to even) and "1.3" in the
other (half up). Both now round half up, as a person says a number, through ``formatting.lots``.

Gate 5: Home's readout printed the last period's net as the candle holds it, while the row beside
it prints the difference of the closes as written, so the two could stand a rupee apart. The
readout now prints the row's figure.
"""
from __future__ import annotations

import re
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from services.production.api import asking
from services.production.api.app import create_app
from services.production.db import models as m
from services.production.db.session import make_session
from services.production.journal import prose
from services.production.mirror import metrics as mx
from tests.helpers.upload import CSRF, sign_up


def plain(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


# ---------- 2. one usual size ----------

def test_a_usual_of_one_and_a_quarter_is_one_point_three_in_the_journal_sentence():
    facts = {"against_your_normal": {"your_normal_day": "3", "lots_today": "2", "lots_usually": "1.25",
                                     "trades_today": 3}}
    assert "Your average size was 2.0 lots against your usual 1.3." in prose._against_normal(facts)


def test_and_in_the_size_line():
    # Opened at 1 lot, lost twice, then 2 lots and lost: "from 1 lot to 2 after 2 losses".
    trades = [{"lots": 1, "net": Decimal(-10)}, {"lots": 1, "net": Decimal(-10)},
              {"lots": 2, "net": Decimal(-10)}]
    line = asking.size_line("2026-09-01", trades, Decimal("1.25"))
    assert line is not None and line.endswith("Your usual is about 1.3 lots.")


@pytest.fixture()
def demo(engine):
    client = sign_up(TestClient(create_app()), engine, "U-5", "usualreader")
    client.post("/upload/demo", data={"csrf_token": CSRF.search(client.get("/upload").text).group(1)})
    client.engine = engine
    return client


def test_every_journal_page_prints_the_usual_one_way(demo, monkeypatch):
    # The page reads the usual live (sections.with_history): a usual of 1.25 on every page.
    monkeypatch.setattr(mx, "average_lots", lambda trips: SimpleNamespace(mean=Decimal("1.25")))
    with make_session(demo.engine) as sess:
        ids = sess.scalars(select(m.Journal.id).where(m.Journal.period_start == m.Journal.period_end)).all()
    said = {"against": set(), "about": set()}
    for jid in ids:
        page = plain(demo.get(f"/journals/{jid}").text)
        said["against"] |= set(re.findall(r"against your usual (\d+(?:\.\d+)?)", page))
        said["about"] |= set(re.findall(r"Your usual is about (\d+(?:\.\d+)?) lots", page))
    assert said["against"] | said["about"] == {"1.3"}, said
    assert said["against"], "no journal page drew the against-your-usual sentence"


# ---------- 5. Home's card: one net figure for the last period ----------

def card(html: str) -> str:
    return re.search(r'<section[^>]*id="how".*?</section>', html, re.DOTALL).group(0)


@pytest.mark.parametrize("query", ["", "?tf=d", "?tf=w", "?tf=m", "?book=nifty-options&tf=d",
                                   "?book=nifty-options&tf=w", "?book=crude-options&tf=m"])
def test_the_readout_and_the_row_beside_it_print_one_net(demo, query):
    html = card(demo.get(f"/{query}").text)
    readout = plain(re.search(r'<span class="hy-readout__net">.*?</span> in the', html, re.DOTALL).group(0))
    first_row = re.search(r'<tr class="hy-row">(.*?)</tr>', html, re.DOTALL).group(1)
    cells = [plain(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", first_row, re.DOTALL)]
    in_the_period = cells[2]
    assert in_the_period in readout, (query, readout, in_the_period)


def paise_trip(tid: str, day: str, net: str) -> mx.Trip:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from services.shared.schemas import scope_v1 as s
    entry = datetime.fromisoformat(f"{day}T10:00").replace(tzinfo=ZoneInfo("Asia/Kolkata"))
    leave = entry.replace(minute=10)
    line = mx.TradeLine("NIFTY", "OPT", "Buy", 75, None, None, Decimal(net), entry_ts=entry)
    return mx.Trip(trip_id=tid, symbol="NIFTY", trading_day=day, entry_ts=entry, exit_ts=leave,
                   holding_seconds=600, net=Decimal(net), lots=1,
                   risk_unit_source=s.RiskUnitSourceV1.PREMIUM_PAID, is_option=True, lines=(line,))


# Two days with paise, worked by hand. Rupees are written cut toward zero (formatting.whole).
#   2 Mar +0.60, ending at 0.60;  3 Mar +0.60, ending at 1.20.
# The last day as the candle holds it: +0.60, written ₹0. Its row: the closes as written,
# ₹1 (1.20) less ₹0 (0.60) = +₹1. The readout printed ₹0 beside a row of +₹1.
PAISE = [paise_trip("p1", "2026-03-02", "0.60"), paise_trip("p2", "2026-03-03", "0.60")]


def test_with_paise_the_readout_prints_the_rows_figure(demo, monkeypatch):
    from services.production.mirror import loader
    real = loader.load_for
    monkeypatch.setattr(loader, "load_for", lambda sess, trader: (PAISE, real(sess, trader)[1]))
    html = card(demo.get("/?tf=d").text)
    readout = plain(re.search(r'<span class="hy-readout__net">.*?</span> in the', html, re.DOTALL).group(0))
    first_row = re.search(r'<tr class="hy-row">(.*?)</tr>', html, re.DOTALL).group(1)
    in_the_period = [plain(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", first_row, re.DOTALL)][2]
    assert in_the_period == "+₹1"
    assert readout == "1 trade · +₹1 in the"
