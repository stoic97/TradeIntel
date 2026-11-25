"""TICKET-1051: the report's filter line in each state, read off the rendered page, and the 29/30
fold boundary on the math and clock pages as on the hidden page.

Filter states, each on the page a reader opens: a later upload that added no new days, with no
book chosen and with a book chosen; a different file that added no new days; and a reader with
one upload, who never reads "Your last upload added no new days" (there is no last upload).

Folds: made-up books of 29 and 30 same-day trades. A book under 30 folds; a book of 30 does not.
"""
from __future__ import annotations

import dataclasses
import re

import pytest
from fastapi.testclient import TestClient

from services.production.api import report_filter as RF
from services.production.api import routes_mirror
from services.production.api.app import create_app
from services.production.mirror import metrics as mx
from tests.helpers.scope_chapters import trips_from
from tests.helpers.scope_facts import fact_page
from tests.helpers.upload import CSRF, sign_up

LAST_ADDED_NONE = "Your last upload added no new days"
EVERYTHING = "Your last upload added no new days, so this shows everything."


def plain(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def filter_line(html: str) -> str:
    """The words under the filter bar, as the page draws them."""
    nav = re.search(r'<nav class="report-filter".*?</nav>', html, re.DOTALL)
    assert nav, "no filter bar on the page"
    return " ".join(plain(p) for p in re.findall(
        r'<p class="body report-filter__words" role="status">(.*?)</p>', nav.group(0), re.DOTALL))


@pytest.fixture()
def reader(engine):
    client = sign_up(TestClient(create_app()), engine, "F-1", "filterreader")
    client.post("/upload/demo", data={"csrf_token": CSRF.search(client.get("/upload").text).group(1)})
    return client


def asked(client, period: str, book: str | None = None) -> None:
    client.cookies.set(RF.COOKIE, RF.ReportFilter(period, book).encode())


# ---------- 3. each filter state, on the rendered page ----------

def test_a_reader_with_one_upload_never_reads_that_his_last_upload_added_nothing(reader):
    asked(reader, RF.SINCE)
    line = filter_line(reader.get("/mirror").text)
    assert LAST_ADDED_NONE not in line
    assert line == "There is no upload before this one, so this shows everything."


def test_one_upload_with_a_book_chosen_keeps_the_book(reader):
    asked(reader, RF.SINCE, "NIFTY options")
    line = filter_line(reader.get("/mirror").text)
    assert LAST_ADDED_NONE not in line
    assert line.startswith("There is no upload before this one, so this shows every day in NIFTY options.")


def test_a_later_upload_with_no_new_days_and_no_book(reader, monkeypatch):
    monkeypatch.setattr(routes_mirror, "_earlier_upload", lambda sess, imp: True)
    monkeypatch.setattr(routes_mirror, "_new_days", lambda sess, imp: None)  # the same file read again
    asked(reader, RF.SINCE)
    assert filter_line(reader.get("/mirror").text) == EVERYTHING


def test_a_later_upload_with_no_new_days_and_a_book_chosen(reader, monkeypatch):
    monkeypatch.setattr(routes_mirror, "_earlier_upload", lambda sess, imp: True)
    monkeypatch.setattr(routes_mirror, "_new_days", lambda sess, imp: None)
    asked(reader, RF.SINCE, "NIFTY options")
    line = filter_line(reader.get("/mirror").text)
    assert line.startswith("Your last upload added no new days, so this shows every day in NIFTY options.")
    assert "shows everything" not in line  # the words line under it keeps its "Show everything" link


def test_a_different_file_that_added_no_new_days(reader, monkeypatch):
    monkeypatch.setattr(routes_mirror, "_earlier_upload", lambda sess, imp: True)
    monkeypatch.setattr(routes_mirror, "_new_days", lambda sess, imp: set())  # a new file, every day known
    asked(reader, RF.SINCE)
    assert filter_line(reader.get("/mirror").text) == EVERYTHING


def test_the_dropped_line_says_whether_there_was_an_upload_before():
    since, every = RF.ReportFilter(RF.SINCE), RF.ReportFilter(RF.ALL)
    assert RF.dropped(since, every, earlier=True) == EVERYTHING
    assert RF.dropped(since, every, earlier=False) == "There is no upload before this one, so this shows everything."


# ---------- 4. the 29/30 fold boundary on math and clock, as on hidden ----------

def book(n: int, symbol: str) -> list[mx.Trip]:
    return [dataclasses.replace(t, trip_id=f"{symbol}{i}", symbol=symbol)
            for i, t in enumerate(trips_from([100 if k % 3 else -80 for k in range(n)]))]


SMALL, BIG = book(29, "WIDGETOIL"), book(30, "GADGETCO")


def folded(page: str, cls: str) -> str:
    found = re.search(rf'<details class="{cls}">(.*?)</details>', page, re.DOTALL)
    return found.group(1) if found else ""


@pytest.mark.parametrize("key, cls", [("hidden", "books-fold"), ("math", "books-fold"), ("clock", "clock-others")])
def test_twenty_nine_trades_fold_and_thirty_do_not(key, cls):
    page = fact_page(key, SMALL + BIG)
    fold = folded(page, cls)
    assert mx.trade_book(SMALL[0]) in fold, key
    assert mx.trade_book(BIG[0]) not in fold, key
    assert mx.trade_book(BIG[0]) in page, key


@pytest.mark.parametrize("key, cls", [("math", "books-fold"), ("clock", "clock-others")])
def test_at_thirty_each_nothing_folds(key, cls):
    page = fact_page(key, book(30, "WIDGETOIL") + BIG)
    assert folded(page, cls) == "", key
