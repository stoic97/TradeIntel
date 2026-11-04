"""The losing run as a story: every figure the page says, worked by hand [TICKET-820].

Synthetic trades, all invented, in India time. EVENING is one book on one day, plus a
costlier, shorter run across two days in another book:

  3 Mar 2026, WIDGETOIL options
  m   09:00:00-09:05:00  5000 CE  50  +200  the morning, before the run
  r1  18:00:00-18:10:00  5000 CE  50  -100
  r2  18:10:12-18:20:00  5000 CE  50  -200  back in after 0:12
  r3  18:21:30-18:30:00  4900 PE 100  -300  1:30, switched, doubled after two losses
  r4  18:32:00-18:40:00  4900 PE 150   -50  2:00, exactly two minutes, tripled
  r5  18:42:01-18:50:00  5000 CE 150  -150  2:01, switched
  r6  18:50:30-19:00:00  4900 PE 100  -200  0:30, switched
  a   19:01:00-19:30:00  5000 CE 100  +400  1:00, the first trade after the run

  The run: 6 losses, -1,000, 18:00 to 19:00. The day: +200 - 1,000 + 400 = -400.
  Switches: r2 to r3, r4 to r5, r5 to r6 = 3. Back within two minutes: 0:12, 1:30, 2:00,
  0:30 = 4 of the 5.

  4-5 Mar 2026, WIDGETIDX options
  c1  4 Mar 15:00-15:10    100 CE  75  -800
  c2  5 Mar 09:20-09:30    100 CE  75  -900
  e   5 Mar 10:00-10:05    100 CE  75   +50

  That run: 2 losses, -1,700, so it is the costliest and not the longest.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from services.production.api import formatting
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s


def trip(
    trip_id, day, opened, closed, net, *, symbol="WIDGETOIL", kind="CE", strike=5000, qty=50,
    closed_day=None, segment="OPT",
):
    entry = datetime.fromisoformat(f"{day}T{opened}+05:30")
    exit_ = datetime.fromisoformat(f"{closed_day or day}T{closed}+05:30")
    is_option = segment == "OPT"
    line = mx.TradeLine(
        symbol=symbol, segment=segment, side="Buy", quantity=qty,
        entry_price=Decimal(10), exit_price=Decimal(9), net=Decimal(net),
        strike=Decimal(strike) if is_option else None,
        option_type=kind if is_option else None, entry_ts=entry,
    )
    return mx.Trip(
        trip_id, symbol, day, entry, exit_, int((exit_ - entry).total_seconds()), Decimal(net), 1,
        s.RiskUnitSourceV1.PREMIUM_PAID, is_option=is_option, lines=(line,),
    )


def spread(trip_id, day, opened, closed, net):
    """A position of two legs: one Trip with one result."""
    first = trip("x", day, opened, closed, net)
    second = trip("y", day, opened, closed, 0, kind="PE", strike=4900)
    legs = (mx.Leg("Bought 5000 CE", Decimal(net)), mx.Leg("Bought 4900 PE", Decimal(0)))
    return mx.Trip(
        trip_id, "WIDGETOIL", day, first.entry_ts, first.exit_ts, first.holding_seconds,
        Decimal(net), 1, s.RiskUnitSourceV1.STRUCTURE_MAX_LOSS, legs=legs,
        lines=(first.lines[0], second.lines[0]),
    )


DAY = "2026-03-03"
RUN = [
    trip("r1", DAY, "18:00:00", "18:10:00", -100),
    trip("r2", DAY, "18:10:12", "18:20:00", -200),
    trip("r3", DAY, "18:21:30", "18:30:00", -300, kind="PE", strike=4900, qty=100),
    trip("r4", DAY, "18:32:00", "18:40:00", -50, kind="PE", strike=4900, qty=150),
    trip("r5", DAY, "18:42:01", "18:50:00", -150, qty=150),
    trip("r6", DAY, "18:50:30", "19:00:00", -200, kind="PE", strike=4900, qty=100),
]
EVENING = [
    trip("m", DAY, "09:00:00", "09:05:00", 200),
    *RUN,
    trip("a", DAY, "19:01:00", "19:30:00", 400, qty=100),
    trip("c1", "2026-03-04", "15:00:00", "15:10:00", -800, symbol="WIDGETIDX", strike=100, qty=75),
    trip("c2", "2026-03-05", "09:20:00", "09:30:00", -900, symbol="WIDGETIDX", strike=100, qty=75),
    trip("e", "2026-03-05", "10:00:00", "10:05:00", 50, symbol="WIDGETIDX", strike=100, qty=75),
]


def story_of(trips):
    """The longest run's story."""
    return mx.run_story(trips, mx.longest_losing_run(trips).trip_ids)


@pytest.fixture()
def story():
    return story_of(EVENING)


