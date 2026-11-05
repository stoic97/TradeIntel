"""Scope uses the screen on desktop [TICKET-845].

A unit test can't see layout, so the real check is in a browser and is in the PR. These hold what a
browser check can't hold on to: that the desktop layout stays a media query in app.css, on the same
templates, so the phone and the desktop can't drift apart and no page's wording is involved.
"""

from __future__ import annotations

import re
from pathlib import Path

CSS = Path("services/production/api/static/css")
TEMPLATES = Path("services/production/api/templates")
QUERY = "@media (min-width: 1024px)"


def desktop_rules() -> str:
    text = (CSS / "app.css").read_text(encoding="utf-8")
    assert QUERY in text, "the desktop layout is one media query in app.css"
    start = text.index("{", text.index(QUERY)) + 1
    depth, i = 1, start
    while depth:
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        i += 1
    return text[start:i - 1]


def rule(selector: str) -> str:
    found = re.search(rf"(?:^|\n)\s*{re.escape(selector)}\s*\{{([^}}]*)\}}", desktop_rules())
    assert found, f"no desktop rule for {selector}"
    return found.group(1)


def test_no_page_stays_a_phone_column():
    assert "max-width: none" in rule(".screen")


def test_the_bottom_nav_becomes_a_header_at_the_top():
    nav = rule(".bottom-nav")
    assert "order: -1" in nav
    assert "position: sticky" in nav and "top: 0" in nav
    assert "max-width: none" in nav


def test_the_body_stops_leaving_room_for_a_bottom_nav():
    assert "padding-bottom" in rule(".screen__body--with-nav")


def test_the_dial_sits_beside_the_story():
    grid = rule(".screen:has(> .stage)")
    assert "display: grid" in grid
    assert "grid-template-columns" in grid


def test_a_facts_trades_sit_beside_its_story():
    assert "display: grid" in rule(".screen__body--fact")
    assert "grid-column: 2" in rule(".screen__body--fact > .evidence")


def test_the_phone_rules_are_left_alone():
    """The kit's stylesheet stays the kit's. Its 430 px column is what a phone still gets."""
    assert "max-width: 430px" in (CSS / "components.css").read_text(encoding="utf-8")


def test_the_layout_adds_no_second_set_of_templates():
    assert not list(TEMPLATES.rglob("desktop*"))
    assert "desk__" not in (TEMPLATES / "layout.html").read_text(encoding="utf-8")


def test_the_next_button_is_not_shown_twice_in_a_row():
    """On a phone the evidence sits between the two. Beside the story, nothing does."""
    assert "display: none" in rule(".screen__body--fact > .day-blocks__next")
