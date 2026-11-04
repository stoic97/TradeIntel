"""The upload page says which broker works and how to get the file [TICKET-829].

A trader cannot find "the trade-level export" from that phrase. The steps name the
export the way the broker does, the same names a rejection gives him (dhan_filemap.yaml),
and show the shape of the file name so he can tell he has the right one.
"""

from __future__ import annotations

import html
import re

from services.production.ctr.intake import outcomes
from tests.unit.api.templating import template_env


def page() -> str:
    return template_env().get_template("upload.html").render(
        title="Upload your tradebook", csrf_token="x", error=None, today="2026-09-08",
    )


def idle_part() -> str:
    return page().split('class="upload__idle"', 1)[1].split('class="upload__reading"', 1)[0]


def steps() -> list[str]:
    listed = re.search(r'<ol class="upload__steps[^"]*">(.*?)</ol>', idle_part(), re.S)
    assert listed, "the page has no list of steps"
    items = re.findall(r"<li>(.*?)</li>", listed[1], re.S)
    return [html.unescape(" ".join(re.sub(r"<[^>]+>", " ", i).split())) for i in items]


def test_it_says_which_brokers_work():
    assert "Works with: Dhan (more coming)" in idle_part()


def test_there_are_three_steps():
    assert len(steps()) == 3


def test_the_steps_use_the_names_a_rejection_gives():
    """Two copies drift: the export's name and place are the broker map's."""
    wanted = outcomes.ADAPTERS[0].file_map().wanted
    assert wanted.broker_name in steps()[0]
    assert wanted.where_it_lives in steps()[0]


def test_the_last_step_shows_the_file_name_shape():
    assert "TRADE_HISTORY_CSV_<client>_<from>_<to>" in steps()[2]


def test_the_steps_come_before_the_form():
    assert idle_part().index("upload__steps") < idle_part().index("<form")


def test_the_existing_description_of_the_file_stays():
    assert "The trade-level export from your broker" in idle_part()
    assert "Not the profit-and-loss statement." in idle_part()


def test_the_reading_state_does_not_repeat_the_steps():
    assert "upload__steps" not in page().split('class="upload__reading"', 1)[1]
