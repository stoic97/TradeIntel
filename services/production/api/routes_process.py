"""Your process, at /process: the rows of ``process.ROWS`` over the report's own record, under the
report's year and book filter, as /numbers reads it. Beside each line, the earlier reading's figure
when he has one. Nothing is computed here (process.build)."""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from services.production.api import process as P
from services.production.api import process_bars
from services.production.api import report_filter as RF
from services.production.api.routes_identity import page
from services.production.api.routes_mirror import load_record
from services.production.ctr.intake import persist
from services.production.db import models as m
from services.production.db.session import make_session
from services.production.mirror import loader

router = APIRouter()


def capital_told(sess, trader_id: int) -> Decimal | None:
    """The capital in his latest risk number, if he told us one."""
    row = sess.scalars(select(m.RiskBudgetDeclaration)
                       .where(m.RiskBudgetDeclaration.trader_id == trader_id)
                       .order_by(m.RiskBudgetDeclaration.declared_at.desc(), m.RiskBudgetDeclaration.id.desc())
                       .limit(1)).first()
    return row.capital_amount if row is not None and row.capital_amount else None


@router.get("/process", response_class=HTMLResponse)
def your_process(request: Request):
    early, record = load_record(request)
    if early is not None:
        return early
    trips, imp, _context = record
    earlier = None
    with make_session(request.app.state.engine) as sess:
        capital = capital_told(sess, imp.trader_id)
        figures = process_bars.stored(sess, imp.id)
        ranges = process_bars.ranges(sess, imp.id)
        before = persist.earlier_reading(sess, imp)
        if before is not None:
            trader = sess.get(m.Trader, imp.trader_id)
            old, _imp = loader.load_for(sess, trader, imp=before)
            chosen = RF.valid(RF.decode(request.cookies.get(RF.COOKIE)), old, None)
            earlier = P.Reading(RF.apply(old, chosen, None), capital=capital,
                                figures=process_bars.stored(sess, before.id),
                                ranges=process_bars.ranges(sess, before.id))
    rows = P.build(P.Reading(trips, capital=capital, figures=figures, ranges=ranges), earlier)
    return page(request, "process.html", title="Your process", imp=imp, rows=rows,
                trades=len(trips), earlier=earlier is not None)
