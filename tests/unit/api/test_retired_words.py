"""A word retired from a surface can't come back to it.

Reads what a trader is shown, on made-up files: rendered HTML with its tags gone, never template
source. That matters because "Import" is on the candidate list and Jinja's own `import` is in
most templates, and `trip` is mostly in code identifiers, which aren't copy. A word is matched
whole, in any case, and only on the surface that retired it, so a word can leave the dial while
it is still live copy on another page. A surface's PR adds its words to `glossary.GLOSSARY` in
the same commit that rewords its pages.

This sits beside the never-use list and test_no_claims, and changes neither.
"""

from __future__ import annotations

import re
from html import unescape

import pytest

from services.production.api import glossary as GL
from services.production.api.app import create_app
from tests.unit.api import figure_pages

STARTING_LIST = {"strike", "uncapped", "of losses", "past it"}
"""The dial's words, the first retired. The list only grows, so this stays in it."""

DIAL = re.compile(r'<div class="scope[^"]*">.*?</svg>', flags=re.DOTALL)
HOME_CARD = re.compile(r'<a class="scope-card on-navy".*?</a>', flags=re.DOTALL)
SURFACES = {GL.DIAL: DIAL, GL.HOME_CARD: HOME_CARD}
"""A surface in `where`, as the part of a page it is. An entry with no `where` is every page."""


SURFACE_PAGES = {GL.MONEY_PAGES: ("/mirror/fact/money", "/mirror/fact/worst-days",
                                  "/mirror/fact/busiest", "/mirror/fact/clock")}
"""A surface in `where` that is whole pages: a word is held to those and left alone elsewhere."""


def shown(html: str) -> str:
    """What a trader reads or hears: the text, and the labels a screen reader says."""
    labels = " ".join(re.findall(r'aria-label="([^"]*)"', html))
    text = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(unescape(f"{text} {labels}").replace("\xa0", " ").split())


def surface_of(html: str, where: str | None) -> str:
    if where is None or where in SURFACE_PAGES:
        return shown(html)
    return " ".join(shown(part) for part in SURFACES[where].findall(html))


def is_said(word: str, text: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text, flags=re.IGNORECASE) is not None


def retired_words_on(page: str, html: str, entries) -> list[str]:
    """One line per word found: which page, which word, where it is retired, what to say instead."""
    found = []
    for entry in entries:
        pages = SURFACE_PAGES.get(entry.where)
        if pages and not any(path in page for path in pages):
            continue
        if entry.status == GL.RETIRED and is_said(entry.word, surface_of(html, entry.where)):
            place = f"the {entry.where}" if entry.where else "this page"
            found.append(f'{page}: "{entry.word}" is retired from {place}. '
                         f'Say "{entry.replaced_by}".')
    return found


# ---------- Every page, in every scene ----------


def test_no_retired_word_is_on_any_page():
    app = create_app()
    scenes = figure_pages.scenes(app, app.state.engine)
    found = []
    for scene, pages in scenes.items():
        for path, (_status, html) in pages.items():
            found += retired_words_on(f"{scene} {path}", html, GL.GLOSSARY)
            assert "{%" not in html, f"{scene} {path}: Jinja's own syntax reached a page"
    assert found == []
    assert DIAL.findall(scenes["demo"]["/mirror"][1]), "no dial found, so its words prove nothing"


# ---------- What the test does ----------


DIAL_PAGE = ('<div class="scope"><svg><a class="scope__slice"><text>45.8%</text>'
             '<text>strike</text></a></svg></div>')


def test_a_failure_names_the_page_the_word_and_what_to_say():
    found = retired_words_on("demo /mirror", DIAL_PAGE, GL.retired(GL.DIAL))
    assert len(found) == 1
    assert "demo /mirror" in found[0]
    assert '"strike"' in found[0]
    assert "the dial" in found[0]
    assert "N of 100 trades made money" in found[0]


