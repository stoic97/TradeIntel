"""The hold-time chart: same-day trades set its scale and its dots [TICKET-795].

One position held for months put every intraday trade at zero on the axis. Expected
values are worked by hand from held_past_day.json:
  same-day winners, minutes in entry order: 30, 20, 10, 375, 10
  same-day losers: 30, 20, 10, 10, 10
  whole history winners add 1440 and 525600, losers add 20 and 2880, so
  sorted winners 10, 10, 20, 30, 375, 1440, 525600 have a median of 30,
  sorted losers 10, 10, 10, 20, 20, 30, 2880 have a median of 20.
"""

from __future__ import annotations

import json
from pathlib import Path

from services.production.api import dial
from services.production.api import scope_facts as SF
from services.production.api import scope_geometry as G
from services.production.mirror import metrics as mx
from tests.unit.api.test_scope_chapters import IMP, TRIPS, chapter_page, readable
from tests.unit.api.test_scope_facts import fact_page

HELD = mx.load_trips(
    json.loads(Path("tests/fixtures/mirror_contract/held_past_day.json").read_text())
)
ONLY_HELD = [t for t in HELD if t.trip_id in {"h03", "h06", "h09", "h11"}]
WINS, LOSSES = [30, 20, 10, 375, 10], [30, 20, 10, 10, 10]
NOTE = (
    "The chart shows trades you closed the day you opened them. "
    "4 positions held past the day are in the figures but not drawn."
)


def figs(trips=HELD) -> dict:
    return SF.facts(SF.record_context(trips), IMP)["hold"]


def test_the_scale_stops_at_the_longest_same_day_trade():
    assert figs()["max_seconds"] == 375 * 60


def test_the_axis_on_the_page_reads_that_scale():
    assert "<span>minutes open, one dot per trade</span><span>375 min</span>" in fact_page(
        "hold", HELD
    )


def test_the_card_draws_only_same_day_trades():
    want = G.chart_hold(WINS, LOSSES, 375, SF.CARD_W, SF.CARD_H["hold"], False)
    assert figs()["chart"] == want


def test_the_mini_chart_draws_only_same_day_trades():
    want = G.chart_hold(WINS, LOSSES, 375, dial.MINI_W, dial.MINI_H, True)
    assert figs()["mini"] == want


def test_the_page_chart_draws_only_same_day_trades():
    assert figs()["page_chart"] == G.chart_hold(WINS, LOSSES, 375, SF.PAGE_W, SF.PAGE_H, False)


def test_the_fact_page_says_what_is_not_drawn():
    assert NOTE in readable(fact_page("hold", HELD))


def test_the_card_says_what_is_not_drawn():
    assert NOTE in readable(chapter_page(2, HELD))


def test_one_held_position_reads_in_the_singular():
    one = [t for t in HELD if t.trip_id not in {"h03", "h09", "h11"}]
    assert "1 position held past the day is in the figures but not drawn." in readable(
        fact_page("hold", one)
    )


def test_a_history_of_only_held_positions_draws_no_dots():
    page = readable(fact_page("hold", ONLY_HELD))
    assert "4 positions held past the day" in page
    assert figs(ONLY_HELD)["max_seconds"] == 0


def test_the_figures_still_read_the_whole_history():
    """The Mirror's sentence and table keep every trade. Only the drawing narrows."""
    f, ctx = figs(), SF.record_context(HELD)
    assert (f["winner_count"], f["loser_count"]) == (7, 7)
    assert ctx["holding"].winners_median_seconds == 30 * 60
    assert ctx["holding"].losers_median_seconds == 20 * 60


def test_with_nothing_held_the_chart_and_page_do_not_change():
    held = mx.holding_series(TRIPS)
    wins = [x / 60 for x in held.winners_seconds]
    losses = [x / 60 for x in held.losers_seconds]
    top = max([*wins, *losses, 1])
    assert figs(TRIPS)["page_chart"] == G.chart_hold(wins, losses, top, SF.PAGE_W, SF.PAGE_H, False)
    assert "not drawn" not in readable(fact_page("hold", TRIPS))
