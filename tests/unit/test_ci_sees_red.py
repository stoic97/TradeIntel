"""Throwaway (TICKET-928 gate 1): a deliberately failing test, to see CI go red. Never merge."""


def test_ci_goes_red_on_a_failing_test():
    assert 1 + 1 == 3, "deliberate: CI must show this run red"
