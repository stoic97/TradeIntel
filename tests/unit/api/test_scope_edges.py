"""The Scope's edge states (handoff 4): what shows when there is nothing, or not enough.

The instrument and no-trades pages keep the app's own words, word for word (handoff
6), on the kit's layout (edge screens e6, e7). A fact that cannot be counted keeps
its card, with its state, on the chapter page (e1, e3).
"""

from __future__ import annotations

import pytest

from services.shared.schemas import scope_v1 as s
from tests.unit.api.templating import template_env
from tests.unit.api.test_scope_chapters import chapter_page, readable, trips_from


def render(name: str, **context) -> str:
    return template_env().get_template(name).render(title="Your record", **context)


def test_an_instrument_not_set_up_is_our_gap_said_in_the_apps_words():
    page = render("mirror_no_profile.html", reason="No profile for MCX WIDGETOIL")
    text = readable(page)
    assert '<h1 class="title">Your record is not ready yet</h1>' in page
    assert (
        "Your file was read in full, but it holds an instrument Scope does not yet carry "
        "the facts for — the exchange's session hours and the contract's size — and "
        "without those it cannot say which trading day a trade belongs to, or how large "
        "it was. We do not guess them."
    ) in text
    assert '<p class="num num--label edge__reason">No profile for MCX WIDGETOIL</p>' in page
    assert (
        "This is our gap, not a problem with your file. Nothing has been discarded; the "
        "record appears as soon as the instrument is added."
    ) in text
    assert '<a class="link" href="/account">Your account</a>' in page
    assert 'aria-current="page">Scope</a>' in page


def test_no_trades_rebuilt_says_so_and_offers_the_upload():
    page = render("mirror_empty.html")
    assert '<p class="label label--plain">Nothing to count yet</p>' in page
    assert (
        "There is nothing here yet. Upload a tradebook and this page fills with what it says."
    ) in page
    assert '<a class="btn btn--primary btn--block" href="/upload">Upload a tradebook</a>' in page
    assert "0%" not in page


@pytest.mark.parametrize("name", ["mirror_no_profile.html", "mirror_empty.html"])
def test_the_edge_pages_are_on_the_kits_layout(name):
    page = render(name, reason="x")
    assert '<link rel="stylesheet" href="/static/css/components.css">' in page
    assert "/static/scope.css" not in page


def test_a_fact_with_not_enough_trades_keeps_its_card_with_its_state():
    page = chapter_page(2, trips_from([100, 200, 300, 50]))  # no losers: hold and run
    assert page.count('<a class="story-card story-card--state"') == 2
    assert page.count("Not enough trades yet") == 2
    assert page.count('story-card__figure story-card__figure--state">—</span>') == 2
    assert '<span class="num">4</span> trades so far' in page
    assert 'href="/mirror/fact/hold?enter=lens"' in page  # still opens


def test_a_fact_not_in_the_file_says_what_is_missing():
    page = chapter_page(4, trips_from([100, -50], s.RiskUnitSourceV1.UNAVAILABLE))
    assert '<a class="story-card story-card--state story-card--dashed"' in page
    assert "Your export has no stop column, and no budget is set." in page
    assert "What is missing, in full" in page
