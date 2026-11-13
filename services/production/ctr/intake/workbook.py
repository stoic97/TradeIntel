"""An uploaded file, as the text the pipeline reads (TICKET-895).

Dhan exports CSV. Groww exports an Excel workbook with a preamble above its header: the
account holder's name, his client code, and a line naming the date range. The pipeline
reads text that starts at a header, so this turns either kind of file into that:

* a workbook's first sheet becomes CSV lines, each cell's stored text kept as written,
  so a value is never round-tripped through a float;
* anything above a known adapter's header is dropped, so the name and client code are
  never read into a row, kept in a row's raw text, or shown back.

The raw file itself is stored as uploaded, encrypted (ADR-007), like every upload. A
file with no known header comes back whole, and the format check rejects it as before.
Standard library only: a workbook is a zip of XML, and that is all this needs to read.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree as ET

_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_ZIP_MAGIC = b"PK\x03\x04"
PREAMBLE_LIMIT = 20
"""How far down a header may sit. Groww's is on row 6; a header further than this is
not a preamble, it is a different file."""


class UnreadableWorkbook(ValueError):
    """A file that says it is a workbook and cannot be read as one."""


def is_workbook(content: bytes) -> bool:
    return content[:4] == _ZIP_MAGIC


def _column(ref: str) -> int:
    letters = re.match(r"[A-Z]+", ref)
    n = 0
    for ch in letters[0] if letters else "A":
        n = n * 26 + ord(ch) - 64
    return n - 1


def _number(text: str) -> str:
    """A numeric cell's text, with a float's last-place noise taken off.

    Excel stores 1234.5 as "1234.5", but a writer that went through a float can store
    1234.4999999999998. Six places is finer than any price or value a broker reports.
    """
    try:
        value = Decimal(text)
    except InvalidOperation:
        return text
    exponent = value.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -6:
        value = value.quantize(Decimal("0.000001")).normalize()
        return format(value, "f")
    return text


def workbook_rows(content: bytes) -> list[list[str]]:
    """The first sheet's rows, each cell as text, empty cells as ''."""
    try:
        book = zipfile.ZipFile(io.BytesIO(content))
        names = set(book.namelist())
        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            for item in ET.fromstring(book.read("xl/sharedStrings.xml")).findall(f"{_MAIN}si"):
                shared.append("".join(t.text or "" for t in item.iter(f"{_MAIN}t")))
        workbook = ET.fromstring(book.read("xl/workbook.xml"))
        first = workbook.find(f"{_MAIN}sheets/{_MAIN}sheet")
        rels = ET.fromstring(book.read("xl/_rels/workbook.xml.rels"))
        target = next(r.get("Target") for r in rels if r.get("Id") == first.get(f"{_REL}id"))
        sheet = ET.fromstring(book.read("xl/" + target.lstrip("/").removeprefix("xl/")))
    except (zipfile.BadZipFile, KeyError, StopIteration, AttributeError, ET.ParseError) as exc:
        raise UnreadableWorkbook(f"not a readable workbook: {exc}") from exc

    rows: list[list[str]] = []
    for row in sheet.iter(f"{_MAIN}row"):
        cells: dict[int, str] = {}
        for cell in row.findall(f"{_MAIN}c"):
            kind = cell.get("t")
            value = cell.find(f"{_MAIN}v")
            if kind == "inlineStr":
                text = "".join(t.text or "" for t in cell.iter(f"{_MAIN}t"))
            elif value is None or value.text is None:
                continue
            elif kind == "s":
                text = shared[int(value.text)]
            elif kind in ("str", "b", "e"):
                text = value.text
            else:
                text = _number(value.text)
            cells[_column(cell.get("r", "A"))] = text
        width = max(cells, default=-1) + 1
        rows.append([cells.get(i, "") for i in range(width)])
    return rows


def _from_header(rows: list[list[str]], headers: Iterable[tuple[str, ...]]) -> list[list[str]]:
    """The rows from the first known header down, or all of them if there is none."""
    known = set(headers)
    for at, row in enumerate(rows[:PREAMBLE_LIMIT]):
        cells = [c.strip().lstrip("﻿") for c in row]
        while cells and not cells[-1]:
            cells.pop()
        if tuple(cells) in known:
            return [cells, *rows[at + 1:]]
    return rows


def text_of(content: bytes, headers: Iterable[tuple[str, ...]]) -> str:
    """The upload as the pipeline reads it: CSV text beginning at its header."""
    headers = list(headers)
    if is_workbook(content):
        rows = workbook_rows(content)
    else:
        text = content.decode("utf-8-sig", errors="replace")
        rows = list(csv.reader(text.splitlines()))
        if rows and tuple(c.strip() for c in rows[0]) in set(headers):
            return text  # already starts at its header: kept byte for byte
    rows = _from_header(rows, headers)
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    for row in rows:
        if any(cell.strip() for cell in row):
            writer.writerow(row)
    return out.getvalue()
