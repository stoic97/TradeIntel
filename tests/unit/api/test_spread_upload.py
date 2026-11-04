"""A spread on the screens: one position, its legs under it, every rupee counted [TICKET-810].

Through a real upload. Synthetic rows, worked by hand, a unit of 100 throughout:

  14 Oct  bought 5100 at 10, sold at 4: -600. Sold 5000 at 30, bought at 11: +1900. One
          position, five seconds apart, +1300. Bought 5300 at 5, sold at 7: +200.
          The day is +1500.
  15 Oct  sold 5200 at 20, bought at 25: -500, a naked sale, uncapped. Bought 5400 at 3,
          sold at 4: +100. The day is -400.
  16 Oct  bought 5500 at 2, sold at 2.50: +50. Bought 5600 at 2, sold at 2.50: +50.

Seven legs in six positions, total +1200 (+1500, -400, +100).
"""

from __future__ import annotations

import re
from decimal import Decimal

import pytest
from sqlalchemy import select

from services.production.db import models as m
from services.production.db.session import make_session
from services.production.mirror import loader
from services.shared.schemas import scope_v1 as s
from tests.unit.api.test_upload import (  # noqa: F401 - fixtures used by name
    CSRF,
    DUPES,
    client,
    engine,
    upload,
)

ROWS = [
    ("2026-10-14", "09:30:00", 5100, "BUY", "10.00"),
    ("2026-10-14", "09:30:05", 5000, "SELL", "30.00"),
    ("2026-10-14", "12:00:00", 5300, "BUY", "5.00"),
    ("2026-10-14", "12:30:00", 5300, "SELL", "7.00"),
    ("2026-10-14", "15:00:00", 5100, "SELL", "4.00"),
    ("2026-10-14", "15:00:05", 5000, "BUY", "11.00"),
    ("2026-10-15", "10:00:00", 5200, "SELL", "20.00"),
    ("2026-10-15", "11:00:00", 5200, "BUY", "25.00"),
    ("2026-10-15", "12:00:00", 5400, "BUY", "3.00"),
    ("2026-10-15", "12:30:00", 5400, "SELL", "4.00"),
    ("2026-10-16", "09:30:00", 5500, "BUY", "2.00"),
    ("2026-10-16", "10:00:00", 5500, "SELL", "2.50"),
    ("2026-10-16", "11:00:00", 5600, "BUY", "2.00"),
    ("2026-10-16", "11:30:00", 5600, "SELL", "2.50"),
]


def tradebook() -> bytes:
    header = (DUPES / "clean.csv").read_text().splitlines()[0]
    lines = [
        f"{day},{time},WIDGETOIL 19 NOV {strike} CALL,{side},INTRADAY,MCX,Commodity,100,"
        f"{price},{Decimal(price) * 100:.2f},Traded"
        for day, time, strike, side, price in ROWS
    ]
    return ("\n".join([header, *lines]) + "\n").encode()


@pytest.fixture()
def uploaded(client, engine):  # noqa: F811
    response = upload(client, content=tradebook())
    assert response.status_code == 303
    return client


def text(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).replace("&#39;", "'").split())


def loaded(engine):  # noqa: F811
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader)).one()
        return loader.load_for(sess, trader)[0]


def spread(engine):  # noqa: F811
    return next(t for t in loaded(engine) if t.legs)


def test_nothing_is_refused(uploaded, engine):  # noqa: F811
    with make_session(engine) as sess:
        assert sess.scalars(select(m.SkippedTrip)).all() == []
        assert sess.scalars(select(m.Import)).one().trips_refused == 0
        assert len(sess.scalars(select(m.Trip)).all()) == 7


def test_the_two_legs_share_a_position_and_the_rest_have_none(uploaded, engine):  # noqa: F811
    with make_session(engine) as sess:
        rows = sess.scalars(select(m.Trip)).all()
    linked = [r for r in rows if r.position_id]
    assert len(linked) == 2
    assert len({r.position_id for r in linked}) == 1


def test_every_leg_keeps_its_strike_and_type(uploaded, engine):  # noqa: F811
    with make_session(engine) as sess:
        rows = sess.scalars(select(m.Trip)).all()
    assert {(r.option_type, int(r.strike)) for r in rows if r.position_id} == {
        ("CE", 5000), ("CE", 5100),
    }


def test_the_record_reads_positions(uploaded, engine):  # noqa: F811
    trips = loaded(engine)
    assert len(trips) == 6
    assert sum(t.net for t in trips) == Decimal(1200)


