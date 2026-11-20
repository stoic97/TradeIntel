"""Moved out of tests/unit/api/test_scope_facts.py by TICKET-945, so that no test file imports another."""

from __future__ import annotations

from services.production.api import scope_facts as SF
from services.production.api import scope_map as S
from services.shared.schemas import scope_v1 as s
from tests.helpers.scope_chapters import IMP, TRIPS
from tests.unit.api.templating import template_env

UNREAD = {"excluded": [(3, "A header row repeated mid-file")], "rejected": [], "refused": []}


ENDING = {
    "journal_href": "/journals",
    "changed": None,
    "answered": False,
    "answers": {},
    "note_limit": 2000,
}


def fact_page(key: str, trips=TRIPS, imp=IMP, unread=UNREAD) -> str:
    """What routes_mirror.scope_fact renders, without the app."""
    ctx = SF.record_context(trips)
    figs = SF.facts(ctx, imp)
    chapter, index = S.chapter_of(key)
    return (
        template_env()
        .get_template(f"scope/facts/{key}.html")
        .render(
            title=S.FACTS[key].title,
            body_class="screen__body--fact",
            chapter=chapter,
            index=index,
            number=index + 1,
            fact=S.FACTS[key],
            back_href=S.chapter_href(chapter.number, fact=index + 1),
            f=figs[key],
            facts=figs,
            groups=S.groups(key, ctx),
            imp=imp,
            trading_day_count=len(ctx["days"].counts),
            sources=s.RiskUnitSourceV1,
            **(unread if key == "unread" else {}),
            **({"ending": ENDING} if key == "not-told" else {}),
            **ctx,
        )
    )
