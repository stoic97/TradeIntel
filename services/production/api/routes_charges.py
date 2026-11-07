"""The optional second step after an upload: the broker's own charges file (TICKET-828).

A record, not a calculation. What the file states is kept in its own insert-only row and
read beside the record. Nothing here writes to a trip or an import: ``fees_available``
is what the tradebook said.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from services.production.api import limits
from services.production.api.routes_consent import has_diagnosis_consent
from services.production.api.routes_identity import current_trader, page, require_csrf
from services.production.api.routes_upload import _owned_import, _store, charges_open
from services.production.charges import record, statement
from services.production.db import models as m
from services.production.db.session import make_session
from services.production.journal import constants as k

router = APIRouter()


def _early(request: Request, sess, import_id: int):
    """(the page to show instead, None), or (None, (trader, import))."""
    trader = current_trader(request, sess)
    if trader is None:
        return RedirectResponse("/login", status_code=303), None
    if not has_diagnosis_consent(sess, trader):
        return RedirectResponse("/consent", status_code=303), None
    imp = _owned_import(sess, trader, import_id)
    if imp is None:
        return page(request, "404.html", status_code=404, title="Not found"), None
    return None, (trader, imp)


def _step(request: Request, sess, trader: m.Trader, imp: m.Import, status_code=200, error=None):
    if imp.fees_available or not imp.trips_reconstructed:
        return RedirectResponse(f"/imports/{imp.id}", status_code=303)
    return page(request, "charges.html", status_code=status_code, title="Add charges", imp=imp,
                gross=record.gross_of(sess, imp), charges=record.build(sess, trader, imp),
                file_open=charges_open(request), error=error)


@router.get("/imports/{import_id}/charges", response_class=HTMLResponse)
def add_charges(request: Request, import_id: int):
    with make_session(request.app.state.engine) as sess:
        early, found = _early(request, sess, import_id)
        if early is not None:
            return early
        return _step(request, sess, *found)


@router.post("/imports/{import_id}/charges")
async def add_file(request: Request, import_id: int,
                   file: UploadFile = File(...),  # noqa: B008 - FastAPI declares uploads this way
                   csrf_token: str = Form(None)):
    if not require_csrf(request, csrf_token):
        return HTMLResponse("Form expired. Reload the page and try again.", status_code=403)
    with make_session(request.app.state.engine) as sess:
        early, found = _early(request, sess, import_id)
        if early is not None:
            return early
        trader, imp = found
        if not charges_open(request):
            limits.count_refusal(request, limits.UNVERIFIED_MAP)
            return page(request, "upload_closed.html", status_code=503,
                        title="Not open for your broker yet")

        def refuse(error: str):
            return _step(request, sess, trader, imp, status_code=400, error=error)

        refusal = limits.upload_refusal(request, sess, trader)
        if refusal is not None:
            return limits.with_retry_after(
                _step(request, sess, trader, imp, status_code=refusal.status_code,
                      error=refusal.sentence),
                refusal.retry_after,
            )

        content = await file.read(k.MAX_UPLOAD_BYTES + 1)
        if len(content) > k.MAX_UPLOAD_BYTES:
            limits.count_refusal(request, limits.FILE_TOO_LARGE)
            return refuse("That file is larger than we take.")
        try:
            days = statement.parse(content)
        except statement.Unreadable as exc:
            return refuse(str(exc))
        if not days.keys() & record.trading_days(sess, imp):
            return refuse("None of the days in that file are in your upload. Nothing was added.")
        digest = hashlib.sha256(content).hexdigest()
        if sess.scalars(select(m.RawFile).where(m.RawFile.trader_id == trader.id,
                                                m.RawFile.sha256 == digest)).first():
            limits.count_refusal(request, limits.SAME_FILE)
            return refuse("You have already uploaded this exact file. Nothing was added.")

        stored = _store(request).put(content)
        raw = m.RawFile(trader_id=trader.id, sha256=stored.sha256,
                        original_name=file.filename or "charges.csv", size=stored.size,
                        stored_path=str(stored.path), uploaded_at=datetime.now(UTC))
        sess.add(raw)
        sess.flush()
        record.record_statement(sess, trader, raw, statement.READER_ID, days)
        sess.commit()
        return RedirectResponse(f"/imports/{imp.id}/charges", status_code=303)
