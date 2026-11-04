"""The budget's "from when" starts at the first date of the history [TICKET-807].

Defaulting to today dates the number after every trade he uploaded, so it applies to
none of them and the page gives no sign why. Through the 40-trip history in conftest,
whose first trading day is 2026-09-01.
"""

from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy import select

from services.production.api.routes_budget import _today
from services.production.db import models as m
from services.production.db.session import make_session
from services.production.mirror import loader
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s

DATE = re.compile(r'id="effective_from"[^>]*\bmax="([^"]+)"[^>]*\bvalue="([^"]+)"')
TOKEN = re.compile(r'name="csrf_token"\s+value="([^"]+)"')


def default_on(page: str) -> str:
    return DATE.search(page).group(2)


def add_earlier_trip(engine, entry: str, exit_: str, exchange: str | None = None) -> None:
    with make_session(engine) as sess:
        stored = sess.scalars(select(m.Trip).where(m.Trip.trip_id == "t01")).one()
        sess.add(m.Trip(
            import_id=stored.import_id, trip_id="earliest", trading_day=entry[:10],
            exchange=exchange or stored.exchange, symbol=stored.symbol,
            segment=stored.segment, direction=stored.direction,
            entry_ts=datetime.fromisoformat(entry), exit_ts=datetime.fromisoformat(exit_),
            quantity=stored.quantity, entry_price=stored.entry_price,
            exit_price=stored.exit_price, gross=stored.gross, fees=stored.fees,
            net=stored.net, fees_available=False,
            risk_unit_source=stored.risk_unit_source,
        ))
        sess.commit()


def test_the_date_starts_at_the_first_day_of_the_history(client):
    assert default_on(client.get("/budget").text) == "2026-09-01"


def test_the_trader_can_still_choose_up_to_today(client):
    assert DATE.search(client.get("/budget").text).group(1) == _today().isoformat()


def test_a_refused_form_keeps_the_same_default(client):
    page = client.get("/budget").text
    refused = client.post("/budget", data={
        "value": "0", "unit": "INR", "effective_from": "2026-09-01",
        "csrf_token": TOKEN.search(page).group(1),
    })
    assert refused.status_code == 400
    assert default_on(refused.text) == "2026-09-01"


def test_the_first_day_is_the_instruments_day_not_utcs(client, engine):
    """00:30 IST on the 20th is still the 19th in UTC."""
    add_earlier_trip(engine, "2026-08-20T00:30:00+05:30", "2026-08-20T00:40:00+05:30")
    assert default_on(client.get("/budget").text) == "2026-08-20"


def test_an_instrument_with_no_profile_falls_back_to_today(client, engine):
    """The budget page has to stay usable; the Mirror says what is wrong with the file."""
    add_earlier_trip(engine, "2026-08-20T10:00:00+05:30", "2026-08-20T10:10:00+05:30",
                     exchange="NOWHERE")
    assert default_on(client.get("/budget").text) == _today().isoformat()


def test_saving_the_default_measures_every_trade_against_the_number(client, engine):
    """The point of the ticket: taking the form as it comes reaches the uploaded trades."""
    page = client.get("/budget").text
    client.post("/budget", data={
        "value": "3000", "unit": "INR", "effective_from": default_on(page),
        "csrf_token": TOKEN.search(page).group(1),
    })
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader).where(m.Trader.login_id == "fx")).one()
        trips, _ = loader.load_for(sess, trader)
    assert mx.risk_figure_counts(trips).counts[s.RiskUnitSourceV1.DECLARED_BUDGET] == 40


def test_saving_the_default_is_still_recorded_as_retrospective(client, engine):
    """A date in the past is a number remembered, whoever filled the date in."""
    page = client.get("/budget").text
    client.post("/budget", data={
        "value": "3000", "unit": "INR", "effective_from": default_on(page),
        "csrf_token": TOKEN.search(page).group(1),
    })
    with make_session(engine) as sess:
        assert sess.scalars(select(m.RiskBudgetDeclaration)).one().retrospective is True
