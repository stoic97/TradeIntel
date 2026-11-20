"""TICKET-910: "What your tradebook has been hiding" - plain counts by book, first half against second.

Pins the gate and the founder's rulings of 13 Nov 2026 (in Jira, not repeated here):
- each book on its own trading days, split in date order; an odd count puts the middle day in the
  second half;
- the counts: days traded, green days and their share, green months of months traded, days since
  the last new high, net per trade, and break-even exactly as metrics.math_row decides it;
- same-day trades only (definitions 1); a position held past the day counts nowhere;
- the control: whole days shuffled between the halves, the change in net per trade, 10,000 draws,
  two-sided, p = (b+1)/(N+1), seed recorded, shown beside its count, never called a finding;
- the page is the report's first page in scope_map's one order (TICKET-903), and every count
  opens its trades (TICKET-905).

Every expected value is worked by hand from the small invented books below, never read off the
code. No trader data is in this file.
"""

from __future__ import annotations

import importlib
import json
import re
import types
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import numpy as np
import pytest

from services.production.api import scope_facts as SF
from services.production.api import scope_map as S
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s
from tests.unit.mirror.wording import page_text

IST = timezone(timedelta(hours=5, minutes=30))
OIL, IDX = "WIDGETOIL options", "WIDGETIDX options"
TITLE = "What your tradebook has been hiding"
IMP = types.SimpleNamespace(
    fees_available=False,
    trips_refused=0,
    rows_in=40,
    rows_parsed=40,
    id=1,
    trips_reconstructed=40,
    rows_excluded=0,
)


def _built(module, name: str):
    assert hasattr(module, name), f"{module.__name__}.{name} is not built yet (TICKET-910)"
    return getattr(module, name)


def _shuffle_module():
    try:
        return importlib.import_module("services.shared.conditions.halves_shuffle")
    except ModuleNotFoundError:
        pytest.fail("services/shared/conditions/halves_shuffle.py is not built yet (TICKET-910)")


def trip(
    i: int, day: str, net: int, symbol: str = "WIDGETOIL", minute: int = 0, held: bool = False
) -> mx.Trip:
    entry = datetime.fromisoformat(day).replace(hour=10, minute=minute, tzinfo=IST)
    leave = entry + (timedelta(days=1) if held else timedelta(minutes=5))
    return mx.Trip(
        f"T{i}",
        symbol,
        day,
        entry,
        leave,
        int((leave - entry).total_seconds()),
        Decimal(net),
        1,
        s.RiskUnitSourceV1.PREMIUM_PAID,
    )


# WIDGETOIL: six trading days over two months. Halves: 5, 6, 20 Jan | 2, 3, 10 Feb.
#   day         trades       day net   running net from 0   new high
#   2026-01-05  +100, -40      +60          +60               yes
#   2026-01-06  -50            -50          +10
#   2026-01-20  +30            +30          +40
#   2026-02-02  -80, +10       -70          -30
#   2026-02-03  +200          +200         +170               yes
#   2026-02-10  -20            -20         +150
# A position opened 6 Jan and held overnight (+999) is not a same-day trade: it counts nowhere.
# WIDGETIDX: two days of its own, on days WIDGETOIL did not trade; it never rises above 0.
BOOKS = [
    trip(1, "2026-01-05", 100),
    trip(2, "2026-01-05", -40, minute=10),
    trip(3, "2026-01-06", -50),
    trip(4, "2026-01-06", 999, minute=20, held=True),
    trip(5, "2026-01-20", 30),
    trip(6, "2026-02-02", -80),
    trip(7, "2026-02-02", 10, minute=10),
    trip(8, "2026-02-03", 200),
    trip(9, "2026-02-10", -20),
    trip(10, "2026-03-02", -10, symbol="WIDGETIDX"),
    trip(11, "2026-03-03", -5, symbol="WIDGETIDX"),
]


def _rows(**kw) -> dict:
    book_halves = _built(mx, "book_halves")
    return {r.book: r for r in book_halves(BOOKS, **kw)}


# ---- gate 1: each book on its own trading days


def test_each_book_is_split_on_its_own_trading_days():
    rows = _rows(minimum=1)
    assert set(rows) == {OIL, IDX}
    oil, idx = rows[OIL], rows[IDX]
    assert (oil.first.first_day, oil.first.last_day) == ("2026-01-05", "2026-01-20")
    assert (oil.second.first_day, oil.second.last_day) == ("2026-02-02", "2026-02-10")
    assert (idx.first.first_day, idx.first.last_day) == ("2026-03-02", "2026-03-02")
    assert (idx.second.first_day, idx.second.last_day) == ("2026-03-03", "2026-03-03")


