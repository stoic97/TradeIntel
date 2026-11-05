"""Upload, import review, duplicate confirmation.

The pipeline decides; this route carries a file to it and shows what came back.

Three things the route does that the pipeline cannot:

**It checks the cap before reading.** A file is refused on its declared size before
its bytes are parsed, because uploads are processed synchronously (ADR 007) and a
pathological file would otherwise hold the request open while being read.

**It refuses a byte-identical re-upload with a message.** Content-addressed storage
makes the second copy harmless, but silently accepting it would leave the trader
believing he had added something. When reconstruction has moved on since that file was
read, the message also offers to read the stored file again; he decides (TICKET-844).

**It checks ownership on every read.** An import that is not yours is a 404, not a
403: "that exists but isn't yours" is itself information about another trader.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from datetime import date

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select

from services.production import demo
from services.production.accounts import deletion
from services.production.accounts.file_store import CannotDecrypt, FileStore, NoSuchFile
from services.production.api import formatting, limits
from services.production.api.routes_consent import (
    has_diagnosis_consent,
    trader_today,
    upload_page,
)
from services.production.api.routes_identity import current_trader, page, require_csrf
from services.production.charges import statement as charge_statement
from services.production.ctr.adapters import filemap
from services.production.ctr.intake import persist
from services.production.ctr.intake import pipeline as pl
from services.production.db import models as m
from services.production.db.session import make_session
from services.production.journal import constants as k
from services.production.journal import generate as gen
from services.production.mirror import loader
from services.shared.schemas import scope_v1 as s

router = APIRouter()
logger = logging.getLogger(__name__)

_READING_AGAIN = threading.Lock()
COULD_NOT_OPEN = ("We could not open your stored file, so it was not read again. Nothing "
                  "changed: your figures are still the ones from the last reading. The "
                  "fault is ours, not your file's.")
COULD_NOT_READ = ("The newer code could not read your stored file, so it was not read again. "
                  "Nothing changed: your figures are still the ones from the last reading.")


def _store(request: Request) -> FileStore:
    config = request.app.state.settings
    return FileStore(root=config.file_store, key=config.file_key)


def _code_version(request: Request) -> str:
    return request.app.state.code_version


def charges_open(request: Request) -> bool:
    """Whether a broker's charges file can be taken: not in production on an unchecked shape."""
    return charge_statement.VERIFIED or not request.app.state.settings.production


def _owned_import(sess, trader: m.Trader, import_id: int) -> m.Import | None:
    imp = sess.get(m.Import, import_id)
    if imp is None or imp.trader_id != trader.id:
        return None
    return imp


def _first_upload(sess, trader: m.Trader, digest: str) -> m.RawFile | None:
    """The first time he sent these bytes. Older confirmations wrote another row for them."""
    return sess.scalars(
        select(m.RawFile).where(m.RawFile.trader_id == trader.id, m.RawFile.sha256 == digest)
        .order_by(m.RawFile.id)
    ).first()


def _when(raw: m.RawFile) -> str:
    return raw.uploaded_at.astimezone(limits.INDIA).strftime("%d %b %Y")


def _same_file_again(sess, trader: m.Trader, digest: str) -> tuple[str, int | None]:
    """What to say when he sends bytes he has already sent, and any import to offer reading.

    Which file, when, and how many rows, because two exports from one account have nearly
    identical names. Never that he should go to his broker for a file he has. The offer is
    only for the file the report reads now, and only when this code would read it differently.
    """
    first = _first_upload(sess, trader, digest)
    named = f"You have already uploaded this exact file: {first.original_name}, on {_when(first)}"
    reading = sess.scalars(
        select(m.Import).join(m.RawFile, m.Import.raw_file_id == m.RawFile.id)
        .where(m.Import.trader_id == trader.id, m.RawFile.sha256 == digest)
        .order_by(m.Import.id.desc())
    ).first()
    if reading is None:  # stored by the charges step, so it has no rows of a tradebook
        return f"{named}. Nothing was added.", None
    if reading.outcome is s.ImportOutcome.REJECTED:
        return f"{named}. We could not read it as a tradebook. Nothing was added.", None

    rows = f"{formatting.count(reading.rows_in)} {'row' if reading.rows_in == 1 else 'rows'}"
    said = f"{named}, {rows}. Nothing was added."
    current = loader.current_import(sess, trader)
    if current is None:
        return said, None
    if sess.get(m.RawFile, current.raw_file_id).sha256 == digest:
        return said, current.id if pl.out_of_date(current) else None
    reads = _first_upload(sess, trader, sess.get(m.RawFile, current.raw_file_id).sha256)
    return f"{said} Your record now reads {reads.original_name}, from {_when(reads)}.", None


