"""Strike rate, averages and break-even read same-day trades only [TICKET-793].

A holding is not a trade the day's decisions made, and a year-long winner in the average
makes the gap look narrower than it is. Worked by hand from held_past_day.json:
  same-day winners 100, 300, 500, 50, 600: five, averaging 310
  same-day losers 200, 400, 600, 100, 50: five, averaging 270
  strike rate 5 of 10 is 50%; break-even is 270 / (310 + 270) = 46.55%, so 46.6%
Whole history would be 7 winners and 7 losers, averaging 8,650 and 360.
"""

from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from services.production.api import formatting
from services.production.api import scope_facts as SF
from services.production.api import scope_map as S
from services.production.mirror import metrics as mx
from tests.unit.api.test_scope_chapters import IMP, TRIPS, chapter_page, readable, trips_from
from tests.unit.api.test_scope_facts import fact_page

HELD = mx.load_trips(
    json.loads(Path("tests/fixtures/mirror_contract/held_past_day.json").read_text())
)
ONLY_HELD = [t for t in HELD if t.trip_id in {"h03", "h06", "h09", "h11"}]
SENTENCE = (
    "Your average winner was ₹310 and your average loser ₹270. "
    "At those sizes, you break even at 47 of 100."
)
NOTE = (
    "These are trades you closed the day you opened them. "
    "4 positions held past the day are not counted here."
)


def test_the_strike_rate_reads_same_day_trades():
    st = SF.record_context(HELD)["strike"]
    assert (st.wins, st.losses, str(st.rate_percent)) == (5, 5, "50")


def test_break_even_is_worked_from_the_average_winner_and_loser():
    be = mx.break_even(mx.same_day_trips(HELD))
    assert be.average_winner == Decimal(310)
    assert be.average_loser == Decimal(270)
    assert str(be.percent) == "46.6"


def test_a_holding_does_not_move_the_break_even():
    assert SF.record_context(HELD)["break_even"].percent == Decimal("46.6")


def test_no_loser_means_no_break_even():
    assert mx.break_even(trips_from([100, 200])).percent is None


def test_no_winner_means_no_break_even():
    assert mx.break_even(trips_from([-100, -200])).percent is None


@pytest.mark.parametrize("page", [lambda: fact_page("math", HELD), lambda: chapter_page(2, HELD)])
def test_the_page_gives_the_averages_and_the_break_even(page):
    assert SENTENCE in readable(page())


@pytest.mark.parametrize("page", [lambda: fact_page("math", HELD), lambda: chapter_page(2, HELD)])
def test_the_page_says_what_is_left_out(page):
    assert NOTE in readable(page())


def test_one_held_position_reads_in_the_singular():
    one = [t for t in HELD if t.trip_id not in {"h03", "h09", "h11"}]
    assert "1 position held past the day is not counted here." in readable(fact_page("math", one))


def test_with_nothing_held_there_is_no_note():
    assert "held past the day" not in readable(fact_page("math", TRIPS))


def test_the_trades_listed_are_the_trades_counted():
    ctx = SF.record_context(HELD)
    ids = {t.trip_id for t in S.trades_behind("math", ctx)}
    assert not ids & {"h03", "h06", "h09", "h11"}
    assert len(ids) == 10


def test_a_history_of_only_held_positions_has_no_strike_rate():
    figs = SF.facts(SF.record_context(ONLY_HELD), IMP)
    assert figs["math"]["state"] == "not-enough"


def test_chapter_three_still_compares_every_trade():
    """Only this fact narrows. After two losses against the rest keeps its own population."""
    ctx = SF.record_context(HELD)
    assert ctx["rest_strike"].wins + ctx["after_strike"].wins == 7


@pytest.mark.parametrize(
    ("value", "written"),
    [
        (Decimal("0.96"), "+₹0.96"),
        (Decimal("-0.5"), "−₹0.50"),
        (Decimal("0.961"), "+₹0.96"),
    ],
)
def test_a_trade_under_a_rupee_shows_its_paise(value, written):
    """A win of 96 paise written as ₹0 reads as a winner that made nothing."""
    assert formatting.rupees_on_a_trade(value) == written


@pytest.mark.parametrize(
    ("value", "written"),
    [(Decimal(0), "₹0"), (Decimal("1.96"), "+₹1"), (Decimal("-12345.6"), "−₹12,345")],
)
def test_every_other_trade_reads_as_before(value, written):
    assert formatting.rupees_on_a_trade(value) == written


def test_the_trade_card_uses_it():
    trips = trips_from([1, -1, 1])
    small = [replace(trips[0], net=Decimal("0.96")), *trips[1:]]
    assert "+₹0.96" in readable(fact_page("clock", small))


def test_totals_keep_the_whole_rupee_cut():
    assert formatting.rupees(Decimal("0.96")) == "₹0"


@pytest.mark.parametrize(
    ("trips", "shown"), [(HELD, "50"), (trips_from([1] * 10 + [-1] * 10), "50")]
)
def test_a_round_percentage_is_written_as_a_number(trips, shown):
    """5E+1 is what a trimmed 50 came out as, on the page."""
    page = readable(fact_page("math", trips))
    assert f"{shown} of 100 trades made money" in page
    assert "E+" not in page
    assert "E+" not in readable(fact_page("math", trips))
