"""Which denominator a trip gets, and why (PRD 5.5, TD-028).

The hierarchy: the declared budget in force at the trip's entry, else a stop the
export recorded, else the premium paid, else nothing. Only the first two may be a
denominator on a v1 screen; the other two are counted and never divided by.

The in-force rule is what makes a declaration honest across time. A trader who
declares Rs 5,000 in October has not retroactively been risking Rs 5,000 since
June, so June's trips take whatever was in force in June, or nothing.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from services.production.ctr.intake import persist
from services.production.ctr.intake import pipeline as pl
from services.production.db import models as m
from services.production.db.session import make_engine, make_session, run_migrations
from services.shared.schemas import scope_v1 as s

DUPES = Path("data/fixtures/duplicates")


@pytest.fixture()
def session():
    import os
    engine = make_engine(os.environ["SCOPE_DB"])
    run_migrations(engine)
    with make_session(engine) as sess:
        yield sess


def a_trader(session) -> m.Trader:
    trader = m.Trader(display_name="F", login_id="f", password_hash="x",
                      created_at=datetime.now(UTC))
    session.add(trader)
    session.flush()
    return trader


def declare(session, trader, value: str, effective_from: str) -> None:
    session.add(m.RiskBudgetDeclaration(
        trader_id=trader.id, value=Decimal(value), unit="INR",
        effective_from=effective_from, declared_at=datetime.now(UTC),
        retrospective=True))
    session.flush()


def an_import(session, trader) -> m.Import:
    plan = pl.plan_import(
        (DUPES / "clean.csv").read_text(),
        context=pl.ImportContext(trader_id=str(trader.id), source_account="A",
                                 code_version="risk"))
    return persist.write_plan(session, trader=trader, plan=plan,
                              raw_sha256="a" * 64, original_name="c.csv",
                              stored_path="/tmp/c", size=1)


def trips(session) -> list[m.Trip]:
    return list(session.scalars(select(m.Trip).order_by(m.Trip.entry_ts)).all())


def test_without_a_declaration_a_long_option_falls_back_to_the_premium(session):
    trader = a_trader(session)
    an_import(session, trader)
    session.commit()
    assert all(t.risk_unit_source is s.RiskUnitSourceV1.PREMIUM_PAID
               for t in trips(session))


def test_a_declaration_in_force_becomes_the_denominator(session):
    trader = a_trader(session)
    declare(session, trader, "3000", "2026-01-01")
    an_import(session, trader)
    session.commit()
    for trip in trips(session):
        assert trip.risk_unit_source is s.RiskUnitSourceV1.DECLARED_BUDGET
        assert trip.risk_unit_value == Decimal(3000)
        assert trip.risk_budget_ref is not None


def test_a_declaration_taking_effect_later_does_not_reach_back(session):
    """October's number is not June's number."""
    trader = a_trader(session)
    declare(session, trader, "5000", "2026-11-01")
    an_import(session, trader)
    session.commit()
    assert all(t.risk_unit_source is not s.RiskUnitSourceV1.DECLARED_BUDGET
               for t in trips(session))


def test_the_latest_declaration_in_force_wins(session):
    trader = a_trader(session)
    declare(session, trader, "3000", "2026-01-01")
    declare(session, trader, "4000", "2026-09-01")
    an_import(session, trader)
    session.commit()
    for trip in trips(session):
        assert trip.risk_unit_value == Decimal(4000)


def test_the_ctr_source_is_kept_alongside_the_product_one(session):
    """Two concepts, never conflated: what reconstruction knew, and what the
    product divides by."""
    trader = a_trader(session)
    declare(session, trader, "3000", "2026-01-01")
    an_import(session, trader)
    session.commit()
    for trip in trips(session):
        assert trip.ctr_risk_source == "PREMIUM_PAID", "what the CTR knew"
        assert trip.risk_unit_source is s.RiskUnitSourceV1.DECLARED_BUDGET


def test_a_budget_declared_after_the_import_still_reaches_the_mirror(session):
    """The order the PRD's flow actually puts these in (section 4).

    Upload, review, *then* the budget question. The trip rows are written during
    the import, before the trader has answered, and they are insert-only. So a
    denominator fixed at import time can never become the declared budget for the
    history that was just loaded: the trader answers the question and the Mirror
    goes on saying no trade has one.

    That is what the first walkthrough showed -- forty trades measured against
    premium paid, zero against the budget, with a declaration covering every one of
    them. Success criterion 4 and decision 15's "x your declared budget" label were
    both unreachable in the normal flow.
    """
    from services.production.mirror import loader

    trader = a_trader(session)
    an_import(session, trader)
    session.commit()

    stored = {t.risk_unit_source for t in trips(session)}
    assert stored == {s.RiskUnitSourceV1.PREMIUM_PAID}, (
        "at import time the premium is all the file supports"
    )

    declare(session, trader, "3000", "2026-01-01")
    session.commit()

    loaded, _ = loader.load_for(session, trader)
    assert loaded, "the fixture should produce trips"
    assert {t.risk_unit_source for t in loaded} == {
        s.RiskUnitSourceV1.DECLARED_BUDGET
    }, "the declaration is in force for these days, so it is the denominator"

    # Nothing was rewritten: the row still records what the file alone supported.
    assert {t.risk_unit_source for t in trips(session)} == {
        s.RiskUnitSourceV1.PREMIUM_PAID
    }


def test_a_later_declaration_leaves_earlier_trades_on_what_was_in_force(session):
    """The case that makes resolving-at-read-time correct rather than convenient."""
    from services.production.mirror import loader

    trader = a_trader(session)
    an_import(session, trader)
    declare(session, trader, "5000", "2030-01-01")
    session.commit()

    loaded, _ = loader.load_for(session, trader)
    assert {t.risk_unit_source for t in loaded} == {
        s.RiskUnitSourceV1.PREMIUM_PAID
    }, "a number that starts in 2030 was not what he risked in 2026"


def test_a_percentage_with_no_capital_is_not_a_denominator(session):
    """A percentage of nothing has no rupee value.

    The budget screen refuses this combination at the door. If one ever reaches the
    database, the figure must read as missing rather than as measured.
    """
    from services.production.accounts import risk_budget as rb

    trader = a_trader(session)
    session.add(m.RiskBudgetDeclaration(
        trader_id=trader.id, value=Decimal(2), unit="PCT",
        capital_amount=None, effective_from="2026-01-01",
        declared_at=datetime.now(UTC), retrospective=True))
    session.flush()

    declarations = rb.for_trader(session, trader)
    assert rb.in_force(declarations, "2026-10-14") is not None
    assert rb.rupees(rb.in_force(declarations, "2026-10-14")) is None


def test_a_correction_on_the_same_date_wins(session):
    from services.production.accounts import risk_budget as rb

    trader = a_trader(session)
    declare(session, trader, "3000", "2026-09-01")
    declare(session, trader, "4000", "2026-09-01")
    session.flush()

    declarations = rb.for_trader(session, trader)
    assert rb.rupees(rb.in_force(declarations, "2026-09-05")) == Decimal(4000)
