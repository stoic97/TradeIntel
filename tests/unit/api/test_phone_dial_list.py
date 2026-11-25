"""TICKET-1002: on a phone a chapter's dial keeps the wedges it has on main; a fact added after it
sits in a list directly under the dial. On desktop every fact keeps its wedge.

The kit sized a wedge's contents for the facts it had: a fourth wedge in chapter 1 or 2, or a
third in chapter 3, runs past its edge at 390 px. So each fact says once whether it sits on the
phone dial (``scope_map.Fact.on_phone_dial``), and a list under the dial carries the others in
the desktop wedge's own words: its figure and noun, what the figure is of, and a link to the
fact page. Every dial main draws today is drawn byte for byte: the hashes below were taken on
main before this change.
"""

from __future__ import annotations

import dataclasses
import hashlib
import re
from html import unescape
from pathlib import Path

import pytest

from services.production.api import dial as D
from services.production.api import glossary as GL
from services.production.api import scope_facts as SF
from services.production.api import scope_geometry as G
from services.production.api import scope_map as S
from tests.helpers.hub_answers import CTX
from tests.helpers.scope_chapters import IMP
from tests.unit.api import figure_pages as P

PAGES = ("/mirror", "/mirror/chapter/1", "/mirror/chapter/2", "/mirror/chapter/3", "/mirror/chapter/4")
FIT_ON_A_PHONE = -13  # the layout's own limit, as test_dial_states_facts holds every dial to it


@pytest.fixture()
def pages():
    """Every page with a dial, on the demo upload, as a visitor reads it."""
    from fastapi.testclient import TestClient

    from services.production.api.app import create_app
    app = create_app()
    client = TestClient(app)
    P._sign_up(client, app.state.engine, "visitor")
    P._consent(client)
    client.post("/upload/demo", data={"csrf_token": P._token(client, "/upload")}, follow_redirects=False)
    return {path: client.get(path).text for path in PAGES}


def dials(html: str) -> list[str]:
    return re.findall(r'<div class="scope[^"]*">.*?</svg>', html, flags=re.DOTALL)

# Every dial on the demo pages, phone then desktop, as main drew them before TICKET-1002, with
# the minis TICKET-1036 redrew at 72 x 20.
ON_MAIN = {
    "/mirror": ["fa7d719b955808e3c9da6b533b6c403dde84210658e45f79efadc45c1622141b",
                "f387c5dc0c65eaaea514f4aa900d6f50fe593661d4d7a4a30e0ff81b8c4de3df"],
    # Dial minis (1036) on every wedge; chapter 3's desktop dial also carries main's After you closed.
    "/mirror/chapter/1": ["dac37b9a4a2eb63750ccff6f9babccf495fd67a0299d9c352f82bcdb62d4528e",
                          "d765b662af7467f0834dc85cae0bc8b2921ed54712d9301e673cbd36c375201c"],
    "/mirror/chapter/2": ["0e9f0fe19966a88147f653511fc3dc4097125f01b9e713035631d99edbad8169",
                          "95c287111cf66a9ad80f493e1217838115c3695c14f5ffa7d2636b78c9856bac"],
    "/mirror/chapter/3": ["461efffc445d451f37c72f3b1d8101ac4b15205bbbcb279c07044d035972a13e",
                          "6c2e142e84115a159c3c4404f5c4c8f5ce1296e4cf08e1de6bbb90017fda965f"],
    "/mirror/chapter/4": ["c1e506fcfa77485e7d82e87d3b63c461ba3db7e8339b3d1cf47143fc20e7a6d3",
                          "f27265173a763ba6714eaf862faaf4ec3788090d7645311a1b2556fa5b34ce7b"],
}
CHAPTERS_ON_MAIN = {
    (1, "phone"): "4b3c47e18100e8edf49dbf6e511b2d97e18b41a93fa592bd1bb0895ac980b20a",
    (1, "desktop"): "6a629f9f0e3b69ec4e37da477b54e0cec0bf0d9874d43798cfed20d21e4704b9",
    (2, "phone"): "931aa33f58d216b255557bb54a897b47f3d26c8a5ba69a2ba4e8e3ac587622ab",
    (2, "desktop"): "0c7ee0b8895cff7363196ac50e73f43624f2ad28797586055603096f22c45beb",
    (3, "phone"): "1a8dc2d67ff6e8570a6b50557c1ebb1de57e799742c5a6bc97f8699c6f04b63c",
    (3, "desktop"): "1ec81fa1bdbbbb702f980315493e672351b814ba36b28f8fe9515e74e1d73c81",
    (4, "phone"): "1dec31d1bc2c5b813c04b4be1ab50920e7c56c53aae7e35c2a4b9c40f4dd6340",
    (4, "desktop"): "255024f97536e6f44aaa175af79421bc03af6c9ebede556ba6159e68704a4196",
}