@router.post("/upload")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),  # noqa: B008 - FastAPI declares uploads this way
    csrf_token: str = Form(None),
    export_date: str = Form(None),
):
    if not require_csrf(request, csrf_token):
        return HTMLResponse("Form expired. Reload the page and try again.", status_code=403)

    with make_session(request.app.state.engine) as sess:
        trader = current_trader(request, sess)
        if trader is None:
            return RedirectResponse("/login", status_code=303)
        if not has_diagnosis_consent(sess, trader):
            return RedirectResponse("/consent", status_code=303)

        refusal = limits.upload_refusal(request, sess, trader)
        if refusal is not None:
            return limits.with_retry_after(
                upload_page(request, status_code=refusal.status_code, error=refusal.sentence),
                refusal.retry_after,
            )

        if export_date:
            try:
                downloaded = date.fromisoformat(export_date)
            except ValueError:
                return upload_page(request, status_code=400, error="That is not a date.")
            if downloaded > trader_today():
                return upload_page(request, status_code=400,
                                   error="That date is in the future. Put the day you "
                                         "downloaded this file.")

        content = await file.read(k.MAX_UPLOAD_BYTES + 1)
        if len(content) > k.MAX_UPLOAD_BYTES:
            return upload_page(request, status_code=400, error=limits.TOO_LARGE)

        digest = hashlib.sha256(content).hexdigest()
        if _first_upload(sess, trader, digest) is not None:
            sentence, offered = _same_file_again(sess, trader, digest)
            return upload_page(request, status_code=400, error=sentence, read_again_id=offered)
        return _ingest(request, sess, trader, content=content,
                       file_name=file.filename or "tradebook.csv",
                       export_date=export_date or None, source_account="A")


@router.post("/upload/demo")
def upload_demo(request: Request, csrf_token: str = Form(None)):
    """"Try it with a demo file" (TICKET-842): the synthetic tradebook, as an upload.

    The ordinary path from here on (``_ingest``), under the demo's own source account.
    A second click opens the demo he already has, and once he has a real record the demo
    is not taken: it would become the record the report reads and hide his own.
    """
    if not require_csrf(request, csrf_token):
        return HTMLResponse("Form expired. Reload the page and try again.", status_code=403)

    with make_session(request.app.state.engine) as sess:
        trader = current_trader(request, sess)
        if trader is None:
            return RedirectResponse("/login", status_code=303)
        if not has_diagnosis_consent(sess, trader):
            return RedirectResponse("/consent", status_code=303)
        if demo.has_real_record(sess, trader):
            return RedirectResponse("/mirror", status_code=303)
        loaded = demo.demo_import(sess, trader)
        if loaded is not None:
            return RedirectResponse(f"/imports/{loaded.id}", status_code=303)
        return _ingest(request, sess, trader, content=demo.FILE.read_bytes(),
                       file_name=demo.FILE_NAME, export_date=demo.EXPORT_DATE,
                       source_account=demo.ACCOUNT)


def _ingest(request: Request, sess, trader: m.Trader, *, content: bytes, file_name: str,
            export_date: str | None, source_account: str):
    """Store the file, plan it, write it and its Journals: one path for every upload.

    A real upload that rebuilt trades replaces the demo, if he loaded one, before it is
    written (TICKET-842): it is then version 1 of its account with nothing behind it.
    A real file refused outright leaves the demo where it was.
    """
    stored = _store(request).put(content)
    text = content.decode("utf-8-sig", errors="replace")
    existing = persist.existing_days(sess, trader=trader, source_account=source_account)
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
                source_account=source_account,
                code_version=_code_version(request),
                existing_days=existing,
                export_date=export_date,
                export_date_source="trader" if export_date else None,
            ),
            production=request.app.state.settings.production,
        )
    except filemap.UnverifiedFileMap:
        return page(request, "upload_closed.html", status_code=503,
                    title="Not open for your broker yet")
    if source_account != demo.ACCOUNT and plan.positions:
        deletion.remove_demo(sess, _store(request), trader=trader)
    imp = persist.write_plan(
        sess, trader=trader, plan=plan, raw_sha256=stored.sha256,
        original_name=file_name, stored_path=str(stored.path), size=stored.size,
        source_account=source_account,
    )
    sess.commit()
    gen.for_import(sess, trader=trader)
    sess.commit()
    if request.headers.get("HX-Request") == "true":
        return _read(request, sess, imp)
    return RedirectResponse(f"/imports/{imp.id}", status_code=303)


