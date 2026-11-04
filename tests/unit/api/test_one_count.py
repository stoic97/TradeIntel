"""One upload, one trade count, on every screen (TICKET-788).

The receipt counted legs while the record counted trades, so a spread made the upload page
one higher per spread than the report behind it. The file is test_spread_upload's, worked
by hand there: seven legs in six positions, total +1200.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select

from services.production.ctr.reconstruct import reconstruct
from services.production.db import models as m
from services.production.db.session import make_session
from services.shared.schemas.ctr_v1 import Side
from tests.unit.api.test_spread_upload import loaded, text, tradebook
from tests.unit.api.test_upload import client, engine, upload  # noqa: F401
from tests.unit.test_reconstruction import fill

TRADES = 6


@pytest.fixture()
def uploaded(client, engine):  # noqa: F811
    assert upload(client, content=tradebook()).status_code == 303
    return client


def _import_id(engine) -> int:  # noqa: F811
    with make_session(engine) as sess:
        return sess.scalars(select(m.Import.id)).one()


def test_the_receipt_counts_a_spread_as_one_trade(uploaded, engine):  # noqa: F811
    with make_session(engine) as sess:
        assert sess.scalars(select(m.Import)).one().trips_reconstructed == TRADES


def test_the_legs_are_all_kept_behind_that_count(uploaded, engine):  # noqa: F811
    """Guard: the count changes, the rows do not."""
    with make_session(engine) as sess:
        assert len(sess.scalars(select(m.Trip)).all()) == 7


def test_the_upload_review_page_states_the_record_count(uploaded, engine):  # noqa: F811
    page = text(uploaded.get(f"/imports/{_import_id(engine)}").text)
    assert f"Trades reconstructed {TRADES}" in page


def test_the_account_page_states_the_record_count(uploaded):
    assert f"{TRADES} trades" in text(uploaded.get("/account").text)


def test_the_unread_fact_states_the_record_count(uploaded):
    page = text(uploaded.get("/mirror/fact/unread").text)
    assert f"Trades reconstructed {TRADES}" in page


def test_the_record_itself_counts_the_same(uploaded, engine):  # noqa: F811
    """Guard: this is the figure the others have to agree with."""
    assert len(loaded(engine)) == TRADES


def test_the_record_keeps_one_total(uploaded, engine):  # noqa: F811
    """Guard: counting a spread once does not move a rupee."""
    assert sum(t.net for t in loaded(engine)) == Decimal(1200)


def test_one_closing_fill_across_two_lots_is_one_trade():
    """Guard, and the reason an outside FIFO can count more than Scope (TICKET-788).

    Bought 1 at 100, bought 1 at 110, sold 2 at 120: +30. Counting one round trip per lot
    gives two. Scope's unit is one per closing fill, so it gives one, with the same money.
    """
    result = reconstruct([fill(Side.BUY, 1, 100, 0), fill(Side.BUY, 1, 110, 1),
                          fill(Side.SELL, 2, 120, 2)])
    assert len(result.round_trips) == 1
    assert result.round_trips[0].gross_pnl == Decimal(30)
