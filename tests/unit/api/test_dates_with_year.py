"""Every date on a page carries its year (TICKET-808).

A history can span years, so "07 Jan" alone leaves the trader guessing which one. The file
below is synthetic and spans three years, one option a day, two trades a day so that
Journals are written per day. The check is on the whole page, so a date that skips
formatting.day fails too.
"""

from __future__ import annotations

import os
import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from services.production.api import formatting
from services.production.api import scope_map as S
from services.production.api.app import create_app
from services.production.db import models as m
from services.production.db.session import make_engine, make_session, run_migrations
from tests.unit.api.test_scope_chapters import TRIPS
from tests.unit.api.test_upload import CSRF, sign_up

MONTHS = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
BARE_DATE = re.compile(rf"\b\d{{1,2}} (?:{MONTHS})\b(?! \d{{4}})", re.IGNORECASE)
HEADER = "Date,Time,Name,Buy/Sell,Order,Exchange,Segment,Quantity/Lot,Trade Price,Trade Value,Status"
DAYS = ["2024-06-14", "2024-11-05", "2025-01-07", "2025-08-14", "2026-03-27", "2026-07-13"]


def _day_rows(day: str, loss: int) -> list[str]:
    # An expiry in the same month: the adapter rejects one too far from the trade.
    option = f"WIDGETOIL 28 {MONTHS.split('|')[int(day[5:7]) - 1].upper()} 5000 CALL"
    rows = []
    for time_in, time_out, sold in (("09:30:00", "09:40:00", 5000 - loss), ("10:00:00", "10:10:00", 5100)):
        rows.append(f"{day},{time_in},{option},BUY,INTRADAY,MCX,Commodity,100,50.00,5000.00,Traded")
        rows.append(
            f"{day},{time_out},{option},SELL,INTRADAY,MCX,Commodity,100,{sold / 100:.2f},{sold:.2f},Traded"
        )
    return rows


FILE = "\n".join(
    [HEADER, *[row for i, day in enumerate(DAYS) for row in _day_rows(day, 100 * (i + 1))]]
) + "\n"


@pytest.fixture()
def client(scope_environment):
    engine = make_engine(os.environ["SCOPE_DB"])
    run_migrations(engine)
    signed_in = sign_up(TestClient(create_app()), engine, "YEARS", "years")
    token = CSRF.search(signed_in.get("/upload").text).group(1)
    sent = signed_in.post("/upload", files={"file": ("t.csv", FILE.encode(), "text/csv")},
                          data={"csrf_token": token}, follow_redirects=False)
    assert sent.status_code == 303, sent.text
    signed_in.engine_for_test = engine
    return signed_in


def _text(html: str) -> str:
    html = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.DOTALL)
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def _bare(client, path: str) -> list[str]:
    got = client.get(path)
    assert got.status_code == 200, path
    return BARE_DATE.findall(_text(got.text))


def test_a_day_is_written_with_its_year():
    assert formatting.day("2026-09-07") == "07 Sep 2026"
    assert formatting.day("2024-12-31") == "31 Dec 2024"


def test_a_trade_card_carries_its_year():
    assert S.trade(TRIPS[0], 1)["day"] == "01 Sep 2026"


def test_the_worst_days_list_shows_each_of_its_years(client):
    page = _text(client.get("/mirror/fact/worst-days").text)
    for year in ("2024", "2025", "2026"):
        assert re.search(rf"\b\d{{2}} (?:{MONTHS}) {year}\b", page), year


@pytest.mark.parametrize("key", list(S.FACTS))
def test_no_fact_page_has_a_date_without_a_year(client, key):
    assert _bare(client, f"/mirror/fact/{key}") == []


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_no_chapter_has_a_date_without_a_year(client, n):
    assert _bare(client, f"/mirror/chapter/{n}") == []


@pytest.mark.parametrize("path", ["/", "/mirror", "/mirror/reveal", "/journals",
                                  "/journals/catch-up", "/account", "/budget"])
def test_the_other_pages_have_no_date_without_a_year(client, path):
    assert _bare(client, path) == []


def test_a_journal_has_no_date_without_a_year(client):
    with make_session(client.engine_for_test) as sess:
        journal_id = sess.scalars(select(m.Journal.id)).first()
    assert _bare(client, f"/journals/{journal_id}") == []


def test_the_check_itself_catches_a_bare_date():
    """Guard: a check that can't fail proves nothing."""
    assert BARE_DATE.findall("Your busiest was 07 Sep, at 3") == ["07 Sep"]
    assert BARE_DATE.findall("Your busiest was 07 Sep 2026, at 3") == []
