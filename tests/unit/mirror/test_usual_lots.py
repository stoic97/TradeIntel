"""Size in lots is counted on option trades only [TICKET-797].

A share has a lot size of one, so counting an ETF purchase as lots put hundreds of "lots"
into the average, and every ordinary day read as smaller than usual. Worked by hand.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select

from services.production.api import scope_facts as SF
from services.production.ctr.profiles import registry as profiles
from services.production.db import models as m
from services.production.db.session import make_session
from services.production.journal import periods as pd
from services.production.journal import prose
from services.production.journal import sections as sec
from services.production.mirror import loader
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s
from tests.unit.api.test_scope_chapters import trips_from
from tests.unit.api.test_scope_facts import fact_page


def history() -> list[mx.Trip]:
    """Day 1: an option at 3 lots and one at 1. Day 2: an option at 2 lots, and 100 shares.
    Options average (3 + 1 + 2) / 3 = 2. Counting the shares, (3 + 1 + 2 + 100) / 4 = 26.5."""
    start = datetime.fromisoformat("2026-09-01T09:15:00+05:30")
    plain = trips_from([100, -100, 100, -100])
    out = []
    for i, (t, day, lots, option) in enumerate(
        zip(plain, (1, 1, 2, 2), (3, 1, 2, 100), (True, True, True, False), strict=True)
    ):
        entry = start.replace(day=day, minute=15 + i)
        out.append(replace(t, trading_day=entry.date().isoformat(), entry_ts=entry,
                           exit_ts=entry.replace(hour=10), lots=lots, is_option=option))
    return out


def test_shares_are_not_counted_as_lots():
    assert mx.average_lots(history()).mean == Decimal(2)


def test_a_history_of_only_shares_has_no_average():
    only_shares = [t for t in history() if not t.is_option]
    result = mx.average_lots(only_shares)
    assert result.mean is None
    assert result.state is s.ResultState.INSUFFICIENT_SAMPLE


def test_a_trip_row_says_whether_it_is_an_option():
    base = {"trip_id": "x", "symbol": "S", "trading_day": "2026-09-01",
            "entry_ts": "2026-09-01T09:30:00+05:30", "exit_ts": "2026-09-01T10:00:00+05:30",
            "holding_seconds": 1800, "net": "1", "lots": 1,
            "risk_unit_source": "premium_paid"}
    assert mx.load_trips([base])[0].is_option is True
    assert mx.load_trips([{**base, "segment": "OPT"}])[0].is_option is True
    assert mx.load_trips([{**base, "segment": "EQ"}])[0].is_option is False


def test_the_loader_marks_a_share_trade(client, engine):
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader).where(m.Trader.login_id == "fx")).one()
        stored = sess.scalars(select(m.Trip).where(m.Trip.trip_id == "t01")).one()
        sess.add(m.Trip(
            import_id=stored.import_id, trip_id="a-share", trading_day="2026-09-01",
            exchange="NSE", symbol="SOME ETF", segment="EQ", direction="LONG",
            entry_ts=datetime.fromisoformat("2026-09-01T12:00:00+05:30"),
            exit_ts=datetime.fromisoformat("2026-09-01T12:10:00+05:30"),
            quantity=500, entry_price=Decimal(10), exit_price=Decimal(10),
            gross=Decimal(0), fees=Decimal(0), net=Decimal(0), fees_available=False,
            risk_unit_source=stored.risk_unit_source,
        ))
        sess.commit()
        trips, _ = loader.load_for(sess, trader)
    by_id = {t.trip_id: t for t in trips}
    assert by_id["a-share"].is_option is False
    assert by_id["t01"].is_option is True


def journal_facts(trips: list[mx.Trip], day: str) -> dict:
    periods = pd.periods_for(trips, unit=s.JournalUnit.DAY, export_date="2026-12-31")
    period = next(p for p in periods if p.period_start == day)
    return sec.build(period, history=trips, fees_available=False)


def test_a_journal_compares_option_size_with_option_size():
    """Day 2 has one option at 2 lots and 100 shares: 2 against the usual 2, not 51."""
    against = journal_facts(history(), "2026-09-02")["against_your_normal"]
    assert Decimal(against["lots_today"]) == Decimal(2)
    assert Decimal(against["lots_usually"]) == Decimal(2)


def test_a_day_above_the_usual_reads_as_above_it():
    """With day 2's option at 1 lot the usual is (3 + 1 + 1) / 3 = 1.667; day 1 averages 2."""
    trips = history()
    trips[2] = replace(trips[2], lots=1)
    text = prose._against_normal(journal_facts(trips, "2026-09-01"))
    assert "Your average size was 2.0 lots against your usual 1.7." in text


def test_a_day_of_only_shares_says_nothing_about_size():
    trips = [t for t in history() if t.trading_day == "2026-09-01"]
    shares = [t for t in history() if not t.is_option]
    facts = journal_facts([*trips, *shares], "2026-09-02")
    assert "lot" not in prose._against_normal(facts)


def test_an_old_journal_with_a_zero_size_says_nothing_about_size_either():
    facts = {"against_your_normal": {"trades_today": 1, "your_normal_day": "1",
                                     "lots_today": "0", "lots_usually": "2"}}
    assert "lot" not in prose._against_normal(facts)


def test_chapter_three_compares_option_size_only():
    """The same function reads both surfaces, so they cannot disagree (TICKET-798)."""
    ctx = SF.record_context(history())
    assert ctx["rest_lots"].mean == Decimal(2)


def test_a_history_of_only_shares_renders_the_chapter_three_fact():
    only_shares = [replace(t, is_option=False) for t in trips_from([100, -100, -100, -100, 50])]
    page = fact_page("down", only_shares)
    assert "None" not in page


def lots(exchange: str, symbol: str, quantity: int, on: str) -> int:
    profile = profiles.lookup(profiles.load_all(loader.PROFILE_DIR), exchange, symbol, "OPT")
    return loader.lots_for(quantity, profile, "units", on=date.fromisoformat(on))


def test_lot_sizes_listed_on_the_broker_today_do_not_refuse_the_record():
    """Fyers' symbol master, 4 Nov 2026. A size missing here stops the whole Mirror."""
    assert lots("NSE", "BANKNIFTY", 30, "2026-11-23") == 1
    assert lots("BSE", "SENSEX", 25, "2027-01-05") == 1
    assert lots("NSE", "HDFCBANK", 750, "2027-01-05") == 1


def test_the_sizes_already_traded_still_read_the_same():
    assert lots("NSE", "BANKNIFTY", 15, "2024-06-03") == 1
    assert lots("NSE", "BANKNIFTY", 35, "2025-10-01") == 1
    assert lots("BSE", "SENSEX", 40, "2026-11-05") == 2
    assert lots("NSE", "HDFCBANK", 650, "2026-11-20") == 1
    assert lots("NSE", "NIFTY", 65, "2026-11-20") == 1
    assert lots("NSE", "NIFTY", 75, "2025-06-02") == 1
    assert lots("NSE", "NIFTY", 25, "2024-08-01") == 1
    assert lots("MCX", "CRUDEOIL", 200, "2026-11-05") == 2
    assert lots("MCX", "CRUDEOILM", 60, "2026-11-05") == 6
