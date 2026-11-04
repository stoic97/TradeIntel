"""The count on a real upload with sold options and a spread [TICKET-831, TICKET-810].

Same synthetic rows as test_spread_upload, worked by hand. Six positions, all same-day:

    14 Oct  a spread: a -600 leg and a +1900 leg, one position, +1300
    14 Oct  +200
    15 Oct  a naked sale, uncapped: -500
    15 Oct  +100
    16 Oct  +50, +50

Against ₹400 the only position past the number is the naked sale. The spread's -600 leg
is past it too, but a position is one decision and the spread made money, so it is not.
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy import select

from services.production.db import models as m
from services.production.db.session import make_session
from services.production.mirror import loader
from services.production.mirror import metrics as mx
from tests.unit.api.test_spread_upload import tradebook
from tests.unit.api.test_upload import (  # noqa: F401 - fixtures used by name
    CSRF,
    client,
    engine,
    upload,
)


@pytest.fixture()
def counted(client, engine):  # noqa: F811
    assert upload(client, content=tradebook()).status_code == 303
    token = CSRF.search(client.get("/budget").text).group(1)
    client.post("/budget", data={"value": "400", "unit": "INR", "effective_from": "2026-10-14",
                                 "csrf_token": token})
    return client


def text(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def test_an_uncapped_sold_option_counts_and_is_still_uncapped(counted, engine):  # noqa: F811
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader)).one()
        trips, _ = loader.load_for(sess, trader)
    past = mx.trades_past_number(trips)
    assert (past.count, past.measured) == (1, 6)
    sold = next(t for t in trips if t.trip_id == past.trip_ids[0])
    assert sold.uncapped is True


def test_a_spread_is_measured_as_one_position_not_by_its_losing_leg(counted, engine):  # noqa: F811
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader)).one()
        trips, _ = loader.load_for(sess, trader)
    spread = next(t for t in trips if t.legs)
    assert spread.trip_id not in mx.trades_past_number(trips).trip_ids


@pytest.mark.parametrize("path", ["/budget", "/mirror/fact/risk"])
def test_both_pages_say_it(counted, path):
    page = text(counted.get(path).text)
    assert "1 trade lost more than your number." in page
    assert "Same-day trades only: 6 of them," in page
