"""The budget page can be reached from the report and the account page [TICKET-806].

It was only reachable through the reveal page's "Continue". No new words: a row in a table
already says "Your declared budget", and the other two links use the page's own title.
"""

from __future__ import annotations

import pytest

from services.shared.schemas import scope_v1 as s
from tests.unit.api.test_deletion_page import client, engine, store  # noqa: F401
from tests.unit.api.test_scope_chapters import chapter_page, readable, trips_from
from tests.unit.api.test_scope_facts import fact_page

NOTHING = trips_from([100, -50, 30], s.RiskUnitSourceV1.UNAVAILABLE)
STOP = trips_from([100, -50, 30], s.RiskUnitSourceV1.DEFINED_STOP)
BUDGET = trips_from([100, -50, 30], s.RiskUnitSourceV1.DECLARED_BUDGET)
TABLE_ROW = '<a class="link" href="/budget">Your declared budget</a>'
SETTINGS_ROW = '<a class="settings-row" href="/budget"><span class="body">What you risk</span>'


@pytest.mark.parametrize("trips", [NOTHING, STOP, BUDGET], ids=["nothing", "stop", "budget"])
def test_the_risk_fact_reaches_it_whatever_the_history(trips):
    assert 'href="/budget"' in fact_page("risk", trips)


@pytest.mark.parametrize("trips", [STOP, BUDGET], ids=["stop", "budget"])
def test_the_table_row_is_the_link(trips):
    assert TABLE_ROW in fact_page("risk", trips)


def test_the_table_row_still_reads_the_same():
    assert "Your declared budget" in readable(fact_page("risk", STOP))


@pytest.mark.parametrize("trips", [NOTHING, STOP, BUDGET], ids=["nothing", "stop", "budget"])
def test_the_chapter_card_keeps_a_single_link(trips):
    """The whole card is a link to the fact, and a link cannot hold another link."""
    assert 'href="/budget"' not in chapter_page(4, trips)


def test_the_end_of_the_report_reaches_it():
    assert SETTINGS_ROW in fact_page("not-told")


def test_the_account_page_reaches_it(client):  # noqa: F811
    assert SETTINGS_ROW in client.get("/account").text


def test_it_comes_first_under_the_settings(client):  # noqa: F811
    page = client.get("/account").text
    assert page.index("What you risk") < page.index("What you agreed to")
