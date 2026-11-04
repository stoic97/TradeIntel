"""Home carries his figures, so it asks for the current consent too [TICKET-803]."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from services.production.db import models as m
from services.production.db.session import make_session
from services.shared.schemas import scope_v1 as s


def test_home_sends_a_grant_on_an_old_text_to_the_consent_screen(client, engine):
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader).where(m.Trader.login_id == "fx")).one()
        sess.add(m.ConsentEvent(
            trader_id=trader.id, purpose=s.ConsentPurpose.DIAGNOSIS, scope="v1",
            terms_version="an-older-text", granted=True, at=datetime.now(UTC),
            method="web", wording_shown="x" * 100,
        ))
        sess.commit()
    response = client.get("/", follow_redirects=False)
    assert (response.status_code, response.headers["location"]) == (303, "/consent")
