"""'Where the money came from': same-day trades ranked, held positions on their own line.

[TICKET-791] Rendered through the app's templates with the hand-calculated fixture.
"""

from __future__ import annotations

import json
from pathlib import Path

from services.production.api import scope_facts as SF
from services.production.api import scope_map as S
from services.production.mirror import metrics as mx
from tests.unit.api.test_scope_chapters import IMP, TRIPS, chapter_page, readable
from tests.unit.api.test_scope_facts import fact_page

HELD = mx.load_trips(
    json.loads(Path("tests/fixtures/mirror_contract/held_past_day.json").read_text())
)
ONLY_HELD = [t for t in HELD if t.trip_id in {"h03", "h06", "h09", "h11"}]

SAME_DAY_NOTE = "The five above are trades you closed the day you opened them."
HELD_LINE = "Held past the day: 4 positions, net +₹57,500."


def body(page: str) -> str:
    """The fact's figure and table, before the list of every trade behind it."""
    return page.split('class="evidence__caption"')[0]


def test_the_fact_page_shows_held_positions_on_their_own_line():
    assert HELD_LINE in readable(fact_page("money", HELD))


def test_the_fact_page_says_the_five_are_same_day_trades():
    assert SAME_DAY_NOTE in readable(fact_page("money", HELD))


def test_a_held_position_is_not_in_the_best_or_worst_five_table():
    table = readable(fact_page("money", HELD)).split(SAME_DAY_NOTE)[0]
    assert "+₹50,000" not in table
    assert "+₹9,000" not in table
    assert "−₹800" not in table


def test_the_chapter_card_shows_the_held_line():
    assert HELD_LINE in readable(chapter_page(1, HELD))


def test_a_single_held_position_reads_in_the_singular():
    one = [t for t in HELD if t.trip_id != "h03" and t.trip_id != "h09" and t.trip_id != "h11"]
    assert "Held past the day: 1 position, net +₹50,000." in readable(fact_page("money", one))


def test_with_nothing_held_the_page_says_nothing_new():
    for page in (fact_page("money", TRIPS), chapter_page(1, TRIPS)):
        assert "Held past the day" not in readable(page)
        assert SAME_DAY_NOTE not in readable(page)


def test_every_held_position_is_listed_among_the_trades_behind_the_fact():
    """Handoff 11: a fact page lists every trade behind it, and the count matches."""
    ctx = SF.record_context(HELD)
    ids = {t.trip_id for t in S.trades_behind("money", ctx)}
    assert {"h03", "h06", "h09", "h11"} <= ids
    assert len(ids) == 14  # five best and five worst, none shared, and four held


def test_the_figure_is_the_same_day_result_not_a_count():
    """By hand in expected_held_past_day.json: the same-day trades come to +200."""
    figs = SF.facts(SF.record_context(HELD), IMP)
    assert figs["money"]["figure"] == "+₹200"


def test_a_history_of_only_held_positions_draws_no_empty_table():
    page = fact_page("money", ONLY_HELD)
    assert "Held past the day: 4 positions" in readable(page)
    assert "Best five" not in body(page)
    assert SAME_DAY_NOTE not in readable(page)
