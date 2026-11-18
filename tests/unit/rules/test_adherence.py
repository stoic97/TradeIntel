"""Kept or broken, trade by trade. Every trade here is made up and worked by hand."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from services.production.mirror import metrics as mx
from services.production.rules import adherence as A
from services.production.rules import chips

IST = ZoneInfo("Asia/Kolkata")
DAY = "2026-11-16"


def at(hh: int, mm: int = 0, day: str = DAY) -> datetime:
    y, mo, d = map(int, day.split("-"))
    return datetime(y, mo, d, hh, mm, tzinfo=IST)


def trip(i: int, opened: datetime, net: int, minutes: int = 5, lots: int = 1, day: str = DAY):
    return mx.Trip(trip_id=f"t{i}", symbol="NIFTY", trading_day=day, entry_ts=opened,
                   exit_ts=opened + timedelta(minutes=minutes), holding_seconds=minutes * 60,
                   net=Decimal(net), lots=lots, risk_unit_source=mx.s.RiskUnitSourceV1.PREMIUM_PAID)


def rule(factor: str, value: int, declared: datetime, rid: int = 1, frm: str = DAY,
         to: str | None = DAY) -> A.Rule:
    return A.Rule(rid, factor, value, declared, frm, to, chips.FACTORS[factor].words(value))


def kept(counts, rid=1) -> list[bool]:
    return [c.kept for c in next(c for c in counts if c.rule.id == rid).trades]


def test_most_trades_breaks_on_the_trade_past_the_limit():
    trips = [trip(i, at(10, 10 * i), -100) for i in range(4)]
    assert kept(A.count([rule("most_trades", 2, at(9))], trips)) == [True, True, False, False]


def test_losses_in_a_row_reads_only_trades_closed_before_the_entry():
    trips = [trip(0, at(10), -100), trip(1, at(10, 10), -100),
             trip(2, at(10, 12), 50, minutes=1),   # opened before trade 1 closed (10:15)
             trip(3, at(10, 30), 50)]              # after two closed losses... and a win
    # t2 opens at 10:12: only t0 has closed (10:05), one loss: kept.
    # t3 opens at 10:30: latest closes are t1 (10:15, loss) then t2 (10:13, win): run is 1: kept.
    assert kept(A.count([rule("losses_in_a_row", 2, at(9))], trips)) == [True, True, True, True]
    trips = [trip(0, at(10), -100), trip(1, at(10, 10), -100), trip(2, at(10, 30), 50)]
    assert kept(A.count([rule("losses_in_a_row", 2, at(9))], trips)) == [True, True, False]


def test_day_down_counts_the_closed_result_before_each_entry():
    trips = [trip(0, at(10), -700), trip(1, at(10, 10), -400), trip(2, at(10, 30), 100)]
    # limit 1,000: before t2 the day had closed -1,100: broken
    assert kept(A.count([rule("day_down", 1, at(9))], trips)) == [True, True, False]


def test_last_hour_and_most_lots():
    trips = [trip(0, at(14, 50), 10, lots=1), trip(1, at(15, 5), 10, lots=3)]
    assert kept(A.count([rule("last_hour", 15, at(9))], trips)) == [True, False]
    assert kept(A.count([rule("most_lots", 2, at(9), rid=2)], trips), rid=2) == [True, False]


def test_a_rule_never_reaches_back_before_it_was_set():
    trips = [trip(0, at(10), -100), trip(1, at(11), -100)]
    counts = A.count([rule("most_trades", 1, at(10, 30))], trips)
    assert [c.trip_id for c in counts[0].trades] == ["t1"]


def test_a_newer_rule_governs_only_the_trades_after_it_and_the_older_keeps_its_own():
    trips = [trip(0, at(10), -100), trip(1, at(11), -100), trip(2, at(12), -100)]
    older = rule("most_trades", 1, at(9), rid=1)
    newer = rule("most_trades", 3, at(10, 30), rid=2)
    counts = A.count([older, newer], trips)
    assert [c.trip_id for c in next(c for c in counts if c.rule.id == 1).trades] == ["t0"]
    assert [c.trip_id for c in next(c for c in counts if c.rule.id == 2).trades] == ["t1", "t2"]
    assert kept(counts, 2) == [True, True]


def test_a_rule_for_one_day_governs_that_day_only():
    trips = [trip(0, at(10), 10), trip(1, at(10, day="2026-11-17"), 10, day="2026-11-17")]
    counts = A.count([rule("most_trades", 1, at(9))], trips)
    assert [c.trip_id for c in counts[0].trades] == ["t0"]


def test_not_enough_trades_until_the_number_stated_at_the_start():
    trips = [trip(i, at(10) + timedelta(minutes=i), 10, minutes=0) for i in range(A.VERDICT_AT)]
    standing = rule("most_lots", 5, at(9), to=None)
    assert A.count([standing], trips[:-1])[0].enough is False
    assert A.count([standing], trips)[0].enough is True
    assert A.VERDICT_AT == 30


def test_cost_is_the_charges_on_the_trades_counted_when_known():
    trips = [trip(0, at(10), 10), trip(1, at(11), 10)]
    fees = {"t0": Decimal(66), "t1": Decimal(70)}
    assert A.count([rule("most_trades", 5, at(9))], trips, fees)[0].fees == Decimal(136)
    assert A.count([rule("most_trades", 5, at(9))], trips)[0].fees is None


def test_a_note_matches_the_first_trade_in_its_book_within_the_window():
    class Note:
        def __init__(self, i, book, when):
            self.id, self.book, self.entered_at = i, book, when
    trips = [trip(0, at(10, 5), 10), trip(1, at(10, 20), 10), trip(2, at(11, 30), 10)]
    notes = [Note(1, "NIFTY options", at(10)), Note(2, "NIFTY options", at(10, 1)),
             Note(3, "Crude options", at(10, 2)), Note(4, "NIFTY options", at(10, 40))]
    matched = A.match_notes(notes, trips, book_of=lambda t: "NIFTY options")
    assert matched == {1: "t0", 2: "t1"}  # 3: wrong book; 4: nothing within 30 minutes
