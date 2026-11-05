"""A figure on a dial means something alone, and no bare digit sits beside it [TICKET-843].

Each slice drew a serial directly above its figure, so the eye read "4 / 80 of 80" or
"3 / 17" as one thing. The serial goes, in the one place a page's dial is drawn, and each
figure carries its unit or label in the same block.

The kit's own output stays byte for byte what test_scope_geometry records: dropping the serial
is an option the app's door sets, as the centre's caption lines are.
"""

from __future__ import annotations

import os
import re
from dataclasses import replace
from html import unescape
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services.production.api import dial as D
from services.production.api import scope_facts as SF
from services.production.api import scope_geometry as G
from services.production.api.app import create_app
from services.production.db.session import make_engine, run_migrations
from tests.unit.api.test_scope_chapters import IMP, TRIPS, chapter_page
from tests.unit.api.test_upload import sign_up, upload

DEMO = Path("data/fixtures/demo/demo_tradebook.csv")
HUB = "/mirror"
CHAPTERS = [f"/mirror/chapter/{n}" for n in (1, 2, 3, 4)]
BARE = re.compile(r"^[−+\-₹\d.,:%×\s]+$")
VIEW = {
    "kind": "chapter",
    "items": [
        {"name": "One", "figure": "15.8%", "label": "strike rate", "href": "/a"},
        {"name": "Two", "figure": "10 trades", "href": "/b"},
    ],
    "centre": {"name": "A chapter", "scopeHref": "/c"},
}


@pytest.fixture(scope="module")
def pages(tmp_path_factory):
    """The hub and the four chapters, as served for the synthetic demo file."""
    root = tmp_path_factory.mktemp("dial")
    saved = {k: os.environ.get(k) for k in ("SCOPE_DB", "SCOPE_FILES", "SCOPE_SECRET_KEY", "SCOPE_FILE_KEY")}
    from services.production.accounts.file_store import generate_key

    os.environ.update(SCOPE_DB=f"sqlite:///{(root / 'd.db').as_posix()}", SCOPE_FILES=str(root / "files"),
                      SCOPE_SECRET_KEY="x" * 40, SCOPE_FILE_KEY=generate_key())
    try:
        engine = make_engine(os.environ["SCOPE_DB"])
        run_migrations(engine)
        client = sign_up(TestClient(create_app()), engine, "U", "demo")
        assert upload(client, path=DEMO).status_code == 303
        got = {path: client.get(path).text for path in (HUB, *CHAPTERS)}
        engine.dispose()
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return got


def slices(html: str) -> list[list[tuple[str, str]]]:
    """Every slice's drawn text as (class, words). The name sits on the rim, outside the slice."""
    out = []
    for block in re.findall(r'<a class="scope__slice.*?</a>', html, flags=re.S):
        texts = re.findall(r'<text class="scope__([a-z-]+)[^"]*"[^>]*>(.*?)</text>', block, flags=re.S)
        out.append([(c, unescape(re.sub(r"<[^>]+>", " ", t)).strip()) for c, t in texts])
    return out


def by_name(html: str) -> dict[str, list[tuple[str, str]]]:
    blocks = re.findall(r'<a class="scope__slice.*?</a>', html, flags=re.S)
    names = [unescape(re.search(r'aria-label="\d+\. ([^"]*)\."', b).group(1)) for b in blocks]
    return dict(zip(names, slices(html), strict=True))


@pytest.mark.parametrize("path", [HUB, *CHAPTERS])
def test_the_page_draws_a_dial_to_check(pages, path):
    assert slices(pages[path])


@pytest.mark.parametrize("path", [HUB, *CHAPTERS])
def test_no_slice_holds_a_lone_digit(pages, path):
    for texts in slices(pages[path]):
        assert not [w for _, w in texts if re.fullmatch(r"\d", w)], texts


@pytest.mark.parametrize("path", [HUB, *CHAPTERS])
def test_no_serial_is_drawn(pages, path):
    assert "scope__number" not in pages[path]


