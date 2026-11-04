"""Scope home (handoff 4, level 1): four chapters on the dial, the share in its centre.

Rendered through the app's templates with the Mirror's 40-trade fixture.
"""

from __future__ import annotations

import re

import pytest

from services.production.api import dial, formatting
from services.production.api import scope_facts as SF
from services.production.api import scope_geometry as G
from services.production.api import scope_map as S
from tests.unit.api.templating import template_env
from tests.unit.api.test_scope_chapters import IMP, TRIPS, trips_from

CTX = SF.record_context(TRIPS)
FIGS = SF.facts(CTX, IMP)


def home_page(trips=TRIPS, imp=IMP) -> str:
    ctx = SF.record_context(trips)
    return template_env().get_template("scope/home.html").render(
        title="Scope", imp=imp, trade_count=len(trips),
        trading_day_count=len(ctx["days"].counts), **SF.home_context(ctx, imp))


def test_home_has_the_four_chapters_in_order_each_scoping_in():
    view = SF.home_view(CTX)
    assert [i["name"] for i in view["items"]] == [c.name for c in S.CHAPTERS]
    assert [i["href"] for i in view["items"]] == [
        S.chapter_href(c.number, from_home=True) for c in S.CHAPTERS]


def test_without_caption_lines_the_dial_is_the_kits_byte_for_byte():
    """The one Python-only addition to the port changes nothing unless it is used."""
    view = {"kind": "home", "centre": {"figure": "96%"},
            "items": [{"name": c.name, "figure": "1", "href": "/x"} for c in S.CHAPTERS]}
    built = G.build_dial(view, "phone", dial.OPTS)
    with_default = G.build_dial({**view, "centre": {"figure": "96%", "captionLines": None}},
                                "phone", dial.OPTS)
    assert G.render_dial_svg(built) == G.render_dial_svg(with_default)


def test_a_caption_line_cannot_break_out_of_the_dial():
    view = SF.home_view(CTX)
    view["centre"]["captionLines"] = ['a "quoted" line']
    with pytest.raises(ValueError, match="double quote"):
        dial.scope_dial(view)


def test_home_is_the_kits_page():
    page = home_page()
    assert '<header class="stage stage--home on-navy">' in page
    assert '<span class="lockup__name">PlusEV</span>' in page
    assert '<span class="chip chip--on-navy">In development.</span>' in page
    assert '<p class="label">Counted from your file</p>' in page
    assert '<h1 class="title fact__title">Your option trades' in page
    assert ('<span class="num">40</span> trades, <span class="num">8</span> trading days. '
            "Every figure here is counted from your file. Open any line to see the trades "
            "behind it.") in page
    assert "<span>No buy or sell calls, ever.</span><span>4 chapters</span>" in page
    assert "every rupee figure below is gross" in page
    assert "Computed from import 7 by Scope version fixturesha" in page
    assert 'aria-current="page">Scope</a>' in page


def test_nothing_unwritten_reaches_home():
    page = home_page()
    for leak in ("None", "{{", "{%", "[N]", "[X]", "five_day_share_percent"):
        assert leak not in page, leak
