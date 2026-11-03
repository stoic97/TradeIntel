"""B7: the leaving card (handoff 5 and 9, screen 19; D2, D9).

At the top of Your Journals, once, ever, after he has read his first Journal: one
question in his own words, or "Not now". Through the app, with the contract fixture's
Journals generated (test_journals' seed).

Its words and its link are not written yet (D9, D2): the card carries placeholders,
marked as such, draws no link, and is never shown in production until signed - the
same rule the guess follows (TR-009).
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy import select

from services.production.db import models as m
from services.production.db.session import make_session
from services.production.journal import leaving
from tests.unit.api.test_journals import _journals, _seed, _sign_in

TOKEN = re.compile(r'name="csrf_token"\s+value="([^"]+)"')
CARD = '<form class="leaving-card" method="post" action="/leaving-card">'


@pytest.fixture()
def engine():
    import os

    from services.production.db.session import make_engine, run_migrations

    e = make_engine(os.environ["SCOPE_DB"])
    run_migrations(e)
    return e


@pytest.fixture()
def client(engine):
    with make_session(engine) as sess:
        _seed(sess, "fx")
    return _sign_in("fx")


def read_a_journal(client, engine):
    client.get(f"/journals/{_journals(engine)[0].id}")


def rows(engine, model):
    with make_session(engine) as sess:
        return list(sess.scalars(select(model)).all())


def send(client, path="/leaving-card", **data):
    token = TOKEN.search(client.get("/account").text).group(1)
    return client.post(path, data={"csrf_token": token, **data}, follow_redirects=False)


def test_not_before_he_has_read_a_journal(client, engine):
    assert CARD not in client.get("/journals").text
    assert rows(engine, m.LeavingCardShown) == []


def test_once_he_has_read_one_it_shows_once_and_never_again(client, engine):
    read_a_journal(client, engine)
    page = client.get("/journals").text
    assert CARD in page
    assert f'<h2 class="leaving-card__title">{leaving.HEADING}</h2>' in page
    assert len(rows(engine, m.LeavingCardShown)) == 1
    assert CARD not in client.get("/journals").text, "shown once: scrolling past counts"


def test_the_placeholders_draw_no_link():
    """D2 is open: no WhatsApp host is exempted, so no link is drawn."""
    assert leaving.LINK is None and not leaving.SIGNED
    assert all("D9" in line for line in (leaving.HEADING, leaving.QUESTION, leaving.OFFER))


def test_his_answer_is_kept_once_in_his_words(client, engine):
    read_a_journal(client, engine)
    client.get("/journals")
    r = send(client, answer="  The worst-days page was the one that landed.  ")
    assert (r.status_code, r.headers["location"]) == (303, "/journals")
    send(client, answer="a second answer")
    kept = rows(engine, m.LeavingCardAnswer)
    assert [(a.outcome, a.answer) for a in kept] == [
        ("answered", "The worst-days page was the one that landed.")]


def test_not_now_is_an_answer_with_no_words(client, engine):
    read_a_journal(client, engine)
    client.get("/journals")
    send(client, "/leaving-card/dismiss")
    assert [(a.outcome, a.answer) for a in rows(engine, m.LeavingCardAnswer)] == [
        ("dismissed", None)]


def test_an_answer_is_cut_to_a_card_not_a_letter(client, engine):
    read_a_journal(client, engine)
    client.get("/journals")
    send(client, answer="x" * (leaving.LONGEST + 500))
    assert len(rows(engine, m.LeavingCardAnswer)[0].answer) == leaving.LONGEST


def test_nothing_is_kept_for_a_card_he_was_never_shown(client, engine):
    assert send(client, answer="unasked").status_code == 303
    assert rows(engine, m.LeavingCardAnswer) == []


def test_an_answer_without_its_token_is_refused(client, engine):
    read_a_journal(client, engine)
    client.get("/journals")
    r = client.post("/leaving-card", data={"answer": "x"}, follow_redirects=False)
    assert r.status_code == 403 and rows(engine, m.LeavingCardAnswer) == []


def test_until_its_words_are_signed_production_never_shows_it(client, engine, monkeypatch):
    monkeypatch.setattr(leaving, "ready", lambda production: False)
    read_a_journal(client, engine)
    assert CARD not in client.get("/journals").text
    assert rows(engine, m.LeavingCardShown) == []


def test_ready_is_live_only_once_signed():
    assert leaving.ready(production=False)
    assert leaving.ready(production=True) is leaving.SIGNED
