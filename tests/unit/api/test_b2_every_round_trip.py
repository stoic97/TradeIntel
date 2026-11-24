"""TICKET-1025, option (a): after two straight losses counts every round trip, as definitions_v1 §2 says.

Prepared for the research seat's choice between (a) every round trip and (b) same-day trades
only; this branch is (a). Eligibility already counts every round trip (main since the 24 Nov
revert); here chapter 3, the finding bar and the Journal count the same trades, so the three
pages say one figure and the finding bar tests the trades the research B2 test was measured on.

Every trade is made up; the expected figures are worked by hand below.

  02 Mar  a1 NIFTY 09:30-09:50 +1000    a2 NIFTY 10:00-10:20 -1500    a3 CRUDE 18:00-18:20 -300
          a4 NIFTY 18:30 -> 03 Mar 10:00 +400   opened after a2 and a3, both closed losses
          a5 CRUDE 19:00-19:20 -100             opened after a2 and a3 (a4 still open, not resolved)
  03 Mar  b1 NIFTY 09:30-09:40 +200     b2 CRUDE 18:00-18:10 +50
  04 Mar  c1 CRUDE 20:00 -> 05 Mar 18:30 -50
  06 Mar  d1 NIFTY 09:30-09:40 -100     d2 NIFTY 09:45-09:50 -100
          d3 NIFTY 10:00 -> 09 Mar 10:00 +300   opened after d1 and d2, both closed losses

Every round trip: the condition is a4, a5 and d3 = 3 trades, on 02 and 06 Mar = 2 days.
Same-day trades only it would be a5 alone, on 1 day (a4 and d3 are held overnight).
The days he closed a same-day trade: 02, 03 and 06 Mar = 3. Every day the condition happens on
is one of them, because the two losses before it closed that same day.
"""
from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from services.production.api import scope_facts as SF
from services.production.eligibility import assess as E
from services.production.journal import sections as sec
from services.production.journal.periods import Period
from services.production.mirror import metrics as mx
from services.shared.conditions import b2_shuffle
from services.shared.schemas import scope_v1 as s
from tests.helpers.scope_chapters import IMP, chapter_page

IST = ZoneInfo("Asia/Kolkata")
D = Decimal


def trip(tid, opened, closed, net, lots=1, book="NIFTY"):
    entry = datetime.fromisoformat(opened).replace(tzinfo=IST)
    leave = datetime.fromisoformat(closed).replace(tzinfo=IST)
    line = mx.TradeLine(book, "OPT", "Buy", lots, None, None, D(str(net)), strike=D("100"),
                        option_type="CE", entry_ts=entry)
    return mx.Trip(trip_id=tid, symbol=book, trading_day=entry.date().isoformat(), entry_ts=entry,
                   exit_ts=leave, holding_seconds=int((leave - entry).total_seconds()), net=D(str(net)),
                   lots=lots, risk_unit_source=s.RiskUnitSourceV1.PREMIUM_PAID, is_option=True,
                   lines=(line,))


RECORD = [
    trip("a1", "2026-03-02T09:30", "2026-03-02T09:50", 1000),
    trip("a2", "2026-03-02T10:00", "2026-03-02T10:20", -1500),
    trip("a3", "2026-03-02T18:00", "2026-03-02T18:20", -300, lots=2, book="CRUDEOIL"),
    trip("a4", "2026-03-02T18:30", "2026-03-03T10:00", 400, lots=3),
    trip("a5", "2026-03-02T19:00", "2026-03-02T19:20", -100, book="CRUDEOIL"),
    trip("b1", "2026-03-03T09:30", "2026-03-03T09:40", 200),
    trip("b2", "2026-03-03T18:00", "2026-03-03T18:10", 50, book="CRUDEOIL"),
    trip("c1", "2026-03-04T20:00", "2026-03-05T18:30", -50, book="CRUDEOIL"),
    trip("d1", "2026-03-06T09:30", "2026-03-06T09:40", -100),
    trip("d2", "2026-03-06T09:45", "2026-03-06T09:50", -100),
    trip("d3", "2026-03-06T10:00", "2026-03-09T10:00", 300),
]


def _page_text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def test_chapter_3_counts_every_round_trip_after_two_losses():
    tl = SF.record_context(RECORD)["two_losses"]
    assert sorted(tl.condition_trip_ids) == ["a4", "a5", "d3"]
    assert tl.condition == 3


def test_eligibility_and_chapter_3_say_one_figure():
    b2 = next(v for v in E.assess(RECORD).verdicts if v.test.id == "B2")
    assert b2.have == SF.record_context(RECORD)["two_losses"].condition == 3


def test_the_journal_counts_the_same_days_as_chapter_3():
    ctx = SF.record_context(RECORD)
    period = Period(s.JournalUnit.DAY, "2026-03-02", "2026-03-02",
                    tuple(t for t in RECORD if t.trading_day == "2026-03-02"), True)
    after = sec.build(period, history=RECORD, fees_available=False,
                      trips_with_a_stop=set())["after_two_straight_losses"]
    assert after["days_it_happened"] == ctx["days_with_the_condition"] == 2
    assert after["your_trading_days"] == ctx["same_day_days"] == 3


def test_chapter_3_page_says_two_of_three_days():
    text = _page_text(chapter_page(3, RECORD))
    assert "This happened on 2 of the 3 days you closed a same-day trade" in text


def test_the_finding_bar_tests_every_round_trip():
    figs = SF.facts(SF.record_context(RECORD), IMP)
    needs = figs["down"]["post_loss_needs"]
    assert needs["condition"] == b2_shuffle.MIN_CONDITION - 3
