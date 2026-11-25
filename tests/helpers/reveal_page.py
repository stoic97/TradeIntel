"""Moved out of tests/unit/api/test_reveal_page.py by TICKET-945, so that no test file imports another.
"""

from __future__ import annotations

from services.production.api import scope_facts as SF
from tests.helpers.scope_chapters import IMP, TRIPS
from tests.unit.api.templating import template_env


def reveal(trips=TRIPS, guessed="[guess option 3, TR-009]") -> str:
    ctx = SF.record_context(trips)
    return (
        template_env()
        .get_template("reveal.html")
        .render(
            title=SF.reveal_days(ctx)["title"],
            reveal_days=SF.reveal_days(ctx),
            screen_class="screen--navy on-navy",
            body_class="reveal",
            guessed=guessed,
            imp=IMP,
            view=SF.reveal_view(ctx),
            worst_href="/mirror/fact/worst-days?enter=lens",
            **ctx,
        )
    )
