"""The count on the line is the count of trades the upload set aside [TICKET-811]."""

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


def test_one_sold_option_reads_in_the_singular_from_the_upload(client, engine):  # noqa: F811
    upload(client, content=with_a_sold_option())
    with make_session(engine) as sess:
        assert len(sess.scalars(select(m.SkippedTrip)).all()) == 1
        assert sess.scalars(select(m.Import)).one().trips_refused == 1
    page = " ".join(client.get("/mirror").text.split())
    assert "1 sold-option trade is not yet counted — totals will change when it is." in page
