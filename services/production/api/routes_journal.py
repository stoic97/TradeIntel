"""The Journal screens (PRD 7).

Three things here are deliberate and would each be easy to get wrong.

**Five on the surface.** An upload that backfills a year generates every Journal and
shows the latest five, with the rest behind a catch-up link. The PRD says a developer
who renders sixty entries has built a defect, so the surface is a function
(``generate.surface``) rather than a slice written at the template.

**Opened is recorded before the question is asked.** The willingness-to-pay trigger
counts Journals opened, and the Journal being read right now is one of them -- so
``mark_opened`` runs before ``should_ask``, which is what makes the third opened
Journal the one that asks.

**No clock times on this page.** The trades are labelled by their order in the
period, not by time of day. Trip rows carry the timestamps as stored; converting
them to the instrument's zone is the Mirror loader's job, and a second copy of that
conversion here is a second place for it to be wrong. It was wrong once already --
every Mirror time rendered in UTC, so a 09:20 trade read as 03:50. The prose carries
the day's shape; the prompts only need to say which trade.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from services.production.api.routes_consent import has_diagnosis_consent
from services.production.api.routes_identity import current_trader, page, require_csrf
from services.production.db import models as m
from services.production.db.session import make_session
from services.production.journal import fields, prose, wtp
from services.production.journal import generate as gen

router = APIRouter()

PER_TRIP_PROMPTS = (
    ("planned_sl", "Where was your stop?"),
    ("rationale", "What was the trade?"),
    ("stop_existed_at_entry", "Was the stop on the chart when you entered? yes / no"),
)


def _gate(request: Request, sess):
    """The trader, or the response that sends him somewhere else first."""
    trader = current_trader(request, sess)
    if trader is None:
        return None, RedirectResponse("/login", status_code=303)
    if not has_diagnosis_consent(sess, trader):
        return None, RedirectResponse("/consent", status_code=303)
    return trader, None


def _owned(sess, trader: m.Trader, journal_id: int) -> m.Journal:
    """A Journal of another trader's is not found, not forbidden.

    Answering 403 would confirm the id exists and belongs to someone.
    """
    journal = sess.get(m.Journal, journal_id)
    if journal is None or journal.trader_id != trader.id:
        raise HTTPException(status_code=404)
    return journal


def _trips_of(sess, trader: m.Trader, journal: m.Journal) -> list[m.Trip]:
    """The trips this Journal covers, in the order they were opened.

    Looked up across all of the trader's imports rather than the current one: a
    Journal written from the first upload keeps its trades after the second lands.
    """
    ids = json.loads(journal.trip_ids)
    if not ids:
        return []
    found = sess.scalars(
        select(m.Trip).join(m.Import, m.Trip.import_id == m.Import.id)
        .where(m.Import.trader_id == trader.id, m.Trip.trip_id.in_(ids))
    ).all()
    return sorted(found, key=lambda t: t.entry_ts)


@router.get("/journals", response_class=HTMLResponse)
def journal_list(request: Request):
    with make_session(request.app.state.engine) as sess:
        trader, elsewhere = _gate(request, sess)
        if elsewhere is not None:
            return elsewhere
        surface = gen.surface(sess, trader=trader)
        return page(request, "journals.html", title="Your Journals",
                    latest=surface.latest, catch_up_count=surface.catch_up_count,
                    total=surface.total)


@router.get("/journals/catch-up", response_class=HTMLResponse)
def journal_catch_up(request: Request):
    with make_session(request.app.state.engine) as sess:
        trader, elsewhere = _gate(request, sess)
        if elsewhere is not None:
            return elsewhere
        return page(request, "journals_catch_up.html", title="Earlier Journals",
                    journals=gen.catch_up(sess, trader=trader))


@router.get("/journals/{journal_id}", response_class=HTMLResponse)
def journal_page(request: Request, journal_id: int):
    with make_session(request.app.state.engine) as sess:
        trader, elsewhere = _gate(request, sess)
        if elsewhere is not None:
            return elsewhere
        journal = _owned(sess, trader, journal_id)

        gen.mark_opened(sess, journal)
        sess.commit()

        paragraphs = [
            para.strip()
            for para in prose.render(json.loads(journal.sections)).split("\n\n")
            if para.strip()
        ]
        trips = _trips_of(sess, trader, journal)
        imp = sess.get(m.Import, journal.import_id)
        rows = [
            {"trip_id": t.trip_id, "label": f"Trade {n}", "net": f"{t.net:,.0f}"}
            for n, t in enumerate(trips, start=1)
        ]
        answers = {
            t.trip_id: {
                name: fields.current(sess, journal=journal, field=name,
                                     trip_id=t.trip_id)
                for name, _ in PER_TRIP_PROMPTS
            }
            for t in trips
        }
        return page(
            request, "journal.html", title=f"Your Journal, {journal.period_start}",
            journal=journal, paragraphs=paragraphs, rows=rows, answers=answers,
            prompts=PER_TRIP_PROMPTS, fees_available=bool(imp and imp.fees_available),
            note=fields.current(sess, journal=journal, field="note", trip_id=None),
            ask_wtp=wtp.should_ask(sess, trader=trader), wtp_question=wtp.QUESTION,
        )


@router.post("/journals/{journal_id}/field")
def journal_field(
    request: Request,
    journal_id: int,
    field: str = Form(...),
    value: str = Form(""),
    trip_id: str = Form(None),
    csrf_token: str = Form(None),
):
    if not require_csrf(request, csrf_token):
        return HTMLResponse("Form expired. Reload the page and try again.",
                            status_code=403)

    with make_session(request.app.state.engine) as sess:
        trader, elsewhere = _gate(request, sess)
        if elsewhere is not None:
            return elsewhere
        journal = _owned(sess, trader, journal_id)

        trip_id = trip_id or None
        trip_entry = trip_exit = None
        if trip_id is not None:
            trip = sess.scalars(
                select(m.Trip).join(m.Import, m.Trip.import_id == m.Import.id)
                .where(m.Import.trader_id == trader.id, m.Trip.trip_id == trip_id)
            ).first()
            if trip is None:
                raise HTTPException(status_code=404)
            trip_entry, trip_exit = trip.entry_ts, trip.exit_ts

        try:
            fields.record(sess, journal=journal, field=field, value=value,
                          trip_id=trip_id, trip_entry=trip_entry, trip_exit=trip_exit)
        except fields.UnknownField:
            raise HTTPException(status_code=400) from None
        sess.commit()
    return RedirectResponse(f"/journals/{journal_id}", status_code=303)


@router.post("/journals/{journal_id}/wtp")
def journal_wtp(
    request: Request,
    journal_id: int,
    answer: str = Form(...),
    free_text: str = Form(""),
    csrf_token: str = Form(None),
):
    if not require_csrf(request, csrf_token):
        return HTMLResponse("Form expired. Reload the page and try again.",
                            status_code=403)

    with make_session(request.app.state.engine) as sess:
        trader, elsewhere = _gate(request, sess)
        if elsewhere is not None:
            return elsewhere
        journal = _owned(sess, trader, journal_id)
        try:
            wtp.record(sess, trader=trader, journal=journal, answer=answer,
                       free_text=free_text)
        except wtp.NotAnAnswer:
            raise HTTPException(status_code=400) from None
        sess.commit()
    return RedirectResponse(f"/journals/{journal_id}", status_code=303)
