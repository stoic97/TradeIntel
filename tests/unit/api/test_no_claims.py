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

TEMPLATE_ROOT = Path("services/production/api/templates")


def templates_under(root: Path) -> list[Path]:
    """Every template under root, subfolders included, in a stable order.

    The Scope keeps one template per fact in facts/. A top-level glob would let a
    banned word through in exactly the files where the Mirror's sentences live.
    """
    return sorted(root.rglob("*.html"))


def template_id(path: Path) -> str:
    """The path inside the templates folder: facts/money.html, not money.html."""
    return path.relative_to(TEMPLATE_ROOT).as_posix()


TEMPLATES = templates_under(TEMPLATE_ROOT)

# Section 6.7 exists to say the product names no cause and recommends nothing, which
# it cannot say without those words. It is the only exemption, and it is by name: the
# Mirror's section, and the Scope's card and fact page that tell it word for word.
DISCLAIMER_TEMPLATES = {"mirror.html", "scope/cards/not-told.html", "scope/facts/not-told.html"}
DISCLAIMER_MARKER = "What we have not told you"

NEVER_USED = [
    "tilt", "revenge", "emotional", "psychology", "disease", "cure",
    "edge", "alpha", "expectancy", "discipline", "mistake", "should have",
    "signal", "tip",
    # Added from the Scope engineering handoff, section 6 (27 Oct). "your plan / your
    # system / your rule" are TR-006: the engine never attributes a behaviour to his
    # intention.
    "guaranteed", "profitable", "winning", "guru", "mentor", "fund", "platform",
    "dna", "ai-powered", "no issues detected", "your plan", "your system", "your rule",
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

# ADR-007: v1 has no email service, so no screen may promise one. These match a
# promise ("we'll email you", "check your inbox"), not a statement that there is no
# email: delete_done.html says "we have no way to email you", and it should.
EMAIL_PROMISES = [
    r"\bwe(?:'ll|’ll| will| shall) (?:also )?e-?mail\b",
    r"\bwe(?:'ll|’ll| will) send (?:you )?(?:an )?e-?mail\b",
    r"\bcheck your (?:e-?mail|inbox)\b",
    r"\b(?:sent|emailed) to your (?:e-?mail|inbox|address)\b",
    r"\bby e-?mail\b",
]

UNQUALIFIED_R = re.compile(r"\b\d+(\.\d+)?\s*R\b")


def body_of(path: Path) -> str:
    """Template text above section 6.7, lowercased."""
    text = path.read_text()
    if template_id(path) in DISCLAIMER_TEMPLATES and DISCLAIMER_MARKER in text:
        text = text.split(DISCLAIMER_MARKER)[0]
    return text.lower()


def test_there_are_templates_to_audit():
    """A glob that matches nothing would make every test below vacuous."""
    assert len(TEMPLATES) >= 10, [p.name for p in TEMPLATES]


@pytest.mark.parametrize("path", TEMPLATES, ids=template_id)
def test_no_template_uses_a_never_use_word(path):
    """Whole words only: 'ledger' contains 'edge' and 'multipart' contains 'tip'.

    Both fired on the first run. A guard that reports a word the template does not
    contain gets switched off by the third person who hits it, and then it guards
    nothing.
    """
    body = body_of(path)
    for word in NEVER_USED:
        found = re.search(rf"\b{re.escape(word)}\b", body)
        assert found is None, f"{template_id(path)} says {word!r}"


@pytest.mark.parametrize("path", TEMPLATES, ids=template_id)
def test_no_template_asserts_a_cause_a_grade_or_a_recommendation(path):
    body = body_of(path)
    for pattern, why in CLAIM_PATTERNS:
        found = re.search(pattern, body)
        assert found is None, f"{template_id(path)} {why}: {found.group(0)!r}"


@pytest.mark.parametrize("path", TEMPLATES, ids=template_id)
def test_no_template_prints_an_unqualified_r(path):
    """Decision 15: a figure divided by a budget is labelled in words."""
    found = UNQUALIFIED_R.search(path.read_text())
    assert found is None, f"{template_id(path)} prints {found.group(0)!r}"


def test_the_disclaimer_is_exempt_by_name_not_by_luck():
    """If 6.7 is renamed, this fails rather than silently exempting nothing."""
    for name in DISCLAIMER_TEMPLATES:
        text = (Path("services/production/api/templates") / name).read_text()
        assert text.count(DISCLAIMER_MARKER) == 1, name


# The never-say list in the Scope engineering handoff, section 6 (27 Oct). Every new
# Scope template is audited against it, so the list above must hold all of it.
HANDOFF_NEVER_SAY = {
    "guaranteed", "profitable", "winning", "signal", "tip", "guru", "mentor", "fund",
    "platform", "tilt", "emotional", "psychology", "disease", "cure", "dna", "revenge",
    "ai-powered", "no issues detected", "your plan", "your system", "your rule",
}


def test_the_never_used_list_holds_every_word_the_handoff_bans():
    missing = HANDOFF_NEVER_SAY - set(NEVER_USED)
    assert not missing, sorted(missing)


def test_templates_in_subfolders_are_audited_too(tmp_path):
    """The Scope adds templates in folders (facts/<key>.html); a top-level glob misses them."""
    (tmp_path / "top.html").write_text("x")
    (tmp_path / "facts").mkdir()
    (tmp_path / "facts" / "money.html").write_text("x")
    found = [p.relative_to(tmp_path).as_posix() for p in templates_under(tmp_path)]
    assert found == ["facts/money.html", "top.html"]


@pytest.mark.parametrize("sentence", [
    "We'll email you when it is ready.",
    "We will email a copy of your deletion.",
    "We will send you an email to confirm.",
    "Check your inbox for the link.",
    "A receipt was sent to your email.",
    "You will hear from us by email.",
])
def test_an_email_promise_is_caught(sentence):
    assert any(re.search(p, sentence.lower()) for p in EMAIL_PROMISES), sentence


@pytest.mark.parametrize("sentence", [
    ("This page is the confirmation — we have no way to email you, and we did not "
     "keep an address to email."),
    "At least 12 characters. There is no email on your account, so",
])
def test_saying_there_is_no_email_is_not_a_promise(sentence):
    """Both are on main today, and both are the honest sentence ADR-007 asks for."""
    assert not any(re.search(p, sentence.lower()) for p in EMAIL_PROMISES), sentence


@pytest.mark.parametrize("path", TEMPLATES, ids=template_id)
def test_no_template_promises_an_email(path):
    """ADR-007: there is no email service, so no screen may promise one."""
    body = path.read_text().lower()
    for pattern in EMAIL_PROMISES:
        found = re.search(pattern, body)
        assert found is None, f"{template_id(path)} promises an email: {found.group(0)!r}"
