"""/replay: blind replay, one card at a time (TICKET-924).

Card, take it or skip it, the reveal, the next card, and at the end the score: calls
against a coin flip, count first. The answers ride in the address (``calls``, one letter a
card), so nothing is stored. The cards are dealt the same way every time for one trader.

Closed until three things hold, and the page says which is missing rather than guess:
the pre-registration is signed (``blind.PREREG_SIGNED``) or the record is the demo file;
the bars for his underlyings are here (``replay.sources``); and he has trades older than
``blind.OLD_AFTER_DAYS``.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from services.production import demo
from services.production.api import formatting
from services.production.api.routes_consent import has_diagnosis_consent, trader_today
from services.production.api.routes_identity import current_trader, page
from services.production.db.session import make_session
from services.production.mirror import loader
from services.production.replay import blind as B
from services.production.replay import sources
from services.shared.market.series import CRUDE_SERVES

router = APIRouter()

CALLS = frozenset("TS")


def today() -> date:
    return trader_today()


def _game(request: Request):
    """(response, None) to show instead, or (None, (dealt, series))."""
    with make_session(request.app.state.engine) as sess:
        trader = current_trader(request, sess)
        if trader is None:
            return RedirectResponse("/login", status_code=303), None
        if not has_diagnosis_consent(sess, trader):
            return RedirectResponse("/consent", status_code=303), None
        trips, imp = loader.load_for(sess, trader)
        key = str(trader.id)
    if not trips:
        return page(request, "replay_closed.html", title="Blind replay", why="no_file"), None
    if not B.PREREG_SIGNED and not demo.is_demo(imp):
        return page(request, "replay_closed.html", title="Blind replay", why="not_signed"), None
    entries = [B.Entry(t.trip_id, _underlying(t.symbol), t.entry_ts, B.direction_of(t))
               for t in trips]
    series = sources.series_for({e.underlying for e in entries})
    if not series:
        return page(request, "replay_closed.html", title="Blind replay", why="no_bars"), None
    dealt = B.deal(entries, series, today(), key=key, candidates=sources.candidates_for(series))
    if not dealt:
        return page(request, "replay_closed.html", title="Blind replay", why="not_old",
                     old_after=B.OLD_AFTER_DAYS), None
    return None, (dealt, series)


def _underlying(symbol: str) -> str:
    """One series per underlying: crude and its mini read the same one (series.CRUDE_SERVES)."""
    return "CRUDEOIL" if symbol in CRUDE_SERVES else symbol


def _calls(raw: str | None, dealt) -> str:
    calls = "".join(c for c in (raw or "") if c in CALLS)
    return calls[:len(dealt)]


@router.get("/replay", response_class=HTMLResponse)
def replay(request: Request):
    early, game = _game(request)
    if early is not None:
        return early
    dealt, _series = game
    return page(request, "replay.html", title="Blind replay", cards=len(dealt),
                old_after=B.OLD_AFTER_DAYS, window=B.WINDOW_MINUTES, horizon=B.HORIZON_MINUTES)


@router.get("/replay/card", response_class=HTMLResponse)
def card(request: Request, calls: str | None = None):
    early, game = _game(request)
    if early is not None:
        return early
    dealt, _series = game
    calls = _calls(calls, dealt)
    if len(calls) >= len(dealt):
        return RedirectResponse(f"/replay/score?calls={calls}", status_code=303)
    shown = dealt[len(calls)].card  # the card alone: whether it is his, and what came next, stay out
    return page(request, "replay_card.html", title="Blind replay", card=shown, cards=len(dealt),
                calls=calls, window=B.WINDOW_MINUTES, path=_path(shown))


@router.get("/replay/reveal", response_class=HTMLResponse)
def reveal(request: Request, calls: str | None = None):
    early, game = _game(request)
    if early is not None:
        return early
    dealt, series = game
    calls = _calls(calls, dealt)
    if not calls:
        return RedirectResponse("/replay/card", status_code=303)
    d = dealt[len(calls) - 1]
    return page(request, "replay_reveal.html", title="Blind replay", card=d.card, cards=len(dealt),
                calls=calls, took=calls[-1] == "T", revealed=(revealed := B.reveal(d, series)),
                moved=_moved(revealed.points, still="nowhere"),
                horizon=B.HORIZON_MINUTES, last=len(calls) == len(dealt),
                when=f"{formatting.day(d.card.moment.date().isoformat())}, "
                     f"{d.card.moment.strftime('%H:%M')}")


@router.get("/replay/score", response_class=HTMLResponse)
def score(request: Request, calls: str | None = None):
    early, game = _game(request)
    if early is not None:
        return early
    dealt, series = game
    calls = _calls(calls, dealt)
    counted = B.score(dealt, calls, series)
    return page(request, "replay_score.html", title="Blind replay", score=counted,
                inside=counted.band[0] <= counted.right <= counted.band[1],
                took=_moved(counted.took_points, still="either way"), horizon=B.HORIZON_MINUTES)


def _moved(points: float, *, still: str) -> dict[str, str]:
    """Points as written, whole and unsigned, and which way they went for him."""
    way = "your way" if points > 0 else "against you" if points < 0 else still
    return {"points": f"{abs(points):.0f}", "way": way}


def _path(card: B.Card) -> str:
    """The closes he sees, as one SVG polyline, scaled to the card's own range."""
    closes = [b.close for b in card.shown]
    low, high = min(closes), max(closes)
    span = (high - low) or 1.0
    width, height = 300, 120
    step = width / max(1, len(closes) - 1)
    return " ".join(f"{i * step:.1f},{height - (c - low) / span * height:.1f}"
                    for i, c in enumerate(closes))
