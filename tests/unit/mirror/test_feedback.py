"""B4: "Does this match your trading?" under chapters 1-3 (handoff 9; kit screen 17).

One answer per chapter per trader, never changed; after Wrong, one optional reason
from three. htmx swaps the row in place; a plain form post comes back to the chapter.
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy import select

from services.production.db import models as m
from services.production.db.session import make_session

TOKEN = re.compile(r'name="csrf_token" value="([^"]+)"')
HTMX = {"HX-Request": "true"}


def token(client) -> str:
    """The session's token, read off a chapter whose feedback form is still showing.

    A chapter that has been answered shows "Recorded" and no form, and chapter 4 has
    none at all; every test here leaves at least one of chapters 1-3 unanswered.
    """
    for n in (1, 2, 3):
        found = TOKEN.search(client.get(f"/mirror/chapter/{n}").text)
        if found:
            return found.group(1)
    raise AssertionError("no chapter still asks, so there is no form to take a token from")


def answer(client, n: int, headers=HTMX, **data):
    return client.post(
        f"/mirror/chapter/{n}/feedback",
        data={"csrf_token": token(client), **data},
        headers=headers,
        follow_redirects=False,
    )


def rows(engine):
    with make_session(engine) as sess:
        return (
            [(f.chapter, f.answer) for f in sess.scalars(select(m.ChapterFeedback))],
            [r.reason for r in sess.scalars(select(m.ChapterFeedbackReason))],
        )


@pytest.mark.parametrize("n", [1, 2, 3])
def test_chapters_one_to_three_ask(client, n):
    page = client.get(f"/mirror/chapter/{n}").text
    assert '<h2 class="feedback__question">Does this match your trading?</h2>' in page
    for value, label in (("accurate", "Accurate"), ("not_sure", "Not sure"), ("wrong", "Wrong")):
        assert f'name="answer" value="{value}">{label}</button>' in page
    assert f'hx-post="/mirror/chapter/{n}/feedback"' in page


def test_the_honest_close_asks_nothing(client):
    assert "Does this match your trading?" not in client.get("/mirror/chapter/4").text
    assert answer(client, 4, answer="accurate").status_code == 404


def test_accurate_is_recorded_once_and_thanked(client, engine):
    r = answer(client, 1, answer="accurate")
    assert r.status_code == 200
    assert '<p class="feedback__done" role="status">Recorded. Thank you.</p>' in r.text
    assert "<html" not in r.text  # the row alone, for htmx to swap in
    assert rows(engine) == ([(1, "accurate")], [])
    assert "Recorded. Thank you." in client.get("/mirror/chapter/1").text


def test_a_second_answer_is_not_a_second_vote(client, engine):
    answer(client, 2, answer="not_sure")
    r = client.post(
        "/mirror/chapter/2/feedback",
        data={"csrf_token": token(client), "answer": "wrong"},
        headers=HTMX,
    )
    assert "Recorded. Thank you." in r.text
    assert rows(engine) == ([(2, "not_sure")], [])


def test_wrong_asks_which_then_takes_one_reason(client, engine):
    r = answer(client, 3, answer="wrong")
    assert '<span class="btn btn--selected">Wrong</span>' in r.text
    assert "If you like, tell us which:" in r.text
    for value, label in (
        ("wrong_facts", "Wrong facts"),
        ("wrong_reading", "Right facts, wrong reading"),
        ("already_changed", "I&#39;ve already changed this"),
    ):
        assert f'name="reason" value="{value}">{label}</button>' in r.text
    assert "Recorded. Thank you." in answer(client, 3, reason="wrong_reading").text
    answer(client, 3, reason="already_changed")  # a second reason changes nothing
    assert rows(engine) == ([(3, "wrong")], ["wrong_reading"])


def test_a_reason_without_a_wrong_is_not_kept(client, engine):
    answer(client, 1, answer="accurate")
    answer(client, 1, reason="wrong_facts")
    assert rows(engine) == ([(1, "accurate")], [])


def test_without_javascript_the_form_comes_back_to_the_chapter(client, engine):
    r = answer(client, 1, headers={}, answer="accurate")
    assert (r.status_code, r.headers["location"]) == (303, "/mirror/chapter/1#feedback")
    assert rows(engine) == ([(1, "accurate")], [])


@pytest.mark.parametrize("data", [{"answer": "maybe"}, {"reason": "bored"}, {}])
def test_anything_but_the_choices_is_refused(client, engine, data):
    assert answer(client, 1, **data).status_code == 400
    assert rows(engine) == ([], [])


def test_a_post_without_its_token_is_refused(client, engine):
    r = client.post("/mirror/chapter/1/feedback", data={"answer": "accurate"}, headers=HTMX)
    assert r.status_code == 403
    assert rows(engine) == ([], [])


def test_the_answer_is_kept_against_the_record_he_was_looking_at(client, engine):
    answer(client, 1, answer="accurate")
    with make_session(engine) as sess:
        fb = sess.scalars(select(m.ChapterFeedback)).one()
        imp = sess.scalars(select(m.Import)).one()
        assert fb.import_id == imp.id
