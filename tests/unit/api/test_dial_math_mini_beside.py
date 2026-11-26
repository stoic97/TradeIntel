"""The wins mini's spoken line reads its rate beside the break-even (TICKET-1036, with 1041's rule).

Two rates that print the same whole number but differ must not read as equal: 45.3 against a
break-even of 45.0 says "45.3 of 100" and "45.0 of 100", not "45 of 100" twice.
"""
from types import SimpleNamespace

from services.production.api import scope_facts as SF


def _ctx(rate, even):
    return {"strike": SimpleNamespace(rate_percent=rate), "break_even": SimpleNamespace(percent=even)}


def test_a_near_tie_shows_one_decimal_on_both():
    _, said = SF._mini("math", _ctx(45.3, 45.0), None)
    assert said == "45.3 of 100 trades made money; break-even at 45.0 of 100."


def test_apart_rates_stay_whole():
    _, said = SF._mini("math", _ctx(46, 51), None)
    assert said == "46 of 100 trades made money; break-even at 51 of 100."
