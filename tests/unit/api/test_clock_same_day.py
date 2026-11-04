"""The clock reads same-day trades only [TICKET-794].

An investment bought in the morning is not a time of day when trading works. Worked by hand
from held_past_day.json:
  09:00 hour: 100 + 300 + 500 + 50 + 600 = +1,550, five trades
  10:00 hour: -200 - 400 - 600 - 100 - 50 = -1,350, five trades
The held positions opened at 15:00, 14:00, 23:50 and 10:00, and none of them is counted.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from services.production.api import scope_facts as SF
from services.production.api import scope_map as S
from services.production.mirror import metrics as mx
from tests.unit.api.test_scope_chapters import IMP, TRIPS, chapter_page, readable
from tests.unit.api.test_scope_facts import fact_page

HELD = mx.load_trips(
    json.loads(Path("tests/fixtures/mirror_contract/held_past_day.json").read_text())
)
ONLY_HELD = [t for t in HELD if t.trip_id in {"h03", "h06", "h09", "h11"}]
NOTE = (
    "These are trades you closed the day you opened them. "
    "4 positions held past the day are not counted here."
)


def test_each_hour_counts_same_day_trades_only():
    hours = SF.record_context(HELD)["hours"]
    assert [(h.hour, h.net, h.trips) for h in hours] == [
        (9, Decimal(1550), 5), (10, Decimal(-1350), 5),
    ]


def test_an_hour_with_only_a_holding_is_gone():
    assert not {14, 15, 23} & {h.hour for h in SF.record_context(HELD)["hours"]}


def test_the_figure_counts_the_hours_shown():
    assert SF.facts(SF.record_context(HELD), IMP)["clock"]["figure"] == "2 hours"


def test_the_trades_listed_are_the_trades_counted():
    ids = {t.trip_id for t in S.trades_behind("clock", SF.record_context(HELD))}
    assert not ids & {"h03", "h06", "h09", "h11"}
    assert len(ids) == 10


@pytest.mark.parametrize("page", [lambda: fact_page("clock", HELD), lambda: chapter_page(2, HELD)])
def test_the_page_says_what_is_left_out(page):
    assert NOTE in readable(page())


def test_one_held_position_reads_in_the_singular():
    one = [t for t in HELD if t.trip_id not in {"h03", "h09", "h11"}]
    assert "1 position held past the day is not counted here." in readable(fact_page("clock", one))


def test_with_nothing_held_there_is_no_note():
    assert "held past the day" not in readable(fact_page("clock", TRIPS))


def test_a_history_of_only_held_positions_says_not_enough():
    figs = SF.facts(SF.record_context(ONLY_HELD), IMP)
    assert figs["clock"]["state"] == "not-enough"
    assert figs["clock"]["figure"] == "—"


def test_that_history_still_renders():
    assert "None" not in readable(fact_page("clock", ONLY_HELD))


def test_the_other_facts_keep_their_own_population():
    """The worst days still read every trade. This ticket moves only the clock."""
    ctx = SF.record_context(HELD)
    assert len(ctx["trips"]) == len(HELD)
    assert ctx["share"].total == Decimal(57700)