def test_an_odd_number_of_days_puts_the_middle_day_in_the_second_half():
    hs = _shuffle_module()
    assert [hs.first_half_size(n) for n in (2, 3, 5, 6)] == [1, 1, 2, 3]


# ---- gate 2: the counts, by hand from the table above


def test_the_counts_for_each_half_and_the_whole_book():
    oil = _rows(minimum=1)[OIL]
    got = {
        name: (
            h.days,
            h.trades,
            h.green_days,
            h.green_day_percent,
            h.months,
            h.green_months,
            h.days_since_high,
            h.net_per_trade,
        )
        for name, h in (("first", oil.first), ("second", oil.second), ("whole", oil.whole))
    }
    assert got == {
        "first": (3, 4, 2, 67, 1, 1, 2, Decimal(10)),
        "second": (3, 4, 1, 33, 1, 1, 1, Decimal("27.5")),
        "whole": (6, 8, 3, 50, 2, 2, 1, Decimal("18.75")),
    }
    assert oil.change_in_net_per_trade == Decimal("17.5")


def test_a_book_that_never_rose_above_zero_has_no_new_high_yet():
    idx = _rows(minimum=1)[IDX]
    assert idx.first.days_since_high is None and idx.whole.days_since_high is None


def test_a_position_held_past_the_day_counts_nowhere():
    oil = _rows(minimum=1)[OIL]
    assert oil.whole.trades == 8 and oil.whole.net_per_trade == Decimal("18.75")
    assert oil.held_past_day == 1


def test_break_even_is_the_math_pages_own_row():
    oil = _rows(minimum=1)[OIL]
    same_day = [t for t in BOOKS if t.closed_same_day and mx.trade_book(t) == OIL]
    assert oil.whole.math == mx.math_row(OIL, same_day)
    assert oil.first.math == mx.math_row(OIL, same_day[:4])
    assert oil.second.math == mx.math_row(OIL, same_day[4:])


def test_a_book_under_the_minimum_has_no_figure_to_print():
    oil = _rows()[OIL]  # 8 same-day trades, under metrics.BOOK_ROW_MINIMUM
    assert oil.state is s.ResultState.INSUFFICIENT_SAMPLE
    assert (oil.first, oil.second, oil.whole, oil.control) == (None, None, None, None)


# ---- gate 3: the control, whole days shuffled between the halves


def test_the_control_is_whole_days_shuffled_between_the_halves_two_sided():
    hs = _shuffle_module()
    # Four days of one trade each, nets 10, 20, -10, -20; halves 10, 20 | -10, -20: change -30.
    # The six equally likely splits change by -30, +30, 0, 0, +10, -10. Two are at least 30 from
    # zero either way, so the exact two-sided p is 2/6.
    r = hs.halves_test(np.array([10.0, 20.0, -10.0, -20.0]), np.array([1, 1, 1, 1]))
    assert r.change == pytest.approx(-30.0)
    assert r.draws == 10000 == hs.DRAWS and r.seed == hs.SEED
    assert abs(r.p - 1 / 3) < 0.02


def test_the_control_weighs_each_day_by_its_trades():
    hs = _shuffle_module()
    # Halves: (100 over 1 trade + 0 over 3) | (30 over 2 + 10 over 2): 25 then 10, change -15.
    r = hs.halves_test(np.array([100.0, 0.0, 30.0, 10.0]), np.array([1, 3, 2, 2]))
    assert r.change == pytest.approx(-15.0)


def test_the_control_is_reproducible_and_never_zero():
    hs = _shuffle_module()
    nets, trades = np.array([5.0, -3.0, 8.0, 1.0, -9.0, 4.0]), np.array([2, 1, 3, 1, 2, 1])
    a, b = hs.halves_test(nets, trades), hs.halves_test(nets, trades)
    assert a.p == b.p
    assert a.p >= 1 / (hs.DRAWS + 1)


def test_the_control_needs_thirty_trades_in_each_half():
    oil = _rows(minimum=1)[OIL]
    assert oil.control is not None and oil.control.p is None  # four trades a half


def test_production_reaches_the_control_without_research():
    src = Path("services/shared/conditions/halves_shuffle.py")
    assert src.exists(), "halves_shuffle.py is not built yet"
    assert "services.research" not in src.read_text(encoding="utf-8")


