"""Moved out of tests/unit/api/test_no_claims.py by TICKET-945, so that no test file imports another."""

from __future__ import annotations

NEVER_USED = [
    "tilt",
    "revenge",
    "emotional",
    "psychology",
    "disease",
    "cure",
    "edge",
    "alpha",
    "expectancy",
    "discipline",
    "mistake",
    "should have",
    "signal",
    "tip",
    # Added from the Scope engineering handoff, section 6 (27 Oct). "your plan / your
    # system / your rule" are TR-006: the engine never attributes a behaviour to his
    # intention.
    "guaranteed",
    "profitable",
    "winning",
    "guru",
    "mentor",
    "fund",
    "platform",
    "dna",
    "ai-powered",
    "no issues detected",
    "your plan",
    "your system",
    "your rule",
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
