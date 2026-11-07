"""TICKET-882: on the pages about where the money went, a figure states a fact.

Cover the label, read the figure aloud. These hold the wording that didn't, on rendered pages on
the made-up demo file, and that the rewording claims nothing the number doesn't support.
"""

from __future__ import annotations

import re
from html import unescape

import pytest
from fastapi.testclient import TestClient

from services.production.api.app import create_app
from tests.unit.api import figure_pages as P

PAGES = ("/mirror/fact/money", "/mirror/fact/worst-days", "/mirror/fact/busiest", "/mirror/fact/clock")
NEVER = ("cost you", "would have", "should have", "because you", "you should", "if you had")


def words(html: str) -> str:
    text = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.DOTALL)
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


def test_the_best_and_worst_five_say_five_of_what(client):
    text = words(client.get("/mirror/fact/money").text)
    assert re.search(r"Your best five trades came to \+₹[\d,]+\.", text)
    assert re.search(r"Your worst five trades came to −₹[\d,]+\.", text)
    assert "Your best five trades ran a median of" in text
    assert re.search(r"All 10 trades are in one", text)


def test_a_worst_day_says_more_of_what(client):
    assert re.search(r"First trade [−+]₹[\d,]+, then \d+ more trades?; \d+ lost\.",
                     words(client.get("/mirror/fact/worst-days").text))


def test_the_clock_says_what_its_figure_is(client):
    text = words(client.get("/mirror/fact/clock").text)
    assert re.search(r"The clock \d\d:00 hour ", text)


def test_the_clocks_chart_and_table_say_result(client):
    text = words(client.get("/mirror/fact/clock").text)
    assert "Result by the hour you opened" in text
    assert "Hour you opened Result Trades" in text


def test_a_trade_list_says_result(client):
    text = words(client.get("/mirror/fact/money").text)
    assert "DayInOutHeldResult" in text


@pytest.mark.parametrize("path", PAGES)
def test_gross_is_still_said_once_at_the_top(client, path):
    assert "every rupee figure below is gross" in words(client.get(path).text)


@pytest.mark.parametrize("path", PAGES)
def test_nothing_starts_estimating_or_advising(client, path):
    text = words(client.get(path).text).lower()
    for phrase in NEVER:
        assert phrase not in text, phrase


def test_the_clocks_card_says_result_too(client):
    """A card renders on its chapter's page, which no fact page's check reads."""
    assert "net (gross)" not in words(client.get("/mirror/chapter/2").text).split("The clock")[1].lower()
