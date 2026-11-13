"""The Mirror, told as the Scope: Home, four chapters, eleven facts (handoff 4, 5).

The pages format; they compute nothing. Every figure comes from
services/production/mirror/metrics.py, through scope_facts.record_context, so there is
one place each is decided and a template cannot quietly invent a number.

Every fact opens to the trades behind it, all of them. That was the long page's
drawer, and it is the cheapest trust mechanism in the product (PRD 6): a line a
trader cannot open is a claim he has to take on faith, and this product's whole
argument is that he should not have to.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import distinct, func, select

from services.production.accounts import risk_budget as rb
from services.production.api import report_filter as RF
from services.production.api import scope_facts as SF
from services.production.api import scope_map as SM
from services.production.api import trade_list as TL
from services.production.api.routes_consent import has_diagnosis_consent, trader_today
from services.production.api.routes_identity import current_trader, page, require_csrf
from services.production.charges import record as charge_record
from services.production.ctr.intake import persist
from services.production.ctr.profiles import registry as profiles
from services.production.db import models as m
from services.production.db.session import make_session
from services.production.mirror import feedback as FB
from services.production.mirror import loader
from services.shared.schemas import scope_v1 as s_enums

router = APIRouter()

SHARE_MOVED = "share"


def is_sample(request: Request) -> bool:
    """Whether this page is being drawn for /sample (routes_sample): read-only, no one's."""
    return getattr(request.state, "sample_trader_id", None) is not None


def reader(request: Request, sess):
    """Whose record a page reads: the sample's on /sample, else the signed-in trader's."""
    if is_sample(request):
        return sess.get(m.Trader, request.state.sample_trader_id)
    return current_trader(request, sess)


def load_record(request: Request):
    """The signed-in trader's record, or the page to show instead of it.

    Returns (response, None) when the trader must go elsewhere first - sign in,
    consent - or when there is no record to show: the instrument is not set up, or
    no trade was rebuilt (handoff 4, edge states). Otherwise (None, (trips, imp,
    context)), context being every figure the Mirror and the Scope read.
    """
    with make_session(request.app.state.engine) as sess:
        trader = reader(request, sess)
        if trader is None:
            return RedirectResponse("/login", status_code=303), None
        if not is_sample(request) and not has_diagnosis_consent(sess, trader):
            return RedirectResponse("/consent", status_code=303), None

        try:
            trips, imp = loader.load_for(sess, trader)
            new_days = None if is_sample(request) or imp is None else _new_days(sess, imp)
        except (profiles.UnknownInstrument, loader.MisdeclaredQuantityUnit) as exc:
            # Our gap, not his error, and the import review already recorded it. A
            # page that names the instrument beats a 500 that names nothing.
            return page(request, "mirror_no_profile.html", title="Your record",
                        reason=str(exc)), None
        if not trips:
            return page(request, "mirror_empty.html", title="Your record"), None
        if is_sample(request):
            return None, (trips, imp, SF.record_context(trips))
        chosen = RF.valid(RF.decode(request.cookies.get(RF.COOKIE)), trips, new_days)
        request.state.report_filter = RF.bar(chosen, trips, new_days, request.url.path)
        request.state.history = trips
        shown = RF.apply(trips, chosen, new_days)
        if not shown:
            return page(request, "scope/filtered_empty.html", title="Your record", imp=imp,
                        report_filter=request.state.report_filter), None
        return None, (shown, imp, SF.record_context(shown))


def _new_days(sess, imp) -> set[str] | None:
    """The days the latest upload added: its day versions with no rows before them. None when
    there was no upload before it to be "since". A file read again adds no days."""
    earlier = persist.earlier_reading(sess, imp)
    if earlier is None or persist.same_file(sess, imp, earlier):
        return None
    return set(sess.scalars(select(m.TradingDayVersion.trading_day).where(
        m.TradingDayVersion.import_id == imp.id,
        m.TradingDayVersion.rows_before == 0)))


