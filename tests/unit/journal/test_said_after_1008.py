"""TICKET-1008: three one-tap questions per trade, counted like the stop question.

"How did it end?", "Did it have a target?" and "Planned before the session?": fixed answers,
one tap each on the journal's trade card, stored as journal field entries (insert-only, the
capture phase derived, never chosen), and counted the way planned_sl is: counts by answer, made
money N of 100 once 30 trades carry an answer, how many trades were answered at all, and "said
after the trade" beside every count. "Don't remember" is an answer, and out of every rate.

These are trade fields. They are not 915's day questions, whose answers nothing counts.
Every trade here is made up; the expected counts are worked by hand in the comments.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from services.production.db import models as m
from services.production.db.session import make_session
from services.production.journal import fields as fl
from services.production.journal import sections as sec
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s
from tests.helpers.journals import journals_client, journals_engine

D = Decimal
ROOT = Path(__file__).resolve().parents[3]


def need(module, name: str):
    """What the ticket adds, as an assertion rather than an AttributeError."""
    assert hasattr(module, name), f"{module.__name__} has no {name}"
    return getattr(module, name)


@pytest.fixture()
def engine():
    return journals_engine()


@pytest.fixture()
def client(engine):
    return journals_client(engine)


# ---------- 1. three per-trade fields, one tap each ----------

def test_the_three_fields_are_per_trade_with_closed_answers():
    assert {"exit_how", "target", "planned"} <= fl.PER_TRIP_FIELDS
    choices = need(fl, "CHOICES")
    assert [label for _, label in choices["exit_how"]] == [
        "At my stop", "At my target", "I closed it", "Held to expiry", "Don't remember"]
    assert [label for _, label in choices["target"]] == ["A price I set", "No target", "Don't remember"]
    assert [label for _, label in choices["planned"]] == ["Yes", "No", "Don't remember"]
    questions = need(fl, "QUESTIONS")
    assert questions == {"exit_how": "How did it end?", "target": "Did it have a target?",
                         "planned": "Planned before the session?"}


def _day(engine) -> m.Journal:
    with make_session(engine) as sess:
        return sess.scalars(select(m.Journal).where(m.Journal.period_start == "2026-09-01")).first()


def test_an_answer_is_saved_and_a_changed_one_is_a_new_row(engine, client):
    assert {"exit_how", "target", "planned"} <= fl.KNOWN_FIELDS
    with make_session(engine) as sess:
        journal = sess.scalars(select(m.Journal).where(m.Journal.period_start == "2026-09-01")).first()
        first = fl.record(sess, journal=journal, field="exit_how", value="closed", trip_id="t02",
                          trip_entry=datetime(2026, 9, 1, 9, 30, tzinfo=UTC),
                          trip_exit=datetime(2026, 9, 1, 10, 0, tzinfo=UTC))
        second = fl.record(sess, journal=journal, field="exit_how", value="stop", trip_id="t02",
                           trip_entry=datetime(2026, 9, 1, 9, 30, tzinfo=UTC),
                           trip_exit=datetime(2026, 9, 1, 10, 0, tzinfo=UTC))
        sess.commit()
        assert second.previous_entry_id == first.id
        assert first.capture_phase == second.capture_phase == s.CapturePhase.AFTER_CLOSE
        assert fl.current(sess, journal=journal, field="exit_how", trip_id="t02").value == "stop"


def test_an_answer_off_the_list_is_refused(engine, client):
    with make_session(engine) as sess:
        journal = sess.scalars(select(m.Journal).where(m.Journal.period_start == "2026-09-01")).first()
        with pytest.raises(fl.UnknownField):
            fl.record(sess, journal=journal, field="planned", value="maybe", trip_id="t01")


def test_one_tap_on_the_card_saves_the_answer(engine, client):
    journal = _day(engine)
    page = client.get(f"/journals/{journal.id}").text
    assert "How did it end?" in page and "Planned before the session?" in page
    assert re.search(r'<button[^>]*name="exit_how"[^>]*value="closed"', page)
    token = re.search(r'name="csrf_token"\s+value="([^"]+)"', page).group(1)
    r = client.post(f"/journals/{journal.id}/field",
                    data={"csrf_token": token, "trip_id": "t02", "exit_how": "closed"},
                    follow_redirects=False)
    assert r.status_code == 303
    with make_session(engine) as sess:
        j = sess.get(m.Journal, journal.id)
        assert fl.current(sess, journal=j, field="exit_how", trip_id="t02").value == "closed"
    page = client.get(f"/journals/{journal.id}").text
    assert re.search(r'name="exit_how"[^>]*value="closed"[^>]*aria-pressed="true"', page)


def test_the_card_carries_no_script(engine, client):
    page = client.get(f"/journals/{_day(engine).id}").text
    main = re.search(r"<main.*?</main>", page, re.DOTALL).group(0)
    assert "<script" not in main


# ---------- 2, 4. counted like planned_sl; "Don't remember" out of the rates ----------

def trip(tid: str, net: str) -> mx.Trip:
    at = datetime(2026, 9, 1, 4, 0, tzinfo=UTC)
    return mx.Trip(trip_id=tid, symbol="WIDGET", trading_day="2026-09-01", entry_ts=at,
                   exit_ts=at + timedelta(minutes=20), holding_seconds=1200, net=D(net), lots=1,
                   risk_unit_source=s.RiskUnitSourceV1.PREMIUM_PAID)


# Ten trades. Answers, worked by hand:
#   exit_how: closed on a1 (-10) a2 (-20) a3 (+30); stop on a4 (-40); dont_remember on a5 (+50)
#   -> answered 5 of 10; "I closed it: 3 trades, 2 of them losses"; "At my stop: 1 trade, 1 loss".
#   Every group is under 30, so every rate says too few.
TEN = [trip(f"a{i}", n) for i, n in enumerate(["-10", "-20", "30", "-40", "50", "60", "-70", "80", "90", "-5"], 1)]
ANSWERS = {"a1": {"exit_how": "closed"}, "a2": {"exit_how": "closed"}, "a3": {"exit_how": "closed"},
           "a4": {"exit_how": "stop"}, "a5": {"exit_how": "dont_remember"}}


def _row(counted, field, value):
    block = next(b for b in counted if b["field"] == field)
    return block, next(r for r in block["rows"] if r["value"] == value)


def test_counts_by_answer_and_how_many_were_answered():
    counted = need(sec, "said_after")(TEN, ANSWERS)
    block, closed = _row(counted, "exit_how", "closed")
    assert (block["answered"], block["of"]) == (5, 10)
    assert (closed["trades"], closed["losses"]) == (3, 2)
    _, stop = _row(counted, "exit_how", "stop")
    assert (stop["trades"], stop["losses"]) == (1, 1)
    assert closed["rate"] is None and stop["rate"] is None  # under 30: too few


def test_dont_remember_is_counted_and_never_rated():
    many = [trip(f"d{i}", "10") for i in range(40)]
    counted = need(sec, "said_after")(many, {t.trip_id: {"planned": "dont_remember"} for t in many})
    block, row = _row(counted, "planned", "dont_remember")
    assert block["answered"] == 40 and row["trades"] == 40
    assert row["rate"] is None


def test_a_rate_once_thirty_trades_carry_an_answer():
    # 30 trades not planned: 12 made money, 18 lost -> 40 of 100. 29 of them: too few.
    thirty = [trip(f"n{i}", "10" if i < 12 else "-5") for i in range(30)]
    answers = {t.trip_id: {"planned": "no"} for t in thirty}
    _, row = _row(need(sec, "said_after")(thirty, answers), "planned", "no")
    assert row["rate"] == D("40.0")
    answers.pop("n29")
    _, row = _row(need(sec, "said_after")(thirty, answers), "planned", "no")
    assert row["trades"] == 29 and row["rate"] is None


def test_the_journals_page_says_said_after_the_trade_beside_every_count(engine, client):
    journal = _day(engine)
    page = client.get(f"/journals/{journal.id}").text
    token = re.search(r'name="csrf_token"\s+value="([^"]+)"', page).group(1)
    for tid, value in (("t02", "closed"), ("t03", "closed"), ("t01", "dont_remember")):
        client.post(f"/journals/{journal.id}/field",
                    data={"csrf_token": token, "trip_id": tid, "exit_how": value})
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", client.get("/journals").text))
    assert "I closed it: 2 trades, 2 of them losses" in text
    assert "answered for 3 of 40 trades" in text
    count_lines = re.findall(r"[^.]*\d+ trades?, \d+ of them loss[^.]*", text)
    assert count_lines and all("said after the trade" in line for line in count_lines), count_lines


# ---------- 3. not 915's day questions ----------

def test_no_trade_field_reaches_the_day_questions():
    for path in (ROOT / "services/production/journal").glob("*.py"):
        if path.name in ("day_answers.py", "day_questions.py"):
            continue
        assert "day_answer" not in path.read_text(encoding="utf-8"), path.name


# ---------- 6. deletion ----------

def test_deleting_him_removes_the_new_answers(engine, client, tmp_path):
    assert {"exit_how", "target", "planned"} <= fl.KNOWN_FIELDS
    from services.production.accounts import deletion
    from services.production.accounts.file_store import FileStore, generate_key
    journal = _day(engine)
    with make_session(engine) as sess:
        j = sess.get(m.Journal, journal.id)
        for field, value in (("exit_how", "closed"), ("target", "price"), ("planned", "yes")):
            fl.record(sess, journal=j, field=field, value=value, trip_id="t01")
        trader = sess.get(m.Trader, j.trader_id)
        deletion.delete_trader(sess, FileStore(tmp_path / "files", generate_key()), trader=trader)
        sess.commit()
        left = sess.scalars(select(m.JournalFieldEntry).where(
            m.JournalFieldEntry.field.in_(("exit_how", "target", "planned")))).all()
        assert left == []