def _read(request: Request, sess, imp: m.Import):
    """Calculating's done state, for an htmx upload (handoff 7, D1 a).

    The final counts, once, and the latest rebuilt trade. A file that rebuilt no
    trade has nothing to show here; htmx is sent straight to its review, which says
    what happened to every row.
    """
    latest = sess.scalars(
        select(m.Trip).where(m.Trip.import_id == imp.id).order_by(m.Trip.entry_ts.desc())
    ).first()
    if latest is None:
        return Response(status_code=200, headers={"HX-Redirect": f"/imports/{imp.id}"})
    raw = sess.get(m.RawFile, imp.raw_file_id)
    return page(request, "calculating.html", title="Your file is read", imp=imp,
                file_name=raw.original_name, latest=latest)


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

        # A first upload has nothing to compare against: every day is new, so the page
        # lists them plainly. Decided here rather than summed in the template (T7).
        first_upload = sum(d.rows_before for d in days) == 0
        changed_days = [] if first_upload else [
            d.trading_day for d in days if d.diff is not s.DayDiff.IDENTICAL
        ]
        shrunk_days = [d.trading_day for d in days if d.day_shrank]
        read_again = persist.read_with_newer_code(sess, imp)
        earlier = persist.earlier_reading(sess, imp) if read_again else None
        confirmed = [r for r in rows if r.flag is s.RowFlag.TRADER_CONFIRMED_DUPLICATE]
        return page(request, "import_review.html", title="What we read",
                    imp=imp, groups=groups, excluded=excluded, rejected=rejected,
                    days=days, first_upload=first_upload, changed_days=changed_days,
                    shrunk_days=shrunk_days, read_again=read_again,
                    same_file=persist.reads_same_file_as_before(sess, imp),
                    rows_confirmed=len(confirmed) if pl.rebuilt_without_confirmed(imp) else 0,
                    trades_before=earlier.trips_reconstructed if earlier else None,
                    charges_offered=(charges_open(request) and not imp.fees_available
                                     and imp.trips_reconstructed > 0))


@router.post("/imports/{import_id}/confirm-duplicates")
def confirm_duplicates(request: Request, import_id: int,
                       dup_group: str = Form(...), csrf_token: str = Form(None)):
    """The trader says a flagged group is one trade recorded twice.

    The file is read again as a new version without those rows, so every figure is
    rebuilt from what remains. The earlier version keeps its rows: a confirmation is a
    new reading of the same file, not an edit of what we first read. It adds no file, so
    the day's upload limit doesn't count it. Only the current import's file, as with a
    re-read: an older file's would replace what the report reads. A page left open on an
    earlier reading of this file adds to the current one, so nothing confirmed since is
    lost, and a group already settled writes nothing.
    """
    if not require_csrf(request, csrf_token):
        return HTMLResponse("Form expired. Reload the page and try again.", status_code=403)

    with _READING_AGAIN, make_session(request.app.state.engine) as sess:
        trader = current_trader(request, sess)
        if trader is None:
            return RedirectResponse("/login", status_code=303)
        imp = _owned_import(sess, trader, import_id)
        current = loader.current_import(sess, trader)
        if imp is None or current is None or not persist.same_file(sess, imp, current):
            return page(request, "404.html", status_code=404, title="Not found")
        if dup_group not in persist.still_suspected(sess, current):
            return RedirectResponse(f"/imports/{current.id}", status_code=303)

        raw = sess.get(m.RawFile, current.raw_file_id)
        # The same gate the upload path keeps. A confirmation re-reads the file
        # from the store and re-plans it, so an unchecked broker map has to
        # refuse here too -- otherwise the gate held on upload and let go one
        # click later, which is the worse failure of the two (TD-024).
        try:
            plan = _read_stored(request, sess, trader, current, raw, also_confirm=(dup_group,))
        except (NoSuchFile, CannotDecrypt):
            logger.exception("import %s: the stored file could not be opened", current.id)
            return _not_read_again(request, 503, COULD_NOT_OPEN)
        except filemap.UnverifiedFileMap:
            return page(request, "upload_closed.html", status_code=503,
                        title="Not open for your broker yet")

        new_import = persist.write_reading(sess, trader=trader, plan=plan, raw=raw,
                                           source_account=current.source_account)
        gen.for_import(sess, trader=trader)
        sess.commit()
        return RedirectResponse(f"/imports/{new_import.id}", status_code=303)


