"""The journey's order (handoff 5): import check, guess, reveal, one number, Scope.

And where a returning trader lands: with nothing uploaded, the upload; with a record
he has not yet been walked through, his import check, which starts the walk; once
he has, home.

Through the app, with the 40-trade fixture trader signed in.
"""

from __future__ import annotations

import re

from sqlalchemy import select

from services.production.api.routes_identity import landing_for
from services.production.db import models as m
from services.production.db.session import make_session

TOKEN = re.compile(r'name="csrf_token" value="([^"]+)"')


def the_import(engine) -> int:
    with make_session(engine) as sess:
        return sess.scalars(select(m.Import.id)).one()


def landing(engine) -> str:
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader).where(m.Trader.login_id == "fx")).one()
        return landing_for(sess, trader)


def record_a_number(client):
    token = TOKEN.search(client.get("/budget").text).group(1)
    return client.post(
        "/budget",
        data={"value": "3000", "unit": "INR", "effective_from": "2026-09-01",
              "csrf_token": token},
        follow_redirects=False,
    )


def test_the_import_check_goes_on_to_the_guess(client, engine):
    page = client.get(f"/imports/{the_import(engine)}").text
    assert '<a href="/guess">See your record</a>' in page
    assert '<a href="/mirror">See your record</a>' not in page


def test_the_one_number_is_the_kits_form_in_the_apps_words(client):
    page = client.get("/budget").text
    assert '<h1 class="title">What you risk</h1>' in page
    assert '<p class="lead">How much are you willing to lose on a single trade?</p>' in page
    assert '<fieldset class="fieldset"><legend class="fieldset__legend">In</legend>' in page
    assert (
        '<input class="choice__input" type="radio" name="unit" value="INR" checked>'
        '<span class="body">rupees</span>'
    ) in page
    assert 'type="radio" name="unit" value="PCT"><span class="body">per cent of my trading' in page
    assert '<button class="btn btn--primary btn--block" type="submit">Record it</button>' in page
    assert (
        '<a class="btn btn--text" href="/eligibility">'
        "Next: what we can and cannot check on your history</a>"
    ) in page
    assert "<select" not in page  # the kit's radios, not the old drop-down


def test_the_history_is_written_by_the_filters(client):
    record_a_number(client)
    page = client.get("/budget").text
    assert '<td class="table__num">₹3,000</td>' in page
    assert "Nothing here is overwritten." in page


def test_recorded_the_journey_goes_on_to_the_scope(client):
    r = record_a_number(client)
    assert (r.status_code, r.headers["location"]) == (303, "/mirror")


def test_a_record_not_yet_walked_through_lands_on_its_import_check(client, engine):
    assert landing(engine) == f"/imports/{the_import(engine)}"


def test_once_he_has_guessed_he_lands_home(client, engine):
    token = TOKEN.search(client.get("/guess").text).group(1)
    client.post("/guess", data={"answer": "option-1", "csrf_token": token})
    assert landing(engine) == "/"


def test_where_the_guess_is_skipped_the_one_number_ends_the_walk(client, engine):
    """In production, until TR-009 freezes the labels, no one guesses: the one number,
    the walk's last step, is what says he has been through it."""
    assert landing(engine).startswith("/imports/")
    record_a_number(client)
    assert landing(engine) == "/"
