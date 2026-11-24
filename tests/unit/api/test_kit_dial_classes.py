"""TICKET-1055: the kit update for the dial, made once and on purpose.

The founder ruled (24 Nov 2026) that the kit stylesheet may change for the four dial tickets
only through one PR whose whole purpose is the kit. These tests pin that every rule those
tickets need is in components.css, that the kit's copy and the app's copy stay byte for byte
the same, and that the pinned fingerprint is the one this change gives.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tests.helpers.figures import KIT_SHA

KIT = Path("docs/design/scope-kit/static/css/components.css")
APP = Path("services/production/api/static/css/components.css")

# Each rule the dial tickets need, as one line of the stylesheet, with the ticket that needs it.
NEEDED = [
    # TICKET-1035, the reference line: the first worse wedge gets one quiet fill.
    ".scope__marked { fill: var(--dial-line); fill-opacity: .08; }",
    # TICKET-1036, readable minis: a count under its bar, and its colour on navy.
    ".chart__label { fill: var(--color-faint); font-family: var(--font-mono); font-size: 8px; }",
    ".chart--on-navy .chart__label { fill: var(--color-on-navy-soft); }",
    # TICKET-1037, the reading ring: one segment a wedge, read by weight, and the centre's count.
    ".scope__progress-seg { fill: none; stroke: var(--dial-line); stroke-linecap: round; }",
    ".scope__progress-seg--unread { stroke-opacity: var(--dial-minor-opacity); stroke-width: 1.5; }",
    ".scope__progress-seg--opened { stroke-opacity: var(--dial-mid-opacity); stroke-width: 3; }",
    ".scope__progress-seg--current { stroke-opacity: 1; stroke-width: 5; }",
    ".scope__centre-read { fill: var(--color-faint); font-size: 10px; }",
    ".scope--desktop .scope__centre-read { font-size: 12px; }",
    ".scope__bezel, .scope__progress, .scope__dividers { transform-origin: center; }",
    # TICKET-1039, phone dial room: two smaller figure sizes.
    ".scope__figure--s12 { font-size: 12px; } .scope__figure--s13 { font-size: 13px; }",
]


def rules(path: Path) -> list[str]:
    """The stylesheet's lines with their trailing comments and spacing taken off."""
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("/*")[0].strip() if not line.lstrip().startswith("/*") else ""
        if line:
            out.append(" ".join(line.split()))
    return out


@pytest.mark.parametrize("rule", NEEDED)
def test_every_rule_the_dial_tickets_need_is_in_the_kit(rule):
    assert any(rule in line for line in rules(KIT)), rule


@pytest.mark.parametrize("rule", NEEDED)
def test_the_app_serves_the_same_rule(rule):
    assert any(rule in line for line in rules(APP)), rule


def test_the_two_copies_stay_byte_for_byte_the_same():
    assert KIT.read_bytes() == APP.read_bytes()


def test_the_pinned_fingerprint_is_this_change():
    css = APP.read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(css).hexdigest() == KIT_SHA


def test_the_transform_hook_names_the_ring_once():
    text = APP.read_text(encoding="utf-8")
    assert text.count(".scope__progress,") == 1
    assert ".scope__bezel, .scope__dividers {" not in text
