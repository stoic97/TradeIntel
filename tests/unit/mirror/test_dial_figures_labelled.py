"""TICKET-843 - the dial's slice serials read as part of the figures.

Gate, as narrowed by Rikk's rulings of 5 Nov 2026:
1-3. No serial on any dial (the hub and the four chapters); handoff s.164 records the change (Q1 a).
4.   Every chapter-dial figure carries its unit or label in its own block. A %, x, rupee sign or
     hh:mm counts as the unit (Q3 a). down reads "N trades" (TICKET-827's), unread "N of M rows read",
     risk "N of M trades", not-told shows its name only, no figure (Q2).
5.   Story-card numbers stay.
6.   No dial slice holds a lone one-character number.
The hub's figures are TICKET-823's (Read/Open); here the hub is held to gates 1 and 6 only.
"""

import re
from pathlib import Path

import pytest

HUB = "/mirror"
CHAPTERS = [f"/mirror/chapter/{n}" for n in (1, 2, 3, 4)]
TEXT = re.compile(r'<text class="([^"]*)"[^>]*>(.*?)</text>', re.DOTALL)
SLICE = re.compile(r'<a class="scope__slice[^"]*"[^>]*>(.*?)</a>', re.DOTALL)
HANDOFF = Path(__file__).resolve().parents[3] / "docs/product/scope_engineering_handoff_v1.md"


def _dial(html: str) -> str:
    start = html.index('class="scope')
    return re.search(r"<svg.*?</svg>", html[start:], re.DOTALL).group(0)


def _words(body: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)).strip()


def _slices(svg: str) -> list[dict]:
    """Each slice: its name (drawn after the link) and the text inside its link."""
    names = [_words(b) for c, b in TEXT.findall(svg) if c.split()[0] == "scope__name"]
    blocks = [[(c.split()[0], _words(b)) for c, b in TEXT.findall(inner)] for inner in SLICE.findall(svg)]
    assert names and len(names) == len(blocks), "one name per slice"
    out = []
    for name, texts in zip(names, blocks):
        fig = " ".join(w for c, w in texts if c in ("scope__figure", "scope__figure-tail") and w)
        out.append({"name": name, "texts": texts, "figure": fig})
    return out


def _has_unit(fig: str) -> bool:
    return bool(re.search("[A-Za-z%\u00d7\u20b9]", fig) or re.search(r"\d:\d\d", fig))


@pytest.mark.parametrize("url", [HUB, *CHAPTERS])
def test_no_dial_draws_a_slice_serial(client, url):
    svg = _dial(client.get(url).text)
    assert "scope__number" not in svg
    assert not re.search(r'<a class="scope__slice[^"]*"[^>]*aria-label="\d', svg)


@pytest.mark.parametrize("url", [HUB, *CHAPTERS])
def test_no_dial_slice_holds_a_lone_one_character_number(client, url):
    for s in _slices(_dial(client.get(url).text)):
        lone = [w for _, w in s["texts"] if re.fullmatch(r"\d", w)]
        assert not lone, f"{url} / {s['name']}: {lone}"


@pytest.mark.parametrize("url", CHAPTERS)
def test_every_chapter_dial_figure_carries_its_unit(client, url):
    for s in _slices(_dial(client.get(url).text)):
        if re.search(r"\d", s["figure"]):
            assert _has_unit(s["figure"]), f"{url} / {s['name']}: {s['figure']!r}"


RULED = {
    3: {"After two straight losses": r"\d[\d,]* trades? right after two losses"},
    4: {
        "What we read": r"\d[\d,]* of \d[\d,]* rows read",
        "Trades with a risk figure": r"\d[\d,]* of \d[\d,]* trades",
        "What we have not told you": r"\d+ items not told",
    },
}


@pytest.mark.parametrize("n", sorted(RULED))
def test_the_ruled_dial_words(client, n):
    got = {s["name"]: s["figure"] for s in _slices(_dial(client.get(f"/mirror/chapter/{n}").text))}
    for name, pattern in RULED[n].items():
        assert re.fullmatch(pattern, got[name]), f"chapter {n} / {name}: {got[name]!r}"


def test_story_cards_keep_their_numbers(client):
    html = client.get("/mirror/chapter/4").text
    assert re.findall(r'<span class="story-card__num">(\d+)</span>', html) == ["1", "2", "3"]


def test_the_handoff_records_that_the_serial_came_off():
    text = HANDOFF.read_text(encoding="utf-8")
    assert "slice number on its own line" not in text
    assert "TICKET-843" in text