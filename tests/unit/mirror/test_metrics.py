"""Every Appendix A metric, against the hand-calculated fixture.

Each test reads its expected value from expected.json rather than restating it, so
there is one place a figure lives and the fixture's arithmetic is what is being
checked. A metric function that disagrees with the fixture is wrong until someone
redoes the arithmetic by hand and changes the fixture deliberately.

The functions are pure: a list of trips in, a typed result out. Nothing here reads
a database, formats a rupee or knows what a template is.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s

FIXTURE = Path("tests/fixtures/mirror_contract")


@pytest.fixture(scope="module")
def trips():
    return mx.load_trips(json.loads((FIXTURE / "main.json").read_text()))


@pytest.fixture(scope="module")
def expected():
    return json.loads((FIXTURE / "expected.json").read_text())


def test_the_fixture_is_the_one_the_expectations_describe(trips, expected):
    assert len(trips) == expected["totals"]["trips"]
    assert sum(t.net for t in trips) == Decimal(expected["totals"]["net"])


def test_five_worst_days(trips, expected):
    result = mx.five_worst_days(trips)
    want = expected["five_worst_days"]
    assert [d.trading_day for d in result.days] == [d["trading_day"] for d in want["days"]]
    assert [d.net for d in result.days] == [Decimal(d["net"]) for d in want["days"]]
    assert result.sum == Decimal(want["sum"])


def test_share_of_total(trips, expected):
    result = mx.share_of_total(trips)
    want = expected["share_of_total"]
    assert result.shown_as_percentage is want["shown_as_percentage"]
    assert str(result.share_percent) == want["share_percent"]
    assert result.other_days_count == want["other_days_count"]
    assert result.other_days_net == Decimal(want["other_days_net"])


def test_normal_day_and_the_busiest(trips, expected):
    result = mx.day_counts(trips)
    want = expected["normal_day"]
    assert result.counts == want["trip_counts_by_day"]
    assert str(result.normal_day) == want["normal_day_trips"]
    assert result.busiest_day == want["busiest_day"]
    assert result.busiest_trips == want["busiest_day_trips"]
    assert str(result.busiest_vs_normal) == want["busiest_day_vs_normal"]


def test_best_five_trades(trips, expected):
    result = mx.best_five(trips)
    want = expected["best_five_trades"]
    assert [t.trip_id for t in result] == [t["trip_id"] for t in want]
    assert [t.net for t in result] == [Decimal(t["net"]) for t in want]


def test_worst_five_trades_resolves_ties_by_earlier_entry(trips, expected):
    result = mx.worst_five(trips)
    want = [t for t in expected["worst_five_trades"] if "trip_id" in t]
    assert [t.trip_id for t in result] == [t["trip_id"] for t in want]


def test_two_straight_losses_matches_the_shared_condition(trips, expected):
    result = mx.two_straight_losses(trips)
    want = expected["two_straight_losses"]
    assert result.population == want["population"]
    assert result.condition == want["condition"]
    assert result.comparison == want["comparison"]
    assert sorted(result.condition_trip_ids) == sorted(want["condition_trip_ids"])
    assert result.condition_net == Decimal(want["condition_net_sum"])
    assert result.comparison_net == Decimal(want["comparison_net_sum"])
    assert str(result.condition_mean) == want["condition_mean"]
    assert str(result.comparison_mean) == want["comparison_mean"]


def test_strike_rate_excludes_scratches(trips, expected):
    result = mx.strike_rate(trips)
    want = expected["strike_rate"]
    assert result.wins == want["wins"]
    assert result.losses == want["losses"]
    assert result.scratches == want["scratches_excluded"]
    assert str(result.rate_percent) == want["rate_percent"]


def test_average_lots(trips, expected):
    result = mx.average_lots(trips)
    assert result.total_lots == expected["average_lots"]["total_lots"]
    assert str(result.mean) == expected["average_lots"]["mean"]


def test_holding_time_by_outcome(trips, expected):
    result = mx.holding_time(trips)
    want = expected["holding_time"]
    assert result.winners_median_seconds == want["winners_median_seconds"]
    assert result.losers_median_seconds == want["losers_median_seconds"]
    assert str(result.ratio) == want["ratio"]


def test_result_by_hour_flags_small_samples(trips, expected):
    result = mx.result_by_hour(trips)
    want = expected["result_by_hour"]
    assert [h.hour for h in result] == [h["hour"] for h in want]
    assert [h.net for h in result] == [Decimal(h["net"]) for h in want]
    assert [h.trips for h in result] == [h["trips"] for h in want]
    assert [h.small_sample for h in result] == [h["small_sample"] for h in want]


def test_longest_losing_run_crosses_days(trips, expected):
    result = mx.longest_losing_run(trips)
    want = expected["longest_losing_run"]
    assert result.length == want["length"]
    assert result.trip_ids == want["trip_ids"]
    assert result.crosses_days is True
    assert result.days == want["days"]


def test_trades_with_a_risk_figure(trips, expected):
    result = mx.risk_figure_counts(trips)
    want = expected["trades_with_a_risk_figure"]
    assert result.counts[s.RiskUnitSourceV1.DECLARED_BUDGET] == want["declared_budget"]
    assert result.counts[s.RiskUnitSourceV1.DEFINED_STOP] == want["defined_stop"]
    assert result.counts[s.RiskUnitSourceV1.PREMIUM_PAID] == want["premium_paid"]
    assert result.counts[s.RiskUnitSourceV1.UNAVAILABLE] == want["unavailable"]
    assert result.counts[s.RiskUnitSourceV1.INFERRED_ATR] == want["inferred_atr"]
    assert result.showable == want["showable_as_denominator"]


def test_journal_unit_default(trips, expected):
    result = mx.journal_unit_default(trips)
    want = expected["journal_unit_default"]
    assert str(result.median_trips_per_day) == want["median_trips_per_eligible_day"]
    assert result.unit.value == want["unit"]


def test_every_metric_returns_a_result_state(trips):
    """Appendix A figures are counted facts; nothing here is a finding."""
    for result in (
        mx.five_worst_days(trips), mx.share_of_total(trips), mx.day_counts(trips),
        mx.two_straight_losses(trips), mx.strike_rate(trips), mx.holding_time(trips),
    ):
        assert result.state in s.V1_EMITTABLE_STATES
        assert result.state is not s.ResultState.VALIDATED_FINDING


def test_an_empty_history_says_so_rather_than_dividing_by_zero():
    for result in (mx.five_worst_days([]), mx.strike_rate([]), mx.holding_time([])):
        assert result.state is s.ResultState.INSUFFICIENT_SAMPLE


def test_every_trip_carries_its_instrument(trips):
    """B1: a trade record names what was traded. The fixture's one instrument."""
    assert {t.symbol for t in trips} == {"WIDGETOIL"}