@pytest.mark.parametrize("path", [HUB, *CHAPTERS])
def test_every_figure_has_a_unit_or_a_label_beside_it(pages, path):
    for texts in slices(pages[path]):
        figures = [w for c, w in texts if c.split()[0] == "figure"]
        siblings = [w for c, w in texts if c in ("figure-tail", "state")]
        for figure in figures:
            assert not BARE.match(figure) or siblings, texts


def test_the_strike_rate_says_what_it_is(pages):
    texts = by_name(pages["/mirror/chapter/2"])["The math of your trading"]
    assert ("figure-tail", "strike rate") in texts


def test_the_hour_says_what_it_is(pages):
    assert ("figure-tail", "largest result") in by_name(pages["/mirror/chapter/2"])["The clock"]


def test_the_two_losses_count_says_what_it_counts(pages):
    texts = by_name(pages["/mirror/chapter/3"])["After two straight losses"]
    assert ("figure-tail", "after two losses") in texts
    assert ("figure", "17 trades") in texts


def test_the_rows_say_they_were_read(pages):
    texts = by_name(pages["/mirror/chapter/4"])["What we read"]
    assert ("figure-tail", "of 80 rows read") in texts


def test_the_count_of_what_was_not_told_says_what_it_counts(pages):
    texts = dict(by_name(pages["/mirror/chapter/4"])["What we have not told you"])
    assert " ".join([texts["figure"], texts.get("figure-tail", "")]).strip() == "4 things"


def test_the_risk_count_says_what_it_counts():
    context = SF.record_context(TRIPS)
    context = {**context, "risk": replace(context["risk"], showable=3)}
    figs = SF.facts(context, IMP)
    if figs["risk"]["state"]:
        figs["risk"] = {**figs["risk"], "state": ""}
    assert figs["risk"]["dial_figure"].endswith(" trades")


def test_a_figure_in_a_state_shows_the_state_and_no_label():
    built = G.slice_block({"figure": "15.8%", "label": "strike rate", "state": "not-enough"}, 22, False)
    assert built["head"] == "—"
    assert built["tail"] == ""


# ---------- How it is drawn ----------


def test_the_label_is_the_line_under_the_figure():
    d = G.build_dial(VIEW, "phone", {"serials": False})
    assert d["slices"][0]["contents"]["head"] == "15.8%"
    assert d["slices"][0]["contents"]["tail"] == "strike rate"


def test_without_a_serial_the_figure_takes_its_place():
    d = G.build_dial(VIEW, "phone", {"serials": False})
    c = d["slices"][1]["contents"]
    assert c["headY"] == c["numberY"]


def test_without_a_serial_the_block_is_shorter_so_it_stays_centred():
    with_serial = G.slice_block(VIEW["items"][1], 22, False)
    without = G.slice_block(VIEW["items"][1], 22, False, serial_row=0)
    assert with_serial["h"] - without["h"] == 17


def test_the_kit_still_draws_its_serial_when_nobody_asks_otherwise():
    assert "scope__number" in G.render_dial_svg(G.build_dial(VIEW, "phone", {}))


def test_the_one_door_a_page_draws_through_leaves_it_out():
    assert "scope__number" not in str(D.scope_dial(VIEW))


def test_a_label_that_would_break_the_markup_is_refused():
    view = {**VIEW, "items": [{**VIEW["items"][0], "label": 'a"b'}, VIEW["items"][1]]}
    with pytest.raises(ValueError, match="double quote"):
        D.scope_dial(view)


def test_the_slice_keeps_its_order_for_a_screen_reader(pages):
    labels = re.findall(r'<a class="scope__slice[^>]*aria-label="(\d)\. ', pages[HUB])
    assert labels == ["1", "2", "3", "4"]


# ---------- What stays ----------


def test_a_facts_serial_beside_its_title_stays():
    assert "story-card__num" in chapter_page(1, TRIPS)


def test_home_keeps_saying_open_or_read(pages):
    assert {w for texts in slices(pages[HUB]) for c, w in texts if c.split()[0] == "figure"} == {"Open"}