@router.get("/mirror/filter")
def choose_filter(request: Request, period: str = RF.ALL, book: str = "", next: str = "/mirror"):
    """Remember the chosen period and book, then go back to the page it was chosen on. Only a
    report address is gone back to; anything else goes to the report's home."""
    back = next if next.startswith("/mirror") and "//" not in next else "/mirror"
    response = RedirectResponse(back, status_code=303)
    chosen = RF.ReportFilter(period or RF.ALL, book or None)
    if chosen.active:
        response.set_cookie(RF.COOKIE, chosen.encode(), httponly=True, samesite="lax", path="/")
    else:
        response.delete_cookie(RF.COOKIE, path="/")
    return response


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


CHAPTER_SURFACE = "scope_chapter"
"""Not one of /events' surfaces: the page can't claim a chapter was opened, only the route can."""


@router.get("/mirror", response_class=HTMLResponse)
def scope_home(request: Request):
    """Scope home (handoff 4, level 1): the four chapters on the dial, the five days'
    share in its centre. Replaces the long Mirror page; its sentences live on in the
    chapters and facts, word for word (tests/unit/mirror/test_wording_reference.py)."""
    early, record = load_record(request)
    if early is not None:
        return early
    trips, imp, context = record
    with make_session(request.app.state.engine) as sess:
        trader = reader(request, sess)
        charges = charge_record.build(sess, trader, imp)
        declared = rb.in_force(rb.for_trader(sess, trader), trader_today().isoformat())
        number = rb.rupees(declared)
    history = getattr(request.state, "history", None) or trips
    bar = getattr(request.state, "report_filter", None)
    filter_books = {} if bar is None else {
        b["label"]: b["href"] for b in bar["books"] if b["label"] != "All books"}
    return page(request, "scope/home.html", title="Scope", enter_class=enter_class(request),
                by_year=RF.by_year(history), filter_books=filter_books,
                imp=imp, trade_count=len(trips), trading_day_count=context["file_trading_days"],
                charges=charges,
                **SF.home_context(context, imp, _opened_chapters(request), number=number))


@router.get("/mirror/chapter/{n}", response_class=HTMLResponse)
def scope_chapter(request: Request, n: int):
    """A chapter: the dial re-divided into its facts, a story card for each."""
    try:
        chapter = SM.chapter(n)
    except KeyError:
        raise HTTPException(status_code=404) from None  # the Not found page, with its way Home (TICKET-860)
    early, record = load_record(request)
    if early is not None:
        return early
    _trips, imp, context = record
    if not is_sample(request):  # a visitor to /sample leaves nothing behind
        _mark_opened(request, chapter)
    figs = SF.facts(context, imp)
    return page(request, "scope/chapter.html", title=chapter.name,
                enter_class=enter_class(request), chapter=chapter,
                view=SF.chapter_view(n, figs), facts=figs, imp=imp,
                next_step=SF.chapter_next(n),
                trading_day_count=len(context["days"].counts),
                sources=s_enums.RiskUnitSourceV1, **_feedback_context(request, n),
                **context)


def _opened_chapters(request: Request) -> frozenset[int]:
    """The chapters this trader has opened, whichever upload he was reading."""
    if is_sample(request):
        return frozenset()
    with make_session(request.app.state.engine) as sess:
        trader = current_trader(request, sess)
        keys = set(sess.scalars(select(m.DwellEvent.key).where(
            m.DwellEvent.trader_id == trader.id, m.DwellEvent.surface == CHAPTER_SURFACE)))
    return frozenset(c.number for c in SM.CHAPTERS if c.name in keys)


def _mark_opened(request: Request, chapter: SM.Chapter) -> None:
    """Noted on the server, so "read" doesn't depend on a script running. One row a chapter;
    the key is its name, because an event's key never holds a digit (routes_events)."""
    with make_session(request.app.state.engine) as sess:
        trader = current_trader(request, sess)
        seen = sess.scalar(select(m.DwellEvent.id).where(
            m.DwellEvent.trader_id == trader.id, m.DwellEvent.surface == CHAPTER_SURFACE,
            m.DwellEvent.key == chapter.name).limit(1))
        if seen is None:
            sess.add(m.DwellEvent(trader_id=trader.id, surface=CHAPTER_SURFACE, key=chapter.name,
                                  event="view", at=datetime.now(UTC), duration_ms=None))
            sess.commit()


def _feedback_context(request: Request, n: int) -> dict:
    """What the feedback row needs: where it stands, its choices, where it posts."""
    if n not in FB.CHAPTERS or is_sample(request):
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