# ---- the page, on the 40-trip contract fixture


def _page(client) -> str:
    r = client.get("/mirror/fact/hidden")
    assert r.status_code == 200, "the page is not built yet"
    return r.text


def test_the_page_is_the_first_of_the_report(client):
    first = S.CHAPTERS[0].facts[0]
    assert (first.key, first.title) == ("hidden", TITLE)
    assert S.page_number("hidden") == 1  # TICKET-903's one order: every surface reads it
    html = _page(client)
    assert "CHAPTER 1 \u00b7 FACT 1 OF 3" in html
    assert re.search(
        rf'class="rail__count[^"]*">1 of {len(S.PAGES)}<', html
    )  # page_text writes it [N] of [N]
    assert 'data-dwell-line="hidden"' in html
    chapter = client.get(S.chapter_href(1)).text
    assert chapter.index(TITLE) < chapter.index("Your worst trading days")


def test_nothing_on_the_page_is_called_a_finding_ranked_or_priced(client):  # gates 4 and 5
    text = page_text(_page(client)).lower()
    assert "plain counts, not a finding." in text
    assert text.replace("not a finding", "").count("finding") == 0
    for word in ("biggest problem", "rank", "saved", "avoided", "cost", "kept"):
        assert re.search(rf"\b{word}", text) is None, word


def test_each_book_has_its_table_and_every_count_opens_its_trades(client):  # gates 1, 2, 6
    html = _page(client)
    assert 'data-table="hidden"' in html and 'data-control="net-per-trade"' in html
    text = page_text(html)
    for head in ("First half", "Second half", "All its days"):
        assert head in text, head
    assert "before charges" in text.lower()
    links = [
        h.replace("&amp;", "&") for h in re.findall(r'<a class="figure-link" href="([^"]+)"', html)
    ]
    halves = [h for h in links if h.startswith("/mirror/fact/hidden/trades")]
    assert any("book=WIDGETOIL+options" in h and "half=first" in h for h in halves)
    assert any("book=WIDGETOIL+options" in h and "half=second" in h for h in halves)


def _fixture_halves() -> tuple[list, list]:
    """Recounted from the fixture and definitions 1 only: same-day, own days, date order."""
    trips = json.loads(Path("tests/fixtures/mirror_contract/main.json").read_text(encoding="utf-8"))
    same_day = [t for t in trips if t["exit_ts"][:10] == t["trading_day"]]
    days = sorted({t["trading_day"] for t in same_day})
    first = set(days[: len(days) // 2])
    return (
        [t for t in same_day if t["trading_day"] in first],
        [t for t in same_day if t["trading_day"] not in first],
    )


@pytest.mark.parametrize("half", ["first", "second"])
def test_a_half_opens_exactly_its_own_trades(client, half):
    first, second = _fixture_halves()
    r = client.get(f"/mirror/fact/hidden/trades?book=WIDGETOIL+options&half={half}")
    assert r.status_code == 200, "the half filter is not built yet"
    assert r.text.count('<article class="trade">') == len(first if half == "first" else second)


def test_a_file_with_no_book_of_thirty_trades_says_not_enough_trades_yet():
    figs = SF.facts(SF.record_context(BOOKS), IMP)
    assert "hidden" in figs, "the fact is not built yet"
    assert figs["hidden"]["state"] == "not-enough"


def test_the_kits_stylesheet_is_untouched():  # gate 7
    app = Path("services/production/api/static/css/components.css").read_bytes()
    kit = Path("docs/design/scope-kit/static/css/components.css").read_bytes()
    assert app == kit


# ---- the money wedge on a phone (founder, 14 Nov): fewer words, a plus may go, never a minus


def _money_wedge(trips):
    return SF.facts(SF.record_context(trips), IMP)["money"]["wedge"]


def test_the_money_wedge_on_a_phone_drops_a_plus():
    wedge = _money_wedge(BOOKS)  # the best same-day trade made +200
    assert wedge["figure"].startswith("+")
    assert wedge["phone_figure"] == wedge["figure"].removeprefix("+")
    assert wedge["phone_label"].replace("\n", " ") == "best trade"


def test_the_money_wedge_on_a_phone_never_drops_a_minus():
    wedge = _money_wedge([trip(1, "2026-01-05", -40), trip(2, "2026-01-06", -10)])  # the best lost
    assert not wedge["figure"].startswith("+")
    assert wedge["phone_figure"] == wedge["figure"]
