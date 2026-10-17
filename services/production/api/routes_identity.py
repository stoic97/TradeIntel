"""Invite, login, logout, account.

The deliberate choices here are about what the pages do *not* say:

A failed login gives one answer whether the login id is unknown or the password is
wrong. Distinguishing them tells an attacker which half to keep trying.

An invite code that has been redeemed is a 404, not "already used". Confirming that
a code once existed is information the holder of a guessed code has not earned.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from services.production.accounts import auth
from services.production.db import models as m
from services.production.db.session import make_session

router = APIRouter()

SIGN_IN_FAILED = "That login id and password do not match an account."


def _templates(request: Request):
    return request.app.state.templates


def _settings(request: Request):
    return request.app.state.settings


def current_session(request: Request) -> auth.Session | None:
    raw = request.cookies.get(auth.SESSION_COOKIE)
    return auth.open_session(raw, _settings(request).secret_key)


def current_trader(request: Request, sess) -> m.Trader | None:
    session = current_session(request)
    if session is None:
        return None
    return sess.get(m.Trader, session.trader_id)


def page(request: Request, name: str, status_code: int = 200, **context) -> HTMLResponse:
    """Render a page with its CSRF token and sign-in state already in context."""
    session = current_session(request)
    context.setdefault("title", "Scope")
    context["csrf_token"] = auth.csrf_token(session, _settings(request).secret_key)
    context["signed_in"] = session is not None
    return _templates(request).TemplateResponse(
        request=request, name=name, context=context, status_code=status_code
    )


def require_csrf(request: Request, token: str | None) -> bool:
    return auth.csrf_ok(token, current_session(request), _settings(request).secret_key)


def _set_session_cookie(response, request: Request, session: auth.Session) -> None:
    config = _settings(request)
    response.set_cookie(
        auth.SESSION_COOKIE,
        auth.seal_session(session, config.secret_key),
        httponly=True,
        samesite="lax",
        secure=config.production,
        max_age=60 * 60 * 24 * 30,
        path="/",
    )


@router.get("/invite/{code}", response_class=HTMLResponse)
def invite_form(request: Request, code: str) -> HTMLResponse:
    with make_session(request.app.state.engine) as sess:
        invite = sess.scalars(
            select(m.InviteCode).where(m.InviteCode.code == code)
        ).first()
        if invite is None or invite.redeemed_by is not None:
            # A redeemed code is a 404, not "already used": confirming that a code
            # once existed is information a guesser has not earned.
            return page(request, "404.html", status_code=404, title="Not found")
    return page(request, "invite.html", title="Create your account", code=code)


@router.post("/invite/{code}")
def invite_redeem(
    request: Request,
    code: str,
    login_id: str = Form(...),
    display_name: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(None),
):
    if not require_csrf(request, csrf_token):
        return HTMLResponse("Form expired. Reload the page and try again.", status_code=403)

    with make_session(request.app.state.engine) as sess:
        invite = sess.scalars(
            select(m.InviteCode).where(m.InviteCode.code == code)
        ).first()
        if invite is None or invite.redeemed_by is not None:
            return HTMLResponse(status_code=404, content="Not found")

        taken = sess.scalars(
            select(m.Trader).where(m.Trader.login_id == login_id)
        ).first()
        if taken is not None:
            return page(request, "invite.html", status_code=400,
                        title="Create your account", code=code,
                        error="That login id is taken.")

        try:
            password_hash = auth.hash_password(password)
        except auth.PasswordTooShort as exc:
            return page(request, "invite.html", status_code=400,
                        title="Create your account", code=code, error=str(exc))

        trader = m.Trader(
            display_name=display_name,
            login_id=login_id,
            password_hash=password_hash,
            created_at=datetime.now(UTC),
        )
        sess.add(trader)
        sess.flush()
        sess.connection().exec_driver_sql(
            "update invite_code set redeemed_by = ?, redeemed_at = ? where id = ?",
            (trader.id, datetime.now(UTC).isoformat(), invite.id),
        )
        sess.add(m.AdminAction(actor=f"trader:{trader.id}", action="redeem_invite",
                               target=code, at=datetime.now(UTC)))
        sess.commit()

        response = RedirectResponse("/login", status_code=303)
        return response


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request) -> HTMLResponse:
    return page(request, "login.html", title="Sign in")


@router.post("/login")
def login(
    request: Request,
    login_id: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(None),
):
    if not require_csrf(request, csrf_token):
        return HTMLResponse("Form expired. Reload the page and try again.", status_code=403)

    with make_session(request.app.state.engine) as sess:
        trader = sess.scalars(
            select(m.Trader).where(m.Trader.login_id == login_id)
        ).first()
        ok = trader is not None and auth.verify_password(trader.password_hash, password)
        if not ok or trader is None:
            # One answer for an unknown login id and a wrong password alike.
            return page(request, "login.html", status_code=400, title="Sign in",
                        error=SIGN_IN_FAILED)

        session = auth.new_session(trader.id)
        response = RedirectResponse("/account", status_code=303)
        _set_session_cookie(response, request, session)
        return response


@router.post("/logout")
def logout(request: Request, csrf_token: str = Form(None)):
    if not require_csrf(request, csrf_token):
        return HTMLResponse("Form expired. Reload the page and try again.", status_code=403)
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(auth.SESSION_COOKIE, path="/")
    return response


@router.get("/account", response_class=HTMLResponse)
def account(request: Request):
    with make_session(request.app.state.engine) as sess:
        trader = current_trader(request, sess)
        if trader is None:
            return RedirectResponse("/login", status_code=303)
        return page(request, "account.html", title="Your account",
                    display_name=trader.display_name, login_id=trader.login_id)
