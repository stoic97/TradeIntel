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
PERCENT = re.compile(r"\d[\d.]*\s?%")


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


_RENDERED: dict[str, str] = {}


@pytest.fixture()
def pages() -> dict[str, str]:
    """Every page in every scene ``figure_pages`` renders, rendered once for this module (the
    environment the suite's autouse fixture sets up is in place by then)."""
    if not _RENDERED:
        app = create_app()
        for scene, rendered in figure_pages.scenes(app, app.state.engine).items():
            for path, (_status, html) in rendered.items():
                _RENDERED[f"{scene} {path}"] = html
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


# ---------- shares stay shares ----------

def test_shares_of_a_total_are_still_written_as_percents(pages):
    text = " ".join(_text(h) for h in pages.values())
    for share in ("of your losses", "of premium"):
        assert re.search(r"\d[\d.]*\s?% " + re.escape(share), text), share


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
