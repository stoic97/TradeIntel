"""B6: the guess before the reveal, and the reveal (handoff 5, 7, 9; TR-009).

Through the app, with the 40-trade fixture trader signed in.
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy import select

from services.production.db import models as m
from services.production.db.session import make_session
from services.production.mirror import guess as GU

TOKEN = re.compile(r'name="csrf_token" value="([^"]+)"')


def guess(client, answer: str):
    token = TOKEN.search(client.get("/guess").text).group(1)
    return client.post(
        "/guess", data={"answer": answer, "csrf_token": token}, follow_redirects=False
    )


def stored(engine):
    with make_session(engine) as sess:
        return [(g.answer, g.labels_version) for g in sess.scalars(select(m.GuessAnswer))]


def test_the_guess_comes_before_the_reveal(client):
    r = client.get("/mirror/reveal", follow_redirects=False)
    assert (r.status_code, r.headers["location"]) == (303, "/guess")
    page = client.get("/guess").text
    assert page.count('class="guess__option"') == len(GU.LABELS)


def test_a_guess_is_kept_and_the_reveal_says_it(client, engine):
    r = guess(client, "option-3")
    assert (r.status_code, r.headers["location"]) == (303, "/mirror/reveal")
    assert stored(engine) == [("option-3", GU.LABELS_VERSION)]
    page = client.get("/mirror/reveal").text
    assert f"You guessed: {GU.LABELS['option-3']}." in page
    assert '<text class="reveal__figure" x="150" y="160" text-anchor="middle">96%</text>' in page


def test_i_dont_know_is_an_answer(client, engine):
    guess(client, "unknown")
    assert stored(engine) == [("unknown", GU.LABELS_VERSION)]
    assert "You guessed: I don&#39;t know." in client.get("/mirror/reveal").text


def test_one_guess_ever(client, engine):
    guess(client, "option-1")
    token = TOKEN.search(client.get("/upload").text).group(1)
    r = client.post(
        "/guess", data={"answer": "option-2", "csrf_token": token}, follow_redirects=False
    )
    assert r.status_code == 303
    assert stored(engine) == [("option-1", GU.LABELS_VERSION)]
    again = client.get("/guess", follow_redirects=False)
    assert (again.status_code, again.headers["location"]) == (303, "/mirror/reveal")


@pytest.mark.parametrize("answer", ["option-99", "", "maybe"])
def test_anything_but_a_label_is_refused(client, engine, answer):
    assert guess(client, answer).status_code == 400
    assert stored(engine) == []


def test_a_guess_without_its_token_is_refused(client, engine):
    r = client.post("/guess", data={"answer": "option-1"}, follow_redirects=False)
    assert r.status_code == 403 and stored(engine) == []


def test_until_the_labels_are_frozen_production_skips_the_guess(client, engine, monkeypatch):
    """A placeholder must never reach a trader (TR-009): the reveal shows without it."""
    monkeypatch.setattr(GU, "ready", lambda production: False)
    r = client.get("/guess", follow_redirects=False)
    assert (r.status_code, r.headers["location"]) == (303, "/mirror/reveal")
    page = client.get("/mirror/reveal").text
    assert "You guessed" not in page and "reveal__slice" in page
    assert stored(engine) == []


def test_ready_is_live_only_once_frozen():
    assert GU.ready(production=False)
    assert GU.ready(production=True) is GU.FROZEN


def test_the_reveal_goes_back_to_the_days_and_not_on_to_the_number(client):
    guess(client, "unknown")
    page = client.get("/mirror/reveal").text
    assert 'href="/mirror/fact/worst-days?enter=lens">Show me those days</a>' in page
    assert 'href="/budget"' not in page  # TICKET-903: the walk is upload, receipt, reveal, report
