"""The challenge: start one by taps, see how far it has got after every upload,
finish or stop it, and, if he wants, share its card by a link he can take away again.

Counts only (``rules.challenge``). The public card at ``/c/<token>`` carries the rules' words
and the counts, never a rupee result, his name or his login id, and needs no sign-in.
"""
from __future__ import annotations

import json
import secrets
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from services.production.api.routes_consent import trader_today
from services.production.api.routes_identity import page, require_csrf
from services.production.api.routes_rules import EXPIRED, _rules, _signed_in
from services.production.db import models as m
from services.production.db.session import make_session
from services.production.mirror import loader
from services.production.rules import challenge as C
from services.shared.market import closures

router = APIRouter()

EXCHANGE = "NSE"
"""Whose trading days a challenge counts. The closures file holds NSE's and BSE's, which are
the same days; MCX isn't in it, so a crude trader's challenge reads NSE's (the ticket's
"NSE when unsure")."""


def _closed() -> frozenset[date]:
    known = closures.load().get(EXCHANGE)
    return known.closed if known else frozenset()


def _last_file_day(trips) -> date | None:
    return max((date.fromisoformat(t.trading_day) for t in trips), default=None)


def _latest(sess, trader) -> m.Challenge | None:
    return sess.scalars(select(m.Challenge).where(m.Challenge.trader_id == trader.id)
                        .order_by(m.Challenge.id.desc()).limit(1)).first()


def _days(row: m.Challenge) -> list[date]:
    first = date.fromisoformat(row.start_day)
    return [first, *C.trading_days(first, row.length - 1, _closed())]


def _progress(sess, trader, row: m.Challenge, trips) -> C.Progress:
    ids = json.loads(row.rule_ids)
    rules = [r for r in _rules(sess, trader) if r.id in ids]
    rules.sort(key=lambda r: ids.index(r.id))
    return C.progress(_days(row), rules, trips, _last_file_day(trips))


def _end(row: m.Challenge, progress: C.Progress, how: str) -> None:
    """End it and keep its card as it reads now: a card is counted as at the moment it ended,
    never recounted from a later upload."""
    row.ended_at, row.ended_how = datetime.now(UTC), how
    row.card_line = C.card_line(progress, stopped=how == "stopped")


def _view(sess, trader, row: m.Challenge, trips) -> dict:
    """How far it has got, and the card; a challenge the files now cover ends as finished."""
    progress = _progress(sess, trader, row, trips)
    if row.ended_at is None and progress.finished:
        _end(row, progress, "finished")
        sess.commit()
    card = None
    if row.ended_at is not None:
        card = row.card_line or C.card_line(progress, stopped=row.ended_how == "stopped")
    return {"row": row, "progress": progress, "running": row.ended_at is None, "card": card}


def home_card(sess, trader, trips) -> dict | None:
    """Home's card while a challenge runs: how far it has got, and the pull back when a day of
    it has passed beyond his latest file (ADR-007 has no email, so this is the only one)."""
    row = _latest(sess, trader)
    if row is None or row.ended_at is not None:
        return None
    view = _view(sess, trader, row, trips)
    if not view["running"]:
        return None
    waiting = view["progress"].next_day
    view["waiting"] = (view["progress"].so_far + 1) if waiting is not None and waiting < trader_today() else None
    return view


@router.get("/challenge", response_class=HTMLResponse)
def challenge_page(request: Request):
    with make_session(request.app.state.engine) as sess:
        trader, away = _signed_in(request, sess)
        if away:
            return away
        trips, _imp = loader.load_for(sess, trader)
        row = _latest(sess, trader)
        view = _view(sess, trader, row, trips) if row is not None else None
        rules = sorted(_rules(sess, trader), key=lambda r: (r.declared_at, r.id), reverse=True)
    return page(request, "challenge.html", title="Your challenge", view=view, rules=rules,
                lengths=C.LENGTHS, most=C.MAX_RULES)


