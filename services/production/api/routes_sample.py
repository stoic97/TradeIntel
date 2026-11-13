"""/sample: the report of an invented trader, open to anyone, read-only (TICKET-914).

Most people who hear about Scope don't have their broker export to hand, and the demo
upload sits behind an account and the consent page. This is the way in before either.

**One record, read once.** The demo tradebook goes through the ordinary upload path
(``routes_upload._ingest``) into one account kept for it, the first time anyone opens a
sample page, and again only when the file changes. Every figure is still the pipeline's.
A visitor gets the same pages the report routes draw, from that one record.

**Nothing per visitor.** No account, no cookie of ours, no row. The report routes are
told whose record to read (``request.state.sample_trader_id``) and, while they draw a
sample page, write nothing: no chapter marked opened, no feedback asked, no reading
beacon on the page. There is no POST route under /sample, so a form could not save even
if one were drawn.

**Never a real trader's data.** The record is chosen by the account kept for the
sample, never by the session, so a signed-in trader on /sample sees the invented
trader, and his own report is untouched. That account can't be signed into: its
password is a random secret thrown away, it is marked as development data so /admin
never counts it as a reader, and sign-up refuses its login id.
"""

from __future__ import annotations

import hashlib
import secrets
import threading
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select

from services.production import demo
from services.production.accounts import auth
from services.production.api import routes_identity, routes_mirror, routes_upload
from services.production.db import models as m
from services.production.db.session import make_session

router = APIRouter()

LOGIN_ID = routes_identity.SAMPLE_LOGIN_ID
"""The account the sample is read into. Sign-up refuses it."""

PREFIX = "/sample"
_READING = threading.Lock()


def _file_sha256() -> str:
    return hashlib.sha256(demo.FILE.read_bytes()).hexdigest()


def sample_trader_id(request: Request) -> int:
    """The sample account, read from the demo file if it isn't yet, or if the file changed."""
    sha = _file_sha256()
    with _READING, make_session(request.app.state.engine) as sess:
        trader = sess.scalars(select(m.Trader).where(
            m.Trader.login_id == LOGIN_ID, m.Trader.development_data.is_(True))).first()
        if trader is None:
            trader = m.Trader(display_name="Sample trader", login_id=LOGIN_ID,
                              password_hash=auth.hash_password(secrets.token_urlsafe(48)),
                              created_at=datetime.now(UTC), development_data=True)
            sess.add(trader)
            sess.commit()
        current = demo.current_import(sess, trader)
        read = current is not None and sess.get(m.RawFile, current.raw_file_id).sha256 == sha
        if not read:
            routes_upload._ingest(request, sess, trader, content=demo.FILE.read_bytes(),
                                  file_name=demo.FILE_NAME, export_date=demo.EXPORT_DATE,
                                  source_account=demo.ACCOUNT)
        return trader.id


def _as_sample(request: Request, draw) -> Response:
    """Draw a report page from the sample's record, with every link kept inside /sample."""
    request.state.sample_trader_id = sample_trader_id(request)
    response = draw()
    if isinstance(response, RedirectResponse):
        location = response.headers["location"]
        if location.startswith("/mirror"):
            return RedirectResponse(PREFIX + location.removeprefix("/mirror"),
                                    status_code=response.status_code)
        return response
    body = response.body.decode("utf-8")
    for attribute in ("href", "action"):
        body = body.replace(f'{attribute}="/mirror', f'{attribute}="{PREFIX}')
    return HTMLResponse(body, status_code=response.status_code)


@router.get(PREFIX, response_class=HTMLResponse)
def sample_home(request: Request):
    return _as_sample(request, lambda: routes_mirror.scope_home(request))


@router.get(PREFIX + "/chapter/{n}", response_class=HTMLResponse)
def sample_chapter(request: Request, n: int):
    return _as_sample(request, lambda: routes_mirror.scope_chapter(request, n))


@router.get(PREFIX + "/fact/{key}", response_class=HTMLResponse)
def sample_fact(request: Request, key: str):
    return _as_sample(request, lambda: routes_mirror.scope_fact(request, key))


@router.get(PREFIX + "/fact/{key}/trades", response_class=HTMLResponse)
def sample_fact_trades(request: Request, key: str):
    return _as_sample(request, lambda: routes_mirror.scope_fact_trades(request, key))
