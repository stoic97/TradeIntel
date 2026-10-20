"""What we can and cannot check on this history (PRD 5.6).

Stated before the Mirror, because a trader should know the shape of what he is
about to read before he reads it -- and because the checks that cannot run are a
fact about the product, not about him.

Two things this page refuses to do.

It does not name the library's checks in its own words. The framework calls them
things like ``overall_edge``, and "edge" is on the never-use list (PRD 7.5): the
product does not tell a trader he has one or has not. Inventing nineteen
replacement descriptions would be writing research content that is the research
seat's to write. So each check is named by its identifier and explained by what it
needs, which is the part we do own.

It does not present a draft framework as a locked one. The thresholds on this page
are pre-registered -- fixed before anyone looked at a trader's data -- and that is
the whole reason they are worth reading. Until the kickoff lock, the page says so.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from services.production.api.routes_consent import has_diagnosis_consent
from services.production.api.routes_identity import current_trader, page
from services.production.ctr.profiles import registry as profiles
from services.production.db.session import make_session
from services.production.eligibility import assess as el
from services.production.mirror import loader
from services.shared.prereg import reader

router = APIRouter()


@router.get("/eligibility", response_class=HTMLResponse)
def eligibility_page(request: Request):
    with make_session(request.app.state.engine) as sess:
        trader = current_trader(request, sess)
        if trader is None:
            return RedirectResponse("/login", status_code=303)
        if not has_diagnosis_consent(sess, trader):
            return RedirectResponse("/consent", status_code=303)

        framework = reader.load()
        if framework.lock is reader.LockState.TAMPERED:
            # The case the lock exists to catch. Every threshold below would be a
            # number nobody agreed to, shown as one everybody did.
            return page(request, "eligibility_unreadable.html", status_code=503,
                        title="We cannot say yet")

        try:
            trips, imp = loader.load_for(sess, trader)
        except profiles.UnknownInstrument:
            return page(request, "eligibility_unreadable.html", status_code=503,
                        title="We cannot say yet")

        if imp is None:
            return RedirectResponse("/upload", status_code=303)

        result = el.assess(trips, framework)
        return page(
            request, "eligibility.html", title="What we can check",
            result=result, trips=len(trips),
            days=len({t.trading_day for t in trips}),
            framework=framework,
            draft=framework.lock is not reader.LockState.LOCKED,
        )