# B2 (handoff section 9): the series the charts are drawn from. Expected values are
# read off the trip table in tests/fixtures/mirror_contract/generate.py, the fixture's
# hand-written specification, not from the functions' output.

def test_the_daily_series_is_every_trading_day_in_date_order(trips):
    """Eight days; the table's own day comments give each net and count."""
    assert [(d.trading_day, d.net, d.trips) for d in mx.daily_series(trips)] == [
        ("2026-09-01", Decimal(-300), 3),
        ("2026-09-02", Decimal(-8000), 6),
        ("2026-09-03", Decimal(-200), 4),
        ("2026-09-04", Decimal(-2000), 5),
        ("2026-09-07", Decimal(-12000), 8),
        ("2026-09-08", Decimal(-500), 4),
        ("2026-09-09", Decimal(-1000), 6),
        ("2026-09-10", Decimal(-1000), 4),
    ]


def test_the_daily_series_adds_up_to_the_whole_result(trips, expected):
    assert sum(d.net for d in mx.daily_series(trips)) == Decimal(expected["totals"]["net"])
    assert sum(d.trips for d in mx.daily_series(trips)) == expected["totals"]["trips"]


def test_the_five_worst_days_are_taken_from_the_daily_series(trips):
    """One place decides a day's net: the five worst are five of the series' days."""
    series = {d.trading_day: d for d in mx.daily_series(trips)}
    for day in mx.five_worst_days(trips).days:
        assert series[day.trading_day] == day


def test_the_holding_series_is_each_trade_in_entry_order_by_outcome(trips):
    """Winners t01 t07 t16 t27 t31 t35; losers t02 to t40 less the six winners and the
    two scratches, t11 and t13, which are in neither (as in holding_time)."""
    held = mx.holding_series(trips)
    assert held.winners_seconds == [minutes * 60 for minutes in (30, 30, 30, 30, 20, 20)]
    assert held.losers_seconds == [minutes * 60 for minutes in (
        30, 20, 15, 10, 10, 10, 60,      # day 1 and day 2
        10, 10,                          # day 3
        10, 10, 10, 10,                  # day 4
        5, 5, 5, 5, 5, 5, 5, 5,          # day 5
        10, 10, 10,                      # day 6
        10, 10, 10, 10,                  # day 7
        10, 10, 10, 10,                  # day 8
    )]


def test_the_holding_medians_come_from_the_holding_series(trips, expected):
    """One place decides a hold: the medians on the page are the series' medians."""
    want = expected["holding_time"]
    assert mx.holding_time(trips).winners_median_seconds == want["winners_median_seconds"]
    assert mx.holding_time(trips).losers_median_seconds == want["losers_median_seconds"]


def test_an_empty_history_has_empty_series():
    assert mx.daily_series([]) == []
    assert mx.holding_series([]) == mx.HoldingSeries(winners_seconds=[], losers_seconds=[])
