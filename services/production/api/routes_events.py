"""Dwell events: which lines a trader opened, and for how long.

PRD decision 12. The Mirror's order is fixed in v1; this is what lets v2 reorder it
per trader. Nothing in v1 reads it, and it is collected now because retrofitting
would mean the first partners use a product that learns nothing from them.

Three rules, each a deliberate limit rather than an oversight:

**A fixed vocabulary.** Only the surfaces and events below are stored. An endpoint
that accepts any key is a general-purpose tracker, and that is not what the trader
consented to.

**No figure ever enters an event.** A line is named by its slug; what the line says
stays out. A test asserts no stored field contains a digit.

**It never breaks the page.** Malformed input returns 204 and stores nothing.
Telemetry that can take down the screen it measures has its priorities backwards.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request, Response

from services.production.api.routes_identity import current_trader
from services.production.db import models as m
from services.production.db.session import make_session

router = APIRouter()

SURFACES = {"mirror_line", "journal_section"}
EVENTS = {"view", "drawer_open", "leave"}
MAX_EVENTS_PER_POST = 50
MAX_DURATION_MS = 1000 * 60 * 30
"""Half an hour. Longer means a tab was left open, not that a line was read."""


@router.post("/events", status_code=204)
async def record(request: Request) -> Response:
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001 - a bad body is not an error worth reporting
        return Response(status_code=204)

    if not isinstance(body, dict) or not isinstance(body.get("events"), list):
        return Response(status_code=204)

    with make_session(request.app.state.engine) as sess:
        trader = current_trader(request, sess)
        if trader is None:
            return Response(status_code=204)

        now = datetime.now(UTC)
        stored = 0
        for raw in body["events"][:MAX_EVENTS_PER_POST]:
            if not isinstance(raw, dict):
                continue
            surface, key, event = raw.get("surface"), raw.get("key"), raw.get("event")
            if surface not in SURFACES or event not in EVENTS:
                continue
            if not isinstance(key, str) or not key or any(ch.isdigit() for ch in key):
                continue

            duration = raw.get("duration_ms")
            if not isinstance(duration, int) or duration < 0 or duration > MAX_DURATION_MS:
                duration = None

            sess.add(m.DwellEvent(trader_id=trader.id, surface=surface, key=key,
                                  event=event, at=now, duration_ms=duration))
            stored += 1
        if stored:
            sess.commit()
    return Response(status_code=204)