def _moved(request: Request, key: str, rest: str = "") -> RedirectResponse:
    """A fact that merged into another: same page below it, same query. No record is read,
    so the page it lands on is the one that asks for a login."""
    query = f"?{request.url.query}" if request.url.query else ""
    return RedirectResponse(f"/mirror/fact/{SM.MOVED_FACTS[key]}{rest}{query}", status_code=301)


@router.get("/mirror/fact/{key}", response_class=HTMLResponse)
def scope_fact(request: Request, key: str):
    """A fact (handoff 4, level 3): the lens and path, the Mirror's sentences and
    figures, then every trade behind it."""
    if key in SM.MOVED_FACTS:
        return _moved(request, key)
    if key == SHARE_MOVED:  # it was fact 2 of chapter 1; its one new row is on worst days now
        return RedirectResponse(SM.fact_href("worst-days", lens=False), status_code=303)
    if key not in SM.FACTS:
        raise HTTPException(status_code=404)  # the Not found page, with its way Home (TICKET-860)
    early, record = load_record(request)
    if early is not None:
        return early
    _trips, imp, context = record
    chapter, index = SM.chapter_of(key)
    unread = _unread(request, imp) if key == "unread" else {}
    figs = SF.facts(context, imp)
    ending = {"ending": _ending(request, imp, figs[key])} if key == "not-told" else {}
    flagged = {"flagged_days": _flagged_days(request, imp)} if key == "worst-days" else {}
    journals = _journal_links(request, key, figs[key], context)
    return page(request, f"scope/facts/{key}.html", title=SM.FACTS[key].title,
                enter_class=enter_class(request), body_class="screen__body--fact",
                chapter=chapter, index=index, number=index + 1, fact=SM.FACTS[key],
                back_href=SM.chapter_href(chapter.number, fact=index + 1),
                f=figs[key], facts=figs,
                groups=[] if figs[key]["see_all"] else SM.groups(key, context), imp=imp,
                trading_day_count=len(context["days"].counts),
                sources=s_enums.RiskUnitSourceV1, **unread, **ending, **flagged, **journals,
                **context)


def _flagged_days(request: Request, imp) -> set[str]:
    if is_sample(request):
        return set()
    with make_session(request.app.state.engine) as sess:
        return FB.flagged_days(sess, current_trader(request, sess), imp.id)


def _journal_ids(sess, trader, days: set[str]) -> dict[str, int]:
    """The newest DAY journal for each of `days`. Ascending version_no, so the latest version
    of a day is the one left in the map; a day with no journal is not in it."""
    if not days:
        return {}
    return dict(sess.execute(
        select(m.Journal.period_start, m.Journal.id)
        .where(m.Journal.trader_id == trader.id, m.Journal.unit == s_enums.JournalUnit.DAY,
               m.Journal.period_start.in_(sorted(days)))
        .order_by(m.Journal.version_no)
    ).all())


def _journal_links(request: Request, key: str, fact: dict, context: dict) -> dict:
    """A finding links the journal of the day it is about, or shows no link (TICKET-839).
    Worst days: one href per block whose day has a journal. The run: the day it began."""
    if is_sample(request):  # its Journals are no visitor's to open
        return {}
    if key == "worst-days":
        days = {b["iso"] for b in fact["blocks"]}
    elif key == "run" and context["run"].days:
        days = {context["run"].days[0]}
    else:
        return {}
    with make_session(request.app.state.engine) as sess:
        opens = _journal_ids(sess, current_trader(request, sess), days)
    hrefs = {day: f"/journals/{jid}" for day, jid in opens.items()}
    if key == "worst-days":
        return {"journal_hrefs": hrefs}
    return {"run_journal_href": hrefs.get(context["run"].days[0])}


