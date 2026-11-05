"""A group of checks with none in it is not drawn [TICKET-809].

An empty table under a heading reads as something missing, when it is something that does
not apply. The sentence above the tables still gives every count, including a zero.
"""

from __future__ import annotations

from types import SimpleNamespace

from tests.unit.api.templating import template_env

NOT_ENOUGH = "Not enough history yet"
WAITING = "Waiting on something that is not your trades"


def verdict(state: str, check: str = "B2") -> SimpleNamespace:
    return SimpleNamespace(
        test=SimpleNamespace(id=check),
        state=SimpleNamespace(value=state),
        reason="a reason",
    )


def page(*blocked: SimpleNamespace) -> str:
    short = [v for v in blocked if v.state.value == "insufficient_sample"]
    waiting = [v for v in blocked if v.state.value == "required_data_missing"]
    result = SimpleNamespace(total=19, enough=[], short=short, waiting=waiting,
                             blocked=list(blocked), undetermined=[],
                             waiting_counts={"finer_prices": len(waiting)} if waiting else {})
    return template_env().get_template("eligibility.html").render(
        title="What we can check", result=result, trips=40, days=8, csrf_token="x",
        framework=SimpleNamespace(version="1.0.0"), draft=True,
    )


def test_a_group_with_no_rows_is_not_drawn():
    assert NOT_ENOUGH not in page(verdict("required_data_missing"))


def test_a_group_with_rows_is_drawn_with_them():
    html = page(verdict("insufficient_sample", "S9"))
    assert NOT_ENOUGH in html and "<td>S9</td>" in html


def test_the_waiting_group_follows_the_same_rule():
    assert WAITING not in page(verdict("insufficient_sample"))
    assert WAITING in page(verdict("required_data_missing"))


def test_with_nothing_blocked_neither_table_is_drawn():
    html = page()
    assert NOT_ENOUGH not in html and WAITING not in html
