"""Moved out of tests/unit/api/test_scope_chapters.py by TICKET-945, so that no test file imports another.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from services.production.api import scope_facts as SF
from services.production.api import scope_map as S
from services.production.mirror import feedback as FB
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s
from tests.unit.api.templating import template_env

TRIPS = mx.load_trips(json.loads(Path("tests/fixtures/mirror_contract/main.json").read_text()))


IMP = SimpleNamespace(
    id=7,
    code_version="fixturesha",
    adapter_id="dhan_tradebook_v1",
    rows_in=40,
    rows_parsed=40,
    rows_excluded=0,
    trips_reconstructed=40,
    trips_refused=0,
    fees_available=False,
)


def trips_from(nets: list[int], source=s.RiskUnitSourceV1.DECLARED_BUDGET) -> list[mx.Trip]:
    """A made-up history: one ten-minute trade a day at 09:15, one day after another."""
    start = datetime.fromisoformat("2026-09-01T09:15:00+05:30")
    out = []
    for i, net in enumerate(nets):
        entry = start + timedelta(days=i)
        out.append(
            mx.Trip(
                f"t{i}",
                "WIDGETOIL",
                entry.date().isoformat(),
                entry,
                entry + timedelta(minutes=10),
                600,
                Decimal(net),
                1,
                source,
            )
        )
    return out


def chapter_page(n: int, trips=TRIPS, imp=IMP, feedback=None) -> str:
    """What routes_mirror.scope_chapter renders, without the app."""
    ctx = SF.record_context(trips)
    figs = SF.facts(ctx, imp)
    asked = {
        "feedback": feedback or FB.State(None, None),
        "feedback_answers": FB.ANSWERS,
        "feedback_reasons": FB.REASONS,
        "feedback_url": f"/mirror/chapter/{n}/feedback",
        "csrf_token": "t",
    }
    return (
        template_env()
        .get_template("scope/chapter.html")
        .render(
            title=S.chapter(n).name,
            chapter=S.chapter(n),
            view=SF.chapter_view(n, figs),
            facts=figs,
            imp=imp,
            trading_day_count=len(ctx["days"].counts),
            sources=s.RiskUnitSourceV1,
            **(asked if n in FB.CHAPTERS else {}),
            **ctx,
        )
    )


CTX = SF.record_context(TRIPS)


FIGS = SF.facts(CTX, IMP)


def readable(html: str) -> str:
    text = re.sub(r"<[^>]+>", "", html).replace("&#39;", "'").replace("&amp;", "&")
    return " ".join(text.split())
