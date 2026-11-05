"""TICKET-850: home says nothing about being in development, its result fits its centre, and a
minus stays with its figure.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from services.production.api import dial
from tests.unit.api.test_scope_home import home_page

CSS = Path("services/production/api/static/css/app.css").read_text()


def centre_class(figure: str, size: str = "phone") -> str:
    view = {
        "kind": "home",
        "items": [{"name": n, "figure": "Open", "href": f"/{i}"}
                  for i, n in enumerate(("One", "Two", "Three", "Four"))],
        "centre": {"figure": figure, "captionLines": ["your result"]},
    }
    found = re.search(r'class="(scope__centre-figure[^"]*)"', str(dial.scope_dial(view, size)))
    assert found, "the dial has no centre figure"
    return found.group(1)


def test_home_does_not_say_it_is_in_development():
    assert "In development" not in home_page()


@pytest.mark.parametrize(("figure", "expected"), [
    ("₹0", "scope__centre-figure"),
    ("−₹1,420", "scope__centre-figure"),
    ("−₹58,522", "scope__centre-figure scope__centre-figure--long"),
    ("+₹9,99,999", "scope__centre-figure scope__centre-figure--longer"),
    ("−₹1,27,263", "scope__centre-figure scope__centre-figure--longer"),
    ("−₹12,34,567", "scope__centre-figure scope__centre-figure--longer"),
])
def test_a_longer_result_is_drawn_smaller_so_it_stays_in_the_centre(figure, expected):
    assert centre_class(figure) == expected


def test_each_size_has_its_rule_on_both_dials():
    for rule in (".scope__centre-figure--long", ".scope__centre-figure--longer",
                 ".scope--desktop .scope__centre-figure--long",
                 ".scope--desktop .scope__centre-figure--longer"):
        assert rule + " {" in CSS


def test_a_number_never_wraps_inside_itself():
    assert re.search(r"(?m)^\.num \{ white-space: nowrap; \}", CSS)
