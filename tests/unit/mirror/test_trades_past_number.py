"""How many trades lost more than the trader's own number [TICKET-831].

A count, not a score: he chose the number, and the count says nothing about whether it
should be different. One function in metrics.py decides it and both /budget and the risk
fact read that function, so they cannot disagree.

Synthetic throughout, and worked by hand from HISTORY below. The number is ₹500 from
2026-09-03, then 2% of ₹50,000 (₹1,000) from 2026-09-07.

    id  opened  closed  net       against  counted?
    a   09-01   09-01   -900      none     no: before the number's date
    b   09-02   09-04   -2000     none     no: held past the day, and before the date
    c   09-03   09-03   -500      500      no: exactly the number is not more than it
    d   09-03   09-03   -500.01   500      YES
    e   09-04   09-04   -700      500      YES
    f   09-04   09-04   +800      500      no: a gain
    g   09-07   09-07   -700      1000     no: the same loss as e, under the later number
    h   09-07   09-07   -1000     1000     no: exactly the number again, from the percentage
    i   09-08   09-08   -1500     1000     YES
    j   09-08   09-09   -1800     1000     no: held past the day
    k   09-09   09-09   0         1000     no: a scratch
    l   09-09   09-09   -1200     1000     YES: a sold option, whose rupees are known

Counted: d, e, i, l = 4. Measured: c, d, e, f, g, h, i, k, l = 9. Same-day before the
date: a = 1. Held past the day: b, j = 2.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from services.production.api.routes_budget import _today
from services.production.db import models as m
from services.production.db.session import make_session
from services.production.mirror import loader
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s

TOKEN = re.compile(r'name="csrf_token"\s+value="([^"]+)"')
COUNT = re.compile(r"(\d+) trades? lost more than your number\.")
OLD, NEW = Decimal(500), Decimal(1000)

HISTORY = [
    ("a", "09-01", "09-01", "-900", None),
    ("b", "09-02", "09-04", "-2000", None),
    ("c", "09-03", "09-03", "-500", OLD),
    ("d", "09-03", "09-03", "-500.01", OLD),
    ("e", "09-04", "09-04", "-700", OLD),
    ("f", "09-04", "09-04", "800", OLD),
    ("g", "09-07", "09-07", "-700", NEW),
    ("h", "09-07", "09-07", "-1000", NEW),
    ("i", "09-08", "09-08", "-1500", NEW),
    ("j", "09-08", "09-09", "-1800", NEW),
    ("k", "09-09", "09-09", "0", NEW),
    ("l", "09-09", "09-09", "-1200", NEW),
]
UNCAPPED = "l"


def trip(name, opened, closed, net, number) -> mx.Trip:
    """A ten-minute trade, opened at 10:00 IST on the day and closed on its closing day."""
    entry = datetime.fromisoformat(f"2026-{opened}T10:00:00+05:30")
    exit_ = datetime.fromisoformat(f"2026-{closed}T10:10:00+05:30")
    source = s.RiskUnitSourceV1.UNAVAILABLE if name == UNCAPPED else s.RiskUnitSourceV1.PREMIUM_PAID
    return mx.Trip(
        trip_id=name, symbol="WIDGETOIL", trading_day=entry.date().isoformat(), entry_ts=entry,
        exit_ts=exit_, holding_seconds=int((exit_ - entry).total_seconds()), net=Decimal(net),
        lots=1, risk_unit_source=source, number_in_force=number,
    )


def trips(rows=HISTORY) -> list[mx.Trip]:
    return [trip(*row) for row in rows]


# ---- the function that decides the count


def test_the_count_on_the_hand_worked_history():
    past = mx.trades_past_number(trips())
    assert past.count == 4
    assert past.trip_ids == ["d", "e", "i", "l"]
    assert past.state is s.ResultState.COUNTED_FACT


def test_the_trades_it_was_read_across():
    past = mx.trades_past_number(trips())
    assert (past.measured, past.before_number, past.held_past_day) == (9, 1, 2)


def test_a_loss_exactly_equal_to_the_number_is_not_more_than_it():
    assert "c" not in mx.trades_past_number(trips()).trip_ids
    assert "h" not in mx.trades_past_number(trips()).trip_ids


def test_a_paisa_past_the_number_is_more_than_it():
    assert "d" in mx.trades_past_number(trips()).trip_ids


def test_apportioning_dust_does_not_tip_a_loss_past_the_number():
    """Fill values split across parcels leave long decimals. A loss is compared in paise."""
    dust = trips([("x", "09-03", "09-03", "-500.00000000000000000001", OLD)])
    assert mx.trades_past_number(dust).count == 0


def test_a_trade_before_the_numbers_date_is_not_measured():
    assert "a" not in mx.trades_past_number(trips()).trip_ids


def test_a_position_held_past_the_day_is_not_counted_however_large():
    ids = mx.trades_past_number(trips()).trip_ids
    assert "b" not in ids
    assert "j" not in ids


def test_each_trade_is_measured_against_the_number_in_force_that_day():
    """The same ₹700 loss: past the ₹500 in force on the 4th, not the ₹1,000 on the 7th."""
    ids = mx.trades_past_number(trips()).trip_ids
    assert "e" in ids
    assert "g" not in ids


def test_a_trade_with_no_risk_figure_counts_when_its_rupees_are_past_the_number():
    """Annex H section 6: a declared budget outranks a risk figure. The count reads rupees."""
    assert "l" in mx.trades_past_number(trips()).trip_ids


def test_with_no_number_in_force_nothing_is_measured():
    past = mx.trades_past_number(trips([("a", "09-01", "09-01", "-900", None)]))
    assert (past.count, past.measured) == (0, 0)
    assert past.state is s.ResultState.INSUFFICIENT_SAMPLE


def test_with_no_trades_nothing_is_measured():
    past = mx.trades_past_number([])
    assert (past.count, past.measured, past.before_number, past.held_past_day) == (0, 0, 0, 0)
    assert past.state is s.ResultState.INSUFFICIENT_SAMPLE


# ---- what the loader reads


def add_history(engine, rows=HISTORY, exchange="MCX") -> None:
    """HISTORY as his newest import, which is the one the record reads."""
    with make_session(engine) as sess:
        previous = sess.scalars(select(m.Import)).first()
        imp = m.Import(
            trader_id=previous.trader_id, raw_file_id=previous.raw_file_id, source_account="A",
            adapter_id="dhan_tradebook_v1", adapter_version="1", filemap_version="1",
            code_version="fixturesha", outcome=s.ImportOutcome.ACCEPTED_PARTIAL_FIELDS,
            rows_in=len(rows), rows_parsed=len(rows), rows_excluded=0, fees_available=False,
            version_no=2, trips_reconstructed=len(rows), trips_refused=0,
            density_default_unit="day", created_at=datetime.now(UTC),
        )
        sess.add(imp)
        sess.flush()
        for name, opened, closed, net, _number in rows:
            source = (
                s.RiskUnitSourceV1.UNAVAILABLE if name == UNCAPPED
                else s.RiskUnitSourceV1.PREMIUM_PAID
            )
            sess.add(m.Trip(
                import_id=imp.id, trip_id=name, trading_day=f"2026-{opened}", exchange=exchange,
                symbol="WIDGETOIL", segment="OPT",
                direction="SHORT" if name == UNCAPPED else "LONG",
                entry_ts=datetime.fromisoformat(f"2026-{opened}T10:00:00+05:30"),
                exit_ts=datetime.fromisoformat(f"2026-{closed}T10:10:00+05:30"),
                quantity=100, entry_price=Decimal(100), exit_price=Decimal(100),
                gross=Decimal(net), fees=Decimal(0), net=Decimal(net), fees_available=False,
                risk_unit_source=source,
            ))
        sess.commit()


def record(client, value="500", unit="INR", effective_from="2026-09-03", capital=None,
           follow_redirects=True):
    token = TOKEN.search(client.get("/budget").text).group(1)
    data = {"value": value, "unit": unit, "effective_from": effective_from, "csrf_token": token}
    if capital:
        data["capital_amount"] = capital
    return client.post("/budget", data=data, follow_redirects=follow_redirects)


def record_both_numbers(client) -> None:
    record(client)
    record(client, value="2", unit="PCT", capital="50000", effective_from="2026-09-07")


def numbers_on(engine) -> dict[str, Decimal | None]:
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader).where(m.Trader.login_id == "fx")).one()
        loaded, _ = loader.load_for(sess, trader)
    return {t.trip_id: t.number_in_force for t in loaded}


def test_the_loader_gives_each_trade_the_number_in_force_that_day(client, engine):
    add_history(engine)
    record_both_numbers(client)
    assert numbers_on(engine) == {name: number for name, _o, _c, _n, number in HISTORY}


def test_with_no_number_set_the_loader_gives_no_trade_a_number(client, engine):
    add_history(engine)
    assert set(numbers_on(engine).values()) == {None}


def test_the_loader_reads_the_day_in_the_instruments_zone(client, engine):
    """00:30 IST on the 3rd is still the 2nd in UTC, and the number starts on the 3rd."""
    add_history(engine, [("x", "09-03", "09-03", "-600", OLD)])
    with make_session(engine) as sess:
        imp = sess.scalars(select(m.Import).order_by(m.Import.id.desc())).first()
        stored = sess.scalars(select(m.Trip).where(m.Trip.import_id == imp.id)).one()
        sess.add(m.Trip(
            import_id=imp.id, trip_id="y", trading_day="2026-09-03", exchange=stored.exchange,
            symbol=stored.symbol, segment=stored.segment, direction=stored.direction,
            entry_ts=datetime.fromisoformat("2026-09-03T00:30:00+05:30"),
            exit_ts=datetime.fromisoformat("2026-09-03T00:40:00+05:30"),
            quantity=stored.quantity, entry_price=stored.entry_price,
            exit_price=stored.exit_price, gross=stored.gross, fees=stored.fees, net=stored.net,
            fees_available=False, risk_unit_source=stored.risk_unit_source,
        ))
        sess.commit()
    record(client)
    assert numbers_on(engine)["y"] == OLD


# ---- the two pages


def readable(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def counted_on(html: str) -> int:
    return int(COUNT.search(readable(html)).group(1))


def test_after_record_it_the_page_it_lands_on_is_the_budget_page(client, engine):
    add_history(engine)
    sent = record(client, follow_redirects=False)
    assert (sent.status_code, sent.headers["location"]) == (303, "/budget")


def test_after_record_it_the_page_shows_the_count(client, engine):
    add_history(engine)
    landed = record(client)
    # Against ₹500 from the 3rd alone, with no later number: d, e, g, h, i, l = 6.
    assert counted_on(landed.text) == 6


def test_the_rupee_and_the_percentage_read_the_same_number(client, engine):
    """2% of ₹25,000 is ₹500, so this is the rupee test's history and its answer."""
    add_history(engine)
    landed = record(client, value="2", unit="PCT", capital="25000")
    assert counted_on(landed.text) == 6


