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
        title="Scope", view=SF.home_view(SF.facts(ctx, imp), ctx), imp=imp,
        trade_count=len(trips), trading_day_count=len(ctx["days"].counts))


def test_home_has_the_four_chapters_in_order_each_scoping_in():
    view = SF.home_view(FIGS, CTX)
    assert [i["name"] for i in view["items"]] == [c.name for c in S.CHAPTERS]
    assert [i["href"] for i in view["items"]] == [
        S.chapter_href(c.number, from_home=True) for c in S.CHAPTERS]


def test_each_chapter_leads_with_its_lead_facts_figure():
    view = SF.home_view(FIGS, CTX)
    assert [i["figure"] for i in view["items"]] == [
        FIGS["share"]["figure"], FIGS["hold"]["figure"], FIGS["down"]["figure"],
        FIGS["unread"]["figure"]]


def test_the_centre_is_the_five_days_share():
    view = SF.home_view(FIGS, CTX)
    assert view["centre"] == {"figure": f"{CTX['share'].share_percent}%"}
    svg = str(dial.scope_dial(view))
    assert f">{CTX['share'].share_percent}%</tspan>" in svg
    assert ">of your result</tspan>" in svg and ">in five days</tspan>" in svg


def test_when_the_share_is_not_a_percentage_the_centre_says_the_whole_result():
    """Handoff 7's second state: no percentage, and no 'in five days' beside it."""
    ctx = SF.record_context(trips_from([-100, -50, -20, -10, -5, 900]))
    view = SF.home_view(SF.facts(ctx, IMP), ctx)
    assert view["centre"]["figure"] == formatting.rupees(ctx["share"].total)
    svg = str(dial.scope_dial(view))
    assert "in five days" not in svg and "%" not in re.sub(r"<[^>]+>", "", svg)
    assert ">your result for</tspan>" in svg and ">the whole period</tspan>" in svg


def test_without_caption_lines_the_dial_is_the_kits_byte_for_byte():
    """The one Python-only addition to the port changes nothing unless it is used."""
    view = {"kind": "home", "centre": {"figure": "96%"},
            "items": [{"name": c.name, "figure": "1", "href": "/x"} for c in S.CHAPTERS]}
    built = G.build_dial(view, "phone", dial.OPTS)
    with_default = G.build_dial({**view, "centre": {"figure": "96%", "captionLines": None}},
                                "phone", dial.OPTS)
    assert G.render_dial_svg(built) == G.render_dial_svg(with_default)


def test_a_caption_line_cannot_break_out_of_the_dial():
    view = SF.home_view(FIGS, CTX)
    view["centre"]["captionLines"] = ['a "quoted" line']
    with pytest.raises(ValueError, match="double quote"):
        dial.scope_dial(view)


def test_a_chapter_whose_lead_fact_is_in_a_state_shows_the_state_on_home():
    ctx = SF.record_context(trips_from([100, 200, 300, 50]))  # no losers: hold not enough
    svg = str(dial.scope_dial(SF.home_view(SF.facts(ctx, IMP), ctx)))
    assert svg.count("scope__slice--not-enough") == 1


def test_home_is_the_kits_page():
    page = home_page()
    assert '<header class="stage stage--home on-navy">' in page
    assert '<span class="lockup__name">PlusEV</span>' in page
    assert '<span class="chip chip--on-navy">In development.</span>' in page
    assert '<p class="label">Counted from your file</p>' in page
    assert '<h1 class="title fact__title">What your trades actually did.</h1>' in page
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