def _ending(request: Request, imp, fact: dict) -> dict:
    """What the report's last page reads from beyond the record (TICKET-825)."""
    with make_session(request.app.state.engine) as sess:
        trader = reader(request, sess)
        worst = fact["flagged"]["worst"]
        opens = {} if worst is None else _journal_ids(sess, trader, {worst["iso"]})
        earlier = sess.scalars(
            select(m.Import).join(m.Trip, m.Trip.import_id == m.Import.id)
            .where(m.Import.trader_id == trader.id, m.Import.id < imp.id)
            .order_by(m.Import.id.desc()).limit(1)
        ).first()
        return {
            "journal_href": f"/journals/{opens[worst['iso']]}"
            if worst and worst["iso"] in opens else "/journals",
            "changed": earlier and {
                "trades": (imp.trips_reconstructed, earlier.trips_reconstructed),
                "days": (_trading_days(sess, imp.id), _trading_days(sess, earlier.id)),
                # One file read again is not a new file (TICKET-844).
                "same_file": persist.same_file(sess, imp, earlier),
            },
            "answered": FB.report_answer(sess, trader, imp.id) is not None,
            "answers": FB.ANSWERS,
            "note_limit": FB.NOTE_LIMIT,
        }


def _trading_days(sess, import_id: int) -> int:
    return sess.scalar(
        select(func.count(distinct(m.Trip.trading_day))).where(m.Trip.import_id == import_id)
    )


@router.post("/mirror/feedback", response_class=HTMLResponse)
def report_feedback(request: Request, answer: str = Form(None), note: str = Form(None),
                    csrf_token: str = Form(None)):
    """The whole report: one answer and an optional note, on the report's last page."""
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
            FB.record_report_answer(sess, trader=trader, import_id=imp.id,
                                    answer=answer or "", note=note)
        except FB.NotAsked:
            return HTMLResponse("", status_code=400)
        sess.commit()
    return RedirectResponse(f"{SM.fact_href('not-told', lens=False)}#report-check",
                            status_code=303)


@router.post("/mirror/feedback/day", response_class=HTMLResponse)
def day_feedback(request: Request, trading_day: str = Form(None), note: str = Form(None),
                 csrf_token: str = Form(None)):
    """"Is this day wrong?" on one of the five worst days, which it must be."""
    if not require_csrf(request, csrf_token):
        return HTMLResponse("Form expired. Reload the page and try again.", status_code=403)
    early, record = load_record(request)
    if early is not None:
        return early
    _trips, imp, context = record
    if trading_day not in {b.trading_day for b in context["day_blocks"]}:
        return HTMLResponse("", status_code=400)
    with make_session(request.app.state.engine) as sess:
        FB.flag_day(sess, trader=current_trader(request, sess), import_id=imp.id,
                    trading_day=trading_day, note=note)
        sess.commit()
    return RedirectResponse(f"{SM.fact_href('worst-days', lens=False)}#day-{trading_day}",
                            status_code=303)


@router.get("/mirror/fact/{key}/trades", response_class=HTMLResponse)
def scope_fact_trades(request: Request, key: str):
    """Every trade behind a fact, with the filters the fact page has no room for. A fact
    page links here when its list is long (TICKET-822), so nothing behind it is out of reach."""
    if key in SM.MOVED_FACTS:
        return _moved(request, key, "/trades")
    if key not in TL.FACTS_WITH_TRADES:
        raise HTTPException(status_code=404)  # the Not found page, with its way Home (TICKET-860)
    early, record = load_record(request)
    if early is not None:
        return early
    _trips, imp, context = record
    with make_session(request.app.state.engine) as sess:
        expiries = loader.expiries_for(sess, imp)
    chapter, index = SM.chapter_of(key)
    return page(request, "scope/trades.html", title=f"{SM.FACTS[key].title}: see all trades",
                body_class="screen__body--fact", chapter=chapter, index=index,
                fact=SM.FACTS[key], fact_href=SM.fact_href(key, lens=False), imp=imp,
                listing=TL.listing(key, context, request.query_params, expiries))


CONFIRMED_ROW = "You told us this row repeats a trade already in the file."


def _plain_refusal(reason: str) -> str:
    """Why a stored trade was refused, for a trader. New uploads refuse no sold option."""
    if "short option" in reason:
        return "A sold option. Scope did not count these when this file was read."
    return "Scope could not count this trade when this file was read."


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
            "excluded": [(r.row_no, r.reason or CONFIRMED_ROW)
                         for r in rows if r.status == "EXCLUDED"],
            "rejected": [(r.row_no, r.reason) for r in rows if r.status == "REJECTED"],
            "refused": [_plain_refusal(t.reason) for t in refused],
        }