def test_a_number_that_changed_counts_each_trade_against_its_own_day(client, engine):
    add_history(engine)
    record_both_numbers(client)
    assert counted_on(client.get("/budget").text) == 4


def test_the_risk_fact_shows_the_same_count(client, engine):
    add_history(engine)
    record_both_numbers(client)
    assert counted_on(client.get("/mirror/fact/risk").text) == 4


def test_the_two_pages_read_one_function_so_they_cannot_disagree(client, engine, monkeypatch):
    add_history(engine)
    record_both_numbers(client)
    decided = mx.TradesPastNumber(
        count=77, trip_ids=[], measured=90, before_number=0, held_past_day=0,
        state=s.ResultState.COUNTED_FACT,
    )
    monkeypatch.setattr(mx, "trades_past_number", lambda _trips: decided)
    assert counted_on(client.get("/budget").text) == 77
    assert counted_on(client.get("/mirror/fact/risk").text) == 77


def test_both_pages_state_the_basis(client, engine):
    add_history(engine)
    record_both_numbers(client)
    for path in ("/budget", "/mirror/fact/risk"):
        page = readable(client.get(path).text)
        assert (
            "Same-day trades only: 9 of them, each against the number in force "
            "the day it was opened."
        ) in page
        assert "1 same-day trade before your number's date is not measured." in page
        assert "2 positions held past the day are not counted here." in page


