"""TICKET-915 gates 3 and 4 through the routes: his answers are kept with the words he saw,
when, and against which day; read back on one list that never shows a result; "Did you know
this?" is what a day question asks; "This looks wrong" still reports the day.
Day 2026-09-07 holds eight trades in the synthetic contract fixture."""

from __future__ import annotations

import html
import re
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select, text

from services.production.api.app import create_app
from services.production.db import models as m
from services.production.db.session import make_session
from services.production.journal import remember
from tests.helpers.journals import CSRF, journals_client, journals_engine

DAY = "2026-09-07"
KNEW = "Did you know this?"


@pytest.fixture()
def engine():
    return journals_engine()


@pytest.fixture()
def client(engine):
    return journals_client(engine)


def _day(engine, day: str = DAY) -> int:
    """The day's Journal, past TICKET-906's "Do you remember this day?" step."""
    with make_session(engine) as sess:
        journal = sess.scalars(
            select(m.Journal).where(m.Journal.period_start == day, m.Journal.period_end == day)
            .order_by(m.Journal.version_no.desc())).first()
        trader = sess.get(m.Trader, journal.trader_id)
        remember.record(sess, trader=trader, journal=journal, answer=remember.YES, on=date.today())
        sess.commit()
        return journal.id


def _keys(page: str) -> list[str]:
    return re.findall(r'name="key" value="([^"]+)"', page)


def _answer(client, journal_id: int, key: str, answer: str):
    csrf = CSRF.search(client.get(f"/journals/{journal_id}").text).group(1)
    return client.post(f"/journals/{journal_id}/day-answer",
                       data={"key": key, "answer": answer, "csrf_token": csrf},
                       follow_redirects=False)


def _rows(engine) -> list[dict]:
    if not inspect(engine).has_table("journal_day_answer"):
        return []
    with engine.connect() as conn:
        return [dict(r._mapping) for r in
                conn.execute(text("select * from journal_day_answer order by id"))]


def test_the_answers_have_their_own_table(engine):
    assert inspect(engine).has_table("journal_day_answer")


def test_the_day_asks_up_to_three_questions_and_did_you_know_this(engine, client):
    page = client.get(f"/journals/{_day(engine)}").text
    assert 1 <= len(_keys(page)) <= 3
    assert KNEW in page


def test_an_answer_is_kept_with_the_words_he_saw_and_his_day(engine, client):
    jid = _day(engine)
    page = html.unescape(client.get(f"/journals/{jid}").text)
    keys = _keys(page)
    assert keys, "no day question on the page"
    assert _answer(client, jid, keys[0], "yes").status_code == 303
    rows = _rows(engine)
    assert len(rows) == 1
    row = rows[0]
    assert (row["trading_day"], row["journal_id"], row["question_key"], row["answer"]) == (
        DAY, jid, keys[0], "yes")
    assert row["question_text"] and row["question_text"] in page
    assert row["answered_at"]


def test_a_changed_answer_is_kept_beside_the_first(engine, client):
    jid = _day(engine)
    keys = _keys(client.get(f"/journals/{jid}").text)
    assert keys, "no day question on the page"
    _answer(client, jid, keys[0], "yes")
    _answer(client, jid, keys[0], "no")
    assert [r["answer"] for r in _rows(engine)] == ["yes", "no"]


def test_his_answers_read_back_with_their_day_and_never_a_result(engine, client):
    jid = _day(engine)
    journal_page = html.unescape(client.get(f"/journals/{jid}?skip=1").text)
    assert "\u20b9" in journal_page, "control: the Journal itself shows money"
    keys = _keys(journal_page)
    assert keys, "no day question on the page"
    _answer(client, jid, keys[0], "no")
    r = client.get("/journals/answers")
    assert r.status_code == 200
    said = html.unescape(r.text)
    rows = _rows(engine)
    assert rows, "nothing was kept"
    assert rows[0]["question_text"] in said
    assert f'href="/journals/{jid}"' in r.text
    assert "\u20b9" not in said


def test_this_looks_wrong_still_reports_the_day(engine, client):
    jid = _day(engine)
    keys = _keys(client.get(f"/journals/{jid}").text)
    assert keys, "no day question on the page"
    _answer(client, jid, keys[0], "wrong")
    with make_session(engine) as sess:
        flagged = sess.scalars(select(m.ReportFeedback.trading_day)
                               .where(m.ReportFeedback.answer == "wrong")).all()
    assert DAY in flagged


def test_an_answer_outside_the_set_or_a_question_not_asked_is_refused(engine, client):
    jid = _day(engine)
    keys = _keys(client.get(f"/journals/{jid}").text)
    assert keys, "no day question on the page"
    assert _answer(client, jid, keys[0], "maybe").status_code == 400
    assert _answer(client, jid, "not-a-question", "yes").status_code == 400
    assert _rows(engine) == []


def test_without_the_form_token_nothing_is_kept(engine, client):
    jid = _day(engine)
    keys = _keys(client.get(f"/journals/{jid}").text)
    assert keys, "no day question on the page"
    r = client.post(f"/journals/{jid}/day-answer", data={"key": keys[0], "answer": "yes"},
                    follow_redirects=False)
    assert r.status_code == 403
    assert _rows(engine) == []


def test_the_answers_page_needs_him_signed_in(engine):
    r = TestClient(create_app()).get("/journals/answers", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"