# The facts allowed on a phone dial: those main has. A fact added later must decide: join this
# list on purpose, or set on_phone_dial=False and sit in the list under the dial.
ON_THE_PHONE_DIAL = {"hidden", "worst-days", "money", "math", "run", "clock", "down", "busiest",
                     "unread", "risk", "not-told"}
OFF_THE_PHONE_DIAL = {"back-in", "same-way", "next-day",  # What you do next (1006)
                      "after-close"}  # After you closed: added after the phone dial was sized


def sha(text) -> str:
    return hashlib.sha256(str(text).encode()).hexdigest()


def slices(svg: str) -> list[str]:
    return re.findall(r'<a class="scope__slice.*?</a>', svg, flags=re.DOTALL)


# A fact added after the dial (made up for the test): chapter 2 with a fourth fact, off the phone dial.
LATER = S.Fact("down", "After two straight losses", "down", on_phone_dial=False)


@pytest.fixture()
def later(monkeypatch):
    two = S.CHAPTERS[1]
    chapters = (S.CHAPTERS[0], dataclasses.replace(two, facts=(*two.facts, LATER)), *S.CHAPTERS[2:])
    monkeypatch.setattr(S, "CHAPTERS", chapters)
    return SF.chapter_view(2, SF.facts(CTX, IMP))


# ---------- decided once, per fact ----------

def test_every_fact_says_whether_it_sits_on_the_phone_dial():
    assert {f.key for c in S.CHAPTERS for f in c.facts if f.on_phone_dial} == ON_THE_PHONE_DIAL
    # every fact on main stays on it; the facts added since sit in the list under the dial
    assert {f.key for c in S.CHAPTERS for f in c.facts if not f.on_phone_dial} == OFF_THE_PHONE_DIAL


# ---------- nothing else moves ----------

def test_every_dial_on_the_pages_is_drawn_as_on_main(pages):
    for path, html in pages.items():
        assert [sha(s) for s in dials(html)] == ON_MAIN[path], path


def test_every_chapter_dial_is_drawn_as_on_main():
    figs = SF.facts(CTX, IMP)
    for (n, size), digest in CHAPTERS_ON_MAIN.items():
        assert sha(D.scope_dial(SF.chapter_view(n, figs), size)) == digest, (n, size)


def test_a_chapter_with_every_fact_on_its_dial_has_no_list(pages):
    for path, html in pages.items():
        if path == "/mirror/chapter/3":  # What you do next (1006) sits in chapter 3's list
            continue
        assert "scope__list" not in html, path


# ---------- a fact off the phone dial ----------

def test_the_phone_dial_leaves_it_out_and_the_desktop_dial_keeps_it(later):
    phone, desk = str(D.scope_dial(later, "phone")), str(D.scope_dial(later, "desktop"))
    assert len(slices(phone)) == 3 and len(slices(desk)) == 4
    assert 'aria-label="After two straight losses.' not in phone
    assert 'aria-label="After two straight losses.' in desk
    assert sha(phone) == CHAPTERS_ON_MAIN[(2, "phone")]  # the phone dial is today's, byte for byte


