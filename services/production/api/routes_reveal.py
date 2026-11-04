"""The guess and the reveal (handoff 5 and 7, screens 10 and 12; B6).

After the import check, before anything is shown: the guess. Then the reveal - his
five worst days as one slice of his whole result, the share in the centre, and the
Mirror's sentences. "Show me those days" opens the worst-days fact; "Continue" goes
on to the one number.

The guess is asked only while guess.ready() - in development always, in production
once the research seat has frozen its labels (TR-009). Until then a real trader goes
straight to the reveal, which shows without "You guessed".
"""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from services.production.api import scope_facts as SF
from services.production.api import scope_map as SM
from services.production.api.routes_consent import has_diagnosis_consent
from services.production.api.routes_identity import current_trader, page, require_csrf
from services.production.api.routes_mirror import load_record
from services.production.ctr.profiles import registry as profiles
from services.production.db.session import make_session
from services.production.eligibility import assess as el
from services.production.mirror import guess as GU
from services.production.mirror import loader
from services.shared.prereg import reader

router = APIRouter()


def _production(request: Request) -> bool:
    return request.app.state.settings.production


def _checkable(trips) -> tuple[int, int] | None:
    """How many of the library's checks his history allows, for the guess's one line
    (TR-008). None when the library cannot be read: the line is left off, not guessed."""
    framework = reader.load()
    if framework.lock is reader.LockState.TAMPERED:
        return None
    result = el.assess(trips, framework)
    return len(result.enough), result.total


@router.get("/guess", response_class=HTMLResponse)
def guess_page(request: Request):
    with make_session(request.app.state.engine) as sess:
        trader = current_trader(request, sess)
        if trader is None:
            return RedirectResponse("/login", status_code=303)
        if not has_diagnosis_consent(sess, trader):
            return RedirectResponse("/consent", status_code=303)
        if not GU.ready(_production(request)) or GU.answer_of(sess, trader) is not None:
            return RedirectResponse("/mirror/reveal", status_code=303)
        try:
            trips, _imp = loader.load_for(sess, trader)
        except (profiles.UnknownInstrument, loader.MisdeclaredQuantityUnit):
            return RedirectResponse("/mirror", status_code=303)  # its own page says why
        if not trips:
            return RedirectResponse("/mirror", status_code=303)
        return page(
            request,
            "guess.html",
            title="Before you look",
            question=GU.QUESTION,
            labels=GU.LABELS,
            unknown=GU.UNKNOWN,
            unknown_label=GU.UNKNOWN_LABEL,
            checkable=_checkable(trips),
        )


@router.post("/guess")
def guess_answer(request: Request, answer: str = Form(None), csrf_token: str = Form(None)):
    if not require_csrf(request, csrf_token):
        return HTMLResponse("Form expired. Reload the page and try again.", status_code=403)
    with make_session(request.app.state.engine) as sess:
        trader = current_trader(request, sess)
        if trader is None:
            return RedirectResponse("/login", status_code=303)
        imp = loader.current_import(sess, trader)
        if imp is None or not GU.ready(_production(request)):
            return RedirectResponse("/mirror/reveal", status_code=303)
        try:
            GU.record(sess, trader=trader, answer=answer or "", import_id=imp.id)
        except GU.NotAGuess:
            return HTMLResponse("", status_code=400)
        sess.commit()
    return RedirectResponse("/mirror/reveal", status_code=303)


@router.get("/mirror/reveal", response_class=HTMLResponse)
def reveal(request: Request):
    """The reveal: after the guess, or without one where the guess is not asked yet."""
    early, record = load_record(request)
    if early is not None:
        return early
    _trips, imp, context = record
    with make_session(request.app.state.engine) as sess:
        trader = current_trader(request, sess)
        guessed = GU.answer_of(sess, trader)
        if guessed is None and GU.ready(_production(request)):
            return RedirectResponse("/guess", status_code=303)
        guessed_label = GU.label_of(guessed.answer) if guessed is not None else None
    return page(
        request,
        "reveal.html",
        title="Your five worst days",
        imp=imp,
        screen_class="screen--navy on-navy",
        body_class="reveal",
        guessed=guessed_label,
        view=SF.reveal_view(context),
        worst_href=SM.fact_href("worst-days"),
        **context,
    )