def test_the_longest_run_is_when_in_what_and_what_it_cost(story):
    assert story.length == 6
    assert story.net == Decimal("-1000.00")
    assert story.days == [DAY]
    assert story.books == ["WIDGETOIL options"]
    assert story.span_seconds == 3600
    assert story.same_day


def test_the_costliest_run_is_by_rupees_not_by_count():
    costliest = mx.costliest_losing_run(EVENING)
    assert costliest.trip_ids == ["c1", "c2"]
    assert costliest.length == 2
    assert costliest.crosses_days
    assert mx.longest_losing_run(EVENING).trip_ids == [t.trip_id for t in RUN]


def test_two_runs_that_cost_the_same_read_the_longer_one_as_costliest():
    trips = [
        trip("a", DAY, "09:00:00", "09:10:00", -300),
        trip("w", DAY, "09:20:00", "09:30:00", 10),
        trip("b", DAY, "09:40:00", "09:50:00", -100),
        trip("c", DAY, "10:00:00", "10:10:00", -200),
    ]
    assert mx.costliest_losing_run(trips).trip_ids == ["b", "c"]


def test_no_loss_has_no_costliest_run_and_no_story():
    trips = [trip("w", DAY, "09:20:00", "09:30:00", 10)]
    assert mx.costliest_losing_run(trips).length == 0
    assert mx.run_story(trips, []) is None


# ---------- The gap is from the previous trade's exit ----------


def test_the_gap_runs_from_the_previous_exit_not_its_entry(story):
    assert story.gaps["r2"] == 12
    assert story.gaps["r3"] == 90
    assert story.gaps["r4"] == 120
    assert story.gaps["r5"] == 121
    assert story.gaps["r6"] == 30


def test_the_first_trade_of_a_run_has_no_gap(story):
    assert "r1" not in story.gaps


def test_the_trade_after_the_run_has_its_gap(story):
    assert story.gaps["a"] == 60


def test_no_gap_is_read_across_a_night():
    story = mx.run_story(EVENING, ["c1", "c2"])
    assert "c2" not in story.gaps


def test_a_trade_opened_before_the_last_one_closed_has_a_negative_gap_and_is_not_back_in():
    trips = [
        trip("a", DAY, "09:00:00", "09:10:00", -100),
        trip("b", DAY, "09:05:00", "09:20:00", -100),
        trip("c", DAY, "09:21:00", "09:30:00", -100),
    ]
    story = mx.run_story(trips, ["a", "b", "c"])
    assert story.gaps["b"] == -300
    assert (story.back_in.within, story.back_in.of) == (1, 1)


@pytest.mark.parametrize(
    ("seconds", "written"),
    [(0, "0:00"), (12, "0:12"), (90, "1:30"), (120, "2:00"), (3725, "62:05")],
)
def test_a_gap_is_written_as_minutes_and_seconds(seconds, written):
    assert formatting.minutes_seconds(seconds) == written


# ---------- Re-entry is the fact of that day only (the ruling) ----------


def test_back_in_within_two_minutes_is_counted_on_the_day_and_two_minutes_counts(story):
    assert (story.back_in.within, story.back_in.of) == (4, 5)


def test_a_run_across_days_makes_no_claim_about_re_entry():
    assert mx.run_story(EVENING, ["c1", "c2"]).back_in is None


def test_a_run_across_books_makes_no_claim_about_re_entry():
    trips = [
        trip("a", DAY, "09:00:00", "09:10:00", -100),
        trip("b", DAY, "09:10:30", "09:20:00", -100, symbol="WIDGETIDX"),
    ]
    assert mx.run_story(trips, ["a", "b"]).back_in is None


def test_no_re_entry_inside_two_minutes_says_nothing():
    trips = [
        trip("a", DAY, "09:00:00", "09:10:00", -100),
        trip("b", DAY, "09:30:00", "09:40:00", -100),
    ]
    assert mx.run_story(trips, ["a", "b"]).back_in is None


# ---------- Switches ----------


def test_switches_between_calls_and_puts_are_counted_from_this_run(story):
    assert story.flips == 3


def test_a_run_of_calls_alone_has_no_switch():
    trips = [trip("a", DAY, "09:00:00", "09:10:00", -1), trip("b", DAY, "09:11:00", "09:12:00", -1)]
    assert mx.run_story(trips, ["a", "b"]).flips == 0


def test_a_call_in_one_book_and_a_put_in_another_is_not_a_switch():
    trips = [
        trip("a", DAY, "09:00:00", "09:10:00", -1),
        trip("b", DAY, "09:11:00", "09:12:00", -1, kind="PE", symbol="WIDGETIDX"),
    ]
    assert mx.run_story(trips, ["a", "b"]).flips == 0


def test_a_future_between_a_call_and_a_put_is_not_a_switch():
    trips = [
        trip("a", DAY, "09:00:00", "09:10:00", -1),
        trip("b", DAY, "09:11:00", "09:12:00", -1, segment="FUT"),
        trip("c", DAY, "09:13:00", "09:14:00", -1, kind="PE"),
    ]
    assert mx.run_story(trips, ["a", "b", "c"]).flips == 0