def test_the_desktop_keeps_chapter_order_and_clears(later):
    assert [i["name"] for i in later["desktop_items"]] == [f.title for f in S.CHAPTERS[1].facts]
    z = G.SIZES["desktop"]
    rr = G.radii(z["R"])
    items = later["desktop_items"]
    sec = G.sectors(len(items), False)
    lay = G.layout_contents(items, sec, rr, z["figSizesChapter"])
    for i, b in enumerate(lay["blocks"]):
        assert G.block_clearance(sec["slices"][i], sec["span"], lay["radius"][i], b, rr) >= FIT_ON_A_PHONE


def test_the_phone_dial_still_clears(later):
    z = G.SIZES["phone"]
    rr = G.radii(z["R"])
    items = [{**i, "figure": i.get("phone_figure", i["figure"]),  # as the phone clearance test reads them
              "label": i.get("phone_label", i.get("label", ""))} for i in later["items"]]
    assert len(items) == 3
    items = D.fitted(items, z["figSizesChapter"])  # each mini as wide as its wedge clears (TICKET-1036)
    sec = G.sectors(len(items), False)
    lay = G.layout_contents(items, sec, rr, z["figSizesChapter"])
    for i, b in enumerate(lay["blocks"]):
        assert G.block_clearance(sec["slices"][i], sec["span"], lay["radius"][i], b, rr) >= FIT_ON_A_PHONE


def test_the_list_row_says_what_the_desktop_wedge_says_and_opens_the_fact(later):
    [row] = later["phone_list"]
    [wedge] = [i for i in later["desktop_items"] if i["name"] == LATER.title]
    assert row["title"] == LATER.title and row["href"] == S.fact_href("down")
    assert str(row["said"]) == wedge["figure"]
    assert row["of"] == wedge["label"].replace("\n", " ")
    assert row["finding"] is SF.facts(CTX, IMP)["down"]["finding"]


@pytest.fixture()
def client_env():
    """The app's own template environment: its filters, its Figure, its dial."""
    from services.production.api.app import TEMPLATES
    return TEMPLATES.env


def test_the_list_sits_inside_the_phone_dial_and_holds_to_880s_rule(later, client_env):
    html = client_env.from_string('{% from "_components.html" import dials %}{{ dials(view) }}').render(view=later)
    phone, desktop = html.split('<div class="scope scope--desktop">', 1)
    assert "scope__list" in phone and "scope__list" not in desktop
    rows = re.findall(r'<li class="scope__list-row".*?</li>', phone, flags=re.DOTALL)
    assert len(rows) == 1
    row = rows[0]
    assert f'href="{S.fact_href("down")}"' in row and "<script" not in html
    assert 'data-known="AT_CLICK"' in row and 'data-rung="SEEN"' in row
    said = " ".join(unescape(re.sub(r"<[^>]+>", " ", row)).replace("\xa0", " ").split())
    words = said.removeprefix(LATER.title).split()
    assert len(words) >= 3, said
    assert set(re.findall(r"[a-z]+", " ".join(words).lower())) & GL.nouns(), said


def test_a_fact_with_too_few_trades_says_so_in_the_list(later, client_env):
    rows = [{**later["phone_list"][0], "state": "not-enough"}]
    html = client_env.from_string('{% from "_components.html" import dial %}{{ dial(view) }}').render(
        view={**later, "phone_list": rows})
    assert "Not enough trades yet." in html


def test_a_row_is_a_tap_target_of_44_px():
    css = Path("services/production/api/static/css/app.css").read_text(encoding="utf-8")
    rule = re.search(r"\.scope__list-row a[^{]*\{([^}]*)\}", css)
    assert rule and "min-height: 44px" in rule.group(1)
