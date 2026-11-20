"""TICKET-986: the running result as candles, per book, by day, week and month.

His result after each closed trade, in exit order, grouped into candles a trader reads
without being taught: open is where the period started, close where it ended, high and low
the best and worst it reached in between. The home card and the Your numbers page read
this; neither computes anything of its own.

Every expected figure below was worked out by hand from the ticket's text before any code
existed (the working is in the comments), never copied from program output. All trades are
made up.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from services.production.api import report_filter as rf
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s

IST = ZoneInfo("Asia/Kolkata")
D = Decimal


def trip(tid: str, when: str, net: str, symbol: str = "NIFTY", segment: str = "OPT") -> mx.Trip:
    """One closed position, leaving at `when` (IST). Shares carry an EQ line, as loaded ones do."""
    leave = datetime.fromisoformat(when).replace(tzinfo=IST)
    entry = leave - timedelta(minutes=20)
    line = mx.TradeLine(symbol, segment, "Buy", 1, None, None, D(net))
    return mx.Trip(
        trip_id=tid, symbol=symbol, trading_day=entry.date().isoformat(),
        entry_ts=entry, exit_ts=leave, holding_seconds=1200, net=D(net), lots=1,
        risk_unit_source=s.RiskUnitSourceV1.PREMIUM_PAID, is_option=segment == "OPT",
        lines=(line,),
    )


def record() -> list[mx.Trip]:
    """Twelve trades: NIFTY options and shares; a Sunday session (Budget day, 1 Feb 2026);
    the week of Mon 26 Jan to Sun 1 Feb crosses a month end; t4's net is after its charges
    (gross 230, charges 30), as the stored net always is. Given out of order on purpose."""
    t = [
        trip("t01", "2026-01-30T10:00", "1000"),
        trip("t02", "2026-01-30T14:00", "-400"),
        trip("t03", "2026-02-01T11:00", "300"),                        # Sunday session
        trip("t04", "2026-02-02T10:00", "200", "TATASTEEL", "EQ"),     # after 30 of charges
        trip("t05", "2026-02-02T15:00", "-1500"),
        trip("t06", "2026-02-03T11:00", "700"),
        trip("t07", "2026-02-05T13:00", "-100", "TATASTEEL", "EQ"),
        trip("t08", "2026-02-09T10:00", "250"),
        trip("t09", "2026-02-09T11:00", "-50"),
        trip("t10", "2026-02-27T14:00", "900"),
        trip("t11", "2026-03-02T10:00", "400", "TATASTEEL", "EQ"),
        trip("t12", "2026-03-02T12:00", "-600"),
    ]
    return list(reversed(t))


# Running result after each trade, in exit order:
#   t01 1000 | t02 600 | t03 900 | t04 1100 | t05 -400 | t06 300 | t07 200
#   t08 450  | t09 400 | t10 1300 | t11 1700 | t12 1100          -> total 1100
def ohlc(c: mx.Candle) -> tuple:
    return (c.period, c.open, c.high, c.low, c.close, c.trades)


def test_the_running_result_ends_at_the_record_total_to_the_rupee():
    run = mx.running_result(record())
    assert run.book == "All"
    assert run.trades == 12
    assert run.total == D("1100") == sum((t.net for t in record()), D(0))
    assert run.candles["day"][-1].close == run.total


def test_day_candles():
    # A day is the exit's date in IST; Sunday 1 Feb is a day of its own. Open is the previous
    # close (0 for the first); high and low take in the open and every value inside the day.
    assert [ohlc(c) for c in mx.running_result(record()).candles["day"]] == [
        ("2026-01-30", D(0), D(1000), D(0), D(600), 2),
        ("2026-02-01", D(600), D(900), D(600), D(900), 1),
        ("2026-02-02", D(900), D(1100), D(-400), D(-400), 2),
        ("2026-02-03", D(-400), D(300), D(-400), D(300), 1),
        ("2026-02-05", D(300), D(300), D(200), D(200), 1),
        ("2026-02-09", D(200), D(450), D(200), D(400), 2),
        ("2026-02-27", D(400), D(1300), D(400), D(1300), 1),
        ("2026-03-02", D(1300), D(1700), D(1100), D(1100), 2),
    ]


def test_week_candles_run_monday_to_sunday_and_cross_a_month_end():
    # The week of Mon 26 Jan holds Fri 30 Jan and Sun 1 Feb. Weeks with no trade have no candle.
    assert [ohlc(c) for c in mx.running_result(record()).candles["week"]] == [
        ("2026-01-26", D(0), D(1000), D(0), D(900), 3),
        ("2026-02-02", D(900), D(1100), D(-400), D(200), 4),
        ("2026-02-09", D(200), D(450), D(200), D(400), 2),
        ("2026-02-23", D(400), D(1300), D(400), D(1300), 1),
        ("2026-03-02", D(1300), D(1700), D(1100), D(1100), 2),
    ]


def test_month_candles():
    assert [ohlc(c) for c in mx.running_result(record()).candles["month"]] == [
        ("2026-01", D(0), D(1000), D(0), D(600), 2),
        ("2026-02", D(600), D(1300), D(-400), D(1300), 8),
        ("2026-03", D(1300), D(1700), D(1100), D(1100), 2),
    ]


def test_each_candle_carries_what_it_made():
    for c in mx.running_result(record()).candles["week"]:
        assert c.net == c.close - c.open


def test_his_high_biggest_drop_and_lowest_point():
    run = mx.running_result(record())
    # High: 1700, reached on 2 Mar.
    assert (run.high.value, run.high.day) == (D(1700), "2026-03-02")
    # Biggest drop: from 1100 (2 Feb, t04) to -400 (2 Feb, t05) = 1500; the later fall from
    # 1700 to 1100 is only 600.
    assert (run.drop.value, run.drop.from_day, run.drop.to_day) == (D(1500), "2026-02-02", "2026-02-02")
    # Lowest: -400, on 2 Feb.
    assert (run.lowest.value, run.lowest.day) == (D(-400), "2026-02-02")


def test_a_high_that_never_rose_above_nothing_is_zero_and_a_drop_from_the_start_says_so():
    run = mx.running_result([trip("a", "2026-01-05T10:00", "-100"), trip("b", "2026-01-06T10:00", "-50")])
    assert (run.high.value, run.high.day) == (D(0), None)
    assert (run.drop.value, run.drop.from_day, run.drop.to_day) == (D(150), None, "2026-01-06")
    assert (run.lowest.value, run.lowest.day) == (D(-150), "2026-01-06")


def test_win_rate_and_break_even_are_the_reports_own():
    run = mx.running_result(record())
    # Wins t01 t03 t04 t06 t08 t10 t11 = 7; losses t02 t05 t07 t09 t12 = 5: 7 / 12 = 58.3%.
    assert run.strike == mx.strike_rate(record())
    assert run.strike.rate_percent == D("58.3")
    # Average winner 3750 / 7 = 535.714...; average loser 2650 / 5 = 530;
    # 530 / (535.714... + 530) = 49.73...% -> 49.7.
    assert run.even == mx.break_even(record())
    assert run.even.percent == D("49.7")


def test_a_book_with_no_loser_has_no_break_even_and_says_so():
    run = mx.running_result([trip("a", "2026-01-05T10:00", "100"), trip("b", "2026-01-06T10:00", "50")])
    assert run.even.percent is None


def test_books_follow_the_reports_rule_and_add_up_to_the_record():
    # Nine NIFTY option trades are under NAMED_BOOK_MINIMUM, so they are "Other options";
    # shares are always their own book. 9 + 3 = 12 trades; 600 + 500 = 1100.
    runs = mx.running_results(record())
    assert [(r.book, r.trades, r.total) for r in runs] == [
        ("All", 12, D(1100)),
        ("Other options", 9, D(600)),
        ("Stocks and ETFs", 3, D(500)),
    ]
    assert sum(r.trades for r in runs[1:]) == runs[0].trades
    assert sum((r.total for r in runs[1:]), D(0)) == runs[0].total


def test_a_books_candles_start_from_nothing_of_its_own():
    shares = {r.book: r for r in mx.running_results(record())}["Stocks and ETFs"]
    # t04 200 | t07 100 | t11 500.
    assert [ohlc(c) for c in shares.candles["month"]] == [
        ("2026-02", D(0), D(200), D(0), D(100), 2),
        ("2026-03", D(100), D(500), D(100), D(500), 1),
    ]
    assert (shares.drop.value, shares.drop.from_day, shares.drop.to_day) == (D(100), "2026-02-02", "2026-02-05")


def test_named_option_books_come_first_by_trades_then_other_options_then_the_rest():
    trips = (
        [trip(f"c{i}", f"2026-01-{5 + i % 20:02d}T10:00", "10", "CRUDEOIL" if i % 2 else "CRUDEOILM")
         for i in range(21)]
        + [trip(f"b{i}", "2026-02-02T10:00", "-5", "BANKNIFTY") for i in range(4)]
        + [trip(f"n{i}", "2026-02-03T10:00", "-5") for i in range(2)]
        + [trip("f1", "2026-02-04T10:00", "7", "NIFTY", "FUT")]
        + [trip("e1", "2026-02-05T10:00", "3", "TATASTEEL", "EQ")]
    )
    groups = mx.book_groups(trips)
    # Crude and crude mini are one book (21); BANKNIFTY 4 + NIFTY 2 pool into Other options.
    assert [(name, len(ts)) for name, ts in groups] == [
        ("Crude options", 21), ("Other options", 6), ("Futures", 1), ("Stocks and ETFs", 1),
    ]
    assert sum(len(ts) for _, ts in groups) == len(trips)


def test_the_verdict_reads_the_same_books():
    trips = record()
    rows = {r.label: (r.trades, r.net) for r in mx.verdict(trips).books}
    assert rows == {name: (len(ts), sum((t.net for t in ts), D(0))) for name, ts in mx.book_groups(trips)}


def test_it_follows_the_report_filter_because_it_reads_what_it_is_given():
    shares_only = rf.apply(record(), rf.ReportFilter(book="Stocks and ETFs"), None)
    run = mx.running_result(shares_only)
    assert (run.trades, run.total) == (3, D(500))


def test_figures_are_decimals_never_floats():
    run = mx.running_result(record())
    for frame in ("day", "week", "month"):
        for c in run.candles[frame]:
            assert all(isinstance(v, Decimal) for v in (c.open, c.high, c.low, c.close, c.net))
    assert all(isinstance(v, Decimal) for v in (run.total, run.high.value, run.drop.value, run.lowest.value))
