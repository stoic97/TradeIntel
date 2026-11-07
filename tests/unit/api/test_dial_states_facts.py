"""TICKET-880: cover a wedge's rim label, read it aloud, and it still states a fact.

Rendered on the demo file: every dial a trader meets, at the phone's and the desktop's size,
read from the SVG that is drawn rather than from the values behind it.
"""

from __future__ import annotations

import re
from html import unescape

import pytest
from fastapi.testclient import TestClient

from services.production.api import dial as D
from services.production.api import formatting
from services.production.api import glossary as GL
from services.production.api import scope_facts as SF
from services.production.api import scope_geometry as G
from services.production.api.app import create_app
from services.production.api.figures import Figure
from tests.unit.api import figure_pages as P

PAGES = ("/mirror", "/mirror/chapter/1", "/mirror/chapter/2", "/mirror/chapter/3", "/mirror/chapter/4")
SIZES = {"scope ": "phone", "scope scope--desktop": "desktop"}
FIT_ON_A_PHONE = -13  # the tightest here, seen in a browser: nothing hidden


@pytest.fixture()
def pages():
    app = create_app()
    client = TestClient(app)
    P._sign_up(client, app.state.engine, "visitor")
    P._consent(client)
    client.post("/upload/demo", data={"csrf_token": P._token(client, "/upload")},
                follow_redirects=False)
    return {path: client.get(path).text for path in PAGES}


def dials(html: str) -> list[str]:
    return re.findall(r'<div class="scope[^"]*">.*?</svg>', html, flags=re.DOTALL)


def wedge_texts(svg: str) -> list[str]:
    """What each wedge says, with no rim label: the figure and the lines under it."""
    out = []
    for block in re.findall(r'<a class="scope__slice.*?</a>', svg, flags=re.DOTALL):
        said = re.findall(r'<text class="scope__figure[^"]*"[^>]*>(.*?)</text>', block, flags=re.DOTALL)
        said = [re.sub(r"<[^>]+>", " ", s) for s in said]
        out.append(" ".join(unescape(" ".join(said)).replace("\xa0", " ").split()))
    return out


def every_wedge(pages) -> list[tuple[str, str]]:
    """A slice with nothing counted from the file says "not in your file" instead: left out."""
    return [(path, said) for path, html in pages.items() for svg in dials(html)
            for said in wedge_texts(svg) if said != "—"]


def test_the_walk_reads_both_sizes_of_every_dial(pages):
    for path, html in pages.items():
        assert len(dials(html)) == 2, path
    assert len(every_wedge(pages)) >= 2 * (4 + 2 + 3 + 2 + 2)


def test_every_wedge_says_a_noun_from_the_glossary(pages):
    nouns = GL.nouns()
    for path, said in every_wedge(pages):
        words = set(re.findall(r"[a-z]+", said.lower()))
        assert words & nouns, (path, said)


def test_no_wedge_is_a_bare_adjective_or_a_bare_number(pages):
    for path, said in every_wedge(pages):
        assert len(said.split()) >= 3, (path, said)


def test_the_retired_words_are_gone_from_every_dial(pages):
    for path, said in every_wedge(pages):
        for entry in GL.retired(GL.DIAL):
            assert entry.word not in said.lower(), (path, said, entry.word)


def test_the_glossary_says_what_replaced_each_retired_word():
    entries = GL.retired(GL.DIAL)
    assert {e.word for e in entries} >= {"strike", "uncapped"}
    assert all(e.replaced_by for e in entries)


def test_a_glossary_entry_is_one_line_to_add():
    assert GL.Entry("trip", GL.RETIRED, "trade", "journal").word == "trip"


def hub_items(trips, number=None):
    from tests.unit.api.test_hub_answers import IMP

    return SF.home_view(SF.record_context(trips), IMP, number=number)["items"]


def test_the_agreed_wording_on_the_desktop_dial():
    from tests.unit.api.test_hub_answers import CTX, FORTY

    words = [f"{i['figure']} {i['label']}".replace("\n", " ") for i in hub_items(FORTY)[:3]]
    assert words[0] == f"5 days lost {CTX['share'].share_percent}% of all you lost"
    assert words[1].endswith("of 100 trades made money")
    assert words[2].endswith("trades on your busiest day")


def test_a_uncapped_wedge_reads_as_agreed():
    from tests.unit.api.test_hub_answers import FORTY, mx

    trips = [mx.replace(x, uncapped=True) if i < 3 else x for i, x in enumerate(FORTY)]
    item = hub_items(trips)[3]
    assert f"{item['figure']} {item['label']}".replace("\n", " ") == "3 trades we could not size"


@pytest.mark.parametrize(("rate", "said"), [
    ("45.8", "46 of 100"), ("45.5", "46 of 100"), ("45.4", "45 of 100"), ("100", "100 of 100"),
    ("0", "0 of 100"),
])
def test_a_rate_is_a_count_out_of_a_hundred(rate, said):
    assert formatting.out_of_a_hundred(rate) == said