def test_a_position_of_two_legs_is_neither_a_call_nor_a_put():
    trips = [
        trip("a", DAY, "09:00:00", "09:10:00", -1),
        spread("b", DAY, "09:11:00", "09:12:00", -1),
        trip("c", DAY, "09:13:00", "09:14:00", -1, kind="PE"),
    ]
    assert mx.run_story(trips, ["a", "b", "c"]).flips == 0


# ---------- Size ----------


def test_the_size_line_is_the_first_rise_and_how_far_it_climbed(story):
    assert story.size.losses_before == 2
    assert story.size.steps == [50, 100, 150]


def test_a_size_that_never_rises_has_no_size_line():
    trips = [
        trip("a", DAY, "09:00:00", "09:10:00", -1, qty=100),
        trip("b", DAY, "09:11:00", "09:12:00", -1, qty=50),
    ]
    assert mx.run_story(trips, ["a", "b"]).size is None


def test_a_climb_stops_at_the_first_drop():
    trips = [
        trip("a", DAY, "09:00:00", "09:10:00", -1, qty=50),
        trip("b", DAY, "09:11:00", "09:12:00", -1, qty=75),
        trip("c", DAY, "09:13:00", "09:14:00", -1, qty=50),
        trip("d", DAY, "09:15:00", "09:16:00", -1, qty=200),
    ]
    size = mx.run_story(trips, ["a", "b", "c", "d"]).size
    assert size.losses_before == 1
    assert size.steps == [50, 75]


def test_quantities_of_two_instruments_are_not_compared():
    trips = [
        trip("a", DAY, "09:00:00", "09:10:00", -1, qty=50),
        trip("b", DAY, "09:11:00", "09:12:00", -1, qty=100, symbol="WIDGETIDX"),
    ]
    assert mx.run_story(trips, ["a", "b"]).size is None


def test_a_position_of_two_legs_has_no_one_size_so_no_size_line():
    trips = [
        trip("a", DAY, "09:00:00", "09:10:00", -1, qty=50),
        spread("b", DAY, "09:11:00", "09:12:00", -1),
        trip("c", DAY, "09:13:00", "09:14:00", -1, qty=100),
    ]
    assert mx.run_story(trips, ["a", "b", "c"]).size is None


# ---------- What came after ----------


def test_the_first_trade_after_the_run_and_the_days_close(story):
    assert story.after.trip_id == "a"
    assert story.last_day == DAY
    assert story.last_day_net == Decimal("-400.00")


def test_a_run_at_the_end_of_the_file_has_nothing_after_it():
    trips = [trip("a", DAY, "09:00:00", "09:10:00", -1)]
    assert mx.run_story(trips, ["a"]).after is None


def test_a_run_across_days_closes_on_the_day_it_ended():
    story = mx.run_story(EVENING, ["c1", "c2"])
    assert story.last_day == "2026-03-05"
    assert story.last_day_net == Decimal("-850.00")  # -900 + 50; the -800 was the day before
    assert story.after.trip_id == "e"


def test_a_position_held_overnight_is_not_a_run_inside_one_day():
    trips = [
        trip("a", DAY, "09:00:00", "09:10:00", -1),
        trip("b", DAY, "15:00:00", "10:00:00", -1, closed_day="2026-03-04"),
    ]
    assert not mx.run_story(trips, ["a", "b"]).same_day


# ---------- A mixed run ----------


def test_a_mixed_run_names_every_book_most_trades_first():
    trips = [
        trip("a", DAY, "09:00:00", "09:10:00", -1, symbol="WIDGETIDX"),
        trip("b", DAY, "09:11:00", "09:12:00", -1),
        trip("c", DAY, "09:13:00", "09:14:00", -1, segment="FUT"),
        trip("d", DAY, "09:15:00", "09:16:00", -1),
    ]
    assert mx.run_story(trips, ["a", "b", "c", "d"]).books == [
        "WIDGETOIL options", "WIDGETIDX options", "Futures",
    ]


# ---------- The hour it started, as the clock tells it ----------


def test_the_hour_a_run_started_is_counted_in_its_book_on_same_day_trades(story):
    # r1 to r6 open in the 18:00 hour and come to -1,000. The trade after opens at 19:01.
    assert story.start_hour.hour == 18
    assert story.start_hour.book == "WIDGETOIL options"
    assert story.start_hour.net == Decimal("-1000.00")
    assert story.start_hour.trips == 6


def test_a_run_that_opened_on_a_position_held_past_the_day_has_no_hour_to_point_at():
    trips = [trip("b", DAY, "15:00:00", "10:00:00", -1, closed_day="2026-03-04")]
    assert mx.run_story(trips, ["b"]).start_hour is None
