"""The risk fact says no budget is set, and links to where to set one [TICKET-805].

Without a stop or a budget this fact is in its not-in-file state, which hides the table, and
with it the one line that says why premium paid is not a risk figure. So the state carries
that line too. The Mirror's words are kept as written; only a link is added.
"""

from __future__ import annotations

from services.shared.schemas import scope_v1 as s
from tests.unit.api.test_scope_chapters import chapter_page, readable, trips_from
from tests.unit.api.test_scope_facts import fact_page

NOTHING = trips_from([100, -50, 30], s.RiskUnitSourceV1.UNAVAILABLE)
BUDGET = trips_from([100, -50, 30], s.RiskUnitSourceV1.DECLARED_BUDGET)
LINK = '<a class="link" href="/budget">no budget is set</a>'
PREMIUM = (
    "Premium paid is the most you could have lost on an option, not what you had at risk, "
    "so it is counted here and used nowhere else."
)


def test_the_line_links_to_the_budget_page():
    assert LINK in fact_page("risk", NOTHING)


def test_the_sentence_still_reads_word_for_word():
    assert "Your export has no stop column, and no budget is set." in readable(
        fact_page("risk", NOTHING)
    )


def test_it_says_why_premium_paid_is_not_a_risk_figure():
    assert PREMIUM in readable(fact_page("risk", NOTHING))


def test_with_a_budget_there_is_no_link_to_set_one():
    assert LINK not in fact_page("risk", BUDGET)


def test_with_a_budget_the_premium_line_is_said_once():
    assert readable(fact_page("risk", BUDGET)).count(PREMIUM) == 1


def test_the_chapter_card_keeps_a_single_link():
    """The whole card is a link to the fact, and a link cannot hold another link."""
    assert 'href="/budget"' not in chapter_page(4, NOTHING)
