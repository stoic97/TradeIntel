"""What the pages say about the five worst days [TICKET-812].

Through the 40-trade fixture: every one of its eight days loses, the worst five come to
-24,000 of -25,000, so 96%. Five of eight days is 62.5%, which rounds to 63%.
"""

from __future__ import annotations

import pytest

from services.production.api import scope_facts as SF
from services.production.api import scope_map as S
from tests.unit.api.test_reveal_page import reveal
from tests.unit.api.test_scope_chapters import IMP, TRIPS, chapter_page, readable, trips_from
from tests.unit.api.test_scope_facts import fact_page

SENTENCE = "5 of your 8 trading days (about 63%) carried about 96% of your losses."
OLD = "of your result"


def test_the_reveal_gives_the_share_the_base_rate_and_the_rupees():
    page = readable(reveal())
    assert SENTENCE in page
    assert "Those five days came to −₹24,000." in page
    assert "Your result for the whole period was −₹25,000." in page


def test_the_worst_days_page_no_longer_leads_with_the_same_sentence():
    """The reveal and the chapter card say it; three pages in a row saying it was the problem."""
    assert SENTENCE not in readable(fact_page("worst-days"))


def test_the_chapter_cards_say_the_same():
    assert SENTENCE in readable(chapter_page(1))


def test_the_fact_is_named_for_what_it_measures():
    assert S.FIGURES["share"].title == "Share of your losses"


@pytest.mark.parametrize(
    "page",
    [
        lambda: reveal(),
        lambda: fact_page("worst-days"),
        lambda: chapter_page(1),
    ],
)
def test_no_page_calls_it_a_share_of_the_result(page):
    assert OLD not in readable(page())


def test_scope_home_centre_is_the_result_not_the_share():
    """The share still reads "of your losses" on its own fact; home's centre is the result."""
    view = SF.home_view(SF.record_context(TRIPS), IMP)
    assert "of your losses" not in view["centre"]["captionLines"]


def test_a_history_with_no_losing_day_tells_the_rupees_only():
    page = readable(fact_page("worst-days", trips_from([10, 20, 30, 40, 50, 60])))
    assert "of your losses" not in page.replace("Share of your losses", "")
    assert "Your result for the whole period was +₹210." in page