@router.post("/challenge/start")
def challenge_start(request: Request, length: str = Form(""), rule: Annotated[list[str] | None, Form()] = None,
                    csrf_token: str = Form(None)):
    rule = rule or []
    if not require_csrf(request, csrf_token):
        return HTMLResponse(EXPIRED, status_code=403)
    with make_session(request.app.state.engine) as sess:
        trader, away = _signed_in(request, sess)
        if away:
            return away
        mine = {r.id for r in _rules(sess, trader)}
        chosen = [int(r) for r in dict.fromkeys(rule) if r.isdigit() and int(r) in mine]
        if not length.isdigit() or int(length) not in C.LENGTHS or not 1 <= len(chosen) <= C.MAX_RULES \
                or len(chosen) != len(set(rule)):
            return HTMLResponse("Choose 10 or 20 trading days and one to three of the rules you set.",
                                status_code=400)
        latest = _latest(sess, trader)
        if latest is not None and latest.ended_at is None:
            return HTMLResponse("A challenge is already running.", status_code=409)
        trips, _imp = loader.load_for(sess, trader)
        first = C.start_day(trader_today(), _last_file_day(trips), _closed())
        _take_links_down(sess, trader)  # an earlier card's link never outlives the page that removes it
        sess.add(m.Challenge(trader_id=trader.id, rule_ids=json.dumps(chosen), length=int(length),
                             start_day=first.isoformat(), started_at=datetime.now(UTC)))
        sess.commit()
    return RedirectResponse("/challenge", status_code=303)


def _take_links_down(sess, trader) -> None:
    for row in sess.scalars(select(m.Challenge).where(m.Challenge.trader_id == trader.id,
                                                      m.Challenge.share_token.is_not(None))):
        row.share_token = None


def _ended(request: Request, csrf_token: str | None, change) -> RedirectResponse | HTMLResponse:
    if not require_csrf(request, csrf_token):
        return HTMLResponse(EXPIRED, status_code=403)
    with make_session(request.app.state.engine) as sess:
        trader, away = _signed_in(request, sess)
        if away:
            return away
        row = _latest(sess, trader)
        if row is None:
            return HTMLResponse("There is no challenge.", status_code=404)
        refused = change(sess, trader, row)
        if refused:
            return HTMLResponse(refused, status_code=409)
        sess.commit()
    return RedirectResponse("/challenge", status_code=303)


@router.post("/challenge/stop")
def challenge_stop(request: Request, csrf_token: str = Form(None)):
    def stop(sess, trader, row):
        if row.ended_at is not None:
            return "This challenge has already ended."
        trips, _imp = loader.load_for(sess, trader)
        _end(row, _progress(sess, trader, row, trips), "stopped")
        return None
    return _ended(request, csrf_token, stop)


@router.post("/challenge/share")
def challenge_share(request: Request, csrf_token: str = Form(None)):
    def share(sess, trader, row):
        if row.ended_at is None:
            return "A challenge can be shared once it has ended."
        row.share_token = row.share_token or secrets.token_urlsafe(16)
        return None
    return _ended(request, csrf_token, share)


@router.post("/challenge/unshare")
def challenge_unshare(request: Request, csrf_token: str = Form(None)):
    def unshare(sess, trader, row):
        _take_links_down(sess, trader)  # every link of his, not only the newest card's
    return _ended(request, csrf_token, unshare)


@router.get("/c/{token}", response_class=HTMLResponse)
def shared_card(request: Request, token: str):
    """The completion card for anyone with the link: counts and the rules' words, nothing else."""
    with make_session(request.app.state.engine) as sess:
        row = sess.scalars(select(m.Challenge).where(m.Challenge.share_token == token)).first() \
            if token else None
        if row is None or row.ended_at is None:
            raise HTTPException(status_code=404)
        trader = sess.get(m.Trader, row.trader_id)
        trips, _imp = loader.load_for(sess, trader)
        view = _view(sess, trader, row, trips)
    return page(request, "challenge_shared.html", title="A challenge, finished on Scope",
                card=view["card"])
