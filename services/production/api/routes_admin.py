"""/admin: the one reader of what the app records (TICKET-848).

An admin is a login id in ADMIN_LOGIN_IDS; it is not a role on the account. To anyone
else the address is the same 404 as an address that does not exist, however it is asked
for. That takes three things here: the page's own check, a route for the trailing slash
(the router would otherwise redirect it, which says something is there) and, in app.py,
turning this path's 405 into the 404. No route here takes anything but GET.

A view writes one AdminAction and nothing else. The actor is ``trader:<id>``, as sign-up
writes it, because an admin action outlives a deletion and a login id is his.

One trader's page (TICKET-875) keeps the same rule. Its id is taken as text and checked after
the admin check, because a framework's 422 for a bad id would say something is here.

**The one amendment (TICKET-998): connecting Fyers for market data.** 848 made this page read
only. The Market data card adds exactly two forms, each a POST with the page's CSRF token, and the
broker's GET back to ``/admin/fyers/callback``, which can't carry that token, so it carries a
``state`` signed for the admin who started the login instead (``market.token.sign_state``). The same
404 holds for everyone else, before any other check. The day's token goes straight to
``market.token.save``, encrypted; no page, log, error or admin action ever holds it or the code.
"""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import quote

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select

from services.production.accounts import auth
from services.production.api import admin_health, admin_view
from services.production.api.routes_identity import (
    current_session,
    current_trader,
    page,
    require_csrf,
)
from services.production.api.trader_trail import build as trader_trail
from services.production.db import models as m
from services.production.db.session import make_session
from services.production.market import fyers
from services.production.market import token as market_token

router = APIRouter()

PATH = "/admin"
TRADERS = f"{PATH}/traders/"
FYERS = f"{PATH}/fyers/"
LONGEST_ID = 18  # past this no id fits the database's integer, so it can't be anyone's


def is_admin_path(path: str) -> bool:
    return path.rstrip("/") == PATH or path.startswith((TRADERS, FYERS))


def sign_in_again(path: str) -> HTTPException:
    """An admin whose sign-in is older than ADMIN_SESSION_HOURS goes to /login and comes back.

    Raised only after the admin check, so it is said to an admin and to no one else.
    """
    return HTTPException(status_code=303, headers={"Location": f"/login?next={quote(path, safe='/')}"})


def require_fresh_signin(request: Request, path: str) -> None:
    session = current_session(request)
    if session is None or not auth.admin_signin_fresh(session, auth.clock()):
        raise sign_in_again(path)


@router.get(PATH, response_class=HTMLResponse)
def admin(request: Request):
    config = request.app.state.settings
    with make_session(request.app.state.engine) as sess:
        trader = current_trader(request, sess)
        if trader is None or trader.login_id not in config.admin_login_ids:
            raise HTTPException(status_code=404)
        require_fresh_signin(request, PATH)
        last_looked = sess.scalar(
            select(func.max(m.AdminAction.at))
            .where(m.AdminAction.actor == f"trader:{trader.id}", m.AdminAction.action == "admin_view")
        )
        sess.add(m.AdminAction(actor=f"trader:{trader.id}", action="admin_view", target=None,
                               at=datetime.now(UTC)))
        sess.commit()
        view = admin_view.build(sess, running_version=request.app.state.code_version,
                                production=config.production, last_looked=last_looked,
                                sort=request.query_params.get("sort"),
                                all_columns=request.query_params.get("columns") == "all",
                                admin_ids=config.admin_login_ids)
    view["market"]["said"] = admin_view.MARKET_SAID.get(request.query_params.get("fyers", ""))
    return page(request, "admin.html", demo=None, title="Admin", screen_class="screen--admin",
                body_class="admin", health=admin_health.build(request.app), **view)


@router.get(f"{PATH}/", response_class=HTMLResponse, include_in_schema=False)
def admin_slash():
    """What an unknown address with a trailing slash gets, for everyone."""
    raise HTTPException(status_code=404)


def _id_of(text: str) -> int | None:
    is_id = text.isascii() and text.isdigit() and len(text) <= LONGEST_ID
    return int(text) if is_id else None


