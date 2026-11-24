"""TICKET-1025: a figure that appears on two pages is one figure, read from one function.

On a real record, the same label read differently on different pages: two biggest drops, two
"usual" sizes on one Journal page, three trading-day counts, the trades after two straight
losses off by one between chapter 3 and Eligibility, headlines that weren't the figure their
first sentence explains, and month rows that didn't add up to their own total. Every trade here
is made up, and the expected figures are worked by hand in the comments.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy import text as sql

from services.production.api import formatting
from services.production.api import how_you_got_here as how
from services.production.api import numbers as N
from services.production.api import scope_facts as SF
from services.production.api.app import create_app
from services.production.db import models as m
from services.production.db.session import make_engine, make_session, run_migrations
from services.production.eligibility import assess as E
from services.production.journal import prose
from services.production.journal import sections as sec
from services.production.journal.periods import Period
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s
from tests.helpers.scope_chapters import IMP, chapter_page
from tests.helpers.upload import CSRF, sign_up

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


# Two books with different sizes, an overnight position and a day of only an overnight trade.
#  02 Mar  a1 NIFTY  09:30-09:50 +1000   a2 NIFTY 10:00-10:20 -1500   a3 CRUDE(2 lots) 18:00-18:20 -300
#          a4 NIFTY(3 lots) 18:30 -> 03 Mar 10:00 +400 (held overnight; opened after two closed losses)
#          a5 CRUDE 19:00-19:20 -100 (opened after a2 and a3, both closed losses: same-day B2)
#  03 Mar  b1 NIFTY 09:30-09:40 +200     b2 CRUDE 18:00-18:10 +50
#  04 Mar  c1 CRUDE 20:00 -> 05 Mar 18:30 -50 (the day's only trade is held overnight)
#  06 Mar  d1 NIFTY 09:30-09:40 -100     d2 NIFTY 09:45-09:50 -100
#          d3 NIFTY 10:00 -> 09 Mar 10:00 +300 (after two closed losses, but held overnight)
#
# Running result, every trade in exit order: 1000, -500, -800, -900 (a5), -700 (b1), -300 (a4),
#   -250, -300 (c1), -400, -500, -200 (d3). High 1000 on 02 Mar, lowest after it -900 on 02 Mar:
#   the biggest drop is 1,900, from 02 Mar to 02 Mar. Day by day it would be 500 (02 Mar's -500).
# Trading days (any trade opened): 02, 03, 04, 06 Mar = 4; with a same-day trade: 02, 03, 06 = 3.
# B2, same-day trades only (what the finding bar tests): a5 alone, on 1 day.
#   On every trade it would be a4, a5 and d3, on 2 days: the off-by-one this ticket closes.
# Options' lots: 1,1,2,3,1,1,1,1,1,1,1 = 14 over 11 trades = 1.27...; written "1.3".
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


def day(iso: str) -> Period:
    return Period(s.JournalUnit.DAY, iso, iso, tuple(t for t in RECORD if t.trading_day == iso), True)


# ---------- 1. one biggest drop ----------

def test_the_deepest_fall_is_the_running_results_biggest_drop():
    drop = mx.running_result(RECORD).drop
    fall = mx.deepest_fall(RECORD)
    assert (drop.value, drop.from_day, drop.to_day) == (D(1900), "2026-03-02", "2026-03-02")
    assert (fall.amount, fall.from_day, fall.to_day) == (D(1900), "2026-03-02", "2026-03-02")


def test_no_drop_is_no_fall():
    rising = [trip("u1", "2026-03-02T09:30", "2026-03-02T09:40", 100),
              trip("u2", "2026-03-03T09:30", "2026-03-03T09:40", 50)]
    assert mx.running_result(rising).drop.value == 0
    assert mx.deepest_fall(rising) is None


# ---------- 2. one usual size ----------

def test_the_journal_reads_its_history_facts_live():
    stale = sec.build(day("2026-03-02"), history=RECORD[:2], fees_available=False, trips_with_a_stop=set())
    stale["against_your_normal"]["lots_usually"] = "9.2"  # what an old version stored
    assert hasattr(sec, "with_history"), "no sections.with_history"
    live = sec.with_history(stale, RECORD)
    assert D(live["against_your_normal"]["lots_usually"]) == mx.average_lots(RECORD).mean
    assert "9.2" not in prose.render(live)


# ---------- 3, 4. trading days and the count after two straight losses ----------

@pytest.mark.skip(reason="superseded by option (a), every round trip (definitions_v1 section 2): test_b2_every_round_trip.py; this pinned option (b), same-day trades only")
def test_the_journal_counts_the_days_as_chapter_3_does():
    ctx = SF.record_context(RECORD)
    facts = sec.build(day("2026-03-02"), history=RECORD, fees_available=False, trips_with_a_stop=set())
    after = facts["after_two_straight_losses"]
    assert after["days_it_happened"] == ctx["days_with_the_condition"] == 1
    assert after["your_trading_days"] == ctx["same_day_days"] == 3  # 02, 03, 06 Mar


@pytest.mark.skip(reason="superseded by option (a), every round trip (definitions_v1 section 2): test_b2_every_round_trip.py; this pinned option (b), same-day trades only")
def test_chapter_3_names_the_days_it_counts():
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", chapter_page(3, RECORD)))
    assert "This happened on 1 of the 3 days you closed a same-day trade" in text


@pytest.mark.skip(reason="pending research seat: B2's population on Eligibility is ruled by the research "
                         "seat (definitions_v1.md section 2 counts every round trip); review of 24 Nov")
def test_eligibility_counts_b2_on_the_trades_the_finding_bar_tests():
    b2 = next(v for v in E.assess(RECORD).verdicts if v.test.id == "B2")
    assert b2.have == SF.record_context(RECORD)["two_losses"].condition == 1


# ---------- 5. a headline is the figure its first sentence explains ----------

def test_where_the_money_came_froms_card_opens_with_the_figure_it_leads_with():
    """The figure is what he closed the same day (818, 882): the card's first line says so.
    Same-day trades: +1000 -1500 -300 -100 +200 +50 -100 -100 = -850."""
    figs = SF.facts(SF.record_context(RECORD), IMP)
    assert figs["money"]["figure"] == formatting.rupees(D(-850))
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", chapter_page(1, RECORD)))
    card = text[text.index("Where the money came from"):]
    assert card.index("Everything you closed the same day: −₹850.") < card.index("Your best five")


@pytest.mark.skip(reason="superseded by option (a), every round trip (definitions_v1 section 2): test_b2_every_round_trip.py; this pinned option (b), same-day trades only")
def test_after_two_straight_losses_leads_with_the_trades_after_two_losses():
    figs = SF.facts(SF.record_context(RECORD), IMP)
    assert figs["down"]["figure"] == "1 trade"  # a5, not the whole population after two closes


# ---------- 6. the best/worst five count says what it holds ----------



# ---------- 7. totals add up as printed ----------

def test_month_rows_add_up_to_their_own_ended_at():
    paise = [trip("p1", "2026-01-10T10:00", "2026-01-10T10:10", "0.6"),
             trip("p2", "2026-02-10T10:00", "2026-02-10T10:10", "0.6")]
    view = how.build(paise, SimpleNamespace(fees_available=False, export_date=None), None, "m")
    assert all("net_shown" in r for r in view["rows"]), "rows carry no net_shown"
    shown = [int(r["net_shown"]) for r in view["rows"]]
    assert sum(shown) == int(view["rows"][0]["candle"].close)  # 0 + 1 == 1, not 0 + 0


def test_the_day_table_says_it_covers_the_months_shown():
    long = [trip(f"l{k}", f"{2025 + k // 12}-{k % 12 + 1:02d}-10T10:00",
                 f"{2025 + k // 12}-{k % 12 + 1:02d}-10T10:10", 100) for k in range(14)]
    assert "months shown" in str(N.calendar(long)["table"])
    assert "months shown" not in str(N.calendar(long, show_all=True)["table"])


# ---------- 2, through the app: one usual on one Journal page ----------

@pytest.fixture()
def client():
    engine = make_engine(os.environ["SCOPE_DB"])
    run_migrations(engine)
    c = sign_up(TestClient(create_app()), engine, "F-1", "figuresreader")
    c.post("/upload/demo", data={"csrf_token": CSRF.search(c.get("/upload").text).group(1)},
           follow_redirects=False)
    c.engine = engine
    return c


def test_a_journal_page_states_one_usual_size(client):
    # An old version's stored "usual", far from the live one. Journals are insert-only, so the
    # test writes the stored facts the way an earlier version would have left them.
    with make_session(client.engine) as sess:
        journals = sess.execute(select(m.Journal.id, m.Journal.sections)
                                .where(m.Journal.period_start == m.Journal.period_end)).all()
        for jid, stored in journals:
            facts = json.loads(stored)
            facts["against_your_normal"]["lots_usually"] = "9.2"
            sess.execute(sql("UPDATE journal SET sections = :s WHERE id = :i"),
                         {"s": json.dumps(facts, sort_keys=True), "i": jid})
        sess.commit()
        ids = [jid for jid, _ in journals]
    usuals = set()
    for jid in ids:
        page = re.sub(r"<[^>]+>", " ", client.get(f"/journals/{jid}").text)
        usuals |= set(re.findall(r"against your usual (\d+(?:\.\d+)?)", page))
        usuals |= set(re.findall(r"Your usual is about (\d+(?:\.\d+)?) lots", page))
    assert usuals and "9.2" not in usuals and len(usuals) == 1


def test_the_best_and_worst_five_count_names_the_held_positions(client):
    page = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", client.get("/mirror/fact/money").text))
    caption = re.search(r"Your best five and worst five[^.]*\.[^.]*\.", page).group(0)
    # The demo has ten ranked same-day trades and two positions held past the day.
    assert "held past the day" in caption and "2 positions" in caption


# ---------- 8. the guard: one label, one function, on any record ----------

def _random_record(seed: int) -> list[mx.Trip]:
    import random
    rnd = random.Random(seed)
    out, n = [], 0
    for d in range(rnd.randint(3, 9)):
        day = f"2026-04-{d + 1:02d}"
        minute = 0
        for _ in range(rnd.randint(1, 7)):
            minute += rnd.randint(1, 50)
            held = rnd.random() < 0.15
            opened = f"{day}T{9 + minute // 60:02d}:{minute % 60:02d}"
            closed = (f"2026-04-{d + 2:02d}T10:00" if held
                      else f"{day}T{9 + (minute + 9) // 60:02d}:{(minute + 9) % 60:02d}")
            out.append(trip(f"r{seed}-{n}", opened, closed, rnd.choice([-700, -300, -80, 0, 90, 250, 900]),
                            lots=rnd.randint(1, 4), book=rnd.choice(["NIFTY", "CRUDEOIL"])))
            n += 1
            minute += 10
    return out


@pytest.mark.parametrize("seed", range(25))
def test_every_paired_figure_reads_one_function(seed):
    record = _random_record(seed)
    drop, fall = mx.running_result(record).drop, mx.deepest_fall(record)
    assert (fall is None) == (drop.value == 0)
    if fall is not None:
        assert (fall.amount, fall.from_day, fall.to_day) == (drop.value, drop.from_day, drop.to_day)
    ctx = SF.record_context(record)
    days = sorted({t.trading_day for t in record})
    facts = sec.build(Period(s.JournalUnit.DAY, days[0], days[0],
                             tuple(t for t in record if t.trading_day == days[0]), True),
                      history=record, fees_available=False, trips_with_a_stop=set())
    after = facts["after_two_straight_losses"]
    assert after["days_it_happened"] == ctx["days_with_the_condition"]
    assert after["your_trading_days"] == ctx["same_day_days"]
    # Eligibility's B2 count is not paired here: its population waits on the research seat.
    assert D(facts["against_your_normal"]["lots_usually"]) == (mx.average_lots(record).mean or 0)
