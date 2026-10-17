"""The consent screen, the ledger, and withdrawal.

Consent is checked by a dependency on every path that touches a trader's data, not
by remembering to check. ``require_consent`` is what the upload route and everything
downstream of it sit behind, so the route simply cannot be reached without a current
grant for DIAGNOSIS.

A withdrawal is a new row. Nothing is edited and nothing is deleted, so the ledger
reads as a history: granted on this date, withdrawn on that one, with the wording
shown at each point.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from services.production.accounts import consent as cs
from services.production.api.routes_identity import current_trader, page, require_csrf
from services.production.db import models as m
from services.production.db.session import make_session
from services.shared.schemas import scope_v1 as s

router = APIRouter()


def consent_state(sess, trader: m.Trader) -> dict[s.ConsentPurpose, bool]:
    """The latest decision per purpose. Absent means never asked."""
    events = sess.scalars(
        select(m.ConsentEvent)
        .where(m.ConsentEvent.trader_id == trader.id)
        .order_by(m.ConsentEvent.id)
    ).all()
    state: dict[s.ConsentPurpose, bool] = {}
    for event in events:
        state[event.purpose] = event.granted
    return state


def has_diagnosis_consent(sess, trader: m.Trader) -> bool:
    return consent_state(sess, trader).get(s.ConsentPurpose.DIAGNOSIS, False)


@router.get("/consent", response_class=HTMLResponse)
def consent_form(request: Request):
    with make_session(request.app.state.engine) as sess:
        trader = current_trader(request, sess)
        if trader is None:
            return RedirectResponse("/login", status_code=303)
        text = cs.require_reviewed(cs.CURRENT, development_data=trader.development_data)
        return page(request, "consent.html", title="Before you upload",
                    text=text, state=consent_state(sess, trader))


@router.post("/consent")
def consent_submit(
    request: Request,
    diagnosis: str = Form(None),
    engine_testing: str = Form(None),
    csrf_token: str = Form(None),
):
    if not require_csrf(request, csrf_token):
        return HTMLResponse("Form expired. Reload the page and try again.", status_code=403)

    with make_session(request.app.state.engine) as sess:
        trader = current_trader(request, sess)
        if trader is None:
            return RedirectResponse("/login", status_code=303)
        text = cs.require_reviewed(cs.CURRENT, development_data=trader.development_data)

        if diagnosis is None:
            return page(
                request, "consent.html", status_code=400, title="Before you upload",
                text=text, state=consent_state(sess, trader),
                error=("Without the first one there is nothing for Scope to do. "
                       "You can close this page and nothing is kept."),
            )

        chosen = {"diagnosis": True, "engine_testing": engine_testing is not None}
        now = datetime.now(UTC)
        for purpose in text.purposes:
            if not chosen.get(purpose.key):
                continue
            sess.add(m.ConsentEvent(
                trader_id=trader.id,
                purpose=purpose.enum,
                scope="v1",
                terms_version=text.version,
                granted=True,
                at=now,
                method="web",
                wording_shown=cs.wording_for(purpose, text),
            ))
        sess.commit()
    return RedirectResponse("/upload", status_code=303)


@router.get("/settings/consent", response_class=HTMLResponse)
def consent_ledger(request: Request):
    with make_session(request.app.state.engine) as sess:
        trader = current_trader(request, sess)
        if trader is None:
            return RedirectResponse("/login", status_code=303)
        events = sess.scalars(
            select(m.ConsentEvent)
            .where(m.ConsentEvent.trader_id == trader.id)
            .order_by(m.ConsentEvent.id.desc())
        ).all()
        return page(request, "consent_ledger.html", title="What you agreed to",
                    events=events, text=cs.CURRENT,
                    state=consent_state(sess, trader))


@router.post("/settings/consent/withdraw")
def consent_withdraw(request: Request, purpose: str = Form(...),
                     csrf_token: str = Form(None)):
    if not require_csrf(request, csrf_token):
        return HTMLResponse("Form expired. Reload the page and try again.", status_code=403)

    with make_session(request.app.state.engine) as sess:
        trader = current_trader(request, sess)
        if trader is None:
            return RedirectResponse("/login", status_code=303)
        chosen = cs.CURRENT.purpose(purpose)
        sess.add(m.ConsentEvent(
            trader_id=trader.id,
            purpose=chosen.enum,
            scope="v1",
            terms_version=cs.CURRENT.version,
            granted=False,
            at=datetime.now(UTC),
            method="web",
            wording_shown=f"[withdrawn] {chosen.title}",
        ))
        sess.commit()
    return RedirectResponse("/settings/consent", status_code=303)


@router.get("/upload", response_class=HTMLResponse)
def upload_placeholder(request: Request):
    """Phase 2D builds this. It exists now so consent has something to gate."""
    with make_session(request.app.state.engine) as sess:
        trader = current_trader(request, sess)
        if trader is None:
            return RedirectResponse("/login", status_code=303)
        if not has_diagnosis_consent(sess, trader):
            return RedirectResponse("/consent", status_code=303)
        return page(request, "upload.html", title="Upload your tradebook")
