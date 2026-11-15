"""The Journal as a month calendar; only the days worth asking about ask [TICKET-906].

Gate (FB-0164, FB-0165):
1. A month calendar replaces the catch-up list, with previous and next day.
2. New days and days worth a look ask straight away. Any other day asks
   "Do you remember this day?" first, and only then offers its questions.
3. "Worth a look" is defined in one place (days_worth_a_look), from the day's trades.
4. The calendar shows which days have been answered.
5. The Journal and its data are unchanged: this is how days are offered, not what a day is.

Rulings, 13 Nov 2026 (on the ticket): a day is new within 7 calendar days of TODAY (a
labelled, arbitrary constant); the calendar holds every day, one day one state one
destination; a period Journal is not on a day cell; Yes and No are stored with the day's
age; an answered day stops asking but stays on the calendar and writable; previous and
next go across trading days.

The history is test_journals_worth_writing's, worked by hand there. Today is pinned to
20 Feb 2025. Worth a look: 04, 05, 06, 07, 10 (five worst), 11 (run), 12 (busiest).
Not flagged: 03 (17 days old - asks first) and 13 (7 days old - new).
"""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select

from services.production.api.app import create_app
from services.production.db import models as m
from services.production.db.session import make_engine, make_session, run_migrations
from services.production.journal import prose
from services.shared.schemas import scope_v1 as s
from tests.unit.api import test_journals_worth_writing as w
from tests.unit.api.test_upload import CSRF, sign_up

REMEMBER = "Do you remember this day?"
FEB = ["2025-02-03", "2025-02-04", "2025-02-05", "2025-02-06", "2025-02-07",
       "2025-02-10", "2025-02-11", "2025-02-12", "2025-02-13"]
OLD_PLAIN = "2025-02-03"
NEW_PLAIN = "2025-02-13"
WORTH = "2025-02-11"
TODAY = date(2025, 2, 20)


@pytest.fixture(autouse=True)
def _today(monkeypatch):
    try:
        from services.production.journal import recency
    except ImportError:
        return
    monkeypatch.setattr(recency, "today", lambda: TODAY)


@pytest.fixture()
def engine(scope_environment):
    built = make_engine(os.environ["SCOPE_DB"])
    run_migrations(built)
    return built


@pytest.fixture()
def client(engine):
    signed_in = sign_up(TestClient(create_app()), engine, "WORTH", "worth")
    token = CSRF.search(signed_in.get("/upload").text).group(1)
    sent = signed_in.post("/upload", files={"file": ("t.csv", w.FILE.encode(), "text/csv")},
                          data={"csrf_token": token}, follow_redirects=False)
    assert sent.status_code == 303, sent.text
    return signed_in


def _ids(engine) -> dict[str, int]:
    return w._journal_ids(engine)


def _tag(html: str, attr: str, value: str) -> str | None:
    found = re.search(rf'<(?:a|span)\b[^>]*\b{attr}="{re.escape(value)}"[^>]*>', html)
    return found.group(0) if found else None


def _href(tag: str) -> str:
    return re.search(r'href="([^"]+)"', tag).group(1)


def _rel(html: str, rel: str) -> str | None:
    tag = re.search(rf'<a\b[^>]*\brel="{rel}"[^>]*>', html)
    return _href(tag.group(0)) if tag else None


def _token(engine, client) -> str:
    return CSRF.search(client.get(f"/journals/{_ids(engine)[WORTH]}").text).group(1)


def _remember(engine, client, journal_id: int, answer: str, token: str | None = "auto"):
    data = {"answer": answer}
    if token == "auto":
        data["csrf_token"] = _token(engine, client)
    elif token is not None:
        data["csrf_token"] = token
    return client.post(f"/journals/{journal_id}/remember", data=data, follow_redirects=False)


def _write_note(engine, client, day: str) -> int:
    journal_id = _ids(engine)[day]
    client.post(f"/journals/{journal_id}/field", data={
        "field": "note", "value": "Slow open.", "trip_id": "", "csrf_token": _token(engine, client),
    })
    return journal_id


def _remembered(engine) -> list[tuple]:
    with make_session(engine) as sess:
        rows = sess.scalars(select(m.JournalRememberAnswer).order_by(m.JournalRememberAnswer.id))
        return [(r.trading_day, r.answer, r.day_age_days, r.journal_id) for r in rows]


