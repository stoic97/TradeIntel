"""Sign-up, login, logout, account.

The deliberate choices here are about what the pages do *not* say:

A failed login gives one answer whether the login id is unknown or the password is
wrong. Distinguishing them tells an attacker which half to keep trying.

Sign-up is open: anyone can make an account, and a new account is signed in straight
away. Consent and eligibility are what stand between it and a record, and neither
moved. It has to say a login id is taken, which is the one thing a sign-up can't avoid
saying, so a login id is not a secret. The password is.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from services.production.accounts import auth
from services.production.api import limits
from services.production.ctr.intake import day_versions as dv
from services.production.ctr.intake import persist
from services.production.ctr.intake import pipeline as pl
from services.production.db import models as m
from services.production.db.session import make_session
from services.production.mirror import loader

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
    trader = sess.get(m.Trader, session.trader_id)
    if trader is None:
        return None
    # The id alone isn't enough: it can belong to a later account by now.
    if not auth.session_is_for(session, trader.password_hash, _settings(request).secret_key):
        return None
    return trader


def page(request: Request, name: str, status_code: int = 200, **context) -> HTMLResponse:
    """Render a page with its CSRF token and sign-in state already in context."""
    session = current_session(request)
    context.setdefault("title", "Scope")
    context["csrf_token"] = auth.csrf_token(session, _settings(request).secret_key)
    context["signed_in"] = session is not None
    if "demo" not in context:
        from services.production import demo

        context["demo"] = demo.LINE if _drawn_from_demo(request, session, context) else None
    return _templates(request).TemplateResponse(
        request=request, name=name, context=context, status_code=status_code
    )


def _drawn_from_demo(request: Request, session, context: dict) -> bool:
    """Whether this page is drawn from the demo tradebook (TICKET-842), so it says so.

    A page about one upload says so by that upload; any other page of a signed-in
    trader, by the record the report reads. A refused real file is his, so its page
    does not, even while the demo is still his record.
    """
    from services.production import demo

    if "imp" in context:
        return demo.is_demo(context["imp"])
    if session is None:
        return False
    with make_session(request.app.state.engine) as sess:
        trader = sess.get(m.Trader, session.trader_id)
        return trader is not None and demo.is_demo(demo.current_import(sess, trader))


def require_csrf(request: Request, token: str | None) -> bool:
    return auth.csrf_ok(token, current_session(request), _settings(request).secret_key)


def _session_for(request: Request, trader: m.Trader) -> auth.Session:
    return auth.new_session(trader.id, trader.password_hash, _settings(request).secret_key)


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


def landing_for(sess, trader: m.Trader) -> str:
    """Where a trader belongs when he arrives.

    Not /account: a page telling him nothing has been uploaded is not a destination.
    With nothing yet, the upload page. With a record he has not yet been walked
    through - import check, guess, reveal, one number (handoff 5) - the import check
    of the upload his record comes from, which starts the walk: not simply his latest
    upload, which may be a file we refused and whose page has no way on. Once he has
    been through it, home. A guess or a number on record says he has: in production
    the guess is skipped until its labels are frozen (TR-009), and the number is the
    walk's last step either way. With uploads but no record, his latest, which says
    why.
    """
    def latest(*, with_trips: bool) -> m.Import | None:
        query = select(m.Import).where(m.Import.trader_id == trader.id)
        if with_trips:
            query = query.join(m.Trip, m.Trip.import_id == m.Import.id)
        return sess.scalars(query.order_by(m.Import.id.desc())).first()

    record = latest(with_trips=True)
    if record is None:
        refused = latest(with_trips=False)
        return f"/imports/{refused.id}" if refused is not None else "/upload"
    walked = any(
        sess.scalars(select(model.id).where(model.trader_id == trader.id)).first() is not None
        for model in (m.GuessAnswer, m.RiskBudgetDeclaration)
    )
    return "/" if walked else f"/imports/{record.id}"


LOGIN_ID_MAX = 100
DISPLAY_NAME_MAX = 200


def _signup_refused(request: Request, error: str):
    return page(request, "signup.html", status_code=400, title="Create your account",
                error=error)


@router.get("/signup", response_class=HTMLResponse)
def signup_form(request: Request):
    with make_session(request.app.state.engine) as sess:
        trader = current_trader(request, sess)
        if trader is not None:
            return RedirectResponse(landing_for(sess, trader), status_code=303)
    return page(request, "signup.html", title="Create your account")


@router.post("/signup")
def signup(
    request: Request,
    login_id: str = Form(""),
    display_name: str = Form(""),
    password: str = Form(""),
    csrf_token: str = Form(None),
):
    if not require_csrf(request, csrf_token):
        return HTMLResponse("Form expired. Reload the page and try again.", status_code=403)

    # Before the password is hashed: hashing is the costly part of a sign-up.
    connection = limits.connection(request)
    wait = request.app.state.signups.wait_seconds(connection)
    if wait:
        limits.count_refusal(request, limits.SIGNUP_CAP)
        return limits.with_retry_after(
            page(request, "signup.html", status_code=429, title="Create your account",
                 error=limits.signups_refused(wait)),
            wait,
        )

    login_id, display_name = login_id.strip(), display_name.strip()
    if not login_id or not display_name:
        return _signup_refused(request, "A name and a login id are both needed.")
    if len(login_id) > LOGIN_ID_MAX or len(display_name) > DISPLAY_NAME_MAX:
        return _signup_refused(request, "That name or login id is too long.")
    try:
        password_hash = auth.hash_password(password)
    except auth.PasswordTooShort as exc:
        return _signup_refused(request, str(exc))

    with make_session(request.app.state.engine) as sess:
        signed_in = current_trader(request, sess)
        if signed_in is not None:
            return RedirectResponse(landing_for(sess, signed_in), status_code=303)
        taken = sess.scalars(select(m.Trader).where(m.Trader.login_id == login_id)).first()
        # A listed id nobody holds, or one whose owner deleted himself, is still an admin's:
        # registering it would make a stranger an admin.
        if taken is not None or login_id in _settings(request).admin_login_ids:
            return _signup_refused(request, "That login id is taken.")

        trader = m.Trader(display_name=display_name, login_id=login_id,
                          password_hash=password_hash, created_at=datetime.now(UTC))
        sess.add(trader)
        try:
            sess.flush()
        except IntegrityError:  # two people asked for one login id at once: the first has it
            sess.rollback()
            return _signup_refused(request, "That login id is taken.")
        # No target: an admin action outlives a deletion, and a login id is his.
        sess.add(m.AdminAction(actor=f"trader:{trader.id}", action="sign_up", target=None,
                               at=datetime.now(UTC)))
        sess.commit()
        request.app.state.signups.add(connection)

        response = RedirectResponse(landing_for(sess, trader), status_code=303)
        _set_session_cookie(response, request, _session_for(request, trader))
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

        session = _session_for(request, trader)
        response = RedirectResponse(landing_for(sess, trader), status_code=303)
        _set_session_cookie(response, request, session)
        return response


@router.post("/logout")
def logout(request: Request, csrf_token: str = Form(None)):
    if not require_csrf(request, csrf_token):
        return HTMLResponse("Form expired. Reload the page and try again.", status_code=403)
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(auth.SESSION_COOKIE, path="/")
    return response


def _upload_changes(sess, trader: m.Trader) -> dict[int, dv.UploadChange]:
    """What each upload changed, by import id, for every upload that followed another.

    A rejected file writes no day versions, so it neither has a change nor counts as
    the upload before one. The first file read has nothing to compare with. That is
    asked of the order of the files, not of rows_before: a later file holding only new
    days also has no rows before it.
    """
    versions = sess.scalars(
        select(m.TradingDayVersion).where(m.TradingDayVersion.trader_id == trader.id)
    ).all()
    by_import: dict[int, list[m.TradingDayVersion]] = {}
    for version in versions:
        by_import.setdefault(version.import_id, []).append(version)
    return {import_id: dv.upload_change(by_import[import_id])
            for import_id in sorted(by_import)[1:]}


@router.get("/account", response_class=HTMLResponse)
def account(request: Request):
    with make_session(request.app.state.engine) as sess:
        trader = current_trader(request, sess)
        if trader is None:
            return RedirectResponse("/login", status_code=303)
        imports = sess.scalars(
            select(m.Import)
            .where(m.Import.trader_id == trader.id)
            .order_by(m.Import.id.desc())
        ).all()
        current = loader.current_import(sess, trader)
        return page(request, "account.html", title="Your account",
                    display_name=trader.display_name, login_id=trader.login_id,
                    imports=imports, changes=_upload_changes(sess, trader),
                    read_again_id=current.id if current and pl.out_of_date(current) else None,
                    reads_again={imp.id for imp in imports
                                 if persist.read_with_newer_code(sess, imp)})
