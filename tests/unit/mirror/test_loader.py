"""The Mirror's loader: what a stored trade becomes when the Mirror reads it.

Through the same 40-trip history and login the page tests use (conftest.py), so the
path tested is the one a trader's trades take: the database, the instrument profile,
the trader's own timezone.
"""

from __future__ import annotations

from sqlalchemy import select

from services.production.db import models as m
from services.production.db.session import make_session
from services.production.mirror import loader


def test_the_loader_carries_each_trades_instrument(client, engine):
    """B1: the symbol a trade record shows is the one stored with the trade."""
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader).where(m.Trader.login_id == "fx")).one()
        trips, _ = loader.load_for(sess, trader)
    assert len(trips) == 40
    assert {t.symbol for t in trips} == {"WIDGETOIL"}
