"""Same-day trades and positions held past the day, kept apart [TICKET-791].

A position held for months is not a trade the day's decisions made, so it must not sit
among the best and worst five. Answers are in expected_held_past_day.json, worked by
hand from held_past_day.json (Manual 5.4).
"""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from services.production.api import scope_facts as SF
from services.production.db import models as m
from services.production.db.session import make_session
from services.production.mirror import loader
from services.production.mirror import metrics as mx

HERE = Path("tests/fixtures/mirror_contract")
ROWS = json.loads((HERE / "held_past_day.json").read_text())
WANT = json.loads((HERE / "expected_held_past_day.json").read_text())


@pytest.fixture()
def trips():
    return mx.load_trips(ROWS)


def test_the_committed_fixture_is_what_the_generator_writes():
    spec = importlib.util.spec_from_file_location("mirror_generate", HERE / "generate.py")
    generate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generate)
    assert generate.build(generate.HELD_PAST_DAY_TRIPS) == ROWS


def test_a_trade_closed_the_day_it_opened_is_same_day(trips):
    same_day = mx.same_day_trips(trips)
    assert len(same_day) == WANT["same_day_trip_count"]
    assert not {t.trip_id for t in same_day} & set(WANT["held_past_day"]["trip_ids"])


def test_open_to_close_on_one_day_is_still_same_day(trips):
    assert "h10" in {t.trip_id for t in mx.same_day_trips(trips)}


def test_twenty_minutes_across_midnight_is_held_past_the_day(trips):
    assert "h09" in {t.trip_id for t in mx.held_past_day(trips).trips}


def test_held_past_the_day_counts_winners_and_losers_together(trips):
    held = mx.held_past_day(trips)
    want = WANT["held_past_day"]
    assert sorted(t.trip_id for t in held.trips) == want["trip_ids"]
    assert held.count == want["count"]
    assert held.net == Decimal(want["net"])


def test_nothing_is_lost_between_the_two_groups(trips):
    same_day_net = sum((t.net for t in mx.same_day_trips(trips)), Decimal(0))
    assert same_day_net + mx.held_past_day(trips).net == Decimal(WANT["whole_history_net"])


def test_a_history_with_nothing_held_has_an_empty_held_group():
    rows = [r for r in ROWS if r["trip_id"] not in WANT["held_past_day"]["trip_ids"]]
    held = mx.held_past_day(mx.load_trips(rows))
    assert held.count == 0 and held.net == 0 and held.trips == []


def test_the_record_reads_best_and_worst_five_from_same_day_trades_only(trips):
    ctx = SF.record_context(trips)
    assert [t.trip_id for t in ctx["best"]] == WANT["best_five_trades"]
    assert [t.trip_id for t in ctx["worst"]] == WANT["worst_five_trades"]


def test_the_record_carries_the_held_group(trips):
    ctx = SF.record_context(trips)
    assert ctx["held_past_day"].count == WANT["held_past_day"]["count"]


def test_the_other_facts_still_read_the_whole_history(trips):
    """Only "Where the money came from" splits. This ticket moves no other figure."""
    ctx = SF.record_context(trips)
    assert len(ctx["trips"]) == len(ROWS)
    assert ctx["share"].total == Decimal(WANT["whole_history_net"])


def test_the_day_is_read_in_the_instruments_zone_not_the_servers(client, engine):
    """23:50 to 00:10 IST is one date in UTC and two in IST; IST is the trader's day."""
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader).where(m.Trader.login_id == "fx")).one()
        stored = sess.scalars(select(m.Trip).where(m.Trip.trip_id == "t01")).one()
        sess.add(m.Trip(
            import_id=stored.import_id, trip_id="across-midnight", trading_day="2026-09-01",
            exchange=stored.exchange, symbol=stored.symbol, segment=stored.segment,
            direction=stored.direction,
            entry_ts=datetime.fromisoformat("2026-09-01T23:50:00+05:30"),
            exit_ts=datetime.fromisoformat("2026-09-02T00:10:00+05:30"),
            quantity=stored.quantity, entry_price=stored.entry_price,
            exit_price=stored.exit_price, gross=stored.gross, fees=stored.fees,
            net=stored.net, fees_available=False,
            risk_unit_source=stored.risk_unit_source,
        ))
        sess.commit()
        loaded, _ = loader.load_for(sess, trader)
    assert [t.trip_id for t in mx.held_past_day(loaded).trips] == ["across-midnight"]
