"""TICKET-1028: a rate reads "N of 100" on every page; a share of a total may stay a percent.

A **rate** is a count out of a count of the same thing: trades that made money out of trades
(the win rate, "you win", "made money"), the win rate break-even needs ("break even at"), and
green days out of days traded. The product's rule is that a rate is written "N of 100"
(``formatting.out_of_a_hundred``), and the report's prose already does; its tables wrote "45%".

A **share** is a part of a whole that is not a count of the same kind, and it may stay a
percent: days as a share of the record ("about 8%"), money as a share of money ("40% of your
losses", "34% of what your winners made"), a trade's result against its premium ("% of
premium"), a loss against capital, and a part of a group of trades described by how it closed
("16% of losers closed within 5 minutes"). Both kinds are listed by name below.

Tables also say what they are in words: no "Table 1", no "Figure 1 ·", no "Or per winner".
"""
from __future__ import annotations

import re
from html import unescape

import pytest
from fastapi.testclient import TestClient

from services.production.api.app import create_app
from tests.unit.api import figure_pages

RATE_HEADERS = ("You win", "Break even at", "Win rate", "Made money")
"""Table columns whose cells are rates."""
RATE_ROWS = ("You win", "Break even at", "Green days")
"""Table rows (first cell) whose cells are rates: the hidden page's halves."""
RATE_PROSE = re.compile(r"(?:win rate of|break even at|made money)\s*\d[\d.]*\s?%", re.IGNORECASE)
"""A rate in a sentence, written as a percent."""
SHARES = ("of your losses", "of premium", "of losers closed within 5 minutes", "of what your winners made",
          "of it")
"""Shares a page may still write as a percent: each ends a "N% <share>" phrase."""
ALLOWED: dict[str, str] = {}
"""Percents a page may write that no share follows, each by name: what it is, and the words
around it as a pattern ("N%" stands for the percent)."""
PERCENT = re.compile(r"\d[\d.]*\s?%")
INLINE = re.compile(r"</?(?:span|tspan|a|b|i|em|strong|small|abbr)\b[^>]*>")
SAID_ALOUD = re.compile(r'\b(?:aria-label|alt|title)="([^"]*)"')


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def _tables(html: str):
    for table in re.findall(r"<table\b.*?</table>", html, re.DOTALL):
        rows = [[_text(c) for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", tr, re.DOTALL)]
                for tr in re.findall(r"<tr\b.*?</tr>", table, re.DOTALL)]
        if rows:
            yield rows


def rate_cells_as_percent(html: str) -> list[str]:
    """Every rate cell in a table, and every rate in a sentence, written as a percent."""
    found = []
    for rows in _tables(html):
        header = rows[0]
        columns = [i for i, h in enumerate(header) if h in RATE_HEADERS]
        for row in rows[1:]:
            cells = [row[i] for i in columns if i < len(row)]
            if row and row[0] in RATE_ROWS:
                cells = row[1:]
            found += [f"{row[0]}: {c}" for c in cells if PERCENT.search(c)]
    main = re.search(r"<main.*?</main>", html, re.DOTALL)
    found += RATE_PROSE.findall(_text(main.group(0) if main else html))
    return found


def _said(html: str) -> str:
    """What the whole page says, its labels included. Every block ends in " | ", so a percent is
    never read together with the words of the next block."""
    html = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.DOTALL)
    labels = " | ".join(SAID_ALOUD.findall(html))
    words = re.sub(r"<[^>]+>", " | ", INLINE.sub(" ", html))
    return re.sub(r"\s+", " ", unescape(f"{words} | {labels}"))


def unnamed_percents(html: str) -> list[str]:
    """Every percent on the page that is neither beside a share in ``SHARES`` nor in ``ALLOWED``."""
    said = _said(html)
    spans = [m.span() for words in ALLOWED.values()
             for m in re.finditer(words.replace("N%", PERCENT.pattern), said)]
    beside = re.compile(r"\s*(?:" + "|".join(map(re.escape, SHARES)) + r")\b")
    return [said[max(0, p.start() - 30):p.end() + 30] for p in PERCENT.finditer(said)
            if not beside.match(said, p.end()) and not any(a <= p.start() and p.end() <= b for a, b in spans)]


_RENDERED: dict[str, str] = {}


def _budget_in_per_cent(app) -> str:
    """The number page with capital and a number in per cent, which no scene sets: it prints
    percents of its own. The demo's trader, as every scene is made up."""
    client = TestClient(app)
    figure_pages._sign_up(client, app.state.engine, "percenter")
    figure_pages._consent(client)
    client.post("/upload/demo", data={"csrf_token": figure_pages._token(client, "/upload")})
    client.post("/budget", data={"csrf_token": figure_pages._token(client, "/budget"), "value": "2", "unit": "PCT",
                                 "capital_amount": "100000", "effective_from": "2024-01-01"})
    return client.get("/budget").text


@pytest.fixture()
def pages() -> dict[str, str]:
    """Every page in every scene ``figure_pages`` renders, rendered once for this module (the
    environment the suite's autouse fixture sets up is in place by then)."""
    if not _RENDERED:
        app = create_app()
        for scene, rendered in figure_pages.scenes(app, app.state.engine).items():
            for path, (_status, html) in rendered.items():
                _RENDERED[f"{scene} {path}"] = html
        _RENDERED["a number in per cent /budget"] = _budget_in_per_cent(app)
    return _RENDERED


