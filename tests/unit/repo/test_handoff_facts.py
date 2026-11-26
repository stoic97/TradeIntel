"""TICKET-1064: the handoff's chapters-and-facts table is the app's own list of facts.

The handoff is the build spec and says it wins where others disagree, so a fact it still lists
after the app dropped it would be built again. Its table under "Chapters and facts" is read here
and held to scope_map.CHAPTERS: the chapters, the fact titles and the fact keys, in order. A fact
added to the app turns this red until its row says so.
"""

from __future__ import annotations

import re
from pathlib import Path

from services.production.api import scope_map

HANDOFF = Path(__file__).resolve().parents[3] / "docs" / "product" / "scope_engineering_handoff_v1.md"
HEADING = "### Chapters and facts"
SEPARATOR = " · "


def handoff() -> str:
    return HANDOFF.read_text(encoding="utf-8").replace("\r\n", "\n")


def table_rows(text: str) -> list[list[str]]:
    """The cells of each body row of the first table under the heading."""
    lines = text.split("\n")
    starts = [i for i, line in enumerate(lines) if line.startswith(HEADING)]
    assert len(starts) == 1, f"{len(starts)} headings start with {HEADING!r}"
    rows: list[list[str]] = []
    for line in lines[starts[0] + 1:]:
        if line.startswith("|"):
            rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
        elif rows or line.startswith("#"):
            break
    assert len(rows) > 2, "no table under the heading"
    return rows[2:]  # past the column heads and the rule under them


def listed() -> list[tuple[int, str, list[str], list[str]]]:
    out = []
    for cells in table_rows(handoff()):
        assert len(cells) == 4, cells
        number, chapter, titles, keys = cells
        out.append((int(number), chapter, titles.split(SEPARATOR), re.findall(r"`([^`]+)`", keys)))
    return out


def in_the_app() -> list[tuple[int, str, list[str], list[str]]]:
    return [(c.number, c.name, [f.title for f in c.facts], [f.key for f in c.facts])
            for c in scope_map.CHAPTERS]


def test_the_table_lists_the_apps_chapters_and_facts_in_order():
    assert listed() == in_the_app()


def test_the_tables_fact_keys_are_the_apps():
    assert [k for row in listed() for k in row[3]] == [f.key for c in scope_map.CHAPTERS for f in c.facts]


def test_the_routes_row_counts_the_facts():
    counts = re.findall(r"^\| 16 \| Fact \((\d+)\) \|", handoff(), flags=re.MULTILINE)
    assert counts == [str(sum(len(c.facts) for c in scope_map.CHAPTERS))]
