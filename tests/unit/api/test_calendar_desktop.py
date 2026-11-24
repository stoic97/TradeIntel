"""TICKET-1034: Your numbers on desktop. The calendar's months sit side by side from 1024 px,
and each traded cell prints its day's result in short form there. Phones are unchanged: the
short figure is hidden below 1024 px and from screen readers (the text table carries the
figures). Every cell still opens exactly its trades. Trades here are made up.
"""
from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from services.production.api import numbers as N
from services.production.api.app import create_app
from services.production.api.figures import Figure
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s
from tests.helpers.upload import CSRF, sign_up

IST = ZoneInfo("Asia/Kolkata")
D = Decimal
CSS = Path("services/production/api/static/css/app.css").read_text(encoding="utf-8")


def trip(tid: str, day: str, net: str) -> mx.Trip:
    entry = datetime.fromisoformat(f"{day}T10:00").replace(tzinfo=IST)
    leave = datetime.fromisoformat(f"{day}T10:20").replace(tzinfo=IST)
    return mx.Trip(trip_id=tid, symbol="NIFTY", trading_day=day, entry_ts=entry, exit_ts=leave,
                   holding_seconds=1200, net=D(net), lots=1,
                   risk_unit_source=s.RiskUnitSourceV1.PREMIUM_PAID, is_option=True,
                   lines=(mx.TradeLine("NIFTY", "OPT", "Buy", 1, None, None, D(net)),))


# 2 Mar +1,800 (two trades), 3 Mar -620, 4 Mar +45, 5 Mar -12,500, 6 Mar 0 (a level day).
RECORD = [trip("a", "2026-03-02", "1000"), trip("b", "2026-03-02", "800"),
          trip("c", "2026-03-03", "-620"), trip("d", "2026-03-04", "45"),
          trip("e", "2026-03-05", "-12500"), trip("f", "2026-03-06", "0")]


def cells() -> dict[str, dict]:
    view = N.calendar(RECORD)
    return {c["iso"]: c for m in view["months"] for w in m["weeks"] for c in w if c}


# ---------- 2. each traded cell carries its short result ----------

def test_a_traded_cell_carries_its_result_in_short_form_as_a_figure():
    c = cells()
    assert isinstance(c["2026-03-02"].get("short"), Figure), "a traded cell has no short figure"
    assert [str(c[d]["short"]) for d in ("2026-03-02", "2026-03-03", "2026-03-04", "2026-03-05")] == [
        "+1.8k", "−620", "+45", "−12.5k"]
    assert str(c["2026-03-06"]["short"]) == "0"


def test_an_untraded_day_carries_no_short_figure():
    c = cells()
    assert "short" in c["2026-03-07"] and c["2026-03-07"]["short"] is None  # a Saturday


# ---------- 1, 2. desktop only, through CSS; no script ----------

def test_months_sit_side_by_side_from_1024px_and_short_figures_show_only_there():
    anchor = "/* Your numbers on desktop"
    assert anchor in CSS, "no desktop calendar block in app.css"
    desktop = re.search(r"@media \(min-width: 1024px\) \{(.*?)\n\}", CSS[CSS.index(anchor):], re.DOTALL)
    assert desktop, "no 1024 px block for the calendar"
    block = desktop.group(1)
    assert ".cal__months" in block and "grid-template-columns" in block
    assert ".cal__result" in block
    assert re.search(r"\.cal__result \{[^}]*display: none", CSS), "the short figure is shown on a phone"


@pytest.fixture()
def demo(engine):
    client = sign_up(TestClient(create_app()), engine, "K-1", "visitor")
    client.post("/upload/demo", data={"csrf_token": CSRF.search(client.get("/upload").text).group(1)})
    return client


def test_the_page_draws_the_short_figure_hidden_from_screen_readers(demo):
    html = demo.get("/numbers").text
    section = re.search(r'<section class="cal" id="calendar">.*?</section>', html, re.DOTALL).group(0)
    assert '<div class="cal__months">' in section
    results = re.findall(r'<text[^>]*class="cal__result[^"]*"[^>]*>', section)
    assert results and all('aria-hidden="true"' in t for t in results)
    assert "<script" not in section


# ---------- 3. nothing else moves ----------

def test_every_traded_cell_still_opens_its_trades(demo):
    html = demo.get("/numbers").text
    section = re.search(r'<section class="cal" id="calendar">.*?</section>', html, re.DOTALL).group(0)
    links = re.findall(r'<a href="([^"]+)" class="cal__day">', section)
    results = re.findall(r'class="cal__result', section)
    assert links and len(results) == len(links)  # one short figure per traded (linked) cell


@pytest.mark.parametrize("net", [Decimal("0.40"), Decimal("-0.40"), Decimal(0)])
def test_a_day_that_rounds_to_nothing_reads_a_bare_zero(net):
    """Review: a day of plus or minus forty paise printed "+0" / "−0" while its title says ₹0."""
    assert str(N._cell_short(net)) == "0"
