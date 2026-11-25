"""TICKET-1011: Your process, the Market row.

His result on quiet, middle and wide days: his traded days split into thirds by how far the
market moved that day (the session's high less its low, in points), his own cut points shown.
The ranges are stored off the web app by the bar-figures worker, one per (underlying, day) he
traded; the page reads them and never bars. Every day and figure here is made up.
"""
from __future__ import annotations

import html
import importlib
import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s
from tests.helpers.no_claims import CLAIM_PATTERNS, NEVER_USED

IST = ZoneInfo("Asia/Kolkata")
D = Decimal
START = date(2026, 1, 5)


def P():
    return importlib.import_module("services.production.api.process")


def trip(tid: str, day: date, net) -> mx.Trip:
    entry = datetime.combine(day, datetime.min.time()).replace(hour=10, tzinfo=IST)
    leave = entry + timedelta(minutes=60)
    return mx.Trip(trip_id=tid, symbol="NIFTY", trading_day=day.isoformat(), entry_ts=entry, exit_ts=leave,
                   holding_seconds=3600, net=D(str(net)), lots=1,
                   risk_unit_source=s.RiskUnitSourceV1.PREMIUM_PAID, is_option=True,
                   lines=(mx.TradeLine("NIFTY", "OPT", "Buy", 1, None, None, D(str(net))),))


def days(n: int) -> list[date]:
    out, d = [], START
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def record(n_days=30, underlying="NIFTY", prefix="t", ranges=None, net=lambda i: 100):
    """One trade a day; day i's range is 100 + 10 i points unless ``ranges`` says otherwise."""
    p = P()
    trips, figures, stored = [], {}, {}
    for i, d in enumerate(days(n_days)):
        t = trip(f"{prefix}{i}", d, net(i))
        trips.append(t)
        figures[t.trip_id] = p.Bars(underlying, D(50), D(10), None)
        stored[(underlying, d.isoformat())] = D(str(ranges[i] if ranges else 100 + 10 * i))
    return trips, figures, stored


def market(trips, figures, ranges, earlier=None):
    p = P()
    before = p.Reading(earlier[0], figures=earlier[1], ranges=earlier[2]) if earlier else None
    rows = p.build(p.Reading(trips, figures=figures, ranges=ranges), before)
    return next(r for r in rows if r.key == "market")


def words(row) -> str:
    return " ".join(html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", str(ln.text)))).strip()
                    for ln in row.lines)


def line(row, key):
    return next(ln for ln in row.lines if ln.key == key)


def test_the_row_comes_after_execution():
    names = [b.__name__ for b in P().ROWS]
    assert names[-2:] == ["execution", "market"]


def test_no_stored_ranges_says_so():
    trips, figures, _ = record()
    row = market(trips, figures, None)
    assert row.lines == () and row.empty


def test_thirds_of_his_own_days_with_his_cut_points():
    # 30 days, ranges 100, 110, ..., 390. The 10th is 190 and the 20th 290: quiet is up to 190,
    # wide is over 290, so 10 days in each third.
    trips, figures, stored = record()
    row = market(trips, figures, stored)
    text = words(row)
    assert "quiet: up to 190 points" in text and "wide: over 290 points" in text
    for third in ("quiet", "middle", "wide"):
        assert len(line(row, f"range-NIFTY-{third}").sets[f"range-NIFTY-{third}"]) == 10


def test_each_third_says_days_trades_result_and_days_that_made_money():
    # days 0..29, a loss of 100 on the quiet days 0..4, a gain of 100 otherwise.
    trips, figures, stored = record(net=lambda i: -100 if i < 5 else 100)
    ln = line(market(trips, figures, stored), "range-NIFTY-quiet")
    text = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", str(ln.text)))).strip()
    assert "10 days" in text and "10 trades" in text
    assert "made money on 5 of 10 days" in text
    assert "₹0" in text  # five losses of 100 and five gains of 100


def test_ties_at_a_cut_point_stay_in_one_third():
    # 30 days: twelve at 100 points, then 200..380. The 10th day is 100, so all twelve are quiet.
    ranges = [100] * 12 + [200 + 10 * i for i in range(18)]
    trips, figures, stored = record(ranges=ranges)
    row = market(trips, figures, stored)
    assert len(line(row, "range-NIFTY-quiet").sets["range-NIFTY-quiet"]) == 12


def test_fewer_than_30_days_is_too_few():
    trips, figures, stored = record(n_days=29)
    assert "too few days" in words(market(trips, figures, stored))


def test_two_underlyings_are_kept_apart():
    a, fa, sa = record(prefix="n")
    b, fb, sb = record(underlying="CRUDEOIL", prefix="c")
    row = market(a + b, {**fa, **fb}, {**sa, **sb})
    keys = {ln.key for ln in row.lines}
    assert "range-NIFTY-quiet" in keys and "range-CRUDEOIL-quiet" in keys


def test_crude_on_another_months_contract_is_counted_apart():
    p = P()
    trips, figures, stored = record(underlying="CRUDEOIL", prefix="c")
    odd = trip("odd", days(1)[0], 900)
    figures[odd.trip_id] = p.Bars("CRUDEOIL", None, None, "contract month differs from the near-month series")
    row = market(trips + [odd], figures, stored)
    assert "odd" not in line(row, "range-CRUDEOIL-quiet").sets["range-CRUDEOIL-quiet"]
    assert any("1 trade on a contract month the series doesn't follow" in n for n in row.notes)


def test_each_third_opens_exactly_its_trades():
    p = P()
    trips, figures, stored = record()
    row = market(trips, figures, stored)
    ln = line(row, "range-NIFTY-wide")
    assert p.members(trips, ln.key, figures=figures, ranges=stored) == ln.sets[ln.key]


def test_the_earlier_reading_beside_todays():
    trips, figures, stored = record(net=lambda i: -100 if i < 5 else 100)
    old = record(prefix="o", net=lambda i: -100 if i < 2 else 100)
    ln = line(market(trips, figures, stored, old), "range-NIFTY-quiet")
    assert ln.was is not None


def test_no_claim_and_no_bars_read(monkeypatch):
    from services.production.prices import layer

    def no(*a, **kw):
        raise AssertionError("a page read bars")

    monkeypatch.setattr(layer.Prices, "__init__", no)
    trips, figures, stored = record()
    text = words(market(trips, figures, stored)).lower()
    assert not [w for w in NEVER_USED if re.search(rf"\b{re.escape(w)}\b", text)]
    assert not [p for p, _why in CLAIM_PATTERNS if re.search(p, text, re.IGNORECASE)]
    for word in ("better", "worse", "suits", "best", "worst"):
        assert not re.search(rf"\b{word}\b", text), word
