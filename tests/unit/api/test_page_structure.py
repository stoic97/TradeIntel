"""TICKET-1029: the report's page structure on a phone.

The five-step ladder's words once per page (each finding keeps its own five marks), books under
the minimum folded on the hidden and math pages as the clock already folds them, the filter bar
one line on a phone, and the filter saying so when the choice it was given can't apply. The
record is the demo file (made up); nothing here is a trader's.
"""
from __future__ import annotations

import os
import re

import pytest
from fastapi.testclient import TestClient

from services.production.api import report_filter as RF
from services.production.api.app import create_app
from services.production.db.session import make_engine, run_migrations
from services.production.mirror import metrics as mx
from tests.helpers.upload import CSRF, sign_up

SAYS = "it appears in your file."  # the first rung's words: on a page once, never per card
LADDER = re.compile(r'<ol class="ladder[^"]*" data-ladder="([^"]+)">(.*?)</ol>', re.DOTALL)


@pytest.fixture()
def client():
    engine = make_engine(os.environ["SCOPE_DB"])
    run_migrations(engine)
    c = sign_up(TestClient(create_app()), engine, "S-1", "structurereader")
    c.post("/upload/demo", data={"csrf_token": CSRF.search(c.get("/upload").text).group(1)},
           follow_redirects=False)
    return c


def main_of(html: str) -> str:
    return re.search(r"<main.*?</main>", html, re.DOTALL).group(0)


# ---------- 1. the ladder: marks per finding, words once per page ----------

@pytest.mark.parametrize("path", ["/mirror/chapter/1", "/mirror/chapter/2", "/mirror/chapter/3",
                                  "/mirror/fact/money", "/mirror/fact/clock"])
def test_the_ladders_words_appear_once_on_a_page(client, path):
    page = main_of(client.get(path).text)
    assert page.count(SAYS) == 1, path
    assert re.search(r'<details class="ladder-words">\s*<summary[^>]*>', page), path


def test_each_finding_keeps_its_own_five_marks_with_their_names_for_a_screen_reader(client):
    page = client.get("/mirror/chapter/1").text
    found = LADDER.findall(page)
    assert len(found) == 3
    for _key, inner in found:
        marks = re.findall(r'<li class="ladder__mark[^"]*"[^>]*data-reached="(yes|no)"', inner)
        assert len(marks) == 5
        assert inner.count('class="visually-hidden"') == 5
        assert "Seen" in inner and "Not reached" in inner


# ---------- 2. small books folded ----------

def test_books_under_the_minimum_fold_on_the_hidden_page(client):
    page = main_of(client.get("/mirror/fact/hidden").text)
    fold = re.search(r'<details class="books-fold">(.*?)</details>', page, re.DOTALL)
    assert fold, "no fold on the hidden page"
    assert f"under {mx.BOOK_ROW_MINIMUM} same-day trades" in re.sub(r"<[^>]+>", "", fold.group(1))
    assert "Stocks and ETFs" in fold.group(1)        # the demo's one-trade book
    assert "NIFTY options" not in fold.group(1)      # a counted book stays out of the fold


def test_books_under_the_minimum_fold_on_the_math_page(client):
    page = main_of(client.get("/mirror/fact/math").text)
    fold = re.search(r'<details class="books-fold">(.*?)</details>', page, re.DOTALL)
    assert fold, "no fold on the math page"
    assert "Stocks and ETFs" in fold.group(1)
    table = page[:page.index('<details class="books-fold">')]
    assert "Crude options" in table and "NIFTY options" in table


# ---------- 3. the filter bar on a phone ----------

def test_the_filter_bar_has_a_one_line_phone_form_and_keeps_its_links(client):
    page = client.get("/mirror").text
    phone = re.search(r'<details class="report-filter__phone">\s*<summary[^>]*>(.*?)</summary>', page,
                      re.DOTALL)
    assert phone, "no phone form of the filter bar"
    said = re.sub(r"<[^>]+>|\s+", " ", phone.group(1))
    assert "All" in said and "All books" in said
    assert 'class="report-filter__desk"' in page       # desktop keeps its rows


# ---------- 4. the filter says when it can't apply ----------

def test_since_your_last_upload_says_so_when_there_is_nothing_since(client):
    client.cookies.set(RF.COOKIE, f"{RF.SINCE}|")
    page = client.get("/mirror").text
    assert "no new days since an earlier upload, so this shows everything" in page


def test_a_book_the_file_does_not_hold_says_so(client):
    client.cookies.set(RF.COOKIE, "all|Gold options")
    page = client.get("/mirror").text
    assert "That book isn't in this file, so this shows every book." in page
