"""Moved out of tests/unit/api/test_chapter_three_describes.py by TICKET-945, so that no test file imports another.
"""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import datetime, timedelta

from services.production.mirror import metrics as mx
from tests.helpers.scope_chapters import readable, trips_from

CLOSED = "No difference we can stand behind."


TITLE = "After two straight losses"


def one_day(nets: list[int], day: str = "2026-09-01") -> list[mx.Trip]:
    start = datetime.fromisoformat(f"{day}T09:15:00+05:30")
    out = []
    for i, (t, net) in enumerate(zip(trips_from([1] * len(nets)), nets, strict=True)):
        entry = start + timedelta(minutes=20 * i)
        out.append(replace(t, trip_id=f"{day}-{i}", trading_day=day, entry_ts=entry,
                           exit_ts=entry + timedelta(minutes=10), net=mx.Decimal(net)))
    return out


DOWN = one_day([-100, -200, 300, -50, -151, -25])


def head_of(page: str) -> tuple[str, str]:
    """A fact page's title, and the sentence straight under it."""
    found = re.search(
        r'<h1 class="title fact__title">(.*?)</h1>\s*<p class="mirror">(.*?)</p>', page, re.DOTALL
    )
    assert found, "the title is not followed straight away by a sentence"
    return readable(found[1]), readable(found[2])


def card_of(page: str, number: int) -> tuple[str, str]:
    """A chapter card's title, and the first sentence in the card."""
    card = page.split(f'<span class="story-card__num">{number}</span>')[1]
    title = re.search(r'class="story-card__title">(.*?)</span>', card)
    sentence = re.search(r'<span class="mirror mirror--card">(.*?)</span>\s*\n', card, re.DOTALL)
    return readable(title[1]), readable(sentence[1])
