"""The guess and the reveal, rendered (handoff 5 and 7, screens 10 and 12).

The reveal's dial is drawn by scope_geometry at the kit's 300 px and held here to
the kit's own path strings; the pages are rendered through the app's templates.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from services.production.api import scope_facts as SF
from tests.unit.api.templating import template_env
from tests.unit.api.test_scope_chapters import TRIPS, readable, trips_from

KIT = Path("docs/design/scope-kit/screens/12-reveal.html").read_text()
CTX = SF.record_context(TRIPS)


def kit_path(cls: str) -> str:
    return re.search(rf'<path class="{cls}" d="([^"{{]+)"', KIT)[1]


def test_the_reveal_dial_is_the_kits():
    view = SF.reveal_view(CTX)
    assert view["outer"] == kit_path("scope__outer")
    assert view["inner"] == kit_path("scope__inner")
    assert view["ticks"]["minor"] == kit_path("scope__tick scope__tick--minor")
    assert view["ticks"]["mid"] == kit_path("scope__tick scope__tick--mid")
    assert view["ticks"]["major"] == kit_path("scope__tick scope__tick--major")
    assert 'stroke-dasharray="{{ reveal_slice_length }} 622.04"' in KIT  # the kit's circumference


def test_the_slice_runs_from_twelve_to_the_share():
    view = SF.reveal_view(CTX)  # the fixture's 96%
    assert view["shown"] and view["slice_length"] == "597.16"  # 622.04 x 0.96
    assert view["edge_tick"].startswith("M") and view["edge_tick"] != view["ticks"]["major"]


def test_a_share_that_is_not_a_percentage_draws_no_slice():
    view = SF.reveal_view(SF.record_context(trips_from([10, 20, 30, 40, 50, 60])))
    assert not view["shown"] and "slice_length" not in view


def reveal(trips=TRIPS, guessed="[guess option 3, TR-009]") -> str:
    ctx = SF.record_context(trips)
    return (
        template_env()
        .get_template("reveal.html")
        .render(
            title="Your five worst days",
            screen_class="screen--navy on-navy",
            body_class="reveal",
            guessed=guessed,
            view=SF.reveal_view(ctx),
            worst_href="/mirror/fact/worst-days?enter=lens",
            **ctx,
        )
    )


def test_the_reveal_is_the_kits_navy_page():
    page = reveal()
    assert '<div class="screen screen--navy on-navy">' in page
    assert '<main class="screen__body reveal">' in page
    assert (
        '<p class="body-small body-small--soft">You guessed: [guess option 3, TR-009].</p>' in page
    )
    assert (
        '<circle class="reveal__slice" cx="150" cy="150" r="99" stroke-dasharray="597.16 622.04"'
        in page
    )
    assert '<text class="reveal__figure" x="150" y="160" text-anchor="middle">96%</text>' in page
    assert (
        '<a class="btn btn--on-navy btn--block" href="/mirror/fact/worst-days?enter=lens">'
        "Show me those days</a>"
    ) in page
    assert '<a class="btn btn--text-on-navy" href="/budget">Continue</a>' in page
    assert '<nav class="bottom-nav"' not in page


def test_the_reveal_tells_the_mirrors_sentences():
    text = readable(reveal())
    assert "Those five days came to" in text
    assert "of your losses." in text
    assert "Your result for the whole period was" in text


def test_the_second_state_has_no_slice_and_the_mirrors_other_sentence():
    page = reveal(trips_from([10, 20, 30, 40, 50, 60]))
    assert "reveal__slice" not in page and "reveal__figure" not in page
    assert '<circle class="reveal__disc reveal__disc--empty"' in page
    text = readable(page)
    assert "Your result for the whole period was" in text and "% of your losses" not in text


def test_without_a_guess_the_reveal_says_nothing_about_one():
    assert "You guessed" not in reveal(guessed=None)


def guess_page(checkable=(12, 19)) -> str:
    from services.production.mirror import guess as GU

    return (
        template_env()
        .get_template("guess.html")
        .render(
            title="Before you look",
            question=GU.QUESTION,
            labels=GU.LABELS,
            unknown=GU.UNKNOWN,
            unknown_label=GU.UNKNOWN_LABEL,
            checkable=checkable,
            csrf_token="t",
        )
    )


def test_the_guess_offers_ten_labels_and_i_dont_know_as_buttons_in_one_form():
    page = guess_page()
    assert (
        page.count('<button class="guess__option" role="listitem" type="submit" name="answer"')
        == 10
    )
    assert '<span class="guess__index">10</span>' in page
    assert 'name="answer" value="unknown">I don&#39;t know</button>' in page
    assert '<form method="post" action="/guess">' in page and 'value="t"' in page
    assert 'href="/reveal?guess=' not in page  # a link must not be able to store a guess


def test_the_guess_says_what_the_history_lets_us_check():
    assert (
        'Your history lets us check <span class="num">12</span> of <span class="num">19'
        "</span> things."
    ) in guess_page()
    assert "lets us check" not in guess_page(checkable=None)


@pytest.mark.parametrize("name", ["guess.html", "reveal.html"])
def test_nothing_unwritten_reaches_the_page(name):
    page = guess_page() if name == "guess.html" else reveal()
    for leak in ("None", "{{", "{%", "undefined"):
        assert leak not in page, leak
