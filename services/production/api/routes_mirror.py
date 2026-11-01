"""The Mirror, told as the Scope: Home, four chapters, twelve facts (handoff 4, 5).

The pages format; they compute nothing. Every figure comes from
services/production/mirror/metrics.py, through scope_facts.record_context, so there is
one place each is decided and a template cannot quietly invent a number.

Every fact opens to the trades behind it, all of them. That was the long page's
drawer, and it is the cheapest trust mechanism in the product (PRD 6): a line a
trader cannot open is a claim he has to take on faith, and this product's whole
argument is that he should not have to.
"""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from services.production.api import scope_facts as SF
from services.production.api import scope_map as SM
from services.production.api.routes_consent import has_diagnosis_consent
from services.production.api.routes_identity import current_trader, page, require_csrf
from services.production.ctr.profiles import registry as profiles
from services.production.db import models as m
from services.production.db.session import make_session
from services.production.mirror import feedback as FB
from services.production.mirror import loader
from services.shared.schemas import scope_v1 as s_enums

router = APIRouter()


def _record(request: Request):
    """The signed-in trader's record, or the page to show instead of it.

    Returns (response, None) when the trader must go elsewhere first - sign in,
    consent - or when there is no record to show: the instrument is not set up, or
    no trade was rebuilt (handoff 4, edge states). Otherwise (None, (trips, imp,
    context)), context being every figure the Mirror and the Scope read.
    """
    with make_session(request.app.state.engine) as sess:
        trader = current_trader(request, sess)
        if trader is None:
            return RedirectResponse("/login", status_code=303), None
        if not has_diagnosis_consent(sess, trader):
            return RedirectResponse("/consent", status_code=303), None

        try:
            trips, imp = loader.load_for(sess, trader)
        except (profiles.UnknownInstrument, loader.MisdeclaredQuantityUnit) as exc:
            # Our gap, not his error, and the import review already recorded it. A
            # page that names the instrument beats a 500 that names nothing.
            return page(request, "mirror_no_profile.html", title="Your record",
                        reason=str(exc)), None
        if not trips:
            return page(request, "mirror_empty.html", title="Your record"), None
        return None, (trips, imp, SF.record_context(trips))


ENTER = {"in": "vt-in vt-tap-{tap}", "out": "vt-out vt-tap-{tap}", "lens": "vt-lens",
         "back": "vt-back"}
"""The kit's ?enter= values and the class each puts on <html> (motion.css plays it)."""


def enter_class(request: Request) -> str:
    """The motion hook for the page, from ?enter= and ?tap=; anything else is no class."""
    enter, tap = request.query_params.get("enter"), request.query_params.get("tap", "")
    if enter not in ENTER:
        return ""
    if "{tap}" in ENTER[enter] and tap not in {str(c.number) for c in SM.CHAPTERS}:
        return ""
    return ENTER[enter].format(tap=tap)


@router.get("/mirror", response_class=HTMLResponse)
def scope_home(request: Request):
    """Scope home (handoff 4, level 1): the four chapters on the dial, the five days'
    share in its centre. Replaces the long Mirror page; its sentences live on in the
    chapters and facts, word for word (tests/unit/mirror/test_wording_reference.py)."""
    early, record = _record(request)
    if early is not None:
        return early
    trips, imp, context = record
    figs = SF.facts(context, imp)
    return page(request, "scope/home.html", title="Scope", enter_class=enter_class(request),
                view=SF.home_view(figs, context), imp=imp, trade_count=len(trips),
                trading_day_count=len(context["days"].counts))


@router.get("/mirror/chapter/{n}", response_class=HTMLResponse)
def scope_chapter(request: Request, n: int):
    """A chapter: the dial re-divided into its facts, a story card for each."""
    try:
        chapter = SM.chapter(n)
    except KeyError:
        return HTMLResponse("", status_code=404)
    early, record = _record(request)
    if early is not None:
        return early
    _trips, imp, context = record
    figs = SF.facts(context, imp)
    return page(request, "scope/chapter.html", title=chapter.name,
                enter_class=enter_class(request), chapter=chapter,
                view=SF.chapter_view(n, figs), facts=figs, imp=imp,
                trading_day_count=len(context["days"].counts),
                sources=s_enums.RiskUnitSourceV1, **_feedback_context(request, n),
                **context)


