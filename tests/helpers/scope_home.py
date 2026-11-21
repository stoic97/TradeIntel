"""Moved out of tests/unit/api/test_scope_home.py by TICKET-945, so that no test file imports another.
"""

from __future__ import annotations

from services.production.api import scope_facts as SF
from tests.helpers.scope_chapters import IMP, TRIPS
from tests.unit.api.templating import template_env


def home_page(trips=TRIPS, imp=IMP) -> str:
    ctx = SF.record_context(trips)
    return template_env().get_template("scope/home.html").render(
        title="Scope", imp=imp, trade_count=len(trips),
        trading_day_count=len(ctx["days"].counts), **SF.home_context(ctx, imp))
