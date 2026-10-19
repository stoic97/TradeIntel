"""The Mirror: counted facts, in the order PRD section 6 fixes, each with a drawer.

The page formats; it computes nothing. Every figure comes from
services/production/mirror/metrics.py, so there is one place each is decided and a
template cannot quietly invent a number.

The drawer is the cheapest trust mechanism in the product (PRD 6): a line a trader
cannot open is a claim he has to take on faith, and this product's whole argument is
that he should not have to.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from services.production.api.routes_consent import has_diagnosis_consent
from services.production.api.routes_identity import current_trader, page
from services.production.db.session import make_session
from services.production.mirror import loader
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s_enums

router = APIRouter()

DRAWERS = {
    "worst-days": "The five days, and every trade on them.",
    "best-worst-trades": "Your best five and worst five, by result.",
    "two-straight-losses": "Every trade opened after two that had already closed at a loss.",
    "holding-time": "How long each trade was open, by how it ended.",
    "by-hour": "Every trade, by the hour you opened it.",
}


def _mirror_context(trips: list[mx.Trip]) -> dict:
    """Every Appendix A figure, computed once."""
    return {
        "worst_days": mx.five_worst_days(trips),
        "share": mx.share_of_total(trips),
        "days": mx.day_counts(trips),
        "best": mx.best_five(trips),
        "worst": mx.worst_five(trips),
        "two_losses": mx.two_straight_losses(trips),
        "strike": mx.strike_rate(trips),
        "lots": mx.average_lots(trips),
        "holding": mx.holding_time(trips),
        "hours": mx.result_by_hour(trips),
        "run": mx.longest_losing_run(trips),
        "risk": mx.risk_figure_counts(trips),
        "trips": trips,
    }


def _comparison_context(trips: list[mx.Trip], two_losses) -> dict:
    """PRD 6.3: those trades against the rest, on strike rate and average lots."""
    after_losses = mx.subset(trips, two_losses.condition_trip_ids)
    the_rest = mx.complement(trips, two_losses.condition_trip_ids)
    return {
        "after_strike": mx.strike_rate(after_losses),
        "after_lots": mx.average_lots(after_losses),
        "rest_strike": mx.strike_rate(the_rest),
        "rest_lots": mx.average_lots(the_rest),
        "days_with_the_condition": len({t.trading_day for t in after_losses}),
    }


@router.get("/mirror", response_class=HTMLResponse)
def mirror(request: Request):
    with make_session(request.app.state.engine) as sess:
        trader = current_trader(request, sess)
        if trader is None:
            return RedirectResponse("/login", status_code=303)
        if not has_diagnosis_consent(sess, trader):
            return RedirectResponse("/consent", status_code=303)

        trips, imp = loader.load_for(sess, trader)
        if not trips:
            return page(request, "mirror_empty.html", title="Your record")
        context = _mirror_context(trips)
        context.update(_comparison_context(trips, context["two_losses"]))
        return page(request, "mirror.html", title="Your record",
                    imp=imp, drawers=DRAWERS,
                    sources=s_enums.RiskUnitSourceV1,
                    showable=s_enums.SHOWABLE_DENOMINATORS, **context)


@router.get("/mirror/{line}/drawer", response_class=HTMLResponse)
def drawer(request: Request, line: str):
    """The trades behind one line. An HTMX partial, so it opens in place."""
    with make_session(request.app.state.engine) as sess:
        trader = current_trader(request, sess)
        if trader is None:
            return HTMLResponse("", status_code=403)
        trips, imp = loader.load_for(sess, trader)
        if not trips or line not in DRAWERS:
            return HTMLResponse("", status_code=404)

        context = _mirror_context(trips)
        shown: list[mx.Trip] = trips
        if line == "worst-days":
            days = {d.trading_day for d in context["worst_days"].days}
            shown = [t for t in trips if t.trading_day in days]
        elif line == "best-worst-trades":
            shown = context["best"] + context["worst"]
        elif line == "two-straight-losses":
            ids = set(context["two_losses"].condition_trip_ids)
            shown = [t for t in trips if t.trip_id in ids]

        return page(request, "_drawer.html", title="Evidence",
                    line=line, caption=DRAWERS[line], shown=shown, imp=imp,
                    **context)
