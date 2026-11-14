"""How old a day is, and which days are new (TICKET-906).

A day is new within NEW_DAY_WITHIN_DAYS calendar days of today - the founder's ruling,
13 Nov 2026. Today, not the upload's export date: an upload opened months later must not
ask straight away about days months old. Anchored to today a day can only drift from
"asks straight away" to "do you remember", never back - a prompt that grows more careful
on its own. There is no export-date fallback because there is no export date here.

Today is the trader's, in IST, as the budget and consent pages read it. Tests pin it by
replacing ``today``; callers read it through this module so they can.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from services.production.journal import constants as k

TRADER_ZONE = ZoneInfo("Asia/Kolkata")


def today() -> date:
    return datetime.now(TRADER_ZONE).date()


def day_age(day: str, on: date) -> int:
    """Calendar days from the trading day to ``on``: 0 on the day itself."""
    return (on - date.fromisoformat(day)).days


def new_days(days, on: date) -> set[str]:
    """The days, of those given, that are new on ``on``."""
    return {d for d in days if 0 <= day_age(d, on) <= k.NEW_DAY_WITHIN_DAYS}
