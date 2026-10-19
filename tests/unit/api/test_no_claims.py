"""No screen makes a claim the product has not earned.

Success criterion 7: zero sentences attributing cause, predicting or recommending,
and no unqualified R, audited on every screen. The Mirror has its own version of
this; this is the audit across everything, because a claim is most likely to arrive
through a screen nobody thought of as a place for claims -- an error message, a
confirmation, an empty state.

The check runs on template SOURCE rather than rendered pages, so a screen nobody has
written a test for is still covered. The cost is that it cannot see words arriving
through variables; the Mirror's rendered-HTML test covers that for the page where
figures actually live.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

TEMPLATES = sorted(Path("services/production/api/templates").glob("*.html"))

# Section 6.7 exists to say the product names no cause and recommends nothing, which
# it cannot say without those words. It is the only exemption, and it is by name.
DISCLAIMER_TEMPLATES = {"mirror.html"}
DISCLAIMER_MARKER = "What we have not told you"

NEVER_USED = [
    "tilt", "revenge", "emotional", "psychology", "disease", "cure",
    "edge", "alpha", "expectancy", "discipline", "mistake", "should have",
    "signal", "tip",
]

# The rule is that the product never explains the TRADER's behaviour. Explaining its
# own is not only permitted but required -- "shown because this is a development
# account" is the kind of sentence that makes a product legible. So the patterns
# below are anchored to the trader: "you ... because", not "because" alone. The
# first version banned the bare word and fired on the draft-text warning, which
# would have meant writing worse English everywhere to satisfy a test.
CLAIM_PATTERNS = [
    (r"\byou\b[^.]{0,80}\bbecause\b", "asserts a cause for the trader's behaviour"),
    (r"\byour\b[^.]{0,80}\bbecause\b", "asserts a cause for the trader's behaviour"),
    (r"\bcaused by\b", "asserts a cause"),
    (r"\bthe cause of\b", "asserts a cause"),
    (r"\bdue to\b", "asserts a cause"),
    (r"\bled to\b", "asserts a cause"),
    (r"\byou should\b", "recommends"),
    (r"\bwe recommend\b", "recommends"),
    (r"\btry to\b", "recommends"),
    (r"\byour score\b", "grades"),
    (r"\bwe estimate\b", "estimates what is not in the file"),
    (r"\bcost you\b", "estimates what a habit cost"),
    (r"\byou tend to\b", "generalises beyond the count"),
    (r"\bthis means\b", "interprets rather than counts"),
]

UNQUALIFIED_R = re.compile(r"\b\d+(\.\d+)?\s*R\b")


def body_of(path: Path) -> str:
    """Template text above section 6.7, lowercased."""
    text = path.read_text()
    if path.name in DISCLAIMER_TEMPLATES and DISCLAIMER_MARKER in text:
        text = text.split(DISCLAIMER_MARKER)[0]
    return text.lower()


def test_there_are_templates_to_audit():
    """A glob that matches nothing would make every test below vacuous."""
    assert len(TEMPLATES) >= 10, [p.name for p in TEMPLATES]


@pytest.mark.parametrize("path", TEMPLATES, ids=lambda p: p.name)
def test_no_template_uses_a_never_use_word(path):
    """Whole words only: 'ledger' contains 'edge' and 'multipart' contains 'tip'.

    Both fired on the first run. A guard that reports a word the template does not
    contain gets switched off by the third person who hits it, and then it guards
    nothing.
    """
    body = body_of(path)
    for word in NEVER_USED:
        found = re.search(rf"\b{re.escape(word)}\b", body)
        assert found is None, f"{path.name} says {word!r}"


@pytest.mark.parametrize("path", TEMPLATES, ids=lambda p: p.name)
def test_no_template_asserts_a_cause_a_grade_or_a_recommendation(path):
    body = body_of(path)
    for pattern, why in CLAIM_PATTERNS:
        found = re.search(pattern, body)
        assert found is None, f"{path.name} {why}: {found.group(0)!r}"


@pytest.mark.parametrize("path", TEMPLATES, ids=lambda p: p.name)
def test_no_template_prints_an_unqualified_r(path):
    """Decision 15: a figure divided by a budget is labelled in words."""
    found = UNQUALIFIED_R.search(path.read_text())
    assert found is None, f"{path.name} prints {found.group(0)!r}"


def test_the_disclaimer_is_exempt_by_name_not_by_luck():
    """If 6.7 is renamed, this fails rather than silently exempting nothing."""
    mirror = (Path("services/production/api/templates/mirror.html")).read_text()
    assert DISCLAIMER_MARKER in mirror
    assert mirror.count(DISCLAIMER_MARKER) == 1