def test_the_basis_says_nothing_of_trades_that_are_not_there(client, engine):
    add_history(engine, [("c", "09-03", "09-03", "-600", OLD)])
    record(client)
    page = readable(client.get("/budget").text)
    assert "Same-day trades only: 1 of them," in page
    assert "before your number's date" not in page
    assert "held past the day" not in page


def test_one_trade_is_written_as_one_trade(client, engine):
    add_history(engine, [("c", "09-03", "09-03", "-600", OLD)])
    record(client)
    page = readable(client.get("/budget").text)
    assert "1 trade lost more than your number." in page


def test_a_count_of_nothing_is_still_a_count(client, engine):
    add_history(engine, [("c", "09-03", "09-03", "-100", OLD)])
    record(client)
    assert counted_on(client.get("/budget").text) == 0
    assert counted_on(client.get("/mirror/fact/risk").text) == 0


@pytest.mark.parametrize("path", ["/budget", "/mirror/fact/risk"])
def test_with_no_number_set_nothing_about_the_count_shows(client, engine, path):
    add_history(engine)
    page = client.get(path).text
    assert "lost more than" not in page
    assert "Same-day trades only" not in page
    assert "before your number" not in page


def test_with_a_number_after_every_trade_there_is_no_count_and_the_page_says_so(client, engine):
    """A zero here would read as a clean record, when nothing was measured at all."""
    add_history(engine)
    record(client, effective_from=_today().isoformat())
    budget = readable(client.get("/budget").text)
    assert "lost more than" not in budget
    assert "No same-day trade in your file is on or after your number's date." in budget
    assert "lost more than" not in client.get("/mirror/fact/risk").text