@router.post("/imports/{import_id}/read-again")
def read_again(request: Request, import_id: int, csrf_token: str = Form(None)):
    """He asks for his stored file to be read by the current code (TICKET-844).

    A new version of the import reading the same ``RawFile``, so nothing earlier changes
    and the day's upload limit doesn't count it. Only the current import's file: any older
    or refused one would replace what the report reads. When there's nothing to do it
    writes nothing, so repeat clicks are harmless. Everything, Journals included, commits
    together or not at all, so a failure leaves the old import current.
    """
    if not require_csrf(request, csrf_token):
        return HTMLResponse("Form expired. Reload the page and try again.", status_code=403)

    # One process (ADR 007), so this makes the check and the write one step: the second
    # of a double click waits, then finds the import already current.
    with _READING_AGAIN, make_session(request.app.state.engine) as sess:
        trader = current_trader(request, sess)
        if trader is None:
            return RedirectResponse("/login", status_code=303)
        if not has_diagnosis_consent(sess, trader):
            return RedirectResponse("/consent", status_code=303)
        imp = _owned_import(sess, trader, import_id)
        current = loader.current_import(sess, trader)
        if imp is None or current is None or not persist.same_file(sess, imp, current):
            return page(request, "404.html", status_code=404, title="Not found")
        if not pl.out_of_date(current):
            return RedirectResponse(f"/imports/{current.id}", status_code=303)

        raw = sess.get(m.RawFile, current.raw_file_id)
        try:
            plan = _read_stored(request, sess, trader, current, raw)
        except (NoSuchFile, CannotDecrypt):
            logger.exception("import %s: the stored file could not be opened", current.id)
            return _not_read_again(request, 503, COULD_NOT_OPEN)
        except filemap.UnverifiedFileMap:
            return page(request, "upload_closed.html", status_code=503,
                        title="Not open for your broker yet")
        except Exception:  # an unforeseen failure must still leave his record as it was
            logger.exception("import %s: the stored file could not be planned", current.id)
            return _not_read_again(request, 422, COULD_NOT_READ)
        if plan.outcome is s.ImportOutcome.REJECTED or not plan.trips:
            return _not_read_again(request, 422, COULD_NOT_READ)

        try:
            new_import = persist.write_reading(sess, trader=trader, plan=plan, raw=raw,
                                               source_account=current.source_account)
            gen.for_import(sess, trader=trader)
            sess.commit()
        except Exception:  # as above: nothing has been committed
            sess.rollback()
            logger.exception("import %s: the new reading could not be written", current.id)
            return _not_read_again(request, 422, COULD_NOT_READ)
        return RedirectResponse(f"/imports/{new_import.id}", status_code=303)


def _not_read_again(request: Request, status_code: int, sentence: str):
    return page(request, "read_again_failed.html", status_code=status_code,
                title="Your file was not read again", sentence=sentence)


def _read_stored(request: Request, sess, trader: m.Trader, imp: m.Import, raw: m.RawFile,
                 also_confirm: tuple[str, ...] = ()) -> pl.ImportPlan:
    """A new plan of an import's stored file, keeping what was stated and confirmed on it."""
    text = _store(request).get(raw.sha256).decode("utf-8-sig", errors="replace")
    return pl.plan_import(
        text,
        context=pl.ImportContext(
            trader_id=str(trader.id), source_account=imp.source_account,
            code_version=_code_version(request),
            existing_days=persist.existing_days(sess, trader=trader,
                                                source_account=imp.source_account),
            export_date=imp.export_date,
            export_date_source=imp.export_date_source,
        ),
        production=request.app.state.settings.production,
        confirmed_groups=persist.confirmed_groups(sess, imp) | set(also_confirm),
    )
