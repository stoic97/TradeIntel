"""Deleting your account, from the account page (PRD 3, PRD 10).

The consent screen promises this, so it is a button, not an email to the founder.
Two deliberate shapes:

**It asks twice, and the second time it says what cannot be undone.** Not a dark
pattern in reverse -- the page states plainly that looking at the data already
informed decisions about the engine, which no deletion reverses. Decision 21.

**The confirmation is shown, not sent.** There is no email service in v1 (ADR-007),
so the page that follows the deletion is the receipt. A trader who closes it has
still been told; the deletion record is what proves it happened.
"""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from services.production.accounts import auth, deletion
from services.production.accounts.file_store import FileStore
from services.production.api.routes_identity import current_trader, page, require_csrf
from services.production.db.session import make_session

router = APIRouter()


def _store(request: Request) -> FileStore:
    settings = request.app.state.settings
    return FileStore(settings.file_store, settings.file_key)


@router.get("/account/delete", response_class=HTMLResponse)
def delete_form(request: Request):
    with make_session(request.app.state.engine) as sess:
        trader = current_trader(request, sess)
        if trader is None:
            return RedirectResponse("/login", status_code=303)
        return page(request, "delete_confirm.html", title="Delete everything")


@router.post("/account/delete")
def delete_submit(
    request: Request,
    understood: str = Form(None),
    csrf_token: str = Form(None),
):
    if not require_csrf(request, csrf_token):
        return HTMLResponse("Form expired. Reload the page and try again.",
                            status_code=403)

    with make_session(request.app.state.engine) as sess:
        trader = current_trader(request, sess)
        if trader is None:
            return RedirectResponse("/login", status_code=303)

        if understood is None:
            return page(request, "delete_confirm.html", status_code=400,
                        title="Delete everything",
                        error="Tick the box if you want this done.")

        record = deletion.delete_trader(sess, _store(request), trader=trader)
        removed = record.what_removed
        retained = record.what_retained
        sess.commit()

    # hide_nav: the header would otherwise offer "Your account" and "Sign out"
    # for an account that no longer exists, because the cookie is still on the
    # request that renders this page.
    response = page(request, "delete_done.html", title="Deleted",
                    removed=removed, retained=retained, hide_nav=True)
    # His session points at an account that no longer exists. Clearing the cookie
    # is tidiness, not security: current_trader already finds nothing.
    response.delete_cookie(auth.SESSION_COOKIE)
    return response
