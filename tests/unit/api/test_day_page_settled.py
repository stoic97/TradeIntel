"""TICKET-1086: two things the first build noticed, settled.

1. "Your other 0 days: ₹0." is a figure that states nothing, so the other-days line is not drawn
   when every day he has is a worst day; it is drawn when there is one other day or more.
2. A trade held overnight stretched the day chart's time axis into the next day and bunched the
   day's own dots at the left on a phone. The axis now ends at his instrument's session close on
   the day; a trade that closes on a later day is drawn at the axis's right edge with a marker
   whose title says when it closed.

Every trade is made up; positions are worked by hand from the chart's own constants below.
"""
from __future__ import annotations

import html as html_lib
import re
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from services.production.api import day_chart as DC
from services.production.api.app import create_app
from services.production.mirror import loader
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s
from tests.helpers.upload import CSRF, sign_up

IST = ZoneInfo("Asia/Kolkata")
D = Decimal


def trip(tid: str, opened: str, closed: str, net: int, side: str, quantity: int = 75) -> mx.Trip:
    entry = datetime.fromisoformat(opened).replace(tzinfo=IST)
    leave = datetime.fromisoformat(closed).replace(tzinfo=IST)
    line = mx.TradeLine("NIFTY", "OPT", "Buy", quantity, D(100), D(100), D(net), strike=D(24000),
                        option_type=side, entry_ts=entry)
    return mx.Trip(trip_id=tid, symbol="NIFTY", trading_day=entry.date().isoformat(), entry_ts=entry,
                   exit_ts=leave, holding_seconds=int((leave - entry).total_seconds()), net=D(net),
                   lots=quantity // 75, risk_unit_source=s.RiskUnitSourceV1.PREMIUM_PAID, is_option=True,
                   lines=(line,))


def plain(fragment: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def main_of(page: str) -> str:
    m = re.search(r"<main.*?</main>", page, re.DOTALL)
    return m.group(0) if m else page


@pytest.fixture()
def page_of(engine, monkeypatch):
    """The routes read the given record in place of the demo file's trades."""
    def make(record: list[mx.Trip]):
        client = sign_up(TestClient(create_app()), engine, "D-8", "daysettled")
        client.post("/upload/demo", data={"csrf_token": CSRF.search(client.get("/upload").text).group(1)})
        real = loader.load_for
        monkeypatch.setattr(loader, "load_for", lambda sess, trader: (record, real(sess, trader)[1]))
        return client
    return make

# ---------- 1. no other-days line when there are no other days ----------

# Two days, one losing trade each: both are among his worst days, so there are 0 other days.
ALL_WORST = [trip("a1", "2026-05-04T09:20", "2026-05-04T09:40", -300, "CE"),
             trip("a2", "2026-05-05T09:20", "2026-05-05T09:40", -200, "PE")]

# Six days: five losing days are the worst; the sixth (+50) is the one other day.
ONE_OTHER = [trip(f"w{i}", f"2026-05-0{i}T09:20", f"2026-05-0{i}T09:40", -100 * i, "CE") for i in range(1, 6)]
ONE_OTHER += [trip("g6", "2026-05-06T09:20", "2026-05-06T09:40", 50, "CE")]


def _other_days(text: str) -> bool:
    return bool(re.search(r"[Oo]ther \d+ days?", text))


def test_no_other_days_line_when_every_day_is_a_worst_day(page_of):
    client = page_of(ALL_WORST)
    assert not _other_days(plain(main_of(client.get("/mirror/fact/worst-days").text)))
    assert not _other_days(plain(main_of(client.get("/mirror/chapter/1").text)))


def test_the_other_days_line_is_drawn_when_there_is_one(page_of):
    client = page_of(ONE_OTHER)
    assert _other_days(plain(main_of(client.get("/mirror/fact/worst-days").text)))


# ---------- 2. the day chart's axis stays within the day ----------

# NIFTY's session closes at 15:30. On 11 May: t1 09:15-10:00, t2 09:30-15:00, both closed that day;
# t3 opened 14:00 and closed 12 May 09:30 (overnight).
# Axis: from the first entry 09:15 to the session close 15:30 = 375 minutes.
# Inner width = W - LEFT - RIGHT = 350 - 8 - 54 = 288.
#   t1 closes at 45 min:  x = 8 + 45/375 * 288  = 42.56 -> 42.6
#   t2 closes at 345 min: x = 8 + 345/375 * 288 = 272.96 -> 273.0
#   t3 closes a day later: drawn at the right edge, x = 8 + 288 = 296.0
DAY = [trip("t1", "2026-05-11T09:15", "2026-05-11T10:00", -100, "CE"),
       trip("t2", "2026-05-11T09:30", "2026-05-11T15:00", -100, "CE"),
       trip("t3", "2026-05-11T14:00", "2026-05-12T09:30", -100, "PE")]


def _cx(svg: str) -> list[float]:
    return [float(v) for v in re.findall(r'<circle class="daychart__dot[^"]*" cx="([^"]+)"', svg)]


def test_the_axis_ends_at_the_session_close_and_the_days_dots_keep_their_place():
    svg = str(DC.view(mx.day_path(DAY))["svg"])
    assert _cx(svg) == [42.6, 273.0, 296.0]


def test_an_overnight_trade_carries_a_marker_saying_when_it_closed():
    svg = str(DC.view(mx.day_path(DAY))["svg"])
    marker = re.search(r'<g class="daychart__later">.*?</g>', svg, re.DOTALL)
    assert marker, "no marker for the trade that closed a day later"
    assert "<title>closed 12 May 09:30</title>" in marker.group(0)


def test_a_day_without_an_overnight_trade_draws_as_before():
    same = DAY[:2]
    svg = str(DC.view(mx.day_path(same))["svg"])
    # Axis from 09:15 to the last close 15:00 = 345 min: t1 x = 8 + 45/345*288 = 45.57 -> 45.6; t2 = 296.0
    assert _cx(svg) == [45.6, 296.0]
    assert "daychart__later" not in svg
