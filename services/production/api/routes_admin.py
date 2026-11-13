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
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select

from services.production.api import admin_health, admin_view
from services.production.api.routes_identity import current_trader, page
from services.production.api.trader_trail import build as trader_trail
from services.production.db import models as m
from services.production.db.session import make_session

router = APIRouter()

PATH = "/admin"
TRADERS = f"{PATH}/traders/"
LONGEST_ID = 18  # past this no id fits the database's integer, so it can't be anyone's


def is_admin_path(path: str) -> bool:
    return path.rstrip("/") == PATH or path.startswith(TRADERS)


@router.get(PATH, response_class=HTMLResponse)
def admin(request: Request):
    config = request.app.state.settings
    with make_session(request.app.state.engine) as sess:
        trader = current_trader(request, sess)
        if trader is None or trader.login_id not in config.admin_login_ids:
            raise HTTPException(status_code=404)
        last_looked = sess.scalar(
            select(func.max(m.AdminAction.at))
            .where(m.AdminAction.actor == f"trader:{trader.id}", m.AdminAction.action == "admin_view")
        )
        sess.add(m.AdminAction(actor=f"trader:{trader.id}", action="admin_view", target=None,
                               at=datetime.now(UTC)))
        sess.commit()
        view = admin_view.build(sess, running_version=request.app.state.code_version,
                                production=config.production, last_looked=last_looked,
                                admin_ids=config.admin_login_ids)
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
