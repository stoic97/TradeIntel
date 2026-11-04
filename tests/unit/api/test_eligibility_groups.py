"""What we can check, grouped by what is missing, for a trader [TICKET-829].

The page keeps the honesty and changes the audience. Above the "For the curious" toggle
a trader reads counts by what each group waits on; identifiers, minimums and framework
versions sit inside it. Neither part says what a check asks: that would be telling him
what it would say.
"""

from __future__ import annotations

import dataclasses
import html
import re
import types

import pytest

from services.production.eligibility import assess as el
from services.shared.prereg import reader
from tests.unit.api.templating import template_env
from tests.unit.api.test_eligibility_page import client, engine  # noqa: F401

NS = types.SimpleNamespace


def result(enough=0, short=0, undetermined=0, **waiting) -> NS:
    def verdicts(state, n):
        return [NS(test=NS(id=f"X{i}"), state=NS(value=state), reason="r", need=1,
                   unit=NS(value="trips")) for i in range(n)]
    short_ = verdicts("insufficient_sample", short)
    waiting_ = verdicts("required_data_missing", sum(waiting.values()))
    return NS(total=19, enough=verdicts("enough", enough), short=short_, waiting=waiting_,
              undetermined=verdicts("undetermined", undetermined),
              blocked=short_ + waiting_, waiting_counts=dict(waiting))


def render(res: NS, draft: bool = True) -> str:
    return template_env().get_template("eligibility.html").render(
        title="What we can check", result=res, trips=40, days=8, csrf_token="x",
        framework=NS(version="9.9.9"), draft=draft)


def column(page: str) -> str:
    return page.split("<main", 1)[1].split("</main>", 1)[0]


def main_part(page: str) -> str:
    """The main column as a trader reads it without opening the toggle."""
    before, _, rest = column(page).partition("<details")
    assert rest, "the page has no toggle"
    return before + rest.split("</details>", 1)[1]


def toggle_part(page: str) -> str:
    return page.split("<details", 1)[1].split("</details>", 1)[0]


def text(page: str) -> str:
    return html.unescape(" ".join(re.sub(r"<[^>]+>", " ", page).split()))


def test_the_library_sorts_into_what_each_check_waits_on():
    """Read by hand from framework_v1.yaml: R8 and S5 on regimes, R7 on stops, E2 and
    E4p on ticks, S10 on events. The trades do not matter to any of them."""
    assert el.assess([]).waiting_counts == {
        "market_context": 2, "stop": 1, "finer_prices": 2, "release_calendar": 1,
    }


def test_each_verdict_keeps_the_reason_it_had():
    verdicts = {v.test.id: v for v in el.assess([]).verdicts}
    assert "TD-003" in verdicts["R7"].reason
    assert "TD-004" in verdicts["E2"].reason
    assert "TD-011" in verdicts["S5"].reason
    assert "TD-014" in verdicts["S10"].reason


def test_a_group_nothing_waits_on_is_not_counted():
    framework = reader.load()
    only_b1 = dataclasses.replace(
        framework, tests=tuple(t for t in framework.tests if t.id == "B1"))
    assert el.assess([], only_b1).waiting_counts == {}


@pytest.mark.parametrize(("on", "line"), [
    ("market_context", "Waiting on market context (2 checks)."),
    ("stop", "Waiting on the stop you used (2 checks): you can help: answer "
             "'Where was your stop?' in your journals."),
    ("finer_prices", "Waiting on finer prices (2 checks)."),
    ("release_calendar", "Waiting on a calendar of news releases (2 checks)."),
])
def test_each_thing_a_check_waits_on_has_its_line(on, line):
    assert line in text(main_part(render(result(**{on: 2}))))


def test_every_waiting_kind_is_a_line_on_the_page():
    """A new kind added to assess.py must not draw an empty line."""
    for kind in el.Waiting:
        assert "Waiting on" in text(main_part(render(result(**{kind.value: 1}))))


def test_one_check_is_written_as_one():
    page = text(main_part(render(result(enough=1, short=1, undetermined=1, finer_prices=1))))
    assert "Ready: 1 check has enough of your trades." in page
    assert "Not enough history yet (1 check)." in page
    assert "Waiting on finer prices (1 check)." in page
    assert "We cannot tell from here (1 check)." in page


def test_ready_counts_the_checks_with_enough():
    page = text(main_part(render(result(enough=7))))
    assert "Ready: 7 checks have enough of your trades." in page


def test_a_group_with_nothing_in_it_has_no_line():
    page = text(main_part(render(result(enough=0, short=0, undetermined=0, stop=1))))
    assert "Ready:" not in page
    assert "Not enough history yet" not in page
    assert "We cannot tell from here" not in page
    assert "market context" not in page


def test_you_can_help_goes_to_the_journals_and_promises_nothing():
    """FB-0110 is unruled: the line may show, but answers are not said to feed a check."""
    page = main_part(render(result(stop=1)))
    assert '<a class="link" href="/journals">your journals</a>' in page
    for promise in ("feed", "unlock", "will run", "so we can", "once you"):
        assert promise not in page.lower(), promise


def test_the_toggle_is_called_for_the_curious():
    page = render(result(enough=1))
    assert re.search(r"<summary[^>]*>\s*For the curious\s*</summary>", page)


def test_identifiers_and_the_framework_version_are_inside_the_toggle(client):  # noqa: F811
    page = client.get("/eligibility").text
    inside, outside = toggle_part(page), main_part(page)
    framework = reader.load()
    for test in framework.tests:
        assert f">{test.id}<" in inside, test.id
        assert f">{test.id}<" not in outside, test.id
    assert framework.version in text(inside)
    assert framework.version not in text(outside)


def test_the_research_teams_words_are_not_outside_the_toggle(client):  # noqa: F811
    outside = text(main_part(client.get("/eligibility").text))
    for word in ("TD-0", "framework", "/bucket", "/cell", "Trips", " trips", "engine's count"):
        assert word not in outside, word


def test_neither_part_says_what_a_check_asks(client):  # noqa: F811
    page = column(client.get("/eligibility").text).lower()
    for test in reader.load().tests:
        for name in (test.title, test.question):
            assert name.lower() not in page, name


def test_the_page_says_why_it_does_not_say(client):  # noqa: F811
    outside = text(main_part(client.get("/eligibility").text))
    assert "We do not say here what each check asks." in outside
    assert "would be telling you what they would say." in outside


def test_a_draft_says_so_without_opening_the_toggle():
    line = "What counts as enough is written down but not yet fixed"
    assert line in text(main_part(render(result(enough=1), draft=True)))
    assert line not in text(main_part(render(result(enough=1), draft=False)))
