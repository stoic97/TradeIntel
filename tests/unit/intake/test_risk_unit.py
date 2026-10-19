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
