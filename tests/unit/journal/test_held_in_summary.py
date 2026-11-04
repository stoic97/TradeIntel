"""The day summary says when a held position closed (TICKET-800).

"All before noon" was worked out from entry hours alone, so a position held for weeks
read as a morning trade. Dates below are invented and the day counts are worked by hand:

    4 Mar to 5 Mar 2024: 1 day. 4 Mar to 11 Mar: 7 days.
    4 Mar to 5 Apr 2024: 27 days to 31 Mar, then 5 more = 32 days.
    2 Jan to 5 Feb 2024: 29 days to 31 Jan, then 5 more = 34 days.

A fact appears only on a day with a held trade. A Journal is rewritten when its facts
differ, so a new key on every day would give every Journal a new version.
"""

from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from services.production.api.app import create_app
from services.production.db import models as m
from services.production.db.session import make_engine, make_session, run_migrations
from services.production.journal import periods as pd
from services.production.journal import prose
from services.production.journal import sections as sec
from services.production.mirror.metrics import Trip
from services.shared.schemas import scope_v1 as s
from tests.unit.api.test_upload import CSRF, sign_up


def _trip(name: str, opened: str, closed: str, net: int = -100) -> Trip:
    entry, exit_ = datetime.fromisoformat(opened), datetime.fromisoformat(closed)
    return Trip(
        trip_id=name, symbol="OPT", trading_day=entry.date().isoformat(), entry_ts=entry,
        exit_ts=exit_, holding_seconds=int((exit_ - entry).total_seconds()),
        net=Decimal(net), lots=1, risk_unit_source=s.RiskUnitSourceV1.PREMIUM_PAID,
    )


def _facts(*trips: Trip) -> dict:
    period = pd.Period(
        unit=s.JournalUnit.DAY,
        period_start=trips[0].trading_day,
        period_end=trips[0].trading_day,
        trips=tuple(trips),
        complete=True,
    )
    return sec.build(period, history=list(trips), fees_available=False)


def _summary(*trips: Trip) -> str:
    return prose.render(_facts(*trips)).split("\n\n")[0]


MONTH_LONG = _trip("held", "2024-03-04T10:00:00", "2024-04-05T15:00:00")
OVERNIGHT = _trip("held", "2024-03-04T10:00:00", "2024-03-05T09:30:00")
MORNING = _trip("a", "2024-03-04T09:10:00", "2024-03-04T09:20:00", net=-40)
AFTERNOON = _trip("b", "2024-03-04T14:00:00", "2024-03-04T14:10:00", net=-60)


def test_one_held_trade_reads_with_both_dates_and_the_days_between():
    assert _summary(MONTH_LONG).startswith(
        "One trade, held past the day: opened on 4 March 2024, closed on 5 April 2024, "
        "32 days later. Net −₹100. It closed down."
    )


def test_a_position_held_overnight_says_the_next_day():
    assert _summary(OVERNIGHT).startswith(
        "One trade, held past the day: opened on 4 March 2024, closed on 5 March 2024, "
        "the next day. Net −₹100."
    )


def test_a_held_position_is_not_called_a_morning_trade():
    assert "before noon" not in _summary(MONTH_LONG)


def test_a_mixed_day_keeps_its_hours_and_adds_the_held_one():
    summary = _summary(MORNING, AFTERNOON, _trip("h", "2024-03-04T14:30:00", "2024-03-11T10:00:00"))
    assert summary.startswith("Three trades, between 09:00 and 14:00.")
    assert (
        "One was held past the day: opened on 4 March 2024, closed on 11 March 2024, "
        "7 days later."
    ) in summary


def test_several_held_trades_are_counted_and_the_longest_is_named():
    summary = _summary(MORNING, OVERNIGHT, _trip("h", "2024-03-04T14:30:00", "2024-04-05T10:00:00"))
    assert (
        "Two were held past the day. The longest opened on 4 March 2024 and closed on "
        "5 April 2024, 32 days later."
    ) in summary


def test_a_trade_closing_after_noon_is_not_all_before_noon():
    """The same sentence, without a held position: in at 11:00, out at 15:15."""
    summary = _summary(_trip("x", "2024-03-04T11:00:00", "2024-03-04T15:15:00"))
    assert "before noon" not in summary


def test_trades_opened_and_closed_before_noon_still_say_so():
    """Guard: the existing sentence stays where it is true."""
    assert _summary(MORNING).startswith("One trade, all before noon.")


def test_a_day_with_nothing_held_carries_no_new_fact():
    """Guard: its facts stay byte-identical, so the next upload writes no new version."""
    assert "held" not in _facts(MORNING, AFTERNOON)


def test_a_stored_journal_from_before_this_still_renders():
    """Guard: stored facts have no held key, and a Journal is never rewritten."""
    facts = _facts(MORNING)
    facts.pop("held", None)
    assert prose.render(facts).startswith("One trade, all before noon.")


HEADER = "Date,Time,Name,Buy/Sell,Order,Exchange,Segment,Quantity/Lot,Trade Price,Trade Value,Status"


def _row(day: str, time: str, name: str, side: str, order: str, value: int) -> str:
    price = value / 50
    return f"{day},{time},{name},{side},{order},NSE,Derivative,50,{price:.2f},{value:.2f},Traded"


FILE = "\n".join([
    HEADER,
    _row("2024-01-02", "09:30:00", "NIFTY 25 JAN 20000 CALL", "BUY", "INTRADAY", 5000),
    _row("2024-01-02", "09:40:00", "NIFTY 25 JAN 20000 CALL", "SELL", "INTRADAY", 4900),
    _row("2024-01-02", "10:00:00", "NIFTY 29 FEB 20000 CALL", "BUY", "MARGIN", 5000),
    _row("2024-02-05", "11:00:00", "NIFTY 29 FEB 20000 CALL", "SELL", "MARGIN", 4800),
    _row("2024-02-06", "09:30:00", "NIFTY 29 FEB 20100 CALL", "BUY", "INTRADAY", 5000),
    _row("2024-02-06", "09:40:00", "NIFTY 29 FEB 20100 CALL", "SELL", "INTRADAY", 5100),
    _row("2024-02-06", "10:00:00", "NIFTY 29 FEB 20100 CALL", "BUY", "INTRADAY", 5000),
    _row("2024-02-06", "10:10:00", "NIFTY 29 FEB 20100 CALL", "SELL", "INTRADAY", 5200),
]) + "\n"


def test_the_journal_page_shows_it_after_a_real_upload(scope_environment):
    engine = make_engine(os.environ["SCOPE_DB"])
    run_migrations(engine)
    client = sign_up(TestClient(create_app()), engine, "HELD", "held")
    token = CSRF.search(client.get("/upload").text).group(1)
    sent = client.post("/upload", files={"file": ("t.csv", FILE.encode(), "text/csv")},
                       data={"csrf_token": token}, follow_redirects=False)
    assert sent.status_code == 303, sent.text
    with make_session(engine) as sess:
        journal_id = sess.scalars(
            select(m.Journal.id).where(m.Journal.period_start == "2024-01-02")
        ).one()
    page = client.get(f"/journals/{journal_id}").text
    assert (
        "One was held past the day: opened on 2 January 2024, closed on 5 February 2024, "
        "34 days later."
    ) in page
    assert "before noon" not in page


@pytest.mark.parametrize("word", ["winning", "losing streak", "should"])
def test_the_new_sentence_makes_no_claim(word):
    assert word not in _summary(MORNING, MONTH_LONG).lower()
