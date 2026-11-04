"""The label on the page agrees with what the upload changed [TICKET-801]."""

from __future__ import annotations

import json

from sqlalchemy import select

from services.production.db import models as m
from services.production.db.session import make_session
from tests.unit.api.test_journals import client, engine  # noqa: F401

LABEL = "A later upload changed this period."


def _add_version(engine, trip_ids=None) -> int:  # noqa: F811
    """A second version of the newest day: the same trades unless told otherwise."""
    with make_session(engine) as sess:
        first = sess.scalars(select(m.Journal).order_by(m.Journal.period_start.desc())).first()
        version = m.Journal(
            trader_id=first.trader_id, import_id=first.import_id, unit=first.unit,
            period_start=first.period_start, period_end=first.period_end,
            version_no=2, supersedes=first.id, generated_at=first.generated_at,
            sections=first.sections,
            trip_ids=first.trip_ids if trip_ids is None else json.dumps(trip_ids),
        )
        sess.add(version)
        sess.commit()
        return version.id


def test_the_same_trades_do_not_claim_a_change(engine, client):  # noqa: F811
    assert LABEL not in client.get(f"/journals/{_add_version(engine)}").text


def test_the_list_does_not_call_it_a_new_version(engine, client):  # noqa: F811
    _add_version(engine)
    assert "version 2" not in client.get("/journals").text


def test_different_trades_say_so_on_the_page(engine, client):  # noqa: F811
    assert LABEL in client.get(f"/journals/{_add_version(engine, ['t99'])}").text


def test_different_trades_say_so_in_the_list(engine, client):  # noqa: F811
    _add_version(engine, ["t99"])
    assert "version 2" in client.get("/journals").text


def test_a_first_version_says_nothing(engine, client):  # noqa: F811
    with make_session(engine) as sess:
        first = sess.scalars(select(m.Journal)).first().id
    assert LABEL not in client.get(f"/journals/{first}").text
