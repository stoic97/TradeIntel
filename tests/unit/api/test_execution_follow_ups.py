"""TICKET-1010 follow-ups from the 25 Nov review of #191.

1. A database error while reading the stored bar figures is raised, not turned into
   "No market figures for this file yet." The worker's tables are on main (migrations 0015 and
   0022), so a missing table is a real fault, not a state to explain.
2. A count on the Execution row opens exactly its trades through the real trade-list route.
3. The short-holds note is true for one trade: "1 trade under 45 minutes is too short".

Every trade here is made up. The route test's figures are worked by hand below.
"""
from __future__ import annotations

import html
import importlib
import os
import re
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from services.production.api.app import create_app
from services.production.db.session import make_engine, make_session, run_migrations
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s
from tests.helpers.upload import CSRF, sign_up

IST = ZoneInfo("Asia/Kolkata")
D = Decimal


def P():
    return importlib.import_module("services.production.api.process")


def PB():
    return importlib.import_module("services.production.api.process_bars")


# ---------- 1. a database error is raised ----------

class _Broken:
    def scalars(self, *_a, **_k):
        raise OperationalError("SELECT bar_trade_figure", {}, Exception("no such table"))


def test_a_database_error_reading_the_stored_trade_figures_is_raised():
    with pytest.raises(OperationalError):
        PB().stored(_Broken(), 1)


def test_a_database_error_reading_the_stored_day_ranges_is_raised():
    with pytest.raises(OperationalError):
        PB().ranges(_Broken(), 1)


# ---------- 3. the short-holds note for one trade ----------

def _trip(tid: str, net, minutes: int) -> mx.Trip:
    entry = datetime(2026, 3, 2, 9, 30, tzinfo=IST)
    leave = entry + timedelta(minutes=minutes)
    return mx.Trip(trip_id=tid, symbol="NIFTY", trading_day="2026-03-02", entry_ts=entry, exit_ts=leave,
                   holding_seconds=minutes * 60, net=D(str(net)), lots=1,
                   risk_unit_source=s.RiskUnitSourceV1.PREMIUM_PAID, is_option=True,
                   lines=(mx.TradeLine("NIFTY", "OPT", "Buy", 1, None, None, D(str(net))),))


def test_one_short_hold_reads_in_the_singular():
    p = P()
    one = _trip("a", 100, 10)
    row = p.execution(p.Reading([one], figures={"a": p.Bars("NIFTY", D(20), D(5), None)}))
    assert "1 trade under 45 minutes is too short to measure on minute bars." in row.notes
    assert not any("1 trade under 45 minutes are" in n for n in row.notes)


# ---------- 2. kept and gave-back open exactly their trades, end to end ----------

@pytest.fixture()
def client():
    engine = make_engine(os.environ["SCOPE_DB"])
    run_migrations(engine)
    c = sign_up(TestClient(create_app()), engine, "Y-1", "execfollowup")
    c.post("/upload/demo", data={"csrf_token": CSRF.search(c.get("/upload").text).group(1)},
           follow_redirects=False)
    c.engine = engine
    return c


def _caption(page: str) -> tuple[int, int]:
    text = html.unescape(re.sub(r"<[^>]+>", "", page))
    m = re.search(r"([\d,]+)\s+of\s+([\d,]+)\s+trades?\.", text)
    assert m, "no 'N of M trades.' caption on the trade list"
    return int(m.group(1).replace(",", "")), int(m.group(2).replace(",", ""))


def test_kept_and_gave_back_open_exactly_their_trades_on_the_page(client):
    """Four of the demo's trades held 45 minutes or more get stored figures, in NIFTY points:

        trade  net     way  took
        W1     +       20   10
        W2     +       30   15
        W3     +       10    4
        L1     -       40   -5

    Kept counts trades the market moved his way (way > 0): all four, so kept-NIFTY opens 4.
    His usual move is the median of 10, 20, 30 and 40, which is 25. Gave back = way above 25 and
    closed at a loss: only L1 (40), so gave-back-NIFTY opens 1. Every other trade has no stored
    figure, so it is in neither list.
    """
    from services.production.db import models as m
    from services.production.mirror import loader

    with make_session(client.engine) as sess:
        trader = sess.query(m.Trader).filter_by(login_id="execfollowup").one()
        trips, imp = loader.load_for(sess, trader)
        held = [t for t in trips if t.holding_seconds >= 45 * 60]
        winners = [t for t in held if t.net > 0][:3]
        losers = [t for t in held if t.net < 0][:1]
        assert len(winners) == 3 and len(losers) == 1, "the demo needs 3 winners and 1 loser held 45 minutes or more"
        figures = [(winners[0], "20", "10"), (winners[1], "30", "15"), (winners[2], "10", "4"),
                   (losers[0], "40", "-5")]
        for t, way, took in figures:
            sess.add(m.BarTradeFigure(import_id=imp.id, trip_id=t.trip_id, underlying="NIFTY", reason=None,
                                      way=way, against="0", took=took, path=None, short=False))
        sess.commit()

    kept = client.get("/mirror/fact/risk/trades", params={"line": "kept-NIFTY"})
    assert kept.status_code == 200
    assert _caption(kept.text)[0] == 4
    back = client.get("/mirror/fact/risk/trades", params={"line": "gave-back-NIFTY"})
    assert back.status_code == 200
    assert _caption(back.text)[0] == 1
