"""The front door and the signed-in home (handoff 5: screens 0 and 20).

Signed out, "/" is the navy door: sign-up on the page, and the way back in. Signed in
with a record, it is home - the verdict that opens the report, the days worth a look,
and the upload. Signed in without a record yet, it sends the trader where
landing_for says he belongs, because a home with nothing on it is not a destination.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from services.production.api import days_worth_a_look as worth
from services.production.api import door
from services.production.api import formatting
from services.production.api.routes_consent import has_diagnosis_consent
from services.production.api.routes_identity import current_trader, landing_for, page
from services.production.api.routes_journal import trades_of, trips_of
from services.production.db.session import make_session
from services.production.journal import generate as gen
from services.production.mirror import loader
from services.production.mirror import metrics as mx

router = APIRouter()

DAYS_ON_HOME = 3
"""Journal rows on home; the Journal tab has the rest."""


def _period(journal) -> str:
    start, end = formatting.day(journal.period_start), formatting.day(journal.period_end)
    return start if start == end else f"{start} – {end}"


@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    with make_session(request.app.state.engine) as sess:
        trader = current_trader(request, sess)
        if trader is None:
            return page(request, "home.html", title="Scope",
                        said=door.said(request.query_params.get("said")))
        trips, imp = loader.load_for(sess, trader)
        if not trips:
            return RedirectResponse(landing_for(sess, trader), status_code=303)
        if not has_diagnosis_consent(sess, trader):
            return RedirectResponse("/consent", status_code=303)
        # The first of the same list the Journal tab leads with, so the two can't disagree.
        flags = worth.flags_by_day(trips)
        named = worth.to_start_with(gen.newest_first(sess, trader=trader), flags)[:DAYS_ON_HOME]
        shown = named or gen.surface(sess, trader=trader).latest[:DAYS_ON_HOME]
        latest = []
        for journal in shown:
            covered = trips_of(sess, trader, journal)
            latest.append(
                {
                    "id": journal.id,
                    "period": _period(journal),
                    "trades": len(trades_of(covered)),
                    "net": sum(t.net for t in covered),
                    "why": " · ".join(f.label for f in flags[journal.period_start])
                    if named else None,
                }
            )
        return page(
            request,
            "home_signed_in.html",
            title="Home",
            trader_name=trader.display_name,
            imp=imp,
            imported=formatting.local_day(imp.created_at),
            verdict=mx.verdict(trips),
            latest=latest,
            days_heading="Days worth a look" if named else "Latest Journals",
        )
