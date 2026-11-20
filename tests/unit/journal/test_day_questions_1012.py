"""TICKET-1012: new day questions about the day's pace, size steps, switching sides, the open
and the last hour. Order and timing only, as every 915 question is (Pawan, 17 Nov 2026): no
money, no tally, nothing about how the day ended. A threshold is his own median or the
instrument's session, never ours. Every day here is made up; every expected sentence is worked
by hand from the times written below.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

from services.production.journal import day_questions as dq
from services.production.journal import day_timing as dt

IST = timezone(timedelta(hours=5, minutes=30))


def at(hm: str) -> datetime:
    h, m = (int(x) for x in hm.split(":"))
    return datetime(2026, 3, 2, h, m, tzinfo=IST)


def hm(s: str) -> time:
    h, m = (int(x) for x in s.split(":"))
    return time(h, m)


def trade(entry: str, exit_: str, *, side="calls", lots=1, net="10", opens="09:15", closes="15:30",
          evening=False) -> dict:
    """A trade the way the Journal hands it to the questions, with its timing added."""
    return {"trip_id": f"{entry}-{exit_}", "net": Decimal(net), "lots": lots, "entry": at(entry),
            "exit": at(exit_), "side": side, "opens": hm(opens), "closes": hm(closes), "evening": evening}


def texts(trades, **context) -> list[str]:
    return [q.text for q in dq.questions_for(trades, context=context or None)]


# ---------- each new sentence ----------

def test_the_pace_after_the_open():
    day = [trade("09:16", "09:18"), trade("09:22", "09:25"), trade("09:30", "09:33")]
    assert "You took 3 trades in the 15 minutes after 09:15." in texts(day)


def test_one_trade_in_the_first_half_hour_is_not_a_pace():
    day = [trade("09:16", "09:18"), trade("11:00", "11:10")]
    assert not [t for t in texts(day) if t.startswith("You took ")]


def test_straight_back_in_is_asked_only_below_his_own_median_gap():
    day = [trade("10:00", "10:10"), trade("10:12", "10:20"), trade("11:00", "11:05")]
    said = "Your next trade came 2 minutes after you closed the one before."
    assert said in texts(day, median_gap=6)
    assert said not in texts(day, median_gap=2)  # not below his median: not asked
    assert said not in texts(day)  # no median of his: no threshold, no question


def test_straight_back_in_within_the_same_minute():
    day = [trade("10:00", "10:10"), trade("10:10", "10:20")]
    assert "Your next trade came within a minute of you closing the one before." not in texts(day, median_gap=5)
    day = [trade("10:00", "10:10"), trade("10:11", "10:20")]
    assert "Your next trade came 1 minute after you closed the one before." in texts(day, median_gap=5)


def test_a_trade_opened_before_the_last_one_closed_is_not_a_next_trade():
    day = [trade("10:00", "10:30"), trade("10:05", "10:20"), trade("10:50", "11:00")]
    # 10:05 opened while 10:00 was still open; the next after 10:30 is 10:50, 20 minutes on
    assert "Your next trade came 20 minutes after you closed the one before." in texts(day, median_gap=25)


def test_switching_between_calls_and_puts():
    day = [trade("11:00", "11:05", side="calls"), trade("11:10", "11:15", side="puts"),
           trade("11:20", "11:25", side="calls"), trade("11:30", "11:35", side="puts")]
    assert "You switched between calls and puts 3 times today." in texts(day)


def test_switching_between_long_and_short_on_futures():
    day = [trade("11:00", "11:05", side="long"), trade("11:10", "11:15", side="short")]
    assert "You switched between long and short 1 time today." in texts(day)


def test_the_last_hour_of_the_session():
    day = [trade("11:00", "11:05"), trade("14:35", "14:40"), trade("14:50", "15:00")]
    assert "You opened 2 trades in the last hour of the session." in texts(day)
    crude = [trade("11:00", "11:05", opens="09:00", closes="23:30"),
             trade("22:45", "22:50", opens="09:00", closes="23:30", evening=True)]
    assert "You opened 1 trade in the last hour of the session." in texts(crude)


def test_the_first_trade_after_the_open_is_asked_only_before_his_own_median():
    day = [trade("09:17", "09:20"), trade("11:00", "11:05")]
    assert "Your first trade came 2 minutes after the open." in texts(day, median_first=10)
    assert "Your first trade came 2 minutes after the open." not in texts(day, median_first=2)
    late = [trade("10:30", "10:35"), trade("11:00", "11:05")]
    assert "Your first trade came 1 hour 15 minutes after the open." in texts(late, median_first=90)


def test_an_mcx_evening_session_is_not_the_open():
    day = [trade("17:05", "17:08", opens="09:00", closes="23:30", evening=True),
           trade("17:20", "17:25", opens="09:00", closes="23:30", evening=True)]
    said = texts(day, median_first=600)
    assert not [t for t in said if "after the open" in t or t.startswith("You took ")]


def test_size_steps_say_when():
    day = [trade("10:02", "10:05", lots=1), trade("10:41", "10:45", lots=4)]
    assert "Your size went from 1 lot to 4 lots between 10:02 and 10:41." in texts(day)


# ---------- the choice ----------

def test_915s_own_questions_come_first_and_a_day_asks_at_most_three():
    day = [trade("09:16", "09:20", side="calls", net="-10"), trade("09:21", "09:25", side="puts", net="-20"),
           trade("09:26", "09:30", side="calls", net="30", lots=3), trade("14:40", "14:45", side="puts")]
    qs = dq.questions_for(day, context={"median_gap": 30, "median_first": 30})
    assert qs[0].key == "first_then_more"
    assert len(qs) == dq.MAX_QUESTIONS and len({q.key for q in qs}) == len(qs)


def test_no_kind_is_asked_twice_in_a_day():
    day = [trade("09:16", "09:18"), trade("09:19", "09:22"), trade("09:23", "09:26"),
           trade("14:35", "14:40"), trade("14:50", "15:00")]
    qs = dq.questions_for(day, context={"median_gap": 30, "median_first": 30})
    assert len({q.key for q in qs}) == len(qs)


def test_a_day_without_timing_asks_exactly_what_915_asked():
    plain = [{"trip_id": "a", "net": Decimal("-10"), "lots": None}, {"trip_id": "b", "net": Decimal("10"), "lots": None}]
    assert [q.key for q in dq.questions_for(plain)] == [q.key for q in dq.questions_for(plain, context=None)]


# ---------- his own medians, from his record ----------

class _Line:
    def __init__(self, segment, side, option_type=None):
        self.segment, self.side, self.option_type = segment, side, option_type


class _Trip:
    def __init__(self, trip_id, day, entry, exit_, lines):
        self.trip_id, self.trading_day = trip_id, day
        self.entry_ts, self.exit_ts, self.lines = entry, exit_, lines


def test_his_median_gap_and_first_minutes_come_from_his_whole_record():
    def t(i, d, e, x):
        h, m = e
        entry = datetime(2026, 3, d, h, m, tzinfo=IST)
        h2, m2 = x
        return _Trip(f"t{i}", f"2026-03-{d:02d}", entry, datetime(2026, 3, d, h2, m2, tzinfo=IST),
                     (_Line("OPT", "Buy", "CE"),))
    record = [t(1, 2, (9, 20), (9, 30)), t(2, 2, (9, 34), (9, 40)),   # gap 4, first 5 minutes
              t(3, 3, (9, 45), (10, 0)), t(4, 3, (10, 10), (10, 20))]  # gap 10, first 30 minutes
    inst = {f"t{i}": ("NSE", "NIFTY", "OPT") for i in range(1, 5)}
    ctx = dt.medians(record, inst, sessions={("NSE", "NIFTY", "OPT"): (time(9, 15), time(15, 30))})
    assert ctx == {"median_gap": 7.0, "median_first": 17.5}


def test_the_side_of_a_trade_by_its_one_leg():
    assert dt.side_of(_Trip("a", "", None, None, (_Line("OPT", "Buy", "CE"),))) == "calls"
    assert dt.side_of(_Trip("a", "", None, None, (_Line("OPT", "Sell", "PE"),))) == "puts"
    assert dt.side_of(_Trip("a", "", None, None, (_Line("FUT", "Sell"),))) == "short"
    assert dt.side_of(_Trip("a", "", None, None, (_Line("OPT", "Buy", "CE"), _Line("OPT", "Sell", "CE")))) is None
