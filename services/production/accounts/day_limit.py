"""Which declared day limit a trading day is measured against (TICKET-974).

The same shape as risk_budget: a declaration is never edited, a new limit is a new row, and
the question asked of each trading day is "what was in force when this day was traded", never
"what is in force now". One difference, ruled on the ticket: a day limit takes no retrospective
``effective_from``. It counts from the day it was declared, so trades before that day are not
counted against it and nothing shows them as if it had been in force.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from services.production.db import models as m

TRADER_ZONE = ZoneInfo("Asia/Kolkata")


def counted_from(declared_at: datetime) -> str:
    """The India day a declaration counts from: the day it was made, never an earlier one."""
    return declared_at.astimezone(TRADER_ZONE).date().isoformat()


def for_trader(sess: Session, trader: m.Trader) -> list[m.DayLimitDeclaration]:
    """Every day limit this trader has declared, oldest first."""
    return list(sess.scalars(
        select(m.DayLimitDeclaration)
        .where(m.DayLimitDeclaration.trader_id == trader.id)
        .order_by(m.DayLimitDeclaration.effective_from, m.DayLimitDeclaration.id)
    ).all())


def in_force(
    declarations: list[m.DayLimitDeclaration], trading_day: str
) -> m.DayLimitDeclaration | None:
    """The limit declared at or before this trading day, the latest of them, or none.

    Two declarations on one day: the later row wins, as in risk_budget.
    """
    covering = [d for d in declarations if d.effective_from <= trading_day]
    return max(covering, key=lambda d: (d.effective_from, d.id)) if covering else None


def rupees(declaration: m.DayLimitDeclaration | None) -> Decimal | None:
    return declaration.value if declaration is not None else None
