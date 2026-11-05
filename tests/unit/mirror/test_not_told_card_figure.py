"""TICKET-854 - the not-told story card shows no figure.

NOT_TOLD = 4 is a constant (scope_facts.py), a count of the statements on the not-told page, not
something counted from the trader's file, and the page says every figure is counted from it. The
chapter 4 dial already shows this slice's name only (Rikk, 5 Nov 2026, Q2 b); this does the same
for the card under the dial. The card keeps its number, title and foot; the other cards keep theirs.
"""

import re

CARD = re.compile(
    r'<span class="story-card__num">(\d+)</span><span class="story-card__title">([^<]*)</span>'
    r'<span class="story-card__figure[^"]*">(.*?)</span>',
    re.DOTALL,
)


def _cards(client):
    html = client.get("/mirror/chapter/4").text
    return {t: (n, re.sub(r"<[^>]+>|\s+", "", f)) for n, t, f in CARD.findall(html)}


def test_the_not_told_card_shows_no_figure(client):
    num, fig = _cards(client)["What we have not told you"]
    assert num == "3"
    assert not re.search(r"\d", fig), f"not-told card figure: {fig!r}"


def test_the_other_chapter_four_cards_keep_their_figures(client):
    cards = _cards(client)
    for title in ("What we read", "Trades with a risk figure"):
        assert re.search(r"\d", cards[title][1]), f"{title}: {cards[title][1]!r}"


def test_the_not_told_card_keeps_its_foot(client):
    assert "Read in full" in client.get("/mirror/chapter/4").text