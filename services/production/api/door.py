"""The door's words (TICKET-914): the question, the answers to a trader's first questions.

One place, so the door, /signup and their tests read the same lines. New copy waits for
D9. The question is round 1's one-tap question, asked before anything else; the answer is
said back to him and not stored, because there is no account yet to keep it with.
"""

from __future__ import annotations

QUESTION = "When your first trade of the day loses, what usually happens next?"

ANSWERS: dict[str, str] = {
    "make-back": "I make it back",
    "break-even": "I break even",
    "lose-more": "I lose more",
    "unknown": "I don't know",
}
"""Each answer's address (?said=) and its words. Any other value is no answer."""

LINE = "You know what your account did last year. You do not know which of your habits produced it."

ROWS: tuple[tuple[str, str], ...] = (
    ("You give us", "The trade file your broker lets you download. Never your broker login."),
    ("You get", "Your own trades, counted: where your results came from, with the trades behind every figure."),
    ("You won't get", "Tips or courses. No buy or sell calls, ever."),
    ("Brokers", "Dhan today. Others are coming."),
    ("Cost", "Free today."),
    ("Your file", "No third party receives it. Delete everything whenever you want."),
)

CONTACT = "team@plusev.in"
"""Where a trader who forgot his password reaches us: a reset is an admin's step."""


def register(env) -> None:
    """The door's words, to every template that draws the door or sign-in."""
    import sys

    env.globals["door"] = sys.modules[__name__]


def said(value: str | None) -> str | None:
    """The answer's key, if it is one of the door's; anything else is no answer."""
    return value if value in ANSWERS else None
