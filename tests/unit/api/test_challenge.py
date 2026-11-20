"""TICKET-1004: the challenge.

He picks 10 or 20 trading days and one to three of the rules he has set. It starts on the next
exchange trading day after he taps, never on a day already in a file. Every upload shows how
far he has got, counted from 922's check and never graded; a finished (or stopped) challenge
becomes a card he may share by a link he can take away again. Every trade and date here is
made up, and the expected counts are worked by hand in the comments.
"""
from __future__ import annotations

import importlib
import importlib.util
import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import select

from services.production.api.app import create_app
from services.production.db import models as m
from services.production.db.session import make_session
from services.production.mirror import metrics as mx
from services.production.rules import adherence as A
from services.shared.schemas import scope_v1 as s
from tests.helpers.no_claims import CLAIM_PATTERNS, NEVER_USED
from tests.helpers.upload import CSRF, sign_up

IST = ZoneInfo("Asia/Kolkata")
D = Decimal


def challenge():
    name = "services.production.rules.challenge"
    assert importlib.util.find_spec(name), "no services/production/rules/challenge.py"
    return importlib.import_module(name)


def at(day: str, hhmm: str) -> datetime:
    return datetime.fromisoformat(f"{day}T{hhmm}:00").replace(tzinfo=IST)


def trip(tid: str, day: str, hhmm: str, net: str) -> mx.Trip:
    entry = at(day, hhmm)
    return mx.Trip(trip_id=tid, symbol="WIDGET", trading_day=day, entry_ts=entry,
                   exit_ts=entry + timedelta(minutes=10), holding_seconds=600, net=D(net), lots=1,
                   risk_unit_source=s.RiskUnitSourceV1.PREMIUM_PAID, is_option=True)


# A made-up holiday: Wednesday 4 March 2026 is shut.
CLOSED = frozenset({date(2026, 3, 4)})
SET_AT = datetime(2026, 2, 27, 12, 0, tzinfo=UTC)  # both rules set before the challenge
MOST = A.Rule(1, "most_trades", 2, SET_AT, "2026-02-27", None, "At most 2 trades in a day")
DOWN = A.Rule(2, "day_down", 5, SET_AT, "2026-02-27", None, "Stop for the day once it is down ₹5,000")

# Ten trading days from Monday 2 March, the holiday skipped:
#   2, 3, 5, 6, 9, 10, 11, 12, 13, 16 March.
# His file runs to Friday 6 March:
#   2 Mar  one trade              -> kept
#   3 Mar  four trades; the 3rd and 4th break "at most 2"  -> broken (once, not twice)
#   5 Mar  no trades              -> no trades: nothing broken
#   6 Mar  two trades             -> kept
#   9 Mar on                      -> not in a file yet
# Day 4 of 10. At most 2 trades: kept on 3 of 4 days, broken on 3 March. Down Rs5,000: kept on
# 4 of 4. Every day so far: broken on 1 of 4 days.
RECORD = [
    trip("d1", "2026-03-02", "10:00", "100"),
    trip("e1", "2026-03-03", "09:30", "-200"), trip("e2", "2026-03-03", "10:30", "50"),
    trip("e3", "2026-03-03", "11:30", "-80"), trip("e4", "2026-03-03", "13:00", "40"),
    trip("f1", "2026-03-06", "09:45", "300"), trip("f2", "2026-03-06", "11:00", "-20"),
]
DAYS = [date(2026, 3, d) for d in (2, 3, 5, 6, 9, 10, 11, 12, 13, 16)]


# ---------- 1. starting: the next trading day, a holiday skipped ----------

def test_ten_trading_days_skip_the_holiday_and_the_weekend():
    assert challenge().trading_days(date(2026, 2, 27), 10, CLOSED) == DAYS


def test_it_starts_on_the_next_trading_day_never_one_already_in_a_file():
    c = challenge()
    # Tapped on Tuesday 3 March with a file through 3 March: Wednesday is shut, so Thursday.
    assert c.start_day(date(2026, 3, 3), date(2026, 3, 3), CLOSED) == date(2026, 3, 5)
    # A file that already reaches past today pushes the start past it.
    assert c.start_day(date(2026, 3, 2), date(2026, 3, 6), CLOSED) == date(2026, 3, 9)


