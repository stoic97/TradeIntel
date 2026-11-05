"""TICKET-840: "Trading on while already down" says what its count counts.

B2's population (services/shared/conditions/b2_condition.py, Annex A.1) is every
trade with at least two earlier same-day trades closed before it opened, whatever
those trades made. Only the condition asks that the two most recent both lost. The
sentence used to say the population's trades came "after two earlier trades that day
had already closed at a loss", which claims the condition of every trade in the
population. The words change; no number does.
"""

from __future__ import annotations

import re

from services.production.api import scope_facts as SF
from tests.unit.api.test_scope_chapters import TRIPS, chapter_page, readable
from tests.unit.api.test_scope_facts import fact_page

SENTENCE = (
    "On {population} occasions you opened a trade after two earlier trades that day had "
    "already closed. On {condition} of those, the two most recent had both lost."
)
CAPTION = "Every trade opened after two earlier trades that day had already closed."
OLD_CLAIM = "had already closed at a loss"


def counts() -> dict[str, int]:
    two_losses = SF.record_context(TRIPS)["two_losses"]
    return {"population": two_losses.population, "condition": two_losses.condition}


def test_the_fixture_has_trades_the_old_sentence_misdescribed():
    """Without this the wording tests below would pass on a history where the two
    readings agree: some of the population must not be after two losses."""
    c = counts()
    assert c["population"] > c["condition"] > 0


def test_the_chapter_three_card_says_what_its_count_counts():
    page = readable(chapter_page(3))
    assert SENTENCE.format(**counts()) in page
    assert OLD_CLAIM not in page


def test_the_fact_page_says_what_its_count_counts():
    page = readable(fact_page("down"))
    assert SENTENCE.format(**counts()) in page
    assert OLD_CLAIM not in page


def test_the_fact_pages_trades_are_captioned_for_what_they_are():
    page = fact_page("down")
    caption = re.search(r'<p class="evidence__caption">(.*?)</p>', page, re.DOTALL)[1]
    assert readable(caption).startswith(CAPTION)
