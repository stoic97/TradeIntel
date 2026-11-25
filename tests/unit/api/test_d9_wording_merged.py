"""TICKET-1081: the D9 copy table of 24 Nov 2026, on the surfaces already merged.

The wins chart's legend is not here: its words were ruled in TICKET-1032's review, so that row
waits on the copy owner rather than being changed ahead of him.

Each sentence is read on the rendered page (or the rendered dial and card), in the words the
table proposes for the copy owner's signature: plain words, the trades each figure counts named.
"""
from __future__ import annotations

import re
from html import unescape

import pytest

from services.production.api import scope_facts as SF
from services.production.api import scope_map as S
from tests.helpers.back_in_b1 import PAIRS, facts_of, paired
from tests.unit.api import figure_pages as P

BACK_IN = "How fast you went back in"


def text(html: str) -> str:
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html)).replace("\xa0", " ").split())


@pytest.fixture()
def env():
    from services.production.api.app import TEMPLATES
    return TEMPLATES.env


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


def test_the_dense_list_names_the_prices_it_folds(demo):
    html = demo.get("/mirror/fact/risk/trades").text
    assert "<summary>Entry and exit prices</summary>" in html
    assert "<summary>Prices</summary>" not in html



def test_back_in_says_flat_not_level(demo, env):
    said = text(demo.get(S.fact_href("back-in")).text)
    assert "after a win or a flat trade" in said.lower()
    assert "level trade" not in said.lower()
    card = text(env.get_template("scope/cards/back-in.html").render(number=1, f=facts_of(paired(30, 20, 10))["back-in"]))
    assert "After a win or a flat trade" in card and "level trade" not in card.lower()


def test_under_thirty_the_wedge_says_what_is_too_few_and_what_it_needs():
    view = SF.chapter_view(3, facts_of(PAIRS))
    [wedge] = [i for i in view["desktop_items"] if i["name"] == BACK_IN]
    assert wedge["label"].replace("\n", " ") == "after a loss, too few (needs 30)"


def test_same_way_says_its_pairs_in_plain_sentences(demo):
    said = text(demo.get(S.fact_href("same-way")).text)
    assert ("Each trade is paired with the last trade that closed before it on the same day. Pairs after "
            "a flat trade are left out. A bought call and a sold put gain when the underlying rises; a "
            "bought put and a sold call gain when it falls.") in said, said


def _one_day_trip():
    from datetime import datetime, timedelta
    from decimal import Decimal

    from services.production.mirror import metrics as mx
    from services.shared.schemas import scope_v1 as sv
    entry = datetime.fromisoformat("2026-01-05T10:00:00+05:30")
    return mx.Trip("2026-01-05-x", "CRUDEOIL", "2026-01-05", entry, entry + timedelta(minutes=10), 600,
                   Decimal(-600), 1, sv.RiskUnitSourceV1.PREMIUM_PAID, is_option=True, lines=())


def test_a_one_day_record_reads_your_only_trading_day():
    from tests.helpers.reveal_page import reveal
    from tests.helpers.scope_chapters import readable
    said = readable(reveal([_one_day_trip()]))
    assert "Your only trading day" in said and "Your one trading day" not in said
