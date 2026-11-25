"""TICKET-1010: Your process, the Execution row.

Of the move the market gave him while he held, how much he kept, in the underlying's points:
"you kept 34 of 100 points the market moved your way while you held". Only holds of 45
minutes or more, because on 1-minute bars the best price reached is biased for short holds
(TD-004). And the trades that went more than his own usual move his way and closed at a loss.
It reads the bar figures stored off the web app (the bar-figures worker), never bars. Every
trade and figure here is made up, worked by hand in the comments.
"""
from __future__ import annotations

import html
import importlib
import re
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s
from tests.helpers.no_claims import CLAIM_PATTERNS, NEVER_USED

IST = ZoneInfo("Asia/Kolkata")
D = Decimal


def P():
    return importlib.import_module("services.production.api.process")


def trip(tid: str, net, minutes: int, i: int = 0) -> mx.Trip:
    entry = datetime(2026, 3, 2, 9, 30, tzinfo=IST) + timedelta(days=i // 5)
    leave = entry + timedelta(minutes=minutes)
    return mx.Trip(trip_id=tid, symbol="NIFTY", trading_day=entry.date().isoformat(), entry_ts=entry,
                   exit_ts=leave, holding_seconds=minutes * 60, net=D(str(net)), lots=1,
                   risk_unit_source=s.RiskUnitSourceV1.PREMIUM_PAID, is_option=True,
                   lines=(mx.TradeLine("NIFTY", "OPT", "Buy", 1, None, None, D(str(net))),))


def bars(underlying="NIFTY", way=None, took=None, reason=None):
    return P().Bars(underlying=underlying, way=None if way is None else D(str(way)),
                    took=None if took is None else D(str(took)), reason=reason)


def record(n=30, way=100, took=34, minutes=60, underlying="NIFTY", prefix="t", net=500):
    trips = [trip(f"{prefix}{i}", net, minutes, i) for i in range(n)]
    figures = {t.trip_id: bars(underlying, way, took) for t in trips}
    return trips, figures


def execution(trips, figures, earlier=None):
    p = P()
    before = p.Reading(earlier[0], figures=earlier[1]) if earlier else None
    rows = p.build(p.Reading(trips, figures=figures), before)
    return next(r for r in rows if r.key == "execution")


def words(row) -> str:
    return " ".join(html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", str(ln.text)))).strip()
                    for ln in row.lines)


def test_the_row_is_in_the_registry_after_the_others():
    assert "execution" in [b.__name__ for b in P().ROWS]


def test_no_stored_figures_yet_the_row_says_so_and_nothing_breaks():
    trips, _ = record()
    row = execution(trips, None)
    assert row.lines == () and row.empty


def test_kept_points_over_holds_of_45_minutes_or_more():
    # 30 trades, each moved 100 points his way while held and closed 34 points his way:
    # 30 x 34 / (30 x 100) = 34 of 100 points.
    trips, figures = record()
    text = words(execution(trips, figures))
    assert "you kept 34 of 100 points the market moved your way while you held" in text
    assert "NIFTY" in text and "in the underlying's points, not your option's price" in text


def test_holds_under_45_minutes_are_left_out_and_counted():
    long_trips, figures = record()
    short = [trip(f"s{i}", 500, 20, i) for i in range(7)]
    figures.update({t.trip_id: bars("NIFTY", 500, 1) for t in short})  # would swamp the rate if counted
    row = execution(long_trips + short, figures)
    assert "you kept 34 of 100 points" in words(row)
    assert any("7 trades under 45 minutes are too short to measure on minute bars" in n for n in row.notes)


def test_a_negative_sum_says_he_gave_back_more_than_it_moved_his_way():
    trips, figures = record(took=-120)
    text = words(execution(trips, figures))
    assert "you gave back more than it moved your way while you held" in text
    assert "kept" not in text


def test_under_30_trades_is_too_few():
    trips, figures = record(n=29)
    assert "too few for a rate" in words(execution(trips, figures))


def test_went_more_than_his_usual_move_and_closed_at_a_loss():
    # ways 10, 20, ..., 300 (30 trades): his usual (median) way is the 15th and 16th's middle,
    # (150 + 160) / 2 = 155. Above it: 160..300, 15 trades; of those, the five with a loss.
    trips = [trip(f"m{i}", -100 if i in (16, 18, 20, 22, 24) else 100, 60, i) for i in range(30)]
    figures = {t.trip_id: bars("NIFTY", 10 * (i + 1), 5) for i, t in enumerate(trips)}
    text = words(execution(trips, figures))
    assert "5 trades went more than your usual 155 points your way and closed at a loss" in text


def test_two_underlyings_are_kept_apart():
    nifty, f1 = record(prefix="n")
    crude, f2 = record(underlying="CRUDEOIL", took=50, prefix="c")
    text = words(execution(nifty + crude, {**f1, **f2}))
    assert "NIFTY" in text and "CRUDEOIL" in text
    assert "you kept 34 of 100 points" in text and "you kept 50 of 100 points" in text


def test_trades_the_worker_could_not_measure_are_not_counted():
    trips, figures = record()
    extra = [trip(f"x{i}", 500, 60, i) for i in range(3)]
    figures.update({t.trip_id: bars("NIFTY", reason="no market data for this underlying") for t in extra})
    assert "you kept 34 of 100 points" in words(execution(trips + extra, figures))


def test_each_figure_opens_exactly_its_trades():
    p = P()
    trips, figures = record()
    row = execution(trips, figures)
    kept = next(ln for ln in row.lines if ln.key.startswith("kept-"))
    assert kept.sets[kept.key] == frozenset(t.trip_id for t in trips)
    assert p.members(trips, kept.key, figures=figures) == kept.sets[kept.key]


def test_the_earlier_reading_is_shown_beside_todays():
    trips, figures = record()
    old_trips, old_figures = record(took=29, prefix="o")
    kept = next(ln for ln in execution(trips, figures, (old_trips, old_figures)).lines
                if ln.key.startswith("kept-"))
    assert kept.was is not None and "29" in str(kept.was)


def test_no_forbidden_words():
    trips, figures = record(took=-120)
    more, f2 = record(prefix="b")
    text = words(execution(trips + more, {**figures, **f2})).lower()
    for phrase in ("left on the table", "could have", "should have", "missed", "cost you"):
        assert phrase not in text, phrase
    assert not [w for w in NEVER_USED if re.search(rf"\b{re.escape(w)}\b", text)]
    assert not [p for p, _why in CLAIM_PATTERNS if re.search(p, text, re.IGNORECASE)]


def test_the_page_never_reads_bars(monkeypatch):
    from services.production.prices import layer

    def no(*a, **kw):
        raise AssertionError("a page read bars")

    monkeypatch.setattr(layer.Prices, "__init__", no)
    trips, figures = record()
    assert execution(trips, figures).lines


@pytest.mark.parametrize("value", ["34", "155"])
def test_figures_are_written_through_figure(value):
    trips = [trip(f"m{i}", -100 if i in (16, 18) else 100, 60, i) for i in range(30)]
    figures = {t.trip_id: bars("NIFTY", 10 * (i + 1), D("3.4") * (i + 1)) for i, t in enumerate(trips)}
    html = "".join(str(ln.text) for ln in execution(trips, figures).lines)
    assert re.search(rf'<span class="num">[^<]*{value}', html) or re.search(rf"num[^>]*>.*?{value}", html)


# ---------- Read from what the worker stored ----------

@pytest.fixture()
def sess():
    import os

    from services.production.db.session import make_engine, make_session, run_migrations
    engine = make_engine(os.environ["SCOPE_DB"])
    run_migrations(engine)
    with make_session(engine) as s_:
        yield s_


def _an_import(sess):
    from datetime import UTC

    from services.production.db import models as m
    trader = m.Trader(display_name="t", login_id="exec-reader", password_hash="x", created_at=datetime.now(UTC))
    sess.add(trader)
    sess.flush()
    raw = m.RawFile(trader_id=trader.id, sha256="e" * 64, original_name="t.csv", size=1, stored_path="x",
                    uploaded_at=datetime.now(UTC))
    sess.add(raw)
    sess.flush()
    imp = m.Import(trader_id=trader.id, raw_file_id=raw.id, source_account="A", adapter_id="dhan_tradebook_v1",
                   adapter_version="1", filemap_version="1", code_version="t",
                   outcome=s.ImportOutcome.ACCEPTED_PARTIAL_FIELDS, rows_in=1, rows_parsed=1, rows_excluded=0,
                   fees_available=False, version_no=1, trips_reconstructed=1, density_default_unit="day",
                   created_at=datetime.now(UTC))
    sess.add(imp)
    sess.flush()
    return imp


def test_nothing_stored_reads_as_none(sess):
    from services.production.api import process_bars
    assert process_bars.stored(sess, _an_import(sess).id) is None


def test_the_stored_figures_are_read_as_points(sess):
    from services.production.api import process_bars
    from services.production.db import models as m
    if not hasattr(m, "BarTradeFigure"):
        pytest.skip("the bar-figures worker's table is not on this branch yet")
    imp = _an_import(sess)
    sess.add(m.BarTradeFigure(import_id=imp.id, trip_id="a", underlying="NIFTY", reason=None, way="62",
                              against="18", took="21", path=None, short=False))
    sess.add(m.BarTradeFigure(import_id=imp.id, trip_id="b", underlying="NIFTY",
                              reason="no market data for this underlying", way=None, against=None, took=None,
                              path=None, short=False))
    sess.flush()
    got = process_bars.stored(sess, imp.id)
    assert got["a"] == P().Bars("NIFTY", D(62), D(21), None)
    assert got["b"].reason == "no market data for this underlying" and got["b"].way is None
