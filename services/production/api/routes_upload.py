"""Upload, import review, duplicate confirmation.

The pipeline decides; this route carries a file to it and shows what came back.

Three things the route does that the pipeline cannot:

**It checks the cap before reading.** A file is refused on its declared size before
its bytes are parsed, because uploads are processed synchronously (ADR 007) and a
pathological file would otherwise hold the request open while being read.

**It refuses a byte-identical re-upload with a message.** Content-addressed storage
makes the second copy harmless, but silently accepting it would leave the trader
believing he had added something.

**It checks ownership on every read.** An import that is not yours is a 404, not a
403: "that exists but isn't yours" is itself information about another trader.
"""

from __future__ import annotations

import hashlib

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from services.production.accounts.file_store import FileStore
from services.production.api.routes_consent import has_diagnosis_consent
from services.production.api.routes_identity import current_trader, page, require_csrf
from services.production.ctr.adapters import filemap
from services.production.ctr.intake import duplicates as dup
from services.production.ctr.intake import persist
from services.production.ctr.intake import pipeline as pl
from services.production.db import models as m
from services.production.db.session import make_session
from services.production.journal import constants as k
from services.production.journal import generate as gen
from services.shared.schemas import scope_v1 as s

router = APIRouter()


def _store(request: Request) -> FileStore:
    config = request.app.state.settings
    return FileStore(root=config.file_store, key=config.file_key)


def _code_version(request: Request) -> str:
    return request.app.state.code_version


def _owned_import(sess, trader: m.Trader, import_id: int) -> m.Import | None:
    imp = sess.get(m.Import, import_id)
    if imp is None or imp.trader_id != trader.id:
        return None
    return imp


@router.post("/upload")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),  # noqa: B008 - FastAPI declares uploads this way
    csrf_token: str = Form(None),
):
    if not require_csrf(request, csrf_token):
        return HTMLResponse("Form expired. Reload the page and try again.", status_code=403)

    with make_session(request.app.state.engine) as sess:
        trader = current_trader(request, sess)
        if trader is None:
            return RedirectResponse("/login", status_code=303)
        if not has_diagnosis_consent(sess, trader):
            return RedirectResponse("/consent", status_code=303)

        content = await file.read(k.MAX_UPLOAD_BYTES + 1)
        if len(content) > k.MAX_UPLOAD_BYTES:
            megabytes = k.MAX_UPLOAD_BYTES // (1024 * 1024)
            return page(request, "upload.html", status_code=400,
                        title="Upload your tradebook",
                        error=f"That file is larger than {megabytes} MB. Every "
                              "tradebook we have seen is far smaller — if yours is "
                              "genuinely this big, tell us and we will raise it.")

        digest = hashlib.sha256(content).hexdigest()
        already = sess.scalars(
            select(m.RawFile).where(m.RawFile.trader_id == trader.id,
                                    m.RawFile.sha256 == digest)
        ).first()
        if already is not None:
            return page(request, "upload.html", status_code=400,
                        title="Upload your tradebook",
                        error="You have already uploaded this exact file. Nothing "
                              "was added. If you meant to send a newer export, "
                              "download it again from your broker.")

        stored = _store(request).put(content)
        text = content.decode("utf-8-sig", errors="replace")
        existing = persist.existing_days(sess, trader=trader, source_account="A")
        # In production the pipeline refuses a file whose broker map nobody has
        # checked, which is right: a rejection built from a guessed map names an
        # export that may not exist. It refused by raising and nothing caught it,
        # so an upload from an unchecked broker reached the trader as "Internal
        # Server Error" -- the same shape as the consent gate's 500, on the
        # screen that matters most. Dhan is checked now; the second adapter will
        # not be (TD-027), and this is the path it takes.
        try:
            plan = pl.plan_import(
                text,
                context=pl.ImportContext(
                    trader_id=str(trader.id),
                    source_account="A",
                    code_version=_code_version(request),
                    existing_days=existing,
                ),
                production=request.app.state.settings.production,
            )
        except filemap.UnverifiedFileMap:
            return page(request, "upload_closed.html", status_code=503,
                        title="Not open for your broker yet")
        imp = persist.write_plan(
            sess, trader=trader, plan=plan, raw_sha256=stored.sha256,
            original_name=file.filename or "tradebook.csv",
            stored_path=str(stored.path), size=stored.size,
        )
        sess.commit()
        gen.for_import(sess, trader=trader)
        sess.commit()
        return RedirectResponse(f"/imports/{imp.id}", status_code=303)


