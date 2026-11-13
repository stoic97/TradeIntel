"""Rules he sets by tapping, and whether he kept them (TICKET-922).

**His rules, our counting, never our suggestion.** These screens record what he chose,
when he chose it, and what happened after. They never propose a rule, rank one, choose a
chip in advance, or call a rule good; every chip is shown alike, in the order
``rules.chips`` lists it. Every input is a tap: a button carrying a chip's value, never
a text box. A chip the lists don't hold is refused.

A rule is never edited. Tapping again sets a newer one, which governs only the trades
opened after it (``rules.adherence``), so a rule a trade was matched to can't change.

Three screens, cheapest first: before the session (today's limit, most trades, what
would make me stop), a standing rule (a factor, then a value), and before a trade (book,
then reason, matched to a fill on the next upload). The overview counts each rule, cost
and trade count first, and says "Not enough trades yet" until the number stated at the
start.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from services.production.api.routes_consent import has_diagnosis_consent, trader_today
from services.production.api.routes_identity import current_trader, page, require_csrf
from services.production.db import models as m
from services.production.db.session import make_session
from services.production.mirror import loader
from services.production.mirror import metrics as mx
from services.production.rules import adherence as A
from services.production.rules import chips

router = APIRouter()

EXPIRED = "Form expired. Reload the page and try again."


def _signed_in(request: Request, sess):
    trader = current_trader(request, sess)
    if trader is None:
        return None, RedirectResponse("/login", status_code=303)
    if not has_diagnosis_consent(sess, trader):
        return None, RedirectResponse("/consent", status_code=303)
    return trader, None


def _rules(sess, trader) -> list[A.Rule]:
    rows = sess.scalars(select(m.RuleDeclaration).where(
        m.RuleDeclaration.trader_id == trader.id, m.RuleDeclaration.factor.is_not(None))).all()
    return [A.Rule(r.id, r.factor, r.value, r.declared_at, r.applies_from, r.applies_to, r.text)
            for r in rows]


def _fees(sess, imp) -> dict[str, Decimal] | None:
    """Charges per trade as the report reads trades, when his file carries them."""
    if imp is None or not imp.fees_available:
        return None
    out: dict[str, Decimal] = defaultdict(Decimal)
    for row in sess.scalars(select(m.Trip).where(m.Trip.import_id == imp.id)):
        out[row.position_id or row.trip_id] += row.fees or Decimal(0)
    return dict(out)


def _declare(sess, trader, factor: str, value: int, screen: str) -> None:
    today = trader_today().isoformat()
    f = chips.FACTORS[factor]
    sess.add(m.RuleDeclaration(trader_id=trader.id, text=f.words(value),
                               declared_at=datetime.now(UTC), factor=factor, value=value,
                               applies_from=today,
                               applies_to=today if screen == "before_session" else None,
                               screen=screen))
    sess.commit()


def _chip(factor: str, value: str) -> int | None:
    """The chip's value, if it is one the lists hold; anything else is refused."""
    f = chips.FACTORS.get(factor)
    if f is None or not value.isdigit() or int(value) not in f.values:
        return None
    return int(value)


@router.get("/rules", response_class=HTMLResponse)
def rules(request: Request):
    with make_session(request.app.state.engine) as sess:
        trader, away = _signed_in(request, sess)
        if away:
            return away
        declared = _rules(sess, trader)
        trips, imp = loader.load_for(sess, trader)
        fees = _fees(sess, imp)
        notes = sess.scalars(select(m.PreTradeNote).where(
            m.PreTradeNote.trader_id == trader.id)).all()
    counts = A.count(declared, trips, fees)
    matched = A.match_notes(list(notes), trips, book_of=mx.trade_book)
    return page(request, "rules.html", title="Rules you set", counts=counts,
                verdict_at=A.VERDICT_AT, notes=len(notes), notes_matched=len(matched),
                fees_known=fees is not None)


