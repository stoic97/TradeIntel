"""TICKET-1022: on Your numbers, a day's figure opens the trades it adds up.

Every day on the page is the day he closed. The day page (/mirror/day/<date>) lists the trades
he opened that day, so it can hold other trades than the figure counts. A day's figure opens
the trades closed that day instead (the closed_day filter): Best day, Worst day, "Most in a day"
and every traded cell of Your calendar. Every trade here is made up; the expected values are
worked by hand in the comments.
"""
from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from services.production.api import numbers as N
from services.production.api import scope_facts as SF
from services.production.api import trade_list as TL
from services.production.api.app import create_app
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s
from tests.helpers.upload import CSRF, sign_up

IST = ZoneInfo("Asia/Kolkata")
D = Decimal


def trip(tid: str, opened: str, closed: str, net: str) -> mx.Trip:
    entry = datetime.fromisoformat(opened).replace(tzinfo=IST)
    leave = datetime.fromisoformat(closed).replace(tzinfo=IST)
    return mx.Trip(
        trip_id=tid, symbol="NIFTY", trading_day=entry.date().isoformat(), entry_ts=entry,
        exit_ts=leave, holding_seconds=int((leave - entry).total_seconds()), net=D(net), lots=1,
        risk_unit_source=s.RiskUnitSourceV1.PREMIUM_PAID, is_option=True,
        lines=(mx.TradeLine("NIFTY", "OPT", "Buy", 1, None, None, D(net)),),
    )


# By the day he closed, worked by hand:
#    9 Mar (Mon)  e +50                              -> +50, 1 trade
#   10 Mar (Tue)  a +500 (opened 9 Mar), b +100      -> +600, 2 trades   best day
#   11 Mar (Wed)  c -300 (opened 10 Mar), d -50      -> -350, 2 trades   worst day
# "Most in a day" is 2, on 10 and 11 Mar; a tie goes to the earlier day, 10 Mar.
# The day page for 10 Mar would list what opened on 10 Mar, b and c: -200 over 2 trades,
# not the +600 the figure counts. Closed on 10 Mar is a and b: +600 over 2.
RECORD = [
    trip("e", "2026-03-09T09:40", "2026-03-09T10:00", "50"),
    trip("a", "2026-03-09T14:00", "2026-03-10T10:00", "500"),
    trip("b", "2026-03-10T09:40", "2026-03-10T10:00", "100"),
    trip("c", "2026-03-10T14:00", "2026-03-11T10:00", "-300"),
    trip("d", "2026-03-11T11:00", "2026-03-11T11:20", "-50"),
]
CLOSED = "/mirror/fact/risk/trades?closed_day="


def closed_on(iso: str) -> list[mx.Trip]:
    """The trades the closed_day filter keeps, read through the filter itself."""
    f = next(f for f in TL.FILTERS if f.name == "closed_day")
    return [t for t in RECORD if (c := f.read(t, {})) is not None and c[1] == iso]


def listed(iso: str) -> int:
    return TL.listing("risk", SF.record_context(RECORD), {"closed_day": iso}, {})["shown"]


@pytest.fixture()
def tiles():
    return N.build(RECORD, {}, gross=True)["tiles"]


def test_best_and_worst_day_open_the_trades_closed_that_day(tiles):
    assert (tiles["best_day"]["day"], tiles["best_day"]["value"]) == ("2026-03-10", D(600))
    assert tiles["best_day"]["href"] == CLOSED + "2026-03-10"
    assert (tiles["worst_day"]["day"], tiles["worst_day"]["value"]) == ("2026-03-11", D(-350))
    assert tiles["worst_day"]["href"] == CLOSED + "2026-03-11"


def test_most_in_a_day_opens_the_trades_closed_that_day(tiles):
    assert (tiles["per_day"]["most"], tiles["per_day"]["day"]) == (2, "2026-03-10")
    assert tiles["per_day"]["href"] == CLOSED + "2026-03-10"


@pytest.mark.parametrize("key, iso, trades, net", [
    ("best_day", "2026-03-10", 2, D(600)),
    ("worst_day", "2026-03-11", 2, D(-350)),
])
def test_the_list_a_day_tile_opens_is_the_trades_its_figure_counts(tiles, key, iso, trades, net):
    assert tiles[key]["value"] == net
    assert listed(iso) == trades
    assert sum(t.net for t in closed_on(iso)) == net
    assert sorted(t.trip_id for t in closed_on(iso)) == (["a", "b"] if iso == "2026-03-10" else ["c", "d"])


def test_every_traded_calendar_cell_opens_the_trades_closed_that_day():
    view = N.calendar(RECORD)
    traded = {c["iso"]: c for m in view["months"] for week in m["weeks"] for c in week
              if c and c["trades"]}
    # 9 Mar +50 over 1; 10 Mar +600 over 2, though b and c opened then; 11 Mar -350 over 2.
    assert {iso: (c["trades"], c["net"]) for iso, c in traded.items()} == {
        "2026-03-09": (1, D(50)), "2026-03-10": (2, D(600)), "2026-03-11": (2, D(-350))}
    for iso, c in traded.items():
        assert c["href"] == CLOSED + iso
        assert listed(iso) == c["trades"]
        assert sum(t.net for t in closed_on(iso)) == c["net"]


# ---------- on the rendered page ----------

@pytest.fixture()
def demo(engine):
    client = sign_up(TestClient(create_app()), engine, "C-1", "visitor")
    client.post("/upload/demo", data={"csrf_token": CSRF.search(client.get("/upload").text).group(1)})
    return client


def test_no_day_figure_on_the_page_opens_the_day_page(demo):
    html = demo.get("/numbers").text
    assert "/mirror/day/" not in html


def test_the_day_tiles_and_every_cell_open_closed_day_lists_that_answer(demo):
    html = demo.get("/numbers").text
    grid = re.search(r'class="numbers__grid".*?</section>', html, re.DOTALL)
    assert grid, "no tiles on the page"
    tile_days = re.findall(r'href="(/mirror/fact/risk/trades\?closed_day=[0-9-]+)"', grid.group(0))
    assert len(tile_days) >= 3  # Best day, Worst day, Most in a day
    cal = re.search(r'<section class="cal" id="calendar">.*?</section>', html, re.DOTALL)
    assert cal, "no calendar on the page"
    cell_days = re.findall(r'<a href="([^"]+)" class="cal__day">', cal.group(0))
    assert cell_days, "no traded cell on the calendar"
    for href in tile_days + cell_days:
        assert href.startswith(CLOSED), href
        assert demo.get(href.replace("&amp;", "&")).status_code == 200, href
