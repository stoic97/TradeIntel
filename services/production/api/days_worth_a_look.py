"""The days the report has already named, and what it said about each.

No new judgement here. A day is on this list because the report's own lists have it: the
longest losing run, the busiest day, the five worst days. Each flag links the fact it came
from, so the trader can check it and the Journal can't disagree with the report.
"""

from __future__ import annotations

from dataclasses import dataclass

from services.production.api import scope_map as S
from services.production.journal import constants as k
from services.production.mirror import metrics as mx

SHORTEST_RUN = 2
"""One loss is not a run."""


@dataclass(frozen=True)
class Flag:
    label: str
    href: str


def flags_by_day(trips: list[mx.Trip]) -> dict[str, list[Flag]]:
    """What the report says about each day it names, most worth starting with first.

    The run comes first, then the busiest day, then the worst days in order. Taking the worst
    days first would fill all five places and leave the other two out. A run across days is
    named on each, but only the day it began leads.
    """
    flags: dict[str, list[Flag]] = {}
    if not trips:
        return flags

    def name(day: str, label: str, key: str) -> None:
        flags.setdefault(day, []).append(Flag(label, S.fact_href(key, lens=False)))

    run = mx.longest_losing_run(trips)
    named_run = run.length >= SHORTEST_RUN
    run_label = (f"{'Part of your' if run.crosses_days else 'Your'} longest losing run: "
                 f"{losses_in_a_row(run.length)}")
    if named_run:
        name(run.days[0], run_label, "run")

    days = mx.day_counts(trips)
    if days.busiest_trips > days.normal_day:
        name(days.busiest_day, f"Your busiest day: {days.busiest_trips} trades", "busiest")

    for worst in mx.five_worst_days(trips).days:
        if worst.net < 0:  # with five days or fewer, a winning day is in the five
            name(worst.trading_day, "This was one of your five worst days", "worst-days")

    if named_run:
        for day in run.days[1:]:
            name(day, run_label, "run")
    return flags


def losses_in_a_row(n: int) -> str:
    return f"{n} {'loss' if n == 1 else 'losses'} in a row"


def to_start_with(journals: list, flags: dict[str, list[Flag]]) -> list:
    """The Journals to start with, in the order the flags rank them, five at most.

    A Journal that covers more than a day (a week, ten trades) is left out: the flag is about
    a day, so saying it of a longer period would claim more than the report did.
    """
    by_day = {j.period_start: j for j in journals if j.period_start == j.period_end}
    named = [by_day[day] for day in flags if day in by_day]
    return named[:k.JOURNALS_ON_SURFACE]

WORTH, NEW, REMEMBER, PERIOD = "worth", "new", "remember", "period"
"""How a Journal is offered (TICKET-906)."""


def offer(journal, flags: dict[str, list[Flag]], new_days: set[str]) -> str:
    """How a Journal is offered, decided in one place.

    PERIOD: it covers more than a day (a week, ten trades). It is not a day, so it is not on
    a day cell and is never asked "Do you remember this day?" - it opens as before.
    WORTH: the report has named the day (flags_by_day: the longest losing run, the busiest
    day, the five worst days). NEW: the day is within NEW_DAY_WITHIN_DAYS of today
    (recency.new_days, from the caller). Both ask straight away. REMEMBER: any other day
    asks whether he remembers it first.

    Every reason is a property of the day's trades or its date, never a judgement about him.
    """
    if journal.period_start != journal.period_end:
        return PERIOD
    if flags.get(journal.period_start):
        return WORTH
    if journal.period_start in new_days:
        return NEW
    return REMEMBER
