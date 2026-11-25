"""What we can and cannot check on this history (PRD 5.6).

Stated before the Mirror, because a trader should know the shape of what he is
about to read before he reads it -- and because the checks that cannot run are a
fact about the product, not about him.

Two things this page refuses to do.

It does not name the library's checks in its own words. The framework calls them
things like ``overall_edge``, and "edge" is on the never-use list (PRD 7.5): the
product does not tell a trader he has one or has not. Inventing nineteen
replacement descriptions would be writing research content that is the research
seat's to write. So the page counts the checks by what they are waiting on, which is
the part we do own, and identifiers and minimums sit behind a toggle (TICKET-829).

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
from services.production.mirror import metrics as mx
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
        # Ruling A, 24 Nov: this page counts every round trip and chapter 3 counts
        # same-day trades, so B2's count can differ between them. Both are passed; the template
        # draws its line only when they do.
        b2 = next((v for v in result.verdicts if v.test.id == "B2"), None)
        report_count = mx.two_straight_losses(mx.same_day_trips(trips)).condition
        b2_differs = b2 is not None and b2.have is not None and b2.have != report_count
        return page(
            request, "eligibility.html", title="What we can check",
            result=result, trips=len(trips),
            days=len({t.trading_day for t in trips}),
            framework=framework, b2_differs=b2_differs,
            b2_page_count=b2.have if b2 else None, b2_report_count=report_count,
            draft=framework.lock is not reader.LockState.LOCKED,
        )
