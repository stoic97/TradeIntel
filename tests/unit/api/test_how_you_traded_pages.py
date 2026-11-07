"""TICKET-883: on the pages about how you traded, a figure states a fact in a trader's words.

Rendered on the made-up demo file. The rewording says what the numbers already said: nothing here
may start naming a cause, scoring, estimating what a habit cost, or recommending a change.
"""

from __future__ import annotations

import re
from html import unescape
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services.production.api import formatting
from services.production.api import glossary as GL
from services.production.api import scope_map as SM
from services.production.api.app import create_app
from tests.unit.api import figure_pages as P

PAGES = ("/mirror/fact/down", "/mirror/fact/run", "/mirror/fact/math", "/mirror/fact/risk",
         "/mirror/chapter/2", "/mirror/chapter/3", "/mirror/chapter/4", "/mirror")
RETIRED = ("strike rate", "qualified", "qualifying", "net (gross)", "the math")
CLAIMS = ("because you", "you should", "should have", "would have", "if you had", "cost you",
          "your score", "try to", "avoid")


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


@pytest.mark.parametrize("path", PAGES)
def test_the_retired_words_are_gone(client, path):
    text = words(client.get(path).text).lower()
    for word in RETIRED:
        assert word not in text, word


@pytest.mark.parametrize("path", PAGES)
def test_nothing_starts_claiming_more(client, path):
    # The boundary table's own row says it refuses this, and that's the opposite of a claim.
    text = words(client.get(path).text).lower().replace("what a habit cost you", "")
    for phrase in CLAIMS:
        assert phrase not in text, phrase


def test_the_rate_is_a_count_with_the_finding_beside_it(client):
    text = words(client.get("/mirror/fact/math").text)
    assert re.search(r"\d+ of 100 trades made money: [\d,]+ winners against [\d,]+ losers\.", text)
    assert re.search(r"At those sizes, you break even at \d+ of 100\.", text)


def test_the_math_page_has_its_new_title():
    assert SM.FACTS["math"].title == "Your wins and losses"


def test_the_hub_says_it_the_same_way(client):
    text = words(client.get("/mirror").text)
    assert re.search(r"\d+ of 100 same-day trades made money\.", text)


def test_the_down_table_says_what_each_row_is(client):
    text = words(client.get("/mirror/chapter/3").text)
    assert "Your other trades after two had closed" in text
    assert "Trades Result Average" in text
    assert "Win rate Average lots" in text


def test_the_lead_figures_say_what_they_count(client):
    down = words(client.get("/mirror/fact/down").text)
    chapter = words(client.get("/mirror/chapter/3").text)
    assert re.search(r"After two straight losses ?[\d,]+ trades", chapter), down[:80]
    assert re.search(r"Longest losing run ?\d+ loss", words(client.get("/mirror/chapter/2").text))


def test_a_good_sentence_is_left_alone():
    source = Path("services/production/api/templates/scope/_hub_answer.html").read_text()
    assert "sold-option" in source and "no risk cap, and no budget is set" in source


@pytest.mark.parametrize(("rate", "said"), [("45.8", "46 of 100"), ("45.5", "46 of 100"),
                                             ("45.4", "45 of 100"), ("100", "100 of 100")])
def test_a_rate_rounds_as_a_person_says_it(rate, said):
    assert formatting.out_of_a_hundred(rate) == said


def test_the_words_are_in_the_glossary_for_every_page():
    gone = {e.word for e in GL.GLOSSARY if e.status == GL.RETIRED and e.where is None}
    assert gone >= {"strike rate", "qualified", "Net (gross)", "the math"}


def test_the_page_leads_with_the_count_its_card_leads_with(client):
    """A bare percentage read aloud states nothing: the page's largest figure has to say
    what the card's says."""
    page = client.get("/mirror/fact/math").text
    hero = re.search(r'num--hero">(.*?)</span>', page, re.DOTALL)[1].strip()
    assert re.fullmatch(r"\d+ of 100 trades", hero)


def test_the_trades_listed_are_captioned_as_the_trades_listed(client):
    """The list holds the trades right after two straight losses. "Every trade opened after
    two earlier trades had closed" is the larger count, written above a smaller one."""
    text = words(client.get("/mirror/fact/down").text)
    assert "Every trade you opened right after two straight losses." in text
    assert "Every trade opened after two earlier trades that day had already closed." not in text