def test_with_a_number_and_no_upload_nothing_about_the_count_shows(engine):
    """A trader can answer before he uploads: there is no file to count from."""
    from fastapi.testclient import TestClient

    from services.production.api.app import create_app
    from tests.unit.api.test_upload import sign_up

    fresh = sign_up(TestClient(create_app()), engine, "N-1", "noupload")
    record(fresh)
    page = fresh.get("/budget").text
    assert "lost more than" not in page
    assert "No same-day trade" not in page


def test_an_instrument_with_no_profile_leaves_the_budget_page_usable(client, engine):
    """The Mirror says what is wrong with the file; this page only has no count to give."""
    add_history(engine, exchange="NOWHERE")
    landed = record(client)
    assert landed.status_code == 200
    assert "lost more than" not in landed.text


def test_with_a_number_recorded_the_page_goes_on_to_the_record(client, engine):
    """It used to redirect there, and landing here must not leave the journey at a dead end."""
    add_history(engine)
    assert 'href="/mirror">See your record' not in client.get("/budget").text
    assert 'href="/mirror">See your record' in record(client).text


def test_the_budget_page_says_its_rupees_are_gross_when_the_file_has_no_charges(client, engine):
    add_history(engine)
    record(client)
    assert "so these losses are gross — before brokerage and taxes." in client.get("/budget").text


def test_a_correction_on_the_same_date_replaces_the_number(client, engine):
    """Two declarations sharing a date: the later row wins, in the count as everywhere."""
    add_history(engine, [("c", "09-03", "09-03", "-600", OLD)])
    record(client)
    assert counted_on(client.get("/budget").text) == 1
    record(client, value="700")
    assert counted_on(client.get("/budget").text) == 0


def test_a_refused_number_adds_no_count(client, engine):
    add_history(engine)
    tomorrow = (_today() + timedelta(days=1)).isoformat()
    refused = record(client, effective_from=tomorrow)
    assert refused.status_code == 400
    assert "lost more than" not in refused.text