def _feedback_context(request: Request, n: int) -> dict:
    """What the feedback row needs: where it stands, its choices, where it posts."""
    if n not in FB.CHAPTERS:
        return {}
    with make_session(request.app.state.engine) as sess:
        trader = current_trader(request, sess)
        state = FB.state(sess, trader, n)
    return {"feedback": state, "feedback_answers": FB.ANSWERS,
            "feedback_reasons": FB.REASONS,
            "feedback_url": f"/mirror/chapter/{n}/feedback"}


@router.post("/mirror/chapter/{n}/feedback", response_class=HTMLResponse)
def chapter_feedback(request: Request, n: int, answer: str = Form(None),
                     reason: str = Form(None), csrf_token: str = Form(None)):
    """B4: one answer per chapter (1-3), then an optional reason after Wrong.

    htmx gets the feedback row back to swap in place; a plain form post goes back
    to the chapter, where the row shows its new state.
    """
    if n not in FB.CHAPTERS:
        return HTMLResponse("", status_code=404)
    if not require_csrf(request, csrf_token):
        return HTMLResponse("Form expired. Reload the page and try again.", status_code=403)
    with make_session(request.app.state.engine) as sess:
        trader = current_trader(request, sess)
        if trader is None:
            return RedirectResponse("/login", status_code=303)
        imp = loader.current_import(sess, trader)
        if imp is None:
            return HTMLResponse("", status_code=404)
        try:
            if answer is not None:
                FB.record_answer(sess, trader=trader, chapter=n, answer=answer,
                                 import_id=imp.id)
            elif reason is not None:
                FB.record_reason(sess, trader=trader, chapter=n, reason=reason)
            else:
                return HTMLResponse("", status_code=400)
        except FB.NotAsked:
            return HTMLResponse("", status_code=400)
        sess.commit()
    if request.headers.get("HX-Request") == "true":
        return page(request, "scope/_feedback.html", **_feedback_context(request, n))
    return RedirectResponse(f"{SM.chapter_href(n)}#feedback", status_code=303)


@router.get("/mirror/fact/{key}", response_class=HTMLResponse)
def scope_fact(request: Request, key: str):
    """A fact (handoff 4, level 3): the lens and path, the Mirror's sentences and
    figures, then every trade behind it."""
    if key not in SM.FACTS:
        return HTMLResponse("", status_code=404)
    early, record = _record(request)
    if early is not None:
        return early
    _trips, imp, context = record
    chapter, index = SM.chapter_of(key)
    unread = _unread(request, imp) if key == "unread" else {}
    figs = SF.facts(context, imp)
    return page(request, f"scope/facts/{key}.html", title=SM.FACTS[key].title,
                enter_class=enter_class(request), body_class="screen__body--fact",
                chapter=chapter, index=index, number=index + 1, fact=SM.FACTS[key],
                back_href=SM.chapter_href(chapter.number, fact=index + 1),
                f=figs[key], facts=figs,
                groups=SM.groups(key, context), imp=imp,
                trading_day_count=len(context["days"].counts),
                sources=s_enums.RiskUnitSourceV1, **unread, **context)


def _unread(request: Request, imp) -> dict:
    """The rows behind "What we could not read": every row set aside or not read,
    each with its reason, and every trade refused - as the import review lists them."""
    with make_session(request.app.state.engine) as sess:
        rows = sess.scalars(
            select(m.ImportRow).where(m.ImportRow.import_id == imp.id,
                                      m.ImportRow.status.in_(("EXCLUDED", "REJECTED")))
            .order_by(m.ImportRow.row_no)
        ).all()
        refused = sess.scalars(
            select(m.SkippedTrip).where(m.SkippedTrip.import_id == imp.id)
            .order_by(m.SkippedTrip.id)
        ).all()
        return {
            "excluded": [(r.row_no, r.reason) for r in rows if r.status == "EXCLUDED"],
            "rejected": [(r.row_no, r.reason) for r in rows if r.status == "REJECTED"],
            "refused": [t.reason for t in refused],
        }
