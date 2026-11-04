"""A grant counts only against the text in force [TICKET-803].

The latest decision used to count whatever text it was made on, so a grant on a draft
stayed live after the reviewed version replaced it. Now a new version asks again.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from services.production.accounts import consent as cs
from services.production.db import models as m
from services.production.db.session import make_session
from services.shared.schemas import scope_v1 as s
from tests.unit.api.test_consent import app_env, signed_in, token  # noqa: F401

ASKED_AGAIN = "We have changed this text since you last agreed, so we are asking again."
OLD = "0-draft"


def grant(engine, purpose: s.ConsentPurpose, version: str = OLD) -> None:
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader)).one()
        sess.add(m.ConsentEvent(
            trader_id=trader.id, purpose=purpose, scope="v1", terms_version=version,
            granted=True, at=datetime.now(UTC), method="web", wording_shown="x" * 100,
        ))
        sess.commit()


def grant_both_on_the_old_text(engine) -> None:
    grant(engine, s.ConsentPurpose.DIAGNOSIS)
    grant(engine, s.ConsentPurpose.ENGINE_TESTING)


def latest(engine) -> dict[s.ConsentPurpose, m.ConsentEvent]:
    with make_session(engine) as sess:
        rows = sess.scalars(select(m.ConsentEvent).order_by(m.ConsentEvent.id)).all()
        sess.expunge_all()
    return {row.purpose: row for row in rows}


def agree(client, **fields):
    return client.post("/consent", data={"csrf_token": token(client), **fields},
                       follow_redirects=False)


@pytest.mark.parametrize("path", ["/upload", "/budget", "/mirror", "/eligibility"])
def test_a_grant_on_an_old_text_closes_the_product(signed_in, path):  # noqa: F811
    client, engine = signed_in
    grant_both_on_the_old_text(engine)
    response = client.get(path, follow_redirects=False)
    assert (response.status_code, response.headers["location"]) == (303, "/consent")


def test_a_grant_on_the_current_text_keeps_it_open(signed_in):  # noqa: F811
    client, engine = signed_in
    grant(engine, s.ConsentPurpose.DIAGNOSIS, cs.CURRENT.version)
    assert client.get("/upload", follow_redirects=False).status_code == 200


def test_the_screen_says_why_it_is_asking_again(signed_in):  # noqa: F811
    client, engine = signed_in
    grant_both_on_the_old_text(engine)
    assert ASKED_AGAIN in client.get("/consent").text


def test_a_first_time_trader_is_not_told_it_changed(signed_in):  # noqa: F811
    client, _ = signed_in
    assert ASKED_AGAIN not in client.get("/consent").text


def test_the_engine_box_is_not_ticked_for_him_when_asked_again(signed_in):  # noqa: F811
    client, engine = signed_in
    grant_both_on_the_old_text(engine)
    page = client.get("/consent").text
    assert 'name="engine_testing" value="yes" checked' not in page


def test_agreeing_again_writes_both_against_the_current_text(signed_in):  # noqa: F811
    client, engine = signed_in
    grant_both_on_the_old_text(engine)
    agree(client, diagnosis="yes", engine_testing="yes")
    rows = latest(engine)
    assert {row.terms_version for row in rows.values()} == {cs.CURRENT.version}
    assert all(row.granted for row in rows.values())
    assert client.get("/upload", follow_redirects=False).status_code == 200


def test_leaving_the_engine_box_empty_ends_the_old_engine_grant(signed_in):  # noqa: F811
    """Otherwise a grant on the old text stays the latest word on that purpose."""
    client, engine = signed_in
    grant_both_on_the_old_text(engine)
    agree(client, diagnosis="yes")
    engine_row = latest(engine)[s.ConsentPurpose.ENGINE_TESTING]
    assert (engine_row.granted, engine_row.terms_version) == (False, cs.CURRENT.version)
    assert client.get("/upload", follow_redirects=False).status_code == 200


def test_nothing_is_written_for_a_purpose_he_never_granted(signed_in):  # noqa: F811
    client, engine = signed_in
    grant(engine, s.ConsentPurpose.DIAGNOSIS)
    agree(client, diagnosis="yes")
    assert s.ConsentPurpose.ENGINE_TESTING not in latest(engine)


def test_the_old_rows_are_kept(signed_in):  # noqa: F811
    """The ledger is a history: asking again adds rows and edits none."""
    client, engine = signed_in
    grant_both_on_the_old_text(engine)
    agree(client, diagnosis="yes", engine_testing="yes")
    with make_session(engine) as sess:
        versions = [e.terms_version for e in sess.scalars(select(m.ConsentEvent)).all()]
    assert versions.count(OLD) == 2 and versions.count(cs.CURRENT.version) == 2


def test_the_ledger_does_not_call_an_old_grant_current(signed_in):  # noqa: F811
    client, engine = signed_in
    grant_both_on_the_old_text(engine)
    assert "Currently granted." not in client.get("/settings/consent").text


def test_agreeing_again_goes_home_not_to_the_upload(signed_in):  # noqa: F811
    client, engine = signed_in
    grant_both_on_the_old_text(engine)
    assert agree(client, diagnosis="yes").headers["location"] == "/"


def test_a_first_agreement_still_goes_to_the_upload(signed_in):  # noqa: F811
    client, _ = signed_in
    assert agree(client, diagnosis="yes").headers["location"] == "/upload"
