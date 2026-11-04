"""A trade opened with a SELL is in the total, and every rupee is accounted for [TICKET-790].

Worked by hand, on invented figures:
  sold option   SELL 65 @ 30, BUY 65 @ 10     +1,300
  sold shares   SELL 10 @ 100, BUY 10 @ 95       +50
  bought option BUY 65 @ 20, SELL 65 @ 15       -325
  shares open   BUY 2 @ 350                  700 at cost, not a result
  total +1,025. Cash from every fill is +325, and 325 + 700 = 1,025.
"""

from __future__ import annotations

from collections import deque
from decimal import Decimal
from types import SimpleNamespace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from services.production.ctr.reconstruct import reconstruct
from services.shared.schemas.ctr_v1 import Direction, Side
from tests.unit.test_reconstruction import EQ, NIFTY, fill, prices, qtys, sides

SOLD_OPTION = [fill(Side.SELL, 65, 30, 0, **NIFTY), fill(Side.BUY, 65, 10, 60, **NIFTY)]
SOLD_SHARES = [fill(Side.SELL, 10, 100, 1, **EQ), fill(Side.BUY, 10, 95, 61, **EQ)]
OTHER_NIFTY = {**NIFTY, "strike": Decimal(5600)}
BOUGHT_OPTION = [
    fill(Side.BUY, 65, 20, 2, **OTHER_NIFTY),
    fill(Side.SELL, 65, 15, 62, **OTHER_NIFTY),
]
OPEN_SHARES = {**EQ, "symbol": "INFY"}
STILL_OPEN = [fill(Side.BUY, 2, 350, 3, **OPEN_SHARES)]
BOOK = SOLD_OPTION + SOLD_SHARES + BOUGHT_OPTION + STILL_OPEN


def cash(fills) -> Decimal:
    return sum(
        ((f.price * f.quantity) * (1 if f.side is Side.SELL else -1) for f in fills), Decimal(0)
    )


def total(result) -> Decimal:
    return sum((t.gross_pnl for t in result.round_trips), Decimal(0))


def test_no_sold_trade_is_left_out():
    r = reconstruct(BOOK, short_options=True)
    assert r.skipped == []
    assert sum(t.direction is Direction.SHORT for t in r.round_trips) == 2


def test_each_sold_trade_keeps_its_result():
    r = reconstruct(BOOK, short_options=True)
    assert sorted(t.gross_pnl for t in r.round_trips if t.direction is Direction.SHORT) == [
        Decimal(50), Decimal(1300),
    ]


def test_the_total_reconciles_to_the_cash_and_what_is_open():
    r = reconstruct(BOOK, short_options=True)
    assert total(r) == Decimal(1025)
    assert cash(BOOK) == Decimal(325)
    assert [(o.symbol, o.quantity) for o in r.open_positions] == [("INFY", 2)]
    assert total(r) == cash(BOOK) + Decimal(700)


def test_a_sold_trade_is_valued_at_the_brokers_trade_value():
    """Why Scope reads a few rupees from a price-times-quantity total: 1,950.30 - 650 = 1,300.30."""
    fills = [
        fill(Side.SELL, 65, 30, 0, **NIFTY).model_copy(update={"trade_value": Decimal("1950.30")}),
        fill(Side.BUY, 65, 10, 60, **NIFTY).model_copy(update={"trade_value": Decimal(650)}),
    ]
    assert reconstruct(fills, short_options=True).round_trips[0].gross_pnl == Decimal("1300.30")


def _open_value(fills) -> Decimal:
    """What FIFO leaves open, worked separately from the code under test: cost if bought,
    minus the proceeds if sold."""
    book: deque = deque()
    for f in fills:
        sign = 1 if f.side is Side.BUY else -1
        left = f.quantity
        while left and book and book[0][0] != sign:
            taken = min(left, book[0][1])
            left -= taken
            book[0][1] -= taken
            if not book[0][1]:
                book.popleft()
        if left:
            book.append([sign, left, f.price])
    return sum((sign * qty * price for sign, qty, price in book), Decimal(0))


@given(st.lists(st.tuples(sides, qtys, prices), min_size=0, max_size=14))
@settings(max_examples=400, deadline=None)
def test_no_rupee_is_lost_with_sold_options_and_open_positions(seq):
    fills = [fill(s, q, p, i, **NIFTY) for i, (s, q, p) in enumerate(seq)]
    r = reconstruct(fills, short_options=True)
    assert r.skipped == []
    assert abs(total(r) - (cash(fills) + _open_value(fills))) <= Decimal("0.01")


def test_the_mirror_report_counts_sold_trades(monkeypatch, tmp_path):
    """The report reads the file itself rather than through the upload, so it has its own call.
    Sold option +1,300, bought option -325, so the result is +975."""
    pytest.importorskip("scipy")  # the report imports the research library
    from scripts import mirror_report

    parsed = SimpleNamespace(
        fills=SOLD_OPTION + BOUGHT_OPTION, rejected=[], fees_available=False, rows_in=4
    )
    monkeypatch.setattr(mirror_report, "parse", lambda *a, **k: parsed)
    monkeypatch.setattr(mirror_report, "OUT", tmp_path)
    export = tmp_path / "book.csv"
    export.write_bytes(b"synthetic")
    page = mirror_report.build(export, "Here").read_text(encoding="utf-8")
    assert "Rs 975" in page
    assert "<td>Trades reconstructed</td><td class=n>2</td><td class=n>0</td>" in page
