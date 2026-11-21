"""Your numbers (TICKET-988), at /numbers: his scoreboard, and his trades by the day he closed
them, by days left to expiry and by book. Read from the report's own record, under the report's
year and book filter, so it says what the report says. Nothing is computed here (numbers.build)."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from services.production.api import numbers as N
from services.production.api.routes_identity import page
from services.production.api.routes_mirror import load_record
from services.production.db.session import make_session
from services.production.mirror import loader

router = APIRouter()


@router.get("/numbers", response_class=HTMLResponse)
def your_numbers(request: Request):
    early, record = load_record(request)
    if early is not None:
        return early
    trips, imp, _context = record
    with make_session(request.app.state.engine) as sess:
        expiries = loader.expiries_for(sess, imp)
    view = N.build(trips, expiries, gross=not imp.fees_available)
    return page(request, "numbers.html", title="Your numbers", imp=imp, **view)
