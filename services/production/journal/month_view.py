"""A month of Journals as a calendar (TICKET-906).

A list of every day is a list nobody reads; a month grid is a thing a trader recognises.
This only lays the month out. Which Journal sits on a date, and how it is offered, is the
route's and days_worth_a_look's business.

Weeks start on Monday, as the ISO week does in definitions_v1 section 3. Previous and next
go to the nearest month that has a Journal, so a gap in his history is never walked
through month by empty month.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass

from markupsafe import Markup

_MONTH = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
# Written out rather than read from the locale: the page is English whatever the server's.
_NAMES = ("January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December")


def title(key: str) -> str:
    """ "YYYY-02" -> "February YYYY": the month key to the name the page shows."""
    year, number = key.split("-")
    return f"{_NAMES[int(number) - 1]} {int(year)}"


@dataclass(frozen=True)
class Month:
    key: str                       # "YYYY-MM"
    title: str                     # "<Month> <year>"
    weeks: list[list[str | None]]  # Monday first; None is a date outside the month
    prev: str | None               # the nearest earlier month with a Journal
    next: str | None               # the nearest later month with a Journal

    def number(self, day: str) -> Markup:
        """The day of the month, as the label on its cell. Markup because it names a place on the
        grid; it is not a figure the report states. Worked out here so no template computes."""
        return Markup(str(int(day[8:10])))


def month(days: list[str], wanted: str | None) -> Month | None:
    """The month asked for, or the newest month with a Journal; None when there is none.

    ``days`` are the dates that have a Journal. A ``wanted`` that is not a month
    (a month past twelve) raises ValueError, which the route answers as not found.
    """
    months = sorted({d[:7] for d in days})
    if wanted is None:
        if not months:
            return None
        wanted = months[-1]
    found = _MONTH.match(wanted)
    if found is None:
        raise ValueError(f"not a month: {wanted!r}")
    year, number = int(found.group(1)), int(found.group(2))
    weeks = [
        [None if d == 0 else f"{year:04d}-{number:02d}-{d:02d}" for d in week]
        for week in calendar.Calendar(firstweekday=calendar.MONDAY).monthdayscalendar(year, number)
    ]
    return Month(
        key=wanted,
        title=f"{_NAMES[number - 1]} {year}",
        weeks=weeks,
        prev=max((m for m in months if m < wanted), default=None),
        next=min((m for m in months if m > wanted), default=None),
    )
