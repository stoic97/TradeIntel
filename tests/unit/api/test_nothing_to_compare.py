"""TICKET-859: "0% against 0%" is not a finding, so it isn't drawn as one.

Rule 8: the absence of a finding is never evidence of good trading. So the line goes without
leaving an all-clear in its place, and a page too thin to say anything keeps its not-enough
state. Every file here is made up.
"""

from __future__ import annotations

import pytest

from services.production.mirror import metrics as mx
from tests.unit.api.test_math_of_trading import make, only_book
from tests.unit.api.test_scope_chapters import readable
from tests.unit.api.test_scope_facts import fact_page

LINE = "closed within 5 minutes"
NO_QUICK_CLOSES = make([100] * 15 + [-50] * 15, [10] * 30)  # 30 same-day trades, all 10 minutes
ONLY_WINNERS = make([100] * 30, [10] * 30)  # no loser to hold a share of
ONLY_LOSERS = make([-100] * 30, [10] * 30)
LEVEL = make([0] * 30, [10] * 30)
ALL_CLEARS = ("nothing wrong", "all clear", "no problem", "no issue", "looks good", "well done",
              "clean record")


@pytest.mark.parametrize("trips", [NO_QUICK_CLOSES, ONLY_WINNERS, ONLY_LOSERS],
                         ids=["none quick", "only winners", "only losers"])
def test_a_comparison_of_two_zeros_is_not_drawn(trips):
    text = readable(fact_page("math", trips))
    assert LINE not in text
    assert "0% of losers" not in text
    assert "against 0%" not in text


def test_the_note_that_explained_the_line_goes_with_it():
    assert "It says nothing about the entries." not in readable(fact_page("math", NO_QUICK_CLOSES))


@pytest.mark.parametrize(("nets", "minutes", "said"), [
    ([100] * 15 + [-50] * 15, [10] * 15 + [2] * 15, "100% of losers closed within 5 minutes, against 0% of winners."),
    ([100] * 15 + [-50] * 15, [2] * 15 + [10] * 15, "0% of losers closed within 5 minutes, against 100% of winners."),
    ([100] * 15 + [-50] * 15, [2] * 30, "100% of losers closed within 5 minutes, against 100% of winners."),
])
def test_a_comparison_with_a_side_that_isnt_zero_still_is(nets, minutes, said):
    assert said in readable(fact_page("math", make(nets, minutes)))


def test_the_rest_of_the_book_stays_when_the_line_goes():
    text = readable(fact_page("math", NO_QUICK_CLOSES))
    assert "By year" in text
    assert "Break even at a win rate of" in text


@pytest.mark.parametrize("trips", [NO_QUICK_CLOSES, ONLY_WINNERS, ONLY_LOSERS, LEVEL])
def test_hiding_it_implies_no_all_clear(trips):
    text = readable(fact_page("math", trips)).lower()
    for words in ALL_CLEARS:
        assert words not in text, words


@pytest.mark.parametrize("nets", [[100, -50], [100], [-50], [0, 0]],
                         ids=["a pair", "one winner", "one loser", "level"])
def test_a_page_too_thin_to_compare_keeps_its_not_enough_state(nets):
    text = readable(fact_page("math", make(nets)))
    assert LINE not in text
    assert "not enough trades" in text.lower()


def test_a_book_says_whether_it_has_anything_to_compare():
    assert only_book(NO_QUICK_CLOSES).quick_closes.has_a_comparison is False
    assert mx.QuickCloses(losers_percent=0, winners_percent=1).has_a_comparison is True
    assert mx.QuickCloses(losers_percent=1, winners_percent=0).has_a_comparison is True
