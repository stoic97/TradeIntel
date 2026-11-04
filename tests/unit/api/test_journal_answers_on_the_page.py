"""The current journal page shows what was written, and the way to what it no longer lists
[TICKET-814]. Day 2026-09-01 holds t01, t02 and t03 in the synthetic contract fixture."""

from __future__ import annotations

import json
import re

from sqlalchemy import func, select

from services.production.db import models as m
from services.production.db.session import make_session
from services.production.journal import fields as fl
from tests.unit.api.test_journals import client, engine  # noqa: F401


def _changed_day(engine) -> tuple[int, int]:  # noqa: F811
    """Answers on version 1 of the day, then a version 2 without t03."""
    with make_session(engine) as sess:
        v1 = sess.scalars(select(m.Journal).where(m.Journal.period_start == "2026-09-01")).first()
        fl.record(sess, journal=v1, field="note", value="NOTE-ON-THE-DAY", trip_id=None)
        fl.record(sess, journal=v1, field="rationale", value="KEPT-TRADE", trip_id="t01")
        fl.record(sess, journal=v1, field="rationale", value="GONE-TRADE", trip_id="t03")
        v2 = m.Journal(
            trader_id=v1.trader_id, import_id=v1.import_id, unit=v1.unit,
            period_start=v1.period_start, period_end=v1.period_end, version_no=2,
            supersedes=v1.id, generated_at=v1.generated_at, sections=v1.sections,
            trip_ids=json.dumps(["t01", "t02"]),
        )
        sess.add(v2)
        sess.commit()
        return v1.id, v2.id


def test_the_note_is_on_the_current_page(engine, client):  # noqa: F811
    _, v2 = _changed_day(engine)
    assert "NOTE-ON-THE-DAY" in client.get(f"/journals/{v2}").text


def test_an_answer_for_a_trade_still_there_is_on_it(engine, client):  # noqa: F811
    _, v2 = _changed_day(engine)
    assert "KEPT-TRADE" in client.get(f"/journals/{v2}").text


def test_an_answer_for_a_trade_no_longer_there_is_not(engine, client):  # noqa: F811
    _, v2 = _changed_day(engine)
    assert "GONE-TRADE" not in client.get(f"/journals/{v2}").text


def test_the_sentence_links_to_the_earlier_version(engine, client):  # noqa: F811
    v1, v2 = _changed_day(engine)
    assert (
        f'The <a class="link" href="/journals/{v1}">earlier version</a> is kept.'
        in client.get(f"/journals/{v2}").text
    )


def test_that_answer_is_on_the_page_it_links_to(engine, client):  # noqa: F811
    v1, _ = _changed_day(engine)
    assert "GONE-TRADE" in client.get(f"/journals/{v1}").text


def test_saving_an_unchanged_answer_writes_nothing(engine, client):  # noqa: F811
    _, v2 = _changed_day(engine)
    page = client.get(f"/journals/{v2}").text
    token = re.search(r'name="csrf_token"\s+value="([^"]+)"', page).group(1)
    with make_session(engine) as sess:
        before = sess.scalar(select(func.count()).select_from(m.JournalFieldEntry))
    client.post(
        f"/journals/{v2}/field",
        data={"field": "note", "value": "NOTE-ON-THE-DAY", "csrf_token": token},
        follow_redirects=False,
    )
    with make_session(engine) as sess:
        assert sess.scalar(select(func.count()).select_from(m.JournalFieldEntry)) == before
