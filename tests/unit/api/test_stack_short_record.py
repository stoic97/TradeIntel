"""TICKET-995, the stack fix (the founder's note of 25 Nov): every sentence on the dial is true
for a short record, and the wins wedge reads its rate beside the rate it needs.

Worked by hand, one ten-minute trade a day (tests.helpers.scope_chapters.trips_from):

* one day, −300: the worst days are every day he has. "5 days" and "1 days" are untrue, so
  the wedge says "Your only trading day" and −₹300.
* three days, −300, −200, +100: all three are the worst days, together −₹400. The wedge says
  "Your 3 trading days" and −₹400.
* the money card on three same-day trades: the best five and the worst five are the same
  three trades, −300 −200 +100 = −₹400, said once: "Your 3 same-day trades came to −₹400".
  One trade: "Your only same-day trade came to −₹300".
* six days, −300, −200, +100, +50, −20, +10: the five worst are −300, −200, −20, +10, +50 =
  −₹460, and the one other day is +₹100. Five or more days read as before, with the other day
  said in the singular ("the other day +₹100", never "the other 1 days").
* wins: 12 winners of +299 and 18 losers of −200 is 12 of 30 = 40.0 of 100. Breaking even
  needs 200 / (299 + 200) = 40.08…, which also prints as 40, so both get one decimal (out of a
  hundred, beside): "40.0 of 100", break-even 40.1. 40.0 is under 40.08, so the wedge is
  marked. With winners of +301 it needs 200 / 501 = 39.92… (39.9), 40.0 is above it, and the
  wedge is not marked.
"""
from __future__ import annotations

import re

from services.production.api import scope_facts as SF
from tests.helpers.scope_chapters import IMP, chapter_page, trips_from

ONE_DAY = [-300]
THREE_DAYS = [-300, -200, 100]
SIX_DAYS = [-300, -200, 100, 50, -20, 10]
UNDER = [299] * 12 + [-200] * 18
OVER = [301] * 12 + [-200] * 18


def text(html: str) -> str:
    """The page as a reader sees it: tags gone, spaces and line breaks single."""
    return " ".join(re.sub(r"<[^>]+>", " ", html).replace("\xa0", " ").split())


def worst_wedge(nets) -> dict:
    view = SF.chapter_view(1, SF.facts(SF.record_context(trips_from(nets)), IMP))
    items = {i["name"]: i for i in (view.get("desktop_items") or view["items"])}
    return items["Your worst trading days"]


def wins_wedge(nets) -> dict:
    view = SF.chapter_view(2, SF.facts(SF.record_context(trips_from(nets)), IMP))
    items = {i["name"]: i for i in (view.get("desktop_items") or view["items"])}
    return items["Your wins and losses"]


def test_one_day_is_your_only_trading_day():
    page = text(chapter_page(1, trips_from(ONE_DAY)))
    assert "Your only trading day" in page
    assert "−₹300" in page
    wedge = worst_wedge(ONE_DAY)
    assert " ".join(wedge["label"].split()) == "Your only trading day"
    assert wedge["figure"] == "−₹300"
    assert "1 days" not in page
    assert "the other 0" not in page
    assert "Those 1 day" not in page
    assert "That day came to −₹300" in page
    assert "1 of your 1 trading days" not in page  # every day he has: a share of all of them says nothing


def test_three_days_are_your_three_trading_days():
    page = text(chapter_page(1, trips_from(THREE_DAYS)))
    assert "Your 3 trading days" in page
    assert "−₹400" in page
    assert " ".join(worst_wedge(THREE_DAYS)["label"].split()) == "Your 3 trading days"
    assert worst_wedge(THREE_DAYS)["figure"] == "−₹400"
    assert "3 of your 3 trading days" not in page


def test_fewer_than_five_trades_are_never_called_five():
    """Three same-day trades: the best five and the worst five are the same three trades, so the
    money card says what they came to, once, and never "five"."""
    page = text(chapter_page(1, trips_from(THREE_DAYS)))
    assert "best five trades" not in page
    assert "worst five trades" not in page
    assert "Your 3 same-day trades came to −₹400" in page
    one = text(chapter_page(1, trips_from(ONE_DAY)))
    assert "Your only same-day trade came to −₹300" in one
    assert "five trades" not in one


def test_six_days_read_as_before_with_one_other_day_singular():
    page = text(chapter_page(1, trips_from(SIX_DAYS)))
    assert "came to −₹460" in page
    assert "the other day +₹100" in page
    assert "the other 1 days" not in page
    assert "other 1 days" not in page.lower()
    assert "trading days" not in " ".join(worst_wedge(SIX_DAYS)["label"].split())


def test_the_wins_wedge_reads_beside_what_it_needs():
    page = text(chapter_page(2, trips_from(UNDER)))
    assert "40.0 of 100" in page
    assert "break-even 40.1" in page
    assert wins_wedge(UNDER)["figure"] == "40.0 of 100"


def test_a_rate_under_what_it_needs_by_a_fraction_is_marked():
    assert SF.worse("math", SF.record_context(trips_from(UNDER)),
                    SF.facts(SF.record_context(trips_from(UNDER)), IMP)["math"])
    assert not SF.worse("math", SF.record_context(trips_from(OVER)),
                        SF.facts(SF.record_context(trips_from(OVER)), IMP)["math"])
