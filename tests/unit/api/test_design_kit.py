"""The design kit's stylesheets and icons, as the app serves them.

docs/design/scope-kit is the code form of the design system (handoff section 7). The
app serves copies from services/production/api/static, and these tests keep the two
from drifting: components.css, motion.css and the icons are the kit's byte for byte,
and tokens.css is the kit's below its font block, which is replaced on purpose
(fonts.css says why). When the kit changes, these fail until the copies are
refreshed, which is the point.

The colour roles are checked against handoff section 7 directly, not against the kit,
because where the two disagree the handoff wins.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

KIT = Path("docs/design/scope-kit/static")
APP = Path("services/production/api/static")

# Handoff section 7, "Colour roles".
COLOUR_ROLES = {
    "--color-page": "#FFFFFF",
    "--color-surface": "#F5F8FD",
    "--color-hairline": "#DDE4F1",
    "--color-ink": "#0B1733",
    "--color-muted": "#3F4F82",
    "--color-faint": "#5D6B96",
    "--color-action-blue": "#04408D",
    "--color-gain": "#0D7A3F",
    "--color-loss": "#B42318",
    "--color-building": "#8A5A00",
}


def tokens_from(css: str) -> dict[str, str]:
    """Every custom property a stylesheet sets, as name -> value."""
    return {name: value.strip() for name, value in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", css)}


def test_custom_properties_are_read_with_their_values():
    css = ":root { --color-page: #FFFFFF;   /* the record */ --space-1: 4px;  --space-2: 8px; }"
    assert tokens_from(css) == {"--color-page": "#FFFFFF", "--space-1": "4px", "--space-2": "8px"}


@pytest.mark.parametrize("name", ["components.css", "motion.css"])
def test_the_kit_stylesheets_are_served_unchanged(name):
    assert (APP / "css" / name).read_bytes() == (KIT / "css" / name).read_bytes()


def test_the_kit_icons_are_served_unchanged():
    kit = sorted(p.name for p in (KIT / "icons").iterdir())
    assert kit, "the kit has no icons to compare against"
    assert sorted(p.name for p in (APP / "icons").iterdir()) == kit
    for name in kit:
        assert (APP / "icons" / name).read_bytes() == (KIT / "icons" / name).read_bytes(), name


def test_the_tokens_are_the_kits_below_its_font_block():
    app = (APP / "css" / "tokens.css").read_text()
    kit = (KIT / "css" / "tokens.css").read_text()
    assert app[app.index(":root {"):] == kit[kit.index(":root {"):]


def test_fonts_are_declared_in_one_place():
    """fonts.css, whose ranges were measured (TR-013), and nowhere else."""
    assert "@font-face" in (APP / "css" / "fonts.css").read_text()
    for css in sorted(APP.rglob("*.css")):
        if css.name != "fonts.css":
            assert "@font-face" not in css.read_text(), css


@pytest.mark.parametrize("role,colour", COLOUR_ROLES.items())
def test_every_colour_role_is_the_handoffs(role, colour):
    tokens = tokens_from((APP / "css" / "tokens.css").read_text())
    assert tokens[role].upper() == colour


def test_no_stylesheet_reaches_outside_the_app():
    for css in sorted(APP.rglob("*.css")):
        assert "://" not in css.read_text(), css
