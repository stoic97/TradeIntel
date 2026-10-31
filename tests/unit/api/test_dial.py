"""The dial on a page (api/dial.py and the dial macro in _components.html).

The geometry is held to the kit by test_scope_geometry.py; this holds the door a page
draws it through: hrefs escaped once, text that would break an attribute refused, the
SVG not escaped a second time, and a chapter's mini charts drawn in their slices.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from services.production.api import dial
from services.production.api import scope_geometry as G
from tests.unit.api.templating import template_env

CASES = json.loads(Path("tests/fixtures/scope_geometry/cases.json").read_text())["dials"]


def raw(view: dict) -> dict:
    """A recorded view with its hrefs as a page gives them: unescaped."""
    view = copy.deepcopy(view)
    for item in view["items"]:
        item["href"] = item["href"].replace("&amp;", "&")
    if "scopeHref" in view["centre"]:
        view["centre"]["scopeHref"] = view["centre"]["scopeHref"].replace("&amp;", "&")
    return view


def page(view: dict, size: str = "phone") -> str:
    env = template_env({"probe.html": '{% from "_components.html" import dial %}{{ dial(v, s) }}'})
    return env.get_template("probe.html").render(v=view, s=size)


def with_minis(view: dict) -> dict:
    """Give each charted slice a mini chart, as a chapter page will."""
    view = copy.deepcopy(view)
    for item in view["items"]:
        if item["chart"] == "worst":
            item["mini"] = G.chart_worst([-300, -8000, -200], dial.MINI_W, dial.MINI_H)
        elif item["chart"] == "share":
            item["mini"] = G.chart_share(0.96, dial.MINI_W, dial.MINI_H, True)
        elif item["chart"] == "money":
            item["mini"] = G.chart_money([1500], [-2000], dial.MINI_W, dial.MINI_H)
    return view


@pytest.mark.parametrize("key", ["home_phone_figures", "home_phone_states", "chapter_4_phone"])
def test_a_page_draws_the_dial_the_kit_draws(key):
    case = CASES[key]
    view = raw(case["view"])
    if key == "chapter_4_phone":
        view["items"][0]["mini"] = G.chart_read(40, 40, dial.MINI_W, dial.MINI_H, True)
        view["items"][2]["mini"] = G.chart_notold(dial.MINI_W, dial.MINI_H, True)
        want = G.render_dial_svg(
            G.build_dial(case["view"], "phone", dial.OPTS),
            {
                "read": G.render_chart(view["items"][0]["mini"]),
                "notold": G.render_chart(view["items"][2]["mini"]),
            },
        )
    else:
        want = case["svg"]
    assert page(view) == f'<div class="scope">{want}</div>'


def test_the_desktop_dial_is_marked_for_the_desktop_stage():
    case = CASES["home_desktop"]
    assert page(raw(case["view"]), "desktop") == (
        f'<div class="scope scope--desktop">{case["svg"]}</div>'
    )


def test_each_slice_draws_its_own_mini_chart():
    view = with_minis(raw(CASES["chapter_1_phone"]["view"]))
    html = page(view)
    assert html.count('<g class="scope__mini chart chart--on-navy" transform="translate(') == 3
    for item in view["items"]:
        assert G.render_chart(item["mini"]) in html, item["chart"]


def test_a_slice_that_names_a_chart_must_give_it():
    view = raw(CASES["chapter_1_phone"]["view"])
    with pytest.raises(ValueError, match="names a worst chart"):
        dial.scope_dial(view)


def test_an_href_is_escaped_once():
    view = raw(CASES["home_phone_figures"]["view"])
    view["items"][0]["href"] = '/mirror/chapter/1?enter=in&tap=1"><script>'
    html = page(view)
    assert 'href="/mirror/chapter/1?enter=in&amp;tap=1&#34;&gt;&lt;script&gt;"' in html
    assert "<script>" not in html
    assert "&amp;amp;" not in html


def test_the_chapter_centre_link_is_escaped_too():
    view = raw(CASES["chapter_2_phone"]["view"])
    view = with_minis(view)
    for item in view["items"]:
        item["chart"] = ""
    view["centre"]["scopeHref"] = "/mirror?enter=out&tap=2"
    assert 'href="/mirror?enter=out&amp;tap=2"' in page(view)


@pytest.mark.parametrize("where", ["name", "figure"])
def test_text_that_would_break_out_of_an_attribute_is_refused(where):
    view = raw(CASES["home_phone_figures"]["view"])
    view["items"][1][where] = 'Your "patterns"'
    with pytest.raises(ValueError, match="double quote"):
        dial.scope_dial(view)


def test_names_and_figures_are_escaped_as_text():
    view = raw(CASES["home_phone_figures"]["view"])
    view["items"][2]["figure"] = "3<4&5"  # no space, so it is not stacked over two lines
    assert ">3&lt;4&amp;5</tspan>" in page(view)


def test_a_home_dial_without_its_centre_figure_is_refused():
    # scope_geometry falls back to the kit's placeholder; a page must never show it.
    view = raw(CASES["home_phone_figures"]["view"])
    view["centre"]["figure"] = ""
    with pytest.raises(ValueError, match="centre figure"):
        dial.scope_dial(view)
