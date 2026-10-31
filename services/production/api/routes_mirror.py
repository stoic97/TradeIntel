"""The Mirror: counted facts, in the order PRD section 6 fixes, each with a drawer.

The page formats; it computes nothing. Every figure comes from
services/production/mirror/metrics.py, so there is one place each is decided and a
template cannot quietly invent a number.

The drawer is the cheapest trust mechanism in the product (PRD 6): a line a trader
cannot open is a claim he has to take on faith, and this product's whole argument is
that he should not have to.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from services.production.api import scope_facts as SF
from services.production.api import scope_map as SM
from services.production.api.routes_consent import has_diagnosis_consent
from services.production.api.routes_identity import current_trader, page
from services.production.ctr.profiles import registry as profiles
from services.production.db import models as m
from services.production.db.session import make_session
from services.production.mirror import loader
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s_enums

router = APIRouter()

DRAWERS = {
    "worst-days": "The five days, and every trade on them.",
    "best-worst-trades": "Your best five and worst five, by result.",
    "two-straight-losses": "Every trade opened after two that had already closed at a loss.",
    "holding-time": "How long each trade was open, by how it ended.",
    "by-hour": "Every trade, by the hour you opened it.",
}


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
def mirror(request: Request):
    early, record = _record(request)
    if early is not None:
        return early
    _trips, imp, context = record
    return page(request, "mirror.html", title="Your record",
                imp=imp, drawers=DRAWERS,
                sources=s_enums.RiskUnitSourceV1,
                showable=s_enums.SHOWABLE_DENOMINATORS, **context)


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
                sources=s_enums.RiskUnitSourceV1, **context)


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


@router.get("/mirror/{line}/drawer", response_class=HTMLResponse)
def drawer(request: Request, line: str):
    """The trades behind one line. An HTMX partial, so it opens in place."""
    with make_session(request.app.state.engine) as sess:
        trader = current_trader(request, sess)
        if trader is None:
            return HTMLResponse("", status_code=403)
        trips, imp = loader.load_for(sess, trader)
        if not trips or line not in DRAWERS:
            return HTMLResponse("", status_code=404)

        context = SF.record_context(trips)
        shown: list[mx.Trip] = trips
        if line == "worst-days":
            days = {d.trading_day for d in context["worst_days"].days}
            shown = [t for t in trips if t.trading_day in days]
        elif line == "best-worst-trades":
            shown = context["best"] + context["worst"]
        elif line == "two-straight-losses":
            ids = set(context["two_losses"].condition_trip_ids)
            shown = [t for t in trips if t.trip_id in ids]

        return page(request, "_drawer.html", title="Evidence",
                    line=line, caption=DRAWERS[line], shown=shown, imp=imp,
                    **context)
