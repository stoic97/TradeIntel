"""TICKET-915 gate 5, as Pawan ruled it on 17 Nov 2026 (Q3 a): the day's rupees - each trade
card and the day's net - stay hidden until he answers one of the day's questions or skips.
Skip shows them for that visit only and stores nothing. And his answers are never counted or
split by result, anywhere (Q2's condition). Day 2026-09-07 holds eight trades."""

from __future__ import annotations

import html
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import inspect, select, text

from services.production.db import models as m
from services.production.db.session import make_session
from services.production.journal import remember
from tests.helpers.journals import CSRF, journals_client, journals_engine

DAY = "2026-09-07"
RUPEE = "\u20b9"
KEY = re.compile(r'name="key" value="([^"]+)"')


@pytest.fixture()
def engine():
    return journals_engine()


@pytest.fixture()
def client(engine):
    return journals_client(engine)


def _day(engine) -> int:
    with make_session(engine) as sess:
        journal = sess.scalars(
            select(m.Journal).where(m.Journal.period_start == DAY, m.Journal.period_end == DAY)
            .order_by(m.Journal.version_no.desc())).first()
        trader = sess.get(m.Trader, journal.trader_id)
        remember.record(sess, trader=trader, journal=journal, answer=remember.YES, on=datetime.now(ZoneInfo("Asia/Kolkata")).date())
        sess.commit()
        return journal.id


def _rows(engine) -> list:
    if not inspect(engine).has_table("journal_day_answer"):
        return []
    with engine.connect() as conn:
        return list(conn.execute(text("select * from journal_day_answer")))


def _read(client, jid: int, query: str = ""):
    """The page raw, and as read - without the price question, whose rupee figure is its own."""
    raw = client.get(f"/journals/{jid}{query}").text
    return raw, html.unescape(re.sub(r'<form[^>]*id="one-question".*?</form>', "", raw, flags=re.DOTALL))


def _answer(client, raw: str, jid: int, key: str, answer: str):
    return client.post(f"/journals/{jid}/day-answer",
                       data={"key": key, "answer": answer,
                             "csrf_token": CSRF.search(raw).group(1)},
                       follow_redirects=False)


def test_the_days_rupees_wait_for_an_answer_or_a_skip(engine, client):
    jid = _day(engine)
    skipped_raw, skipped = _read(client, jid, "?skip=1")
    assert RUPEE in skipped, "control: the skipped page shows the day's rupees"
    assert "closed down" in skipped, "control: and how the trades closed"
    assert KEY.search(skipped_raw), "the questions are still there after a skip"
    raw, hidden = _read(client, jid)
    assert KEY.search(raw), "the day's questions are on the page"
    assert RUPEE not in hidden
    assert "closed down" not in hidden and " Net " not in hidden
    assert f'href="/journals/{jid}?skip=1"' in raw


def test_skip_shows_the_figures_for_that_visit_only_and_stores_nothing(engine, client):
    jid = _day(engine)
    _, shown = _read(client, jid, "?skip=1")
    assert RUPEE in shown
    assert _rows(engine) == []
    with make_session(engine) as sess:
        assert sess.scalars(select(m.ReportFeedback.id)).all() == []
    _, again = _read(client, jid)
    assert RUPEE not in again


@pytest.mark.parametrize("answer", ["yes", "no", "wrong"])
def test_an_answer_reveals_the_figures_and_they_stay(engine, client, answer):
    jid = _day(engine)
    raw, hidden = _read(client, jid)
    keys = KEY.findall(raw)
    assert keys, "no day question on the page"
    assert RUPEE not in hidden
    assert _answer(client, raw, jid, keys[0], answer).status_code == 303
    _, now = _read(client, jid)
    assert RUPEE in now
    _, later = _read(client, jid)
    assert RUPEE in later


ALLOWED = {
    "services/production/db/models.py",
    "services/production/journal/day_answers.py",
    "services/production/api/routes_journal.py",
    "services/production/accounts/deletion.py",
}


def test_nothing_else_reads_his_day_answers():
    """Q2's condition: no count or split of these answers by result, admin included."""
    seen = set()
    for path in Path("services/production").rglob("*"):
        if path.suffix in {".py", ".html"} and re.search(
                r"JournalDayAnswer|journal_day_answer", path.read_text(encoding="utf-8")):
            seen.add(path.as_posix())
    assert seen, "control: the guard found nothing to guard"
    assert seen <= ALLOWED, sorted(seen - ALLOWED)


def test_the_answers_module_knows_nothing_of_results():
    src = Path("services/production/journal/day_answers.py")
    assert src.exists()
    body = src.read_text(encoding="utf-8")
    for name in ("Trip", "net", "gross", "mirror", "metrics"):
        assert not re.search(rf"\b{name}\b", body), name