# ---------- the guard ----------

def test_no_page_writes_a_rate_as_a_percent(pages):
    offenders = {where: found for where, html in pages.items() if (found := rate_cells_as_percent(html))}
    assert offenders == {}, list(offenders.items())[:5]


def test_the_guard_catches_a_rate_and_leaves_a_share():
    table = ("<table><tr><th>Book</th><th>You win</th></tr><tr><td>Crude</td><td>45%</td></tr></table>"
             "<table><tr><th></th><th>First half</th></tr><tr><td>Green days</td><td>15 (58 %)</td></tr></table>")
    assert len(rate_cells_as_percent(table)) == 2
    assert rate_cells_as_percent("<main><p>Break even at a win rate of 53.4%, about 13 more.</p></main>")
    shares = ("<main><p>5 of your days (about 8%) carried about 40% of your losses. Paid ₹900 · +23.3% of "
              "premium. 16% of losers closed within 5 minutes.</p></main>")
    assert rate_cells_as_percent(shares) == []


def test_every_percent_is_a_named_share_or_allowed_by_name(pages):
    offenders = {where: found for where, html in pages.items() if (found := unnamed_percents(html))}
    assert offenders == {}, (len(offenders), list(offenders.items())[:5])


def test_a_percent_nobody_named_is_found_on_a_page_of_every_scene(pages):
    for where, html in _a_page_of_every_kind(pages):
        assert any("61% of something new" in found
                   for found in unnamed_percents(_with(html, "61% of something new"))), where


SCENES = {"signed out", "signed up", "consented", "demo", "demo with a number", "small file"}


def _a_page_of_every_kind(pages):
    """Each page in every scene that says anything; every scene has one."""
    spoken = [(where, html) for where, html in pages.items() if "</main>" in html]
    assert {where.split(" /")[0] for where, _ in spoken} >= SCENES
    return spoken


def _with(html: str, sentence: str) -> str:
    """The page with one more sentence at the end of what it says."""
    return html.replace("</main>", f"<p>{sentence}</p></main>", 1)


def _not_caught(pages, *sentences: str) -> list[str]:
    """Pages the guard passes although a sentence that writes a rate as a percent is on them."""
    return [where for where, html in _a_page_of_every_kind(pages) for sentence in sentences
            if not rate_cells_as_percent(_with(html, sentence))]


def test_the_guard_catches_won_n_percent(pages):
    assert _not_caught(pages, "You won 45% in this book.", 'You won <span class="num">45</span>%.') == []


def test_the_guard_catches_n_percent_of_trades_made_money(pages):
    assert _not_caught(pages, "45% of trades made money.", '<span class="num">45</span>% of trades made money.') == []


def test_the_guard_catches_a_win_rate_outside_a_table(pages):
    assert _not_caught(pages, "Win rate 45%", 'Win rate <span class="num">45</span>%') == []


def test_the_guard_catches_green_days_outside_a_table_row(pages):
    assert _not_caught(pages, "Green days 15 (58%)",
                       'Green days <span class="num">15</span> (<span class="num">58</span>%)') == []


# ---------- the math page's two lines ----------

def _math_pages(pages):
    found = {where: _text(html) for where, html in pages.items()
             if where.endswith("/fact/math") and "closed within 5 minutes" in html and "lost more than" in html}
    assert found
    return found.items()


def test_quick_closes_read_n_of_100(pages):
    for where, text in _math_pages(pages):
        assert re.search(r"\d+ of 100 losers closed within 5 minutes, against \d+ of 100 winners\b", text), where
        assert not re.search(r"%\s*of (?:losers|winners)\b", text), where


def test_the_biggest_losers_out_of_the_trades_read_n_of_100_and_their_losses_stay_a_share(pages):
    for where, text in _math_pages(pages):
        assert re.search(r"\btrades? \(\s?\d+ of 100\s?\) lost more than", text), where
        assert not re.search(r"\btrades? \(\s?\d+\s?%", text), where
        assert re.search(r"\d+\s?% of this book's losses", text), where


# ---------- shares stay shares ----------

def test_every_share_and_every_allowed_percent_is_still_on_a_page(pages):
    said = [_said(h) for h in pages.values()]
    for words in [rf"N%\s*{re.escape(share)}\b" for share in SHARES] + list(ALLOWED.values()):
        shape = re.compile(words.replace("N%", PERCENT.pattern))
        assert any(shape.search(text) for text in said), words


# ---------- tables say what they are ----------

def test_no_table_or_figure_is_named_by_its_number(pages):
    for where, html in pages.items():
        main = re.search(r"<main.*?</main>", html, re.DOTALL)
        text = _text(main.group(0) if main else html)
        assert not re.search(r"\b(?:Table|Figure) \d+\b", text), where
        assert "Or per winner" not in text, where


def test_the_book_table_reads_n_of_100_and_names_its_last_column(pages):
    math = next(h for where, h in pages.items() if where.endswith("/mirror/fact/math"))
    rows = next(rows for rows in _tables(math) if rows[0][:3] == ["Book", "Trades", "You win"])
    assert rows[0][-1] == "Or a bigger winner by"
    assert all(re.fullmatch(r"\d+ of 100", r[2]) for r in rows[1:] if len(r) > 3), rows
    assert "Break even at 51 of 100" in _text(math) or "Break even at 53 of 100" in _text(math)
