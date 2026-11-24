"""TICKET-1030 review (24 Nov): the evening roll-up only for an MCX book, where 17:00 is the
exchange's own evening session; small files never read "Your other 0 days", "Your other 1 days"
or "1 more winners".

Every trade is made up and worked by hand beside its test.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from decimal import Decimal

from services.production.api import scope_facts as SF
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s
from tests.helpers.scope_chapters import IMP, chapter_page, readable, trips_from
from tests.helpers.scope_facts import fact_page
from tests.unit.api.templating import template_env

D = Decimal


def at(day: int, hhmm: str, net: int, tid: str, symbol: str = "WIDGETOIL") -> mx.Trip:
    entry = datetime.fromisoformat(f"2026-09-{day:02d}T{hhmm}:00+05:30")
    return mx.Trip(tid, symbol, entry.date().isoformat(), entry, entry + timedelta(minutes=10), 600,
                   D(net), 1, s.RiskUnitSourceV1.DECLARED_BUDGET)


# NIFTY options (an NSE book) with trades opened at 18:00 and 20:00: no evening session is NSE's,
# so no "from 17:00" line. WIDGETOIL (an MCX profile) keeps its line.
NSE_LATE = [at(1, "10:05", 60, "a", "NIFTY"), at(2, "18:05", -300, "b", "NIFTY"),
            at(3, "20:05", -200, "c", "NIFTY")]


def test_a_book_that_is_not_mcx_has_no_evening_line():
    book = SF.facts(SF.record_context(NSE_LATE), IMP)["clock"]["clocks"][0]
    assert book.get("evening", "missing") is None
    assert "trades opened from 17:00" not in readable(fact_page("clock", NSE_LATE))


def test_an_mcx_book_keeps_its_evening_line():
    mcx = [at(1, "10:05", 60, "a"), at(2, "18:05", -300, "b")]
    assert SF.facts(SF.record_context(mcx), IMP)["clock"]["clocks"][0]["evening"]


# 6 winners of 200 and 8 losers of 150: win 6/14 = 42.86 -> 43 of 100; break-even
# 150/350 = 42.86... -> 43: no gap. 7 winners of 200, 10 losers of 150: win 41.18 -> 41;
# break-even 42.86 -> 43: 2 more. 9 winners of 200 and 13 losers of 150: win 40.91 -> 41,
# break-even 43: 2. 10 of 200, 13 of 150: win 43.48 -> 43; 43: none. 9 of 200, 12 of 150:
# win 42.86 -> 43. 8 of 200 and 11 of 150: win 42.11 -> 42; 43 - 42 = 1 more winner.
ONE_MORE = trips_from([200] * 8 + [-150] * 11)


def test_one_more_winner_is_singular():
    figs = SF.facts(SF.record_context(ONE_MORE), IMP)
    assert figs["math"]["gap"]["more"] == 1
    page = readable(chapter_page(2, ONE_MORE))
    assert "1 more winner in every 100" in page and "1 more winners" not in page


def days(n: int) -> list[mx.Trip]:
    """n trading days, one losing trade a day of -100 more each day: the five worst are the last."""
    return [at(i + 1, "10:05", -100 * (i + 1), f"d{i}") for i in range(n)]


def hub_line(n: int) -> str:
    answer = SF._answer_one(SF.record_context(days(n)))
    html = template_env().get_template("scope/_hub_answer.html").render(c={"number": 1, "answer": answer})
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def test_a_file_of_exactly_five_days_does_not_lead_with_your_other_zero_days():
    assert not SF._answer_one(SF.record_context(days(5)))["five_vs_rest"]
    assert "Your other 0 days" not in hub_line(5)


def test_one_other_day_is_singular():
    line = hub_line(6)
    assert "Your other 1 day:" in line and "Your other 1 days" not in line
