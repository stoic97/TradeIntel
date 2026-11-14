"""Write the Groww golden fixture, a made-up order history workbook (TICKET-895).

Laid out as Groww's real download is: a preamble (name, client code, a line naming the
dates), a blank row, the header on row 6, one row per order, oldest first. Every name,
code, id and figure in it is made up. Deterministic: the same bytes on every run.

    uv run python scripts/make_groww_fixture.py
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path("data/fixtures/groww_orders_sample.xlsx")

PREAMBLE = [
    ["Name", "Sample Trader"],
    ["Unique Client Code", "0000000000"],
    [],
    ["Order history for stocks from 01-11-2026 to 13-11-2026 "],
    [],
]
HEADER = ["Stock name", "Symbol", "ISIN", "Type", "Quantity", "Value", "Exchange",
          "Exchange Order Id", "Execution date and time", "Order status"]

# (stock name, symbol, isin, type, quantity, value, exchange, when, status)
ORDERS = [
    # a share bought and sold the same day
    ("RELIANCE INDUSTRIES LTD", "RELIANCE", "INE002A01018", "BUY", 10, "25000", "NSE", "02-11-2026 09:31 AM", "Executed"),
    ("RELIANCE INDUSTRIES LTD", "RELIANCE", "INE002A01018", "SELL", 10, "25210.5", "NSE", "02-11-2026 02:45 PM", "Executed"),
    # an order filled at several prices: 4595.50 / 3 is a repeating decimal
    ("INFOSYS LTD", "INFY", "INE009A01021", "BUY", 3, "4595.5", "NSE", "03-11-2026 10:05 AM", "Executed"),
    ("INFOSYS LTD", "INFY", "INE009A01021", "SELL", 3, "4800", "NSE", "04-11-2026 11:20 AM", "Executed"),
    # an after-market order, stamped 09:00 when it was sent
    ("STATE BANK OF INDIA", "SBIN", "INE062A01020", "BUY", 5, "4000", "NSE", "05-11-2026 09:00 AM", "Executed"),
    ("STATE BANK OF INDIA", "SBIN", "INE062A01020", "SELL", 5, "4105.25", "NSE", "05-11-2026 01:10 PM", "Executed"),
    # a share on BSE
    ("TATA STEEL LIMITED", "TATASTEEL", "INE081A01020", "BUY", 20, "3100", "BSE", "06-11-2026 10:40 AM", "Executed"),
    ("TATA STEEL LIMITED", "TATASTEEL", "INE081A01020", "SELL", 20, "3062", "BSE", "09-11-2026 12:15 PM", "Executed"),
    # a partial close: 6 of 10 stay open
    ("ITC LTD", "ITC", "INE154A01025", "BUY", 10, "4100", "NSE", "09-11-2026 09:45 AM", "Executed"),
    ("ITC LTD", "ITC", "INE154A01025", "SELL", 4, "1652", "NSE", "10-11-2026 10:30 AM", "Executed"),
    # a monthly option: the symbol has no day, so it is the month's last Tuesday
    ("BANKNIFTY Nov 52000 Put", "BANKNIFTY26NOV52000PE", "", "BUY", 30, "5100", "NSE", "10-11-2026 11:00 AM", "Executed"),
    ("BANKNIFTY Nov 52000 Put", "BANKNIFTY26NOV52000PE", "", "SELL", 30, "4650", "NSE", "11-11-2026 02:00 PM", "Executed"),
    # a future
    ("NIFTY Nov Fut", "NIFTY26NOVFUT", "", "BUY", 65, "1560000", "NSE", "11-11-2026 09:20 AM", "Executed"),
    ("NIFTY Nov Fut", "NIFTY26NOVFUT", "", "SELL", 65, "1565200", "NSE", "12-11-2026 03:10 PM", "Executed"),
    # a weekly option, one NIFTY lot in units
    ("NIFTY 17 Nov 24000 Call", "NIFTY26N1724000CE", "", "BUY", 65, "6630", "NSE", "12-11-2026 10:00 AM", "Executed"),
    ("NIFTY 17 Nov 24000 Call", "NIFTY26N1724000CE", "", "SELL", 65, "7125", "NSE", "13-11-2026 10:00 AM", "Executed"),
    # orders that did not trade, and a row nothing can identify
    ("HDFC BANK LTD", "HDFCBANK", "INE040A01034", "BUY", 4, "3800", "NSE", "13-11-2026 11:00 AM", "Cancelled"),
    ("YES BANK LIMITED", "YESBANK", "INE528G01035", "SELL", 100, "2000", "NSE", "13-11-2026 11:05 AM", "Rejected"),
    ("MYSTERY ITEM", "NOT A CONTRACT", "", "BUY", 1, "100", "NSE", "13-11-2026 11:10 AM", "Executed"),
    # a comma in the name, and a position left open
    ("BAJAJ FINANCE, LTD", "BAJFINANCE", "INE296A01032", "BUY", 2, "1800.1", "NSE", "13-11-2026 12:00 PM", "Executed"),
]


def _col(i: int) -> str:
    return "ABCDEFGHIJ"[i]


def sheet_and_strings(orders: list[tuple] | None = None) -> tuple[str, str]:
    strings: list[str] = []

    def s(text: str) -> int:
        if text not in strings:
            strings.append(text)
        return strings.index(text)

    rows = [*PREAMBLE, HEADER]
    for n, (name, sym, isin, side, qty, value, exch, when, status) in enumerate(orders or ORDERS):
        rows.append([name, sym, isin, side, qty, value, exch, f"{1000000000000000 + n * 7919}", when, status])

    out = []
    for r, row in enumerate(rows, start=1):
        cells = []
        for c, v in enumerate(row):
            ref = f"{_col(c)}{r}"
            if v == "":
                continue
            if isinstance(v, int) or (c == 5 and r > len(PREAMBLE) + 1):
                cells.append(f'<c r="{ref}"><v>{v}</v></c>')
            else:
                cells.append(f'<c r="{ref}" t="s"><v>{s(str(v))}</v></c>')
        out.append(f'<row r="{r}">{"".join(cells)}</row>')
    sheet = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
             f'<sheetData>{"".join(out)}</sheetData></worksheet>')
    shared = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
              f'count="{len(strings)}" uniqueCount="{len(strings)}">'
              + "".join(f"<si><t>{escape(t)}</t></si>" for t in strings) + "</sst>")
    return sheet, shared


PARTS = {
    "[Content_Types].xml": (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
        "</Types>"),
    "_rels/.rels": (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"),
    "xl/workbook.xml": (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>'),
    "xl/_rels/workbook.xml.rels": (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>'
        "</Relationships>"),
}


def build(orders: list[tuple] | None = None) -> bytes:
    """The workbook; `orders` picks a subset, e.g. only the shares, as a test needs."""
    import io

    sheet, shared = sheet_and_strings(orders)
    parts = {**PARTS, "xl/worksheets/sheet1.xml": sheet, "xl/sharedStrings.xml": shared}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as book:
        for name, body in parts.items():
            info = zipfile.ZipInfo(name, date_time=(2026, 11, 13, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3  # "made on Unix", whatever OS runs this: same bytes everywhere
            book.writestr(info, body)
    return buffer.getvalue()


if __name__ == "__main__":
    OUT.write_bytes(build())
    print(f"written: {OUT}")
