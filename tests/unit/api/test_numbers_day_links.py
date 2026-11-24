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
from html import unescape
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from services.production.api import numbers as N
from services.production.api import routes_mirror as RM
from services.production.api import routes_numbers as RN
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
    tile_days = [tile_link(html, label) for label in WANT]  # one link, from each tile's own markup
    cal = re.search(r'<section class="cal" id="calendar">.*?</section>', html, re.DOTALL)
    assert cal, "no calendar on the page"
    cell_days = re.findall(r'<a href="([^"]+)" class="cal__day">', cal.group(0))
    assert cell_days, "no traded cell on the calendar"
    for href in tile_days + cell_days:
        assert href.startswith(CLOSED), href
        assert demo.get(href.replace("&amp;", "&")).status_code == 200, href


# ---------- TICKET-1040: each tile's link, read on the rendered page from its own tile ----------

# One more made-up record, so "Most in a day" is not also the best day. By the day he closed:
#    9 Mar (Mon)  e +50, f +10, g -20                -> +40, 3 trades    most in a day
#   10 Mar (Tue)  a +500 (opened 9 Mar), b +100      -> +600, 2 trades   best day
#   11 Mar (Wed)  c -300 (opened 10 Mar), d -50      -> -350, 2 trades   worst day
BUSY = RECORD + [
    trip("f", "2026-03-09T11:00", "2026-03-09T11:20", "10"),
    trip("g", "2026-03-09T12:00", "2026-03-09T12:20", "-20"),
]
# The words on the tile -> (the tile's date, the trades its figure counts, their net).
WANT = {
    "Best day": ("2026-03-10", 2, 600),
    "Worst day": ("2026-03-11", 2, -350),
    "Most in a day": ("2026-03-09", 3, 40),
}
KEYS = {"Best day": "best_day", "Worst day": "worst_day", "Most in a day": "per_day"}
TILE = re.compile(r'<div class="numbers__tile">(.*?)</div>', re.DOTALL)
HREF = re.compile(r'href="([^"]*)"')
SHOWN = re.compile(r'class="evidence__caption"><span class="num">(\d+)</span> of ')
NET = re.compile(r'class="trade__net[^"]*">([^<]+)<')
CELLS = re.compile(r'<a href="([^"]+)" class="cal__day">')


def tile(html: str, label: str) -> str:
    """One tile's own markup, found by the words on it."""
    found = [t for t in TILE.findall(html) if label in t]
    assert len(found) == 1, f"{label!r}: {len(found)} tiles carry it"
    return found[0]


def tile_link(html: str, label: str) -> str:
    """The one link inside that tile. No link, or a second one, fails here."""
    hrefs = HREF.findall(tile(html, label))
    assert len(hrefs) == 1, f"{label!r} tile holds {len(hrefs)} links, not one: {hrefs}"
    return unescape(hrefs[0])


def on_the_list(html: str) -> tuple[int, list[int]]:
    """What the trade list itself says: how many trades it shows, and each row's result."""
    shown = SHOWN.search(html)
    assert shown, "the list does not say how many trades it shows"
    nets = [int(n.replace("\u2212", "-").replace("\u20b9", "").replace("+", "").replace(",", "").strip())
            for n in NET.findall(html)]
    return int(shown.group(1)), nets


@pytest.fixture()
def made(demo, monkeypatch):
    """The signed-in pages, drawn from BUSY: the routes read this record in place of the demo's."""
    real = RM.load_record

    def load_made(request):
        early, record = real(request)
        if early is not None:
            return early, record
        _trips, imp, _context = record
        return None, (BUSY, imp, SF.record_context(BUSY))

    monkeypatch.setattr(RM, "load_record", load_made)
    monkeypatch.setattr(RN, "load_record", load_made)
    return demo


def test_most_in_a_day_is_read_on_a_day_that_is_not_the_best_day():
    tiles = N.build(BUSY, {}, gross=True)["tiles"]
    assert (tiles["best_day"]["day"], tiles["best_day"]["value"]) == ("2026-03-10", D(600))
    assert (tiles["worst_day"]["day"], tiles["worst_day"]["value"]) == ("2026-03-11", D(-350))
    assert (tiles["per_day"]["day"], tiles["per_day"]["most"]) == ("2026-03-09", 3)
    assert tiles["per_day"]["day"] != tiles["best_day"]["day"]


@pytest.mark.parametrize("label", list(WANT))
def test_each_day_tile_on_the_page_opens_its_own_days_closed_trades(made, label):
    html = made.get("/numbers").text
    assert tile_link(html, label) == CLOSED + WANT[label][0]


@pytest.mark.parametrize("label", list(WANT))
def test_the_list_a_tiles_link_opens_holds_the_trades_its_figure_counts(made, label):
    _iso, trades, net = WANT[label]
    page = made.get(tile_link(made.get("/numbers").text, label))
    assert page.status_code == 200
    shown, nets = on_the_list(page.text)
    assert shown == trades
    assert len(nets) == trades
    assert sum(nets) == net


@pytest.mark.parametrize("fault", ["day_page", "missing"])
@pytest.mark.parametrize("label", list(WANT))
def test_one_wrong_tile_link_is_caught_though_every_cell_is_right(made, monkeypatch, label, fault):
    real = N.build

    def broken(*args, **kwargs):
        view = real(*args, **kwargs)
        one = view["tiles"][KEYS[label]]
        one["href"] = "/mirror/day/" + one["day"] if fault == "day_page" else None
        return view

    monkeypatch.setattr(N, "build", broken)
    html = made.get("/numbers").text
    cal = re.search(r'<section class="cal" id="calendar">.*?</section>', html, re.DOTALL)
    assert cal, "no calendar on the page"
    cells = CELLS.findall(cal.group(0))
    assert cells and all(c.startswith(CLOSED) for c in cells)
    with pytest.raises(AssertionError):
        assert tile_link(html, label) == CLOSED + WANT[label][0]
    for other in WANT:
        if other != label:
            assert tile_link(html, other) == CLOSED + WANT[other][0]