def test_lengths_and_the_rule_limit():
    c = challenge()
    assert c.LENGTHS == (10, 20) and c.MAX_RULES == 3


# ---------- 3. progress: kept, broken, no trades, not in a file yet ----------

def progress():
    return challenge().progress(DAYS, [MOST, DOWN], RECORD, date(2026, 3, 6))


def test_each_day_is_kept_broken_no_trades_or_not_in_a_file_yet():
    p = progress()
    assert [(d.day.isoformat(), d.state) for d in p.days][:5] == [
        ("2026-03-02", "kept"), ("2026-03-03", "broken"), ("2026-03-05", "no-trades"),
        ("2026-03-06", "kept"), ("2026-03-09", "not-yet")]
    assert all(d.state == "not-yet" for d in p.days[4:])
    assert p.so_far == 4 and p.length == 10


def test_a_rule_broken_twice_in_a_day_is_one_broken_day_with_its_trades():
    most = next(r for r in progress().rules if r.rule.id == MOST.id)
    assert (most.kept_days, most.days) == (3, 4)
    assert most.broken_days == [date(2026, 3, 3)]
    assert most.broken_trades == ["e3", "e4"]
    down = next(r for r in progress().rules if r.rule.id == DOWN.id)
    assert (down.kept_days, down.days, down.broken_days) == (4, 4, [])


def test_the_status_line_is_counts_never_an_adjective():
    p = progress()
    assert p.status == "broken on 1 of 4 days"
    clean = challenge().progress(DAYS, [DOWN], RECORD, date(2026, 3, 6))
    assert clean.status == "kept on every day so far"


def test_it_finishes_when_the_files_cover_every_day():
    c = challenge()
    assert not progress().finished
    covered = c.progress(DAYS, [DOWN], RECORD, date(2026, 3, 16))
    assert covered.finished and covered.so_far == 10


def test_the_completion_card_holds_counts_and_the_rules_words_only():
    c = challenge()
    p = c.progress(DAYS, [MOST, DOWN], RECORD, date(2026, 3, 16))
    line = c.card_line(p, stopped=False)
    assert line == ("10 trading days · the rules you set: At most 2 trades in a day, "
                    "Stop for the day once it is down ₹5,000 · kept on 9 of 10 days")
    stopped = c.card_line(progress(), stopped=True)
    assert stopped.startswith("Stopped on day 4 of 10 · the rules you set:")


# ---------- through the app ----------

def signed_in(engine):
    client = sign_up(TestClient(create_app()), engine, "C-1", "challenger")
    client.post("/upload/demo", data={"csrf_token": CSRF.search(client.get("/upload").text).group(1)})
    return client


def token(client, path="/challenge"):
    found = CSRF.search(client.get(path).text)
    assert found, f"no form on {path}"
    return found.group(1)


def set_rule(client, factor="most_trades", value="2"):
    client.post("/rules/set", data={"factor": factor, "value": value, "csrf_token": token(client, f"/rules/set?factor={factor}")})


def rule_ids(engine) -> list[int]:
    with make_session(engine) as sess:
        return list(sess.scalars(select(m.RuleDeclaration.id)))


def start(client, engine, length="10"):
    ids = rule_ids(engine)
    return client.post("/challenge/start", data={"length": length, "rule": [str(i) for i in ids],
                                                 "csrf_token": token(client)}, follow_redirects=False)


def test_the_rules_page_offers_a_challenge(engine):
    client = signed_in(engine)
    assert 'href="/challenge"' in client.get("/rules").text
    page = client.get("/challenge").text
    assert "Start a challenge" in page and "10 trading days" in page and "20 trading days" in page


