"""The risk budget declaration (PRD 5.5).

Two questions, and the second is the one most products would skip: not just how much
he is willing to lose on a trade, but whether that has been his number for the whole
history he uploaded. A budget without an effective date tells you nothing about the
trades it is meant to divide.

Three refusals, each protecting a number a trader will later read:

**A percentage without the capital amount.** A percentage of nothing has no rupee
value, and every trip measured against it would be silently wrong rather than
visibly missing.

**A future effective date.** A budget for trades he has not taken says nothing about
the history he uploaded.

**Zero or less.** Not a budget, and a denominator of zero is not a number.

Declarations are never edited. A new number is a new row, so October's trips keep
October's -- the lookup is by the declaration in force at each trip's entry.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from services.production.api.routes_consent import has_diagnosis_consent
from services.production.api.routes_identity import current_trader, page, require_csrf
from services.production.db import models as m
from services.production.db.session import make_session

router = APIRouter()

TRADER_ZONE = ZoneInfo("Asia/Kolkata")
"""The zone a declaration's 'today' is read in.

_today() would use the SERVER's zone, so a trader declaring at 01:00 IST on a
UTC server would have his declaration dated yesterday -- and a declaration dated
yesterday is marked retrospective when it is not. v1 launches in India; a trader
abroad gets his instrument profile's zone when TD-026 is closed.
"""


def _today() -> date:
    return datetime.now(TRADER_ZONE).date()


def _history(sess, trader: m.Trader) -> list[m.RiskBudgetDeclaration]:
    return list(sess.scalars(
        select(m.RiskBudgetDeclaration)
        .where(m.RiskBudgetDeclaration.trader_id == trader.id)
        .order_by(m.RiskBudgetDeclaration.effective_from.desc(),
                  m.RiskBudgetDeclaration.id.desc())
    ).all())


@router.get("/budget", response_class=HTMLResponse)
def budget_form(request: Request):
    with make_session(request.app.state.engine) as sess:
        trader = current_trader(request, sess)
        if trader is None:
            return RedirectResponse("/login", status_code=303)
        if not has_diagnosis_consent(sess, trader):
            return RedirectResponse("/consent", status_code=303)
        return page(request, "budget.html", title="What you risk",
                    declarations=_history(sess, trader),
                    today=_today().isoformat())


@router.post("/budget")
def budget_submit(
    request: Request,
    value: str = Form(...),
    unit: str = Form(...),
    effective_from: str = Form(...),
    capital_amount: str = Form(None),
    csrf_token: str = Form(None),
):
    if not require_csrf(request, csrf_token):
        return HTMLResponse("Form expired. Reload the page and try again.", status_code=403)

    with make_session(request.app.state.engine) as sess:
        trader = current_trader(request, sess)
        if trader is None:
            return RedirectResponse("/login", status_code=303)
        if not has_diagnosis_consent(sess, trader):
            return RedirectResponse("/consent", status_code=303)

        def refuse(message: str) -> HTMLResponse:
            return page(request, "budget.html", status_code=400,
                        title="What you risk", error=message,
                        declarations=_history(sess, trader),
                        today=_today().isoformat())

        try:
            amount = Decimal(value)
        except (InvalidOperation, TypeError):
            return refuse("That is not a number.")
        if amount <= 0:
            return refuse("A budget has to be more than zero.")

        if unit not in ("INR", "PCT"):
            return refuse("Choose rupees or a percentage of your capital.")

        capital = None
        if unit == "PCT":
            try:
                capital = Decimal(capital_amount) if capital_amount else None
            except (InvalidOperation, TypeError):
                capital = None
            if capital is None or capital <= 0:
                return refuse(
                    "A percentage needs your trading capital in rupees — without it "
                    "there is no rupee figure to measure a trade against."
                )

        try:
            effective = date.fromisoformat(effective_from)
        except ValueError:
            return refuse("That is not a date.")
        if effective > _today():
            return refuse(
                "That date is in the future. This is about the trades you have "
                "already taken."
            )

        sess.add(m.RiskBudgetDeclaration(
            trader_id=trader.id,
            value=amount,
            unit=unit,
            capital_amount=capital,
            effective_from=effective.isoformat(),
            declared_at=datetime.now(UTC),
            retrospective=effective < _today(),
        ))
        sess.commit()
    return RedirectResponse("/budget", status_code=303)
