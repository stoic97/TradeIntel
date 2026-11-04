"""The front door and the signed-in home (handoff 5: screens 0 and 20).

Signed out, "/" is the navy door: invitation only, and the way back in. Signed in
with a record, it is home - the headline card that opens the Scope, the latest
Journals, and the upload. Signed in without a record yet, it sends the trader where
landing_for says he belongs, because a home with nothing on it is not a destination.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from services.production.api import formatting
from services.production.api import scope_facts as SF
from services.production.api.routes_identity import current_trader, landing_for, page
from services.production.api.routes_journal import trades_of, trips_of
from services.production.db.session import make_session
from services.production.journal import generate as gen
from services.production.mirror import loader

router = APIRouter()

LATEST_ON_HOME = 3
"""Journal rows on home; the Journal tab has the rest."""


def _period(journal) -> str:
    start, end = formatting.day(journal.period_start), formatting.day(journal.period_end)
    return start if start == end else f"{start} – {end}"


@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    with make_session(request.app.state.engine) as sess:
        trader = current_trader(request, sess)
        if trader is None:
            return page(request, "home.html", title="Scope")
        trips, imp = loader.load_for(sess, trader)
        if not trips:
            return RedirectResponse(landing_for(sess, trader), status_code=303)
        latest = []
        for journal in gen.surface(sess, trader=trader).latest[:LATEST_ON_HOME]:
            covered = trips_of(sess, trader, journal)
            latest.append(
                {
                    "id": journal.id,
                    "period": _period(journal),
                    "trades": len(trades_of(covered)),
                    "net": sum(t.net for t in covered),
                }
            )
        share = SF.record_context(trips)["share"]
        return page(
            request,
            "home_signed_in.html",
            title="Home",
            trader_name=trader.display_name,
            imp=imp,
            imported=formatting.day(imp.created_at.date().isoformat()),
            share=share,
            latest=latest,
        )