def _week_journal(engine) -> int:
    """A week Journal over 03-09 Feb, beside the day Journals (a trader's own setting)."""
    with make_session(engine) as sess:
        day = sess.get(m.Journal, _ids(engine)[OLD_PLAIN])
        week = m.Journal(trader_id=day.trader_id, import_id=day.import_id,
                         unit=s.JournalUnit.WEEK, period_start="2025-02-03",
                         period_end="2025-02-09", version_no=1, supersedes=None,
                         generated_at=datetime.now(UTC), trip_ids="[]", sections=day.sections)
        sess.add(week)
        sess.commit()
        return week.id


# ---------- The calendar (gate 1, 4) ----------


def test_the_calendar_replaces_the_list_and_opens_on_the_newest_month(client):
    html = client.get("/journals/catch-up").text
    assert 'class="calendar"' in html
    assert "February 2025" in w._readable(html)
    assert "journal-index__row" not in html, "no list of days on this page"


def test_the_week_starts_on_monday(client):
    assert "Mon Tue Wed Thu Fri Sat Sun" in w._readable(client.get("/journals/catch-up").text)


def test_every_day_with_a_journal_is_a_link_on_its_date(engine, client):
    html = client.get("/journals/catch-up").text
    ids = _ids(engine)
    for day in FEB:
        tag = _tag(html, "data-day", day)
        assert tag and tag.startswith("<a"), day
        assert _href(tag) == f"/journals/{ids[day]}", day


def test_a_date_with_no_journal_is_not_a_link(client):
    html = client.get("/journals/catch-up").text
    for day in ("2025-02-01", "2025-02-14", "2025-02-28"):
        tag = _tag(html, "data-day", day)
        assert tag and tag.startswith("<span"), day


@pytest.mark.parametrize("day", ["2025-02-04", "2025-02-10", "2025-02-11", "2025-02-12"])
def test_a_day_worth_a_look_is_marked_on_the_calendar(client, day):
    assert 'data-state="worth"' in _tag(client.get("/journals/catch-up").text, "data-day", day)


def test_a_plain_old_day_is_marked_ask_first(client):
    html = client.get("/journals/catch-up").text
    assert 'data-state="remember"' in _tag(html, "data-day", OLD_PLAIN)


def test_a_day_within_seven_days_of_today_is_marked_new(client):
    html = client.get("/journals/catch-up").text
    assert 'data-state="new"' in _tag(html, "data-day", NEW_PLAIN)


def test_the_calendar_marks_the_days_answered(engine, client):
    assert 'data-answered="yes"' not in client.get("/journals/catch-up").text
    _write_note(engine, client, OLD_PLAIN)
    html = client.get("/journals/catch-up").text
    assert 'data-answered="yes"' in _tag(html, "data-day", OLD_PLAIN)
    assert 'data-answered="yes"' not in _tag(html, "data-day", "2025-02-04")


def test_a_day_answered_no_stays_on_the_calendar(engine, client):
    journal_id = _ids(engine)[OLD_PLAIN]
    _remember(engine, client, journal_id, "no")
    tag = _tag(client.get("/journals/catch-up").text, "data-day", OLD_PLAIN)
    assert tag.startswith("<a") and _href(tag) == f"/journals/{journal_id}"
    assert 'data-answered="yes"' in tag


def test_a_month_can_be_asked_for_by_name(client):
    html = client.get("/journals/catch-up?month=2025-02").text
    assert "February 2025" in w._readable(html)


def test_with_one_month_of_journals_there_is_no_previous_or_next_month(client):
    html = client.get("/journals/catch-up").text
    assert _rel(html, "prev") is None and _rel(html, "next") is None


def test_a_month_that_is_not_a_month_is_not_found(client):
    assert client.get("/journals/catch-up?month=2025-13").status_code == 404


def test_a_week_journal_sits_in_its_own_strip_not_on_a_day(engine, client):
    day_id = _ids(engine)[OLD_PLAIN]
    week_id = _week_journal(engine)
    html = client.get("/journals/catch-up").text
    assert _href(_tag(html, "data-day", OLD_PLAIN)) == f"/journals/{day_id}"
    assert f'href="/journals/{week_id}"' in html, "the week is still reachable"
    assert not re.search(
        rf'<a\b(?=[^>]*href="/journals/{week_id}")(?=[^>]*data-day=)[^>]*>', html
    ), "a week is not a claim about one day"


# ---------- The month, on its own ----------


