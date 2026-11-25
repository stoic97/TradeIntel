"""TICKET-1006, review of 24 Nov 2026 on the B1 rebuild: "too few" holds on every surface.

Under 30 in either of B1's groups the fact page already says how many there are and "too few".
The chapter's desktop wedge and the row under the phone dial must say the same, not a median.
The card's legend names the comparison group as the ruling words it, and Same way again no longer
claims to read "the same pairs" as How fast you went back in: since the ruling, back-in puts a
pair after a level trade in its comparison group, and Same way again leaves that pair out.

Every trade here is made up; the counts are worked by hand in test_back_in_b1:
PAIRS has 2 trades after a loss and 4 after a win or a level trade.
"""
from __future__ import annotations

import re
from html import unescape

import pytest

from services.production.api import scope_facts as SF
from services.production.api import scope_map as S
from tests.helpers.back_in_b1 import PAIRS, facts_of, paired
from tests.unit.api import figure_pages as P

TITLE = "How fast you went back in"


def text(html: str) -> str:
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html)).replace("\xa0", " ").split())


@pytest.fixture()
def env():
    from services.production.api.app import TEMPLATES
    return TEMPLATES.env


def test_under_thirty_the_desktop_wedge_says_the_count_and_too_few():
    view = SF.chapter_view(3, facts_of(PAIRS))
    [wedge] = [i for i in view["desktop_items"] if i["name"] == TITLE]
    assert wedge["figure"] == "2 trades"
    label = wedge["label"].replace("\n", " ")
    assert "after a loss" in label and "too few" in label, label
    assert "median" not in label and "min" not in wedge["figure"]


def test_under_thirty_the_phone_list_row_says_the_count_and_too_few(env):
    view = SF.chapter_view(3, facts_of(PAIRS))
    [row] = [r for r in view["phone_list"] if r["title"] == TITLE]
    assert str(row["said"]) == "2 trades" and "too few" in row["of"]
    html = env.from_string('{% from "_components.html" import dials %}{{ dials(view) }}').render(view=view)
    phone, desktop = html.split('<div class="scope scope--desktop">', 1)
    rows = [text(r) for r in re.findall(r'<li class="scope__list-row".*?</li>', phone, flags=re.DOTALL)]
    [said] = [r for r in rows if r.startswith(TITLE)]
    assert "2 trades" in said and "too few" in said and "median" not in said, said
    assert "median wait" not in text(desktop)


def test_at_thirty_each_the_wedge_still_gives_the_median():
    view = SF.chapter_view(3, facts_of(paired(30, 20, 10)))
    [wedge] = [i for i in view["desktop_items"] if i["name"] == TITLE]
    assert wedge["figure"] == "10 min" and "too few" not in wedge["label"]


def test_the_cards_legend_names_the_comparison_group_as_ruled(env):
    f = facts_of(paired(30, 20, 10))["back-in"]
    said = text(env.get_template("scope/cards/back-in.html").render(number=1, f=f))
    assert "After a win or a flat trade" in said, said


@pytest.fixture()
def demo():
    from fastapi.testclient import TestClient

    from services.production.api.app import create_app
    app = create_app()
    client = TestClient(app)
    P._sign_up(client, app.state.engine, "visitor")
    P._consent(client)
    client.post("/upload/demo", data={"csrf_token": P._token(client, "/upload")}, follow_redirects=False)
    return client


def test_same_way_says_its_own_pairs_not_back_ins(demo):
    said = text(demo.get(S.fact_href("same-way")).text)
    assert "The same pairs as How fast you went back in" not in said
    assert "after a flat trade are left out" in said, said
