"""The journey's order (handoff 5): import check, guess, reveal, one number, Scope.

And where a returning trader lands: with nothing uploaded, the upload; with a record
he has not yet been walked through, his import check, which starts the walk; once
he has, home.

Through the app, with the 40-trade fixture trader signed in.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from sqlalchemy import select

from services.production.api.routes_identity import landing_for
from services.production.db import models as m
from services.production.db.session import make_session
from services.shared.schemas import scope_v1 as s

TOKEN = re.compile(r'name="csrf_token" value="([^"]+)"')


def the_import(engine) -> int:
    """The upload his record comes from: the fixture's, the first."""
    with make_session(engine) as sess:
        return sess.scalars(select(m.Import.id).order_by(m.Import.id)).first()


def refuse_a_later_file(engine) -> int:
    """A second upload, refused: a P&L statement, say. No trips."""
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader).where(m.Trader.login_id == "fx")).one()
        raw = m.RawFile(trader_id=trader.id, sha256="e" * 64, original_name="pnl.csv",
                        size=1, stored_path="/tmp/e", uploaded_at=datetime.now(UTC))
        sess.add(raw)
        sess.flush()
        imp = m.Import(trader_id=trader.id, raw_file_id=raw.id, source_account="A",
                       adapter_id="dhan_tradebook_v1", adapter_version="1",
                       filemap_version="1", code_version="fixturesha",
                       outcome=s.ImportOutcome.REJECTED, rejection_text="no prices",
                       rows_in=1, rows_parsed=0, rows_excluded=0, fees_available=False,
                       version_no=2, created_at=datetime.now(UTC))
        sess.add(imp)
        sess.commit()
        return imp.id


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
    assert page.count('href="/guess">See your record') == 2  # the line and the button
    assert 'href="/mirror">See your record' not in page


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


def test_a_refused_later_file_does_not_hide_the_walk(client, engine):
    """Found walking it: his latest upload was a refused file, whose page has no way on."""
    refused = refuse_a_later_file(engine)
    assert refused != the_import(engine)
    assert landing(engine) == f"/imports/{the_import(engine)}"
