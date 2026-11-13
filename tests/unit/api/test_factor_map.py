"""The published factor map: derived from the spec and the code, and carrying no one's results."""

from __future__ import annotations

import html
import importlib
import re

from fastapi.testclient import TestClient

from services.production.api import factor_map as FM
from services.production.api import scope_map as SM
from services.production.api import trade_list as TL
from services.production.api.app import create_app
from services.shared.prereg import reader
from tests.unit.api.test_read_again import send
from tests.unit.api.test_upload import client, engine  # noqa: F401

TIERS = ("Established", "Likely", "Exploratory")


def text(page: str) -> str:
    main = page.split("<main", 1)[1].split("</main>", 1)[0]
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", main)).split())


# ---- derived from the spec and the code, both ways

def test_every_check_in_the_framework_is_on_the_map():
    on_map = {c for f in FM.FACTORS for c in f.checks}
    assert {t.id for t in reader.load().tests} <= on_map


def test_every_trade_list_filter_is_on_the_map():
    assert {f.name for f in TL.FILTERS} <= {k for f in FM.FACTORS for k in f.filters}


def test_every_report_fact_is_on_the_map_or_says_why_not():
    mapped = {k for f in FM.FACTORS for k in f.facts}
    assert set(SM.FACTS) <= mapped | set(FM.NOT_FACTORS)
    assert not mapped & set(FM.NOT_FACTORS)


def test_the_map_names_nothing_that_no_longer_exists():
    checks = {t.id for t in reader.load().tests}
    for f in FM.FACTORS:
        assert set(f.checks) <= checks, f.name
        assert set(f.filters) <= {x.name for x in TL.FILTERS}, f.name
        assert set(f.facts) <= set(SM.FACTS), f.name
        for source in f.sources:
            importlib.import_module(source)


def test_each_factor_is_named_once():
    names = [f.name for f in FM.FACTORS]
    assert len(names) == len(set(names))


# ---- the page

def test_anyone_can_open_it(engine):  # noqa: F811
    page = TestClient(create_app()).get("/factors")
    assert page.status_code == 200
    said = text(page.text)
    for f in FM.FACTORS:
        assert f.name in said, f.name
    for family in FM.FAMILIES:
        assert family in said
    for status in FM.Status:
        assert status.value in said and FM.STATUS_MEANS[status] in said


def test_it_says_when_each_is_known(engine):  # noqa: F811
    said = text(TestClient(create_app()).get("/factors").text)
    for f in FM.FACTORS:
        assert f"{f.name} {f.known.value} {f.status.value}" in said, f.name


def test_signed_out_there_is_no_column_about_a_file(engine):  # noqa: F811
    page = TestClient(create_app()).get("/factors").text
    assert "In your file?" not in page


def test_it_carries_no_figure_from_anyones_file(client):  # noqa: F811
    """README rule 1: nothing on the published map comes from a trader's results."""
    send(client)
    for c in (TestClient(create_app()), client):
        said = text(c.get("/factors").text)
        assert "₹" not in said
        assert not re.search(r"\d+\s*%", said)
        assert not re.search(r"\b\d{2,}\b", said.replace("15 minutes", ""))


def test_a_signed_in_trader_sees_what_his_file_held_and_nothing_is_dropped(client):  # noqa: F811
    send(client)
    page = client.get("/factors").text
    assert "In your file?" in page
    said = text(page)
    for f in FM.FACTORS:
        assert f.name in said, f.name
    assert "Only you can give it" in said
    assert "Needs bars" in said
    rows = dict(re.findall(r'<tr data-factor="([^"]+)">.*?<td class="factor-map__file">([^<]+)</td>',
                           page, re.DOTALL))
    assert len(rows) == len(FM.FACTORS)
    assert rows["Hour you opened"] == "Yes"
    assert rows["Worst days"] == rows["Losing runs"] == rows["Best and worst trades"] == "Yes"
    assert rows["Your stop"] == "Only you can give it"
    assert rows["The minute before you bought"] == "Needs bars"


def test_no_page_prints_the_specs_tiers(client):  # noqa: F811
    send(client)
    paths = ["/factors", "/mirror", *(f"/mirror/chapter/{c.number}" for c in SM.CHAPTERS),
             *(f"/mirror/fact/{k}" for k in SM.FACTS)]
    for path in paths:
        said = text(client.get(path).text)
        for tier in TIERS:
            assert not re.search(rf"\b{tier}\b", said), (path, tier)


def test_the_reports_last_page_links_to_it(client):  # noqa: F811
    send(client)
    assert 'href="/factors"' in client.get("/mirror/fact/not-told").text