def test_the_month_grid_is_weeks_of_seven_from_monday():
    from services.production.journal import month_view as mv

    month = mv.month(["2025-02-03"], "2025-02")
    assert month.title == "February 2025"
    assert all(len(week) == 7 for week in month.weeks)
    assert month.weeks[0] == [None] * 5 + ["2025-02-01", "2025-02-02"]
    days = [d for week in month.weeks for d in week if d]
    assert (days[0], days[-1], len(days)) == ("2025-02-01", "2025-02-28", 28)


def test_previous_and_next_month_skip_to_the_nearest_month_with_a_journal():
    from services.production.journal import month_view as mv

    month = mv.month(["2024-11-04", "2025-02-03", "2025-05-05"], "2025-02")
    assert (month.prev, month.next) == ("2024-11", "2025-05")


def test_no_month_named_opens_the_newest():
    from services.production.journal import month_view as mv

    assert mv.month(["2024-11-04", "2025-02-03"], None).title == "February 2025"


def test_the_only_month_has_nothing_either_side():
    from services.production.journal import month_view as mv

    month = mv.month(["2025-02-03"], "2025-02")
    assert (month.prev, month.next) == (None, None)


def test_a_month_that_is_not_a_month_is_refused():
    from services.production.journal import month_view as mv

    with pytest.raises(ValueError):
        mv.month(["2025-02-03"], "2025-13")


# ---------- Which days ask (gate 2, 3) ----------


def test_which_days_ask_straight_away_is_decided_in_one_place():
    from services.production.api import days_worth_a_look as worth

    class Flagged:
        period_start = period_end = "2025-02-11"

    class Plain:
        period_start = period_end = "2025-02-03"

    class Week:
        period_start, period_end = "2025-02-03", "2025-02-09"

    flags = {"2025-02-11": [worth.Flag("Your longest losing run", "/mirror/fact/run")]}
    assert worth.offer(Flagged(), flags, new_days=set()) == "worth"
    assert worth.offer(Plain(), flags, new_days={"2025-02-03"}) == "new"
    assert worth.offer(Plain(), flags, new_days=set()) == "remember"
    assert worth.offer(Week(), flags, new_days={"2025-02-03"}) == "period"


def test_a_day_is_new_within_seven_calendar_days_of_today():
    from services.production.journal import constants as k
    from services.production.journal import recency

    assert k.NEW_DAY_WITHIN_DAYS == 7
    assert "arbitrary" in k.ARGUMENTS["NEW_DAY_WITHIN_DAYS"].lower()
    assert recency.new_days(["2025-02-12", "2025-02-13", "2025-02-20"], TODAY) == {
        "2025-02-13", "2025-02-20"}
    assert recency.day_age("2025-02-03", TODAY) == 17


def test_a_day_worth_a_look_asks_straight_away(engine, client):
    html = client.get(f"/journals/{_ids(engine)[WORTH]}").text
    assert REMEMBER not in w._readable(html)
    assert 'name="rationale"' in html and 'name="value"' in html


def test_a_new_day_asks_straight_away(engine, client):
    html = client.get(f"/journals/{_ids(engine)[NEW_PLAIN]}").text
    assert REMEMBER not in w._readable(html)
    assert 'name="rationale"' in html and 'name="value"' in html


def test_a_plain_old_day_asks_if_he_remembers_first(engine, client):
    html = client.get(f"/journals/{_ids(engine)[OLD_PLAIN]}").text
    assert REMEMBER in w._readable(html)
    assert 'name="rationale"' not in html, "no trade questions before he answers"
    assert 'name="value"' not in html, "nor the note's question"


def test_the_day_itself_is_still_there_before_he_answers(engine, client):
    journal_id = _ids(engine)[OLD_PLAIN]
    with make_session(engine) as sess:
        written = prose.render(json.loads(sess.get(m.Journal, journal_id).sections))
    assert written.split(".")[0] in client.get(f"/journals/{journal_id}").text


def test_the_question_is_a_form_with_yes_and_no(engine, client):
    journal_id = _ids(engine)[OLD_PLAIN]
    html = client.get(f"/journals/{journal_id}").text
    assert f'action="/journals/{journal_id}/remember"' in html
    assert re.search(r'name="answer"\s+value="yes"', html) and re.search(r'name="answer"\s+value="no"', html)
    assert "?remember=" not in html, "a link anyone could send must not store an answer"