@router.get(f"{TRADERS}{{trader_id}}", response_class=HTMLResponse)
def admin_trader(request: Request, trader_id: str):
    config = request.app.state.settings
    with make_session(request.app.state.engine) as sess:
        admin = current_trader(request, sess)
        if admin is None or admin.login_id not in config.admin_login_ids:
            raise HTTPException(status_code=404)
        require_fresh_signin(request, f"{TRADERS}{trader_id}")
        wanted = _id_of(trader_id)
        view = trader_trail(sess, wanted) if wanted is not None else None
        if view is None:
            raise HTTPException(status_code=404)
        sess.add(m.AdminAction(actor=f"trader:{admin.id}", action="admin_view_trader",
                               target=f"trader:{wanted}", at=datetime.now(UTC)))
        sess.commit()
    return page(request, "admin_trader.html", demo=None, title="Admin", screen_class="screen--admin",
                body_class="admin", **view)


@router.get(f"{TRADERS}{{trader_id}}/", response_class=HTMLResponse, include_in_schema=False)
def admin_trader_slash(trader_id: str):
    """The same as admin_slash: a redirect would say something is here."""
    raise HTTPException(status_code=404)


# ---------- Connect Fyers (TICKET-998) ----------


def _admin_actor(request: Request, sess) -> str:
    """``trader:<id>`` for an admin, else the same 404 as an unknown address."""
    trader = current_trader(request, sess)
    if trader is None or trader.login_id not in request.app.state.settings.admin_login_ids:
        raise HTTPException(status_code=404)
    require_fresh_signin(request, PATH)  # the broker's callback can't be replayed after sign-in
    return f"trader:{trader.id}"


def _back(said: str) -> RedirectResponse:
    return RedirectResponse(f"{PATH}?fyers={said}#market", status_code=303)


def _connect_with(request: Request, sess, actor: str, app: fyers.FyersApp, code: str) -> RedirectResponse:
    now = datetime.now(UTC)
    try:
        login = fyers.exchange(app, code)
        market_token.save(sess, request.app.state.settings.file_key, login, actor=actor, now=now)
    except (fyers.ExchangeFailed, ValueError):
        sess.add(m.AdminAction(actor=actor, action="fyers_connect_refused", target=None, at=now))
        sess.commit()
        return _back("expired")
    sess.add(m.AdminAction(actor=actor, action="fyers_connected", target=None, at=now))
    sess.commit()
    return _back("connected")


@router.post(f"{FYERS}connect", include_in_schema=False)
def fyers_connect(request: Request, csrf_token: str = Form(None)):
    """Send the admin to the broker's login, with a state signed for him."""
    with make_session(request.app.state.engine) as sess:
        actor = _admin_actor(request, sess)
        app = fyers.from_env()
        if app is None:
            raise HTTPException(status_code=404)
        if not require_csrf(request, csrf_token):
            return HTMLResponse("Form expired. Reload the page and try again.", status_code=403)
        now = datetime.now(UTC)
        state = market_token.sign_state(request.app.state.settings.secret_key, actor, now)
        sess.add(m.AdminAction(actor=actor, action="fyers_login_started", target=None, at=now))
        sess.commit()
    return RedirectResponse(fyers.login_url(app, state), status_code=303)


@router.get(f"{FYERS}callback", include_in_schema=False)
def fyers_callback(request: Request):
    """Where the broker's login comes back, when the app is registered with this address."""
    with make_session(request.app.state.engine) as sess:
        actor = _admin_actor(request, sess)
        app = fyers.from_env()
        if app is None:
            raise HTTPException(status_code=404)
        code, state = request.query_params.get("auth_code"), request.query_params.get("state")
        if not market_token.state_ok(request.app.state.settings.secret_key, actor, state, datetime.now(UTC)):
            sess.add(m.AdminAction(actor=actor, action="fyers_connect_refused", target=None,
                                   at=datetime.now(UTC)))
            sess.commit()
            return _back("refused")
        if not code:
            return _back("no-code")
        return _connect_with(request, sess, actor, app, code)


@router.post(f"{FYERS}paste", include_in_schema=False)
def fyers_paste(request: Request, address: str = Form(""), csrf_token: str = Form(None)):
    """The whole address bar the broker's login ended on, pasted. Always there."""
    with make_session(request.app.state.engine) as sess:
        actor = _admin_actor(request, sess)
        app = fyers.from_env()
        if app is None:
            raise HTTPException(status_code=404)
        if not require_csrf(request, csrf_token):
            return HTMLResponse("Form expired. Reload the page and try again.", status_code=403)
        code, _state = market_token.auth_code_from(address)
        if not code:
            return _back("no-code")
        return _connect_with(request, sess, actor, app, code)