def test_a_wide_count_stands_alone_over_the_short_words_on_a_phone():
    wide = SF._trades_wedge(167, "past your number", "past number")
    assert (wide["figure"], wide["phone_figure"], wide["phone_label"]) == (
        "167 trades", "167", "past number")
    assert "phone_figure" not in SF._trades_wedge(99, "on your busiest day", "busiest day")


@pytest.mark.parametrize(("n", "of", "phone"), [
    (99, "past your number", "past number"), (167, "past your number", "past number"),
    (1600, "we could not size", "not sized"), (1234, "on your busiest day", "busiest day"),
])
def test_a_count_of_any_size_stays_clear_on_a_phone(n, of, phone):
    item = SF._trades_wedge(n, of, phone)
    z = G.SIZES["phone"]
    rr, sec = G.radii(z["R"]), G.sectors(4, True)
    block = G.slice_block({"figure": item.get("phone_figure", item["figure"]),
                           "label": item["phone_label"]}, min(D.HUB_FIG_SIZES_PHONE), False)
    best, rc = -1e9, rr["ring"]
    while rc <= rr["inner"]:
        best = max(best, G.block_clearance(sec["slices"][0], sec["span"], rc, block, rr))
        rc += 0.5
    assert best >= FIT_ON_A_PHONE


def test_one_trade_is_one_trade():
    assert SF._trades(1).with_noun == "1 trade"


def test_a_figure_says_itself_with_its_noun():
    assert Figure(8, "trades").with_noun == "8 trades"


def test_the_label_breaks_on_whole_words():
    assert SF._lines("lost 36% of all you lost") == "lost 36% of\nall you lost"
    assert SF._lines("is set") == "is set"
    assert SF._lines("busiest day,\n17\xa0Aug\xa02026") == "busiest day,\n17\xa0Aug\xa02026"


def test_the_phone_gets_its_short_form_and_the_desktop_the_agreed_one():
    view = {"kind": "home", "centre": {"figure": "−₹1", "captionLines": ["your result,", "before charges"]},
            "items": [{"name": str(i), "figure": "8 trades", "label": "on your\nbusiest day",
                       "phone_label": "busiest day", "state": "", "href": "#"} for i in range(4)]}
    phone, desktop = str(D.scope_dial(view, "phone")), str(D.scope_dial(view, "desktop"))
    assert "on your" not in phone and "busiest day" in phone
    assert "on your" in desktop


def test_a_dial_with_no_short_form_keeps_the_kits_sizes():
    """Only a hub answer takes the smaller figure, so the kit's own dials draw as the kit draws."""
    view = {"kind": "home", "centre": {"figure": "−₹1", "captionLines": ["a", "b"]},
            "items": [{"name": str(i), "figure": "9", "state": "", "href": "#"} for i in range(4)]}
    assert "scope__figure--s22" in str(D.scope_dial(view, "phone"))


@pytest.mark.parametrize("size", ["phone", "desktop"])
def test_every_chapter_dial_stays_clear_inside_its_wedge(pages, size):
    """The drawn wedges, at the size each is drawn, against the layout's own measure."""
    from tests.unit.api.test_hub_answers import CTX, IMP

    figs = SF.facts(CTX, IMP)
    z = G.SIZES[size]
    rr = G.radii(z["R"])
    for n in (1, 2, 3, 4):
        view = SF.chapter_view(n, figs)
        items = view["items"] if size == "desktop" else [
            {**i, "figure": i.get("phone_figure", i["figure"]),
             "label": i.get("phone_label", i.get("label", ""))} for i in view["items"]]
        sec = G.sectors(len(items), False)
        lay = G.layout_contents(items, sec, rr, z["figSizesChapter"])
        for i, block in enumerate(lay["blocks"]):
            clear = G.block_clearance(sec["slices"][i], sec["span"], lay["radius"][i], block, rr)
            assert clear >= FIT_ON_A_PHONE, (n, view["items"][i]["name"], clear)


def test_the_centre_keeps_its_figure_and_its_qualifier_together(pages):
    svg = dials(pages["/mirror"])[0]
    text = unescape(re.sub(r"<[^>]+>", " ", svg))
    assert "your result," in text and "before charges" in text
    assert re.search(r"−₹[\d,]+|\+₹[\d,]+", text), "the sign stays with its number"
    assert not re.search(r"−\s+₹", text)


def test_the_demo_is_all_this_reads(pages):
    assert "This is a demo file, not your trading." in pages["/mirror"]


def test_the_kit_stylesheet_is_untouched():
    import hashlib
    from pathlib import Path

    from tests.unit.api.test_figures import KIT_SHA

    css = Path("services/production/api/static/css/components.css").read_bytes()
    assert hashlib.sha256(css).hexdigest() == KIT_SHA