def test_the_spread_is_its_legs_added_up(uploaded, engine):  # noqa: F811
    p = spread(engine)
    assert p.net == Decimal(1300)
    assert p.trading_day == "2026-10-14"
    assert [(leg.label, leg.net) for leg in p.legs] == [
        ("Bought 5100 CE", Decimal(-600)), ("Sold 5000 CE", Decimal(1900)),
    ]


def test_the_spreads_day_reads_as_the_trader_reads_it(uploaded):
    page = text(uploaded.get("/mirror/fact/worst-days").text)
    assert "+₹1,500" in page


def test_a_spread_is_one_trade_with_its_legs_shown(uploaded):
    """Section 3 of the feedback: a spread is shown as one position with its legs."""
    page = text(uploaded.get("/mirror/fact/money").text)
    assert "+₹1,300" in page
    assert "Bought 5100 CE −₹600" in page
    assert "Sold 5000 CE +₹1,900" in page


def test_the_leg_alone_is_not_ranked(uploaded, engine):  # noqa: F811
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader)).one()
        trips = loader.load_for(sess, trader)[0]
    assert Decimal(1900) not in {t.net for t in trips}
    assert Decimal(-600) not in {t.net for t in trips}


def test_a_naked_sale_shows_uncapped_and_its_money_counts(uploaded, engine):  # noqa: F811
    naked = next(t for t in loaded(engine) if t.net == Decimal(-500))
    assert naked.risk_unit_source is s.RiskUnitSourceV1.UNCAPPED
    assert "Uncapped" in text(uploaded.get("/mirror/fact/risk").text)


def test_a_capped_spread_is_not_labelled_uncapped(uploaded, engine):  # noqa: F811
    assert spread(engine).risk_unit_source is s.RiskUnitSourceV1.STRUCTURE_MAX_LOSS


def test_neither_is_ever_a_denominator():
    assert s.RiskUnitSourceV1.UNCAPPED not in s.SHOWABLE_DENOMINATORS
    assert s.RiskUnitSourceV1.STRUCTURE_MAX_LOSS not in s.SHOWABLE_DENOMINATORS


def test_the_risk_fact_counts_them_on_their_own_rows(uploaded):
    page = text(uploaded.get("/mirror/fact/risk").text)
    assert "A spread's maximum loss 1" in page
    assert "Uncapped: a sold option 1" in page


@pytest.mark.parametrize("path", ["/mirror/fact/risk", "/mirror/chapter/4"])
def test_chapter_four_says_it_in_plain_words(uploaded, path):
    """Annex H section 6. With no stop and no budget this fact is in its not-in-file state,
    which hides the table, so the sentence has to live outside it."""
    page = text(uploaded.get(path).text)
    assert "1 trade was a sold option with no cap on its loss, so it has no risk figure." in page
    assert "Its rupees are counted." in page


def test_a_declared_budget_still_outranks_a_structure(uploaded, engine):  # noqa: F811
    page = uploaded.get("/budget").text
    uploaded.post("/budget", data={"value": "3000", "unit": "INR", "effective_from": "2026-10-01",
                                   "csrf_token": CSRF.search(page).group(1)})
    assert spread(engine).risk_unit_source is s.RiskUnitSourceV1.DECLARED_BUDGET


def journal_for(engine, day: str) -> int:  # noqa: F811
    with make_session(engine) as sess:
        return sess.scalars(select(m.Journal.id).where(m.Journal.period_start == day)).one()


def test_a_journal_lists_the_spread_as_one_trade(uploaded, engine):  # noqa: F811
    page = text(uploaded.get(f"/journals/{journal_for(engine, '2026-10-14')}").text)
    assert "Trade 1 — +₹1,300" in page
    assert "Trade 2 — +₹200" in page
    assert "Trade 3" not in page


def test_a_journal_answer_on_a_spread_is_saved(uploaded, engine):  # noqa: F811
    jid = journal_for(engine, "2026-10-14")
    page = uploaded.get(f"/journals/{jid}").text
    form = re.search(r'name="trip_id" value="([^"]+)"', page).group(1)
    assert form == spread(engine).trip_id
    response = uploaded.post(
        f"/journals/{jid}/field",
        data={"trip_id": form, "csrf_token": CSRF.search(page).group(1), "planned_sl": "10"},
        follow_redirects=False,
    )
    assert response.status_code in (200, 303)


def test_home_counts_the_spread_as_one_trade(uploaded):
    page = text(uploaded.get("/").text)
    assert "2 trades" in page
    assert "+₹1,500" in page
