"""Chapter 3 through the real routes, on the contract fixture, in both gate states [TICKET-832].

The figures come from the shared metrics on the same fixture, so this reads what a signed-in
trader is served; test_chapter_three_describes works the sentence out by hand.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.production.api import formatting
from services.production.mirror import metrics as mx
from tests.unit.api.test_chapter_three_describes import CLOSED, TITLE, card_of, head_of
from tests.unit.api.test_scope_chapters import readable

TRIPS = mx.load_trips(json.loads(Path("tests/fixtures/mirror_contract/main.json").read_text()))
TL = mx.two_straight_losses(TRIPS)
OPEN = (
    f"After two straight losses, your next trades averaged "
    f"{formatting.rupees(TL.condition_mean, exact=True)}. "
    f"Your other trades after two had closed averaged {formatting.rupees(TL.comparison_mean, exact=True)}."
)


@pytest.mark.parametrize(
    ("opened", "want"), [(False, CLOSED), (True, OPEN)], ids=["gate closed", "gate open"]
)
def test_the_served_pages_open_with_the_title_and_the_sentence(client, monkeypatch, opened, want):
    if opened:
        monkeypatch.setattr(mx, "post_loss_sentence_may_show", lambda trips: True)
    assert head_of(client.get("/mirror/fact/down").text) == (TITLE, want)
    assert card_of(client.get("/mirror/chapter/3").text, 1) == (TITLE, want)


# ---------- The story and where the pages go next, served [TICKET-827] ----------


def test_the_served_chapter_ends_with_the_way_into_chapter_four(client):
    page = client.get("/mirror/chapter/3").text
    assert page.rindex("Chapter 4: What we read") > page.index("Does this match your trading?")
    assert 'href="/mirror/chapter/4"' in page


def test_the_served_busiest_page_tells_the_day_and_goes_on(client):
    page = client.get("/mirror/fact/busiest").text
    day = formatting.day(mx.day_counts(TRIPS).busiest_day)
    assert f"{day}: {mx.day_counts(TRIPS).busiest_trips} trades." in readable(page)
    assert 'href="/mirror/chapter/4"' in page


def test_the_served_down_page_goes_to_the_next_fact(client):
    page = client.get("/mirror/fact/down").text
    assert "Next: Your busiest day" in page
    assert "Table 1" not in page
