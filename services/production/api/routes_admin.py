"""/admin: the one reader of what the app records (TICKET-848).

An admin is a login id in ADMIN_LOGIN_IDS; it is not a role on the account. To anyone
else the address is the same 404 as an address that does not exist, however it is asked
for. That takes three things here: the page's own check, a route for the trailing slash
(the router would otherwise redirect it, which says something is there) and, in app.py,
turning this path's 405 into the 404. No route here takes anything but GET.

A view writes one AdminAction and nothing else. The actor is ``trader:<id>``, as sign-up
writes it, because an admin action outlives a deletion and a login id is his.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select

from services.production.api import admin_health, admin_view
from services.production.api.routes_identity import current_trader, page
from services.production.db import models as m
from services.production.db.session import make_session

router = APIRouter()

PATH = "/admin"


def is_admin_path(path: str) -> bool:
    return path.rstrip("/") == PATH


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
                                production=config.production, last_looked=last_looked)
    return page(request, "admin.html", demo=None, title="Admin", screen_class="screen--admin",
                body_class="admin", health=admin_health.build(request.app), **view)


@router.get(f"{PATH}/", response_class=HTMLResponse, include_in_schema=False)
def admin_slash():
    """What an unknown address with a trailing slash gets, for everyone."""
    raise HTTPException(status_code=404)
