"""Chapter 3's titles name the condition; each page opens by saying what it shows [TICKET-832].

Worked by hand, in order, each trade closed before the next opens, all on one day:

    -100  no two trades before it
    -200  no two trades before it
    +300  the two before both lost: after two straight losses
    -50   two before it, but the last one won: another trade while down
    -151  two before it, but one of them won: another trade while down
    -25   the two before both lost: after two straight losses

After two straight losses: (300 - 25) / 2 = +137.5. The others: (-50 - 151) / 2 = -100.5.

No shuffle test can be called from production today (see metrics), so the directional
sentence is tested by opening the one function that decides whether it may show.
"""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from services.production.mirror import metrics as mx
from tests.unit.api.test_scope_chapters import chapter_page, readable, trips_from
from tests.unit.api.test_scope_facts import fact_page

CLOSED = "No difference we can stand behind."
OLD_TITLE = "Trading on while already down"
TITLE = "After two straight losses"
BETTER = (
    "After two straight losses, your next trades averaged +₹137.5. "
    "Your other trades while down averaged −₹100.5."
)


def one_day(nets: list[int], day: str = "2026-09-01") -> list[mx.Trip]:
    start = datetime.fromisoformat(f"{day}T09:15:00+05:30")
    out = []
    for i, (t, net) in enumerate(zip(trips_from([1] * len(nets)), nets, strict=True)):
        entry = start + timedelta(minutes=20 * i)
        out.append(replace(t, trip_id=f"{day}-{i}", trading_day=day, entry_ts=entry,
                           exit_ts=entry + timedelta(minutes=10), net=mx.Decimal(net)))
    return out


DOWN = one_day([-100, -200, 300, -50, -151, -25])
"""The history the module docstring works by hand."""


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


@pytest.fixture()
def gate_open(monkeypatch):
    """As if research had exposed a test production may call, and this file had passed it."""
    monkeypatch.setattr(mx, "post_loss_sentence_may_show", lambda trips: True)


DOWN_PAGES = [
    (lambda: fact_page("down", DOWN), head_of),
    (lambda: chapter_page(3, DOWN), lambda p: card_of(p, 1)),
]


# ---------- The gate ----------


def test_no_post_loss_sentence_may_show_today():
    assert mx.post_loss_sentence_may_show(DOWN) is False


# ---------- Titles ----------


@pytest.mark.parametrize(
    ("page", "read"),
    DOWN_PAGES,
    ids=["fact page", "card"],
)
def test_the_title_names_the_condition_and_carries_no_verdict(page, read):
    assert read(page())[0] == TITLE
    assert OLD_TITLE not in page()


# ---------- With the gate closed, as it is today ----------


@pytest.mark.parametrize(
    ("page", "read"),
    DOWN_PAGES,
    ids=["fact page", "card"],
)
def test_closed_the_page_opens_with_no_difference_we_can_stand_behind(page, read):
    assert read(page())[1] == CLOSED


@pytest.mark.parametrize("page", [lambda: fact_page("down", DOWN), lambda: chapter_page(3, DOWN)],
                         ids=["fact page", "card"])
def test_closed_the_numbers_are_still_shown_and_no_pattern_is_invented(page):
    text = readable(page())
    assert "+₹137.5" in text
    assert "−₹100.5" in text
    assert "your next trades averaged" not in text
    assert "while down averaged" not in text


# ---------- With the gate open, ready for when research exposes a callable test ----------


@pytest.mark.usefixtures("gate_open")
@pytest.mark.parametrize(
    ("page", "read"),
    DOWN_PAGES,
    ids=["fact page", "card"],
)
def test_open_the_page_opens_with_the_means_from_the_shared_definition(page, read):
    title, sentence = read(page())
    assert title == TITLE
    assert sentence == BETTER
    assert CLOSED not in readable(page())


@pytest.mark.usefixtures("gate_open")
def test_open_a_minus_sign_stays_with_its_figure():
    """Found at 390 px on the card: the minus ended one line and the rupees began the next."""
    page = fact_page("down", DOWN)
    assert page.count('<span class="opening-figure">') == 2
    css = Path("services/production/api/static/css/app.css").read_text()
    assert ".opening-figure { white-space: nowrap; }" in css


@pytest.mark.usefixtures("gate_open")
def test_open_the_sentence_says_it_whichever_way_the_table_points():
    """Here the trades after two straight losses did worse than the others.

    In order: -100, -200, -300, +50, +150, -100, -80. After two straight losses: -300 and
    +50, so -250 / 2 = -125. The others: +150, -100, -80, so -30 / 3 = -10.
    """
    trips = one_day([-100, -200, -300, 50, 150, -100, -80])
    _, sentence = head_of(fact_page("down", trips))
    assert sentence == (
        "After two straight losses, your next trades averaged −₹125. "
        "Your other trades while down averaged −₹10."
    )


@pytest.mark.usefixtures("gate_open")
@pytest.mark.parametrize(
    "nets",
    [[-100, 50, 60, 70], [-100, -200, -300, -400]],
    ids=["nothing after two straight losses", "nothing to set it against"],
)
def test_open_a_side_with_no_trades_has_no_average_so_the_closed_sentence_stands(nets):
    _, sentence = head_of(fact_page("down", one_day(nets)))
    assert sentence == CLOSED


# ---------- The busiest day: not a post-loss sentence, so not gated ----------


BUSY = (one_day([10, 10, 10, 10], "2026-09-01") + one_day([10], "2026-09-02")
        + one_day([10, 10], "2026-09-03"))
"""Days of 4, 1 and 2 trades: the normal (median) day is 2, the busiest 4."""


@pytest.mark.parametrize("opened", [False, True], ids=["gate closed", "gate open"])
def test_the_busiest_card_opens_with_what_its_chart_shows(opened, monkeypatch):
    """The card has the chart. The fact page opens with the day's story (test_busiest_day_story)."""
    if opened:
        monkeypatch.setattr(mx, "post_loss_sentence_may_show", lambda trips: True)
    title, sentence = card_of(chapter_page(3, BUSY), 2)
    assert title == "Your busiest day"
    assert sentence == "Your busiest day had 4 trades, against 2 on your normal day."


def test_a_busiest_day_of_one_trade_is_one_trade():
    days = one_day([10], "2026-09-01") + one_day([10], "2026-09-02")
    _, sentence = card_of(chapter_page(3, days), 2)
    assert sentence == "Your busiest day had 1 trade, against 1 on your normal day."


@pytest.mark.parametrize(
    ("key", "line"),
    [
        ("down", "occasions you opened a trade after two earlier trades"),
        ("busiest", "Your busiest was"),
    ],
)
def test_the_mirrors_own_sentence_still_follows_on_the_card(key, line):
    """On the card. The fact page no longer repeats it (test_busiest_day_story)."""
    trips = DOWN if key == "down" else BUSY
    assert line in readable(chapter_page(3, trips))


# ---------- A fact in a state says none of this ----------


@pytest.mark.parametrize("key", ["down", "busiest"])
def test_a_fact_in_a_state_has_no_opening_sentence(key):
    text = readable(fact_page(key, []))
    assert CLOSED not in text
    assert "Your busiest day had" not in text
