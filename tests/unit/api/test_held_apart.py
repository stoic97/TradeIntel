"""TICKET-1026: held positions shown apart from trading.

The ruling (founder's delegation, 23 Nov 2026): a position is held when it closed on a later day
than it opened, the same-day rule the chapters already use. Trading figures are the same-day
trades; held positions are said on their own line and never mixed into a trading figure.

Every trade here is made up, and the expected values are worked by hand in the comments.
"""
from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from services.production.api import how_you_got_here as how
from services.production.api import numbers as N
from services.production.journal import sections
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s

IST = ZoneInfo("Asia/Kolkata")
D = Decimal


def trip(tid: str, opened: str, closed: str, net: str, option: bool = True) -> mx.Trip:
    entry = datetime.fromisoformat(opened).replace(tzinfo=IST)
    leave = datetime.fromisoformat(closed).replace(tzinfo=IST)
    symbol, seg = ("NIFTY", "OPT") if option else ("WIDGETETF", "EQ")
    return mx.Trip(trip_id=tid, symbol=symbol, trading_day=entry.date().isoformat(), entry_ts=entry,
                   exit_ts=leave, holding_seconds=int((leave - entry).total_seconds()), net=D(net), lots=1,
                   risk_unit_source=s.RiskUnitSourceV1.PREMIUM_PAID, is_option=option,
                   lines=(mx.TradeLine(symbol, seg, "Buy", 1, None, None, D(net)),))


# Same-day trades:
#   2 Mar  a1 +300  a2 -100            -> day +200, 2 trades
#   3 Mar  b1 -400  b2 +100            -> day -300, 2 trades
#   4 Mar  c1 +200                     -> day +200, 1 trade
# Held past the day:
#   o1, an option opened 2 Mar 15:00, closed 3 Mar 10:00, -250
#   e1, an ETF opened 5 Jan, closed 4 Mar, +5,000
#
# Same-day only: winners 300, 100, 200 (3, average 200); losers 100, 400 (2, average 250).
#   Win rate 3 of 5 = 60 of 100. Break-even 250 / (200 + 250) = 55.6, "56 of 100".
# With the held positions mixed in, the ETF lifts the average winner to 1,400 and break-even
#   falls to 250 / (1,400 + 250) = 15.2: the trading would look close to break-even. It isn't.
# Best day 2 Mar +200 (ties: the earlier day), worst day 3 Mar -300.
# Months: March +100, so 1 of 1. Trades a day: 5 over 3 days = 1.7, most 2 on 2 Mar.
# Held past the day: 2 positions, -250 + 5,000 = +4,750.
# Every closed trade: +100 + 4,750 = +4,850.
RECORD = [
    trip("a1", "2026-03-02T09:30", "2026-03-02T09:50", "300"),
    trip("a2", "2026-03-02T11:00", "2026-03-02T11:20", "-100"),
    trip("o1", "2026-03-02T15:00", "2026-03-03T10:00", "-250"),
    trip("b1", "2026-03-03T09:30", "2026-03-03T09:50", "-400"),
    trip("b2", "2026-03-03T11:00", "2026-03-03T11:20", "100"),
    trip("c1", "2026-03-04T09:30", "2026-03-04T09:50", "200"),
    trip("e1", "2026-01-05T10:00", "2026-03-04T14:00", "5000", option=False),
]


def tiles():
    return N.build(RECORD, {}, gross=True)


# ---------- Your numbers: the tiles read same-day trades ----------

def test_average_winner_and_loser_are_same_day_trades():
    t = tiles()["tiles"]
    assert (t["winner"]["value"], t["winner"]["count"]) == (D(200), 3)
    assert (t["loser"]["value"], t["loser"]["count"]) == (D(-250), 2)


def test_best_and_worst_day_are_same_day_trades():
    t = tiles()["tiles"]
    assert (t["best_day"]["day"], t["best_day"]["value"]) == ("2026-03-02", D(200))
    assert (t["worst_day"]["day"], t["worst_day"]["value"]) == ("2026-03-03", D(-300))


def test_months_and_trades_a_day_are_same_day_trades():
    t = tiles()["tiles"]
    assert (t["months"]["made"], t["months"]["of"]) == (1, 1)
    assert t["per_day"]["value"] == D("1.7") and t["per_day"]["most"] == 2


def test_the_held_positions_have_their_own_line():
    v = tiles()
    assert "held" in v, "no held line on Your numbers"
    assert (v["held"]["count"], v["held"]["net"]) == (2, D(4750))
    assert v["trades"] == 7  # the top line still counts every closed trade


# ---------- Home's card: made money and needed read same-day trades ----------

def card():
    return how.build(RECORD, SimpleNamespace(fees_available=False, export_date=None))


def test_home_made_money_and_needed_are_same_day():
    c = card()
    assert c["strike"] == D(60)
    assert round(c["even"]) == 56  # not the 15 a held winner would make it


def test_home_result_says_what_is_held_in_it():
    c = card()
    assert c["total"] == D(4850)
    assert "held" in c, "no held line on Home's card"
    assert (c["held"]["count"], c["held"]["net"]) == (2, D(4750))


# ---------- One normal day ----------

def test_the_journals_normal_day_is_same_day_trades_as_chapter_three():
    facts = sections.history_facts(RECORD)
    same = mx.day_counts(mx.same_day_trips(RECORD)).normal_day
    assert D(facts["against_your_normal"]["your_normal_day"]) == same == D(2)


# ---------- The wording names it ----------

def test_the_pages_name_same_day_trades_and_the_held_line():
    from pathlib import Path
    numbers = Path("services/production/api/templates/numbers.html").read_text(encoding="utf-8")
    card_t = Path("services/production/api/templates/_how_you_got_here.html").read_text(encoding="utf-8")
    assert "Held past the day" in numbers and "Held past the day" in card_t
    assert re.search(r"same-day trades", numbers) and re.search(r"same-day trades", card_t)
