"""TICKET-953: one home for each kind of record, as docs/where_things_live.md sets out.

Gate:
1. No file in docs/ calls itself a register or tracker, or the place where items go.
2. Every TD and TR id mentioned anywhere in the repo (code comments included) maps to a
   Jira key, or to a closed note.
3. The deferrals index has no id above the highest one on 17 Nov 2026, and no column beyond
   id, title, area and Jira key.
4. docs/where_things_live.md exists and docs/README.md links to it.

TD ids are looked up in the index (docs/deferrals.md); TR ids in the Jira key column of the
archived testing register. Whether a key opens in Jira is checked by hand in the PR, because
tests have no network.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
INDEX = "docs/deferrals.md"
ARCHIVE = "docs/archive/scope_testing_register_v1.md"
RULE = ROOT / "docs" / "where_things_live.md"
README = ROOT / "docs" / "README.md"

# The highest ids on 17 Nov 2026, as numbers, so that this file names no id itself.
HIGHEST = {"TD": 34, "TR": 14}
INDEX_HEADER = ["id", "title", "area", "jira key"]

ID = re.compile(r"\bT[DR]-(?:\d{3}|D\d+)\b")
KEY_CELL = re.compile(
    r"TICKET-\d+(?:\s*,\s*TICKET-\d+)*"
    r"|Closed \d{1,2} [A-Z][a-z]{2}(?: \d{4})?: \S.*"
)
SEPARATOR = re.compile(r"\|?(?:\s*:?-+:?\s*\|)*\s*:?-+:?\s*\|?")
SELF_TITLE = re.compile(r"^#\s.*\b(?:register|tracker)\s*$", re.IGNORECASE)

# What the old lists said about themselves (audit of 13 Nov, finding H3), and the ways a
# new one would say it. Matched in lower case with whitespace collapsed.
SELF_CLAIMS = (
    "this file is the register",
    "this file is the tracker",
    "is the register",
    "is the tracker",
    "ticket register",
    "has no tracker",
    "not listed here does not exist",
    "every bug, feature and change goes here",
    "new items go here",
    "new rows go here",
    "leaves this register",
)


def _tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True)
    return [f for f in out.stdout.decode("utf-8").split("\0") if f]


def _text(rel: str) -> str | None:
    path = ROOT / rel
    if not path.is_file():
        return None
    data = path.read_bytes()
    if b"\0" in data[:8192]:
        return None
    return data.decode("utf-8", errors="replace")


def _cells(line: str) -> list[str]:
    return [c.strip() for c in re.split(r"(?<!\\)\|", line.strip().strip("|"))]


def _tables(text: str) -> tuple[list[dict], list[int]]:
    """Tables as GitHub reads them: a header row, a separator row, then rows up to the first
    line that is not a row. Also returns the line numbers of rows outside any table."""
    lines = text.splitlines()
    tables: list[dict] = []
    orphans: list[int] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
        if line.lstrip().startswith("|") and SEPARATOR.fullmatch(nxt):
            table = {"header": [h.lower() for h in _cells(line)], "rows": []}
            i += 2
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                table["rows"].append((i + 1, _cells(lines[i])))
                i += 1
            tables.append(table)
            continue
        if line.lstrip().startswith("|"):
            orphans.append(i + 1)
        i += 1
    return tables, orphans


def _keyed_rows(rel: str) -> dict[str, tuple[int, str]]:
    """id -> (line, key cell) for every row of every table in `rel` that has a Jira key
    column."""
    text = _text(rel) or ""
    found: dict[str, tuple[int, str]] = {}
    for table in _tables(text)[0]:
        if "jira key" not in table["header"]:
            continue
        col = table["header"].index("jira key")
        for line_no, cells in table["rows"]:
            if cells and ID.fullmatch(cells[0]):
                found[cells[0]] = (line_no, cells[col] if col < len(cells) else "")
    return found


def _over_the_top(ident: str) -> bool:
    kind, _, number = ident.partition("-")
    return number.isdigit() and int(number) > HIGHEST[kind]


# ---------- Gate 1: no file in docs/ calls itself the list ----------


def test_no_doc_calls_itself_a_register_or_tracker():
    hits = []
    for rel in _tracked():
        if not rel.startswith("docs/"):
            continue
        text = _text(rel)
        if text is None:
            continue
        title = next((line for line in text.splitlines() if line.startswith("# ")), "")
        if SELF_TITLE.match(title):
            hits.append(f"{rel}: title '{title.strip()}'")
        flat = " ".join(text.lower().split())
        hits += [f"{rel}: '{claim}'" for claim in SELF_CLAIMS if claim in flat]
    assert not hits, "docs that say they are where items go:\n" + "\n".join(hits)


def test_the_archived_register_says_jira_replaced_it():
    text = _text(ARCHIVE)
    assert text is not None, f"{ARCHIVE} does not exist"
    assert not (ROOT / "docs/product/scope_testing_register_v1.md").exists(), (
        "the testing register is still in docs/product/"
    )
    assert "Superseded by Jira" in "\n".join(text.splitlines()[:8]), (
        f"{ARCHIVE} has no 'Superseded by Jira' banner at the top"
    )


# ---------- Gate 2: every id maps to a key or a closed note ----------


def test_every_td_and_tr_id_in_the_repo_maps_to_a_key_or_a_closed_note():
    mapped = {**_keyed_rows(ARCHIVE), **_keyed_rows(INDEX)}
    bad_cells = [
        f"{ident} ({where}:L{line_no}): '{cell}'"
        for where in (INDEX, ARCHIVE)
        for ident, (line_no, cell) in _keyed_rows(where).items()
        if not KEY_CELL.fullmatch(cell)
    ]
    assert not bad_cells, "rows whose key cell is neither a Jira key nor a closed note:\n" + (
        "\n".join(bad_cells)
    )
    seen: dict[str, list[str]] = {}
    for rel in _tracked():
        text = _text(rel)
        if text is None:
            continue
        for ident in set(ID.findall(text)):
            seen.setdefault(ident, []).append(rel)
    assert seen, "the scan found no TD or TR id at all"
    unmapped = sorted(f"{i}: {', '.join(sorted(fs)[:3])}" for i, fs in seen.items()
                      if i not in mapped)
    assert not unmapped, "ids with no Jira key or closed note:\n" + "\n".join(unmapped)


def test_no_new_td_or_tr_ids_anywhere():
    over = sorted({i for rel in _tracked() if (t := _text(rel)) for i in ID.findall(t)
                   if _over_the_top(i)})
    assert not over, f"ids above the highest of 17 Nov 2026 (a new deferral is a Jira ticket): {over}"


# ---------- Gate 3: the index is an index ----------


def test_the_index_is_one_table_of_id_title_area_and_key():
    tables, orphans = _tables(_text(INDEX) or "")
    assert len(tables) == 1, f"{INDEX} has {len(tables)} tables; the index is one"
    assert not orphans, f"{INDEX} rows outside the table (GitHub shows them as text): {orphans}"
    table = tables[0]
    assert table["header"] == INDEX_HEADER, f"index columns are {table['header']}"
    for line_no, cells in table["rows"]:
        assert len(cells) == len(INDEX_HEADER), f"{INDEX}:L{line_no} has {len(cells)} cells"
        assert re.fullmatch(r"TD-\d{3}", cells[0]), f"{INDEX}:L{line_no} id '{cells[0]}'"
        assert not _over_the_top(cells[0]), f"{INDEX}:L{line_no} {cells[0]} is a new id"


# ---------- Gate 4: the rule is written down and linked ----------


def test_the_rule_is_written_down():
    assert RULE.exists(), "docs/where_things_live.md does not exist"
    text = RULE.read_text(encoding="utf-8")
    assert "| What | Its one home | Allowed anywhere else |" in text, "the rule table is missing"


def test_docs_readme_links_the_rule():
    if not README.exists():
        pytest.xfail("docs/README.md is not written yet (TICKET-933)")
    assert "where_things_live.md" in README.read_text(encoding="utf-8"), (
        "docs/README.md does not link docs/where_things_live.md"
    )