@router.get("/rules/today", response_class=HTMLResponse)
def before_session(request: Request):
    with make_session(request.app.state.engine) as sess:
        trader, away = _signed_in(request, sess)
        if away:
            return away
        today = trader_today().isoformat()
        set_today = {}
        for r in sorted(_rules(sess, trader), key=lambda r: (r.declared_at, r.id)):
            if r.applies_from == today and r.applies_to == today:
                set_today[r.factor] = r
    return page(request, "rules_today.html", title="Before the session",
                factors=[chips.FACTORS[k] for k in chips.BEFORE_SESSION], set_today=set_today)


@router.post("/rules/today")
def before_session_set(request: Request, factor: str = Form(""), value: str = Form(""),
                       csrf_token: str = Form(None)):
    if not require_csrf(request, csrf_token):
        return HTMLResponse(EXPIRED, status_code=403)
    chip = _chip(factor, value) if factor in chips.BEFORE_SESSION else None
    if chip is None:
        return HTMLResponse("That is not one of the choices.", status_code=400)
    with make_session(request.app.state.engine) as sess:
        trader, away = _signed_in(request, sess)
        if away:
            return away
        _declare(sess, trader, factor, chip, "before_session")
    return RedirectResponse("/rules/today", status_code=303)


@router.get("/rules/set", response_class=HTMLResponse)
def standing(request: Request, factor: str | None = None):
    with make_session(request.app.state.engine) as sess:
        _trader, away = _signed_in(request, sess)
        if away:
            return away
    chosen = chips.FACTORS.get(factor) if factor else None
    return page(request, "rules_set.html", title="Set a rule",
                factors=list(chips.FACTORS.values()), chosen=chosen)


@router.post("/rules/set")
def standing_set(request: Request, factor: str = Form(""), value: str = Form(""),
                 csrf_token: str = Form(None)):
    if not require_csrf(request, csrf_token):
        return HTMLResponse(EXPIRED, status_code=403)
    chip = _chip(factor, value)
    if chip is None:
        return HTMLResponse("That is not one of the choices.", status_code=400)
    with make_session(request.app.state.engine) as sess:
        trader, away = _signed_in(request, sess)
        if away:
            return away
        _declare(sess, trader, factor, chip, "standing")
    return RedirectResponse("/rules", status_code=303)


def _books(trips) -> list[str]:
    return sorted({mx.trade_book(t) for t in trips}) + [chips.OTHER_BOOK]


@router.get("/rules/click", response_class=HTMLResponse)
def before_click(request: Request, book: str | None = None):
    with make_session(request.app.state.engine) as sess:
        trader, away = _signed_in(request, sess)
        if away:
            return away
        trips, _imp = loader.load_for(sess, trader)
    books = _books(trips)
    return page(request, "rules_click.html", title="Before a trade", books=books,
                book=book if book in books else None, reasons=chips.REASONS, noted=None)


@router.post("/rules/click", response_class=HTMLResponse)
def before_click_note(request: Request, book: str = Form(""), reason: str = Form(""),
                      csrf_token: str = Form(None)):
    if not require_csrf(request, csrf_token):
        return HTMLResponse(EXPIRED, status_code=403)
    with make_session(request.app.state.engine) as sess:
        trader, away = _signed_in(request, sess)
        if away:
            return away
        trips, imp = loader.load_for(sess, trader)
        books = _books(trips)
        if book not in books or reason not in chips.REASONS:
            return HTMLResponse("That is not one of the choices.", status_code=400)
        sess.add(m.PreTradeNote(trader_id=trader.id, book=book, reason=reason,
                                entered_at=datetime.now(UTC)))
        sess.commit()
        fees = _fees(sess, imp)
    in_book = [t for t in trips if book == chips.OTHER_BOOK or mx.trade_book(t) == book]
    paid = [fees[t.trip_id] for t in in_book if fees and t.trip_id in fees]
    record = {
        "trades": len(in_book),
        "won": sum(t.is_win for t in in_book),
        "cost": (sum(paid, Decimal(0)) / len(paid)) if paid else None,
    }
    return page(request, "rules_click.html", title="Before a trade", books=books, book=book,
                reasons=chips.REASONS, noted={"book": book, "reason": reason, **record})