@router.get("/imports/{import_id}", response_class=HTMLResponse)
def import_review(request: Request, import_id: int):
    with make_session(request.app.state.engine) as sess:
        trader = current_trader(request, sess)
        if trader is None:
            return RedirectResponse("/login", status_code=303)
        imp = _owned_import(sess, trader, import_id)
        if imp is None:
            return page(request, "404.html", status_code=404, title="Not found")

        rows = sess.scalars(
            select(m.ImportRow).where(m.ImportRow.import_id == imp.id)
            .order_by(m.ImportRow.row_no)
        ).all()
        days = sess.scalars(
            select(m.TradingDayVersion)
            .where(m.TradingDayVersion.import_id == imp.id)
            .order_by(m.TradingDayVersion.trading_day)
        ).all()

        groups: dict[str, list[m.ImportRow]] = {}
        for row in rows:
            if row.flag is s.RowFlag.SUSPECTED_DUPLICATE and row.dup_group:
                groups.setdefault(row.dup_group, []).append(row)
        excluded = [r for r in rows if r.status == "EXCLUDED"]
        rejected = [r for r in rows if r.status == "REJECTED"]

        return page(request, "import_review.html", title="What we read",
                    imp=imp, groups=groups, excluded=excluded, rejected=rejected,
                    days=days)


@router.post("/imports/{import_id}/confirm-duplicates")
def confirm_duplicates(request: Request, import_id: int,
                       dup_group: str = Form(...), csrf_token: str = Form(None)):
    """The trader says a flagged group is one trade recorded twice.

    The import is re-run as a new version with those rows excluded. The earlier
    version keeps its rows: a confirmation is a new reading of the same file, not an
    edit of what we first read.
    """
    if not require_csrf(request, csrf_token):
        return HTMLResponse("Form expired. Reload the page and try again.", status_code=403)

    with make_session(request.app.state.engine) as sess:
        trader = current_trader(request, sess)
        if trader is None:
            return RedirectResponse("/login", status_code=303)
        imp = _owned_import(sess, trader, import_id)
        if imp is None:
            return page(request, "404.html", status_code=404, title="Not found")

        raw = sess.get(m.RawFile, imp.raw_file_id)
        content = _store(request).get(raw.sha256)
        text = content.decode("utf-8-sig", errors="replace")

        existing = persist.existing_days(sess, trader=trader, source_account="A")
        plan = pl.plan_import(
            text,
            context=pl.ImportContext(
                trader_id=str(trader.id), source_account="A",
                code_version=_code_version(request), existing_days=existing,
            ),
        )
        confirmed = dup.confirm_group(
            dup.Classification(tuple(
                dup.ClassifiedRow(r.row_no, r.raw_text, r.flag, r.dup_group, r.fill_id)
                for r in plan.rows
            )),
            dup_group,
        )
        by_row = {r.row_no: r for r in confirmed.rows}
        plan = plan.with_rows(tuple(
            pl.PlannedRow(
                r.row_no,
                r.raw_text,
                "EXCLUDED" if by_row[r.row_no].excluded else r.status,
                r.reason,
                by_row[r.row_no].flag,
                r.dup_group,
                r.fill_id,
            )
            for r in plan.rows
        ))

        new_import = persist.write_plan(
            sess, trader=trader, plan=plan, raw_sha256=raw.sha256,
            original_name=raw.original_name, stored_path=raw.stored_path,
            size=raw.size,
        )
        sess.commit()
        gen.for_import(sess, trader=trader)
        sess.commit()
        return RedirectResponse(f"/imports/{new_import.id}", status_code=303)
