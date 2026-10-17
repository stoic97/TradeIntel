"""The B2 condition, called the way the Mirror calls it.

PRD v1.2 section 6.3: the Mirror's "trading on after two straight losses" is the
research library's B2 condition by construction -- one definition, one function.
These cases come from definitions_v1.md section 2 and Appendix A, hand-written from
the rule, never from program output.

The Mirror passes net rupees where the research library passes R. The function reads
only the sign, so the last test asserts the two call paths agree on the same trips.
"""

from __future__ import annotations

from services.research.library import b2 as research_b2
from services.shared.conditions.b2_condition import Obs, population_and_condition


def trips(*specs: tuple[int, float, float, float]) -> list[Obs]:
    """(day, entry, exit, result) tuples, in the order a caller would pass them."""
    return [Obs(day=d, entry_at=en, exit_at=ex, r=r) for d, en, ex, r in specs]


def test_fewer_than_two_resolved_priors_is_outside_the_population():
    obs = trips((1, 0, 1, -5.0), (1, 2, 3, -5.0))
    in_pop, cond = population_and_condition(obs)
    assert list(in_pop) == [False, False]
    assert list(cond) == [False, False]


def test_two_losses_then_a_trade_is_in_the_condition():
    obs = trips((1, 0, 1, -5.0), (1, 2, 3, -5.0), (1, 4, 5, 9.0))
    in_pop, cond = population_and_condition(obs)
    assert list(in_pop) == [False, False, True]
    assert list(cond) == [False, False, True]


def test_two_losses_then_a_win_then_a_trade_is_not_in_the_condition():
    obs = trips((1, 0, 1, -5.0), (1, 2, 3, -5.0), (1, 4, 5, 7.0), (1, 6, 7, -2.0))
    in_pop, cond = population_and_condition(obs)
    assert list(in_pop) == [False, False, True, True]
    assert list(cond) == [False, False, True, False]


def test_a_scratch_trade_between_two_losses_breaks_the_run():
    """Appendix A: net = 0 among the two most recent breaks the run.

    Trip 3's two most recent resolved priors are the scratch and the first loss, so it
    is not in the condition. Trip 4's are the second loss and the scratch -- also not.
    A scratch between two losses therefore suppresses the condition for both trades
    that follow it, which is the point of the rule.
    """
    obs = trips((1, 0, 1, -5.0), (1, 2, 3, 0.0), (1, 4, 5, -5.0), (1, 6, 7, -1.0))
    in_pop, cond = population_and_condition(obs)
    assert list(in_pop) == [False, False, True, True]
    assert list(cond) == [False, False, False, False]


def test_an_overlapping_trip_is_not_resolved():
    # The third trip's two priors are open at its entry: one exits later, one much later.
    obs = trips((1, 0, 9, -5.0), (1, 1, 8, -5.0), (1, 2, 3, -1.0))
    in_pop, _cond = population_and_condition(obs)
    assert list(in_pop) == [False, False, False]


def test_losses_do_not_carry_across_the_day_boundary():
    obs = trips((1, 0, 1, -5.0), (1, 2, 3, -5.0), (2, 4, 5, -1.0), (2, 6, 7, -1.0))
    in_pop, _cond = population_and_condition(obs)
    assert list(in_pop) == [False, False, False, False]


def test_the_mirror_path_and_the_research_path_agree_on_the_same_trips():
    """Net rupees and R differ in scale; the condition reads only the sign."""
    in_r = trips((1, 0, 1, -0.8), (1, 2, 3, -1.2), (1, 4, 5, 0.5), (1, 6, 7, -0.3))
    in_rupees = trips((1, 0, 1, -2400.0), (1, 2, 3, -3600.0), (1, 4, 5, 1500.0), (1, 6, 7, -900.0))

    pop_r, cond_r = population_and_condition(in_r)
    pop_rupees, cond_rupees = population_and_condition(in_rupees)

    assert list(pop_r) == list(pop_rupees)
    assert list(cond_r) == list(cond_rupees)
    assert list(cond_r) == [False, False, True, False]


def test_the_research_module_still_exports_the_same_function():
    assert research_b2.population_and_condition is population_and_condition
    assert research_b2.Obs is Obs