def test_starting_stores_one_challenge_and_a_second_is_refused(engine):
    client = signed_in(engine)
    set_rule(client)
    assert start(client, engine).status_code == 303
    with make_session(engine) as sess:
        rows = sess.scalars(select(m.Challenge)).all()
    assert len(rows) == 1 and rows[0].length == 10 and rows[0].share_token is None
    assert rows[0].start_day > "2026-08-31"  # the demo's file ends in August: never a day in it
    assert start(client, engine).status_code == 409


def test_four_rules_or_none_are_refused(engine):
    client = signed_in(engine)
    for f, v in (("most_trades", "2"), ("most_lots", "1"), ("last_hour", "15"), ("losses_in_a_row", "2")):
        set_rule(client, f, v)
    assert start(client, engine).status_code == 400
    assert client.post("/challenge/start", data={"length": "10", "csrf_token": token(client)}).status_code == 400


def test_the_home_card_pulls_him_back_only_when_a_day_is_waiting(engine, monkeypatch):
    assert importlib.util.find_spec("services.production.api.routes_challenge"), "no routes_challenge"
    routes_challenge = importlib.import_module("services.production.api.routes_challenge")
    client = signed_in(engine)
    set_rule(client)
    start(client, engine)
    with make_session(engine) as sess:
        first = date.fromisoformat(sess.scalars(select(m.Challenge.start_day)).one())
    monkeypatch.setattr(routes_challenge, "trader_today", lambda: first - timedelta(days=1))
    assert "is waiting" not in client.get("/").text
    monkeypatch.setattr(routes_challenge, "trader_today", lambda: first + timedelta(days=1))
    assert "Upload today's file. Day 1 of your challenge is waiting." in client.get("/").text


def test_stop_share_and_remove_the_link(engine):
    client = signed_in(engine)
    set_rule(client)
    start(client, engine)
    client.post("/challenge/stop", data={"csrf_token": token(client)})
    page = client.get("/challenge").text
    assert "Stopped on day 0 of 10" in page
    client.post("/challenge/share", data={"csrf_token": token(client)})
    with make_session(engine) as sess:
        row = sess.scalars(select(m.Challenge)).one()
    assert row.ended_how == "stopped" and row.share_token
    public = TestClient(create_app()).get(f"/c/{row.share_token}")
    assert public.status_code == 200
    text = re.sub(r"<[^>]+>", " ", public.text)
    assert "₹" not in text.replace("₹5,000", "") and "challenger" not in text
    client.post("/challenge/unshare", data={"csrf_token": token(client)})
    assert TestClient(create_app()).get(f"/c/{row.share_token}").status_code == 404


def test_deleting_him_removes_the_challenge_and_its_link(engine, tmp_path):
    from services.production.accounts import deletion
    from services.production.accounts.file_store import FileStore, generate_key
    client = signed_in(engine)
    set_rule(client)
    start(client, engine)
    client.post("/challenge/stop", data={"csrf_token": token(client)})
    client.post("/challenge/share", data={"csrf_token": token(client)})
    with make_session(engine) as sess:
        link = sess.scalars(select(m.Challenge.share_token)).one()
        trader = sess.scalars(select(m.Trader)).one()
        store = FileStore(tmp_path / "files", generate_key())
        deletion.delete_trader(sess, store, trader=trader)
        sess.commit()
        assert sess.scalars(select(m.Challenge)).all() == []
    assert TestClient(create_app()).get(f"/c/{link}").status_code == 404


def test_its_words_make_no_claim_and_use_no_never_used_word(engine):
    client = signed_in(engine)
    set_rule(client)
    start(client, engine)
    for path in ("/challenge", "/"):
        main = re.search(r"<main.*?</main>", client.get(path).text, re.DOTALL).group(0)
        text = re.sub(r"<[^>]+>", " ", main).lower()
        assert not [w for w in NEVER_USED if re.search(rf"\b{re.escape(w.lower())}\b", text)], path
        assert not [p for p, _why in CLAIM_PATTERNS if re.search(p, text, re.IGNORECASE)], path
    main = re.search(r"<main.*?</main>", client.get("/challenge").text, re.DOTALL).group(0)
    assert "<script" not in main
