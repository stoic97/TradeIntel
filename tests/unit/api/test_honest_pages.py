"""TICKET-884: on the honest pages, a count says what it counts.

Cover the label, read the figure aloud, and it states a fact. These pages' words are mostly right
already, so this holds only the counts that weren't, and that their boundary table stays whole.
Everything is read from rendered pages on the made-up demo file.
"""

from __future__ import annotations

import re
from html import unescape

import pytest
from fastapi.testclient import TestClient

from services.production.api import days_worth_a_look as worth
from services.production.api.app import create_app
from tests.unit.api import figure_pages as P


def words(html: str) -> str:
    text = re.sub(r"<(script|style|svg)\b.*?</\1>", " ", html, flags=re.DOTALL)
    text = re.sub(r"</?(span|a|strong|em)\b[^>]*>", "", text)
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", text)).replace("\xa0", " ").split())


@pytest.fixture()
def client():
    app = create_app()
    client = TestClient(app, follow_redirects=False)
    P._sign_up(client, app.state.engine, "visitor")
    P._consent(client)
    client.post("/upload/demo", data={"csrf_token": P._token(client, "/upload")})
    return client


@pytest.mark.parametrize("path", ["/mirror/fact/unread", "/mirror/chapter/4"])
def test_what_we_read_counts_its_rows_and_trades(client, path):
    text = words(client.get(path).text)
    assert re.search(r"Rows in your file [\d,]+ rows", text)
    assert re.search(r"Rows we read [\d,]+ rows", text)
    assert re.search(r"Rows set aside [\d,]+ rows", text)
    assert re.search(r"Trades reconstructed [\d,]+ trades", text)
    assert re.search(r"Trades refused [\d,]+ trades", text)


def test_the_busiest_day_on_the_last_page_says_what_it_was_at(client):
    assert re.search(r"Your busiest was \d\d \w+ \d{4}, at \d+ trades", words(
        client.get("/mirror/fact/not-told").text))


def test_a_flagged_run_is_not_your_date(client):
    text = words(client.get("/mirror/fact/not-told").text)
    assert not re.search(r"Your \d\d \w+ \d{4}", text)
    assert re.search(r"\d\d \w+ \d{4} — \d+ losses in a row", text)


def test_the_journal_list_says_what_it_has_so_far(client):
    assert re.search(r"[\d,]+ Journals so far", words(client.get("/journals").text))


def test_a_losing_run_flag_says_losses(client):
    assert re.search(r"longest losing run: \d+ losses in a row", words(client.get("/journals").text))


@pytest.mark.parametrize(("n", "said"), [(1, "1 loss"), (2, "2 losses")])
def test_a_run_counts_in_the_singular_too(n, said):
    assert worth.losses_in_a_row(n) == f"{said} in a row"


def test_the_table_of_what_the_report_doesnt_do_keeps_its_four_rows(client):
    text = words(client.get("/mirror/fact/not-told").text)
    for row in ("Name a cause", "Score you", "Estimate what a habit cost you", "Recommend a change"):
        assert row in text, row
