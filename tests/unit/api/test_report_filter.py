"""The report's year and book filter (TICKET-904).

The file is synthetic and its figures are worked by hand: NIFTY options in January 2024 and
January 2025, and WIDGETOIL options (the test instrument) in November 2025.

    2024  NIFTY      one lot of 50, bought for 5000, sold for 4500   -500
    2025  NIFTY      one lot of 75, bought for 7500, sold for 7800   +300
    2025  WIDGETOIL  100 units, bought at 10.00, sold at 12.00      +200
    later upload:    WIDGETOIL, the next day, 10.00 to 9.00         -100
"""

from __future__ import annotations

import re
from decimal import Decimal
from urllib.parse import urlencode

from fastapi.testclient import TestClient

from services.production.api import report_filter as RF
from services.production.api.app import create_app
from services.production.mirror import metrics as mx
from tests.unit.api.test_read_again import HEADER, send, words
from tests.unit.api.test_upload import client, engine  # noqa: F401


def _nifty(day: str, time: str, side: str, value: int, expiry: str, units: int) -> str:
    """One NIFTY lot: 50 units in January 2024, 75 in January 2025 (profile lot_sizes)."""
    return (f"{day},{time},NIFTY {expiry} 20000 CALL,{side},INTRADAY,NSE,Derivative,{units},"
            f"{value / units:.2f},{value:.2f},Traded")


def _widget(day: str, time: str, side: str, price: str) -> str:
    return (f"{day},{time},WIDGETOIL 19 NOV 5000 CALL,{side},INTRADAY,MCX,Commodity,100,{price},"
            f"{Decimal(price) * 100:.2f},Traded")


FIRST = "\n".join([
    HEADER,
    _nifty("2024-01-02", "09:30:00", "BUY", 5000, "25 JAN", 50),
    _nifty("2024-01-02", "09:40:00", "SELL", 4500, "25 JAN", 50),
    _nifty("2025-01-07", "09:30:00", "BUY", 7500, "30 JAN", 75),
    _nifty("2025-01-07", "09:40:00", "SELL", 7800, "30 JAN", 75),
    _widget("2025-11-03", "11:00:00", "BUY", "10.00"),
    _widget("2025-11-03", "11:30:00", "SELL", "12.00"),
]).encode() + b"\n"
LATER = FIRST + "\n".join([
    _widget("2025-11-04", "11:00:00", "BUY", "10.00"),
    _widget("2025-11-04", "11:30:00", "SELL", "9.00"),
]).encode() + b"\n"


def choose(client, period: str = RF.ALL, book: str = "", next_: str = "/mirror"):  # noqa: F811
    return client.get("/mirror/filter?" + urlencode({"period": period, "book": book, "next": next_}),
                      follow_redirects=False)


def test_the_bar_offers_each_year_and_book_and_all(client):  # noqa: F811
    send(client, FIRST)
    page = client.get("/mirror").text
    said = words(page)
    for label in ("Period All 2024 2025", "Book All books", "NIFTY options", "WIDGETOIL options"):
        assert label in said, label
    assert RF.SINCE_WORDS not in said  # one upload: there is nothing to be "since"


def test_a_year_changes_every_page_and_says_so(client):  # noqa: F811
    send(client, FIRST)
    r = choose(client, "2025")
    assert r.status_code == 303 and r.headers["location"] == "/mirror"
    for path in ("/mirror", "/mirror/chapter/1", "/mirror/fact/worst-days"):
        assert "Showing 2025 only." in words(client.get(path).text), path
    home = words(client.get("/mirror").text)
    assert "2 trades" in home  # the 2025 trades only: one NIFTY, one WIDGETOIL


def test_the_choice_survives_a_page_move_and_clears_in_one_tap(client):  # noqa: F811
    send(client, FIRST)
    choose(client, "2024", next_="/mirror/chapter/2")
    assert "Showing 2024 only." in words(client.get("/mirror/fact/math").text)
    choose(client)
    assert "Showing" not in words(client.get("/mirror").text).split("Counted from your file")[0]


def test_a_book_row_is_a_link_that_filters_to_that_book(client, monkeypatch):  # noqa: F811
    """Each book gets its own row on Scope home only from a minimum of trades; this file is
    tiny, so the minimum is lowered to let each book have its row, as a real record's do."""
    monkeypatch.setattr(mx, "NAMED_BOOK_MINIMUM", 1)
    send(client, FIRST)
    page = client.get("/mirror").text
    link = re.search(r'<a class="link" href="(/mirror/filter\?[^"]*book=NIFTY\+options[^"]*)">NIFTY options</a>', page)
    assert link
    client.get(link.group(1).replace("&amp;", "&"))
    assert "Showing NIFTY options only." in words(client.get("/mirror/chapter/1").text)


def test_an_empty_choice_is_shown_not_hidden(client):  # noqa: F811
    send(client, FIRST)
    choose(client, "2024", "WIDGETOIL options")
    said = words(client.get("/mirror").text)
    assert "No trades here" in said and "Show everything" in said
    assert "Showing 2024 only, in WIDGETOIL options." in said


def test_each_book_shows_its_result_year_by_year(client, monkeypatch):  # noqa: F811
    """Each book gets its own row on Scope home only from a minimum of trades; this file is
    tiny, so the minimum is lowered to let each book have its row, as a real record's do."""
    monkeypatch.setattr(mx, "NAMED_BOOK_MINIMUM", 1)
    send(client, FIRST)
    said = words(client.get("/mirror").text)
    assert "By year: 2024 −₹500 · 2025 +₹300" in said
    assert "By year: 2024 no trades · 2025 +₹200" in said


def test_since_your_last_upload_reads_only_the_new_days(client):  # noqa: F811
    send(client, FIRST)
    send(client, LATER, name="later.csv")
    assert RF.SINCE_WORDS in words(client.get("/mirror").text)
    choose(client, RF.SINCE)
    said = words(client.get("/mirror").text)
    assert "Showing your trades since your last upload." in said
    assert "1 trades" in said or "1 trade" in said


def test_home_stays_the_whole_record(client):  # noqa: F811
    send(client, FIRST)
    before = words(client.get("/").text)
    choose(client, "2024")
    assert words(client.get("/").text) == before


def test_it_only_ever_goes_back_to_a_report_page(client):  # noqa: F811
    send(client, FIRST)
    for bad in ("https://elsewhere.example/", "//elsewhere.example", "/account"):
        assert choose(client, "2025", next_=bad).headers["location"] == "/mirror"


def test_a_year_the_file_does_not_hold_falls_back_to_all(client):  # noqa: F811
    send(client, FIRST)
    choose(client, "1999", "Gold options")
    assert "Showing" not in words(client.get("/mirror").text).split("Counted from your file")[0]


def test_the_sample_is_never_filtered(engine):  # noqa: F811
    visitor = TestClient(create_app())
    visitor.cookies.set(RF.COOKIE, "2026|")
    page = visitor.get("/sample").text
    assert "report-filter" not in page and "Showing" not in words(page).split("Counted from your file")[0]
