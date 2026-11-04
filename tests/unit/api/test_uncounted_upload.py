"""What the upload set aside, now that sold options are counted [TICKET-811, TICKET-810]."""

from __future__ import annotations

from sqlalchemy import select

from services.production.db import models as m
from services.production.db.session import make_session
from tests.unit.api.test_upload import _two_days, client, engine, upload  # noqa: F401


def with_a_sold_option() -> bytes:
    sold = (
        "2026-10-15,13:30:00,WIDGETOIL 19 NOV 5100 CALL,SELL,INTRADAY,MCX,"
        "Commodity,100,53.00,5300.00,Traded\n"
        "2026-10-15,14:30:00,WIDGETOIL 19 NOV 5100 CALL,BUY,INTRADAY,MCX,"
        "Commodity,100,52.00,5200.00,Traded\n"
    )
    return _two_days() + sold.encode()


def test_a_sold_option_is_counted_so_the_line_does_not_show(client, engine):  # noqa: F811
    """[TICKET-810] ended what TICKET-811's line was waiting for."""
    upload(client, content=with_a_sold_option())
    with make_session(engine) as sess:
        assert sess.scalars(select(m.SkippedTrip)).all() == []
        assert sess.scalars(select(m.Import)).one().trips_refused == 0
    assert "not yet counted" not in " ".join(client.get("/mirror").text.split())
