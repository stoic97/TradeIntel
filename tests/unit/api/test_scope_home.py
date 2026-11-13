"""Scope home (handoff 4, level 1): four chapters on the dial, the share in its centre.

Rendered through the app's templates with the Mirror's 40-trade fixture.
"""

from __future__ import annotations

import pytest

from services.production.api import dial
from services.production.api import scope_facts as SF
from services.production.api import scope_geometry as G
from services.production.api import scope_map as S
from tests.unit.api.templating import template_env
from tests.unit.api.test_scope_chapters import IMP, TRIPS

CTX = SF.record_context(TRIPS)
FIGS = SF.facts(CTX, IMP)


def home_page(trips=TRIPS, imp=IMP) -> str:
    ctx = SF.record_context(trips)
    return template_env().get_template("scope/home.html").render(
        title="Scope", imp=imp, trade_count=len(trips),
        trading_day_count=len(ctx["days"].counts), **SF.home_context(ctx, imp))


def test_home_has_the_four_chapters_in_order_each_scoping_in():
    view = SF.home_view(CTX, IMP)
    assert [i["name"] for i in view["items"]] == [c.name for c in S.CHAPTERS]
    # Each wedge opens the trades behind its figure (TICKET-905), from its chapter's fact; the
    # chapters themselves are reached from the list below the dial.
    figs = SF.facts(CTX, IMP)
    for c, item in zip(S.CHAPTERS, view["items"], strict=True):
        assert item["href"] in (figs[SF.HUB_FACT[c.number]]["opens"], None)
    assert view["items"][0]["href"] == figs["worst-days"]["opens"]


def test_without_caption_lines_the_dial_is_the_kits_byte_for_byte():
    """The one Python-only addition to the port changes nothing unless it is used."""
    view = {"kind": "home", "centre": {"figure": "96%"},
            "items": [{"name": c.name, "figure": "1", "href": "/x"} for c in S.CHAPTERS]}
    built = G.build_dial(view, "phone", dial.OPTS)
    with_default = G.build_dial({**view, "centre": {"figure": "96%", "captionLines": None}},
                                "phone", dial.OPTS)
    assert G.render_dial_svg(built) == G.render_dial_svg(with_default)


def test_a_caption_line_cannot_break_out_of_the_dial():
    view = SF.home_view(CTX, IMP)
    view["centre"]["captionLines"] = ['a "quoted" line']
    with pytest.raises(ValueError, match="double quote"):
        dial.scope_dial(view)


def test_home_is_the_kits_page():
    page = home_page()
    assert '<header class="stage stage--home on-navy">' in page
    assert '<span class="lockup__name">PlusEV</span>' in page
    assert '<p class="label">Counted from your file</p>' in page
    assert '<h1 class="title fact__title">Your option trades' in page
    assert "40 trades · 8 trading days · before charges</span><span>No buy or sell calls, ever.</span>" in page
    assert "every rupee figure below is gross" in page
    assert "Computed from import 7 by Scope version fixturesha" in page
    assert 'aria-current="page">Scope</a>' in page


def test_nothing_unwritten_reaches_home():
    page = home_page()
    for leak in ("None", "{{", "{%", "[N]", "[X]", "five_day_share_percent"):
        assert leak not in page, leak
