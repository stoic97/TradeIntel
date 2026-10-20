"""Which declared budget a trade is measured against.

PRD 5.5 keeps two things apart: what a trader *intends* to risk -- his declared
budget, with an effective range -- and what a given trade's result is divided by.
This module answers the first half: which declaration was in force when a trade was
opened, and what that declaration is worth in rupees.

**Why it is resolved when the figure is read, not when the file is imported.** The
PRD's own flow (section 4) declares the budget *after* the import: upload, review,
then the budget question. Trips are insert-only. So a denominator decided during
the import can never become the declared budget for the history that was just
loaded -- the trader answers the question and the Mirror goes on reporting that no
trade has a declared-budget denominator. That was true of every trade in the first
walkthrough: forty measured against premium paid, zero against the budget, with a
declaration covering the whole period.

Resolving it at the point of reading also gets the harder case right for free. A
trader who declares a new number in November leaves October's trips on October's,
because the question asked of each trip is always "what was in force when this was
opened", never "what is in force now".
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from services.production.db import models as m


def for_trader(sess: Session, trader: m.Trader) -> list[m.RiskBudgetDeclaration]:
    """Every declaration this trader has made, oldest first."""
    return list(sess.scalars(
        select(m.RiskBudgetDeclaration)
        .where(m.RiskBudgetDeclaration.trader_id == trader.id)
        .order_by(m.RiskBudgetDeclaration.effective_from,
                  m.RiskBudgetDeclaration.id)
    ).all())


def in_force(
    declarations: list[m.RiskBudgetDeclaration], trading_day: str
) -> m.RiskBudgetDeclaration | None:
    """The declaration covering this trading day, or none.

    The latest one whose effective_from is on or before the day. A number declared
    in November is not what he was risking in September, and treating it as such
    would make every figure measured against it quietly wrong -- the kind of wrong
    that looks like a real result.

    Two declarations sharing an effective_from are a correction, so the later row
    wins: ``id`` breaks the tie.
    """
    covering = [d for d in declarations if d.effective_from <= trading_day]
    if not covering:
        return None
    return max(covering, key=lambda d: (d.effective_from, d.id))


def rupees(declaration: m.RiskBudgetDeclaration | None) -> Decimal | None:
    """What the declaration is worth on one trade, in rupees.

    ``None`` when there is no declaration, or when it is a percentage with no
    capital amount behind it -- a percentage of nothing has no rupee value, and a
    figure divided by it would be silently wrong rather than visibly missing. The
    budget screen refuses that combination at the door; this is the second lock.
    """
    if declaration is None:
        return None
    if declaration.unit == "INR":
        return declaration.value
    if declaration.capital_amount:
        return declaration.capital_amount * declaration.value / Decimal(100)
    return None
