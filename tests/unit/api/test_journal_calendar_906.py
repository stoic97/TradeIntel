"""The Journal as a month calendar; only the days worth asking about ask [TICKET-906].

Gate (FB-0164, FB-0165):
1. A month calendar replaces the catch-up list, with previous and next day.
2. New days and days worth a look ask straight away. Any other day asks
   "Do you remember this day?" first, and only then offers its questions.
3. "Worth a look" is defined in one place (days_worth_a_look), from the day's trades.
4. The calendar shows which days have been answered.
5. The Journal and its data are unchanged: this is how days are offered, not what a day is.

The history is test_journals_worth_writing's, worked by hand there. Worth a look:
04, 05, 06, 07, 10 (five worst), 11 (run), 12 (busiest). Not flagged: 03 and 13.
03 Feb is eleven days before the file's last day, so it is not new under any reading
of "new": it is the day that asks first. Which days are new waits for a ruling.
"""

from __future__ import annotations

import json
import os
import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select

from services.production.api.app import create_app
from services.production.db import models as m
from services.production.db.session import make_engine, make_session, run_migrations
from services.production.journal import prose
from tests.unit.api import test_journals_worth_writing as w
from tests.unit.api.test_upload import CSRF, sign_up

REMEMBER = "Do you remember this day?"
FEB = ["2025-02-03", "2025-02-04", "2025-02-05", "2025-02-06", "2025-02-07",
       "2025-02-10", "2025-02-11", "2025-02-12", "2025-02-13"]
OLD_PLAIN = "2025-02-03"
WORTH = "2025-02-11"


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


def _answer(engine, client, day: str) -> int:
    journal_id = _ids(engine)[day]
    html = client.get(f"/journals/{journal_id}?remember=yes").text
    client.post(f"/journals/{journal_id}/field", data={
        "field": "note", "value": "Slow open.", "trip_id": "",
        "csrf_token": CSRF.search(html).group(1),
    })
    return journal_id


def _counts(engine) -> tuple[int, int]:
    with make_session(engine) as sess:
        return tuple(sess.scalar(select(func.count()).select_from(t))
                     for t in (m.Journal, m.JournalFieldEntry))


# ---------- The calendar (gate 1, 4) ----------


def test_the_calendar_replaces_the_list_and_opens_on_the_newest_month(client):
    html = client.get("/journals/catch-up").text
    assert 'class="calendar"' in html
    assert "February 2025" in w._readable(html)
    assert "journal-index" not in html, "the list is gone from this page"


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


def test_the_calendar_marks_the_days_answered(engine, client):
    assert 'data-answered="yes"' not in client.get("/journals/catch-up").text
    _answer(engine, client, OLD_PLAIN)
    html = client.get("/journals/catch-up").text
    assert 'data-answered="yes"' in _tag(html, "data-day", OLD_PLAIN)
    assert 'data-answered="yes"' not in _tag(html, "data-day", "2025-02-04")


def test_a_month_can_be_asked_for_by_name(client):
    html = client.get("/journals/catch-up?month=2025-02").text
    assert "February 2025" in w._readable(html)


def test_with_one_month_of_journals_there_is_no_previous_or_next_month(client):
    html = client.get("/journals/catch-up").text
    assert _rel(html, "prev") is None and _rel(html, "next") is None


def test_a_month_that_is_not_a_month_is_not_found(client):
    assert client.get("/journals/catch-up?month=2025-13").status_code == 404


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

    flags = {"2025-02-11": [worth.Flag("Your longest losing run", "/mirror/fact/run")]}
    assert worth.offer(Flagged(), flags, new_days=set()) == "worth"
    assert worth.offer(Plain(), flags, new_days={"2025-02-03"}) == "new"
    assert worth.offer(Plain(), flags, new_days=set()) == "remember"


def test_a_day_worth_a_look_asks_straight_away(engine, client):
    html = client.get(f"/journals/{_ids(engine)[WORTH]}").text
    assert REMEMBER not in w._readable(html)
    assert 'name="rationale"' in html and 'name="value"' in html


def test_a_plain_old_day_asks_if_he_remembers_first(engine, client):
    html = client.get(f"/journals/{_ids(engine)[OLD_PLAIN]}").text
    assert REMEMBER in w._readable(html)
    assert 'name="rationale"' not in html, "no trade questions before he says yes"
    assert 'name="value"' not in html, "nor the note's question"


def test_the_day_itself_is_still_there_before_he_answers(engine, client):
    journal_id = _ids(engine)[OLD_PLAIN]
    with make_session(engine) as sess:
        written = prose.render(json.loads(sess.get(m.Journal, journal_id).sections))
    assert written.split(".")[0] in client.get(f"/journals/{journal_id}").text


def test_yes_offers_the_questions_and_no_goes_back_to_the_month(engine, client):
    journal_id = _ids(engine)[OLD_PLAIN]
    html = client.get(f"/journals/{journal_id}").text
    assert f'href="/journals/{journal_id}?remember=yes"' in html
    assert 'href="/journals/catch-up?month=2025-02"' in html
    said_yes = client.get(f"/journals/{journal_id}?remember=yes").text
    assert REMEMBER not in w._readable(said_yes)
    assert 'name="rationale"' in said_yes and 'name="value"' in said_yes


def test_a_day_he_has_answered_does_not_ask_again(engine, client):
    journal_id = _answer(engine, client, OLD_PLAIN)
    html = client.get(f"/journals/{journal_id}").text
    assert REMEMBER not in w._readable(html)
    assert "Slow open." in html


# ---------- Previous and next day (gate 1) ----------


def test_a_day_links_the_day_before_and_the_day_after(engine, client):
    ids = _ids(engine)
    html = client.get(f"/journals/{ids['2025-02-05']}").text
    assert (_rel(html, "prev"), _rel(html, "next")) == (
        f"/journals/{ids['2025-02-04']}", f"/journals/{ids['2025-02-06']}")


def test_the_first_and_last_days_link_one_way(engine, client):
    ids = _ids(engine)
    assert _rel(client.get(f"/journals/{ids['2025-02-03']}").text, "prev") is None
    assert _rel(client.get(f"/journals/{ids['2025-02-13']}").text, "next") is None


# ---------- What a day is stays (gate 5) ----------


def test_saying_yes_stores_nothing(engine, client):
    journal_id = _ids(engine)[OLD_PLAIN]
    client.get(f"/journals/{journal_id}")
    before = _counts(engine)
    client.get(f"/journals/{journal_id}?remember=yes")
    assert _counts(engine) == before


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