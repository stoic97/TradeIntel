"""Chapter 2 reads same-day trades only, in both its hold and its clock [TICKET-792].

Two charts were showing investing while claiming to show trading. Worked by hand from
held_past_day.json:
  same-day winners, minutes: 30, 20, 10, 375, 10, sorted 10, 10, 20, 30, 375, median 20
  same-day losers, minutes: 30, 20, 10, 10, 10, sorted 10, 10, 10, 20, 30, median 10
  so a ratio of 2.0, over five winners and five losers. The clock is covered in
  test_clock_same_day.py; here it is checked on the overview, beside the hold.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from services.production.api import scope_facts as SF
from services.production.api import scope_map as S
from services.production.mirror import metrics as mx
from tests.unit.api.test_scope_chapters import IMP, chapter_page, readable
from tests.unit.api.test_scope_facts import fact_page

HELD = mx.load_trips(
    json.loads(Path("tests/fixtures/mirror_contract/held_past_day.json").read_text())
)
HELD_IDS = {"h03", "h06", "h09", "h11"}
ONLY_HELD = [t for t in HELD if t.trip_id in HELD_IDS]
ONE_SIDED = [t for t in HELD if t.is_win and t.trip_id not in HELD_IDS]
NOTE = (
    "These are trades you closed the day you opened them. "
    "4 positions held past the day are not counted here."
)


def facts(trips=HELD) -> dict:
    return SF.facts(SF.record_context(trips), IMP)


def test_the_medians_read_same_day_trades():
    h = SF.record_context(HELD)["holding"]
    assert (h.winners_median_seconds, h.losers_median_seconds) == (20 * 60, 10 * 60)
    assert h.ratio == Decimal("2.0")


def test_the_figure_reads_those_medians():
    assert facts()["hold"]["figure"] == "20 · 10 min"


def test_the_table_counts_same_day_trades():
    f = facts()["hold"]
    assert (f["winner_count"], f["loser_count"]) == (5, 5)


def test_the_trades_listed_are_the_trades_counted():
    ids = {t.trip_id for t in S.trades_behind("hold", SF.record_context(HELD))}
    assert not ids & HELD_IDS
    assert len(ids) == 10


def test_both_cards_count_the_same_trades():
    figs = facts()
    assert figs["hold"]["trade_count"] == figs["clock"]["trade_count"] == 10


def test_the_overview_draws_no_holding_in_either():
    page = readable(chapter_page(2, HELD))
    assert "375 min" in page
    assert "525600" not in page and "5,25,600" not in page
    assert page.count(NOTE) == 2


def test_the_fact_page_says_what_is_left_out():
    assert NOTE in readable(fact_page("hold", HELD))


def test_a_history_of_only_held_positions_says_not_enough():
    f = facts(ONLY_HELD)["hold"]
    assert f["state"] == "not-enough"
    assert f["figure"] == "—"


def test_that_history_still_renders():
    for page in (fact_page("hold", ONLY_HELD), chapter_page(2, ONLY_HELD)):
        assert "None" not in readable(page)


def test_same_day_winners_with_no_loser_say_not_enough():
    assert facts(ONE_SIDED)["hold"]["state"] == "not-enough"
    assert "None" not in readable(fact_page("hold", ONE_SIDED))