def test_yes_is_kept_with_the_days_age_and_opens_the_questions(engine, client):
    journal_id = _ids(engine)[OLD_PLAIN]
    sent = _remember(engine, client, journal_id, "yes")
    assert sent.status_code == 303 and sent.headers["location"].endswith(f"/journals/{journal_id}")
    assert _remembered(engine) == [(OLD_PLAIN, "yes", 17, journal_id)]
    html = client.get(f"/journals/{journal_id}").text
    assert REMEMBER not in w._readable(html)
    assert 'name="rationale"' in html and 'name="value"' in html


def test_no_is_kept_goes_back_to_the_month_and_the_day_stays_writable(engine, client):
    journal_id = _ids(engine)[OLD_PLAIN]
    sent = _remember(engine, client, journal_id, "no")
    assert sent.status_code == 303
    assert sent.headers["location"].endswith("/journals/catch-up?month=2025-02")
    assert _remembered(engine) == [(OLD_PLAIN, "no", 17, journal_id)]
    html = client.get(f"/journals/{journal_id}").text
    assert REMEMBER not in w._readable(html), "it stops asking"
    assert 'name="rationale"' in html and 'name="value"' in html, "and can still be written"


def test_the_first_answer_stands(engine, client):
    journal_id = _ids(engine)[OLD_PLAIN]
    _remember(engine, client, journal_id, "yes")
    _remember(engine, client, journal_id, "no")
    assert _remembered(engine) == [(OLD_PLAIN, "yes", 17, journal_id)]


def test_opening_a_day_stores_no_answer(engine, client):
    client.get(f"/journals/{_ids(engine)[OLD_PLAIN]}")
    assert _remembered(engine) == []


def test_an_answer_without_the_form_token_is_refused(engine, client):
    sent = _remember(engine, client, _ids(engine)[OLD_PLAIN], "yes", token=None)
    assert sent.status_code == 403 and _remembered(engine) == []


def test_only_yes_or_no_is_an_answer(engine, client):
    sent = _remember(engine, client, _ids(engine)[OLD_PLAIN], "maybe")
    assert sent.status_code == 400 and _remembered(engine) == []


def test_a_week_journal_is_never_asked_if_he_remembers_the_day(engine, client):
    sent = _remember(engine, client, _week_journal(engine), "yes")
    assert sent.status_code == 400 and _remembered(engine) == []


def test_a_day_he_has_written_on_does_not_ask_again(engine, client):
    journal_id = _write_note(engine, client, OLD_PLAIN)
    html = client.get(f"/journals/{journal_id}").text
    assert REMEMBER not in w._readable(html)
    assert "Slow open." in html


# ---------- Previous and next trading day (gate 1) ----------


def test_a_day_links_the_trading_day_before_and_after(engine, client):
    ids = _ids(engine)
    html = client.get(f"/journals/{ids['2025-02-07']}").text
    assert (_rel(html, "prev"), _rel(html, "next")) == (
        f"/journals/{ids['2025-02-06']}", f"/journals/{ids['2025-02-10']}"), "over the weekend"


def test_the_first_and_last_days_link_one_way(engine, client):
    ids = _ids(engine)
    assert _rel(client.get(f"/journals/{ids['2025-02-03']}").text, "prev") is None
    assert _rel(client.get(f"/journals/{ids['2025-02-13']}").text, "next") is None


# ---------- What a day is stays (gate 5) ----------


def test_the_journal_and_its_answers_keep_their_shape(engine):
    shape = {t: {c["name"] for c in inspect(engine).get_columns(t)}
             for t in ("journal", "journal_field_entry")}
    assert shape == {
        "journal": {"id", "trader_id", "import_id", "unit", "period_start", "period_end",
                    "version_no", "supersedes", "generated_at", "opened_at", "trip_ids",
                    "sections"},
        "journal_field_entry": {"id", "journal_id", "trip_id", "field", "value", "entered_at",
                                "capture_phase", "previous_entry_id"},
    }


def test_answers_are_counted_not_typed(engine):
    """No typed word: consent v1 stays as it is."""
    columns = {c["name"]: str(c["type"]) for c in inspect(engine).get_columns("journal_remember_answer")}
    assert set(columns) == {"id", "trader_id", "journal_id", "trading_day", "answer",
                            "day_age_days", "answered_at"}
    assert "TEXT" not in columns["answer"].upper()
    with make_session(engine) as sess:
        assert sess.scalar(select(func.count()).select_from(m.JournalRememberAnswer)) == 0