def test_a_word_retired_from_the_dial_is_still_free_elsewhere():
    """The math page's "strike rate" is live until its own surface lands."""
    page = f"<p>Your strike rate was 45%.</p>{DIAL_PAGE.replace('strike', 'made money')}"
    assert retired_words_on("a page", page, GL.retired(GL.DIAL)) == []


def test_a_word_with_no_surface_is_retired_from_every_page():
    entry = GL.Entry("qualified", GL.RETIRED, "counted")
    assert retired_words_on("a page", "<p>Trades that qualified</p>", [entry])
    assert retired_words_on("a page", "<p>Trades that counted</p>", [entry]) == []


def test_adding_a_word_is_one_line():
    """If this takes more than the one Entry, the module's shape is wrong (the ticket's gate)."""
    assert GL.Entry("fact", GL.RETIRED, "page").where is None


def test_a_word_in_use_is_no_failure():
    entry = GL.Entry("trades", GL.IN_USE)
    assert retired_words_on("a page", "<p>8 trades</p>", [entry]) == []


# ---------- It reads what is rendered, not what is written ----------


@pytest.mark.parametrize("word", ["trip", "reconstruct", "Import"])
def test_code_is_not_copy(word):
    """Identifiers and attributes hold these words all over, and no trader reads them."""
    page = ('<a href="/imports/1" class="trip trip--import" data-x="reconstruct" '
            'id="trips_reconstructed">Open</a><script>var trip = "reconstruct"; import("x");</script>'
            "<style>.import { color: red }</style>")
    assert retired_words_on("a page", page, [GL.Entry(word, GL.RETIRED, "x")]) == []


@pytest.mark.parametrize("word", ["trip", "reconstruct", "import"])
def test_part_of_a_longer_word_is_not_the_word(word):
    page = "<p>trips reconstructed, an important one</p>"
    assert retired_words_on("a page", page, [GL.Entry(word, GL.RETIRED, "x")]) == []


def test_a_word_said_to_a_trader_is_caught_in_any_case():
    entry = GL.Entry("Import", GL.RETIRED, "upload")
    assert retired_words_on("a page", "<p>Your report · import 13</p>", [entry])


def test_a_phrase_is_caught_across_the_tags_and_lines_that_split_it():
    entry = GL.Entry("of losses", GL.RETIRED, "x")
    assert retired_words_on("a page", "<svg><text>of</text>\n<text>losses</text></svg>", [entry])


def test_a_word_in_a_label_a_screen_reader_says_is_caught():
    entry = GL.Entry("strike", GL.RETIRED, "x")
    assert retired_words_on("a page", '<a aria-label="Your strike rate">45%</a>', [entry])


# ---------- The module ----------


def test_an_entry_is_a_word_its_status_and_what_replaced_it():
    entry = GL.Entry("strike", GL.RETIRED, "win rate", GL.DIAL)
    assert (entry.word, entry.status, entry.replaced_by) == ("strike", GL.RETIRED, "win rate")


def test_the_starting_list_is_the_dials_words_and_the_list_only_grows():
    assert {e.word for e in GL.retired(GL.DIAL)} >= STARTING_LIST
    assert "Net (gross)" in {e.word for e in GL.GLOSSARY if e.status == GL.RETIRED}


def test_nothing_is_retired_beyond_the_surfaces_that_have_landed():
    """Retired only as its surface lands, or the test rewords pages nobody has ruled on."""
    for entry in GL.GLOSSARY:
        if entry.status == GL.RETIRED:
            assert entry.where is None or entry.where in SURFACES or entry.where in SURFACE_PAGES, entry.word


def test_every_retired_word_says_what_replaced_it():
    for entry in GL.GLOSSARY:
        if entry.status == GL.RETIRED:
            assert entry.replaced_by, entry.word


def test_a_word_has_one_entry():
    words = [(e.word, e.where) for e in GL.GLOSSARY]
    assert len(words) == len(set(words))
